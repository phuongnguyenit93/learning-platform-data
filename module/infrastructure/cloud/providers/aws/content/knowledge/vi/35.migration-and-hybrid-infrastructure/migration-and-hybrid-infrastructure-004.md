# AWS Application Migration Service và di chuyển máy chủ

Di chuyển máy chủ lên AWS thường là một trong những bước đầu tiên khi doanh nghiệp chuyển trung tâm dữ liệu hoặc workload từ một nhà cung cấp cloud khác. Thách thức không chỉ nằm ở việc sao chép ổ đĩa. Nhóm di chuyển phải giữ hệ thống nguồn hoạt động trong lúc dữ liệu được chuyển, chuẩn bị mạng và quyền truy cập ở đích, kiểm tra ứng dụng trước khi chuyển người dùng, rồi thực hiện cutover trong một cửa sổ gián đoạn có thể dự đoán.

AWS Application Migration Service (AWS MGN) được đổi tên thành **AWS Transform MGN** vào tháng 6 năm 2026. Dịch vụ giữ nguyên API và công nghệ replication cốt lõi, đồng thời trở thành engine rehosting được AWS Transform sử dụng. Nhóm có thể thao tác trực tiếp trong AWS Transform MGN console hoặc dùng workflow agentic của AWS Transform để hỗ trợ discovery, lập migration wave, chuẩn bị mạng và thực hiện rehosting. Bài học dùng tên AWS Transform MGN khi mô tả dịch vụ hiện hành và nhắc AWS Application Migration Service/AWS MGN khi giải thích tên cũ trong tài liệu hoặc giao diện trước đây.

AWS Transform MGN chuyển máy chủ vật lý, máy ảo hoặc máy chủ chạy trên cloud khác thành Amazon EC2 instance bằng cách sao chép dữ liệu ở mức block liên tục vào staging area trong AWS. Khi dữ liệu ban đầu đã đồng bộ, các thay đổi tiếp theo tiếp tục được replicate. Nhóm có thể khởi chạy test instance để xác minh ứng dụng, sau đó thực hiện cutover và chuyển workload sang EC2 với thời gian gián đoạn ngắn hơn so với một lần sao chép thủ công.

Bài học này thuộc phạm vi CLOUD_PROVIDERS_AWS: lựa chọn và triển khai hạ tầng AWS có khả năng vận hành, bảo mật, phục hồi và kiểm soát chi phí. Trọng tâm là chuẩn bị máy chủ nguồn, thiết kế staging area, cấu hình replication và launch settings, kiểm thử, cutover, xử lý các vấn đề thường gặp và phối hợp MGN với các dịch vụ di chuyển khác.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vai trò của AWS Transform MGN trong chiến lược rehost máy chủ.
- Phân biệt MGN với AWS DMS, AWS DataSync, AWS Elastic Disaster Recovery và các công cụ theo dõi migration.
- Mô tả kiến trúc replication agent, replication server, staging area và EC2 launch template.
- Kiểm tra điều kiện hệ điều hành, phần cứng, định danh máy chủ và kết nối mạng trước khi cài agent.
- Thiết kế staging subnet, operational subnet, quyền IAM, mã hóa và đường truyền riêng.
- Cấu hình replication settings, launch settings và post-launch actions.
- Lập kế hoạch test, cutover, rollback và kiểm tra sau di chuyển.
- Ước tính chi phí MGN, tài nguyên staging và test/cutover instance.
- Tổ chức migration theo ứng dụng và wave để giảm rủi ro trong môi trường nhiều máy chủ.

## 2. Rehost và vai trò của AWS Transform MGN

### 2.1. Rehost là gì?

Rehost, thường được gọi là lift-and-shift, là chuyển máy chủ và workload sang hạ tầng đích với ít thay đổi nhất đối với ứng dụng. Thay vì viết lại ứng dụng hoặc thay đổi kiến trúc ngay trong đợt di chuyển đầu tiên, nhóm đưa hệ điều hành và dữ liệu block sang EC2, điều chỉnh cấu hình hạ tầng cần thiết rồi xác minh ứng dụng hoạt động.

Rehost phù hợp khi:

- Trung tâm dữ liệu cần đóng cửa hoặc hợp đồng hosting sắp hết hạn.
- Doanh nghiệp cần chuyển workload nhanh để giảm phụ thuộc vào phần cứng cũ.
- Ứng dụng cũ khó thay đổi hoặc chưa có đủ thời gian để refactor.
- Nhóm muốn chuyển hạ tầng trước, hiện đại hóa ứng dụng trong một giai đoạn sau.
- Cần chuyển máy chủ giữa Region hoặc giữa tài khoản AWS theo kế hoạch đã kiểm chứng.

Rehost không tự động biến ứng dụng thành cloud-native. Máy chủ sau khi chuyển vẫn có thể giữ nguyên cách cấu hình, phụ thuộc, phiên bản hệ điều hành và giới hạn mở rộng như trước. Sau khi ổn định, nhóm có thể đánh giá replatform, refactor, repurchase hoặc retire.

### 2.2. AWS Transform MGN làm gì?

AWS Transform MGN tự động hóa phần sao chép máy chủ và khởi chạy máy chủ đích:

1. Cài AWS Replication Agent trên máy chủ nguồn được hỗ trợ.
2. Agent theo dõi thay đổi ở mức block và truyền dữ liệu sang AWS.
3. Replication server trong staging area ghi dữ liệu vào các EBS staging disk và tạo snapshot theo cơ chế dịch vụ.
4. MGN tiếp tục đồng bộ các block thay đổi để duy trì replication lag ở mức thấp.
5. Khi nhóm yêu cầu, MGN khởi chạy test hoặc cutover instance dựa trên launch settings và EC2 launch template.
6. Sau khi cutover hoàn tất, máy chủ đích trở thành workload vận hành trên AWS; nhóm tiếp tục tối ưu, giám sát và quản trị như các EC2 instance khác.

MGN chủ yếu giải quyết việc rehost máy chủ. Dịch vụ không thay thế công việc đánh giá dependency, thiết kế VPC, chuyển đổi DNS, kiểm tra license, thay đổi cấu hình ứng dụng, di chuyển schema database hoặc lập kế hoạch vận hành sau migration.

### 2.3. Tên dịch vụ và cách truy cập hiện hành

AWS Application Migration Service được đổi tên thành AWS Transform MGN ngày 08-06-2026. API vẫn thuộc namespace MGN và các tài liệu cũ có thể tiếp tục ghi AWS Application Migration Service hoặc AWS MGN. Khi tra cứu, hãy nhận diện đây là cùng công nghệ rehost.

Hiện có hai cách làm việc:

- **AWS Transform MGN console:** nhóm trực tiếp kiểm soát cấu hình replication, launch settings, test và cutover theo từng máy chủ.
- **AWS Transform workflow:** workflow agentic có thể hỗ trợ discovery, migration wave, landing zone, network setup và chuẩn bị rehost. Ở giai đoạn rehost, nhóm vẫn có thể chuyển sang MGN console để kiểm soát thủ công.

Hai cách truy cập sử dụng cùng replication engine. Việc dùng workflow agentic không loại bỏ nhu cầu kiểm tra inventory, quyền truy cập, network, launch template và kết quả kiểm thử.

### 2.4. Những việc MGN không thay thế

| Nhu cầu | Công cụ hoặc công việc phù hợp |
|---|---|
| Rehost hệ điều hành và block disk thành EC2 | AWS Transform MGN |
| Di chuyển dữ liệu và chuyển đổi schema database | AWS Database Migration Service (AWS DMS) |
| Sao chép file và object giữa hệ thống lưu trữ | AWS DataSync hoặc công cụ truyền file phù hợp |
| Disaster recovery và failback về môi trường nguồn | AWS Elastic Disaster Recovery (AWS DRS) |
| Discovery, đánh giá và lập kế hoạch migration rộng hơn | AWS Transform và các công cụ discovery/assessment phù hợp |
| Thiết kế VPC, subnet, route, DNS, firewall và kết nối hybrid | Amazon VPC, Direct Connect, Site-to-Site VPN và dịch vụ mạng liên quan |

MGN không phải công cụ chuyển đổi dữ liệu database ở mức logic. Nếu ứng dụng dùng database có yêu cầu consistency hoặc cần đổi engine, hãy lập kế hoạch database riêng, thường phối hợp DMS hoặc quy trình backup/restore của database.

## 3. Kiến trúc replication

### 3.1. Các thành phần chính

**Máy chủ nguồn (source server)** là máy chủ vật lý, VM hoặc cloud instance đang chạy ứng dụng. Máy chủ phải dùng hệ điều hành và kiến trúc được hỗ trợ.

**AWS Replication Agent** được cài trên máy chủ nguồn. Agent đọc các thay đổi block, quản lý tiến trình replication và gửi dữ liệu tới staging area. Việc cài agent cần quyền quản trị hệ điều hành và kết nối mạng phù hợp.

**Staging area subnet** là subnet trong VPC đích dùng cho replication server và các tài nguyên hỗ trợ. Đây là khu vực trung gian để nhận và lưu dữ liệu trong khi máy chủ nguồn vẫn đang hoạt động. AWS khuyến nghị tạo một subnet riêng cho staging area để dễ quản lý, theo dõi và kiểm soát network.

**Replication server** là EC2 instance do MGN khởi tạo trong staging area để nhận và xử lý dữ liệu replication. Cấu hình và số lượng replication server phụ thuộc workload, throughput và settings.

**Staging EBS disks và snapshots** lưu dữ liệu block được replicate. Dung lượng và hiệu năng staging ảnh hưởng tốc độ đồng bộ, thời gian hoàn tất và chi phí.

**EC2 launch template** mô tả cách MGN tạo test/cutover instance, ví dụ instance type, subnet, security group, storage và các thuộc tính EC2 khác.

**Operational subnet** là subnet nơi test instance và cutover instance chạy. Subnet này thường nằm trong VPC ứng dụng đích, tách biệt với staging subnet.

### 3.2. Luồng dữ liệu

~~~mermaid
flowchart LR
    A[Máy chủ nguồn] -->|AWS Replication Agent| B[Đường truyền được bảo vệ]
    B --> C[Replication server]
    C --> D[Staging EBS disks]
    D --> E[Recovery snapshots]
    E --> F[MGN launch workflow]
    F --> G[Test EC2 instance]
    F --> H[Cutover EC2 instance]
    H --> I[VPC ứng dụng đích]
~~~

Replication chạy liên tục trong thời gian chuẩn bị migration. Khi test hoặc cutover instance được khởi chạy, MGN dùng dữ liệu đã replicate để tạo máy chủ đích. Agent replication được loại bỏ khỏi test/cutover instance trong quá trình launch theo cơ chế của dịch vụ; instance đích không tiếp tục chạy như một source server.

### 3.3. Initial sync và continuous replication

Khi agent mới được cài, MGN thực hiện initial sync để sao chép dữ liệu ban đầu của các volume được hỗ trợ. Đây thường là giai đoạn truyền nhiều dữ liệu nhất và có thể kéo dài tùy dung lượng, tốc độ thay đổi block, băng thông và hiệu năng nguồn/đích.

Sau initial sync, continuous replication chỉ truyền các block thay đổi. Điều này giúp giữ bản sao đích gần với trạng thái nguồn mà không cần sao chép toàn bộ volume mỗi lần. Người vận hành cần theo dõi replication status và lag để biết khi nào có thể bắt đầu test hoặc cutover.

Replication lag thấp không có nghĩa ứng dụng đã sẵn sàng cutover. Nhóm vẫn phải xác minh dependency, cấu hình mạng, quyền truy cập, dữ liệu ứng dụng và thời gian dừng dịch vụ.

### 3.4. Giới hạn block storage

MGN replicate block device được hệ điều hành nhìn thấy. Các ổ SAN được trình bày như block device thường có thể được replicate tương tự ổ đĩa cục bộ nếu đáp ứng yêu cầu dịch vụ. Network file share như NFS hoặc SMB/CIFS không được chuyển như một block disk gắn trực tiếp; cần dùng công cụ truyền file hoặc thiết kế storage migration riêng. Nếu NFS server chứa dữ liệu trên block disk, phải đánh giá máy chủ thực sự sở hữu dữ liệu và cài agent tại đúng nơi cần replicate.

Không giả định rằng mọi mount point hoặc storage appliance đều được MGN bảo vệ. Inventory phải phân biệt local/block volume, SAN LUN, NFS share, SMB share, object storage và database-managed storage.

## 4. Đánh giá và chuẩn bị máy chủ nguồn

### 4.1. Inventory trước khi cài agent

Thu thập ít nhất:

- Hostname, địa chỉ IP, DNS name, hệ điều hành và phiên bản.
- CPU, RAM, kiến trúc CPU, kernel và boot mode.
- Số lượng disk, dung lượng, partition, filesystem và loại storage.
- Dung lượng sử dụng và tốc độ thay đổi dữ liệu theo giờ/ngày.
- Ứng dụng, service, process, port và dependency.
- Database, file share, license, certificate và secret liên quan.
- Domain membership, DNS, NTP, firewall và kết nối tới hệ thống bên ngoài.
- Owner nghiệp vụ, mức độ quan trọng, RPO/RTO và cửa sổ cutover.

Phân nhóm máy chủ theo ứng dụng, dependency và thứ tự khởi động. Một ứng dụng nhiều tầng có thể cần database và identity service sẵn sàng trước application server, rồi mới đưa load balancer và người dùng vào.

### 4.2. Hệ điều hành và kiến trúc được hỗ trợ

MGN hỗ trợ nhiều phiên bản Windows và Linux, nhưng danh sách thay đổi theo thời gian. Cần kiểm tra trang Supported Operating Systems tại thời điểm triển khai, đúng Region và phiên bản kernel. Không dựa vào một danh sách OS cũ trong runbook vì AWS có thể thêm hoặc ngừng hỗ trợ phiên bản.

Các điều kiện tổng quát cần kiểm tra:

- Hệ điều hành thuộc danh sách được hỗ trợ.
- Hệ thống dùng kiến trúc x86; MGN không hỗ trợ OS 32-bit hoặc ARM source theo yêu cầu agent hiện hành.
- Định danh phần cứng của máy chủ phải ổn định và duy nhất. Clone VM cần có identifier riêng trước khi cài agent.
- Máy chủ có đủ RAM và dung lượng trống cho agent.
- Linux có kernel headers tương ứng với kernel đang chạy, bootloader và package cần thiết theo từng distro.
- Quyền cài đặt phải là root hoặc user có sudo; Windows cần quyền Administrator và các prerequisite theo phiên bản.
- Không sử dụng cấu hình fully paravirtualized không được hỗ trợ.

Yêu cầu cụ thể có thể khác giữa Linux và Windows. Ví dụ, Linux cần kiểm tra /tmp có quyền ghi và thực thi trong lúc cài agent; một số hệ điều hành cần kernel-devel hoặc linux-headers khớp chính xác kernel đang chạy.

### 4.3. Dung lượng và disk size

Trước khi cài agent, xác nhận dung lượng trống trên root filesystem, RAM khả dụng và dung lượng tạm phục vụ installer. Tài liệu yêu cầu cài đặt hiện hành nêu tối thiểu 2 GB trống trên root và 300 MB RAM cho agent; Linux còn có yêu cầu riêng cho /tmp và /boot tùy cấu hình.

Theo release notes tháng 11-2026, MGN đã mở rộng hỗ trợ source disk lên đến 64 TiB. Disk lớn hơn 16 TiB cần staging disk loại General Purpose SSD gp3 hoặc Provisioned IOPS SSD io2. Hãy kiểm tra release notes và tài liệu disk size mới nhất trước khi migration ổ đĩa lớn, vì hướng dẫn cũ có thể vẫn ghi giới hạn 16 TiB.

### 4.4. Kiểm tra license và phụ thuộc hệ điều hành

Di chuyển máy chủ không tự động chuyển giao mọi quyền sử dụng phần mềm. Đặc biệt cần rà soát:

- Windows Server licensing và lựa chọn license-included/BYOL.
- RHEL, SUSE hoặc các subscription của nhà cung cấp Linux.
- Microsoft SQL Server licensing và khả năng chuyển đổi license nếu được hỗ trợ.
- Phần mềm có khóa license gắn với MAC address, hardware ID hoặc hostname.
- Driver, kernel module, antivirus, EDR, backup agent và phần mềm giám sát.
- Certificate, secret, service account và cấu hình hard-coded địa chỉ IP.

Kiểm tra hợp đồng license và yêu cầu của nhà cung cấp trước khi chuyển production. Không xem việc EC2 boot thành công là bằng chứng license hợp lệ.

## 5. Chuẩn bị AWS target environment

### 5.1. Chọn Region và tài khoản

Khởi tạo MGN trong Region đích mà máy chủ sẽ được migrate tới. Xác định:

- AWS account sở hữu workload.
- Tài khoản quản trị migration nếu dùng AWS Organizations/delegated administrator.
- VPC, CIDR, subnet và Availability Zone.
- Staging area subnet và operational subnet.
- Kết nối tới on-premises hoặc cloud nguồn trong thời gian replication và hybrid operation.
- Dịch vụ đích như EC2, EBS, FSx for NetApp ONTAP hoặc database target tùy kiến trúc.

MGN là dịch vụ theo Region. Không giả định cấu hình, source server hoặc staging area ở Region này tự động xuất hiện ở Region khác. Với migration đa Region, hãy lập kế hoạch riêng cho từng target Region và kiểm tra tính sẵn sàng của dịch vụ.

### 5.2. Staging subnet và operational subnet

Staging subnet nên được dành riêng cho replication server và tài nguyên hỗ trợ. Tách staging khỏi subnet ứng dụng giúp:

- Dễ giới hạn security group và route.
- Theo dõi replication traffic riêng.
- Tránh ảnh hưởng đến workload production.
- Dự toán tài nguyên và chi phí staging rõ hơn.

Operational subnet là nơi test/cutover instance chạy. Chọn subnet dựa trên kiến trúc VPC đích, routing, load balancer, DNS, firewall, directory service và các dependency cần thiết.

Nếu test instance dùng cùng subnet và địa chỉ với production source, có thể gây IP conflict hoặc kết nối nhầm hệ thống. Nên thiết kế test VPC/subnet riêng hoặc cơ chế cô lập tương đương. Khi test Active Directory, đặc biệt tránh để domain controller thử nghiệm có route không kiểm soát về mạng production vì client có thể kết nối nhầm domain controller.

### 5.3. Kết nối mạng và firewall

Các luồng mạng quan trọng cần được cho phép theo tài liệu MGN:

| Nguồn | Đích | Giao thức/cổng | Mục đích |
|---|---|---|---|
| Source server | MGN API endpoint của Region | TCP 443 | Điều khiển và đăng ký replication |
| Source server | Staging area subnet/replication server | TCP 1500 | Truyền dữ liệu block replication |
| Staging area subnet | MGN API endpoint | TCP 443 | Giao tiếp dịch vụ và điều phối |
| Staging area subnet | Amazon S3 và EC2 endpoints | HTTPS/TCP 443 | Tải thành phần, package và gọi API cần thiết |

Tất cả giao tiếp được mã hóa bằng TLS theo cơ chế dịch vụ. Không áp dụng SSL interception cho kết nối giữa source server/replication server và MGN API endpoint. Proxy hoặc firewall có thể làm gián đoạn agent nếu thay đổi chứng chỉ hoặc nội dung TLS.

Trong môi trường không cho phép Internet trực tiếp, có thể dùng AWS Direct Connect, Site-to-Site VPN hoặc kết nối private phù hợp để truyền dữ liệu. Cần xác nhận route, DNS, MTU, băng thông, latency, security group, network ACL và firewall ở cả hai phía.

### 5.4. Ước tính băng thông

Băng thông cần thiết phụ thuộc:

- Tổng dung lượng cần initial sync.
- Tốc độ thay đổi block trong giờ cao điểm.
- Số máy chủ replicate đồng thời.
- Cửa sổ migration và thời hạn cần hoàn thành initial sync.
- Băng thông còn lại sau khi trừ traffic ứng dụng.

Ước lượng dữ liệu ban đầu:

\[
\text{Thời gian truyền (giây)} \approx \frac{\text{Dung lượng dữ liệu (bit)}}{\text{Thông lượng thực tế (bit/giây)}}
\]

Thông lượng thực tế thấp hơn bandwidth danh nghĩa do overhead, packet loss, giới hạn disk I/O, throttling và cạnh tranh với traffic khác. Hãy thử nghiệm một nhóm nhỏ trước, đo replication throughput và lag rồi mới tăng số server trong wave.

### 5.5. IAM và quyền quản trị

Phân biệt quyền người vận hành MGN với quyền của service role và quyền của EC2 instance đích. Người quản trị cần quyền khởi tạo MGN, cấu hình replication/launch settings, xem trạng thái và khởi chạy test/cutover. MGN cũng cần quyền tạo và quản lý replication resources theo service role/policy của dịch vụ.

Nguyên tắc:

- Dùng AWS managed policies hoặc policy do tổ chức kiểm soát theo tài liệu hiện hành.
- Chỉ cấp quyền ở account và Region phục vụ migration.
- Phân tách người được phép cấu hình với người phê duyệt cutover production.
- Dùng IAM role và temporary credentials thay cho access key dài hạn.
- Kiểm soát EC2 instance profile của máy chủ đích theo ứng dụng.
- Nếu dùng post-launch actions, cấu hình quyền AWS Systems Manager và quyền thực thi SSM documents.
- Ghi nhận thay đổi qua CloudTrail và rà soát quyền sau khi migration hoàn tất.

Không sao chép một IAM policy cũ từ tài liệu lịch sử mà không kiểm tra tên service, action và trust relationship đang được AWS hỗ trợ.

## 6. Cấu hình MGN

### 6.1. Khởi tạo dịch vụ

Trong target Region:

1. Mở AWS Transform MGN console.
2. Khởi tạo service và chấp nhận cấu hình/role cần thiết.
3. Kiểm tra replication settings template ở cấp account.
4. Chọn staging area subnet và các thiết lập replication mặc định.
5. Kiểm tra launch settings template và post-launch settings template.
6. Chuẩn bị EC2 launch template, IAM role và VPC resources.

Các template cấp account giúp chuẩn hóa cấu hình cho máy chủ mới. Tuy nhiên, từng source server vẫn có thể cần override theo workload. Sau khi thêm máy chủ, kiểm tra settings thực tế trước khi bắt đầu replication.

### 6.2. Cài AWS Replication Agent

Quy trình chung:

1. Xác nhận OS, kernel, disk, RAM, định danh máy chủ và network.
2. Tải installer theo hướng dẫn của MGN trong Region đích.
3. Chạy installer với quyền root/sudo trên Linux hoặc Administrator trên Windows.
4. Cung cấp thông tin đăng ký/credential theo hướng dẫn console và xác nhận Region.
5. Kiểm tra source server xuất hiện trong MGN console.
6. Theo dõi agent health và trạng thái initial sync.

Không cài agent lên bản clone có cùng hardware identifier với máy chủ đã đăng ký. MGN có thể nhận diện đó là cùng một source server, dẫn đến cập nhật nhầm bản ghi và dừng replication của máy chủ trước.

Từ tháng 10-2026, agentless replication không còn khả dụng cho deployment mới; AWS khuyến nghị agent-based replication cho các migration mới. Nếu môi trường cũ đã dùng agentless, hãy kiểm tra hướng dẫn chuyển đổi và phạm vi hỗ trợ trước khi thay đổi.

### 6.3. Replication settings

Replication settings điều khiển cách dữ liệu được replicate vào staging area:

- Staging area subnet và Availability Zone.
- Replication server instance type hoặc cách chọn capacity.
- Staging disk type, IOPS và throughput.
- Bandwidth throttling nếu cần bảo vệ đường truyền.
- Cấu hình mã hóa và KMS key theo yêu cầu.
- Các tùy chọn liên quan đến snapshot và replication behavior.

Đặt staging disk đủ hiệu năng để theo kịp tốc độ thay đổi của source. Nếu staging server hoặc disk quá nhỏ, replication lag có thể tăng, initial sync kéo dài hoặc replication job thất bại. Nếu cấp dư capacity cho hàng trăm server mà không cần thiết, chi phí tăng mà không mang lại lợi ích tương xứng.

### 6.4. Launch settings và EC2 launch template

Launch settings xác định test/cutover instance sẽ được tạo như thế nào:

- Instance type hoặc cơ chế right-sizing.
- VPC và subnet.
- Security group.
- Private IP và network interface.
- IAM instance profile.
- EBS volume type, size, IOPS, throughput, encryption và delete-on-termination.
- Tenancy, license option và các thuộc tính EC2 khác.
- Boot mode và các setting liên quan tới OS.

MGN tạo EC2 launch template khi source server được thêm vào. Hãy xem launch template là cấu hình đích cần review, không phải thứ có thể bỏ qua. Instance type được chọn tự động để phù hợp OS/CPU/RAM có thể ghi đè instance type đặt trong template theo chế độ right-sizing đã chọn.

Thay đổi launch settings thường chỉ ảnh hưởng các test/cutover instance được launch sau đó. Nếu đã launch một test instance, cập nhật template không tự sửa instance đang chạy; cần launch lại để xác minh cấu hình mới.

### 6.5. Post-launch actions

Post-launch actions cho phép tự động hóa công việc sau khi test/cutover instance khởi chạy. Framework sử dụng AWS Systems Manager documents, có thể gồm:

- Cài hoặc cấu hình SSM Agent khi hệ điều hành hỗ trợ.
- Cài CloudWatch Agent hoặc security agent.
- Kiểm tra disk, process, HTTP/HTTPS endpoint và kết nối.
- Thay đổi license hoặc thực hiện OS upgrade theo tính năng được hỗ trợ.
- Chạy script tùy chỉnh cho cấu hình ứng dụng.

Post-launch actions phải được kích hoạt ở cấp account template hoặc cho từng source server. Kiểm tra document version, thứ tự thực thi, operating system filter, parameter và quyền SSM. Một action chạy sai hệ điều hành hoặc thiếu quyền có thể bị skip hoặc thất bại.

Từ tháng 11-2026, MGN bổ sung source actions để chạy script trên máy chủ nguồn trong migration thông qua MGN connector và script được lưu trong Systems Manager Parameter Store. Source actions khác post-launch actions: một nhóm chạy trên source trước/đang migration, nhóm kia chạy sau khi instance đích được launch. Hãy kiểm tra release notes để xác nhận tính năng, Region và quyền connector trước khi dùng.

## 7. Quy trình migration từ đầu đến cuối

### 7.1. Giai đoạn 1: Chuẩn bị

1. Xác định ứng dụng và dependency.
2. Phân nhóm server thành migration wave.
3. Chọn target Region, account, VPC và subnet.
4. Chuẩn bị IAM, firewall, staging area và launch settings.
5. Kiểm tra OS support, disk layout, license và network.
6. Xác định RPO/RTO, cửa sổ test và cutover.
7. Xây dựng kế hoạch rollback và người phê duyệt.

### 7.2. Giai đoạn 2: Replication

1. Khởi tạo MGN trong target Region.
2. Cài agent trên source server.
3. Xác nhận source server xuất hiện trong console.
4. Theo dõi initial sync cho đến khi hoàn tất.
5. Xác minh continuous replication đang hoạt động.
6. Theo dõi lag, replication server, staging disks và snapshot.
7. Xử lý lỗi trước khi chuyển sang test.

Không nên bắt đầu cutover chỉ vì source server đã được đăng ký. Initial sync phải hoàn tất và replication phải ổn định. Nếu workload có tốc độ ghi cao, cần kiểm tra lag trong giờ tải lớn thay vì chỉ xem một thời điểm yên tĩnh.

### 7.3. Giai đoạn 3: Test launch

Khi initial sync hoàn tất:

1. Review launch settings.
2. Kiểm tra subnet, security group, instance type, disk và IAM instance profile.
3. Launch test instance.
4. Kiểm tra boot, system log, disk, filesystem và network interface.
5. Kiểm tra DNS, Active Directory, NTP, certificate, secret và kết nối tới dependency.
6. Chạy smoke test, integration test, performance test và nghiệp vụ quan trọng.
7. Xác minh dữ liệu và ứng dụng có thể phục vụ traffic thử nghiệm.
8. Ghi nhận vấn đề, sửa cấu hình và launch lại khi cần.

Test instance cần được kiểm tra trong môi trường cô lập. Đặc biệt với domain controller hoặc hệ thống có cùng hostname/IP với production, tránh để test traffic đi vào mạng thật ngoài kế hoạch. Nếu ứng dụng cần database hoặc API khác để test, tạo test dependency tương ứng hoặc cấu hình route có kiểm soát.

Sau khi hoàn tất, finalize test theo quy trình MGN và terminate test instance nếu không còn cần. Test instance không tự động miễn phí; EC2, EBS và các tài nguyên liên quan vẫn phát sinh phí.

### 7.4. Giai đoạn 4: Chuẩn bị cutover

Trước cửa sổ cutover:

- Đã test thành công từng máy chủ trong ứng dụng.
- Replication lag ở mức chấp nhận được và không có lỗi đang mở.
- Launch settings và post-launch actions đã được review.
- DNS TTL, load balancer, firewall và route đã có kế hoạch chuyển.
- Nhóm ứng dụng, database, network, security và business owner đã xác nhận thời điểm.
- Có backup/snapshot và phương án khôi phục theo chính sách workload.
- Có danh sách kiểm tra và người có quyền phê duyệt go/no-go.

Đừng chờ tới phút cutover mới phát hiện target instance thiếu quyền truy cập, không resolve được DNS hoặc không kết nối được license server.

### 7.5. Giai đoạn 5: Cutover

Một quy trình cutover điển hình:

1. Đóng băng thay đổi ứng dụng theo kế hoạch.
2. Thông báo bắt đầu maintenance window.
3. Dừng service ghi dữ liệu hoặc đưa ứng dụng nguồn vào maintenance mode.
4. Xác nhận replication lag đã về mức yêu cầu.
5. Khởi chạy cutover instance từ MGN.
6. Kiểm tra instance đích boot và post-launch actions hoàn tất.
7. Xác minh dữ liệu cuối cùng, kết nối và health check.
8. Chuyển DNS, load balancer hoặc routing tới máy chủ đích.
9. Mở traffic theo từng bước và theo dõi lỗi/latency.
10. Business owner xác nhận nghiệp vụ hoạt động.
11. Finalize cutover và archive source server theo quy trình.

MGN hỗ trợ rút ngắn thời gian chuyển đổi nhờ replication trước đó, nhưng không đảm bảo mọi workload đều có cùng thời gian downtime. Thời gian thực tế phụ thuộc ứng dụng, database, dữ liệu cuối cùng, DNS, network và các bước xác minh.

### 7.6. Giai đoạn 6: Ổn định sau migration

Sau cutover:

- Kiểm tra CPU, memory, disk I/O, network, process và application metrics.
- Kiểm tra log hệ điều hành và ứng dụng.
- Kiểm tra backup, monitoring, alert, patching và security agent.
- Kiểm tra quyền IAM và security group theo nguyên tắc tối thiểu.
- Xác minh DNS, certificate, license và tích hợp bên ngoài.
- So sánh hiệu năng và chi phí với baseline trước migration.
- Cập nhật CMDB, sơ đồ mạng, runbook và tài liệu vận hành.
- Chỉ decommission source server sau thời gian xác nhận và phê duyệt theo chính sách tổ chức.

## 8. Ví dụ: di chuyển ứng dụng ba tầng

### 8.1. Hiện trạng

Một hệ thống nội bộ có ba nhóm máy chủ trong trung tâm dữ liệu:

| Nhóm | Vai trò | Phụ thuộc chính |
|---|---|---|
| Web | Nhận HTTPS request và phục vụ UI | DNS, load balancer, application tier |
| Application | Xử lý nghiệp vụ và gọi API nội bộ | Database, Active Directory, message broker |
| Database | Lưu dữ liệu giao dịch | Storage, backup, DNS và license |

Nhóm muốn chuyển máy chủ sang AWS trước, sau đó mới đánh giá thay database engine hoặc refactor ứng dụng. Vì vậy, MGN phù hợp cho rehost OS và block storage; database migration logic nếu cần đổi engine sẽ là workstream riêng.

### 8.2. Thiết kế target

- Tạo VPC production với private subnet ở ít nhất hai AZ theo yêu cầu availability.
- Tạo staging subnet riêng cho MGN replication resources.
- Tạo operational subnet cho test/cutover EC2 instances.
- Thiết lập Site-to-Site VPN hoặc Direct Connect để replication và hybrid dependency đi qua đường truyền riêng.
- Tạo security group riêng cho web, application, database và staging.
- Chuẩn bị target DNS, Active Directory connectivity, load balancer và monitoring.
- Xác định EC2 instance type, EBS volume type và encryption key.

### 8.3. Chia migration wave

Một kế hoạch có thể chia:

1. Wave 0: kiểm thử network, domain, DNS, monitoring và một máy chủ không quan trọng.
2. Wave 1: database test replica hoặc database server theo chiến lược dữ liệu riêng.
3. Wave 2: application servers sau khi database và identity dependency sẵn sàng.
4. Wave 3: web servers, load balancer và DNS cutover.

Thứ tự thực tế cần dựa trên dependency và khả năng tương thích của ứng dụng. Không bắt buộc phải migrate database bằng MGN cùng lúc với application server; cần xác định rõ database sẽ rehost nguyên máy hay chuyển bằng DMS/backup restore.

### 8.4. Kiểm thử và cutover

Trong test:

- Khởi chạy database và xác minh volume, filesystem, service và dữ liệu.
- Khởi chạy application server trong test subnet có kết nối tới database test.
- Khởi chạy web tier và kiểm tra luồng end-to-end.
- Xác minh authentication, DNS, certificate, outbound API và logging.
- Chạy kiểm thử hiệu năng để kiểm tra instance sizing.

Trong cutover:

- Dừng ghi ở ứng dụng nguồn.
- Chờ replication lag đạt ngưỡng.
- Khởi chạy database cutover trước, kiểm tra health.
- Khởi chạy application tier, xác minh kết nối.
- Chuyển web/load balancer và DNS.
- Theo dõi giao dịch đầu tiên và đối soát dữ liệu.

Nếu lỗi xảy ra, quyết định rollback phải dựa trên việc đã có ghi dữ liệu ở đích hay chưa. Khi cả nguồn và đích cùng nhận ghi, không thể chỉ đổi DNS về nguồn mà bảo đảm dữ liệu nhất quán. Cần có quy trình đối soát hoặc bù trừ trước khi mở lại source.

## 9. Bảo mật và bảo vệ dữ liệu trong migration

### 9.1. Mã hóa và đường truyền

Dữ liệu replication được truyền qua kết nối được mã hóa bằng TLS. Dữ liệu staging được lưu trên AWS storage và cần cấu hình mã hóa theo yêu cầu của tổ chức. Kiểm tra KMS key, key policy và quyền sử dụng key của service role/replication resources.

Khi dùng private connectivity, xác minh route và firewall không làm rò rỉ traffic sang đường truyền ngoài dự kiến. Nếu sử dụng proxy hoặc inspection appliance, không áp dụng TLS interception cho các endpoint MGN được AWS yêu cầu miễn inspection.

### 9.2. Quyền trên source server

Agent có quyền đọc block device và hoạt động ở cấp hệ điều hành. Cần:

- Cài agent bằng tài khoản quản trị được phê duyệt.
- Xác minh installer lấy từ nguồn AWS chính thức.
- Giới hạn outbound connectivity theo endpoint và port cần thiết.
- Theo dõi agent process và log.
- Gỡ agent hoặc dọn cấu hình sau khi migration hoàn tất theo quy trình.

Không chia sẻ thông tin đăng nhập admin của máy chủ nguồn trong file inventory hoặc ticket không được bảo vệ.

### 9.3. Test environment

Test instance có thể chứa dữ liệu production. Hãy bảo vệ test VPC và tài khoản tương tự production:

- Hạn chế inbound access.
- Không công khai IP nếu không cần.
- Dùng dữ liệu đã masking khi quy trình cho phép.
- Không gửi email/SMS thật hoặc gọi payment gateway production trong test.
- Ngăn test instance tác động domain controller, database hoặc message broker production.
- Dọn test resources khi kết thúc.

### 9.4. Cutover và dữ liệu nhạy cảm

Trước khi chuyển dữ liệu, kiểm tra phân loại dữ liệu, yêu cầu residency, retention, encryption và quyền truy cập. Nếu chuyển sang Region khác, cần đánh giá quy định pháp lý và yêu cầu của chủ sở hữu dữ liệu.

## 10. Chi phí MGN và tài nguyên liên quan

### 10.1. Thời gian miễn phí của dịch vụ

Theo pricing FAQ hiện hành, mỗi source server có thời gian sử dụng MGN không tính phí dịch vụ trong 2.160 giờ, tương đương 90 ngày nếu replication liên tục. Thời gian này bắt đầu khi cài AWS Replication Agent và source server bắt đầu active replication. Nếu tiếp tục replicate sau thời gian miễn phí, phí dịch vụ theo giờ sẽ áp dụng theo bảng giá hiện hành.

### 10.2. Tài nguyên vẫn tính phí trong thời gian miễn phí

Thời gian miễn phí của MGN không có nghĩa migration không phát sinh chi phí. Các tài nguyên AWS được provision để hỗ trợ replication và launch vẫn tính theo đơn giá tương ứng:

- Replication server EC2.
- Staging EBS disks và snapshot.
- Test/cutover EC2 instances.
- EBS volume và storage đích.
- FSx for NetApp ONTAP nếu được chọn làm target storage.
- Data transfer và các dịch vụ mạng liên quan.
- Các dịch vụ giám sát, logging, security và backup được bật.

### 10.3. Các yếu tố làm tăng chi phí

- Replication kéo dài quá 90 ngày.
- Initial sync hoặc change rate cao làm cần staging server/disk lớn hơn.
- Launch test instance nhiều lần và để chúng chạy lâu.
- Nhiều wave replicate đồng thời.
- Giữ snapshot, EBS volume hoặc tài nguyên thử nghiệm sau khi không còn cần.
- Chọn instance type lớn hơn nhu cầu thực tế.
- Dùng nhiều AZ/subnet staging không cần thiết.

### 10.4. Kiểm soát chi phí

- Ước tính dung lượng và change rate trước migration.
- Bắt đầu với một wave pilot để đo staging consumption.
- Đặt lịch test và terminate test instances sau khi hoàn tất.
- Theo dõi ngày bắt đầu replication để không vượt quá free period ngoài kế hoạch.
- Dọn tài nguyên staging, snapshot và launch test không còn cần theo quy trình MGN.
- Dùng tag để phân bổ chi phí theo application, wave, owner và cost center.
- Kiểm tra bảng giá MGN và AWS Pricing Calculator trước khi mở rộng.

Không xóa staging resources khi source server vẫn cần replicate hoặc cutover. Chỉ dọn dẹp sau khi trạng thái migration đã được xác nhận và quy trình archive/finalize cho phép.

## 11. Vận hành migration ở quy mô lớn

### 11.1. Application và migration wave

Một application thường gồm nhiều source server có dependency với nhau. Migration wave là nhóm máy chủ được di chuyển trong cùng một cửa sổ hoặc theo một kế hoạch phối hợp.

Lập wave dựa trên:

- Dependency giữa web, application, database, identity và middleware.
- Mức độ quan trọng của ứng dụng.
- Dung lượng và change rate.
- Khả năng test và rollback.
- Cửa sổ downtime và owner sẵn sàng.
- Target account, Region, VPC và license.

Không nên gom quá nhiều ứng dụng không liên quan vào cùng wave chỉ để tăng số lượng máy chủ. Wave quá lớn làm phức tạp go/no-go, kiểm thử và rollback.

### 11.2. Migration connector và AWS Transform

Trong môi trường nhiều tài khoản, AWS Transform workflow và MGN connector có thể hỗ trợ tự động hóa inventory, chuẩn bị quyền và thực hiện thao tác trên source server. Connector có thể hỗ trợ các tác vụ cài agent và quản lý source actions theo quyền đã cấu hình.

Tự động hóa giúp giảm thao tác lặp lại, nhưng cần:

- Phân quyền connector theo account và server scope.
- Kiểm tra script và SSM Parameter Store trước khi chạy source actions.
- Ghi nhận kết quả từng action.
- Có quy trình xử lý khi action thất bại hoặc source server không truy cập được.
- Duy trì phê duyệt thủ công cho cutover production.

### 11.3. Import/export inventory

Với số lượng server lớn, có thể dùng inventory import/export để chuẩn hóa cấu hình theo CSV/template được dịch vụ hỗ trợ. Có thể quản lý các thuộc tính source server, application, wave, tag, launch settings và replication settings theo schema hiện hành.

Trước khi import diện rộng:

1. Xuất template mới từ console.
2. Kiểm tra cột bắt buộc, kiểu dữ liệu và giá trị enum.
3. Thử import một nhóm nhỏ.
4. Đối chiếu kết quả với source server thực tế.
5. Lưu phiên bản inventory và người phê duyệt.

Không tự tạo cột theo suy đoán. Schema import/export có thể thay đổi theo phiên bản dịch vụ.

## 12. Xử lý sự cố thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Không cài được agent | OS/kernel không hỗ trợ, thiếu quyền, thiếu package hoặc disk | Kiểm tra OS support, kernel headers, RAM, root, /tmp và quyền admin |
| Source server không xuất hiện | Sai Region, agent chưa đăng ký, network hoặc identifier trùng | Kiểm tra MGN API 443, log installer và hardware identifier |
| Initial sync kéo dài | Băng thông thấp, change rate cao, staging disk chậm | Đo throughput, disk I/O, network và staging capacity |
| Replication lag tăng | Source ghi dữ liệu nhanh hơn tốc độ replicate | Kiểm tra change rate, bandwidth throttling và replication server |
| Replication server không kết nối | Route, security group, NACL hoặc firewall chặn port | Kiểm tra TCP 1500, route tới staging subnet và network ACL |
| Test instance không boot | Boot mode, driver, disk mapping hoặc OS conversion | Kiểm tra EC2 system log, launch settings và source OS prerequisites |
| Instance boot nhưng app không hoạt động | DNS, AD, license, secret, IP hoặc dependency chưa đúng | Kiểm tra network, DNS, identity, certificate và application logs |
| Post-launch action thất bại | SSM Agent, IAM role, document version hoặc OS filter | Kiểm tra SSM connectivity, execution history và parameters |
| Cutover có dữ liệu thiếu | Replication lag chưa về ngưỡng hoặc ứng dụng còn ghi ở source | Dừng ghi, xác minh final sync và đối soát dữ liệu |
| Chi phí tăng ngoài dự kiến | Test instance, staging resource hoặc replication tồn tại quá lâu | Kiểm tra billing, MGN lifecycle, EC2, EBS, snapshot và FSx |

## 13. Checklist migration máy chủ

### Trước migration

1. Xác định application owner, source server và dependency.
2. Kiểm tra OS support, CPU architecture, kernel, disk layout và license.
3. Xác minh hardware identifier duy nhất.
4. Đánh giá change rate, dung lượng và băng thông.
5. Chọn Region, account, VPC, staging subnet và operational subnet.
6. Cấu hình IAM, KMS, security group, route và firewall.
7. Xác định wave, RPO/RTO, test plan, cutover window và rollback.
8. Ước tính phí dịch vụ MGN và tài nguyên AWS.

### Trong replication

1. Cài AWS Replication Agent.
2. Xác nhận source server đã đăng ký đúng.
3. Theo dõi initial sync.
4. Kiểm tra continuous replication và lag.
5. Theo dõi staging server, EBS disk và snapshot.
6. Điều chỉnh bandwidth/capacity nếu cần.
7. Chỉ chuyển sang test khi replication ổn định.

### Trong test

1. Review EC2 launch template.
2. Launch test instance trong môi trường cô lập.
3. Kiểm tra OS, disk, network, DNS, AD và license.
4. Kiểm tra application, database và dependency.
5. Chạy smoke, integration và performance test.
6. Ghi nhận lỗi và lặp lại test sau khi sửa.
7. Finalize test và dọn test resources.

### Trong cutover

1. Xác nhận go/no-go và người phê duyệt.
2. Đóng băng thay đổi và dừng ghi ở source.
3. Xác nhận replication lag đạt yêu cầu.
4. Launch cutover instance.
5. Kiểm tra post-launch actions và health check.
6. Chuyển DNS/load balancer/routing.
7. Xác nhận nghiệp vụ và đối soát dữ liệu.
8. Theo dõi hệ thống và quyết định finalize hoặc rollback.

### Sau migration

1. Cập nhật monitoring, backup, patching và security.
2. Rà soát IAM role, security group và network route.
3. Tối ưu instance size và EBS storage theo số liệu.
4. Cập nhật CMDB, sơ đồ và runbook.
5. Kiểm soát chi phí staging/test resources.
6. Chỉ decommission source sau khi owner xác nhận và retention policy cho phép.

## 14. Kết luận

AWS Transform MGN, tên mới của AWS Application Migration Service từ tháng 6-2026, là dịch vụ rehost máy chủ bằng block-level replication liên tục. Agent trên máy chủ nguồn truyền dữ liệu tới staging area trong AWS; khi initial sync hoàn tất, nhóm có thể kiểm thử test instance, chuẩn bị cutover và tạo EC2 instance đích theo launch settings.

Một migration thành công bắt đầu từ inventory và dependency map, tiếp theo là chuẩn bị OS, network, IAM, staging subnet và launch template. Nhóm cần theo dõi replication lag, test ứng dụng trong môi trường cô lập, phối hợp dừng ghi và final sync trước cutover, rồi xác minh dữ liệu và nghiệp vụ sau khi chuyển traffic. MGN xử lý phần rehost; DNS, database logic, license, security, monitoring, backup và vận hành vẫn cần kế hoạch riêng.

Ở quy mô lớn, chia ứng dụng thành migration wave giúp phối hợp dependency và cửa sổ downtime. Kết hợp MGN với AWS Transform, DMS, DataSync, Direct Connect, VPN và các dịch vụ AWS khác theo đúng vai trò sẽ giúp giảm rủi ro, kiểm soát chi phí và đưa workload lên AWS theo từng bước có thể kiểm chứng.

## 15. Tài liệu tham khảo chính thức

- [AWS Transform MGN – trang dịch vụ](https://aws.amazon.com/application-migration-service/)
- [Thông báo đổi tên AWS Application Migration Service thành AWS Transform MGN](https://aws.amazon.com/about-aws/whats-new/2026/06/aws-transform-mgn-rebrand/)
- [Migration workflow](https://docs.aws.amazon.com/mgn/latest/ug/migration-workflow-gs.html)
- [Installation requirements](https://docs.aws.amazon.com/mgn/latest/ug/installation-requirements.html)
- [Network requirements](https://docs.aws.amazon.com/mgn/latest/ug/preparing-environments.html)
- [Launch settings](https://docs.aws.amazon.com/mgn/latest/ug/launch-settings.html)
- [Post-launch settings](https://docs.aws.amazon.com/mgn/latest/ug/post-launch-settings.html)
- [Release notes](https://docs.aws.amazon.com/mgn/latest/ug/mgn-release-notes.html)
- [Pricing và pricing FAQ](https://aws.amazon.com/application-migration-service/pricing/)
