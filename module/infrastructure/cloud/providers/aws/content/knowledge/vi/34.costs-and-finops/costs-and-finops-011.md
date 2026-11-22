# Tối ưu chi phí lưu trữ, NAT, data transfer và telemetry

Chi phí AWS không chỉ đến từ số lượng máy chủ đang chạy. Một workload có thể phát sinh khoản chi đáng kể từ dữ liệu lưu lâu hơn nhu cầu, volume EBS được cấp dư, NAT Gateway xử lý traffic nội bộ, dữ liệu đi qua nhiều Availability Zone, log được giữ vô thời hạn hoặc telemetry có quá nhiều metric series và trace.

Tối ưu chi phí không đồng nghĩa với chọn dịch vụ có đơn giá thấp nhất. Cần xem xét toàn bộ vòng đời dữ liệu, đường đi của network traffic, mức quan sát cần thiết, yêu cầu sẵn sàng và thời gian khôi phục. Một thay đổi chỉ tiết kiệm storage nhưng làm tăng retrieval, request hoặc data transfer có thể khiến tổng hóa đơn cao hơn.

Bài học thuộc chương **Chi phí và FinOps** của module CLOUD_PROVIDERS_AWS. Module khám phá hệ sinh thái AWS từ Region/AZ, IAM, VPC đến compute, storage, database, integration và serverless; người học rèn khả năng chọn dịch vụ, thiết kế và triển khai ứng dụng an toàn, có khả năng giám sát, phục hồi và kiểm soát chi phí.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân tích các thành phần chi phí chính của S3, EBS, EFS, NAT Gateway, data transfer và telemetry.
- Chọn storage class hoặc volume type dựa trên access pattern, độ trễ, độ bền và thời gian lưu giữ.
- Thiết kế S3 Lifecycle, EBS snapshot lifecycle và EFS lifecycle để giảm dữ liệu dư thừa.
- Ước lượng khi nào VPC endpoint có thể giảm chi phí NAT Gateway và khi nào interface endpoint có thể đắt hơn.
- Nhận diện phí data transfer liên AZ, liên Region, internet egress và phí xử lý của dịch vụ trung gian.
- Giảm chi phí CloudWatch Logs, metrics, traces và VPC Flow Logs mà vẫn giữ tín hiệu phục vụ vận hành, bảo mật và kiểm toán.
- Phân bổ chi phí bằng cost allocation tags, Cost Categories và dữ liệu CUR 2.0.
- Thiết lập ngân sách, phát hiện bất thường và ưu tiên hành động FinOps có thể đo lường.

## 1. Tư duy FinOps: tối ưu tổng chi phí, không tối ưu một dòng hóa đơn

FinOps là cách phối hợp giữa kỹ thuật, tài chính và đơn vị sử dụng để tạo ra giá trị kinh doanh từ chi phí cloud. Với chủ đề này, hãy nhìn mỗi quyết định qua ba câu hỏi:

1. **Chi phí nào đang phát sinh?** Storage GB-month, IOPS, throughput, NAT Gateway-hour, GB processed, data transfer, log ingestion, metric series, trace hoặc query scan?
2. **Chi phí có tạo ra giá trị cần thiết không?** Dữ liệu có cần truy cập nhanh không? Traffic có cần qua NAT không? Log có cần được tìm kiếm trực tuyến trong nhiều tháng không?
3. **Nếu giảm chi phí thì trade-off nào xuất hiện?** Retrieval chậm hơn, mất khả năng chịu lỗi AZ, thiếu dữ liệu điều tra, tăng độ phức tạp vận hành hoặc tăng rủi ro khôi phục?

### 1.1. Phân biệt đơn giá và mức tiêu thụ

Một dịch vụ thường có nhiều đơn vị tính phí. Ví dụ:

| Dịch vụ | Đơn vị tiêu thụ thường gặp | Thành phần dễ bị bỏ sót |
|---|---|---|
| Amazon S3 | GB-month, request, GB retrieval, replication | Version cũ, delete marker, incomplete multipart upload, transition request |
| Amazon EBS | GB-month, IOPS, throughput, snapshot GB-month | Volume chưa attach, snapshot cũ, Fast Snapshot Restore |
| Amazon EFS | Storage class GB-month, read/write throughput, tiering | File nhỏ có minimum billable size, phí đọc IA/Archive, backup |
| NAT Gateway | Gateway-hour, GB processed | Cross-AZ transfer và internet egress |
| Data transfer | GB đi qua ranh giới tính phí | Cross-AZ, cross-Region, NAT, Transit Gateway, PrivateLink |
| CloudWatch | Log ingestion, storage, query scan, metric, alarm | Dimension cardinality, vended logs, data protection, trace sampling |

Đừng kết luận một giải pháp rẻ chỉ từ đơn giá lưu trữ. Hãy cộng cả chi phí ghi/đọc, truy xuất, truyền dữ liệu, bản sao, backup, giám sát và vận hành.

### 1.2. Xây baseline trước khi thay đổi

Trước khi sửa kiến trúc, hãy thu thập baseline ít nhất một chu kỳ sử dụng đại diện:

- Dung lượng trung bình và đỉnh theo storage class hoặc volume type.
- Tốc độ tăng trưởng dữ liệu, số lượng object/file, tuổi dữ liệu và tần suất truy cập.
- Tỷ lệ cache hit, số request, GB tải lên/tải xuống và egress theo Region.
- NAT Gateway-hour, GB processed, traffic theo AZ và đích đến.
- Log GB ingested/ngày, dung lượng lưu, GB query scan, số metric series và trace được ghi nhận.
- Số tài nguyên idle, unattached, không có owner hoặc không có tag.

Chọn đơn vị đo gắn với sản phẩm, ví dụ chi phí trên 1.000 giao dịch, 1 GB dữ liệu khách hàng, 1 giờ xử lý batch hoặc 1 triệu request. Như vậy, nhóm có thể phân biệt hóa đơn tăng do workload phát triển với chi phí tăng do thiết kế kém hiệu quả.

## 2. Đo lường, phân bổ và kiểm soát chi phí

### 2.1. Cost Explorer, CUR 2.0 và Data Exports

**AWS Cost Explorer** phù hợp để xem xu hướng chi phí theo thời gian, dịch vụ, tài khoản, Region, usage type và tag đã kích hoạt. Có thể bật dữ liệu granular để điều tra theo giờ hoặc theo resource trong phạm vi được hỗ trợ. Dữ liệu hourly và resource-level có thể có thời gian chờ trước khi xuất hiện; không dùng nó như telemetry thời gian thực.

**Cost and Usage Report (CUR) 2.0** là nguồn dữ liệu chi tiết cho phân tích sâu. AWS khuyến nghị tạo CUR 2.0 thông qua **Data Exports**. Có thể xuất dữ liệu sang S3 và truy vấn bằng Athena hoặc công cụ BI. Tùy cấu hình, dữ liệu có thể chứa resource ID, usage type, pricing, discount, tag, cost category và các cột phân bổ chi phí.

Khi cần phân bổ chi phí container, cấu hình split cost allocation data trong CUR 2.0. Tùy chọn này bổ sung các dòng và cột phân bổ chi phí của tài nguyên dùng chung, chẳng hạn EC2 instance được chia cho các container; đổi lại kích thước export và số dòng có thể tăng đáng kể.

Một quy trình phân tích hữu ích:

1. Dùng Cost Explorer để phát hiện dịch vụ hoặc usage type tăng bất thường.
2. Mở CUR 2.0 để xác định SKU, Region, resource ID, usage type và đơn vị tính phí.
3. Đối chiếu với metric kỹ thuật: số GB, request, giờ hoạt động, IOPS hoặc số metric series.
4. Gắn owner và business context cho từng khoản chi.
5. Tạo hành động có người phụ trách, thời hạn và chỉ số xác minh sau thay đổi.

### 2.2. Cost allocation tags và Cost Categories

Dùng bộ tag nhất quán, chẳng hạn:

| Tag key | Ví dụ giá trị | Mục đích |
|---|---|---|
| `Application` | `checkout-api` | Nhóm theo ứng dụng |
| `Environment` | `production`, `staging`, `dev` | Phân biệt môi trường |
| `Owner` | `platform-team` | Xác định người chịu trách nhiệm |
| `CostCenter` | `CC-042` | Đối chiếu ngân sách |
| `DataClass` | `hot`, `warm`, `archive` | Hỗ trợ quản trị vòng đời dữ liệu |

User-defined tags phải được áp dụng lên tài nguyên và kích hoạt trong Billing and Cost Management trước khi xuất hiện trong báo cáo phân bổ. Tag mới có thể cần thời gian để hiển thị. Không đưa thông tin bí mật, dữ liệu cá nhân hoặc thông tin nhạy cảm vào tag.

**Cost Categories** cho phép ánh xạ chi phí theo quy tắc, ví dụ business unit, sản phẩm, môi trường hoặc shared platform. Chúng hữu ích khi một chi phí dùng chung không thể phân bổ chỉ bằng tag của một tài nguyên.

### 2.3. Budgets, Cost Anomaly Detection và Cost Optimization Hub

- **AWS Budgets:** đặt ngân sách theo cost, usage, RI hoặc Savings Plans coverage/utilization; có thể cảnh báo theo actual hoặc forecasted spend. Dữ liệu ngân sách cập nhật theo chu kỳ billing, không phải tức thời.
- **AWS Cost Anomaly Detection:** dùng mô hình phát hiện thay đổi chi tiêu bất thường theo service, account, tag hoặc Cost Category. Dữ liệu Cost Explorer có độ trễ; quá trình phát hiện thường chạy nhiều lần trong ngày, vì vậy cảnh báo có thể đến sau khi usage phát sinh.
- **Cost Optimization Hub:** tổng hợp khuyến nghị trên nhiều tài khoản và Region, bao gồm rightsizing, tài nguyên idle, EBS volume và NAT Gateway. Hãy đánh giá savings estimate, rủi ro và effort trước khi triển khai.

Không coi budget alert là cơ chế tự động ngăn mọi khoản chi vượt ngưỡng. Cần kết hợp budget, anomaly monitor, quota, IAM guardrail và quy trình xử lý sự cố.

## 3. Chọn storage phù hợp với vòng đời dữ liệu

Một quyết định storage tốt bắt đầu từ access pattern chứ không phải từ tên storage class:

- **Hot:** truy cập thường xuyên, cần độ trễ thấp.
- **Warm:** truy cập định kỳ, chấp nhận một mức phí retrieval hoặc độ trễ cao hơn.
- **Cold:** hiếm khi truy cập, có thể chấp nhận thời gian restore.
- **Archive:** lưu dài hạn theo yêu cầu tuân thủ hoặc điều tra, ít khi đọc.

Cần phân biệt object storage, block storage và file storage:

| Loại | Dịch vụ tiêu biểu | Phù hợp với |
|---|---|---|
| Object | Amazon S3 | Object, file tĩnh, backup, data lake, log, archive |
| Block | Amazon EBS | Filesystem và block device gắn với EC2, database, boot volume |
| Shared file | Amazon EFS | NFS dùng chung cho nhiều compute workload |
| Managed file system chuyên biệt | Amazon FSx | SMB/Windows, Lustre, NetApp ONTAP, OpenZFS |

Không thay thế EBS bằng S3 chỉ để giảm giá GB nếu workload cần block I/O hoặc filesystem semantics. Tương tự, EFS tiện cho chia sẻ file nhưng có thể không phải lựa chọn kinh tế nhất cho dữ liệu object lớn, bất biến và ít truy cập.

## 4. Tối ưu Amazon S3

### 4.1. Các thành phần chi phí S3

Hóa đơn S3 có thể bao gồm:

- Dung lượng lưu theo storage class và thời gian lưu.
- Request như PUT, COPY, POST, LIST, GET và lifecycle transition.
- Data retrieval và restore từ các class có tính phí truy xuất.
- Data transfer, Transfer Acceleration và request từ ứng dụng.
- S3 Replication, S3 Storage Lens advanced tier và các tính năng quản lý/insights.
- S3 Select hoặc các tính năng transform/query nếu sử dụng.

Một bucket có nhiều object nhỏ có thể tốn đáng kể ở request và lifecycle transition dù tổng dung lượng không lớn. Một bucket versioning-enabled có thể tiếp tục giữ dữ liệu cũ sau khi ứng dụng ghi đè hoặc xóa object.

### 4.2. Chọn storage class

| Storage class | Access pattern | Đặc điểm chi phí và vận hành |
|---|---|---|
| S3 Standard | Dữ liệu thường xuyên truy cập | Truy xuất tức thì, không có minimum storage duration |
| S3 Intelligent-Tiering | Access pattern không rõ hoặc thay đổi | Tự chuyển tier; tính phí monitoring/automation theo object; không có minimum storage duration |
| S3 Standard-IA | Lưu lâu, ít đọc nhưng cần truy cập tức thì | Có retrieval charge, minimum duration 30 ngày và minimum billable object size 128 KB |
| S3 One Zone-IA | Dữ liệu tái tạo được, ít đọc, chấp nhận rủi ro một AZ | Tương tự IA nhưng chỉ lưu trong một AZ; có retrieval charge và minimum duration 30 ngày |
| S3 Glacier Instant Retrieval | Archive nhưng vẫn cần truy cập tức thì | Retrieval charge, minimum duration 90 ngày và minimum billable object size 128 KB |
| S3 Glacier Flexible Retrieval | Archive, có thể chờ restore | Phù hợp dữ liệu hiếm đọc; minimum duration 90 ngày |
| S3 Glacier Deep Archive | Lưu dài hạn, rất hiếm restore | Chi phí lưu thấp hơn nhưng thời gian restore dài; minimum duration 180 ngày |

Lưu ý:

- S3 Intelligent-Tiering có phí monitoring và automation theo object. Object nhỏ hơn 128 KB vẫn có thể được lưu trong class này nhưng không được tự động tiering và được tính theo Frequent Access tier. Object chuyển vào Archive Access hoặc Deep Archive Access cũng có metadata overhead; hãy kiểm tra số lượng object nhỏ trước khi bật các tier archive.
- S3 Standard-IA và S3 One Zone-IA có minimum billable size 128 KB. Object nhỏ hơn vẫn có thể bị tính dung lượng tối thiểu 128 KB.
- S3 Glacier Flexible Retrieval và Deep Archive tính thêm 40 KB metadata cho mỗi object archive: 32 KB được tính theo storage class Glacier tương ứng và 8 KB được tính theo S3 Standard. Với object nhỏ, overhead này có thể làm giảm đáng kể savings; cân nhắc gom nhiều object nhỏ thành file lớn hơn.
- Nếu object bị xóa, ghi đè hoặc chuyển class trước minimum storage duration, có thể phát sinh phí phần thời gian còn lại.
- Các tier archive của Intelligent-Tiering có hành vi truy cập đồng bộ hoặc bất đồng bộ khác nhau. Không chọn archive tier nếu ứng dụng cần đọc ngay mà chưa đánh giá thời gian restore.
- S3 One Zone-IA không phù hợp với bản sao duy nhất của dữ liệu quan trọng nếu tổ chức không chấp nhận mất AZ.

Chọn Intelligent-Tiering khi access pattern khó dự đoán và phí monitoring hợp lý so với savings tiềm năng. Chọn Lifecycle tĩnh khi vòng đời dữ liệu ổn định và có thể mô tả bằng quy tắc rõ ràng.

### 4.3. Lifecycle và minimum duration

Lifecycle cho phép tự động:

- Chuyển object từ Standard sang IA hoặc Glacier khi đủ tuổi.
- Chuyển noncurrent versions sang class rẻ hơn.
- Xóa current version hoặc noncurrent version theo retention.
- Xóa expired delete marker.
- Abort incomplete multipart uploads.

S3 Lifecycle transition có tính phí request. Mặc định hiện hành, object nhỏ hơn 128 KB không được chuyển sang storage class khác; nếu cần xử lý object nhỏ, phải cấu hình size filter rõ ràng và tính lại lợi ích. Một số cấu hình lifecycle cũ có thể giữ hành vi mặc định trước đây cho đến khi được chỉnh sửa.

Trước khi đặt rule, hãy so sánh:

\[
\text{Net saving} =
\text{Storage saving}
-\text{Transition request cost}
-\text{Retrieval cost}
-\text{Early deletion cost}
\]

Ví dụ, một bucket có hàng triệu object JSON nhỏ, mỗi object chỉ vài KB. Chuyển toàn bộ sang IA có thể không có lợi vì phí transition và minimum billable size làm mất phần savings. Có thể gom dữ liệu thành file lớn hơn theo ngày hoặc partition trước khi chuyển sang class khác, nếu ứng dụng có thể chấp nhận cách truy xuất mới.

### 4.4. Quản lý version, delete marker và multipart upload

Trong bucket bật Versioning:

- PUT cùng key tạo version mới; version cũ trở thành noncurrent.
- DELETE không chỉ định version ID thường tạo delete marker, không xóa vĩnh viễn dữ liệu cũ.
- Expiration cho current version có thể tạo delete marker; noncurrent version vẫn còn cho đến khi có rule riêng.
- Object Lock, legal hold hoặc retention period có thể ngăn xóa vĩnh viễn.

Một Lifecycle configuration thường cần nhiều rule độc lập:

1. Expire current version sau thời gian lưu đã duyệt.
2. Permanently delete noncurrent versions sau retention và số version mới hơn được giữ.
3. Remove expired delete markers.
4. Abort incomplete multipart uploads sau một số ngày, thường dùng mốc 7 ngày làm baseline rồi điều chỉnh theo quy trình upload.

Ví dụ cấu hình lifecycle rút gọn:

~~~json
{
  "Rules": [
    {
      "ID": "abort-incomplete-multipart",
      "Status": "Enabled",
      "Filter": {
        "Prefix": ""
      },
      "AbortIncompleteMultipartUpload": {
        "DaysAfterInitiation": 7
      }
    },
    {
      "ID": "expire-old-noncurrent-versions",
      "Status": "Enabled",
      "Filter": {
        "Prefix": "application-logs/"
      },
      "NoncurrentVersionExpiration": {
        "NoncurrentDays": 90,
        "NewerNoncurrentVersions": 3
      }
    },
    {
      "ID": "remove-expired-delete-markers",
      "Status": "Enabled",
      "Filter": {
        "Prefix": "application-logs/"
      },
      "Expiration": {
        "ExpiredObjectDeleteMarker": true
      }
    }
  ]
}
~~~

Đây là ví dụ minh họa. Hãy kiểm tra schema lifecycle, versioning state, Object Lock, retention requirement và phạm vi prefix trước khi áp dụng. Rule abort multipart upload không dùng tag-based filter. Lifecycle chạy bất đồng bộ nên không đảm bảo xóa đúng tại thời điểm đồng hồ vừa chạm ngưỡng.

### 4.5. S3 Storage Lens và Inventory

Dùng S3 Storage Lens để tìm:

- Bucket hoặc prefix tăng dung lượng nhanh.
- Nhiều noncurrent versions hoặc delete markers.
- Incomplete multipart uploads tồn tại lâu.
- Bucket chưa có lifecycle rule phù hợp.
- Request activity hoặc bytes downloaded cho thấy dữ liệu có thể được chuyển class.

Free metrics phù hợp để quan sát tổng quan. Advanced tier có thêm activity metrics, prefix aggregation, recommendation và khả năng xuất metrics sang CloudWatch; hãy tính phí trước khi bật.

S3 Inventory hữu ích khi cần danh sách object, version, storage class, encryption, size và last-modified time để phân tích offline. Có thể xuất CSV hoặc Parquet và dùng Athena để xác định object cũ, object nhỏ hoặc prefix không còn được truy cập.

## 5. Tối ưu Amazon EBS

### 5.1. Right-size volume type và performance

EBS tính phí dung lượng được provision; một số loại volume còn tính riêng IOPS và throughput.

**gp3** thường là điểm bắt đầu tốt cho general-purpose SSD:

- Có baseline 3.000 IOPS và 125 MiB/s ở mọi dung lượng volume.
- Có thể provision IOPS và throughput độc lập với dung lượng.
- Performance vượt baseline được tính phí bổ sung.
- AWS công bố gp3 có thể giảm đến 20% chi phí mỗi GB so với gp2, nhưng tổng chi phí còn phụ thuộc IOPS và throughput được provision.

Không chuyển tất cả volume sang gp3 một cách máy móc. Với workload yêu cầu IOPS rất cao và latency thấp, io2 có thể phù hợp hơn. Với workload tuần tự như throughput-intensive data warehouse hoặc log processing, st1 có thể phù hợp; sc1 dành cho cold HDD workload. Hãy benchmark bằng workload thật và so sánh tổng giá volume + performance + instance EBS bandwidth.

Một quy trình right-size:

1. Lấy inventory volume theo account, Region, AZ, instance và owner.
2. Kiểm tra `VolumeReadOps`, `VolumeWriteOps`, `VolumeReadBytes`, `VolumeWriteBytes`, queue length và latency.
3. So sánh peak IOPS/throughput thực tế với baseline và mức đã provision.
4. Chọn volume type mới và cấu hình IOPS/throughput vừa đủ.
5. Thử nghiệm trong staging; theo dõi performance sau khi modify.
6. Kiểm tra snapshot/backup trước khi thực hiện thay đổi rủi ro.

### 5.2. Tìm volume không còn sử dụng

Volume có trạng thái `available` không được attach vào instance. Volume này vẫn phát sinh storage charge. Tuy nhiên, không được xóa chỉ dựa vào trạng thái:

- Có thể là volume dự phòng cho recovery.
- Có thể là volume được detach trong maintenance.
- Có thể chứa dữ liệu cần lưu giữ hoặc phục vụ một hệ thống đang tạm dừng.

Bắt đầu bằng inventory chỉ đọc:

~~~bash
aws ec2 describe-volumes \
  --filters Name=status,Values=available \
  --query "Volumes[].{VolumeId:VolumeId,SizeGiB:Size,Type:VolumeType,AZ:AvailabilityZone,Created:CreateTime,Encrypted:Encrypted,Tags:Tags}"
~~~

Đối chiếu tag `Owner`, `Application`, `Environment`, thời điểm detach, snapshot gần nhất và hồ sơ thay đổi. Chỉ xóa sau khi owner xác nhận và chính sách backup/retention cho phép. Volume root và volume có `DeleteOnTermination=false` cần được kiểm tra kỹ khi instance bị terminate.

### 5.3. Quản lý snapshot và Fast Snapshot Restore

Snapshot EBS là incremental:

- Snapshot đầu tiên của volume là full snapshot của các block đã ghi.
- Snapshot sau lưu các block thay đổi kể từ snapshot trước.
- Storage cost dựa trên dữ liệu snapshot được lưu, không phải dung lượng provisioned của volume.

Xóa một snapshot không nhất thiết làm giảm chi phí tương ứng với toàn bộ size hiển thị, vì block có thể còn được snapshot khác tham chiếu. Chỉ dữ liệu không còn được snapshot nào tham chiếu mới được giải phóng. Vì vậy, không xóa snapshot theo kiểu “xóa snapshot cũ nhất để tiết kiệm đúng dung lượng của nó”.

Amazon Data Lifecycle Manager hoặc AWS Backup giúp tự động hóa lịch tạo, retention và xóa snapshot/AMI. Hãy định nghĩa policy theo tag và retention phù hợp; kiểm tra AMI còn sử dụng snapshot trước khi xóa.

**EBS Snapshots Archive** phù hợp với snapshot cần giữ lâu (ít nhất 90 ngày) và hiếm khi restore:

- Archive snapshot luôn là full copy, có thể lớn hơn incremental snapshot trong Standard tier.
- Minimum archive period là 90 ngày.
- Restore có phí theo GB và có thể mất nhiều giờ; tài liệu AWS nêu thời gian restore có thể lên đến 72 giờ tùy kích thước.
- Không nên archive snapshot cuối cùng trong một incremental snapshot set nếu vẫn cần tạo volume nhanh từ snapshot đó.
- Không phải snapshot nào cũng rẻ hơn sau khi archive; tính full-copy size, retrieval, restore time và phí minimum duration.

Fast Snapshot Restore (FSR) có thể giảm thời gian khởi tạo volume từ snapshot nhưng bị tính phí theo snapshot, mỗi AZ và thời gian bật. Chỉ bật ở AZ và thời gian cần thiết, sau đó tắt nếu không còn yêu cầu khôi phục tức thì.

## 6. Tối ưu Amazon EFS và file storage

### 6.1. Storage class và file system type

EFS có hai file system type:

- **Regional:** lưu dữ liệu dư thừa qua nhiều AZ trong Region, phù hợp workload cần availability và durability cao.
- **One Zone:** lưu trong một AZ, có thể giảm storage cost nhưng không chịu được sự cố mất toàn bộ AZ. EFS One Zone được AWS Backup tự động backup mặc định; cần tính thêm chi phí backup và restore.

EFS có các storage class:

| Class | Access pattern | Lưu ý |
|---|---|---|
| EFS Standard | File đang hoạt động, cần latency thấp | Phù hợp dữ liệu thường xuyên đọc/ghi |
| EFS Infrequent Access (IA) | File ít truy cập, vài lần mỗi quý | Storage rẻ hơn, có phí đọc và minimum billing charge 128 KiB/file; không có minimum storage duration |
| EFS Archive | File rất ít truy cập, vài lần mỗi năm hoặc ít hơn | Có phí đọc, minimum billing charge 128 KiB/file và minimum duration 90 ngày |

IA và Archive có minimum billing charge 128 KiB cho mỗi file; 2 KiB metadata của file vẫn được metered trong Standard, còn data access được metered theo từng khối 128 KiB. Ngoài phí đọc, thao tác tiering giữa Standard, IA và Archive cũng có thể phát sinh data-access/tiering charge.

Lifecycle Management chuyển file giữa Standard, IA và Archive dựa trên thời gian từ lần truy cập cuối. Với cấu hình khuyến nghị mặc định trong console, EFS có thể đặt transition sang IA sau 30 ngày và Archive sau 90 ngày; hãy xác nhận lại policy trên file system trước khi dựa vào mốc này. EFS không chuyển file vào Archive trước IA: mốc `TransitionToArchive` phải sau `TransitionToIA`.

EFS Archive chỉ được hỗ trợ trên Regional file system dùng Elastic Throughput và General Purpose performance mode. Nếu lifecycle policy chuyển dữ liệu vào Archive, không thể đổi throughput mode sang Bursting hoặc Provisioned. AWS Backup không phát sinh data-access charge khi backup file system đã bật lifecycle management; vẫn phải tính backup storage và restore. Đừng chỉ nhìn giá lưu trữ; hãy tính cả data access, throughput, backup và replication.

### 6.2. Chọn throughput mode

- **Elastic Throughput:** hiệu năng tự co giãn theo hoạt động; chi phí phụ thuộc dữ liệu read/write được metered. Đây là mode mặc định được khuyến nghị cho phần lớn use case.
- **Provisioned Throughput:** provision mức throughput độc lập với dung lượng và burst credit; có thể gây lãng phí nếu workload không dùng hết.
- **Bursting Throughput:** khả năng throughput liên quan đến dung lượng lưu trữ và burst credit; workload có traffic thất thường cần theo dõi credit và metered throughput.

Theo dõi CloudWatch metric `MeteredIOBytes` và các chỉ số throughput. Với Provisioned Throughput, EFS meter read requests ở mức một phần ba so với các request khác; đối chiếu throughput thực tế với mức provision định kỳ để giảm phần capacity không dùng. Bursting throughput chỉ tính dữ liệu trong EFS Standard khi xác định mức throughput được phép.

### 6.3. Khi nào nên cân nhắc FSx?

Nếu ứng dụng cần SMB/Windows file share, ONTAP, OpenZFS hoặc Lustre, Amazon FSx có thể phù hợp hơn EFS. Tuy nhiên, hãy so sánh capacity, throughput capacity, SSD/HDD tier, backup, replication, data access và thời gian hoạt động. Không nên thay file system chỉ dựa trên giá GB; workload có thể cần thay đổi giao thức hoặc application semantics.

## 7. Tối ưu NAT Gateway

### 7.1. Mô hình chi phí

NAT Gateway thường có ba nhóm chi phí:

1. **NAT Gateway-hour:** thời gian gateway được provision và available; mỗi phần giờ được tính như một giờ đầy đủ.
2. **Data processing:** mỗi GB đi qua NAT Gateway, bất kể nguồn hoặc đích.
3. **Data transfer khác:** ví dụ cross-AZ giữa workload và NAT Gateway hoặc internet egress.

Công thức ước lượng:

\[
C_{NAT} =
(H_{NAT}\times R_{hour})
+(GB_{processed}\times R_{processing})
+C_{crossAZ}
+C_{internetEgress}
\]

Trong đó, `H_NAT` phải tính theo số NAT Gateway hoặc số AZ được Regional NAT Gateway hỗ trợ. Một gateway không có traffic vẫn có thể phát sinh hourly charge.

### 7.2. Zonal NAT Gateway và Regional NAT Gateway

**Zonal NAT Gateway** hoạt động trong một AZ. Nếu workload ở nhiều AZ cùng route qua một NAT Gateway, traffic có thể phát sinh cross-AZ transfer; đồng thời nếu AZ chứa NAT Gateway gặp sự cố, workload ở AZ khác có thể mất đường internet egress. Thiết kế HA truyền thống thường tạo NAT Gateway riêng cho mỗi AZ và route workload tới NAT cùng AZ.

**Regional NAT Gateway** là lựa chọn mới cho multi-AZ. Một resource NAT Gateway có thể tự mở rộng hoặc thu hẹp phạm vi AZ theo workload presence; có thể dùng một NAT ID chung trong route table. Phí hourly vẫn tính theo từng AZ được cấu hình/hỗ trợ, cộng data processing và data transfer. Regional NAT Gateway không hỗ trợ private NAT; use case cần private connectivity vẫn phải đánh giá zonal NAT Gateway.

Lưu ý, khi Regional NAT Gateway mới phát hiện workload ở AZ mới, quá trình mở rộng có thể mất tới 60 phút. Trong lúc mở rộng, traffic từ AZ mới có thể được xử lý xuyên AZ qua một AZ hiện hữu và phát sinh transfer charge. Đọc tài liệu hiện hành và kiểm thử route behavior trước khi chuyển production. Việc chuyển đổi từ zonal sang regional có thể reset các connection đang tồn tại; nên thực hiện trong maintenance window.

### 7.3. Giảm traffic không cần qua NAT

Các bước tối ưu thường có tác động lớn:

- Tạo **S3 Gateway VPC Endpoint** và **DynamoDB Gateway VPC Endpoint** cho traffic tương ứng. Hai loại gateway endpoint này không có hourly charge hoặc data processing charge bổ sung.
- Dùng interface endpoint cho AWS service hỗ trợ PrivateLink khi lợi ích từ việc tránh NAT, kiểm soát private connectivity hoặc giảm cross-network traffic lớn hơn chi phí endpoint.
- Đặt workload và NAT Gateway trong cùng AZ nếu dùng zonal gateway; hoặc cân nhắc NAT per-AZ/Regional NAT để cân bằng chi phí và HA.
- Phân loại traffic theo đích. Traffic tới S3 cùng Region có thể không có data transfer charge nhưng vẫn bị tính NAT data processing nếu đi vòng qua NAT.
- Loại bỏ route NAT cho traffic AWS service có thể dùng gateway endpoint.
- Kiểm tra container image pull, package download, update agent, telemetry exporter và backup job; các luồng nền này có thể tạo nhiều GB processed mà ít được chú ý.
- Tắt NAT Gateway không còn cần sau khi xác nhận route table và workload không còn phụ thuộc.

### 7.4. Gateway endpoint hay interface endpoint?

| Tiêu chí | Gateway endpoint | Interface endpoint (PrivateLink) |
|---|---|---|
| Dịch vụ điển hình | S3, DynamoDB | Nhiều AWS service và endpoint service của đối tác |
| Hạ tầng | Route table target | ENI private trong subnet |
| Phí endpoint | Không có hourly hoặc processing fee bổ sung | Có hourly charge theo AZ và data processing |
| Kết nối on-prem/peered VPC | Gateway endpoint S3/DynamoDB có giới hạn | Có thể hỗ trợ tùy kiến trúc và service |
| Quản trị | Route table, endpoint policy, bucket/table policy | Endpoint ENI, DNS, security group, endpoint policy |

Không phải cứ tạo interface endpoint là rẻ hơn NAT. Hãy tính:

\[
C_{endpoint} =
(AZ_{endpoint}\times H\times R_{hour})
+(GB_{endpoint}\times R_{processing})
+C_{transfer}
\]

So sánh với phần NAT processing và cross-AZ có thể tránh được. Nếu NAT Gateway vẫn cần cho internet egress, endpoint chỉ tiết kiệm phần traffic được chuyển khỏi NAT; hourly NAT không tự biến mất.

### 7.5. Ví dụ quyết định

Một workload private subnet tải artifact từ S3 cùng Region với lượng dữ liệu lớn mỗi ngày. Nếu route S3 qua NAT, doanh nghiệp trả phí NAT processing dù S3 và EC2 cùng Region. Tạo S3 Gateway Endpoint, gắn route table thích hợp và kiểm soát bằng endpoint policy/bucket policy có thể loại bỏ phần NAT processing của luồng này.

Nếu cùng workload còn tải dependency từ public package registry, traffic đó vẫn có thể cần NAT hoặc một proxy/cache riêng. Vì vậy, không nên xóa NAT chỉ vì đã tạo S3 endpoint.

## 8. Tối ưu data transfer

### 8.1. Phân biệt các ranh giới tính phí

| Loại transfer | Ví dụ | Hướng tối ưu |
|---|---|---|
| Internet ingress | Người dùng upload vào AWS | Thường không bị tính phí ingress; vẫn có thể có phí service/request |
| Internet egress | EC2/S3 gửi dữ liệu ra internet | Cache, nén, CloudFront, giảm payload và request không cần thiết |
| Cross-AZ | EC2 AZ-a gọi database hoặc NAT ở AZ-b | Ưu tiên local-AZ routing khi phù hợp, tránh hairpin |
| Cross-Region | Replication, backup, app gọi service ở Region khác | Giảm dữ liệu copy, chọn Region gần workload, chỉ replicate theo yêu cầu |
| Qua NAT Gateway | Private subnet đi tới public endpoint | Gateway endpoint, interface endpoint hoặc proxy/cache |
| Qua Transit Gateway/PrivateLink | Kết nối VPC hoặc service | Tính thêm phí processing và data transfer theo service |

AWS thường không tính phí dữ liệu đi vào từ internet, nhưng outbound, cross-AZ, cross-Region và phí xử lý của dịch vụ trung gian có thể phát sinh. Mỗi dịch vụ có quy tắc riêng; cần đọc trang pricing của dịch vụ nguồn và đích.

Public IPv4 address cũng là một khoản network cost riêng: địa chỉ đang gắn với tài nguyên và địa chỉ public IPv4 idle trong tài khoản đều có thể bị tính phí theo giờ. Kiểm kê Elastic IP/public IPv4 không còn sử dụng và kiểm tra các dịch vụ tự tạo public address trước khi tối ưu NAT.

Một số luồng EC2-to-EC2 trong cùng AZ dùng private IP có thể không có phí data transfer; cross-AZ thường tính theo GB ở cả hai phía theo bảng giá áp dụng. Không suy rộng quy tắc này cho mọi dịch vụ hoặc mọi loại endpoint.

### 8.2. Thiết kế để giảm cross-AZ transfer

- Đặt compute và thành phần data plane gần nhau về AZ khi kiến trúc cho phép.
- Dùng load balancer và database topology có nhận thức AZ; cân nhắc cross-zone load balancing cùng phí liên quan.
- Với zonal NAT Gateway, route subnet tới NAT cùng AZ để tránh cross-AZ path.
- Tránh ứng dụng chatty gọi service hoặc database ở AZ khác cho từng request nhỏ; batch hoặc aggregate request nếu phù hợp.
- Dùng cache gần compute và giảm số lần tải cùng một object.
- Theo dõi topology sau khi autoscaling; instance mới có thể được đặt ở AZ khác và làm thay đổi luồng traffic.

Không ép mọi workload vào một AZ chỉ để tiết kiệm transfer nếu điều đó làm mất khả năng chịu lỗi hoặc tăng RTO/RPO. Tối ưu phải giữ nguyên SLO và resilience target.

### 8.3. Internet egress và CloudFront

Amazon CloudFront có thể giảm số lần origin phải phục vụ cùng một nội dung. Với AWS origin như S3, Elastic Load Balancing hoặc API Gateway, data transfer từ origin tới CloudFront được miễn phí theo hướng dẫn CloudFront; traffic từ edge tới viewer vẫn có giá theo khu vực, request và tính năng.

Các đòn bẩy:

- Cache nội dung tĩnh và response có thể cache an toàn.
- Thiết lập TTL, cache key và query string hợp lý để tăng cache hit ratio.
- Nén response và tránh gửi payload không cần thiết.
- Dùng Origin Shield khi pattern truy cập phù hợp để giảm request trùng về origin.
- Phân biệt dynamic content với static content; không cache dữ liệu cá nhân hoặc response nhạy cảm nếu policy không cho phép.

CloudFront không phải lúc nào cũng rẻ hơn trực tiếp. Cần cộng phí data transfer out tới viewer, request, invalidation, real-time log và các feature đang bật; một số luồng dữ liệu từ edge về origin cũng có thể phát sinh phí theo loại request và bảng giá hiện hành.

### 8.4. Cross-Region replication và backup

S3 Cross-Region Replication, EBS snapshot copy, AWS Backup copy và database replication có thể tạo data transfer và storage ở Region đích. Hãy xác định rõ:

- Dữ liệu nào cần DR, dữ liệu nào chỉ cần backup tại Region hiện tại.
- RPO/RTO yêu cầu cho từng nhóm dữ liệu.
- Tần suất và lượng dữ liệu thay đổi.
- Thời gian lưu giữ bản sao và cơ chế xóa theo retention.
- Chi phí KMS, request, storage và data transfer ở Region đích.

Không tắt replication hoặc backup chỉ để giảm hóa đơn nếu chưa đánh giá rủi ro mất dữ liệu và nghĩa vụ compliance.

## 9. Tối ưu telemetry: log, metric, trace và network flow

Telemetry cần đủ chi tiết để phát hiện sự cố, điều tra bảo mật và đáp ứng kiểm toán. Nhưng thu thập mọi thứ, giữ vô thời hạn và truy vấn toàn bộ dữ liệu sẽ tạo chi phí lớn.

### 9.1. Các thành phần tính phí

| Tín hiệu | Chi phí thường gặp | Đòn bẩy tối ưu |
|---|---|---|
| Logs | Ingestion, storage, query scan, data protection, vended log delivery | Giảm log noise, retention, log class, filter, archive |
| Metrics | Unique metric series, API requests, high-resolution metrics, alarms | Giảm cardinality, aggregate, chọn resolution |
| Traces | Trace recorded/retrieved, span ingestion/indexing | Sampling, tail sampling, chỉ giữ trace cần điều tra |
| VPC Flow Logs | Vended log ingestion và destination storage/query | Filter traffic, chọn S3 hay CloudWatch, giảm field không cần |
| Metric Streams | Metric updates, Firehose, destination và transfer | Chỉ stream metric cần dùng, giảm tần suất và số statistics |

### 9.2. CloudWatch Logs: ingestion, storage và query

CloudWatch Logs mặc định giữ dữ liệu vô thời hạn nếu không đặt retention. Do đó, log group mới có thể tiếp tục phát sinh storage charge dù ứng dụng không còn sử dụng.

Đặt retention theo mục đích:

- Application debug: ngắn, đủ thời gian xử lý sự cố.
- Security/audit: theo policy, compliance và khả năng điều tra.
- Access log lớn: archive S3 sau giai đoạn truy vấn nóng.
- Log tạm thời trong dev/test: retention ngắn và cleanup theo môi trường.

Retention là cấu hình theo log group; dữ liệu hết hạn có thể mất thêm thời gian để được xóa vật lý. Hãy xác nhận policy đã áp dụng đúng nhóm log, không chỉ dựa vào một setting mặc định.

### 9.3. Chọn CloudWatch Logs Standard, Essentials và Delivery

CloudWatch Logs có ba log class cần phân biệt:

| Class | Phù hợp với | Lưu ý |
|---|---|---|
| **Standard** | Log cần real-time monitoring, metric filter, subscription và tính năng đầy đủ | Ingestion price cao hơn Essentials |
| **Essentials** (tên cũ: Infrequent Access) | Log tập trung, truy vấn ad-hoc hoặc forensic không cần pipeline realtime | Lower ingestion charge, nhưng feature subset |
| **Delivery** | Chuyển Lambda logs tới S3 hoặc Firehose | Log chỉ giữ trong CloudWatch Logs hai ngày, không có đầy đủ query/monitoring |

Standard và Essentials khác nhau ở ingestion pricing; storage charge và CloudWatch Logs Insights query charge giống nhau. Essentials không hỗ trợ một số tính năng như subscription filters, metric filters, Live Tail, field indexing và EMF. Hãy chọn log class khi tạo log group vì class không thể đổi sau khi group được tạo.

Tên Infrequent Access đã được đổi thành Essentials. Bắt đầu tháng 12/2026, các API read-path trả `ESSENTIALS` thay cho `INFREQUENT_ACCESS` trong trường `logGroupClass`; đây là thay đổi tên, không phải thay đổi giá hoặc hành vi.

Essentials cũng không hỗ trợ API `GetLogEvents` và `FilterLogEvents`; để xem log trong class này, dùng CloudWatch Logs Insights.

### 9.4. Query hiệu quả hơn

CloudWatch Logs Insights tính phí theo dữ liệu được scan. Để giảm query cost:

- Giới hạn time range trước khi chạy query.
- Chọn đúng log group thay vì query toàn bộ log group.
- Dùng field index cho các field hay lọc, ví dụ `requestId`, `instanceId` hoặc `traceId`, nếu log group thuộc Standard class và workload truy vấn phù hợp.
- Ưu tiên structured JSON để filter theo field, thay vì regex trên log text không có cấu trúc.
- Dùng `filterIndex` khi có field index phù hợp để giảm lượng dữ liệu cần scan.
- Tránh dashboard tự động chạy query rộng mỗi lần refresh.
- Lưu query thường dùng và giới hạn lịch chạy.

Ví dụ query có time range nhỏ và filter theo request ID:

~~~text
fields @timestamp, level, requestId, message
| filter requestId = "req-7f31"
| sort @timestamp desc
| limit 100
~~~

Field index chỉ áp dụng cho log event được ingest sau khi index policy được tạo và chỉ hoạt động với log class hỗ trợ. Không index mọi field; ưu tiên field có tần suất truy vấn cao và có thể giảm đáng kể phạm vi dữ liệu scan.

### 9.5. Archive log sang S3

Với log cần lưu dài hạn nhưng ít truy vấn:

1. Dùng subscription hoặc pipeline phù hợp để chuyển log liên tục sang S3.
2. Partition theo account, Region, service và ngày.
3. Nén và cân nhắc Parquet cho workload Athena scan lớn.
4. Dùng S3 Lifecycle để chuyển sang storage class rẻ hơn hoặc xóa khi hết retention.
5. Giữ CloudWatch Logs Standard cho log cần alert hoặc query realtime.

CloudWatch Logs Export task phù hợp với export theo khoảng thời gian, không phải phương pháp archive liên tục. AWS khuyến nghị dùng subscription cho luồng archive thường xuyên. Khi archive sang S3, vẫn phải tính S3 storage, PUT request, Firehose nếu dùng và Athena query nếu phân tích.

### 9.6. Giảm log volume mà không mất tín hiệu

- Không ghi body request/response đầy đủ nếu chỉ cần status code, latency, request ID.
- Không log token, secret, password hoặc thông tin cá nhân.
- Dùng log level theo môi trường: DEBUG chỉ bật có thời hạn và có kiểm soát.
- Sampling log thành công với tần suất thấp hơn; giữ lại error, timeout và security event.
- Aggregate log lặp, dùng structured log và tránh lặp stack trace trong vòng retry.
- Tách audit log bắt buộc khỏi debug log để không vô tình giảm retention của dữ liệu tuân thủ.
- Dùng metric cho counter/gauge cần cảnh báo liên tục thay vì tạo log event cho mỗi lần đếm.

Không loại bỏ log có giá trị điều tra hoặc compliance chỉ vì nó tốn chi phí. Hãy xác định yêu cầu lưu giữ và bằng chứng cần có trước khi giảm volume.

## 10. Tối ưu metrics và OpenTelemetry

### 10.1. Cardinality là nguồn chi phí quan trọng

Với CloudWatch custom metrics, mỗi tổ hợp metric name và dimension values được xem như một metric riêng. Nếu một metric có dimensions `Service`, `Environment`, `TenantId`, `RequestId`, số series có thể tăng rất nhanh.

Ví dụ, metric `RequestLatency` có:

- 5 service,
- 3 environment,
- 1.000 tenant,
- 100.000 request ID.

Nếu dimension kết hợp không được giới hạn, số series có thể bùng nổ. Không đưa `requestId`, `sessionId`, email, user ID hoặc dữ liệu không giới hạn vào metric dimension. Các giá trị này phù hợp hơn với log hoặc trace attributes, nơi có cơ chế truy vấn và sampling khác.

Dùng dimension có cardinality thấp như service, environment, operation hoặc region. Nếu cần phân tích từng request, ghi request ID trong structured log và trace.

### 10.2. Chọn độ phân giải và cách aggregate

- Dùng standard resolution khi metric được đánh giá theo phút.
- Chỉ dùng high-resolution metric khi thực sự cần phản ứng ở khoảng thời gian ngắn.
- Aggregate ở application hoặc OpenTelemetry Collector trước khi gửi metric.
- Không gửi lại cùng một metric point nhiều lần do retry của exporter.
- Chỉ tạo alarm cho metric có action rõ ràng; tránh tạo alarm cho mọi metric chỉ để hiển thị dashboard.

### 10.3. OpenTelemetry metrics

CloudWatch OpenTelemetry metrics được tính theo GB payload OTLP chưa nén nhận được; payload bao gồm metric value, name, timestamp, attributes và resource metadata. Vì vậy, thêm nhiều attributes hoặc tag có thể làm tăng số byte ingestion dù số data point không đổi.

Để giảm chi phí:

- Giảm attributes không cần thiết.
- Tránh đưa user ID, request ID hoặc giá trị ngẫu nhiên vào resource attributes.
- Aggregate metric theo service/operation trước khi export.
- Dùng processor để drop metric không còn sử dụng.
- Kiểm soát interval và batch size phù hợp.
- Theo dõi byte volume tại Collector và CloudWatch.

Cross-account observability cho phép xem/query metrics và logs từ monitoring account mà không cần copy dữ liệu; đây là lựa chọn tốt khi chỉ cần quan sát tập trung. Metric centralization tạo bản copy vật lý và có thể phát sinh phí cho các bản sao bổ sung.

## 11. Tối ưu distributed traces

Trace giúp tìm nguyên nhân latency và lỗi xuyên qua nhiều service, nhưng ghi lại mọi request trong hệ thống có traffic lớn có thể làm tăng chi phí.

Các chiến lược:

- **Head sampling:** quyết định lấy trace ở đầu request. Dễ triển khai, giảm tải sớm nhưng có thể bỏ lỡ lỗi hiếm.
- **Tail sampling:** quyết định sau khi có thêm thông tin span; có thể ưu tiên giữ trace lỗi, latency cao hoặc request đặc biệt. Cần collector có state và capacity phù hợp.
- Giữ tỷ lệ sample cao hơn cho canary, staging hoặc service quan trọng trong giai đoạn điều tra.
- Giữ trace có error/timeout và sample thấp hơn cho request thành công bình thường.
- Giới hạn span attributes; không gắn payload lớn hoặc dữ liệu nhạy cảm.
- Tránh tạo span quá chi tiết cho vòng lặp nội bộ hoặc thao tác rất nhỏ nếu không giúp ích cho điều tra.
- Đặt retention và index policy theo mục tiêu truy vấn.

Không dùng sampling để che giấu error rate. Metrics phải phản ánh tổng traffic và lỗi; trace sampling chỉ giảm số request được ghi chi tiết.

## 12. Tối ưu VPC Flow Logs và network telemetry

VPC Flow Logs ghi metadata về IP traffic tới/đi khỏi network interface. Dữ liệu được thu thập ngoài đường đi traffic nên không làm thay đổi throughput hoặc latency của workload; tuy nhiên, ingestion và archive của flow logs có tính phí.

Chọn destination theo nhu cầu:

| Destination | Phù hợp với | Thành phần chi phí |
|---|---|---|
| CloudWatch Logs | Alert, truy vấn gần thời gian thực, tích hợp metric/query | Vended log ingestion, storage, query |
| Amazon S3 | Archive dài hạn, Athena/Parquet, forensic theo batch | Vended log delivery, S3 storage/request, query |
| Amazon Data Firehose | Stream log tới S3 hoặc hệ thống phân tích | Vended log delivery và Firehose processing/destination |

Các cách giảm chi phí:

- Dùng traffic type `REJECT` nếu mục tiêu chỉ là điều tra traffic bị chặn; dùng `ALL` khi cần baseline đầy đủ.
- Chọn aggregation interval và field format theo mục đích; không thu thập mọi field nếu không dùng.
- Tránh tạo nhiều flow log trùng phạm vi trên cùng VPC/subnet/ENI.
- Dùng S3 partition và lifecycle cho dữ liệu cần lưu lâu.
- Không đưa toàn bộ VPC Flow Logs vào CloudWatch Standard nếu chỉ cần phân tích forensic theo batch.
- Gắn cost allocation tag lên destination resource để truy nguyên chi phí flow logs.

Khi phân tích NAT Gateway, kết hợp flow logs với metric của NAT và route table để tìm traffic có byte volume cao, đích đến lặp lại hoặc workload đang đi sai đường.

## 13. Kết hợp tối ưu storage, network và telemetry

Các nhóm chi phí liên hệ với nhau. Ví dụ, archive log từ CloudWatch sang S3 giảm log storage nhưng tạo thêm S3 PUT, storage và Athena query. Chuyển dữ liệu sang Glacier giảm storage rate nhưng làm tăng retrieval time và restore cost. Tạo interface endpoint giảm NAT processing nhưng tạo hourly endpoint charge.

Hãy dùng ma trận quyết định:

| Tình huống | Hướng thử nghiệm | Điều phải kiểm tra |
|---|---|---|
| S3 chứa nhiều object cũ, ít đọc | Lifecycle sang IA/Glacier hoặc Intelligent-Tiering | Object size, minimum duration, transition/retrieval cost |
| EBS gp2 volume có IOPS thấp | Benchmark và thử gp3 | Baseline IOPS/throughput, performance, extra provisioning |
| EBS volume ở trạng thái `available` | Xác minh owner rồi xóa nếu không còn cần | Backup, AMI, recovery, retention |
| EFS có phần lớn file ít truy cập | Lifecycle sang IA/Archive | Read frequency, access charge, latency, throughput mode |
| NAT xử lý nhiều traffic S3/DynamoDB | Gateway endpoint | Route table, endpoint policy, bucket/table policy |
| NAT xử lý nhiều traffic AWS service khác | So sánh interface endpoint | Hourly per AZ, GB processing, NAT còn cần cho internet không |
| EC2 gọi service ở AZ khác liên tục | Xem lại placement, cache và route | HA, cross-AZ fee, failover behavior |
| Internet egress lớn cho static content | CloudFront caching/compression | Edge transfer, request fee, cache hit ratio |
| CloudWatch Logs tăng nhanh | Giảm noise, retention, Essentials, S3 archive | Real-time alert cần Standard không? |
| CloudWatch metrics tăng nhanh | Giảm dimension cardinality, aggregate | Alert/SLO có còn đủ độ chính xác? |
| Trace volume quá lớn | Head/tail sampling | Error trace và slow trace có được giữ lại? |

## 14. Ví dụ tính toán chi phí

Các ví dụ sau dùng biến giá để tránh nhầm lẫn giữa Region, thời điểm và loại tài khoản. Lấy đơn giá thực tế từ trang pricing hoặc AWS Pricing Calculator trước khi đưa vào ngân sách.

### 14.1. Ước lượng NAT Gateway

Giả sử một kiến trúc có hai AZ, mỗi AZ có NAT Gateway riêng:

- NAT Gateway-hour = số AZ × số giờ trong tháng.
- NAT processed GB = tổng GB từ private subnet đi qua NAT.
- Cross-AZ GB = traffic đi từ workload tới NAT ở AZ khác.
- Internet egress GB = dữ liệu gửi ra internet.

\[
C = 2\times730\times R_{hour}
+GB_{NAT}\times R_{GB}
+GB_{crossAZ}\times R_{crossAZ}
+GB_{egress}\times R_{egress}
\]

Nếu 60% NAT processed bytes là traffic tới S3 cùng Region, hãy thử S3 Gateway Endpoint và đo lại GB processed. Savings tiềm năng gồm NAT processing cho phần traffic đã bypass; không tự động giảm hourly charge nếu hai NAT Gateway vẫn cần cho internet traffic.

### 14.2. Ước lượng S3 Lifecycle

Giả sử có 2 TB dữ liệu ít truy cập:

\[
C_{before}=2.000\times R_{Standard}
\]

\[
C_{after}=2.000\times R_{IA}
+GB_{retrieved}\times R_{retrieval}
+N_{transition}\times R_{transition}
\]

Nếu object bị xóa trước minimum duration, cộng thêm early deletion charge. Nếu object chỉ vài KB, cần tính minimum billable size và transition request; chuyển class có thể không đem lại savings.

### 14.3. Ước lượng CloudWatch Logs

Giả sử ứng dụng ingest 20 GB log/ngày trong 30 ngày:

\[
GB_{ingest}=20\times30=600\ GB
\]

Tổng chi phí cần xét:

\[
C_{logs} =
600\times R_{ingestion}
+GB_{stored}\times R_{storage}
+GB_{scanned}\times R_{query}
+C_{dataProtection}
\]

Nếu một dashboard chạy query scan 200 GB mỗi lần, 20 lần/tháng, query volume là 4.000 GB. Giới hạn time range, log group, filter và field index có thể giảm phần query scan mà không cần xóa log.

### 14.4. Metric cardinality

Một ứng dụng phát 8 metric names cho 40 service instances, với 4 environment values và 100 tenant values:

- Nếu metric dimension gồm `instance` và `environment`: số series xấp xỉ 8 × 40 × 4 = 1.280.
- Nếu thêm `tenantId` có 100 giá trị: số series có thể lên tới 128.000.

Chỉ đưa tenant dimension vào metric nếu có nhu cầu vận hành rõ ràng và đã ước lượng cost. Phần lớn trường hợp, aggregate theo service/environment và giữ tenant ID trong log/trace là hợp lý hơn.

## 15. Công cụ và lệnh kiểm tra an toàn

### 15.1. Liệt kê NAT Gateway

~~~bash
aws ec2 describe-nat-gateways \
  --query "NatGateways[].{NatGatewayId:NatGatewayId,State:State,VpcId:VpcId,SubnetId:SubnetId,ConnectivityType:ConnectivityType,AvailabilityMode:AvailabilityMode}"
~~~

Đối chiếu từng gateway với route table của private subnet. Không xóa NAT Gateway chỉ vì metric traffic thấp trong một khoảng ngắn; có thể đó là đường dự phòng hoặc traffic theo lịch.

### 15.2. Kiểm tra route table

~~~bash
aws ec2 describe-route-tables \
  --query "RouteTables[].{RouteTableId:RouteTableId,VpcId:VpcId,Routes:Routes,Associations:Associations}"
~~~

Kiểm tra default route `0.0.0.0/0`, route prefix list tới S3/DynamoDB gateway endpoint và subnet association. Nếu thay route, phải đánh giá cả IPv4, IPv6, failover và security policy.

### 15.3. Inventory EBS

~~~bash
aws ec2 describe-volumes \
  --filters Name=status,Values=available \
  --query "Volumes[].{VolumeId:VolumeId,SizeGiB:Size,Type:VolumeType,AZ:AvailabilityZone,CreateTime:CreateTime,Encrypted:Encrypted,Tags:Tags}"

aws ec2 describe-snapshots \
  --owner-ids self \
  --query "Snapshots[].{SnapshotId:SnapshotId,VolumeId:VolumeId,StartTime:StartTime,VolumeSizeGiB:VolumeSize,Description:Description,Tags:Tags}"
~~~

Hai lệnh trên chỉ đọc inventory. Trước khi xóa volume hoặc snapshot, phải kiểm tra owner, AMI, AWS Backup, Recycle Bin, retention, snapshot lineage và quy trình restore.

### 15.4. Kiểm tra log group và retention

~~~bash
aws logs describe-log-groups \
  --query "logGroups[].{Name:logGroupName,Class:logGroupClass,RetentionDays:retentionInDays,StoredBytes:storedBytes}"
~~~

Nhóm không có `retentionInDays` có thể đang giữ log vô thời hạn. Không tự động áp dụng retention ngắn cho security/audit log nếu chưa xác nhận policy.

### 15.5. Xem chi phí theo service

~~~bash
aws ce get-cost-and-usage \
  --time-period Start=2026-10-01,End=2026-11-01 \
  --granularity MONTHLY \
  --metrics UnblendedCost \
  --group-by Type=DIMENSION,Key=SERVICE
~~~

Khoảng ngày trong ví dụ là tháng đã kết thúc. AWS Cost Explorer có độ trễ cập nhật và yêu cầu quyền Billing/Cost Management phù hợp. Dùng CUR 2.0/Athena khi cần resource ID, usage type hoặc line item chi tiết hơn.

## 16. Những lỗi tối ưu thường gặp

**Chuyển toàn bộ S3 sang class rẻ nhất.** Điều này có thể tăng retrieval cost, minimum duration charge và restore time. Hãy phân loại theo access pattern.

**Xóa current version nhưng quên noncurrent versions.** Versioning có thể giữ lại dữ liệu cũ và delete marker. Hãy cấu hình Lifecycle riêng cho current, noncurrent và expired delete marker.

**Chuyển object nhỏ sang IA/Glacier mà không tính minimum size.** Request transition và minimum billable size có thể lớn hơn storage savings.

**Xóa snapshot cũ và kỳ vọng tiết kiệm đúng dung lượng hiển thị.** Snapshot incremental có thể chia sẻ block với snapshot khác; chỉ block không còn được tham chiếu mới được giải phóng.

**Archive snapshot mà không tính 90-day minimum.** Nếu cần restore sớm, phí restore và minimum duration có thể làm phương án kém kinh tế.

**Dùng một NAT Gateway cho nhiều AZ chỉ để giảm hourly fee.** Thiết kế này có thể tạo cross-AZ transfer và giảm khả năng chịu lỗi. So sánh tổng chi phí với NAT per-AZ hoặc Regional NAT.

**Tạo interface endpoint cho mọi AWS service.** Interface endpoint có hourly và processing charges. Ưu tiên gateway endpoint miễn phí cho S3/DynamoDB; chỉ tạo interface endpoint khi cần và khi tổng chi phí hợp lý.

**Giảm telemetry bằng cách tắt log toàn hệ thống.** Điều này có thể làm mất khả năng phát hiện, điều tra và bằng chứng audit. Hãy giảm noise, đặt retention và sampling có mục tiêu.

**Đưa request ID hoặc user ID vào metric dimension.** Cardinality tăng rất nhanh và làm custom metric cost phình to. Giữ ID trong log/trace.

**Cho rằng Budgets hoặc Cost Anomaly Detection báo ngay.** Billing data có độ trễ. Cần metric kỹ thuật, quota và cảnh báo vận hành riêng cho các ngưỡng cần phản ứng nhanh.

**Không đo lại sau khi tối ưu.** Savings chỉ có ý nghĩa khi đo được trước/sau, kiểm tra hiệu năng, availability và chi phí phụ phát sinh.

## 17. Quy trình FinOps hàng tuần và hàng tháng

### Hàng tuần

1. Xem Cost Explorer theo service, Region và usage type.
2. Kiểm tra NAT Gateway-hour, processed bytes, egress và cross-AZ.
3. Tìm EBS volume `available`, snapshot cũ và FSR không còn cần.
4. Kiểm tra S3 buckets tăng trưởng nhanh, noncurrent versions và incomplete multipart uploads.
5. Xem CloudWatch log ingestion, metric series, trace volume và query scan.
6. Đối chiếu anomalies và phân công owner.

### Hàng tháng

1. So sánh actual spend với budget và forecast.
2. Đối chiếu CUR 2.0 với KPI kinh doanh.
3. Xác minh cost allocation tags và Cost Categories có bao phủ tài nguyên mới.
4. Đánh giá retention, backup, replication và archive policy.
5. Đánh giá Savings Plan/RI hoặc rightsizing nếu workload ổn định.
6. Ghi lại savings đã thực hiện và chi phí phát sinh do trade-off.

### Chỉ số nên theo dõi

| KPI | Cách đo | Ý nghĩa |
|---|---|---|
| Storage cost per TB-month | Storage spend / TB-month | So sánh hiệu quả lưu trữ |
| S3 lifecycle coverage | Bucket có lifecycle phù hợp / bucket thuộc phạm vi | Mức độ tự động hóa vòng đời |
| EBS unattached spend | Cost của volume `available` | Dữ liệu/volume có thể dư thừa |
| NAT cost per GB | NAT spend / GB processed | Hiệu quả network egress |
| Cross-AZ transfer per request | Cross-AZ GB / request | Mức độ chatty và placement |
| Log cost per million requests | Logs spend / triệu request | Hiệu quả logging |
| Metric series growth | Số series theo tháng | Theo dõi cardinality |
| Trace sampling ratio | Trace recorded / request count | Kiểm soát độ chi tiết telemetry |

## 18. Tình huống thực hành tổng hợp

Một ứng dụng thương mại điện tử chạy trên EC2/ECS ở ba AZ trong một Region. Hệ thống dùng S3 lưu ảnh và log archive, EBS cho database node, EFS chia sẻ file upload, NAT Gateway cho private subnet, CloudWatch Logs/metrics và distributed tracing.

Hóa đơn tăng trong ba tháng liên tiếp. Nhóm FinOps nhận thấy:

- S3 Standard tăng nhanh do ảnh cũ và nhiều noncurrent versions.
- EBS có một số volume ở trạng thái `available`.
- NAT Gateway processed bytes tăng dù traffic người dùng không tăng nhiều.
- CloudWatch Logs ingestion tăng do debug log và VPC Flow Logs.
- Custom metrics tăng mạnh sau khi thêm tenant ID vào dimension.

Hãy thiết kế kế hoạch điều tra theo thứ tự ưu tiên:

1. Dùng Cost Explorer tìm usage type và Region tăng; sau đó dùng CUR 2.0 xác định resource ID/line item.
2. Dùng S3 Storage Lens và Inventory xác định prefix, object age, noncurrent versions và incomplete multipart uploads.
3. Thử Lifecycle trên một prefix mẫu, tính transition/retrieval cost và kiểm tra Object Lock/retention.
4. Liệt kê EBS volume `available`; xác nhận owner, backup và AMI trước khi xóa.
5. Dùng VPC Flow Logs và NAT metrics để xác định top destination. Kiểm tra S3/DynamoDB traffic có đi qua NAT không.
6. Thêm S3/DynamoDB gateway endpoints và đo lại NAT processed GB.
7. Kiểm tra EFS lifecycle, throughput mode và `MeteredIOBytes`.
8. Phân loại log theo mục đích; Standard cho alert/realtime, Essentials cho forensic ad-hoc, S3 cho archive dài hạn.
9. Đặt retention cho log group; dùng subscription để archive liên tục và giảm debug log.
10. Loại tenant ID khỏi metric dimension; aggregate theo service/environment, giữ tenant ID trong log/trace.
11. Điều chỉnh trace sampling để giữ error/slow trace và giảm trace thành công bình thường.
12. Tạo budget/anomaly alert và dashboard theo application, environment, owner.

Đánh giá kết quả bằng ba nhóm chỉ số: savings thực tế, hiệu năng/SLO và khả năng điều tra/khôi phục. Không đóng một hành động chỉ vì chi phí giảm nếu latency, availability hoặc RTO/RPO vượt ngưỡng.

## 19. Câu hỏi tự kiểm tra

1. Vì sao tối ưu storage GB-month không đồng nghĩa tối ưu tổng chi phí?
2. S3 Standard-IA và One Zone-IA khác nhau về resilience như thế nào?
3. Khi nào S3 Intelligent-Tiering có lợi hơn Lifecycle tĩnh?
4. Minimum storage duration ảnh hưởng chi phí transition và deletion ra sao?
5. Vì sao Lifecycle cần quản lý cả noncurrent versions và expired delete markers?
6. Incomplete multipart uploads gây chi phí như thế nào?
7. Vì sao gp3 có thể giảm chi phí so với gp2 nhưng vẫn cần benchmark?
8. Snapshot EBS incremental hoạt động thế nào và tại sao xóa snapshot cũ chưa chắc giảm cost?
9. Khi nào EBS Snapshot Archive có thể không có lợi?
10. EFS IA và Archive phù hợp access pattern nào?
11. NAT Gateway tính phí theo những thành phần nào?
12. Vì sao NAT Gateway tập trung ở một AZ có thể làm tăng cross-AZ transfer và giảm resilience?
13. Gateway endpoint khác interface endpoint về chi phí và cách định tuyến ra sao?
14. Data transfer ingress, internet egress, cross-AZ và cross-Region khác nhau như thế nào?
15. CloudFront có thể giảm loại chi phí origin nào và vẫn còn loại chi phí nào?
16. CloudWatch Logs Essentials khác Standard ở điểm gì?
17. Vì sao log group không đặt retention có thể tạo chi phí dài hạn?
18. Logs Insights query cost phụ thuộc vào yếu tố nào?
19. Vì sao metric dimension chứa request ID hoặc tenant ID có thể làm tăng cardinality?
20. Sampling trace cần giữ lại loại request nào để không làm giảm khả năng điều tra?
21. Vì sao VPC Flow Logs cũng có chi phí vended log?
22. CUR 2.0 bổ sung góc nhìn nào so với dashboard tổng quan của Cost Explorer?
23. Cost allocation tag cần bước nào trước khi xuất hiện trong báo cáo?
24. Vì sao AWS Budgets không phải hệ thống cảnh báo chi phí thời gian thực?
25. Cần đo những chỉ số nào để chứng minh một thay đổi FinOps thành công?

## 20. Checklist trước khi áp dụng tối ưu production

- [ ] Đã có baseline chi phí, usage và SLO trước thay đổi.
- [ ] Dữ liệu được phân loại theo hot/warm/cold/archive và yêu cầu restore.
- [ ] S3 class đã được chọn theo access pattern, minimum duration, object size và retrieval fee.
- [ ] S3 Lifecycle quản lý current, noncurrent, delete marker và incomplete multipart upload.
- [ ] Object Lock, legal hold, backup và compliance retention được tôn trọng.
- [ ] EBS volume type, IOPS và throughput dựa trên metric thực tế.
- [ ] Volume `available` đã có owner xác nhận trước khi xóa.
- [ ] EBS snapshot lineage, AMI, AWS Backup, Recycle Bin và FSR đã được kiểm tra.
- [ ] EFS lifecycle, throughput mode, file minimum billing và backup cost đã được tính.
- [ ] NAT Gateway cost đã cộng hourly, processing, cross-AZ và internet egress.
- [ ] S3/DynamoDB gateway endpoint đã được đánh giá trước khi thêm interface endpoint.
- [ ] Route table, AZ affinity, HA và failover đã được kiểm thử.
- [ ] CloudFront cache key, TTL, compression và security policy phù hợp.
- [ ] CloudWatch log class được chọn theo nhu cầu alert/query, không chỉ theo ingestion price.
- [ ] Log retention, archive, query scan và data protection cost đã được xác định.
- [ ] Metric cardinality và high-resolution metric được kiểm soát.
- [ ] Trace sampling giữ đủ error/slow trace cho điều tra.
- [ ] VPC Flow Logs có phạm vi, destination, retention và owner rõ ràng.
- [ ] Cost allocation tags đã được áp dụng và kích hoạt.
- [ ] CUR 2.0, Cost Explorer, Budgets và Cost Anomaly Detection được cấu hình.
- [ ] Đã có kế hoạch rollback và người chịu trách nhiệm.
- [ ] Savings, hiệu năng và resilience được đo lại sau triển khai.

## Kết luận

Tối ưu chi phí lưu trữ, NAT, data transfer và telemetry là bài toán tối ưu toàn bộ luồng dữ liệu. S3 Lifecycle, EBS gp3/snapshot lifecycle và EFS tiering giảm dung lượng không cần thiết; gateway endpoint, NAT topology, placement theo AZ và CloudFront giảm phí network; retention, log class, cardinality và sampling giúp telemetry có giá trị hơn với chi phí hợp lý.

FinOps hiệu quả cần dữ liệu chi phí có thể phân bổ, metric kỹ thuật để giải thích usage và quy trình review định kỳ. Mọi thay đổi phải giữ được yêu cầu bảo mật, availability, performance, backup và khả năng điều tra.

## Tài liệu AWS tham khảo

- [Amazon S3 pricing](https://aws.amazon.com/s3/pricing/)
- [Understanding and managing Amazon S3 storage classes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage-class-intro.html)
- [Managing the lifecycle of objects](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lifecycle-mgmt.html)
- [S3 Lifecycle transition considerations](https://docs.aws.amazon.com/AmazonS3/latest/userguide/lifecycle-transition-general-considerations.html)
- [S3 Lifecycle configuration examples](https://docs.aws.amazon.com/AmazonS3/latest/userguide/lifecycle-configuration-examples.html)
- [Understanding S3 Glacier storage classes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/glacier-storage-classes.html)
- [Troubleshooting S3 Lifecycle issues](https://docs.aws.amazon.com/AmazonS3/latest/userguide/troubleshoot-lifecycle.html)
- [Amazon S3 Storage Lens](https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage_lens.html)
- [Amazon EBS pricing](https://aws.amazon.com/ebs/pricing/)
- [Amazon EBS volume types](https://docs.aws.amazon.com/ebs/latest/userguide/ebs-volume-types.html)
- [How Amazon EBS snapshots work](https://docs.aws.amazon.com/ebs/latest/userguide/how_snapshots_work.html)
- [Delete an Amazon EBS snapshot](https://docs.aws.amazon.com/ebs/latest/userguide/ebs-deleting-snapshot.html)
- [Archive Amazon EBS snapshots](https://docs.aws.amazon.com/ebs/latest/userguide/snapshot-archive.html)
- [Automate backups with Amazon Data Lifecycle Manager](https://docs.aws.amazon.com/ebs/latest/userguide/snapshot-lifecycle.html)
- [Amazon EFS pricing](https://aws.amazon.com/efs/pricing/)
- [EFS storage classes and file system types](https://docs.aws.amazon.com/efs/latest/ug/features.html)
- [Configuring EFS lifecycle policies](https://docs.aws.amazon.com/efs/latest/ug/enable-lifecycle-management.html)
- [Managing EFS throughput](https://docs.aws.amazon.com/efs/latest/ug/managing-throughput.html)
- [How Amazon EFS reports file system and object sizes](https://docs.aws.amazon.com/efs/latest/ug/metered-sizes.html)
- [Amazon VPC pricing](https://aws.amazon.com/vpc/pricing/)
- [Pricing for NAT gateways](https://docs.aws.amazon.com/vpc/latest/userguide/nat-gateway-pricing.html)
- [Regional NAT gateways](https://docs.aws.amazon.com/vpc/latest/userguide/nat-gateways-regional.html)
- [NAT gateway basics](https://docs.aws.amazon.com/vpc/latest/userguide/nat-gateway-basics.html)
- [Gateway endpoints for Amazon S3](https://docs.aws.amazon.com/vpc/latest/privatelink/vpc-endpoints-s3.html)
- [Gateway endpoints for Amazon DynamoDB](https://docs.aws.amazon.com/vpc/latest/privatelink/vpc-endpoints-ddb.html)
- [Access AWS services through AWS PrivateLink](https://docs.aws.amazon.com/vpc/latest/privatelink/privatelink-access-aws-services.html)
- [AWS data transfer FAQs](https://aws.amazon.com/about-aws/global-infrastructure/global-network/faqs/)
- [Amazon CloudFront pricing](https://aws.amazon.com/cloudfront/pricing/)
- [What is Amazon CloudWatch Logs?](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/)
- [CloudWatch Logs log classes](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/CloudWatch_Logs_Log_Classes.html)
- [Change CloudWatch Logs retention](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/Working-with-log-groups-and-streams.html)
- [Create field indexes for CloudWatch Logs](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/CloudWatchLogs-Field-Indexing.html)
- [Export log data to Amazon S3](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/S3Export.html)
- [Amazon CloudWatch pricing](https://aws.amazon.com/cloudwatch/pricing/)
- [VPC Flow Logs](https://docs.aws.amazon.com/vpc/latest/userguide/flow-logs.html)
- [Cost and Usage Report 2.0 table dictionary](https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-cur2.html)
- [Creating Cost and Usage Reports](https://docs.aws.amazon.com/cur/latest/userguide/creating-cur.html)
- [Cost Explorer hourly cost and usage data](https://docs.aws.amazon.com/cost-management/latest/userguide/ce-services-hourly.html)
- [Activating user-defined cost allocation tags](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/activating-tags.html)
- [Managing costs with AWS Budgets](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html)
- [AWS Cost Anomaly Detection](https://docs.aws.amazon.com/cost-management/latest/userguide/getting-started-ad.html)
- [Cost Optimization Hub](https://docs.aws.amazon.com/cost-management/latest/userguide/cost-optimization-hub.html)
- [AWS Pricing Calculator](https://calculator.aws/)

