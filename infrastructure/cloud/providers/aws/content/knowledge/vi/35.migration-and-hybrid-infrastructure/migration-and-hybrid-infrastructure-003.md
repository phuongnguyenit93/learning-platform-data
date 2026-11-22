# AWS Migration Hub và theo dõi tiến độ di chuyển

Di chuyển hệ thống lên AWS là một chương trình nhiều giai đoạn: khám phá hạ tầng hiện tại, hiểu phụ thuộc giữa ứng dụng, đánh giá chi phí, lập kế hoạch theo đợt, thực hiện di chuyển, kiểm thử và chuyển lưu lượng. Một tổ chức có thể dùng nhiều công cụ khác nhau cho máy chủ, cơ sở dữ liệu, container và ứng dụng doanh nghiệp. Nếu mỗi nhóm theo dõi trong một bảng riêng, người quản lý khó biết ứng dụng nào đã sẵn sàng, máy chủ nào đang sao chép dữ liệu, tác vụ nào bị lỗi và đợt di chuyển nào có nguy cơ trễ.

AWS Migration Hub được thiết kế để tập trung trạng thái di chuyển từ nhiều công cụ AWS và đối tác vào một nơi. Dịch vụ liên kết tài nguyên nguồn với ứng dụng, hiển thị các lần cập nhật và giúp theo dõi tiến độ ở cấp máy chủ, database và application. Migration Hub không tự thực hiện mọi hoạt động sao chép hay chuyển đổi; các công cụ như AWS Application Migration Service (AWS MGN) và AWS Database Migration Service (AWS DMS) thực hiện công việc chuyên biệt rồi gửi trạng thái về Hub.

**Lưu ý về vòng đời dịch vụ tại ngày 20-11-2026:** AWS Migration Hub và AWS Application Discovery Service đã ngừng nhận khách hàng mới từ ngày 07-11-2025. Khách hàng hiện hữu có thể tiếp tục dùng các dự án đang triển khai để hoàn tất migration; AWS không bổ sung tính năng mới cho Migration Hub. AWS Transform là hướng thay thế được AWS khuyến nghị cho các dự án mới, với discovery, assessment, migration planning, wave execution và theo dõi tiến độ được mở rộng. Bài học giải thích Migration Hub để người học hiểu cách các dự án hiện hữu được theo dõi, đồng thời trình bày AWS Transform là quy trình hiện hành cho chương trình di chuyển mới.

## Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích vai trò của AWS Migration Hub trong một chương trình migration nhiều công cụ.
- Phân biệt discovery, assessment, migration planning, execution, cutover và post-migration validation.
- Hiểu home Region và lý do dữ liệu Migration Hub được tập trung tại một Region.
- Đọc inventory máy chủ, grouping theo application và migration updates.
- Phân biệt trạng thái ứng dụng với trạng thái task của công cụ di chuyển.
- Kết hợp AWS MGN, AWS DMS, Migration Hub Orchestrator và các công cụ đối tác trong một kế hoạch theo dõi.
- Sử dụng API/CLI của Migration Hub để tích hợp một migration tool tùy chỉnh.
- Theo dõi migration wave, replication, test, cutover, SLA và rủi ro tồn đọng.
- Giải thích lộ trình chuyển sang AWS Transform cho các dự án mới.

## 1. AWS Migration Hub giải quyết vấn đề gì?

AWS Migration Hub là nơi tập trung thông tin tiến độ từ các công cụ migration được kết nối. Dịch vụ giúp nhóm có góc nhìn thống nhất về:

- Máy chủ và database đang được di chuyển.
- Ứng dụng gồm những tài nguyên nào.
- Công cụ nào đang thực hiện từng migration task.
- Task đang ở trạng thái nào và lần cập nhật gần nhất là khi nào.
- Ứng dụng nào chưa bắt đầu, đang di chuyển hoặc đã hoàn tất.
- Những resource hoặc update chưa được map đúng vào application.

Migration Hub đặc biệt hữu ích khi một chương trình có nhiều nhóm cùng làm việc: nhóm infrastructure rehost EC2, nhóm database dùng DMS, nhóm SAP dùng workflow chuyên biệt và nhóm ứng dụng phối hợp kiểm thử/cutover.

Migration Hub cung cấp khả năng tổng hợp và tracking. Việc thực hiện migration vẫn nằm ở công cụ chuyên dụng:

| Nhu cầu | Công cụ thực hiện | Vai trò của Migration Hub |
|---|---|---|
| Rehost server từ data center lên EC2 | AWS Application Migration Service (MGN) | Nhận cập nhật lifecycle/tiến độ của server và nhóm server theo application. |
| Di chuyển hoặc replicate database | AWS Database Migration Service (DMS) | Tổng hợp trạng thái migration task và tài nguyên database. |
| Điều phối workflow có nhiều bước | Migration Hub Orchestrator đối với khách hàng hiện hữu | Hiển thị tiến độ workflow và các bước cần hoàn thành. |
| Di chuyển bằng công cụ đối tác | Migration tool tích hợp | Nhận các migration updates mà công cụ gửi tới Hub. |
| Di chuyển mới, lập kế hoạch theo wave | AWS Transform | Cung cấp discovery, assessment, planning, execution và báo cáo tiến độ cho dự án mới. |

Không nên coi Migration Hub là một công cụ thay thế MGN hoặc DMS. Hub giúp trả lời “toàn bộ chương trình đang ở đâu?”; công cụ chuyên biệt trả lời “tác vụ kỹ thuật đang chạy thế nào và cần thao tác gì tiếp theo?”.

## 2. Tình trạng dịch vụ và lựa chọn lộ trình

### 2.1. AWS Migration Hub dành cho khách hàng hiện hữu

AWS thông báo Migration Hub ngừng nhận khách hàng mới từ ngày 07-11-2025. Các khách hàng đã sử dụng dịch vụ có thể tiếp tục truy cập dữ liệu lịch sử và hoàn tất dự án đang chạy. AWS tiếp tục duy trì tính ổn định và cập nhật bảo mật, nhưng không bổ sung tính năng mới.

AWS Application Discovery Service cũng đóng đăng ký khách hàng mới từ cùng ngày. Các dự án discovery hiện hữu có thể tiếp tục đến khi hoàn tất. Do đó, các hướng dẫn về Discovery Agent, Agentless Collector, Migration Hub import và Orchestrator trong bài này áp dụng cho môi trường khách hàng hiện hữu đã có quyền sử dụng các dịch vụ đó.

### 2.2. AWS Transform cho dự án mới

AWS Transform là dịch vụ thế hệ mới được AWS khuyến nghị cho các dự án migration mới. Dịch vụ cung cấp trải nghiệm agentic AI để hỗ trợ discovery, assessment, lập kế hoạch migration wave, tạo landing zone, migration network, rehost server và các quy trình modernization được hỗ trợ.

Một số điểm cần biết:

- Không cần thực hiện một quy trình chuyển dữ liệu riêng từ Migration Hub sang AWS Transform. Dự án Migration Hub hiện hữu tiếp tục chạy đến khi hoàn tất; dự án mới có thể bắt đầu trực tiếp trong AWS Transform.
- AWS Transform có thể nhập inventory, phân tích dependency, gom application, tạo move groups và lập migration waves.
- Assessment và migration planning có thể chạy độc lập sau discovery hoặc kết hợp trong cùng migration job.
- Bản cập nhật ngày 06-11-2026 cho phép migration job kết hợp discovery, assessment và wave planning trong cùng một job.
- AWS Transform hỗ trợ báo cáo tổng hợp workspace về trạng thái job, bước workflow, approvals, wave plan, network topology, rehost progress và artifacts.

AWS Transform dùng AI để phân tích và đề xuất công việc. Các thay đổi quan trọng như xác nhận inventory, phê duyệt, cutover và triển khai production vẫn cần người có trách nhiệm kiểm tra theo quy trình tổ chức.

### 2.3. Chọn lộ trình theo trạng thái tài khoản

| Tình huống | Lộ trình phù hợp |
|---|---|
| Đang có dự án Migration Hub/Orchestrator chạy trước 07-11-2025 | Tiếp tục dự án hiện hữu trong Migration Hub đến khi hoàn tất; liên hệ AWS Support khi cần trợ giúp. |
| Đã dùng Application Discovery Service và đang hoàn thành discovery | Tiếp tục dự án hiện hữu; dùng dữ liệu đã thu thập để hoàn tất kế hoạch theo phạm vi được hỗ trợ. |
| Bắt đầu một chương trình migration mới | Bắt đầu bằng AWS Transform. |
| Cần rehost server bằng MGN hoặc migrate database bằng DMS | Dùng công cụ chuyên biệt phù hợp; tích hợp tiến độ vào quy trình quản lý migration được tổ chức chọn. |
| Cần điều phối một workflow cũ đã được tạo trong Migration Hub Orchestrator | Tiếp tục workflow hiện hữu theo quyền truy cập của khách hàng hiện hữu; các dự án mới dùng AWS Transform. |

## 3. Các khái niệm chính trong Migration Hub

Migration Hub có ba khái niệm cốt lõi:

1. **Application:** nhóm logic gồm một hoặc nhiều resource cùng phục vụ một ứng dụng hoặc business capability.
2. **Resource:** máy chủ, database hoặc tài nguyên nguồn được migration tool nhận diện.
3. **Update:** thông tin trạng thái/progress mà migration tool gửi về Hub cho một resource hoặc migration task.

Các khái niệm khác:

| Khái niệm | Ý nghĩa |
|---|---|
| Home Region | Region trung tâm lưu trữ discovery data và migration tracking data của Migration Hub trong một AWS account. |
| Migration tool | Công cụ thực hiện migration và gửi trạng thái về Hub, ví dụ MGN, DMS hoặc partner tool. |
| Progress update stream | Namespace nhận diện migration tool; đồng thời là ranh giới cấp quyền cho các migration task của tool. |
| Migration task | Tác vụ di chuyển một server, database hoặc resource cụ thể. |
| Migration wave | Nhóm application được lên kế hoạch di chuyển cùng một đợt; khái niệm này được dùng nổi bật trong AWS Transform. |
| Move group | Tập hợp application phụ thuộc lẫn nhau cần được chuyển cùng nhau trong wave planning. |
| Cutover | Thời điểm chuyển workload production từ môi trường nguồn sang môi trường đích. |

Một application trong Migration Hub là nhóm logic phục vụ tracking. Việc tạo application trong Hub không tự động tạo AWS resource, không thay đổi DNS và không di chuyển dữ liệu.

## 4. Home Region và dữ liệu tập trung

### 4.1. Vì sao cần home Region?

Migration Hub yêu cầu chọn home Region trước khi thực hiện discovery hoặc migration tracking. Dữ liệu được tập trung tại home Region để nhóm có một nơi xem inventory, application grouping và migration updates, kể cả khi tài nguyên đích được triển khai ở Region khác.

Các nguyên tắc:

- Chọn một Region được Migration Hub hỗ trợ cho account.
- Chọn home Region trước khi cài data collectors hoặc gửi migration updates.
- Xem dashboard và application details tại home Region.
- Các API write như create, notify, associate, disassociate, import và put phải được gọi từ home Region.
- Các thao tác read như list và describe có thể được hỗ trợ ngoài home Region, nhưng nên chuẩn hóa automation ở home Region để tránh lỗi endpoint.
- Thay đổi home Region có thể khiến phải thu thập lại dữ liệu; dữ liệu của home Region cũ không tự chuyển sang Region mới.

AWS hướng dẫn khách hàng liên hệ AWS Support khi cần thay đổi home Region. Không nên chọn Region chỉ theo thói quen hoặc theo Region đích của workload; hãy xem nơi lưu trữ dữ liệu migration và khả năng truy cập của nhóm điều phối.

### 4.2. Kiểm tra home Region

Với khách hàng Migration Hub hiện hữu, có thể kiểm tra bằng AWS CLI:

~~~bash
aws migrationhub-config get-home-region
~~~

Lệnh gọi API GetHomeRegion trả về home Region của account nếu đã cấu hình. Theo tài liệu AWS, nên gọi API này trước các API khác của Application Discovery Service và Migration Hub để xác định endpoint Region cần sử dụng.

Nếu home Region chưa được cấu hình, các write operation có thể trả HomeRegionNotSetException. Nếu gọi write API từ Region khác, có thể nhận InvalidInputException.

## 5. Discovery và thu thập inventory

Discovery giúp trả lời: tổ chức đang có những server/database nào, cấu hình ra sao, sử dụng tài nguyên thế nào và phụ thuộc vào hệ thống nào?

Với khách hàng hiện hữu của Application Discovery Service, có ba cách thu thập dữ liệu phổ biến:

| Phương thức | Cách triển khai | Dữ liệu điển hình |
|---|---|---|
| Agentless Collector | Cài VM appliance OVA trong VMware vCenter. | VM/host inventory, CPU/RAM/disk, utilization, database metadata và network traffic giữa server. |
| Discovery Agent | Cài agent trên từng máy chủ vật lý hoặc VM Linux/Windows. | Cấu hình, time-series utilization, process đang chạy và TCP network connections. |
| File-based import | Import dữ liệu inventory từ file được hỗ trợ. | Phụ thuộc các trường có trong file; phù hợp khi đã có inventory từ CMDB hoặc công cụ khác. |

### 5.1. Agentless Collector

Agentless Collector phù hợp khi môi trường dùng VMware vCenter và tổ chức muốn giảm việc cài agent trên từng server. Collector được triển khai như một VM trong môi trường VMware và dùng các module thu thập dữ liệu.

Một số loại dữ liệu:

- Hostname, IP, MAC và thông tin VM.
- Số CPU, RAM và dung lượng disk.
- Average/peak utilization.
- Metadata của database và analytics server qua module tương ứng.
- Network traffic giữa các server theo khả năng collector hỗ trợ.

Agentless không có cùng độ chi tiết với agent-based discovery. Nếu cần process-level inventory hoặc time-series network/process detail trên từng host, cần xem khả năng của phương thức thu thập khác.

### 5.2. Discovery Agent

Discovery Agent được cài trên từng server vật lý hoặc VM. Agent chạy với quyền hệ thống cần thiết để thu thập cấu hình, process và network connection. Dữ liệu được truyền an toàn qua TLS về home Region.

Discovery Agent có thể thu thập:

- OS, CPU, RAM, disk và cấu hình host.
- Utilization theo thời gian.
- Process đang chạy.
- Inbound/outbound TCP connections.
- Thông tin hỗ trợ xác định dependency giữa các máy chủ.

Trước khi triển khai agent, cần kiểm tra OS support, quyền cài đặt, network egress, proxy và yêu cầu bảo mật nội bộ. Không cài agent đại trà trước khi có phê duyệt từ owner của server.

### 5.3. File import và dữ liệu đối tác

Nếu tổ chức đã có CMDB, RVTools export hoặc dữ liệu inventory từ công cụ đối tác, có thể dùng file-based import hoặc tích hợp đối tác trong môi trường Migration Hub hiện hữu. Cần chuẩn hóa hostname, IP, MAC, FQDN và server identifiers để tránh tạo bản ghi trùng.

Với dự án mới, AWS Transform cung cấp discovery inventory import và các collector/khả năng phân tích mới. Hãy dùng hướng dẫn AWS Transform thay vì bắt đầu một triển khai Application Discovery Service mới.

### 5.4. Chất lượng inventory

Một inventory có giá trị cần có:

- Server ID ổn định và hostname đã chuẩn hóa.
- Environment, application, owner và business criticality.
- OS, CPU, RAM, storage và utilization.
- IP, subnet, network zone và các connection quan trọng.
- Database engine/version, size, throughput và dependency.
- Licensing, support lifecycle và constraint.
- Thời điểm thu thập và mức độ đầy đủ của dữ liệu.

Không dùng inventory thiếu utilization để chốt instance size hoặc business case cuối cùng. Thiếu dữ liệu nên được ghi thành assumption/risk và có người chịu trách nhiệm bổ sung.

## 6. Gom server thành application

Migration Hub cho phép nhóm discovered servers thành application. Một application có thể chứa web tier, application tier, database, message broker và các thành phần cần được di chuyển phối hợp.

Cách grouping nên kết hợp hai loại quan hệ:

- **Technical dependency:** ứng dụng gọi database, message queue, shared file system, authentication service hoặc một application khác.
- **Business/operational dependency:** cùng business capability, owner, maintenance window, data center, RTO/RPO hoặc quy trình kiểm thử.

Với Migration Hub hiện hữu, nhóm có thể vào Servers, tìm/lọc server theo metadata, chọn các server và dùng Group as application để tạo application mới hoặc thêm vào application đã có. Có thể gắn tags để lưu application, owner, environment hoặc wave.

Trước khi lưu grouping, kiểm tra:

1. Các server có thực sự thuộc cùng application boundary không?
2. Database/shared service có được nhiều application dùng chung không?
3. Có dependency đồng bộ hoặc yêu cầu cutover cùng lúc không?
4. Owner và người kiểm thử đã được xác định chưa?
5. Có resource nào đang thiếu inventory hoặc sai mapping không?

Không gom tất cả server trong cùng subnet thành một application. Subnet là một thuộc tính network; application boundary cần phản ánh dependency và mục tiêu nghiệp vụ.

### 6.1. Kiểm tra mapping migration updates

Khi migration tool gửi update, Migration Hub cố gắng map update vào server đã discovery bằng các thuộc tính như IP, MAC, FQDN hoặc VMware identifiers. Mapping tự động có thể sai hoặc không tìm được server.

Nếu update không xuất hiện trong application:

- Mở trang Updates và kiểm tra update có được nhận hay không.
- Kiểm tra cột Mapped servers.
- Xác minh update có map tới đúng server không.
- Nếu sai, dùng chức năng Edit server mapping.
- Quay lại Servers để xác nhận server đã được group vào đúng application.
- Refresh application details để xem trạng thái mới.

Một update có thể hiển thị ở trang Updates nhưng chưa xuất hiện trong application nếu server chưa được group hoặc mapping chưa chính xác.

## 7. Migration planning và migration waves

Migration wave là một nhóm application được di chuyển trong cùng một đợt. Wave planning cần xét dependency, mức độ quan trọng, khả năng kiểm thử, năng lực đội vận hành, thời gian downtime và điều kiện cutover.

Với AWS Transform, migration planning có bốn giai đoạn:

1. **Scope and analyze:** xem inventory, xác định server thuộc phạm vi migration và phân tích software/network dependency.
2. **Group apps:** gom server thành application dựa trên hostname, network dependency, business rules hoặc inventory đã có.
3. **Generate move groups:** nhóm các application phụ thuộc nhau, ví dụ dùng chung database, queue hoặc business function.
4. **Build waves:** sắp xếp move groups vào wave theo ưu tiên, kích thước, số người dùng, độ phức tạp và timeline.

Một move group là tập application phụ thuộc nhau cần chuyển cùng nhau. Một wave có thể gồm một hoặc nhiều move group.

### 7.1. Phân loại dependency

| Loại dependency | Ví dụ | Tác động tới wave |
|---|---|---|
| Hard/critical dependency | Application cần database hoặc shared service để khởi động. | Thường cần migrate cùng wave hoặc có bridge connectivity rõ ràng. |
| Soft dependency | Hệ thống báo cáo có thể đọc dữ liệu trễ vài phút. | Có thể migrate ở wave khác nếu chấp nhận độ trễ. |
| Business dependency | Hai application hỗ trợ cùng quy trình nghiệp vụ và cùng maintenance window. | Có thể cần cutover đồng bộ dù không có dependency network trực tiếp. |
| Operational dependency | Cùng owner, team, data center hoặc change window. | Cần phối hợp nguồn lực và lịch release. |

### 7.2. Tiêu chí sắp xếp wave

Có thể dùng ma trận sau để lên kế hoạch:

| Tiêu chí | Câu hỏi |
|---|---|
| Business criticality | Nếu cutover lỗi, tác động tới doanh thu/khách hàng là gì? |
| Dependency | Những application/resource nào phải chuyển cùng nhau? |
| Complexity | Có nhiều integration, batch job, shared database hoặc protocol cũ không? |
| Data volume | Dung lượng và tốc độ thay đổi dữ liệu ảnh hưởng thời gian replication thế nào? |
| RTO/RPO | Workload cần phục hồi trong bao lâu và có thể mất tối đa bao nhiêu dữ liệu? |
| Owner readiness | Nhóm ứng dụng, database, network và security đã sẵn sàng chưa? |
| Testability | Có test data, test environment và business acceptance criteria không? |
| Target readiness | Landing zone, network, IAM, quota, logging và backup đã sẵn sàng chưa? |

Nên bắt đầu với wave pilot có phạm vi nhỏ và dependency dễ kiểm soát. Kết quả pilot giúp hiệu chỉnh runbook, thời gian thực hiện và checklist trước khi tăng quy mô.

## 8. Kết nối migration tools với Migration Hub

Migration Hub nhận status updates từ migration tools. Trước khi tracking, khách hàng hiện hữu cần kết nối/authorize công cụ trong phần Tools của console hoặc cấu hình IAM role phù hợp.

Các tích hợp thường gặp:

- **AWS MGN:** rehost server và gửi trạng thái replication/test/cutover.
- **AWS DMS:** full load, change data capture (CDC), task state và table statistics.
- **Migration Hub Orchestrator:** workflow theo template với các bước được điều phối.
- **Partner migration tools:** gửi status qua integration/API theo phạm vi được hỗ trợ.
- **Custom migration tool:** dùng Migration Hub API để đăng ký task và gửi tiến độ.

Việc connect tool là một bước cấp quyền. Nếu tool chưa được authorize hoặc thiếu IAM role, Hub có thể không nhận được update dù tác vụ migration vẫn chạy trong console riêng của công cụ.

### 8.1. AWS Application Migration Service (MGN)

MGN là công cụ chính cho lift-and-shift/rehost server lên Amazon EC2. MGN sao chép block-level data từ source server sang staging area trong AWS, sau đó cho phép launch test instance và cutover instance.

Các trạng thái lifecycle thường gặp:

| Lifecycle | Ý nghĩa |
|---|---|
| Not ready | Đang initial sync; chưa sẵn sàng launch test. |
| Ready for testing | Replication đã bắt đầu và có thể launch test instance. |
| Test in progress | Test instance đang được launch hoặc kiểm thử. |
| Ready for cutover | Đã kiểm thử và sẵn sàng cutover. |
| Cutover in progress | Cutover instance đang được launch. |
| Cutover complete | Dữ liệu đã được chuyển sang cutover instance. |
| Disconnected | Server đã ngắt khỏi MGN. |

Lifecycle status cần đọc cùng replication health/lag, launch status, last test và cảnh báo. Ví dụ, Ready for testing không có nghĩa application đã pass UAT; nó chỉ cho biết có thể bắt đầu test instance.

### 8.2. AWS Database Migration Service (DMS)

DMS hỗ trợ full load, ongoing replication/CDC hoặc các kiểu migration phù hợp với engine nguồn/đích. Khi theo dõi, cần xem đồng thời:

- Task status: Running, Stopped, Failed, Error hoặc trạng thái chuyển tiếp.
- Table state: Before load, Full load, Table completed hoặc Table error.
- Full load progress và số bảng đã tải.
- CDC latency và backlog nếu đang replicate ongoing changes.
- CloudWatch metrics, task logs và DMS events.

Không dựa duy nhất vào phần trăm hoàn thành. DMS có thể ước lượng progress từ table statistics; nếu source table thiếu thống kê số hàng, task status vẫn có thể Running nhưng thanh phần trăm không di chuyển. Khi đó, xem rows loaded, table state, CDC latency và log.

Đối với homogeneous data migrations, console có các trạng thái cụ thể như Load running, Load complete, replication ongoing, Replication ongoing, Stopped, Failed và Maintenance. Những trạng thái này thuộc DMS; không đồng nhất chúng với ApplicationStatus của Migration Hub.

### 8.3. Migration Hub Orchestrator

Orchestrator giúp khách hàng Migration Hub hiện hữu tạo workflow theo template và theo dõi step groups/steps. Các template được công bố gồm:

- Migrate SAP NetWeaver applications to AWS.
- Rehost applications on Amazon EC2 bằng MGN.
- Rehost SQL Server on Amazon EC2 bằng backup/restore.
- Replatform SQL Server to Amazon RDS.
- Replatform applications to Amazon ECS.
- Import virtual machine images to AWS.
- Custom templates được tạo từ template hiện có.

Một số template cần Orchestrator plugin tại on-premises để kết nối source/target environment. Workflow có thể chứa step groups, step phụ thuộc, script chạy ở on-premises hoặc AWS, cùng các bước cần người dùng chú ý.

Đối với dự án mới, dùng AWS Transform để lập và điều phối migration workflow thay cho việc bắt đầu Migration Hub Orchestrator mới.

## 9. Theo dõi tiến độ trong Migration Hub dashboard

Dashboard Migration Hub tổng hợp thông tin discovery và migration. Nhóm có thể xem số server, application, data collectors và trạng thái application được cập nhật gần đây.

Một quy trình kiểm tra:

1. Mở Migration Hub tại home Region.
2. Vào Dashboard và xem Discovery summary.
3. Mở Most recently updated applications.
4. Chọn application cần theo dõi.
5. Kiểm tra danh sách server, migration tool, task updates và trạng thái từng resource.
6. Mở Updates để xem các lần migration tool gửi trạng thái.
7. Đối chiếu với MGN/DMS console khi cần điều tra chi tiết.
8. Refresh application details sau khi có update mới.

Migration Hub có thể mất tối đa khoảng 5 phút để hiển thị update đầu tiên sau khi nhận từ migration tool. Các update sau đó phụ thuộc tần suất gửi của công cụ.

### 9.1. Trạng thái application

Migration Hub sử dụng ba trạng thái chính cho application:

| Application status | Ý nghĩa |
|---|---|
| NOT_STARTED | Migration chưa bắt đầu. |
| IN_PROGRESS | Có migration task đang thực hiện. |
| COMPLETED | Application đã được đánh dấu hoàn tất theo quy trình migration. |

Khi migration task đầu tiên của một server trong application bắt đầu, application thường tự chuyển sang IN_PROGRESS. Nếu trạng thái chưa tự cập nhật, người dùng có thể cập nhật thủ công sau khi xác minh.

Khi dữ liệu ở application details cho thấy migration đã hoàn tất, nhóm phải thực hiện testing và verification trước khi đặt application thành COMPLETED. Trạng thái này là mức tổng hợp ở application; nó không thay thế việc xác nhận từng server/database đã hoạt động đúng.

### 9.2. Trạng thái migration task

Migration Hub API sử dụng các trạng thái task:

| Task status | Ý nghĩa |
|---|---|
| NOT_STARTED | Task đã đăng ký nhưng chưa bắt đầu. |
| IN_PROGRESS | Công việc đang chạy. |
| FAILED | Task thất bại và cần điều tra. |
| COMPLETED | Công cụ báo task hoàn tất. |

Task có thể kèm ProgressPercent từ 0 đến 100 và StatusDetail để giải thích bước đang thực hiện hoặc lỗi. ProgressPercent là thông tin do migration tool gửi; không phải mọi công cụ đều có thể tính phần trăm chính xác.

### 9.3. Đọc progress đúng cách

Không nên lấy trung bình phần trăm của tất cả server để báo tiến độ toàn chương trình. Một server nhỏ và một database rất lớn không có trọng số công việc tương đương.

Nên báo cáo theo nhiều lớp:

- **Portfolio:** số application trong scope, completed, in-progress, not-started và blocked.
- **Wave:** số move group/application/server đã pass từng gate.
- **Resource:** lifecycle, replication health, task state, last update và blocker.
- **Business:** số user, giao dịch hoặc business capability đã chuyển và được owner chấp nhận.
- **Quality:** test pass rate, lỗi sau cutover, rollback và incident.
- **Schedule:** planned date, forecast date, overdue và dependency chưa sẵn sàng.

## 10. Tích hợp API để gửi trạng thái từ migration tool tùy chỉnh

Khách hàng Migration Hub hiện hữu có thể tích hợp công cụ riêng bằng Migration Hub API. Quy trình cơ bản:

1. Xác định home Region và gọi API tại Region đó.
2. Tạo ProgressUpdateStream cho migration tool.
3. Đăng ký từng migration task bằng ImportMigrationTask.
4. Map task với source resource bằng PutResourceAttributes hoặc association API.
5. Gửi trạng thái bằng NotifyMigrationTaskState.
6. Gửi cập nhật mới khi trạng thái hoặc progress thay đổi.
7. Dùng DescribeMigrationTask/ListMigrationTaskUpdates để kiểm tra thông tin đã được ghi nhận.

ProgressUpdateStream là namespace và ranh giới cấp quyền cho migration tool. MigrationTaskName định danh task trong stream; không đưa dữ liệu cá nhân hoặc secret vào tên này.

### 10.1. Tạo stream và đăng ký task

Ví dụ dùng AWS CLI v2 tại home Region:

~~~bash
aws mgh create-progress-update-stream \
  --progress-update-stream-name custom-migrator \
  --region ap-southeast-1

aws mgh import-migration-task \
  --progress-update-stream custom-migrator \
  --migration-task-name app01-web-01 \
  --region ap-southeast-1
~~~

Trong ví dụ, ap-southeast-1 chỉ là Region minh họa. Hãy thay bằng home Region đã cấu hình cho account. Task nên được đăng ký sớm, kể cả khi migration chưa bắt đầu, để người theo dõi biết task đã tồn tại.

### 10.2. Gửi cập nhật tiến độ

~~~bash
aws mgh notify-migration-task-state \
  --progress-update-stream custom-migrator \
  --migration-task-name app01-web-01 \
  --task "Status=IN_PROGRESS,StatusDetail='Copying source data',ProgressPercent=72" \
  --update-date-time 2026-11-20T05:00:00Z \
  --next-update-seconds 300 \
  --region ap-southeast-1
~~~

Các trường quan trọng:

- Status: NOT_STARTED, IN_PROGRESS, FAILED hoặc COMPLETED.
- ProgressPercent: số nguyên từ 0 đến 100, nếu công cụ có thể ước lượng.
- StatusDetail: mô tả bước đang chạy hoặc nguyên nhân lỗi.
- UpdateDateTime: thời điểm công cụ thu thập trạng thái.
- NextUpdateSeconds: số giây Hub có thể chờ update tiếp theo trước khi coi task là stale.

Công cụ cần retry khi API lỗi tạm thời/throttling và gửi update khi có thay đổi. Nếu NextUpdateSeconds quá ngắn so với chu kỳ thực tế, task có thể bị đánh dấu stale dù migration vẫn chạy.

### 10.3. Cập nhật trạng thái application

Với application đã được tạo trong Application Discovery Service, API NotifyApplicationState có thể cập nhật NOT_STARTED, IN_PROGRESS hoặc COMPLETED. Application ID là configurationId của application trong Application Discovery Service.

Không đặt application COMPLETED chỉ vì task migration đã trả COMPLETED. Cần có bước verify và business owner acceptance.

### 10.4. IAM cho custom migration tool

Chỉ cấp các action cần thiết, ví dụ:

- mgh:CreateProgressUpdateStream
- mgh:ImportMigrationTask
- mgh:NotifyMigrationTaskState
- mgh:PutResourceAttributes
- mgh:DescribeMigrationTask
- mgh:ListMigrationTasks
- mgh:GetHomeRegion

Giới hạn resource theo ARN của progress update stream và migration task khi API hỗ trợ. Không cấp mgh:* hoặc AdministratorAccess cho migration integration role chỉ để gửi tiến độ.

## 11. AWS Transform: theo dõi dự án migration mới

AWS Transform sử dụng workspace và migration jobs để quản lý một hoặc nhiều dự án. Workspace là container logic chứa jobs và artifacts; Region của workspace quyết định nơi lưu discovery data và recommendations. Target Region có thể khác workspace Region trong các cấu hình được hỗ trợ.

### 11.1. Các loại migration job

AWS Transform hỗ trợ các job type theo phạm vi:

- End-to-end migration: discovery, migration plan, connect target accounts, landing zone, network migration và server migration.
- Discovery and migration planning: thu thập inventory và xây dựng wave plan trước khi thực hiện.
- Migration assessment: đánh giá chi phí/TCO và business case trước khi quyết định phạm vi.
- Các job có thể được tùy chỉnh để thêm hoặc bỏ bước theo nhu cầu.

Từ bản cập nhật ngày 06-11-2026, discovery, assessment và migration planning có thể được thực hiện trong cùng một migration job. Discovery là đầu vào cần thiết; sau đó có thể chạy assessment, planning hoặc cả hai theo thứ tự phù hợp và chạy lại khi inventory thay đổi.

### 11.2. Discovery, assessment và planning

Quy trình điển hình:

1. Tạo migration job trong workspace.
2. Upload inventory dữ liệu máy chủ/ứng dụng.
3. Xem discovery summary và data quality warnings.
4. Điều chỉnh scope, loại trừ server ngoài phạm vi.
5. Chạy assessment để ước tính chi phí AWS, TCO và business case.
6. Phân tích dependency và group applications.
7. Tạo move groups và migration waves.
8. Review, điều chỉnh và phê duyệt wave plan.

Assessment có thể xem compute, database, storage, analytics và business value. Không dùng output TCO như báo giá cuối cùng; cần kiểm tra assumption về licensing, support, network, Region, pricing model và usage.

### 11.3. Thực thi wave

Với rehost server bằng MGN, AWS Transform hướng dẫn các bước:

1. Setup migration wave: cấu hình target account, kiểm tra quyền và tagging.
2. Validate inventory: xác nhận server configuration, instance recommendation và network assignment.
3. Deploy replication agents.
4. Replicate dữ liệu liên tục ở mức block.
5. Launch test instances và xác minh workload.
6. Cutover và kiểm tra kết quả chuyển đổi.

Các server trong cùng wave không nhất thiết phải cùng trạng thái tại mọi thời điểm. Có thể cho các server đã pass test tiếp tục sang cutover trong khi server lỗi được giữ lại để kiểm thử lại, nếu dependency và business rule cho phép.

### 11.4. Theo dõi trạng thái server và wave

AWS Transform cung cấp wave status table với thông tin lifecycle, replication status và next steps. Các lifecycle state thường gặp:

| Trạng thái | Ý nghĩa |
|---|---|
| Not ready | Initial sync chưa hoàn tất. |
| Ready for testing | Replication đã bắt đầu, có thể launch test/cutover instance. |
| Test in progress | Test instance đang được launch. |
| Ready for cutover | Server đã được test và sẵn sàng cutover. |
| Cutover in progress | Cutover instance đang được launch. |
| Cutover complete | Dữ liệu đã được chuyển sang cutover instance. |
| Disconnected | Server đã disconnect khỏi MGN. |

Có thể hỏi agent về trạng thái server, wave hoặc workflow step. Tuy nhiên, status table là công cụ hỗ trợ điều phối; vẫn phải xác minh health, test result, dependency và business acceptance.

### 11.5. Báo cáo tiến độ workspace

AWS Transform có thể tạo workspace summary report dạng PDF, tổng hợp:

- Job status và workflow step hiện tại.
- User actions và approvals.
- Wave planning details.
- Network migration topology.
- Landing zone configuration.
- Rehost progress.
- Containerization decisions.
- Artifacts được tạo trong quá trình migration.

Báo cáo này hữu ích cho steering committee và stakeholder cần xem tiến độ tổng thể. Nên kết hợp báo cáo với RAID log (Risks, Assumptions, Issues, Dependencies), timeline và KPI của chương trình.

Một số giới hạn cần lưu ý theo tài liệu hiện hành:

- Một migration job chỉ chọn một target Region.
- Có thể migrate nhiều target account trong cùng một Region nếu đáp ứng điều kiện AWS Organizations.
- Migration nhiều target Region cần tạo các project/job riêng theo Region.
- Nếu stop một migration job rồi yêu cầu agent restart, job có thể chạy lại từ đầu và mất tiến độ đã thực hiện; artifacts trước đó vẫn còn. Vì vậy, không stop/restart job như một cách khắc phục lỗi thông thường.

## 12. Đo lường tiến độ và quản lý migration portfolio

Dashboard chỉ có giá trị khi các chỉ số gắn với mục tiêu và owner. Nên xây dựng dashboard portfolio có các nhóm chỉ số:

| Nhóm | Chỉ số | Ý nghĩa |
|---|---|---|
| Inventory | Tổng server, database, application trong scope | Xác định mẫu số của chương trình. |
| Discovery coverage | Tỷ lệ resource có owner, utilization và dependency data | Đánh giá chất lượng kế hoạch. |
| Application readiness | Số application có dependency map, test plan và target design | Đo mức sẵn sàng trước migration. |
| Wave progress | Planned, in progress, blocked, completed | Theo dõi tiến độ theo đợt. |
| Replication | Replication health, lag, data transfer rate | Phát hiện nguy cơ không kịp cutover. |
| Test | Test launched, pass, fail, retest | Đánh giá chất lượng trước cutover. |
| Cutover | Planned date, actual date, success, rollback | Đo kết quả chuyển đổi. |
| Data migration | Full load, CDC latency, table errors, row counts | Đánh giá tính đầy đủ của dữ liệu. |
| Business validation | UAT pass, transaction success, owner sign-off | Xác nhận hệ thống đáp ứng nghiệp vụ. |
| Schedule | On-time wave rate, overdue tasks, dependency delay | Quản lý timeline và escalation. |
| Quality | Incident sau cutover, defect, rollback, data reconciliation | Đo chất lượng migration. |
| Cost | Cost per server/application/wave, temporary dual-run cost | Quản lý ngân sách. |

### 12.1. Không dùng một tỷ lệ duy nhất

Một chương trình có thể có 80% server đã replicate nhưng chỉ 30% application đã pass test. Một database có full load complete nhưng CDC latency còn cao và chưa thể cutover. Vì vậy, cần tách:

- Technical progress: task/lifecycle của công cụ.
- Application readiness: dependency, test và owner sign-off.
- Wave readiness: target environment, network, IAM, backup và rollback.
- Business completion: traffic chuyển, dữ liệu reconcile, SLO đạt và owner chấp nhận.

### 12.2. Đặt gate cho từng wave

Một wave chỉ nên chuyển sang giai đoạn tiếp theo khi đạt gate rõ ràng:

| Gate | Điều kiện ví dụ |
|---|---|
| Discovery complete | Inventory đủ, owner/dependency được xác nhận. |
| Plan approved | Target architecture, network, security, cost và cutover plan được duyệt. |
| Replication healthy | MGN replication healthy hoặc DMS task/CDC đạt tiêu chí. |
| Test passed | Functional, integration, performance và security test đạt. |
| Cutover approved | Change record, rollback, communication và owner sign-off đã sẵn sàng. |
| Migration validated | Traffic/data đã chuyển, monitoring ổn định, reconciliation hoàn tất. |
| Source decommission approved | Retention, backup, audit và business owner cho phép ngừng nguồn. |

## 13. Cutover và xác nhận hoàn tất

Cutover là bước có rủi ro cao vì thay đổi đường đi của người dùng và dữ liệu production. Một migration task báo hoàn tất không có nghĩa toàn bộ application đã sẵn sàng đóng dự án.

Checklist cutover:

1. Xác nhận replication health và lag nằm trong ngưỡng.
2. Xác nhận database consistency, row counts, schema, sequence và CDC state.
3. Xác nhận test instance đã pass functional/integration/security/performance test.
4. Freeze hoặc kiểm soát thay đổi ở source theo cutover plan.
5. Thực hiện final sync và dừng ghi theo đúng quy trình của công cụ.
6. Chuyển DNS, load balancer, route hoặc client endpoint.
7. Chạy smoke test và business validation.
8. Theo dõi error rate, latency, transaction success, queue backlog và data integrity.
9. Giữ rollback window theo chính sách.
10. Chỉ finalize cutover và decommission source khi owner chấp thuận.

Với database có CDC, cần xác nhận không còn backlog thay đổi chưa áp dụng hoặc đạt điều kiện cutover đã định. Với server rehost, kiểm tra application service, scheduled jobs, license, monitoring agent, backup, domain join và network dependency.

## 14. Bảo mật, quyền truy cập và governance

Migration thường mở rộng quyền truy cập vào dữ liệu và hạ tầng nguồn/đích. Cần thiết kế governance ngay từ đầu:

- Dùng AWS Organizations và account separation để cô lập workload, migration tooling và log archive.
- Dùng IAM role tách biệt cho discovery, replication, target provisioning và cutover.
- Cấp quyền least privilege theo từng tool và workflow.
- Bảo vệ credentials của agent/plugin và rotate khi kết thúc dự án.
- Dùng TLS cho dữ liệu truyền; encryption at rest theo policy.
- Giới hạn quyền đọc inventory vì có thể chứa hostname, IP, process, database metadata và network topology.
- Ghi lại thay đổi IAM, resource, network và cutover bằng CloudTrail.
- Dùng tagging cho application, wave, owner, environment, data classification và migration status.
- Đặt retention cho discovery data, logs, reports và artifacts.
- Xác định người phê duyệt cho production cutover, data retention và source decommission.

Không chia sẻ inventory hoặc topology cho đối tác vượt phạm vi hợp đồng. Đặc biệt, discovery data có thể tiết lộ hệ thống nội bộ và quan hệ kết nối giữa các server.

## 15. Theo dõi và xử lý sự cố

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không thấy migration updates trong Hub | Chưa chọn home Region hoặc đang xem sai Region. | Kiểm tra home Region và mở đúng console Region. |
| Tool chạy nhưng Hub không nhận status | Tool chưa được authorize hoặc thiếu IAM role. | Kiểm tra Migrate → Tools, role và quyền mgh cần thiết. |
| Update có trên Updates nhưng không vào application | Server chưa group hoặc mapping sai. | Kiểm tra Mapped servers, edit mapping và group server vào application. |
| Update đầu tiên chưa xuất hiện | Độ trễ ingest/hiển thị. | Chờ tối đa khoảng 5 phút, sau đó kiểm tra tool authorization và API. |
| Task bị stale | Không gửi update trong NextUpdateSeconds. | Kiểm tra scheduler, retry, clock/time source và chu kỳ gửi update. |
| API trả HomeRegionNotSetException | Chưa cấu hình home Region. | Cấu hình home Region trước khi write API. |
| API trả InvalidInputException | Gọi write API ngoài home Region hoặc payload sai. | Xác minh endpoint, Region và schema request. |
| MGN không đạt Ready for testing | Initial sync chưa xong hoặc replication có vấn đề. | Kiểm tra replication health, network, agent, staging resources và logs. |
| DMS progress không tăng | Thiếu table statistics hoặc task/table error. | Kiểm tra table state, rows loaded, task logs và CloudWatch metrics. |
| DMS full load xong nhưng chưa cutover được | CDC vẫn đang chạy hoặc latency chưa đạt ngưỡng. | Kiểm tra CDC latency, source changes và cutover criteria. |
| Application status không đổi | Task update chưa được map hoặc cần cập nhật application state. | Kiểm tra Updates, resource grouping và trạng thái application. |
| AWS Transform wave bị block | Dependency, target permission, inventory hoặc network chưa sẵn sàng. | Xem job/workflow step, worklog, approvals và next-step recommendation. |

### 15.1. Điều tra theo thứ tự

Khi dashboard không phản ánh tiến độ, kiểm tra từ ngoài vào trong:

1. Đúng account, home Region/workspace Region và target Region.
2. Migration tool hoặc AWS Transform job có đang hoạt động không.
3. Tool đã được authorize và có IAM role hợp lệ chưa.
4. Task/resource có được đăng ký và map đúng không.
5. Application đã được group đầy đủ chưa.
6. Last update, NextUpdateSeconds và clock có hợp lệ không.
7. Tool-specific logs, CloudWatch metrics, DMS task logs hoặc MGN replication health.
8. Network connectivity, endpoint, DNS, proxy, security group và service quota.
9. Workflow approval hoặc dependency có đang chờ owner không.

Không kết luận migration bị dừng chỉ từ một dashboard cũ. Đối chiếu timestamp và trạng thái trực tiếp trong công cụ thực hiện migration.

## 16. Tình huống thực hành: di chuyển một hệ thống đặt hàng

Một doanh nghiệp có hệ thống đặt hàng tại data center gồm:

- Hai web servers.
- Ba application servers.
- Một database SQL Server.
- Một message broker.
- Một file server chứa tài liệu đơn hàng.
- Một batch worker chạy vào ban đêm.

Các thành phần có dependency: web gọi application; application gọi database và message broker; batch worker đọc dữ liệu từ database/file server.

### 16.1. Discovery và scope

Với khách hàng Migration Hub hiện hữu, sử dụng dữ liệu discovery đã có từ Agentless Collector/Discovery Agent hoặc import. Kiểm tra hostname, CPU/RAM, disk, utilization, network connection và database metadata.

Với dự án mới, tạo AWS Transform migration job, upload inventory, review discovery summary và data quality warnings.

### 16.2. Grouping và wave plan

Nhóm các server thành application order-management. Database và message broker là hard dependency; batch worker là thành phần cùng business function và cần phối hợp cutover. File server được đánh giá riêng về storage protocol và access pattern.

Có thể lập hai wave:

- **Wave 1 – Pilot:** một web server và một application server trong môi trường test để kiểm chứng network, deployment và monitoring.
- **Wave 2 – Production application:** các web/app servers, database, message broker, file server và batch worker theo dependency/cutover plan đã duyệt.

Nếu database phải migrate trước để có thời gian CDC, có thể bắt đầu replication sớm hơn và chỉ cutover cùng application khi đạt điều kiện. Wave plan phải phản ánh cả thời điểm bắt đầu replication lẫn thời điểm chuyển production.

### 16.3. Execution và tracking

- MGN thực hiện rehost server; theo dõi lifecycle và replication health.
- DMS thực hiện full load/CDC cho SQL Server; theo dõi table state, CDC latency và errors.
- Migration Hub hiện hữu nhận các update, map server và hiển thị application progress.
- AWS Transform dùng wave status table và workflow steps cho dự án mới.

Mỗi task có owner và gate riêng. Không cho wave chuyển sang cutover chỉ vì tất cả task có progress 100%; cần test, data reconciliation và business sign-off.

### 16.4. Cutover và validation

Trong maintenance window:

1. Freeze thay đổi dữ liệu theo kế hoạch.
2. Chờ DMS CDC latency đạt ngưỡng.
3. Đồng bộ dữ liệu cuối và xác minh row counts/checksum hoặc business reconciliation.
4. Launch/cutover server theo dependency order.
5. Chuyển traffic và endpoint.
6. Chạy order placement, payment, inventory, batch và notification tests.
7. Theo dõi SLO và incident trong rollback window.
8. Ghi nhận application migration completed sau khi business owner chấp thuận.

## 17. Những hiểu lầm thường gặp

1. **Migration Hub tự di chuyển server/database.** Hub tập trung tracking; MGN, DMS hoặc tool khác thực hiện migration.
2. **Migration Hub còn nhận khách hàng mới.** Dịch vụ ngừng nhận khách hàng mới từ 07-11-2025; AWS Transform là hướng cho dự án mới.
3. **Application Discovery Service vẫn có thể đăng ký mới.** ADS cũng ngừng nhận khách hàng mới từ 07-11-2025.
4. **Home Region là Region đích.** Home Region là nơi tập trung dữ liệu tracking; target Region có thể khác.
5. **Có inventory là đủ lập wave.** Cần dependency, owner, business criticality, RTO/RPO và cutover window.
6. **Một server tương đương một application.** Application thường gồm nhiều resource phụ thuộc nhau.
7. **Progress 100% đồng nghĩa đã cutover.** Cần test, final sync, traffic switch và validation.
8. **DMS progress percent luôn chính xác.** Estimate phụ thuộc table statistics và không thay thế task/table state.
9. **Ready for testing nghĩa là test đã pass.** Đây chỉ là trạng thái cho phép launch test instance.
10. **Application Completed được tự động hóa hoàn toàn.** Cần xác minh và có thể phải cập nhật application state theo quy trình.
11. **Mọi update tự động map đúng server.** Cần kiểm tra Mapped servers và sửa mapping khi cần.
12. **Có thể gọi write API từ bất kỳ Region nào.** Write API Migration Hub phải chạy tại home Region.
13. **Không thấy update nghĩa là tool đã dừng.** Có thể do authorization, mapping, Region hoặc ingest delay.
14. **Wave chỉ là nhóm server theo kích thước.** Wave cần phản ánh dependency và business/operational constraints.
15. **Cutover complete là có thể xóa hệ thống nguồn ngay.** Cần validation, rollback window, backup/retention và phê duyệt decommission.

## 18. Câu hỏi tự kiểm tra

**1. AWS Migration Hub có vai trò gì trong chương trình migration?**

Tập trung trạng thái từ nhiều migration tools, liên kết task/resource với application và cung cấp góc nhìn tiến độ.

**2. Migration Hub có thực hiện sao chép dữ liệu server không?**

Không. MGN, DMS hoặc công cụ chuyên biệt thực hiện migration; Hub nhận trạng thái.

**3. Migration Hub ngừng nhận khách hàng mới từ ngày nào?**

Ngày 07-11-2025. AWS Transform là hướng thay thế được khuyến nghị cho dự án mới.

**4. Home Region dùng để làm gì?**

Lưu tập trung discovery data và migration tracking data của account.

**5. Vì sao cần group servers thành application?**

Để theo dõi tiến độ theo business workload và thể hiện các resource cần phối hợp khi migration.

**6. Khác nhau giữa application và migration task là gì?**

Application là nhóm logic gồm nhiều resource; migration task là công việc di chuyển một resource cụ thể do tool quản lý.

**7. Migration Hub có thể nhận status từ những công cụ nào?**

Ví dụ MGN, DMS và các migration tools/partners được tích hợp.

**8. ProgressUpdateStream có tác dụng gì?**

Định danh migration tool và cung cấp namespace/ràng buộc truy cập cho các migration task.

**9. NextUpdateSeconds có ý nghĩa gì?**

Khoảng thời gian Migration Hub chờ update tiếp theo trước khi coi task là stale.

**10. Vì sao DMS progress bar có thể không tăng?**

Estimate có thể thiếu dữ liệu khi source table không có row statistics phù hợp; cần xem task status, table state và rows loaded.

**11. Move group khác migration wave như thế nào?**

Move group chứa các application phụ thuộc nhau cần chuyển cùng nhau; wave gồm một hoặc nhiều move group.

**12. Ready for cutover có nghĩa gì?**

Server đã được kiểm thử và sẵn sàng cho bước cutover; vẫn cần change approval và cutover validation.

**13. AWS Transform workspace summary report có thể tổng hợp những gì?**

Job status, workflow steps, approvals, wave plan, network topology, landing zone, rehost progress và artifacts.

**14. Có thể đặt application Completed ngay khi task migration Completed không?**

Không. Cần kiểm thử, xác minh dữ liệu và business owner acceptance.

**15. Vì sao cần theo dõi cả kỹ thuật lẫn nghiệp vụ?**

Task có thể hoàn tất nhưng application vẫn lỗi, dữ liệu chưa nhất quán hoặc người dùng chưa thể sử dụng workload.

## 19. Checklist vận hành migration

- [ ] Đã xác định dự án là Migration Hub hiện hữu hay dự án mới cần AWS Transform.
- [ ] Đã chọn đúng account, home Region/workspace Region và target Region.
- [ ] Inventory có server, database, utilization, owner và dependency.
- [ ] Data quality warnings đã được xử lý hoặc ghi thành risk.
- [ ] Application grouping phản ánh dependency và business boundary.
- [ ] Move groups và migration waves có owner, timeline và dependency rõ ràng.
- [ ] MGN/DMS/partner tools đã được authorize và có IAM role phù hợp.
- [ ] Migration task được map đúng source resource và application.
- [ ] Dashboard có last update, stale task, replication health và blockers.
- [ ] DMS có full-load/table state/CDC metrics và log.
- [ ] MGN có lifecycle, replication health, test status và cutover readiness.
- [ ] Có test plan, data reconciliation và rollback plan.
- [ ] Cutover có maintenance window, approver và communication plan.
- [ ] Application chỉ được đánh dấu Completed sau validation.
- [ ] Có dashboard portfolio, wave status, SLA và cost tracking.
- [ ] Có audit trail cho thay đổi IAM, network, resource và cutover.
- [ ] Có retention policy cho inventory, logs, reports và artifacts.
- [ ] Source decommission chỉ thực hiện sau phê duyệt và kiểm tra backup/retention.

## Tài liệu tham khảo

- [AWS Migration Hub – Service overview](https://docs.aws.amazon.com/migrationhub/latest/ug/what-is-migrationhub.html)
- [AWS Migration Hub availability change](https://docs.aws.amazon.com/migrationhub-orchestrator/latest/userguide/migrationhub-availability-change.html)
- [AWS Application Discovery Service availability change](https://docs.aws.amazon.com/application-discovery/latest/userguide/application-discovery-service-availability-change.html)
- [What is AWS Application Discovery Service?](https://docs.aws.amazon.com/application-discovery/latest/userguide/what-is-appdiscovery.html)
- [Application Discovery Service Agentless Collector](https://docs.aws.amazon.com/application-discovery/latest/userguide/agentless-collector.html)
- [AWS Application Discovery Agent](https://docs.aws.amazon.com/application-discovery/latest/userguide/discovery-agent.html)
- [View and explore discovered data](https://docs.aws.amazon.com/application-discovery/latest/userguide/view-and-explore.html)
- [Choosing an AWS Migration Hub home Region](https://docs.aws.amazon.com/migrationhub/latest/ug/select-home-region.html)
- [Managing the AWS Migration Hub home Region](https://docs.aws.amazon.com/migrationhub/latest/ug/home-region.html)
- [AWS Migration Hub API reference](https://docs.aws.amazon.com/migrationhub/latest/ug/api-reference.html)
- [Tracking migration updates in AWS Migration Hub](https://docs.aws.amazon.com/migrationhub/latest/ug/updates-tracking-wt.html)
- [Track the status of your migrations](https://docs.aws.amazon.com/migrationhub/latest/ug/migrate-wt-track.html)
- [Grouping servers in the Migration Hub console](https://docs.aws.amazon.com/application-discovery/latest/userguide/applications.html)
- [NotifyMigrationTaskState API](https://docs.aws.amazon.com/migrationhub/latest/ug/API_NotifyMigrationTaskState.html)
- [Migration Hub troubleshooting](https://docs.aws.amazon.com/migrationhub/latest/ug/troubleshooting.html)
- [Migration Hub Orchestrator templates](https://docs.aws.amazon.com/migrationhub-orchestrator/latest/userguide/templates.html)
- [What is AWS Transform?](https://docs.aws.amazon.com/transform/latest/userguide/)
- [AWS Transform discovery, assessment, and planning](https://docs.aws.amazon.com/transform/latest/userguide/transform-migrations-discover-assess-plan.html)
- [AWS Transform migration planning](https://docs.aws.amazon.com/transform/latest/userguide/transform-vmware-review-groupings-and-waves.html)
- [AWS Transform migration wave execution](https://docs.aws.amazon.com/transform/latest/userguide/transform-vmware-ms-wave-execution.html)
- [AWS Transform server lifecycle states](https://docs.aws.amazon.com/transform/latest/userguide/transform-vmware-ms-server-lifecycle.html)
- [AWS Transform migration jobs and workspace reports](https://docs.aws.amazon.com/transform/latest/userguide/vmware-jobs.html)
- [Monitoring AWS DMS tasks](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_Monitoring.html)
- [AWS CLI create-progress-update-stream](https://docs.aws.amazon.com/cli/latest/reference/mgh/create-progress-update-stream.html)
- [AWS CLI import-migration-task](https://docs.aws.amazon.com/cli/latest/reference/mgh/import-migration-task.html)
- [AWS CLI notify-migration-task-state](https://docs.aws.amazon.com/cli/latest/reference/mgh/notify-migration-task-state.html)

