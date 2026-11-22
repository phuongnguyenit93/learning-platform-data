# AWS DataSync và di chuyển dữ liệu file, object

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích vai trò của AWS DataSync trong việc chuyển dữ liệu file và object giữa on-premises, AWS và các nhà cung cấp cloud khác.
- Phân biệt DataSync agent, location, task và task execution.
- Chọn Basic mode hoặc Enhanced mode dựa trên loại storage, số lượng file/object và yêu cầu hiệu năng.
- Xác định trường hợp cần agent và trường hợp có thể chuyển dữ liệu agentless.
- Thiết kế kết nối NFS, SMB, HDFS, object storage, Amazon S3, Amazon EFS và Amazon FSx.
- Cấu hình IAM role, bucket policy, KMS key, network endpoint và quyền truy cập nguồn/đích.
- Chọn transfer mode, overwrite, delete handling, metadata preservation, filters, manifests và verification.
- Thiết kế initial copy, incremental sync và cutover cho một đợt migration.
- Theo dõi tiến độ bằng task execution status, CloudWatch metrics/logs, task reports, CloudTrail và EventBridge.
- Tối ưu throughput, phân vùng dữ liệu, giới hạn băng thông, chi phí và quota.
- Xử lý lỗi thường gặp và xây dựng runbook cho migration an toàn.

## 1. AWS DataSync giải quyết bài toán nào?

Khi chuyển một hệ thống file server, NAS hoặc object storage lên AWS, việc sao chép dữ liệu bằng lệnh thủ công thường gặp nhiều vấn đề: tốc độ không ổn định, khó theo dõi tiến độ, thiếu kiểm tra toàn vẹn, khó giữ metadata và khó chạy lại phần dữ liệu thay đổi.

AWS DataSync là dịch vụ truyền dữ liệu trực tuyến được quản lý, hỗ trợ sao chép file và object giữa các hệ thống lưu trữ. Dịch vụ xử lý việc đọc dữ liệu, truyền qua mạng, ghi dữ liệu vào đích, so sánh thay đổi, kiểm tra checksum và theo dõi task execution.

Các tình huống thường gặp:

- Di chuyển file server/NAS từ trung tâm dữ liệu lên Amazon S3, Amazon EFS hoặc Amazon FSx.
- Đồng bộ object giữa các S3 buckets.
- Chuyển dữ liệu giữa AWS và các dịch vụ lưu trữ ở cloud khác.
- Di chuyển dữ liệu từ S3 sang EFS hoặc FSx để phục vụ ứng dụng file-based.
- Tạo bản sao dữ liệu định kỳ cho analytics, archive hoặc business continuity.
- Chuyển dữ liệu theo nhiều đợt để giảm thời gian ngừng hoạt động khi cutover.

DataSync phù hợp với dữ liệu file và object. Dịch vụ không thay thế công cụ migration database, block-level replication hoặc replication của ứng dụng. Với database cần chuyển schema, transaction log và kiểm soát consistency, hãy đánh giá AWS Database Migration Service. Với workload cần replication cấp máy chủ/volume, hãy xem AWS Elastic Disaster Recovery hoặc giải pháp phù hợp với storage platform.

### DataSync và các lựa chọn liên quan

| Nhu cầu | Dịch vụ nên đánh giá |
|---|---|
| Chuyển file/object online, incremental và có verification | AWS DataSync |
| Di chuyển database và giữ thay đổi phát sinh trong lúc migration | AWS Database Migration Service |
| Chuyển lượng dữ liệu rất lớn khi mạng không đủ | AWS Snow Family hoặc phương án offline phù hợp |
| Cung cấp file interface cho ứng dụng on-premises truy cập S3 | AWS Storage Gateway |
| Replicate máy chủ để phục hồi sau thảm họa | AWS Elastic Disaster Recovery |
| Đồng bộ object giữa S3 buckets theo cấu hình bucket | S3 Replication |
| Backup tài nguyên AWS theo policy | AWS Backup |

## 2. Kiến trúc và các khái niệm chính

Một transfer của DataSync được mô tả bởi hai location và một task. Mỗi lần chạy task tạo ra một task execution.

| Thành phần | Vai trò |
|---|---|
| Agent | Appliance VM dùng để đọc/ghi dữ liệu với hệ thống storage do khách hàng quản lý |
| Location | Mô tả một endpoint lưu trữ và cách DataSync truy cập endpoint đó |
| Task | Ghép source location, destination location và các tùy chọn transfer |
| Task execution | Một lần chạy cụ thể của task |
| Task report | Báo cáo JSON về dữ liệu đã chuyển, bỏ qua, xác minh hoặc xóa |
| Service endpoint | Điểm agent kết nối tới DataSync control plane |
| Task network interface | Network interface dùng cho data plane khi task kết nối tới AWS storage |

Luồng tổng quát:

~~~mermaid
flowchart LR
    S["Source storage"] --> A["DataSync agent or service connector"]
    A --> D["AWS DataSync service"]
    D --> T["Task execution"]
    T --> N["Task network interface / data path"]
    N --> O["Destination storage"]
    T --> M["CloudWatch metrics, logs and task report"]
~~~

DataSync có ba công việc chính trong một task execution:

1. **Prepare:** quét source và destination để xác định dữ liệu cần xử lý.
2. **Transfer:** đọc dữ liệu từ source, truyền qua data path và ghi vào destination.
3. **Verify:** kiểm tra checksum và metadata theo verification mode đã chọn.

Thời gian ở giai đoạn Prepare có thể dài hơn thời gian truyền thực tế, đặc biệt với dataset có hàng chục triệu file nhỏ. Vì vậy, throughput mạng cao không bảo đảm toàn bộ task hoàn tất nhanh nếu thời gian inventory/scan là nút thắt.

## 3. Những hệ thống lưu trữ được hỗ trợ

DataSync hỗ trợ các nhóm location sau. Danh sách cloud providers và khả năng tương thích có thể thay đổi theo Region và task mode; hãy kiểm tra ma trận AWS hiện hành trước khi thiết kế.

| Nhóm | Location types |
|---|---|
| File storage tự quản lý | NFS, SMB |
| Hadoop | HDFS |
| Object storage tự quản lý | S3-compatible object storage |
| AWS object storage | Amazon S3 |
| AWS file storage | Amazon EFS |
| AWS managed file systems | FSx for Windows File Server, FSx for Lustre, FSx for OpenZFS, FSx for NetApp ONTAP |
| Cloud storage khác | Google Cloud Storage, Azure Blob Storage, Azure Files và các object storage providers được AWS hỗ trợ |

Một số điểm cần nhớ:

- NFS và SMB thường cần agent đặt gần file server.
- HDFS cần agent có network access tới NameNode và DataNodes.
- S3-to-S3 trong cùng account có thể dùng DataSync mà không cần agent.
- Chuyển giữa AWS storage services trong cùng account thường không cần agent.
- Một số transfer cross-account có thể agentless khi một đầu là Amazon S3.
- Transfer giữa EFS và FSx ở các account khác nhau có thể cần agent và cấu hình location theo NFS/SMB.
- S3 on Outposts có giới hạn task mode riêng.

Không nên suy luận rằng mọi cặp source/destination đều được hỗ trợ chỉ vì từng location type xuất hiện trong danh sách. Khả năng chuyển phụ thuộc account, Region, partition và Basic/Enhanced mode.

## 4. Khi nào cần DataSync agent?

Agent là appliance VM mà DataSync dùng để truy cập storage do bạn quản lý. Agent có thể được triển khai trong on-premises environment, VPC hoặc môi trường ảo hóa được hỗ trợ.

### 4.1 Trường hợp thường cần agent

- On-premises NFS/SMB/HDFS sang AWS.
- AWS EFS/FSx sang storage ở cloud khác.
- Một số transfer giữa AWS storage services ở các accounts khác nhau khi không có S3 làm một đầu.
- Một số luồng giữa commercial Region và AWS GovCloud khi cả hai đầu là EFS/FSx.

### 4.2 Trường hợp thường agentless

- AWS storage services trong cùng account.
- S3 và một AWS storage service khác giữa các accounts theo ma trận hỗ trợ.
- Amazon S3 và object storage ở cloud khác.
- Một số luồng S3 giữa commercial Region và GovCloud.

Ví dụ:

| Source | Destination | Agent |
|---|---|---|
| On-prem NFS | S3 | Có |
| On-prem SMB | FSx for Windows | Có |
| S3 | S3 cùng account | Không |
| S3 account A | S3 account B | Không |
| S3 | EFS khác account, theo ma trận hỗ trợ | Không |
| EFS | FSx khác account | Có thể cần, tùy cách cấu hình location |
| S3 on Outposts | S3 trong Region | Có |

Luôn xác nhận bằng trang “Do I need an AWS DataSync agent?” và “Where can I transfer your data?” trước khi tạo location.

### 4.3 Vị trí triển khai agent

Đặt agent gần source storage để giảm latency và tăng throughput. Agent phải có:

- Kết nối tới source storage bằng giao thức tương ứng.
- Kết nối tới DataSync service endpoint.
- Kết nối data plane tới task network interfaces và destination service.
- DNS resolution và route phù hợp.
- CPU, RAM và disk đáp ứng quy mô dataset.

Có thể triển khai agent trên VMware ESXi 7.0/8.0, KVM, Nutanix AHV qua KVM image, Microsoft Hyper-V hoặc Amazon EC2 theo các tùy chọn AWS hỗ trợ hiện hành. Enhanced mode agent cũng hỗ trợ Red Hat OpenShift Virtualization theo cập nhật tháng 10/2026.

Sau khi activation, AWS quản lý appliance và tự động cập nhật phần mềm agent cùng hệ điều hành nền. Việc cập nhật thường chỉ diễn ra khi agent idle; agent có thể offline trong thời gian ngắn sau update. Hãy theo dõi trạng thái agent trước khi chạy task theo lịch quan trọng.

### 4.4 Yêu cầu tài nguyên tham khảo

| Loại agent VM | vCPU | RAM | Disk |
|---|---:|---:|---:|
| Basic mode agent | 4 | 32 GB cho dataset tới 20 triệu items; 64 GB khi lớn hơn | 80 GB |
| Enhanced mode agent | 8 | 32 GB | 80 GB |

Với agent trên EC2, AWS đưa ra khuyến nghị instance family/size riêng theo mode và số lượng file. Dataset có nhiều directory hoặc metadata lớn có thể cần nhiều RAM hơn dự kiến. Không chọn instance chỉ theo tổng dung lượng TB; số lượng file và kích thước trung bình của file cũng quan trọng.

## 5. Basic mode và Enhanced mode

DataSync có hai task modes. Mode phải được chọn khi tạo task và không thể đổi sau đó. Nếu muốn chuyển mode, cần tạo task mới.

| Tiêu chí | Enhanced mode | Basic mode |
|---|---|---|
| Xử lý | Listing, preparing, transfer và verify song song | Các giai đoạn chủ yếu tuần tự |
| Dataset | Hầu như không giới hạn số object theo quota task | Có quota file/object/directory |
| Hiệu năng | Thường cao hơn, nhất là dataset lớn | Có thể chậm hơn do prepare/verify tuần tự |
| Logging | Structured JSON logs | Unstructured logs |
| Verification | Xác minh dữ liệu được chuyển | Mặc định kiểm tra toàn bộ source/destination |
| Task mode | Không thể đổi sau khi tạo | Không thể đổi sau khi tạo |
| S3 on Outposts | Không hỗ trợ | Hỗ trợ |
| Agent | Cần Enhanced mode agent khi transfer thuộc loại agent-based | Cần Basic mode agent khi transfer thuộc loại agent-based |

### 5.1 Khả năng Enhanced mode cập nhật trong năm 2026

Enhanced mode đã mở rộng hỗ trợ theo các cập nhật gần đây của AWS:

- Tháng 07/2026: hỗ trợ thêm EFS, FSx for Lustre, HDFS và agent-based transfer với Azure Blob/object storage; bổ sung Hyper-V agent.
- Tháng 10/2026: hỗ trợ NFS 4.2, FSx for OpenZFS và tùy chọn kiểm soát object metadata.
- Ngày 29/10/2026: hỗ trợ các loại FSx còn lại như FSx for Windows File Server và FSx for NetApp ONTAP; agent image cho Red Hat OpenShift Virtualization.

Enhanced mode hiện được hỗ trợ cho hầu hết các transfer location mà DataSync hỗ trợ, ngoại trừ các transfer sử dụng S3 on Outposts. Một số luồng tới/từ NFS, SMB, HDFS, Azure Blob hoặc object storage cần Enhanced mode agent. Nếu không dùng agent, khả năng hỗ trợ phụ thuộc source/destination cụ thể.

### 5.2 Khác biệt về object tags

Khi chuyển cloud storage tới hoặc từ location không hỗ trợ object tags:

- Enhanced mode có thể fail task ngay nếu ObjectTags không được chỉ định hoặc đặt PRESERVE.
- Basic mode có thể tiếp tục nhưng báo lỗi theo từng object có tag không thể giữ.

Hãy kiểm tra hỗ trợ metadata/tag của destination trước khi tạo task, đặc biệt khi migration object storage giữa các providers.

### 5.3 Quyền cần thiết

Để tạo Enhanced mode task, principal gọi CreateTask cần quyền **iam:CreateServiceLinkedRole**. Tài khoản cũng cần quyền truy cập DataSync resources và quyền cần thiết tới location resources. Không cấp quyền quá rộng chỉ để khắc phục một lỗi permission; hãy xác định role nào thực hiện từng thao tác.

## 6. Agentless transfer và cross-account/cross-Region

DataSync có thể truyền dữ liệu giữa AWS storage services mà không cần agent. Khi chuyển giữa các AWS storage services trong cùng account, dữ liệu vẫn nằm trong AWS network và không đi qua public internet.

### 6.1 Cross-account

Với S3 cross-account, cấu hình IAM role cho DataSync ở account sở hữu bucket đích hoặc nguồn. Role trust phải cho phép DataSync assume role; bucket policy và KMS key policy phải cho phép thao tác cần thiết.

Không nhầm lẫn giữa:
- Role mà DataSync assume để truy cập bucket.
- Role của người tạo task.
- Role hoặc credential mà agent dùng để truy cập hệ thống tự quản lý.

### 6.2 Cross-Region

Với transfer giữa AWS storage services ở hai Regions, một location phải nằm trong Region nơi DataSync task được sử dụng. Một số luồng NFS/SMB/HDFS/object storage không thể được cấu hình như một transfer xuyên Region theo cùng cách; hai location cần nằm trong Region nơi agent được kích hoạt.

Dữ liệu chuyển giữa Regions phát sinh data transfer out từ source Region. Hãy tính phí này cùng DataSync per-GB charge và phí dịch vụ lưu trữ.

## 7. Cách chọn destination storage

DataSync di chuyển dữ liệu; việc chọn storage đích vẫn là quyết định kiến trúc.

| Destination | Khi phù hợp |
|---|---|
| Amazon S3 | Object, backup files, data lake, archive, static content |
| Amazon EFS | Shared POSIX file system cho Linux workloads |
| FSx for Windows File Server | SMB shares, Windows ACLs, Active Directory integration |
| FSx for Lustre | HPC, ML, high-performance file workloads |
| FSx for OpenZFS | NFS workloads cần filesystem features và latency thấp |
| FSx for NetApp ONTAP | Enterprise NAS, NFS/SMB, multi-protocol và NetApp data services |

Cần đánh giá:

- Giao thức ứng dụng đang sử dụng.
- POSIX permissions, UID/GID, Windows ACLs.
- File locking và concurrent writers.
- Throughput, IOPS, latency.
- Capacity và growth.
- Backup, replication, retention.
- Storage class và lifecycle.
- Availability Zone/Region và disaster recovery.

Chuyển từ NFS sang S3 là thay đổi mô hình dữ liệu. Ứng dụng cần đọc/ghi object qua API hoặc gateway tương thích; không thể giả định một POSIX path sẽ hoạt động trực tiếp trên S3.

## 8. Tạo location cho NFS

NFS location cần một agent có thể mount NFS export.

Trước khi tạo location:

1. Xác định NFS server hostname/IP và export path.
2. Chọn agent cùng network có thể truy cập server.
3. Cho phép NFS ports trên firewall.
4. Cấu hình export permissions cho agent.
5. Kiểm tra quyền đọc hoặc ghi theo vai trò source/destination.

DataSync mặc định dùng NFS 4.1. Các phiên bản 4.2, 4.0 và 3.x cũng được hỗ trợ; NFS 4.2 chỉ dùng với Enhanced mode.

Ví dụ export source read-only:

~~~text
/export/data 10.20.1.50(ro,no_root_squash)
~~~

Ví dụ export destination read/write:

~~~text
/export/landing 10.20.1.50(rw,no_root_squash)
~~~

Đây là ví dụ minh họa. Cần giới hạn theo IP của agent và security policy của hệ thống. Nếu không cấp root access, cần cấu hình UID/GID phù hợp để DataSync có thể đọc hoặc ghi dữ liệu và metadata cần thiết.

Tạo location:

~~~bash
aws datasync create-location-nfs \
  --server-hostname 192.0.2.10 \
  --on-prem-config AgentArns=arn:aws:datasync:ap-southeast-1:111122223333:agent/agent-0123456789abcdef0 \
  --subdirectory /export/data \
  --region ap-southeast-1
~~~

Lệnh trả về LocationArn. Lưu ARN này để dùng làm source hoặc destination của task.

## 9. Tạo location cho SMB và HDFS

### 9.1 SMB

SMB location cần agent và thông tin truy cập share. DataSync hỗ trợ NTLM và Kerberos authentication theo cấu hình location.

Các yếu tố cần kiểm tra:

- Server hostname/domain và share path.
- User có quyền enumerate, read, write và đọc metadata phù hợp.
- Domain/DNS và Kerberos realm nếu dùng Kerberos.
- SMB version. AWS khuyến nghị SMB 3.0.2 trở lên vì SMB 1.0 có các rủi ro bảo mật đã biết.
- Quyền đọc/ghi Windows ACLs nếu muốn bảo toàn security descriptors.

Ví dụ tạo SMB location bằng NTLM:

~~~bash
aws datasync create-location-smb \
  --agent-arns arn:aws:datasync:ap-southeast-1:111122223333:agent/agent-0123456789abcdef0 \
  --server-hostname fileserver.example.internal \
  --subdirectory /share/migration \
  --authentication-type NTLM \
  --user datasync-user \
  --password fileb://smb-password.txt \
  --domain EXAMPLE \
  --region ap-southeast-1
~~~

Trong môi trường thực tế, không đưa password vào shell history hoặc source control. Ưu tiên cơ chế lưu credential được AWS hỗ trợ như Secrets Manager và quyền đọc secret giới hạn.

### 9.2 HDFS

HDFS location cần agent có thể kết nối:

- NameNode.
- DataNodes.
- Hadoop KMS nếu cluster dùng encryption zones.
- Kerberos KDC nếu xác thực Kerberos được cấu hình và hỗ trợ cho loại location/task đó.

Các port thường gặp là NameNode 8020, DataNode 9866 với Hadoop 3.x, Hadoop KMS 9600 và Kerberos KDC 88. Port thực tế phụ thuộc Hadoop distribution và cấu hình cluster.

## 10. Tạo location cho object storage

DataSync có thể truy cập S3-compatible object storage on-premises hoặc ở cloud khác. Cần cung cấp:

- Server hostname.
- Bucket/container name.
- Prefix (subdirectory) nếu chỉ transfer một vùng.
- HTTP/HTTPS protocol và port.
- Access key/secret key hoặc credential được hỗ trợ.
- Agent ARN nếu transfer scenario cần agent.
- Certificate chain nếu object storage dùng private/self-signed CA.

Ưu tiên HTTPS. Không dùng HTTP qua network không tin cậy vì credential và data có thể bị lộ. Nếu server dùng private CA, cung cấp certificate chain đúng để DataSync xác thực server.

DataSync có thể chuyển object storage với hoặc không agent tùy source/destination và task mode. Kiểm tra agent requirement trước khi tạo location.

## 11. Tạo location Amazon S3

S3 location dùng IAM role mà DataSync assume để truy cập bucket. Role cần quyền khác nhau tùy bucket là source hay destination.

### 11.1 Quyền source S3

Các quyền thường cần gồm:

- s3:GetBucketLocation
- s3:ListBucket
- s3:ListBucketMultipartUploads
- s3:GetObject
- s3:GetObjectTagging nếu copy tags
- s3:GetObjectVersion và s3:GetObjectVersionTagging khi cần xử lý versioned objects
- s3:ListMultipartUploadParts khi cần

### 11.2 Quyền destination S3

Ngoài quyền list/location, destination role thường cần:

- s3:PutObject
- s3:AbortMultipartUpload
- s3:ListMultipartUploadParts
- s3:GetObject và s3:GetObjectTagging cho verification hoặc metadata operations
- s3:PutObjectTagging nếu giữ object tags
- s3:DeleteObject nếu task được phép remove destination objects

Đây là nhóm quyền tham khảo. Tùy task options, versioning, object tags, encryption và cross-account access, policy cần thêm quyền cụ thể.

### 11.3 Tạo S3 location

~~~bash
aws datasync create-location-s3 \
  --s3-bucket-arn arn:aws:s3:::company-migration-bucket \
  --s3-config BucketAccessRoleArn=arn:aws:iam::111122223333:role/DataSyncS3AccessRole \
  --subdirectory /migration/finance \
  --s3-storage-class STANDARD \
  --region ap-southeast-1
~~~

Nếu bucket dùng SSE-KMS với customer managed key, key policy phải cho phép IAM role DataSync sử dụng key. IAM policy cũng cần quyền KMS phù hợp với thao tác đọc/ghi; quyền cụ thể phụ thuộc source/destination và encryption settings. Với cross-account SSE-KMS, dùng đầy đủ key ARN trong role policy và cho phép role trong key policy của account sở hữu key. DataSync không truy cập được bucket dùng SSE-C.

### 11.4 Cross-account S3

Với bucket thuộc account khác:

- Role DataSync assume phải được tạo trong account sở hữu bucket.
- Trust policy cho phép DataSync assume role.
- Bucket policy cho phép role thao tác.
- KMS key policy cho phép role dùng key nếu bucket dùng SSE-KMS.
- Xem xét điều kiện aws:SourceAccount và aws:SourceArn để giảm rủi ro confused deputy.
- Kiểm tra Object Ownership và ACL settings để tránh object được ghi nhưng owner/access không như mong muốn.

Với Basic mode, prefix S3 không được bắt đầu bằng dấu gạch chéo và không được chứa các pattern như //, /./ hoặc /../. Enhanced mode hỗ trợ các prefix này. Nếu source bucket đã dùng object keys có dạng đặc biệt, hãy kiểm tra mode và thử trên prefix mẫu trước khi tạo task production.

## 12. IAM, Secrets Manager và KMS

DataSync sử dụng nhiều lớp quyền. Nên phân tách:

| Principal | Trách nhiệm |
|---|---|
| Migration operator | Tạo agent/location/task, start/stop execution |
| DataSync service-linked role | Thực hiện các thao tác service cần quyền AWS-managed |
| S3 access role | Cho phép DataSync truy cập bucket source/destination |
| Agent/local storage credentials | Truy cập NFS, SMB, HDFS hoặc object storage |
| Logging role/service-linked permissions | Ghi log vào CloudWatch |
| Manifest access role | Đọc manifest từ S3 nếu task dùng manifest |

### 12.1 Least privilege

- Chỉ cấp DataSync operator quyền trên task/location/agent cần thiết.
- Scope S3 access role vào đúng bucket và prefix.
- Không cấp s3:* trên toàn bộ account.
- Giới hạn KMS key theo đúng role và encryption context nếu phù hợp.
- Không chia sẻ SMB password hoặc object-storage secret trong file task definition.
- Dùng CloudTrail để audit thay đổi role, location, task và policy.

### 12.2 Mã hóa dữ liệu

DataSync mã hóa traffic giữa các locations bằng mutual TLS 1.3. Kết nối tới source/destination dùng các cơ chế bảo vệ của storage protocol tương ứng, ví dụ SMB security features, TLS của object storage hoặc encryption features của AWS storage service.

Mã hóa at rest vẫn do storage destination kiểm soát:

- S3 SSE-S3 hoặc SSE-KMS.
- EFS encryption at rest.
- FSx encryption at rest bằng KMS key.
- Encryption của source storage nếu hệ thống hiện hữu hỗ trợ.

DataSync không tự động biến mọi source/destination thành encrypted-at-rest storage. Hãy kiểm tra cấu hình storage và key policy riêng.

## 13. Network design cho DataSync

Một transfer có ít nhất ba kết nối logic:

1. Agent kết nối source storage để đọc dữ liệu.
2. DataSync data plane truyền dữ liệu giữa source và destination.
3. DataSync service kết nối destination storage để ghi dữ liệu.

Với on-premises agent dùng public hoặc FIPS endpoint, agent cần HTTPS tới DataSync service. Với VPC service endpoint, agent dùng AWS PrivateLink để kết nối service. Task network interfaces trong subnet/VPC cần security groups và routes phù hợp để kết nối AWS storage.

### 13.1 Các port thường gặp

| Source | Destination | TCP port | Mục đích |
|---|---|---:|---|
| Agent | NFS server | 2049 | NFS 4.0/4.1/4.2 |
| Agent | NFS server | 111, 2049 | NFS 3.x |
| Agent | SMB server | 139 hoặc 445 | SMB |
| Agent | S3-compatible object storage | 443 hoặc 80 | Object API; ưu tiên HTTPS |
| Agent | Hadoop NameNode | 8020 mặc định | HDFS metadata |
| Agent | Hadoop DataNodes | 9866 mặc định Hadoop 3.x | HDFS data |
| Agent | Kerberos KDC | 88 | Authentication |
| Agent | DataSync VPC endpoint | 1024-1064 | Control plane |
| Agent | DataSync task network interfaces | 443 | Data plane |

Port cụ thể phụ thuộc protocol và cấu hình storage. Hãy kiểm tra tài liệu network requirements cho đúng loại location.

DataSync có dual-stack IPv4/IPv6 cho các data sources được hỗ trợ như EFS, NFS, SMB và object storage. Agent image cũ tải trước ngày 16/07/2025 không hỗ trợ IPv6. Trong dual-stack network, xác nhận agent version và IP preference để tránh một bên dùng IPv6 trong khi route/firewall chỉ cho IPv4.

### 13.2 PrivateLink và FIPS

DataSync hỗ trợ public, VPC và FIPS service endpoints tại các Regions tương ứng. VPC endpoint policies có thể giới hạn DataSync actions. Nếu yêu cầu compliance, xác nhận FIPS endpoint availability, agent compatibility và encryption settings.

### 13.3 Direct Connect và VPN

Direct Connect hoặc Site-to-Site VPN có thể cung cấp network path giữa agent và on-premises/VPC resources. Tuy nhiên, DataSync vẫn cần đường kết nối tới service endpoint và task data path. Kiểm tra route propagation, MTU, firewall, DNS và security groups ở cả hai chiều.

## 14. Cách DataSync phát hiện thay đổi và transfer

Mặc định, DataSync scan source và destination để xác định file/object cần copy. Nó so sánh nội dung/metadata theo task options, sau đó chỉ truyền những phần khác nhau khi TransferMode là CHANGED.

Trong lần đầu, phần lớn dataset sẽ được transfer. Các lần chạy sau có thể chỉ chuyển những file/object thay đổi.

### 14.1 Basic mode

Basic mode chuẩn bị dataset, sau đó transfer và verify theo trình tự. Với nhiều file nhỏ, thời gian scan/prepare có thể chiếm phần lớn tổng thời gian.

### 14.2 Enhanced mode

Enhanced mode xử lý listing, preparing, transfer và verification song song. Dữ liệu có thể được chuyển ngay khi đã được prepare, giúp scale tốt hơn với dataset rất lớn.

### 14.3 File đang mở hoặc bị khóa

- DataSync thường có thể transfer file đang mở.
- Nếu file đang được ghi trong lúc transfer, verification có thể phát hiện không nhất quán; chạy task lần nữa để lấy phiên bản mới nhất.
- Nếu file bị khóa và storage server không cho DataSync mở, file có thể bị skip kèm lỗi.
- DataSync không khóa hoặc mở khóa file thay cho ứng dụng.

Với database files hoặc ứng dụng ghi liên tục, hãy phối hợp snapshot/quiesce hoặc application-level export. Không coi một lần copy thành công là bằng chứng dataset có consistency giao dịch.

## 15. Transfer mode, overwrite và delete behavior

Các tùy chọn này quyết định DataSync đồng bộ dữ liệu theo cách nào.

| Tùy chọn | API value | Ý nghĩa |
|---|---|---|
| Transfer only changed data | CHANGED | Sau initial copy, chỉ copy data/metadata khác nhau |
| Transfer all data | ALL | Copy mọi dữ liệu source mỗi lần chạy |
| Overwrite destination | ALWAYS | Ghi đè khi source khác destination |
| Do not overwrite | NEVER | Giữ destination dù source khác |
| Keep destination-only files | PRESERVE | Không xóa file/object chỉ có ở destination |
| Remove destination-only files | REMOVE | Xóa dữ liệu đích không còn ở source |

Lưu ý:

- CHANGED phù hợp với recurring synchronization.
- ALL có thể hữu ích khi muốn ép copy lại toàn bộ nhưng làm tăng data transfer và request cost.
- REMOVE có thể gây mất dữ liệu ở destination.
- Không thể kết hợp PreserveDeletedFiles=REMOVE với TransferMode=ALL vì DataSync không scan destination để xác định dữ liệu cần xóa trong ALL mode.
- Overwrite có thể phát sinh retrieval/early deletion charges với một số S3 storage classes.
- Khi destination có thay đổi độc lập, NEVER giúp bảo vệ dữ liệu đích nhưng có thể khiến source và destination không đồng nhất.

Trước khi bật REMOVE, hãy chạy pilot với prefix riêng, xác nhận filters, backup/versioning và owner của dữ liệu đích.

## 16. Bảo toàn metadata

Di chuyển file/object không chỉ là copy bytes. Ứng dụng có thể phụ thuộc vào permissions, owner, timestamps, tags và metadata.

### 16.1 POSIX metadata

DataSync có thể giữ:

- UID/GID.
- POSIX permissions.
- Access time (Atime).
- Modification time (Mtime).
- Metadata của special devices theo giới hạn hỗ trợ.

Atime là best-effort vì hành vi timestamp không hoàn toàn đồng nhất giữa các hệ thống. Mtime PRESERVE được khuyến nghị cho recurring transfers để DataSync so sánh thay đổi ổn định.

DataSync không hỗ trợ sao chép NFS version 4 ACLs. Nếu ứng dụng phụ thuộc NFSv4 ACLs, hãy lập kế hoạch chuyển quyền truy cập riêng và kiểm thử trên destination trước cutover.

### 16.2 SMB security descriptors

Khi transfer giữa SMB và FSx for Windows File Server hoặc giữa các FSx for Windows File Server locations, có thể cấu hình copy owner, DACL và SACL theo SecurityDescriptorCopyFlags.

SACL cần quyền bổ sung trên Windows source. Đích có thể gán owner theo user được cấu hình cho destination location. Hãy kiểm tra ACL semantics và domain identity trước khi cutover.

### 16.3 Object metadata và tags

Khi chuyển giữa object storage systems, DataSync có thể giữ user-defined object metadata và object tags. Enhanced mode đã bổ sung option kiểm soát ObjectMetadata trong bản cập nhật tháng 10/2026.

Metadata mapping giữa các cloud providers không phải lúc nào cũng tương đương. Một số attributes như ContentType, ContentEncoding, ContentLanguage và CacheControl có thể được copy theo best-effort nếu destination hỗ trợ.

Không mặc định rằng mọi metadata riêng của vendor nguồn đều được giữ nguyên ở destination. Hãy tạo test dataset gồm nhiều loại metadata/tag và xác minh kết quả trước migration lớn.

## 17. Filters và manifests

Có hai cách chọn tập dữ liệu cần chuyển:

- **Filters:** chọn file/folder/object theo pattern.
- **Manifest:** liệt kê chính xác các file/object cần chuyển.

### 17.1 Include filters

Include filter giới hạn dữ liệu được scan/transfer. Ví dụ chỉ lấy hai thư mục:

~~~text
/finance|/legal
~~~

Include patterns hỗ trợ wildcard * ở cuối pattern. Ví dụ /reports* được hỗ trợ, nhưng *.csv không phải include pattern hợp lệ theo quy tắc wildcard hiện hành.

### 17.2 Exclude filters

Exclude filter bỏ qua dữ liệu không cần chuyển:

~~~text
*/.temp|*/cache|*.tmp
~~~

Filters phân biệt chữ hoa/chữ thường và được tính tương đối với source location path. Khi dùng AWS CLI, dùng dấu nháy đơn bao filter và ký tự | để phân tách nhiều pattern.

Ví dụ:

~~~bash
aws datasync create-task \
  --source-location-arn arn:aws:datasync:ap-southeast-1:111122223333:location/loc-source12345678901 \
  --destination-location-arn arn:aws:datasync:ap-southeast-1:111122223333:location/loc-dest1234567890123 \
  --excludes FilterType=SIMPLE_PATTERN,Value='*/temp|*/tmp'
~~~

### 17.3 Manifest

Manifest là file CSV liệt kê chính xác path file/object cần transfer. Manifest phù hợp khi danh sách đối tượng đến từ hệ thống inventory hoặc cần kiểm soát một tập dữ liệu xác định.

Một manifest không dùng tên thư mục để hàm ý copy toàn bộ nội dung bên trong. Hãy liệt kê từng object/file path hoặc dùng include filter cho directory tree.

Enhanced mode hỗ trợ manifest tối đa 20 GB. Manifest đặt trong S3 và cần IAM role cho DataSync đọc object. Có thể chỉ định version ID của manifest để đảm bảo lần chạy dùng đúng danh sách đã phê duyệt.

### 17.4 Dữ liệu DataSync tự loại trừ

DataSync tự bỏ qua một số path đặc biệt như .snapshot, /.aws-datasync, /.awssync và /.zfs trong các tình huống tương ứng. Kiểm tra danh sách AWS hiện hành nếu storage platform tạo snapshot directories hoặc metadata paths riêng.

## 18. Data integrity và verification

DataSync luôn thực hiện integrity checks trong quá trình transfer. Ngoài ra, có thể chọn cách verify sau khi transfer.

| Verify mode | API value | Hành vi |
|---|---|---|
| Verify only transferred data | ONLY_FILES_TRANSFERRED | So sánh checksum của dữ liệu được chuyển ở source và destination |
| Verify all data | POINT_IN_TIME_CONSISTENT | Scan và xác minh toàn bộ dataset source/destination |
| No additional verification | NONE | Chỉ giữ integrity checks trong lúc transfer |

ONLY_FILES_TRANSFERRED là lựa chọn được khuyến nghị cho nhiều trường hợp và là default của Enhanced mode. POINT_IN_TIME_CONSISTENT là default của Basic mode, nhưng không được hỗ trợ trong Enhanced mode.

Nếu dùng manifest, verification chỉ áp dụng cho những item có trong manifest. POINT_IN_TIME_CONSISTENT không phù hợp với S3 Glacier Flexible Retrieval hoặc S3 Glacier Deep Archive; hãy xem storage class guidance trước khi chọn.

Các lỗi verification có thể gồm:

- Checksum failure.
- Metadata failure.
- Files were added.
- Files were removed.
- Source thay đổi trong khi task đang chạy.

Một task execution SUCCESS cho biết DataSync hoàn thành theo options đã cấu hình. Nó không chứng minh ứng dụng đã được cutover đúng, mọi business transaction đã nhất quán hoặc mọi metadata ngoài phạm vi hỗ trợ đã được giữ.

## 19. Lên lịch và incremental synchronization

DataSync task có thể chạy thủ công hoặc theo lịch. Schedule hỗ trợ cron/rate expression với khoảng thời gian tối thiểu một giờ. Lịch sử dụng UTC.

Ví dụ chạy mỗi ngày lúc 22:00 UTC:

~~~text
cron(0 22 * * ? *)
~~~

Ví dụ chạy mỗi 12 giờ:

~~~text
rate(12 hours)
~~~

Task schedule có thể tự động bị disable nếu task liên tục thất bại với cùng một lỗi hoặc Region được sử dụng bị disable. Hãy theo dõi Schedule status và DisabledReason.

### 19.1 Migration theo nhiều vòng

Một chiến lược phổ biến:

1. Initial copy: chuyển toàn bộ dataset.
2. Incremental copy: chạy định kỳ để copy phần thay đổi.
3. Rehearsal: đo thời gian delta sync và kiểm tra ứng dụng trên destination.
4. Freeze: dừng ghi vào source hoặc chuyển ứng dụng sang chế độ read-only.
5. Final sync: chạy lần cuối và verify.
6. Cutover: chuyển client/application sang destination.
7. Validation: kiểm tra read/write, permissions, path, metadata và business workflows.
8. Rollback window: giữ source read-only hoặc giữ phương án quay lại theo chính sách.
9. Decommission: chỉ ngừng source khi owner chấp thuận và retention đã được đáp ứng.

DataSync không tự tạo transactionally consistent snapshot cho mọi ứng dụng. Với file đang được ghi liên tục, hãy dùng application quiesce, snapshot hoặc cơ chế nhất quán riêng của storage system.

## 20. Theo dõi task execution

Khi start task, DataSync có thể hiển thị các trạng thái:

| Trạng thái | Ý nghĩa |
|---|---|
| QUEUED | Đang chờ agent/task slot |
| LAUNCHING | Khởi tạo task execution |
| LAUNCHED | Execution đã được khởi chạy |
| PREPARING | Scan và xác định dữ liệu cần chuyển |
| TRANSFERRING | Đang truyền dữ liệu |
| VERIFYING | Đang xác minh dữ liệu |
| SUCCESS | Hoàn thành |
| ERROR | Execution thất bại |
| CANCELLING | Đang dừng execution |

Task status và task execution status là hai khái niệm khác nhau. Task có thể AVAILABLE hoặc UNAVAILABLE trong khi một execution có trạng thái riêng.

Một agent chỉ chạy một task execution tại một thời điểm. Nếu task khác dùng cùng agent, execution có thể ở QUEUED. Task queueing được bật mặc định.

## 21. CloudWatch metrics, logs và task reports

### 21.1 CloudWatch metrics

DataSync gửi metrics vào namespace **aws/datasync** theo chu kỳ 5 phút và giữ metrics 15 tháng.

Một số metric hữu ích:

| Metric | Ý nghĩa |
|---|---|
| BytesTransferred | Logical bytes DataSync gửi trước compression |
| BytesCompressed | Physical bytes truyền qua network sau compression nếu có |
| BytesWritten | Bytes được ghi tại destination |
| FilesTransferred | Số file/object/directory được truyền |
| FilesSkipped | Số item bị bỏ qua |
| FilesDeleted | Số item bị xóa tại destination |
| FilesListedSource | Số object được Enhanced mode tìm thấy ở source |
| FilesPrepared | Số object được chuẩn bị để transfer trong Enhanced mode |
| BytesVerifiedDestination | Bytes được xác minh tại destination trong Basic mode |
| BytesPreparedSource | Bytes được chuẩn bị tại source trong Basic mode |

Metric availability khác nhau giữa Basic và Enhanced mode. Dùng metric theo TaskId và AgentId để phân tích bottleneck.

### 21.2 CloudWatch Logs

Nên bật ít nhất log cơ bản và lỗi transfer. Enhanced mode tự gửi structured logs tới log group /aws/datasync thông qua service-linked role. Basic mode cần cấu hình log group và quyền ghi phù hợp.

Chọn log level theo mục tiêu:

- OFF: không gửi task logs.
- BASIC: log thông tin cơ bản và transfer errors.
- TRANSFER: log từng file/object được chuyển và integrity checks.

TRANSFER có thể tạo log volume lớn; cân nhắc retention và chi phí ingestion.

### 21.3 Task reports

Task report được tạo dưới dạng JSON và có hai mức:

- Summary only: số item transferred/skipped/verified/deleted, bytes, start/end time, trạng thái và task options.
- Standard: summary cộng chi tiết từng file/object/folder đã transfer, skip, verify hoặc delete; có thể chọn errors only hoặc successes and errors.

Task reports hữu ích khi migration hàng triệu file, audit chain-of-custody hoặc cần điều tra chính xác item nào lỗi.

### 21.4 CloudTrail và EventBridge

CloudTrail ghi nhận các API calls như create location, create task, start task execution, update task và delete resources. EventBridge có thể nhận sự kiện thay đổi trạng thái task execution để kích hoạt notification hoặc automation.

Có thể dùng SNS/Chatbot hoặc hệ thống incident management để thông báo owner khi execution ERROR hoặc schedule bị disable.

## 22. Tối ưu throughput và thời gian migration

Hiệu năng phụ thuộc nhiều yếu tố:

- Băng thông và latency giữa agent với source/destination.
- Storage throughput/IOPS.
- Số lượng file và kích thước trung bình.
- Metadata lookup performance.
- CPU/RAM của agent.
- Task mode.
- Số task chạy đồng thời.
- Compression và nội dung có thể nén.
- Thời gian Prepare và Verify.

### 22.1 Nhiều file nhỏ

Với hàng triệu file nhỏ, metadata operations và directory traversal có thể là bottleneck. Cân nhắc:

- Chia dataset theo thư mục hoặc prefix.
- Chạy nhiều tasks song song với agent riêng cho từng task.
- Dùng nhiều agents với cùng location khi thích hợp.
- Giảm scope bằng include/exclude filters hoặc manifest.
- Kiểm tra storage array không bị quá tải do nhiều parallel reads.

DataSync cho phép tối đa bốn Basic mode agents và bốn Enhanced mode agents gắn với một location. Nhưng multiple agents không phải HA: tất cả agents gắn vào location phải online khi bắt đầu task.

### 22.2 Nhiều file lớn

Với file lớn, throughput mạng và storage I/O thường quan trọng hơn metadata scanning. Kiểm tra:

- NIC bandwidth và EC2 instance network performance.
- Direct Connect/VPN throughput.
- Destination storage throughput.
- Data compression ratio.
- Task bandwidth limit.

### 22.3 Bandwidth throttling

Có thể giới hạn BytesPerSecond để không chiếm hết băng thông production. Giá trị -1 thường biểu thị không giới hạn theo cấu hình DataSync. Với migration ban đêm, có thể tăng bandwidth; giờ cao điểm giảm giới hạn.

Không thay đổi bandwidth chỉ dựa trên network utilization. Hãy xem cả source storage latency, application latency và queue backlog.

## 23. Quota và giới hạn cần biết

Quota có thể thay đổi theo Region. Kiểm tra AWS Service Quotas trước migration lớn.

| Hạng mục | Giá trị mặc định được AWS công bố |
|---|---:|
| Tasks trên mỗi account/Region | 100, có thể yêu cầu tăng |
| Basic mode: items cho on-prem/self-managed/other cloud tới AWS | 50 triệu file/object/directory mỗi task execution |
| Basic mode: items giữa AWS storage services | 25 triệu mỗi task execution |
| Enhanced mode: items | Hầu như không giới hạn theo quota dataset task |
| Throughput tối đa mỗi task có agent | 10 Gbps |
| Throughput tối đa mỗi task agentless | 5 Gbps |
| Filter length | 102.400 ký tự tổng hợp |
| Queued executions mỗi task | 50 |
| Concurrent Enhanced task executions | 120 |
| Task execution history | 30 ngày |
| Enhanced mode manifest | 20 GB |

Với Basic mode có hơn 20 triệu items, AWS yêu cầu tối thiểu 64 GB RAM cho agent. Prefix S3 cũng được tính như directory trong quota Basic mode; một object path có nhiều prefix components làm tăng số item inventory.

Nếu dataset quá lớn, chia task theo prefix/directory và kiểm soát overlap để tránh copy trùng hoặc xóa nhầm. Không chỉ dựa vào tổng TB để đánh giá quota; cần inventory số file/object/directory.

## 24. Chi phí AWS DataSync

Chi phí DataSync gồm:

1. **DataSync data transfer charge:** phí theo GB được chuyển.
2. **Enhanced mode task execution charge:** task execution fee bổ sung cho Enhanced mode.
3. **Storage request charges:** S3 LIST, HEAD, GET, PUT, tagging và multipart requests.
4. **Destination storage charges:** S3/EFS/FSx storage, throughput, IOPS hoặc capacity.
5. **Data transfer charges:** cross-Region, internet egress hoặc các network charges liên quan.
6. **KMS charges:** request sử dụng customer managed key.
7. **PrivateLink:** phí VPC interface endpoints nếu dùng.
8. **Logging/reporting:** CloudWatch Logs, S3 task reports và Athena queries.

### 24.1 Vì sao S3 request costs có thể cao?

Mỗi task execution có thể scan source và destination. DataSync có thể gọi:

- ListObjectV2 để list prefix.
- HeadObject để đọc metadata trong prepare/verify.
- GetObject để đọc nội dung.
- GetObjectTagging để đọc tags.
- PutObject và multipart upload để ghi object.
- PutObjectTagging để ghi tags.
- CopyObject khi cần cập nhật metadata.

Ngay cả khi không có nhiều bytes thay đổi, việc scan hàng triệu objects vẫn có thể phát sinh request charges.

### 24.2 Storage class

Khi S3 là destination, DataSync có thể ghi object mới vào storage class đã chọn. Với object đã tồn tại, DataSync mặc định giữ storage class hiện có nếu task không dùng TransferMode=ALL.

Một số storage classes có retrieval, overwrite, deletion hoặc minimum storage duration charges. Việc overwrite metadata cũng có thể tương đương delete/create object mới và phát sinh chi phí.

Hãy xem xét:

- S3 Standard/Intelligent-Tiering cho dữ liệu truy cập thường xuyên hoặc chưa rõ pattern.
- S3 Standard-IA/One Zone-IA khi phù hợp và có kế hoạch retrieval.
- Glacier classes cho archive sau khi migration hoàn tất, thay vì mặc định dùng archive class trong vòng sync liên tục.
- Lifecycle rules để quản lý incomplete multipart uploads.

### 24.3 Tối ưu chi phí

- Không chạy lịch quá thường xuyên so với tần suất thay đổi dữ liệu.
- Giới hạn prefixes và scope bằng filters/manifest.
- Chọn Basic/Enhanced theo số lượng object, khả năng hỗ trợ và chi phí execution.
- Đặt bandwidth limit phù hợp với network.
- Tránh verify toàn bộ dataset mỗi lần nếu chỉ cần verify transferred files.
- Lên kế hoạch storage class và lifecycle.
- Ước lượng cross-Region data transfer.
- Theo dõi S3 request metrics và DataSync metrics.

## 25. Bảo đảm cutover và rollback

Một migration không kết thúc khi DataSync báo SUCCESS. Cần xác minh ứng dụng, owner và data consistency.

### 25.1 Checklist cutover

1. Inventory source dataset và ghi lại số lượng file/object, tổng dung lượng.
2. Chọn destination storage và xác nhận permission/metadata mapping.
3. Chạy initial copy.
4. Xem task report, errors và skipped items.
5. Chạy incremental sync theo lịch.
6. Thử nghiệm ứng dụng trên destination.
7. Chọn maintenance window và thông báo owner.
8. Dừng ghi hoặc chuyển source sang read-only.
9. Chạy final sync.
10. Chạy verification và đối soát dữ liệu.
11. Chuyển DNS, mount path hoặc application configuration.
12. Theo dõi application metrics và error logs.
13. Giữ source theo rollback window.
14. Chỉ decommission sau khi business owner ký xác nhận.

### 25.2 Rollback

Nếu application không hoạt động trên destination:

- Dừng writes vào destination để tránh split-brain.
- Chuyển application/mount path về source nếu source vẫn authoritative.
- Xác định dữ liệu phát sinh sau cutover và cách reconcile.
- Không chạy reverse sync tự động khi chưa xác định overwrite/delete semantics.
- Ghi lại lỗi và sửa task/options trước lần cutover kế tiếp.

DataSync không tự giải quyết xung đột dữ liệu hai chiều. Nếu cả source và destination cùng nhận writes, cần ứng dụng hoặc giải pháp đồng bộ có conflict-resolution semantics.

## 26. AWS DataSync Discovery và thay đổi dịch vụ

AWS DataSync Discovery từng hỗ trợ thu thập thông tin capacity, utilization và performance của một số storage systems để gợi ý AWS storage đích. Tuy nhiên, tính năng DataSync Discovery đã không còn khả dụng kể từ ngày 20/05/2025.

Vì vậy, với dự án mới, không thiết kế quy trình dựa trên việc tạo DataSync Discovery jobs. Có thể dùng inventory từ storage vendor, AWS Migration Hub hoặc công cụ discovery/assessment phù hợp khác để lập kế hoạch, sau đó dùng DataSync cho data movement.

Đây là điểm cần chú ý khi gặp tutorial cũ vẫn mô tả DataSync Discovery.

## 27. Lab: chuyển dữ liệu NFS lên Amazon S3

Lab mô phỏng migration từ NFS file server sang S3 bằng Enhanced mode. Dùng tài khoản sandbox và dữ liệu thử nghiệm. Không dùng dữ liệu production hoặc bật delete destination trong lần đầu.

### Bước 1: chuẩn bị

Cần có:

- AWS account và Region hỗ trợ DataSync.
- NFS server có export thử nghiệm.
- DataSync Enhanced mode agent đặt gần NFS server.
- S3 bucket đích.
- IAM role cho DataSync truy cập S3.
- Network path giữa agent, NFS server và DataSync endpoint.

Tạo bucket và cấu hình encryption/lifecycle theo yêu cầu lab. Kiểm tra NFS export chỉ cho phép IP agent.

### Bước 2: tạo NFS location

~~~bash
aws datasync create-location-nfs \
  --server-hostname 192.0.2.10 \
  --on-prem-config AgentArns=arn:aws:datasync:ap-southeast-1:111122223333:agent/agent-0123456789abcdef0 \
  --subdirectory /export/lab \
  --region ap-southeast-1
~~~

Lưu LocationArn trả về thành SOURCE_LOCATION_ARN.

### Bước 3: tạo S3 access role và location

Role DataSync cần source/destination permissions tương ứng. Với bucket đích, cho phép list bucket, multipart operations, put/get object và tag operations nếu task giữ tags.

Tạo S3 location:

~~~bash
aws datasync create-location-s3 \
  --s3-bucket-arn arn:aws:s3:::company-datasync-lab \
  --s3-config BucketAccessRoleArn=arn:aws:iam::111122223333:role/DataSyncS3AccessRole \
  --subdirectory /lab-migration \
  --s3-storage-class STANDARD \
  --region ap-southeast-1
~~~

Lưu LocationArn trả về thành DESTINATION_LOCATION_ARN.

### Bước 4: tạo Enhanced mode task

~~~bash
aws datasync create-task \
  --source-location-arn arn:aws:datasync:ap-southeast-1:111122223333:location/loc-source12345678901 \
  --destination-location-arn arn:aws:datasync:ap-southeast-1:111122223333:location/loc-dest1234567890123 \
  --name nfs-to-s3-lab \
  --task-mode ENHANCED \
  --options TransferMode=CHANGED,VerifyMode=ONLY_FILES_TRANSFERRED,OverwriteMode=ALWAYS,PreserveDeletedFiles=PRESERVE,LogLevel=TRANSFER \
  --region ap-southeast-1
~~~

Thay location ARNs bằng ARN thực tế. Principal tạo Enhanced task cần quyền iam:CreateServiceLinkedRole. Đối với task Enhanced, DataSync tự động gửi structured logs tới log group /aws/datasync nếu quyền service-linked role và Region được cấu hình phù hợp.

### Bước 5: chạy task

~~~bash
aws datasync start-task-execution \
  --task-arn arn:aws:datasync:ap-southeast-1:111122223333:task/task-0123456789abcdef0 \
  --region ap-southeast-1
~~~

Lưu TaskExecutionArn trả về. Theo dõi trạng thái:

~~~bash
aws datasync describe-task-execution \
  --task-execution-arn arn:aws:datasync:ap-southeast-1:111122223333:task/task-0123456789abcdef0/execution/exec-0123456789abcdef0 \
  --query Status \
  --region ap-southeast-1
~~~

### Bước 6: kiểm tra dữ liệu

- Kiểm tra task execution đạt SUCCESS.
- Xem CloudWatch logs và task report nếu đã cấu hình.
- Đối chiếu số file/object và bytes transferred.
- Kiểm tra một số file mẫu bằng checksum.
- Kiểm tra POSIX permissions/UID/GID nếu cần.
- Kiểm tra object metadata/tags nếu được yêu cầu.
- Xác nhận source files không bị xóa.
- Chạy lại task để kiểm tra incremental behavior.

### Bước 7: thử lỗi

Tạo một test file mà agent không có quyền đọc hoặc tạo một file đang bị khóa. Quan sát skipped/error report. Sau đó sửa permission và chạy lại.

### Bước 8: cleanup

Sau khi hoàn thành lab và lưu kết quả:

~~~bash
aws datasync delete-task \
  --task-arn arn:aws:datasync:ap-southeast-1:111122223333:task/task-0123456789abcdef0 \
  --region ap-southeast-1
~~~

~~~bash
aws datasync delete-location \
  --location-arn arn:aws:datasync:ap-southeast-1:111122223333:location/loc-source12345678901 \
  --region ap-southeast-1
~~~

~~~bash
aws datasync delete-location \
  --location-arn arn:aws:datasync:ap-southeast-1:111122223333:location/loc-dest1234567890123 \
  --region ap-southeast-1
~~~

Chỉ xóa S3 bucket, IAM role và agent khi chắc chắn không còn resource khác sử dụng. Các lệnh trên là mẫu; thay ARN bằng resource do lab tạo.

## 28. Troubleshooting thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Agent offline | VM dừng, DNS/network/firewall hoặc endpoint không truy cập được | Kiểm tra agent status, VM, route, DNS và endpoint ports |
| NFS mount failed | Export path sai, NFS port bị chặn hoặc export permission thiếu | Test mount từ host cùng network và kiểm tra export rules |
| SMB access denied | User/domain/password hoặc share/NTFS ACL không đủ | Kiểm tra credentials, domain, DNS, share và file ACL |
| Kerberos authentication failed | Principal/keytab/krb5.conf không khớp | Kiểm tra principal case-sensitive, realm và clock synchronization |
| S3 location creation failed | IAM role, bucket policy, KMS key policy hoặc trust policy thiếu | Kiểm tra role assume và các S3/KMS permissions |
| S3 HeadObject/GetObjectTagging AccessDenied | Thiếu quyền đọc object metadata/tag/version | Bổ sung đúng GetObject/GetObjectTagging/GetObjectVersion permissions |
| Task ở PREPARING quá lâu | Dataset có quá nhiều file nhỏ hoặc storage scan chậm | Kiểm tra số item, agent RAM, storage metadata performance và filters |
| Task QUEUED | Agent đang chạy task khác | Chờ task trước hoàn tất hoặc phân phối task sang agent riêng |
| Task UNAVAILABLE | Agent offline hoặc location không truy cập được | Kiểm tra agent và location connectivity |
| Checksum failure | File thay đổi khi transfer hoặc storage read inconsistency | Dừng writes, chạy lại incremental và điều tra source storage |
| Metadata failure | Destination không hỗ trợ metadata source | Điều chỉnh metadata options hoặc chọn storage đích phù hợp |
| Files skipped | Filter, permission, locked file hoặc special path | Đọc task report để xác định lý do từng item |
| Enhanced task fail do object tags | Destination không hỗ trợ tags nhưng ObjectTags đang PRESERVE | Đặt ObjectTags=NONE nếu business không cần tags |
| S3 request cost cao | Task scan hàng triệu object mỗi lần chạy | Giảm schedule frequency, scope theo prefix hoặc manifest |
| Throughput thấp | Agent/storage/network bottleneck hoặc quá nhiều small files | Đo từng thành phần, scale agent/task và phân vùng dataset |
| Task schedule bị disable | Task lỗi liên tục hoặc Region bị disable | Kiểm tra DisabledReason, sửa lỗi rồi enable schedule |
| Destination có file cũ không mong muốn | PreserveDeletedFiles=PRESERVE | Đánh giá REMOVE sau backup và test scope |
| Destination bị ghi đè | OverwriteMode=ALWAYS | Dùng NEVER hoặc tách prefix; kiểm tra task execution options |
| Task mode không hỗ trợ | Source/destination/task mode không tương thích | Đối chiếu support matrix và tạo task mới đúng mode |

## 29. Best practices

### Trước migration

- Inventory số lượng file/object, dung lượng và kích thước trung bình.
- Phân loại dữ liệu theo owner, sensitivity và retention.
- Kiểm tra storage compatibility và task mode.
- Chọn agent/agentless dựa trên ma trận AWS.
- Đo throughput và thời gian prepare bằng pilot.
- Thiết kế IAM least privilege, KMS và network.
- Xác định RPO, RTO, cutover window và rollback plan.

### Trong migration

- Dùng Enhanced mode cho dataset lớn nếu location hỗ trợ.
- Dùng filters/manifests để kiểm soát scope.
- Bật task reports cho dataset lớn hoặc yêu cầu audit.
- Giữ source authoritative cho tới khi final sync và validation hoàn tất.
- Theo dõi task status, errors, skipped files và checksum.
- Dùng bandwidth limit để bảo vệ production network/storage.
- Chạy nhiều task song song chỉ khi source/destination có đủ I/O và network capacity.

### Sau migration

- Xác minh file counts, bytes, metadata và permissions.
- Kiểm thử ứng dụng với destination.
- Giữ source theo rollback/retention policy.
- Đối soát cost và S3 request charges.
- Lưu task reports và bằng chứng approval.
- Decommission source sau khi business owner xác nhận.

### Vận hành định kỳ

- Đặt lịch sync tối thiểu theo nhu cầu thực tế.
- Theo dõi schedule status và task execution errors.
- Cảnh báo khi task ERROR, agent offline hoặc queue age tăng.
- Review task reports và CloudWatch metrics.
- Rà soát IAM roles, Secrets Manager secrets và KMS permissions.
- Kiểm tra quota trước các đợt migration lớn.
- Cập nhật runbook khi AWS thay đổi task modes hoặc supported locations.

## 30. Bài tập tự luyện

1. AWS DataSync giải quyết bài toán gì?
2. Phân biệt agent, location, task và task execution.
3. Khi nào DataSync cần agent?
4. Cho ví dụ một luồng agentless giữa hai S3 buckets.
5. Enhanced mode khác Basic mode ở prepare/transfer/verify như thế nào?
6. Vì sao task mode không thể đổi sau khi tạo?
7. DataSync Discovery còn khả dụng không?
8. Vì sao agent cần đặt gần source storage?
9. Một NFS location cần những thông tin nào?
10. Vì sao S3 access role phải tách biệt với operator role?
11. Sự khác nhau giữa TransferMode CHANGED và ALL là gì?
12. OverwriteMode NEVER bảo vệ điều gì?
13. Vì sao PreserveDeletedFiles REMOVE cần được kiểm tra kỹ?
14. Có thể kết hợp REMOVE và TransferMode ALL không?
15. DataSync giữ những loại metadata nào?
16. Include filter có phân biệt chữ hoa/thường không?
17. Khi nào nên dùng manifest thay cho filter?
18. ONLY_FILES_TRANSFERRED khác POINT_IN_TIME_CONSISTENT thế nào?
19. Vì sao file đang được ghi trong lúc migration có thể fail verification?
20. DataSync schedule có thể chạy nhanh hơn mỗi giờ không?
21. Task reports cung cấp thông tin gì?
22. Vì sao S3 request costs có thể cao dù ít dữ liệu thay đổi?
23. Một agent có thể chạy nhiều task cùng lúc không?
24. DataSync có giải quyết conflict khi source và destination cùng nhận writes không?
25. Những bước nào cần hoàn tất trước cutover?

### Gợi ý đáp án

1. Truyền file/object có quản lý, incremental, verification và monitoring giữa on-premises, AWS và cloud khác.
2. Agent truy cập storage; location mô tả endpoint; task mô tả source/destination/options; execution là một lần chạy.
3. Chủ yếu khi truy cập on-prem/self-managed storage hoặc các cặp transfer cross-account/cross-cloud theo support matrix.
4. S3 bucket account A sang S3 bucket account B theo luồng được hỗ trợ có thể agentless.
5. Enhanced chạy các giai đoạn song song và hỗ trợ dataset rất lớn; Basic xử lý tuần tự và có quotas.
6. Mode ảnh hưởng agent, processing model và task behavior; cần tạo task mới để đổi.
7. Không. Discovery ngừng khả dụng từ 20/05/2025.
8. Giảm network latency và tăng khả năng đọc dữ liệu từ storage.
9. Agent ARN, server hostname, export path và NFS mount options.
10. Operator tạo task; DataSync assume role để đọc/ghi S3. Tách role giúp least privilege.
11. CHANGED chỉ copy khác biệt sau initial copy; ALL copy mọi dữ liệu source mỗi lần chạy.
12. Không ghi đè dữ liệu đã thay đổi ở destination.
13. Vì có thể xóa dữ liệu đích, gây mất dữ liệu hoặc phát sinh storage charges.
14. Không. REMOVE yêu cầu scan destination; ALL không scan destination để xác định phần cần xóa.
15. Tùy hệ thống: POSIX UID/GID/permissions/timestamps, SMB ACLs, object tags và user-defined metadata.
16. Có. Filters case-sensitive.
17. Khi cần transfer danh sách file/object chính xác thay vì pattern.
18. ONLY_FILES_TRANSFERRED xác minh item đã chuyển; POINT_IN_TIME_CONSISTENT scan toàn bộ dataset và không hỗ trợ Enhanced mode.
19. Source có thể thay đổi trong lúc transfer nên checksum/metadata không còn khớp.
20. Không. Minimum schedule interval là một giờ.
21. Summary và chi tiết item transferred/skipped/verified/deleted cùng trạng thái, bytes và thời gian.
22. DataSync vẫn scan và gửi LIST/HEAD/GET/tagging requests trên nhiều objects.
23. Không. Một agent chỉ chạy một task execution tại một thời điểm.
24. Không. Cần thiết kế authoritative source và conflict resolution riêng.
25. Initial/incremental sync, freeze writes, final sync, verification, application validation, owner approval và rollback plan.

## 31. Câu hỏi phỏng vấn

### Khi nào nên chọn DataSync thay vì tự viết script rsync?

Khi cần transfer được quản lý, monitoring, scheduling, incremental copy, verification, filters/manifests và tích hợp AWS storage. Script riêng có thể phù hợp với môi trường nhỏ hoặc logic đặc thù nhưng đội vận hành phải tự xây retry, audit, monitoring và kiểm soát consistency.

### DataSync có phải công cụ backup không?

DataSync có thể copy dữ liệu định kỳ và hỗ trợ một phần use cases business continuity, nhưng không thay thế backup lifecycle, point-in-time recovery, immutable retention hoặc application-consistent backup. Cần kết hợp AWS Backup, S3 versioning/Object Lock hoặc snapshot theo workload.

### Vì sao Enhanced mode phù hợp với hàng chục triệu object?

Enhanced mode song song hóa listing, preparing, transfer và verification, đồng thời tránh quotas dataset của Basic mode. Tuy nhiên, agent, storage I/O, network và supported locations vẫn là các giới hạn thực tế.

### Khi nào cần nhiều agents?

Khi dataset lớn, nhiều file nhỏ hoặc cần nhiều task song song và storage/network có thể chịu tải. Nhiều agent gắn vào một location không tạo HA; tất cả agents cần online khi chạy task.

### DataSync có đảm bảo consistency khi ứng dụng vẫn ghi dữ liệu không?

Không đảm bảo transaction-level consistency cho ứng dụng. DataSync có thể phát hiện một số file thay đổi trong lúc transfer, nhưng migration vẫn cần quiesce hoặc snapshot và final incremental sync.

### Tại sao task SUCCESS vẫn cần kiểm tra application?

SUCCESS xác nhận transfer hoàn tất theo task options. Ứng dụng có thể phụ thuộc ACL, path, case sensitivity, ownership, file locking hoặc semantics không được destination hỗ trợ đầy đủ.

### Khi nào dùng manifest thay cho include filter?

Manifest khi có danh sách chính xác các file/object cần transfer, ví dụ inventory được phê duyệt. Filter khi muốn chọn theo pattern thư mục hoặc tên file.

### Có thể dùng DataSync để đồng bộ hai chiều không?

Một task có source và destination rõ ràng, không phải conflict-resolving bidirectional sync. Hai task ngược chiều có thể ghi đè nhau. Cần thiết kế source of truth và xử lý conflict ở application/storage layer.

## 32. Checklist trước khi đưa migration vào production

### Scope và compatibility

- [ ] Source/destination nằm trong ma trận transfer được hỗ trợ.
- [ ] Task mode đã được chọn đúng.
- [ ] Agent requirement đã được xác định.
- [ ] Dataset inventory có số file/object/directory và tổng dung lượng.
- [ ] Storage metadata và permissions đã được mapping.
- [ ] Discovery được loại khỏi kế hoạch nếu tài liệu cũ còn đề cập.

### Security và networking

- [ ] Agent nằm trong network gần source storage.
- [ ] Security groups/firewalls cho phép các port cần thiết.
- [ ] DataSync service endpoint và task ENIs có network path.
- [ ] IAM roles theo least privilege.
- [ ] S3 bucket policy và KMS key policy đúng.
- [ ] Secrets không nằm trong shell history/source control.
- [ ] Encryption at rest/in transit đã được xác nhận.

### Task options

- [ ] TransferMode phù hợp.
- [ ] OverwriteMode đã được review.
- [ ] PreserveDeletedFiles không xóa nhầm dữ liệu.
- [ ] Metadata/tag/ACL options phù hợp destination.
- [ ] Filters/manifest đã được test.
- [ ] VerifyMode phù hợp task mode và storage class.
- [ ] Bandwidth limit và schedule đã được phê duyệt.

### Monitoring và operations

- [ ] CloudWatch metrics được theo dõi.
- [ ] Task logs và task reports được bật.
- [ ] CloudTrail/EventBridge notifications có owner.
- [ ] Runbook xử lý ERROR, agent offline và skipped items.
- [ ] Quota và throughput đã được kiểm tra.
- [ ] S3 request costs và data transfer charges đã được ước lượng.

### Cutover

- [ ] Initial copy hoàn tất.
- [ ] Incremental sync đã được diễn tập.
- [ ] Maintenance window được thông báo.
- [ ] Source writes đã được dừng hoặc kiểm soát.
- [ ] Final sync và verification PASS.
- [ ] Application validation PASS.
- [ ] Rollback plan và retention window được duyệt.
- [ ] Business owner xác nhận trước khi decommission source.

## 33. Tài liệu tham khảo chính thức

- [What is AWS DataSync?](https://docs.aws.amazon.com/datasync/latest/userguide/what-is-datasync.html)
- [How AWS DataSync works](https://docs.aws.amazon.com/datasync/latest/userguide/how-datasync-transfer-works.html)
- [Where can I transfer my data with AWS DataSync?](https://docs.aws.amazon.com/datasync/latest/userguide/working-with-locations.html)
- [Do I need an AWS DataSync agent?](https://docs.aws.amazon.com/datasync/latest/userguide/do-i-need-datasync-agent.html)
- [Choosing a task mode for your data transfer](https://docs.aws.amazon.com/datasync/latest/userguide/choosing-task-mode.html)
- [Requirements for AWS DataSync agents](https://docs.aws.amazon.com/datasync/latest/userguide/agent-requirements.html)
- [Deploying your AWS DataSync agent](https://docs.aws.amazon.com/datasync/latest/userguide/deploy-agents.html)
- [Activating your AWS DataSync agent](https://docs.aws.amazon.com/datasync/latest/userguide/activate-agent.html)
- [AWS DataSync network requirements](https://docs.aws.amazon.com/datasync/latest/userguide/datasync-network.html)
- [AWS DataSync encryption in transit](https://docs.aws.amazon.com/datasync/latest/userguide/encryption-in-transit.html)
- [Configuring AWS DataSync transfers with an NFS file server](https://docs.aws.amazon.com/datasync/latest/userguide/create-nfs-location.html)
- [Configuring AWS DataSync transfers with an SMB file server](https://docs.aws.amazon.com/datasync/latest/userguide/create-smb-location.html)
- [Configuring AWS DataSync transfers with Amazon S3](https://docs.aws.amazon.com/datasync/latest/userguide/create-s3-location.html)
- [Configuring DataSync transfers with an object storage system](https://docs.aws.amazon.com/datasync/latest/userguide/create-object-location.html)
- [Creating a task for transferring your data](https://docs.aws.amazon.com/datasync/latest/userguide/create-task-how-to.html)
- [Choosing what AWS DataSync transfers](https://docs.aws.amazon.com/datasync/latest/userguide/task-options.html)
- [Configuring how to handle files, objects, and metadata](https://docs.aws.amazon.com/datasync/latest/userguide/configure-metadata.html)
- [Transferring specific files, objects, and folders by using filters](https://docs.aws.amazon.com/datasync/latest/userguide/filtering.html)
- [Transferring specific files or objects by using a manifest](https://docs.aws.amazon.com/datasync/latest/userguide/transferring-with-manifest.html)
- [Configuring how AWS DataSync verifies data integrity](https://docs.aws.amazon.com/datasync/latest/userguide/configure-data-verification-options.html)
- [Scheduling when your AWS DataSync task runs](https://docs.aws.amazon.com/datasync/latest/userguide/task-scheduling.html)
- [Starting a task to transfer your data](https://docs.aws.amazon.com/datasync/latest/userguide/run-task.html)
- [Monitoring your AWS DataSync transfers](https://docs.aws.amazon.com/datasync/latest/userguide/monitoring-overview.html)
- [Monitoring data transfers with Amazon CloudWatch metrics](https://docs.aws.amazon.com/datasync/latest/userguide/monitor-datasync.html)
- [Monitoring data transfers with task reports](https://docs.aws.amazon.com/datasync/latest/userguide/task-reports.html)
- [Monitoring data transfers with Amazon CloudWatch Logs](https://docs.aws.amazon.com/datasync/latest/userguide/configure-logging.html)
- [AWS DataSync quotas](https://docs.aws.amazon.com/datasync/latest/userguide/datasync-limits.html)
- [AWS DataSync pricing](https://aws.amazon.com/datasync/pricing/)
- [AWS DataSync document history](https://docs.aws.amazon.com/datasync/latest/userguide/doc-history.html)


