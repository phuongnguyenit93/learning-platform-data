# Kiểm thử restore và xác minh tính toàn vẹn dữ liệu

## Mục tiêu học tập

Một bản sao lưu chỉ có giá trị khi tổ chức có thể khôi phục dữ liệu đúng thời điểm, đúng phạm vi và trong thời gian chấp nhận được. Trạng thái backup job thành công cho biết dịch vụ đã tạo recovery point theo quy trình của nó; trạng thái restore job hoàn tất cho biết tài nguyên đã được dựng lại. Cả hai tín hiệu đều chưa chứng minh ứng dụng có thể phục vụ người dùng hoặc dữ liệu đã khôi phục đáp ứng các quy tắc nghiệp vụ.

Bài học đặt việc kiểm thử khôi phục vào bối cảnh vận hành AWS: chọn recovery point, dựng tài nguyên trong môi trường an toàn, đo RTO/RPO, xác minh dữ liệu ở nhiều lớp, kiểm thử ứng dụng và lưu bằng chứng. Nội dung áp dụng cho các workload dùng EC2, EBS, RDS, Aurora, DynamoDB, S3, EFS, FSx, Redshift và các dịch vụ tích hợp AWS Backup.

Sau bài học, người học có thể:

- Phân biệt backup success, restore success, data integrity và application recovery.
- Xây dựng chiến lược kiểm thử dựa trên RTO, RPO, mức độ quan trọng và loại dữ liệu.
- Tạo AWS Backup restore testing plan và selection, chọn recovery point mới nhất hoặc ngẫu nhiên trong một cửa sổ phù hợp.
- Chuẩn bị account, VPC, IAM, KMS và dependency cô lập để chạy thử an toàn.
- Xác minh dữ liệu bằng checksum, manifest, kiểm tra cấu trúc, truy vấn và quy tắc nghiệp vụ.
- Tự động hóa validation bằng EventBridge, Lambda và AWS Backup API.
- Đo thời gian phục hồi, điều tra lỗi và tạo bằng chứng kiểm toán có thể lặp lại.

## 1. Vì sao phải kiểm thử restore?

Backup là một quy trình tạo và lưu recovery point. Restore là quy trình sử dụng recovery point để tái tạo dữ liệu hoặc tài nguyên. Kiểm thử restore kiểm tra khả năng thực hiện quy trình thứ hai trong điều kiện được kiểm soát.

Một backup job có thể thành công nhưng quá trình khôi phục vẫn thất bại vì:

- Recovery point không nằm trong vault hoặc account mà đội khôi phục có quyền truy cập.
- KMS key đã bị vô hiệu hóa, xóa, thay policy hoặc không cho phép role restore giải mã.
- Metadata khôi phục không còn phù hợp với subnet, security group, engine version, instance class hoặc cấu hình hiện tại.
- IAM role thiếu quyền tạo tài nguyên, gắn volume, tạo log hoặc đọc secret.
- Quota, địa chỉ IP, dung lượng, subnet hoặc giới hạn đồng thời không đủ.
- Dữ liệu khôi phục được nhưng database không khởi động, ứng dụng không kết nối hoặc dependency bên ngoài không sẵn sàng.
- Dữ liệu thiếu, sai phiên bản, không nhất quán giữa các bảng hoặc không đáp ứng quy tắc nghiệp vụ.

Kiểm thử định kỳ làm lộ các vấn đề này trước khi có sự cố thật. Nó cũng giúp đội ngũ hiểu rõ ai thực hiện restore, cần quyền nào, mất bao lâu, phải kiểm tra gì và bằng chứng nào chứng minh hệ thống đã phục hồi.

## 2. Phân biệt các trạng thái và khái niệm

| Khái niệm | Ý nghĩa | Điều chưa thể kết luận |
|---|---|---|
| Backup job COMPLETED | Dịch vụ hoàn tất job tạo recovery point | Chưa chứng minh dữ liệu khôi phục được |
| Recovery point available | Có điểm khôi phục trong vault hoặc dịch vụ nguồn | Chưa chứng minh quyền truy cập và metadata còn hợp lệ |
| Restore job COMPLETED | Dịch vụ hoàn tất thao tác tạo tài nguyên hoặc dữ liệu khôi phục | Chưa chứng minh dữ liệu logic đúng hoặc ứng dụng hoạt động |
| Integrity validation successful | Các phép kiểm tra toàn vẹn đã định nghĩa đều đạt | Không chứng minh mọi trường hợp nghiệp vụ đều đúng |
| Application validation successful | Các dependency và luồng ứng dụng được kiểm tra hoạt động | Không thay thế kiểm thử tải hoặc kiểm thử bảo mật toàn diện |
| DR exercise passed | Kịch bản phục hồi đã đạt tiêu chí được thống nhất | Chỉ có ý nghĩa trong phạm vi, thời điểm và giả định đã kiểm thử |

**Recovery point** là điểm dữ liệu có thể dùng để khôi phục. Với snapshot, điểm này đại diện cho trạng thái dữ liệu tại thời điểm snapshot. Với continuous backup hoặc point-in-time recovery (PITR), có thể chọn một thời điểm trong khoảng thời gian mà dịch vụ hỗ trợ.

**Restore test** thường tạo tài nguyên khôi phục tạm thời để kiểm tra. **Disaster recovery exercise** có phạm vi lớn hơn: có thể bao gồm account hoặc Region dự phòng, DNS, mạng, IAM, secrets, thứ tự khởi động, chuyển traffic, truyền thông sự cố và quyết định failback.

## 3. RTO, RPO và cách đo kết quả

RTO (Recovery Time Objective) là khoảng thời gian gián đoạn tối đa mà tổ chức đặt mục tiêu chấp nhận. RPO (Recovery Point Objective) là lượng dữ liệu tối đa có thể mất, thường biểu diễn bằng thời gian tính từ lúc sự cố đến điểm dữ liệu có thể khôi phục.

Ví dụ, một dịch vụ đặt RTO 60 phút và RPO 15 phút:

- Khi sự cố bắt đầu lúc 10:00, dịch vụ phải trở lại trạng thái phục vụ được trước 11:00.
- Dữ liệu mới nhất được khôi phục phải không cũ hơn 09:45 theo tiêu chí của workload.

Đây là mục tiêu thiết kế, không phải cam kết thời gian của AWS Backup. AWS không cung cấp SLA cho thời gian restore; thời gian thực tế có thể thay đổi theo tải hệ thống, dung lượng dữ liệu, loại resource và trạng thái dịch vụ.

### 3.1. Đo đúng các mốc thời gian

Không chỉ đo thời gian từ lúc bấm Restore đến lúc job hoàn tất. Với một dịch vụ thực tế, hãy ghi:

1. **T0 – Incident declared:** thời điểm bắt đầu tính thời gian phục hồi theo quy ước.
2. **T1 – Restore initiated:** thời điểm restore job được yêu cầu.
3. **T2 – Resource available:** tài nguyên mới đã được tạo và có thể truy cập.
4. **T3 – Data validated:** kiểm tra cấu trúc và dữ liệu đạt.
5. **T4 – Application ready:** ứng dụng và dependency thiết yếu hoạt động.
6. **T5 – Service accepted:** người phụ trách xác nhận có thể chuyển traffic hoặc hoàn tất bài diễn tập.

Restore duration của AWS Backup thường phản ánh thời gian của restore job. RTO đầu-cuối cần tính cả các bước cần thiết khác theo định nghĩa tổ chức. Nếu đội ngũ chỉ ghi T1 đến T2, báo cáo đó không thể thay cho RTO từ T0 đến T5.

### 3.2. Đo RPO bằng dữ liệu, không chỉ bằng lịch backup

Lịch backup 15 phút không tự chứng minh RPO đạt 15 phút. Một job có thể trễ hoặc thất bại; recovery point có thể chưa được copy sang vault hoặc Region dự phòng. Hãy ghi thời điểm dữ liệu thực tế trong recovery point và so sánh với mốc sự cố giả lập.

Đối với database, dùng transaction marker hoặc một bảng audit ghi timestamp và sequence number. Đối với file/object, dùng manifest có thời gian tạo và phiên bản. Đối với hệ thống sự kiện, ghi event offset hoặc sequence. Kiểm tra dữ liệu phục hồi đến đâu mới cho biết lượng dữ liệu mất thực tế.

## 4. Xây dựng chiến lược kiểm thử

Không phải workload nào cũng cần restore toàn bộ mỗi ngày. Tần suất và độ sâu kiểm thử nên dựa trên mức độ quan trọng, tốc độ thay đổi dữ liệu, yêu cầu tuân thủ và chi phí.

| Nhóm kiểm thử | Phạm vi | Tần suất gợi ý để thiết kế |
|---|---|---|
| Kiểm tra recovery point | Job, vault, tuổi recovery point, mã hóa, copy | Hằng ngày hoặc theo lịch backup |
| Restore kỹ thuật | Một resource đại diện, xác minh restore job | Hằng tuần hoặc hằng tháng |
| Kiểm tra toàn vẹn dữ liệu | Checksum, số lượng bản ghi, constraint, manifest | Mỗi lần restore test |
| Kiểm thử ứng dụng | Health check, kết nối database, luồng đọc/ghi thử | Hằng tháng hoặc sau thay đổi lớn |
| DR theo Region/account | Dựng lại một phần hoặc toàn bộ hệ thống ở môi trường dự phòng | Theo mức criticality và quy định |
| Diễn tập failover/failback | Chuyển traffic, DNS, dependency và quy trình con người | Theo kế hoạch DR đã phê duyệt |

Đây là tần suất tham khảo. Tổ chức phải chọn lịch phù hợp với retention, RTO/RPO và khả năng chịu tải của môi trường. Một test chỉ khôi phục một EC2 instance không chứng minh toàn bộ hệ thống nhiều tầng có thể phục hồi.

### 4.1. Phân tầng theo mức độ quan trọng

- **Tier 0 – Critical:** giao dịch, thanh toán, danh tính hoặc control plane nội bộ. Cần kiểm thử recovery point, restore, dữ liệu và ứng dụng với tần suất cao; có thể cần diễn tập account/Region.
- **Tier 1 – Important:** dịch vụ ảnh hưởng lớn nhưng có phương án vận hành tạm thời. Kiểm thử restore định kỳ và kiểm tra phụ thuộc.
- **Tier 2 – Standard:** có thể phục hồi trong thời gian dài hơn. Có thể chọn mẫu resource đại diện và kiểm thử theo lịch ít thường xuyên hơn.
- **Tier 3 – Archive:** chủ yếu yêu cầu truy xuất dữ liệu lưu trữ. Cần kiểm tra khả năng truy cập, giải mã, đọc và xác minh nội dung theo chu kỳ.

Đừng dùng một lịch duy nhất cho tất cả resource. Hãy ưu tiên các hệ thống có RTO/RPO ngắn, dữ liệu thay đổi nhanh, nhiều dependency hoặc yêu cầu khôi phục phức tạp.

## 5. Mô hình kiểm thử theo nhiều lớp

Một bài test đáng tin cậy cần đi qua nhiều lớp. Mỗi lớp trả lời một câu hỏi khác nhau.

~~~mermaid
flowchart TD
    A[Recovery point được chọn] --> B[Restore job hoàn tất]
    B --> C[Resource và storage truy cập được]
    C --> D[Integrity: checksum / cấu trúc / dữ liệu]
    D --> E[Application: dependency / health / giao dịch thử]
    E --> F[Đối chiếu RTO / RPO và tiêu chí]
    F --> G[Evidence, kết luận và action items]
~~~

1. **Availability:** recovery point có sẵn và restore role có thể truy cập.
2. **Resource integrity:** tài nguyên được tạo với thuộc tính cần thiết, volume hoặc file system có thể mount.
3. **Storage integrity:** nội dung file hoặc object đọc được và checksum khớp.
4. **Logical integrity:** database mở được, index/constraint hợp lệ, dữ liệu quan trọng có đủ.
5. **Application integrity:** ứng dụng kết nối đúng dependency, xử lý được request đại diện và không ghi nhầm vào production.
6. **Operational readiness:** monitoring, logging, secret, IAM, DNS, runbook và owner đã sẵn sàng.

Nếu một lớp không áp dụng cho resource cụ thể, ghi rõ lý do thay vì bỏ qua âm thầm.

## 6. AWS Backup Restore Testing hoạt động như thế nào?

AWS Backup có tính năng Restore testing để đánh giá định kỳ khả năng khôi phục và theo dõi thời gian hoàn tất restore job. Một restore testing plan gồm hai phần:

- **Plan:** tên, lịch chạy, thời điểm bắt đầu, start window và cách chọn recovery point.
- **Selection:** resource type, phạm vi protected resources, IAM role, tham số restore và thời gian giữ resource tạm để validation.

Khi đến lịch, AWS Backup chọn resource và recovery point phù hợp, sau đó khởi chạy restore job giống quy trình restore on-demand. Kết quả hiển thị trong AWS Backup console và có thể truy vấn bằng API/CLI. Restore testing có thể tích hợp AWS Backup Audit Manager để đánh giá thời gian restore có đạt mục tiêu đặt ra hay không.

Restore testing không phải bài kiểm thử logic ứng dụng tự động. Muốn xác minh dữ liệu và health check, cần xây dựng validation workflow hoặc chạy các bước kiểm tra riêng.

### 6.1. Các resource type được hỗ trợ

Theo tài liệu AWS Backup Restore testing, các resource type có thể đưa vào plan gồm:

- Amazon Aurora và Amazon RDS.
- Amazon DocumentDB và Amazon Neptune.
- Amazon DynamoDB.
- Amazon EBS và Amazon EC2.
- Amazon EFS.
- Amazon FSx for Lustre, ONTAP, OpenZFS và Windows File Server.
- Amazon Redshift.
- Amazon S3.

Phạm vi hỗ trợ có thể khác nhau theo Region, loại recovery point, engine và tính năng restore. Kiểm tra bảng feature availability của AWS Backup cho đúng resource trước khi thiết kế lịch.

### 6.2. Restore test và restore on-demand

| Thuộc tính | Restore testing | Restore on-demand |
|---|---|---|
| Cách chạy | Theo lịch của plan | Người vận hành hoặc automation yêu cầu |
| Recovery point | Chọn theo quy tắc trong plan | Người dùng chọn recovery point |
| Kết quả | Có thể ghi nhận validation và thời gian test | Tài nguyên khôi phục thường được giữ lại |
| Cleanup | AWS Backup bắt đầu xóa tài nguyên test sau validation window | Người dùng quản lý vòng đời resource |
| Mục tiêu | Kiểm tra định kỳ và tạo bằng chứng | Khôi phục khi cần hoặc xử lý sự cố |

Restore testing dùng cùng loại recovery point và restore operation như restore on-demand. Một bài test tốt vẫn cần mô phỏng các tham số và dependency gần với kịch bản khôi phục thật.

## 7. Thiết kế restore testing plan và recovery point selection

Khi tạo plan, chọn lịch chạy và cửa sổ bắt đầu phù hợp với quy mô restore. AWS Backup có thể ngẫu nhiên hóa thời điểm bắt đầu các restore job trong start window để phân tán tải. Start window được cấu hình theo giờ; giới hạn hiện hành là từ 1 đến 168 giờ.

Recovery point selection xác định:

- **IncludeVaults:** backup vault được phép chọn recovery point; có thể chỉ định vault cụ thể hoặc wildcard theo API.
- **ExcludeVaults:** vault cần loại trừ nếu có.
- **Algorithm:** chọn recovery point mới nhất trong cửa sổ hoặc một recovery point ngẫu nhiên trong cửa sổ.
- **RecoveryPointTypes:** chọn snapshot, continuous/PITR hoặc cả hai.
- **SelectionWindowDays:** khoảng thời gian tối đa để tìm recovery point, từ 1 đến 365 ngày.

Chọn LATEST_WITHIN_WINDOW khi cần kiểm tra điểm khôi phục gần nhất. Chọn RANDOM_WITHIN_WINDOW khi muốn lấy mẫu recovery point cũ hơn để phát hiện vấn đề liên quan đến thời gian lưu trữ hoặc các thay đổi lâu ngày. Hai cách chọn trả lời các câu hỏi khác nhau; có thể tạo các plan riêng nếu cần cả hai góc nhìn.

### 7.1. Tính selection window

Selection window được tính từ thời điểm restore job thực sự chạy, không phải thời gian dự kiến trên lịch. Vì job có thể bắt đầu trong start window, selection window phải đủ rộng để recovery point hợp lệ không bị loại do lịch chạy trễ.

Ví dụ:

- Backup chạy mỗi ngày.
- Restore testing plan có thể bắt đầu trong cửa sổ 6 giờ.
- SelectionWindowDays được đặt 1 ngày.

Nếu job thực tế bắt đầu sau thời điểm recovery point vừa vượt khỏi cửa sổ 1 ngày, resource có thể không có recovery point đủ điều kiện. Hãy chọn selection window lớn hơn chu kỳ backup cộng phần start window cần thiết, sau đó kiểm tra retention để tránh chọn điểm quá cũ.

### 7.2. Chọn PITR hay snapshot

Snapshot phù hợp để kiểm tra restore theo các mốc backup đã tạo. Continuous backup/PITR phù hợp khi cần khôi phục tới một thời điểm cụ thể trong khoảng dịch vụ hỗ trợ.

PITR không tự đảm bảo mọi transaction trong thời gian mong muốn đã được ghi nhận. Với database, hãy xác minh transaction marker hoặc timestamp sau restore. Kiểm tra feature availability và retention của PITR theo từng resource type.

### 7.3. Protected resource selection và recovery point selection khác nhau

Resource selection xác định protected resource nào được đưa vào plan. Recovery point selection xác định recovery point nào của resource đó đủ điều kiện để restore.

Tag conditions của protected resource được đánh giá dựa trên tag của recovery point mới nhất trong vault chứa resource. Các tag condition không phải bộ lọc chọn recovery point cũ hơn. Do đó, đừng suy luận rằng recovery point được restore chắc chắn có cùng bộ tag với recovery point mới nhất.

Mỗi lần plan chạy, AWS Backup restore tối đa một recovery point cho mỗi protected resource được chọn. Nếu cần kiểm tra nhiều mốc dữ liệu của cùng một resource, hãy thiết kế nhiều lần chạy hoặc một kịch bản on-demand riêng.

### 7.4. Quota và concurrency

Một số giới hạn phổ biến của restore testing plan gồm 100 plans mỗi account/Region, 30 selections mỗi plan, tối đa 30 ARN hoặc condition theo selection và selection window tối đa 365 ngày. Số restore job đồng thời còn phụ thuộc resource type. Nếu quota concurrency đạt ngưỡng, job có thể không khởi chạy trong start window và bị đánh dấu FAILED.

Đọc quota hiện hành trước khi mở rộng plan. Chia nhỏ lịch, tăng start window hợp lý hoặc yêu cầu tăng quota nếu dịch vụ cho phép. Không dồn tất cả database, volume và bucket lớn vào cùng một thời điểm nếu điều đó gây áp lực lên account hoặc dependency.

## 8. Môi trường khôi phục an toàn

Best practice là chỉ định account chuyên dùng cho restore test. Môi trường test phải cô lập đủ để tài nguyên khôi phục không gây tác động tới production.

### 8.1. Account và network

- Dùng account hoặc OU dành cho recovery exercise nếu mô hình quản trị cho phép.
- Tạo VPC, subnet và security group có phạm vi kết nối giới hạn.
- Chặn route tới production data plane nếu bài test không cần truy cập.
- Dùng DNS zone hoặc hostname riêng cho test.
- Tránh trùng tên resource, endpoint và địa chỉ IP với production.
- Không mở inbound rộng chỉ để làm health check dễ dàng.

Một số restore metadata được suy luận từ recovery point, nhưng môi trường đích vẫn có thể cần subnet, security group hoặc tham số khác. Hãy xem lại các tham số restore trước khi chạy.

### 8.2. IAM least privilege

Restore testing sử dụng IAM role được chỉ định trong selection. Khi tạo plan, AWS Backup tạo service-linked role cho tính năng. Restore role cần các quyền trong policy AWSBackupServiceRolePolicyForRestores hoặc quyền tương đương đã được tùy chỉnh đúng phạm vi.

Ngoài quyền của AWS Backup, hãy xác minh quyền tạo resource đích, gắn volume, áp dụng tag, truy cập KMS key, ghi log và đọc secret. Nếu dùng custom role, thiếu một quyền phụ như tag resource cũng có thể làm restore hoặc cleanup thất bại.

Không cấp quyền AdministratorAccess chỉ để xử lý lỗi restore. Dùng CloudTrail và lỗi của job để xác định API bị từ chối, rồi bổ sung quyền nhỏ nhất cần thiết.

### 8.3. KMS và mã hóa

Restore có thể cần giải mã recovery point và mã hóa resource đích bằng KMS key khác. Kiểm tra:

- Key còn hoạt động và ở đúng Region.
- Key policy cho phép principal restore hoặc dịch vụ thực hiện thao tác cần thiết.
- IAM policy và grant có đủ quyền sử dụng key.
- Key cross-account được chia sẻ theo đúng quy trình.
- Có quyền tạo grant hoặc dùng key theo yêu cầu của resource type.

Không giả định quyền đọc backup vault đồng nghĩa với quyền giải mã dữ liệu. Khi dùng customer managed key, đưa KMS policy và khả năng truy cập key vào bài test định kỳ.

### 8.4. Secret và dependency

Ứng dụng có thể khôi phục database nhưng không khởi động vì thiếu secret, certificate, parameter hoặc endpoint. Dùng secret dành riêng cho test, tránh kết nối đến production payment gateway, email provider hoặc webhook thật.

Tạo stub hoặc sandbox cho dependency bên ngoài. Nếu cần xác minh kết nối tới dịch vụ AWS, dùng endpoint và role trong account test. Ghi lại các dependency bị giả lập để báo cáo không mô tả sai mức độ phục hồi.

## 9. Metadata và những khác biệt khi restore

AWS Backup có thể suy luận một phần metadata cần thiết từ recovery point. Với resource type nhất định, người vận hành có thể override các trường như subnet, security group, instance class, database name, availability zone hoặc encryption key.

API GetRecoveryPointRestoreMetadata giúp lấy metadata được lưu cùng recovery point. Khi tự động hóa restore, không nên hard-code mọi giá trị từ môi trường cũ. Hãy phân biệt:

- **Metadata cần giữ:** engine, cấu hình dữ liệu hoặc thuộc tính cần để tái tạo đúng workload.
- **Metadata cần thay:** subnet, security group, KMS key hoặc tên resource để phù hợp account test.
- **Metadata nhạy cảm:** secret, password hoặc thông tin định danh cần lấy từ secret manager.

Phần lớn restore bằng AWS Backup tạo resource mới để bảo vệ resource đang tồn tại. Tuy nhiên, có ngoại lệ destructive restore: Amazon Redshift Serverless namespace restore ghi đè dữ liệu trong target namespace; SAP HANA trên EC2 restore ghi đè database tại vị trí đích được chỉ định. Kiểm tra tài liệu resource-specific và chỉ dùng target cô lập cho các trường hợp này.

### 9.1. Tag và cleanup

Với resource type hỗ trợ tag-on-restore, AWS Backup gắn tag awsbackup-restore-test để nhận diện resource test và quản lý cleanup. Nếu ai đó xóa tag này trước khi cleanup, AWS Backup có thể không xóa được resource và cần thao tác thủ công.

Một số resource như DynamoDB và S3 không hỗ trợ tag-on-restore trong restore testing; cleanup dựa trên tên resource. Việc xóa bucket S3 có thể mất vài ngày do lifecycle rule cần thời gian xử lý object. Đừng giả định mọi resource được xóa ngay khi validation kết thúc.

Tạo quy trình kiểm tra resource còn sót lại sau test, theo dõi deletion status và cảnh báo khi cleanup thất bại. Đưa chi phí lưu trữ tạm thời, snapshot và resource đang chạy vào ngân sách restore test.

## 10. Tự động hóa validation với EventBridge và Lambda

AWS Backup có thể phát sự kiện Restore Job State Change lên EventBridge. Khi job của restore testing chuyển sang COMPLETED, rule có thể gọi Lambda hoặc target khác để thực hiện kiểm tra dữ liệu và ứng dụng.

Luồng mẫu:

~~~mermaid
flowchart TD
    A[AWS Backup restore test] --> B[Restore Job State Change]
    B --> C{status = COMPLETED?}
    C -->|No| D[Log trạng thái và xử lý lỗi job]
    C -->|Yes| E[EventBridge rule]
    E --> F[Lambda validation workflow]
    F --> G[Kiểm tra resource, dữ liệu, ứng dụng]
    G --> H[PutRestoreValidationResult]
    H --> I[AWS Backup console / API / audit evidence]
~~~

Event pattern có thể lọc theo resource type và restore testing plan ARN:

~~~json
{
  "source": ["aws.backup"],
  "detail-type": ["Restore Job State Change"],
  "detail": {
    "resourceType": ["RDS"],
    "restoreTestingPlanArn": ["arn:aws:backup:ap-southeast-1:111122223333:restore-testing-plan:weekly_critical"],
    "status": ["COMPLETED"]
  }
}
~~~

Không gọi validation khi job chưa hoàn tất. Nếu restore job FAILED, hãy ghi nhận lỗi restore riêng; không báo validation thành công chỉ vì Lambda đã chạy.

### 10.1. Các trường dữ liệu cần dùng

Event restore job có thể cung cấp restoreJobId, resourceType, createdResourceArn, recovery point và restore testing plan ARN. Dùng ARN của resource mới để tìm đúng tài nguyên được tạo trong lần test này. Không suy ra tên resource từ resource nguồn nếu AWS Backup tạo tên mới.

Validation workflow cần:

1. Xác thực event đến từ nguồn AWS Backup và đúng plan được phép.
2. Đọc resource ARN và restore job ID.
3. Chờ resource sẵn sàng theo retry có giới hạn.
4. Chạy các kiểm tra đã định nghĩa cho resource type.
5. Ghi kết quả chi tiết vào log hoặc hệ thống lưu bằng chứng.
6. Gọi PutRestoreValidationResult với trạng thái và thông điệp.

### 10.2. Ghi nhận kết quả

PutRestoreValidationResult cho phép gửi kết quả validation độc lập. Các trạng thái hợp lệ gồm SUCCESSFUL, FAILED, TIMED_OUT và VALIDATING. API yêu cầu RestoreJobId và ValidationStatus; ValidationStatusMessage là tùy chọn.

Ví dụ minh họa bằng AWS CLI:

~~~bash
aws backup put-restore-validation-result --restore-job-id 12345678-1234-1234-1234-123456789012 --validation-status SUCCESSFUL --validation-status-message "RDS connectivity, schema and critical data checks passed"
~~~

Một khi validation status đã được đặt, trạng thái đó không thể thay đổi. Vì vậy, hãy coi lời gọi API là thao tác một lần và chỉ gửi kết quả sau khi workflow đã có kết luận. Mặc dù API liệt kê VALIDATING như một giá trị hợp lệ, không dùng nó như trạng thái tạm thời nếu workflow còn cần cập nhật sang kết quả cuối; trạng thái nội bộ của workflow nên được lưu riêng cho đến khi hoàn tất.

PutRestoreValidationResult không có sẵn trong AWS SDK for JavaScript Lambda SDK theo tài liệu AWS; ví dụ chính thức khuyến nghị dùng Lambda layer chứa SDK mới nhất. Với runtime khác, kiểm tra phiên bản SDK và API support trước khi triển khai.

### 10.3. Idempotency và retry

EventBridge và Lambda có thể gửi lại event. Validation phải có tính idempotent:

- Dùng restoreJobId làm khóa định danh lần test.
- Không tạo side effect nghiệp vụ thật trong bước kiểm tra.
- Lưu trạng thái từng phép kiểm tra để tránh chạy lặp không kiểm soát.
- Retry lỗi tạm thời có exponential backoff và giới hạn thời gian.
- Không gửi nhiều kết quả cuối cho cùng một restore job.

Nếu workflow timeout hoặc không thể xác minh, ghi TIMED_OUT hoặc FAILED theo chính sách. Một kết quả chưa biết không nên được coi là thành công.

## 11. Xác minh tính toàn vẹn dữ liệu

Tính toàn vẹn có nhiều lớp. Một checksum khớp chứng minh byte được so sánh không đổi theo thuật toán đó; nó không chứng minh bản ghi có ý nghĩa đúng, transaction đã commit hoặc dữ liệu đáp ứng quy tắc nghiệp vụ.

| Lớp kiểm tra | Ví dụ | Điều chứng minh |
|---|---|---|
| Byte-level | SHA-256 của file hoặc object | Nội dung byte khớp với manifest |
| Object-level | Số lượng object, key, version, metadata | Tập object và thuộc tính mong đợi tồn tại |
| File-system | Mount, quyền, owner, file count, filesystem check | File system có thể truy cập và cấu trúc phù hợp |
| Database structural | Engine khởi động, schema, index, constraint | Database có cấu trúc đọc được |
| Database logical | Row count, aggregate, foreign key, transaction marker | Dữ liệu logic đáp ứng điều kiện đã định nghĩa |
| Application | API health, login, đọc/ghi thử, workflow nghiệp vụ | Ứng dụng dùng được với dữ liệu đã khôi phục |

### 11.1. Manifest và checksum

Trước khi backup hoặc tại thời điểm tạo dữ liệu chuẩn, có thể tạo manifest gồm:

- Đường dẫn hoặc object key.
- Kích thước byte.
- Checksum và thuật toán.
- Phiên bản hoặc timestamp.
- Nhãn dữ liệu và owner.

Sau khi restore, tính lại checksum trên nội dung đã khôi phục và so sánh với manifest tương ứng recovery point. Manifest phải được lưu độc lập, có versioning và quyền ghi hạn chế; nếu manifest nằm cùng nơi với dữ liệu bị hỏng hoặc bị sửa, nó không còn là bằng chứng độc lập.

SHA-256 phù hợp để phát hiện thay đổi nội dung ngoài ý muốn. Nếu threat model bao gồm kẻ tấn công có thể sửa cả dữ liệu và manifest, hãy ký manifest hoặc lưu hash gốc ở một hệ thống được bảo vệ khác.

### 11.2. Lưu ý với Amazon S3 ETag

Không mặc định ETag là MD5 của object. Với multipart upload, mã hóa hoặc một số luồng copy, ETag có thể không phải checksum MD5 của toàn bộ nội dung. Dùng checksum được S3 hỗ trợ như SHA-256 hoặc CRC theo khả năng của thao tác upload/download, và tính lại checksum trên nội dung thực tế khi cần bằng chứng độc lập.

Ví dụ tải object test về và tính SHA-256:

~~~bash
aws s3api get-object --bucket recovery-test-data --key manifests/orders-2026-11.csv restored-orders.csv
sha256sum restored-orders.csv
~~~

Đối chiếu kết quả với manifest được lưu độc lập. Với object lớn hoặc multipart, kiểm tra checksum type và cách S3 tổng hợp checksum để so sánh đúng cùng một phạm vi dữ liệu.

### 11.3. Chọn dữ liệu kiểm tra đại diện

Không nhất thiết phải quét toàn bộ petabyte dữ liệu trong mọi lần test. Có thể kết hợp:

- Kiểm tra toàn bộ metadata và số lượng resource.
- Kiểm tra checksum cho dữ liệu có giá trị cao.
- Lấy mẫu có phân tầng theo partition, ngày, tenant hoặc loại file.
- Kiểm tra các bản ghi mới nhất, cũ nhất và các mốc biên.
- Kiểm tra transaction marker, tổng tiền, số lượng đơn và quan hệ dữ liệu.

Ghi rõ tỷ lệ lấy mẫu, cách chọn mẫu, thời điểm và giới hạn. Nếu chỉ lấy mẫu 1%, không mô tả kết quả là đã xác minh toàn bộ dataset.

## 12. Xác minh EC2 và EBS

Restore EC2/EBS cần xác minh cả block device, file system, OS và ứng dụng:

1. Instance hoặc volume được tạo ở subnet và AZ mong muốn.
2. Instance có trạng thái running và system status checks đạt.
3. Volume được gắn đúng device và có trạng thái available/in-use phù hợp.
4. File system mount thành công và có quyền truy cập đúng.
5. File quan trọng tồn tại, kích thước và checksum phù hợp.
6. Service khởi động, đọc cấu hình và kết nối dependency.
7. Health check ứng dụng trả kết quả mong đợi.

### 12.1. Kiểm tra ở tầng hệ điều hành

Với Linux, dùng lsblk, findmnt, df và journalctl để xác minh volume, mount point và log khởi động. Không chạy fsck trên file system đang mount ở chế độ ghi. Nếu cần kiểm tra offline, detach volume và dùng quy trình phù hợp với loại file system.

Ví dụ kiểm tra trạng thái mount:

~~~bash
lsblk -f
findmnt
df -h
systemctl --failed
~~~

Với Windows, kiểm tra disk online, volume letter, NTFS/ReFS và Windows Event Log. Tránh thay đổi chữ ký disk hoặc drive mapping trong lúc chỉ cần đọc kiểm tra.

Volume tạo từ EBS snapshot có thể cần khởi tạo block từ snapshot trước khi đạt hiệu năng đầy đủ. Trong thời gian này, lần đọc block chưa được tải có thể có độ trễ cao hơn. Nếu RTO bao gồm khả năng phục vụ tải thực tế, hãy đo cả thời gian khởi tạo hoặc dùng cơ chế như Fast Snapshot Restore hay Provisioned Rate for Volume Initialization khi phù hợp.

### 12.2. Kiểm tra file và ứng dụng

Tạo tập file quan trọng có manifest checksum, ví dụ file cấu hình đã version, artifact hoặc dữ liệu giao dịch export. Sau restore, tính lại checksum và kiểm tra quyền owner/group. Một file có checksum đúng nhưng quyền truy cập sai vẫn có thể làm ứng dụng không hoạt động.

Với EC2 chạy database, không chỉ kiểm tra process đang chạy. Thực hiện truy vấn đọc, kiểm tra schema và xác minh transaction marker theo quy trình của database engine.

## 13. Xác minh RDS, Aurora và database quan hệ

Với database, restore job hoàn tất mới là bước đầu. Kiểm tra:

- Engine và phiên bản tương thích với ứng dụng.
- Instance/cluster có trạng thái available.
- Endpoint và security group cho phép client test kết nối.
- Database, schema, table, index và constraint cần thiết tồn tại.
- Số lượng bản ghi hoặc aggregate quan trọng khớp với baseline.
- Transaction marker phản ánh RPO mong muốn.
- Các query nghiệp vụ trọng yếu trả kết quả đúng.

### 13.1. Kiểm tra schema và dữ liệu

Ví dụ PostgreSQL:

~~~sql
SELECT current_database(), current_timestamp;
SELECT COUNT(*) FROM orders;
SELECT status, COUNT(*) FROM orders GROUP BY status ORDER BY status;
SELECT MAX(updated_at) FROM orders;
~~~

Ví dụ MySQL:

~~~sql
SELECT DATABASE(), NOW();
SELECT COUNT(*) FROM orders;
SELECT status, COUNT(*) FROM orders GROUP BY status ORDER BY status;
SELECT MAX(updated_at) FROM orders;
~~~

Các truy vấn trên chỉ minh họa. Bảng và cột thực tế cần được chọn theo data contract của ứng dụng. Với bảng lớn, COUNT(*) có thể tốn tài nguyên; hãy dùng snapshot baseline, partition aggregate hoặc truy vấn được tối ưu.

### 13.2. Kiểm tra constraint và quan hệ

Đối với relational database, xác minh primary key, foreign key, unique constraint và các quy tắc không-null. Kiểm tra số bản ghi mồ côi bằng anti-join hoặc query tương ứng. Kiểm tra index quan trọng và kế hoạch query nếu hiệu năng là một phần của tiêu chí phục hồi.

Một database có thể khởi động dù dữ liệu bị thiếu hoặc các bảng không đồng bộ. Vì vậy, hãy chọn các invariant đại diện, ví dụ tổng số đơn theo trạng thái, tổng giá trị giao dịch theo ngày hoặc quan hệ order-item-customer.

### 13.3. Consistency và transaction

Snapshot ở cấp storage có thể nhất quán crash-consistent hoặc application-consistent tùy dịch vụ, engine và cách tạo backup. Đối với database, ưu tiên cơ chế backup được tích hợp với engine và kiểm tra transaction đã commit.

Nếu dữ liệu liên quan đến nhiều database hoặc nhiều resource, restore riêng từng resource có thể tạo ra trạng thái không đồng bộ. Cần kiểm thử theo một recovery point set hoặc một quy trình có thể tái lập quan hệ giữa các thành phần.

## 14. Xác minh DynamoDB và Amazon S3

### 14.1. DynamoDB

Với DynamoDB, kiểm tra:

- Table được tạo và trạng thái ACTIVE.
- Partition key, sort key, index và stream configuration cần thiết.
- TTL, encryption, point-in-time recovery và autoscaling theo thiết kế.
- Số lượng item hoặc aggregate ở partition quan trọng.
- Một tập item đại diện có key và attribute đúng.
- Ứng dụng đọc được các item quan trọng bằng IAM role test.

Không dùng một lần Scan có Limit để kết luận tổng số item của toàn bảng. Scan có thể phân trang và chỉ trả về số item trong trang hiện tại. Nếu cần tổng count, xử lý pagination đầy đủ hoặc dùng số liệu/manifest đã được tạo cho mục tiêu kiểm thử.

### 14.2. Amazon S3

Với S3, xác minh:

- Bucket đích được tạo đúng Region và encryption setting.
- Prefix hoặc object key quan trọng tồn tại.
- Versioning và object metadata đáp ứng yêu cầu.
- Object có thể đọc bằng role được dự kiến.
- Checksum hoặc manifest khớp với baseline.
- Lifecycle, storage class, retention và access policy không vô tình loại bỏ hoặc chặn dữ liệu cần phục hồi.

Nếu backup có nhiều version, hãy kiểm tra đúng version và thời điểm mong muốn. Đếm object qua ListObjectsV2 cần xử lý continuation token; một trang đầu tiên không đại diện toàn bucket.

Đối với bucket rất lớn, tạo manifest phân vùng theo prefix và xác minh mẫu có kiểm soát. Ghi rõ object nào đã kiểm tra, object nào bỏ qua và lý do.

## 15. Xác minh EFS, FSx và Redshift

### 15.1. EFS

Sau khi restore EFS:

- Mount file system từ EC2 hoặc client trong subnet được phép.
- Kiểm tra mount target, security group và DNS.
- Xác minh thư mục, file count, quyền POSIX, owner/group và checksum.
- Thử đọc/ghi một file kiểm tra trong thư mục test riêng.
- Kiểm tra ứng dụng có thể truy cập path mà nó sử dụng.

Nếu dùng access point, xác minh root directory và POSIX identity phù hợp. Không để bài test vô tình ghi dữ liệu vào file system production.

### 15.2. FSx

Với FSx for Windows, kiểm tra trạng thái file system, DNS, domain join, SMB share, ACL và quyền truy cập của user test. Với FSx for ONTAP, OpenZFS hoặc Lustre, xác minh volume, export/share, mount, snapshot và file metadata theo đúng protocol.

Không chỉ kiểm tra file system available. Một share có thể tồn tại nhưng người dùng hoặc service account không có quyền đọc dữ liệu.

### 15.3. Redshift

Với Redshift, kiểm tra cluster hoặc namespace available, database kết nối được, schema và table tồn tại, query aggregate trọng yếu đúng. Đối với Redshift Serverless, đặc biệt lưu ý namespace restore có thể ghi đè dữ liệu ở target namespace. Dùng namespace riêng dành cho test và xác nhận target trước khi bắt đầu.

## 16. Xác minh ở tầng ứng dụng và quy trình nghiệp vụ

Ứng dụng chỉ được coi là phục hồi khi các chức năng thiết yếu hoạt động trên dữ liệu đã khôi phục. Xác định một tập transaction đại diện có thể chạy lặp lại và không tạo side effect thật.

Ví dụ cho hệ thống bán hàng:

1. Health endpoint trả trạng thái ready.
2. Service đọc được cấu hình và secret dành cho test.
3. Checkout tìm thấy sản phẩm đã biết.
4. Đơn hàng lịch sử có thể được truy vấn.
5. Tổng tiền đơn hàng khớp baseline.
6. Inventory đọc được số lượng tại một thời điểm đã biết.
7. Một giao dịch giả lập có thể chạy trong sandbox và được rollback hoặc xóa.

Đối với hệ thống event-driven, kiểm tra event source, queue, offset, DLQ và khả năng xử lý idempotent. Đừng phát lại message thật tới consumer production khi đang test restore.

### 16.1. Health check không đủ

HTTP 200 ở endpoint health chỉ chứng minh một phần. Readiness check nên xác minh dependency thiết yếu như database, cache, object store và message broker theo cách không gây tải quá mức. Bổ sung một số truy vấn nghiệp vụ đại diện để kiểm tra dữ liệu.

### 16.2. Kiểm tra quyền và bảo mật sau restore

Khôi phục dữ liệu mà mở quyền truy cập rộng hơn production cũng là một thất bại. Kiểm tra IAM role, security group, bucket policy, KMS key, database grants, secret rotation và log. Đảm bảo dữ liệu nhạy cảm chỉ được truy cập bởi nhóm test được phép.

## 17. Kịch bản kiểm thử đầu-cuối

Một kịch bản nên ghi rõ mục tiêu, phạm vi, tiền điều kiện, dữ liệu chuẩn, bước thực hiện, tiêu chí pass/fail và người chịu trách nhiệm.

~~~text
Scenario: Restore đơn hàng và xác minh checkout
Scope: RDS/Aurora + EC2/ECS application
Recovery point: Một snapshot hoặc PITR được chọn trong cửa sổ 24 giờ
RTO target: 60 phút từ lúc bắt đầu restore đến lúc application-ready
RPO target: Không mất transaction marker quá 15 phút

1. Tạo marker và ghi baseline trước khi backup.
2. Chọn recovery point và khởi chạy restore test.
3. Restore database vào subnet test, dùng KMS key và security group test.
4. Chờ database available, ghi timestamp.
5. Kiểm tra schema, count, aggregate, foreign key và marker.
6. Khởi chạy application trong môi trường test.
7. Chạy health check và các query nghiệp vụ read-only.
8. Chạy một giao dịch sandbox nếu được phê duyệt.
9. Ghi thời gian, checksum, query result và log.
10. Gửi kết quả validation và xác nhận cleanup.

Pass: mọi invariant đạt, ứng dụng ready và RTO/RPO trong mục tiêu.
Fail: một invariant không đạt, dependency không sẵn sàng hoặc mục tiêu thời gian vượt ngưỡng.
~~~

Kịch bản phải chỉ ra liệu RTO tính từ lúc restore job bắt đầu hay từ lúc incident declared. Nếu không thống nhất mốc, kết quả giữa các lần test không thể so sánh.

## 18. Thực hành: tạo restore testing plan bằng AWS CLI

Ví dụ sau tạo một plan chạy hằng tuần và chọn ngẫu nhiên recovery point snapshot hoặc continuous trong 14 ngày gần nhất. Đây là cấu hình minh họa; điều chỉnh vault, resource type, role, lịch và thời gian theo môi trường.

Tạo file restore-testing-plan.json:

~~~json
{
  "RestoreTestingPlan": {
    "RestoreTestingPlanName": "weekly_critical_restore",
    "ScheduleExpression": "cron(0 2 ? * SUN *)",
    "ScheduleExpressionTimezone": "Asia/Ho_Chi_Minh",
    "StartWindowHours": 6,
    "RecoveryPointSelection": {
      "Algorithm": "RANDOM_WITHIN_WINDOW",
      "RecoveryPointTypes": ["SNAPSHOT", "CONTINUOUS"],
      "IncludeVaults": ["*"],
      "SelectionWindowDays": 14
    }
  }
}
~~~

Tạo plan:

~~~bash
aws backup create-restore-testing-plan --cli-input-json file://restore-testing-plan.json
~~~

Sau khi plan được tạo thành công, tạo selection riêng cho từng resource type. Ví dụ selection dùng wildcard ARN kết hợp tag condition để chọn resource RDS thuộc môi trường production:

~~~json
{
  "RestoreTestingPlanName": "weekly_critical_restore",
  "RestoreTestingSelection": {
    "RestoreTestingSelectionName": "rds_critical",
    "IamRoleArn": "arn:aws:iam::111122223333:role/AWSBackupRestoreTestingRole",
    "ProtectedResourceType": "RDS",
    "ProtectedResourceArns": ["*"],
    "ProtectedResourceConditions": {
      "StringEquals": [
        {
          "Key": "Environment",
          "Value": "production"
        }
      ]
    },
    "ValidationWindowHours": 12
  }
}
~~~

Tạo selection:

~~~bash
aws backup create-restore-testing-selection --cli-input-json file://restore-testing-selection.json
~~~

Trong API, selection có thể dùng danh sách ARN cụ thể hoặc wildcard kèm conditions. Không trộn danh sách ARN cụ thể với điều kiện theo cách không được API hỗ trợ. Hãy kiểm tra schema hiện hành trước khi đưa JSON vào pipeline.

Xem plan và selection:

~~~bash
aws backup list-restore-testing-plans
aws backup list-restore-testing-selections --restore-testing-plan-name weekly_critical_restore
aws backup get-restore-testing-plan --restore-testing-plan-name weekly_critical_restore
~~~

Xem restore job:

~~~bash
aws backup list-restore-jobs --by-restore-testing-plan-arn arn:aws:backup:ap-southeast-1:111122223333:restore-testing-plan:weekly_critical_restore
aws backup describe-restore-job --restore-job-id 12345678-1234-1234-1234-123456789012
~~~

Các lệnh chỉ minh họa cú pháp và luồng thao tác. Cần xác minh option trong AWS CLI version đang cài và quyền IAM trước khi áp dụng. Thay ARN và account minh họa bằng giá trị của môi trường test trước khi chạy.

## 19. Bằng chứng và kiểm toán

Một kết quả restore test cần có thể truy vết và lặp lại. Lưu bằng chứng ở nơi độc lập với resource test:

- Restore testing plan ARN, selection name và thời gian chạy.
- Recovery point ARN/ID, vault, loại recovery point và timestamp dữ liệu.
- Restore job ID, trạng thái, resource type và resource ARN được tạo.
- Thời điểm bắt đầu/kết thúc từng bước.
- Kết quả checksum, query, file count, health check và business invariant.
- Phiên bản script, container image hoặc Lambda version đã chạy validation.
- Người phê duyệt, người vận hành, kết luận và action items.
- Cleanup status và resource còn tồn tại sau test.

CloudTrail có thể ghi nhận các API như StartRestoreJob nếu account bật logging phù hợp. AWS Backup console và API hiển thị restore job, trạng thái và validation status. AWS Backup Audit Manager có control Restore time for resources meet target để đánh giá restore job hoàn tất trong thời gian mục tiêu cấu hình.

Control này đánh giá thời gian restore của resource type theo metric mà AWS Backup cung cấp; nó không thay cho validation checksum hoặc application test của tổ chức. Báo cáo tuân thủ cần phân biệt rõ kiểm tra thời gian với kiểm tra tính toàn vẹn dữ liệu.

### 19.1. Lưu bằng chứng chống sửa đổi

Nếu cần bằng chứng phục vụ kiểm toán hoặc điều tra, lưu kết quả vào bucket riêng, bật versioning và chính sách retention phù hợp. Có thể dùng S3 Object Lock khi yêu cầu lưu trữ bất biến. Giới hạn principal có quyền ghi, xóa hoặc thay đổi retention. Lưu checksum của report và manifest; cân nhắc ký kết quả bằng cơ chế được tổ chức phê duyệt.

Không ghi secret, private key, password hoặc toàn bộ dữ liệu cá nhân vào report. Dùng ARN, serial number, hash và metadata tối thiểu cần thiết để truy vết.

## 20. Phân tích lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| Không có recovery point đủ điều kiện | Selection window quá ngắn, vault bị loại trừ, retention không đủ | Kiểm tra IncludeVaults, ExcludeVaults, RecoveryPointTypes và thời điểm job thực tế |
| Restore job FAILED do permission | Role thiếu quyền resource hoặc KMS | Đọc status message, CloudTrail AccessDenied và key policy |
| Job không bắt đầu trong start window | Quota concurrent restore job hoặc thiếu capacity | Tăng start window phù hợp, giảm concurrency hoặc xử lý quota |
| EC2 restore xong nhưng không SSH được | Subnet, route, security group, key pair hoặc OS network | Kiểm tra instance status, ENI, route và console/system log |
| Volume attach được nhưng không mount | Device mapping, filesystem hoặc UUID khác | Kiểm tra lsblk, dmesg, mount options và filesystem |
| RDS available nhưng ứng dụng không kết nối | Security group, subnet group, DNS, secret hoặc database grant | Kiểm tra endpoint, port, TLS, credentials và database user |
| Database mở được nhưng dữ liệu thiếu | Recovery point cũ, PITR sai thời điểm hoặc transaction chưa commit | So sánh transaction marker, timestamp và aggregate |
| Checksum không khớp | Manifest sai phiên bản, object sai version hoặc dữ liệu hỏng | Xác minh recovery point, version ID, thuật toán và phạm vi hash |
| Validation Lambda không chạy | Event pattern sai, target permission hoặc retry/DLQ | Kiểm tra EventBridge metrics, rule match, Lambda permission và DLQ |
| Validation đã báo SUCCESSFUL quá sớm | Gửi kết quả trước khi tất cả test kết thúc | Thiết kế state machine và chỉ gửi kết quả cuối sau cùng |
| Cleanup thất bại | Tag test bị xóa, resource type dùng name-based cleanup hoặc service chưa xóa xong | Kiểm tra deletion status, tag, tên resource và job message |
| Chi phí test tăng bất thường | Resource lớn, retention dài, S3 cleanup chậm hoặc test quá dày | Đối chiếu usage, restore duration, retention và lịch test |

### 20.1. Phân loại lỗi

Ghi nhận lỗi theo một trong các nhóm:

- **Backup/recovery point:** không có điểm phù hợp hoặc điểm không truy cập được.
- **Restore execution:** quyền, quota, metadata hoặc dịch vụ đích khiến job thất bại.
- **Integrity:** checksum, cấu trúc hoặc dữ liệu logic không đạt.
- **Application:** dependency, cấu hình, secret hoặc health check không đạt.
- **Security:** quyền truy cập sau restore không phù hợp.
- **Cleanup:** tài nguyên test không được xóa theo kế hoạch.
- **Evidence:** thiếu log, timestamp hoặc kết quả để kết luận.

Phân loại giúp action item đi đến đúng owner và tránh đánh dấu toàn bộ bài test là một lỗi chung chung.

## 21. Tối ưu chi phí và mức độ bao phủ

Restore test có chi phí riêng và restore resource có thể phát sinh chi phí compute, storage, I/O, network, snapshot, database hoặc dịch vụ phụ trợ. Resource được giữ lâu hơn để validation cũng có thể làm tăng chi phí.

Các biện pháp kiểm soát:

1. Bắt đầu bằng số lượng nhỏ resource và resource type để đo chi phí thực tế.
2. Chọn recovery point theo risk; không phải test tất cả resource mỗi lần.
3. Phân tán lịch để tránh peak capacity và concurrent restore quota.
4. Dùng validation window vừa đủ cho phép kiểm tra.
5. Giới hạn kích thước dữ liệu test nếu có thể tạo dataset đại diện riêng.
6. Theo dõi deletion status và xử lý resource còn sót.
7. Dùng tag hoặc naming convention để phân biệt tài nguyên test.
8. Theo dõi chi phí theo plan, resource type và account.

Không rút ngắn validation window đến mức workflow không thể kiểm tra xong. Mục tiêu là có đủ bằng chứng với chi phí có thể kiểm soát.

## 22. Bài tập tự kiểm tra

### Câu 1

Backup job có trạng thái COMPLETED. Có thể kết luận dữ liệu đã khôi phục thành công không?

**Đáp án:** Không. COMPLETED chỉ cho biết backup job hoàn tất. Cần restore test để xác minh recovery point có thể dùng và dữ liệu/ứng dụng sau restore đạt tiêu chí.

### Câu 2

Restore job COMPLETED nhưng API trả lỗi khi đọc database. Bài test đạt hay chưa?

**Đáp án:** Chưa. Restore job chỉ xác nhận thao tác restore hoàn tất. Cần kiểm tra network, credentials, database schema, quyền và query ứng dụng.

### Câu 3

RTO là 60 phút. Restore job mất 20 phút và application validation mất 25 phút sau đó. Có thể báo RTO 20 phút không?

**Đáp án:** Không nếu RTO được định nghĩa đến khi service-ready. Cần đo từ mốc bắt đầu theo quy ước đến khi hoàn tất validation/application readiness; trong ví dụ chưa tính các giai đoạn trước và tổng thể ít nhất là 45 phút kể từ khi bắt đầu restore.

### Câu 4

SelectionWindowDays được tính từ thời gian dự kiến trên lịch hay thời điểm job thực sự chạy?

**Đáp án:** Từ thời điểm job thực sự chạy. Cần tính cả StartWindowHours khi chọn selection window để tránh recovery point bị loại.

### Câu 5

Một lần Scan DynamoDB với Limit 100 trả về 100 item. Có thể kết luận bảng chỉ có 100 item không?

**Đáp án:** Không. Scan có thể phân trang; phải xử lý LastEvaluatedKey hoặc dùng baseline/aggregate phù hợp.

### Câu 6

ETag của object S3 có luôn là MD5 của toàn bộ object không?

**Đáp án:** Không. Multipart upload và một số cách mã hóa/copy làm ETag không đại diện MD5 toàn object. Dùng checksum được hỗ trợ hoặc tính hash trên dữ liệu đã tải.

### Câu 7

Tại sao cần manifest checksum độc lập?

**Đáp án:** Nếu manifest bị hỏng hoặc bị sửa cùng dữ liệu, so sánh nội bộ không còn đáng tin. Manifest cần được lưu ở nơi có quyền và vòng đời độc lập, có thể ký hoặc bảo vệ bất biến.

### Câu 8

AWS Backup restore testing có tự xác minh nghiệp vụ ứng dụng không?

**Đáp án:** Không. Cần workflow riêng như EventBridge và Lambda để chạy health check, query và business invariant rồi gửi kết quả validation.

### Câu 9

Điều gì xảy ra nếu xóa tag awsbackup-restore-test trước khi cleanup?

**Đáp án:** Với resource type dựa vào tag-on-restore, AWS Backup có thể không nhận diện được tài nguyên để xóa tự động; cần điều tra và cleanup thủ công. Một số resource type dùng name-based cleanup.

### Câu 10

AWS Backup Audit Manager control Restore time for resources meet target chứng minh checksum của dữ liệu đã khôi phục đúng không?

**Đáp án:** Không. Control này đánh giá thời gian restore so với mục tiêu; checksum và dữ liệu logic cần validation riêng.

## 23. Checklist trước khi công bố một restore test thành công

- [ ] Đã xác định RTO, RPO và mốc thời gian bắt đầu/kết thúc.
- [ ] Recovery point, vault, Region và timestamp được ghi nhận.
- [ ] Restore role có quyền tối thiểu cần thiết và truy cập KMS thành công.
- [ ] Resource được restore vào môi trường cô lập.
- [ ] Network, subnet, security group và DNS test đúng.
- [ ] Resource đạt trạng thái sẵn sàng và có thể truy cập.
- [ ] File/object checksum hoặc manifest khớp theo phạm vi đã định nghĩa.
- [ ] Database schema, constraint, aggregate và transaction marker đạt.
- [ ] Ứng dụng vượt qua readiness và các luồng nghiệp vụ đại diện.
- [ ] IAM, KMS, secret và policy sau restore được xác minh.
- [ ] Validation status chỉ được gửi sau khi toàn bộ bước kiểm tra kết thúc.
- [ ] Evidence có restore job ID, recovery point, timestamps, script version và kết quả.
- [ ] Cleanup status được theo dõi và resource còn sót đã có owner.
- [ ] Sai lệch RTO/RPO, integrity hoặc application có action item và deadline.
- [ ] Kịch bản đã được cập nhật khi kiến trúc hoặc dependency thay đổi.

## 24. Tài liệu tham khảo chính thức

- [AWS Backup: Restore testing](https://docs.aws.amazon.com/aws-backup/latest/devguide/restore-testing.html)
- [AWS Backup: Restore testing validation](https://docs.aws.amazon.com/aws-backup/latest/devguide/restore-testing-validation.html)
- [AWS Backup: Restore a backup by resource type](https://docs.aws.amazon.com/aws-backup/latest/devguide/restoring-a-backup.html)
- [AWS Backup API: CreateRestoreTestingPlan](https://docs.aws.amazon.com/aws-backup/latest/APIReference/API_CreateRestoreTestingPlan.html)
- [AWS Backup API: RestoreTestingRecoveryPointSelection](https://docs.aws.amazon.com/aws-backup/latest/APIReference/API_RestoreTestingRecoveryPointSelection.html)
- [AWS Backup API: PutRestoreValidationResult](https://docs.aws.amazon.com/aws-backup/latest/APIReference/API_PutRestoreValidationResult.html)
- [AWS Backup: Quotas](https://docs.aws.amazon.com/aws-backup/latest/devguide/aws-backup-limits.html)
- [AWS Backup Audit Manager: Controls and remediation](https://docs.aws.amazon.com/aws-backup/latest/devguide/controls-and-remediation.html)
- [AWS Backup: Feature availability by resource](https://docs.aws.amazon.com/aws-backup/latest/devguide/backup-feature-availability.html)
- [Amazon S3: Checking object integrity](https://docs.aws.amazon.com/AmazonS3/latest/userguide/checking-object-integrity.html)
- [AWS Backup: Restore an Amazon EBS volume](https://docs.aws.amazon.com/aws-backup/latest/devguide/restoring-ebs.html)
- [Amazon RDS: Restoring a DB instance](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_RestoreFromSnapshot.html)

Tên API, quota và feature availability có thể thay đổi theo dịch vụ và Region. Trước khi triển khai, đối chiếu tài liệu hiện hành của resource type, Region và phiên bản AWS CLI/SDK đang sử dụng.
