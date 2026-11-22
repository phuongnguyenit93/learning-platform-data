# Sao chép backup khác Region và AWS Backup Vault Lock

## Mục tiêu bài học

Trong hệ sinh thái CLOUD_PROVIDERS_AWS, khả năng khôi phục sau sự cố phụ thuộc vào việc có bản backup dùng được ở nơi độc lập với môi trường đang chạy. AWS Backup hỗ trợ sao chép recovery point sang AWS Region khác theo lịch hoặc theo yêu cầu. Bản sao tại Region đích được mã hóa bằng khóa của backup vault đích và có thể được dùng để khôi phục khi Region nguồn gặp sự cố.

AWS Backup Vault Lock bổ sung cơ chế bảo vệ bản backup khỏi thao tác xóa sớm hoặc thay đổi vòng đời ngoài chính sách. Hai chế độ Governance và Compliance đáp ứng mức độ kiểm soát khác nhau. Khi kết hợp copy khác Region với Vault Lock, tổ chức có thể xây dựng một bản sao dự phòng được lưu ở địa điểm khác và khó bị xóa bởi thao tác nhầm hoặc tài khoản bị xâm phạm.

Sau bài học, người học có thể:

- Giải thích mục đích của cross-Region backup copy và sự khác nhau giữa backup, copy, replication và restore.
- Thiết kế backup plan có copy action sang Region đích, với retention riêng.
- Kiểm tra khả năng hỗ trợ theo resource type và Region trước khi triển khai.
- Cấu hình backup vault, AWS KMS key và IAM role cho bản sao khác Region.
- Phân biệt Vault Lock Governance mode và Compliance mode.
- Thiết lập min/max retention, grace period và kiểm tra trạng thái khóa.
- Kết hợp cross-account copy, AWS Organizations và vault access policy khi cần tách tài khoản lưu trữ.
- Theo dõi copy job, kiểm tra lỗi và tổ chức restore testing để xác nhận khả năng phục hồi.
- Ước lượng chi phí, RPO/RTO và các rủi ro khi áp dụng retention bất biến.

## 1. Vì sao cần bản backup ở Region khác?

Backup trong cùng Region giúp phục hồi khi ứng dụng hoặc tài nguyên bị lỗi, bị xóa nhầm hay gặp sự cố ở cấp dịch vụ. Tuy nhiên, nếu một sự cố lớn ảnh hưởng tới toàn Region, cả workload và bản backup cùng Region có thể bị gián đoạn truy cập. Một bản copy ở Region khác tạo thêm lựa chọn phục hồi khi Region nguồn không còn khả dụng.

Ví dụ, một ứng dụng thương mại điện tử chạy tại ap-southeast-1 (Singapore). Nhóm vận hành lưu backup hằng ngày trong backup vault tại Region này và sao chép recovery point sang ap-southeast-2 (Sydney). Nếu Region nguồn gặp sự cố, nhóm có thể sử dụng bản copy tại Sydney để khôi phục tài nguyên theo kế hoạch DR.

Cross-Region copy giúp đáp ứng một số mục tiêu:

- **Khả năng phục hồi theo địa lý:** có bản backup ngoài Region vận hành chính.
- **Tuân thủ và lưu giữ:** giữ dữ liệu ở một địa điểm khác theo yêu cầu nội bộ hoặc pháp lý.
- **Giảm rủi ro do xóa nhầm:** nếu backup nguồn bị xóa, bản copy độc lập ở Region đích có thể vẫn còn.
- **Tách biệt quyền quản trị:** kết hợp với cross-account backup để giới hạn quyền của tài khoản vận hành đối với bản lưu trữ.
- **Linh hoạt khôi phục:** chọn Region phù hợp với kế hoạch DR, vị trí người dùng và năng lực dịch vụ.

Cần phân biệt:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Backup | Recovery point được tạo từ tài nguyên tại một thời điểm hoặc khoảng thời gian | Snapshot RDS hằng ngày |
| Cross-Region copy | AWS Backup tạo một recovery point khác ở Region đích | Copy snapshot từ Singapore sang Sydney |
| Replication | Cơ chế đồng bộ dữ liệu hoặc thay đổi theo cách thức của dịch vụ | S3 Cross-Region Replication, RDS read replica |
| Restore | Tạo lại tài nguyên hoặc dữ liệu từ recovery point | Khôi phục database từ snapshot tại Region đích |

Cross-Region copy không đồng nghĩa với active-active hoặc failover tự động. Nó tạo bản backup để phục hồi. Đội vận hành vẫn cần triển khai hạ tầng, mạng, DNS, secret, quyền truy cập, capacity và kiểm thử ứng dụng ở Region DR.

## 2. RPO, RTO và chọn Region đích

Trước khi cấu hình backup plan, cần xác định mục tiêu phục hồi của từng workload.

- **Recovery Point Objective (RPO):** lượng dữ liệu tối đa mà tổ chức chấp nhận mất, thường tính bằng thời gian từ lần backup khả dụng gần nhất tới thời điểm sự cố.
- **Recovery Time Objective (RTO):** thời gian tối đa để đưa dịch vụ trở lại mức hoạt động được chấp nhận.
- **Retention:** thời gian lưu recovery point.
- **Copy lag:** khoảng thời gian từ khi backup nguồn hoàn tất đến khi bản copy ở Region đích hoàn tất và có thể sử dụng.

Ví dụ, nếu RPO là 24 giờ, backup hằng ngày có thể là điểm khởi đầu. Nhưng nếu cần RPO 15 phút, chỉ backup hằng ngày là không đủ; cần xem xét continuous backup/PITR hoặc cơ chế replication phù hợp với dịch vụ. Nếu RTO là 2 giờ, chỉ có snapshot ở Region đích cũng chưa chắc đáp ứng vì còn thời gian provision hạ tầng, restore dữ liệu, cấu hình ứng dụng và kiểm tra traffic.

Bảng lựa chọn ví dụ:

| Loại workload | Mục tiêu minh họa | Phương án cần đánh giá |
|---|---|---|
| Website nội dung ít thay đổi | RPO 24 giờ, RTO 8 giờ | Backup hằng ngày, copy khác Region, runbook restore |
| API thương mại điện tử | RPO 1 giờ, RTO 2 giờ | Backup thường xuyên hơn, copy khác Region, hạ tầng DR dựng sẵn một phần |
| Database giao dịch quan trọng | RPO vài phút, RTO dưới 1 giờ | PITR, native replication hoặc multi-Region database architecture; backup copy là lớp bảo vệ bổ sung |
| Hồ sơ cần lưu giữ dài hạn | RPO theo chính sách, retention nhiều năm | Backup plan, copy tới vault riêng, Vault Lock Compliance sau khi kiểm chứng |

Khi chọn Region đích, hãy đánh giá:

1. Khoảng cách địa lý và yêu cầu về nơi lưu trữ dữ liệu.
2. AWS service và resource type có hỗ trợ cross-Region copy ở cả hai Region hay không.
3. Khả năng opt-in Region và giới hạn của AWS partition.
4. Khả năng cung cấp instance class, storage, quota và địa chỉ mạng khi restore.
5. Chi phí lưu trữ, truyền dữ liệu và KMS key.
6. Mức độ độc lập về quyền quản trị và blast radius giữa Region nguồn và đích.

Không chọn Region chỉ vì gần nhất hoặc có giá lưu trữ thấp nhất. Region DR phải hỗ trợ đủ dịch vụ và dung lượng để chạy workload sau khi khôi phục.

## 3. AWS Backup cross-Region copy hoạt động thế nào?

AWS Backup có thể copy recovery point sang một hoặc nhiều Region khác theo hai cách:

- **On-demand copy:** người vận hành chọn recovery point và khởi chạy copy job khi cần.
- **Scheduled copy:** backup plan định nghĩa CopyActions để tự động copy mỗi khi backup rule tạo recovery point.

Khi copy sang Region mới lần đầu, AWS Backup thường thực hiện full copy. Với resource type hỗ trợ incremental backup, những lần copy tiếp theo tới cùng destination vault thường là incremental. Bản copy được mã hóa lại bằng KMS key của backup vault đích.

Có một ngoại lệ quan trọng với Amazon EBS: nếu copy snapshot sang vault sử dụng KMS key khác, copy có thể trở thành full copy thay vì incremental. Nếu liên tục copy tới cùng vault và cùng encryption key, các lần sau có thể tiếp tục incremental.

Cross-Region copy có các giới hạn:

- Không phải mọi resource type đều hỗ trợ copy. Cần kiểm tra cột Cross-Region backup trong bảng Feature availability by resource.
- Không phải mọi cặp Region đều hỗ trợ copy. Cần kiểm tra bảng Feature availability by AWS Region và trạng thái opt-in của tài khoản.
- AWS Backup không hỗ trợ copy recovery point đã lưu trong cold storage hoặc archive tier sang Region khác.
- Một số dịch vụ có điều kiện riêng. Ví dụ, RDS cross-Region copy có thể cần tạo sẵn option group tương ứng tại Region đích nếu source dùng custom option group với persistent options.
- AWS Backup không cam kết SLA về thời gian hoàn tất copy job. Thời gian phụ thuộc kích thước dữ liệu, dịch vụ nguồn, tải hệ thống và các điều kiện vận hành.

Một số resource type hỗ trợ continuous backup/PITR. Khi copy continuous recovery point sang Region khác, bản copy trở thành snapshot backup định kỳ; khả năng point-in-time restore không được giữ nguyên cho bản copy đó. Vì vậy, không giả định copy của PITR sẽ cho phép khôi phục đến mọi thời điểm như bản nguồn.

Trước khi triển khai, hãy lập ma trận:

| Resource type | Region nguồn | Region đích | Cross-Region support | Điều kiện đặc biệt |
|---|---|---|---|---|
| Amazon EBS | ap-southeast-1 | ap-southeast-2 | Kiểm tra bảng hỗ trợ | Đổi KMS key có thể làm copy full |
| Amazon RDS | ap-southeast-1 | ap-southeast-2 | Kiểm tra loại DB và Region | Kiểm tra option group, engine/version |
| Amazon S3 | ap-southeast-1 | ap-southeast-2 | Kiểm tra feature matrix | PITR/continuous copy trở thành snapshot |
| Amazon EFS | ap-southeast-1 | ap-southeast-2 | Kiểm tra loại file system | Kiểm tra lifecycle và restore support |
| Amazon Aurora | ap-southeast-1 | ap-southeast-2 | Kiểm tra cluster và Region | Một số copy là full backup |

Bảng trên là ví dụ để lập kế hoạch; trạng thái hỗ trợ thực tế phải lấy từ AWS Backup Feature availability tại thời điểm triển khai.

## 4. Tạo backup vault và KMS key ở Region đích

Backup vault là nơi AWS Backup lưu recovery points. Mỗi vault thuộc một AWS account và một Region. Khi copy recovery point sang Region đích, hãy tạo vault đích trước và chọn encryption key phù hợp.

Quy trình cơ bản:

1. Chọn Region DR.
2. Tạo customer managed KMS key tại Region đích nếu loại tài nguyên và yêu cầu mã hóa cần khóa này.
3. Tạo backup vault ở Region đích.
4. Chọn KMS key làm encryption key cho vault.
5. Thiết lập access policy, IAM role và Vault Lock theo yêu cầu.
6. Cấu hình copy action trỏ tới ARN của vault đích.

Ví dụ tạo vault ở ap-southeast-2:

~~~bash
aws backup create-backup-vault \
  --backup-vault-name dr-vault \
  --encryption-key-arn arn:aws:kms:ap-southeast-2:111122223333:key/12345678-1234-1234-1234-123456789012 \
  --region ap-southeast-2
~~~

ARN minh họa cần được thay bằng KMS key thực tế tại Region đích. KMS key là tài nguyên theo Region; key ở ap-southeast-1 không thể được tham chiếu như key của vault ở ap-southeast-2.

### 4.1. Hiểu cách mã hóa khi copy

AWS Backup sử dụng KMS key của destination vault để mã hóa bản copy đối với hầu hết loại tài nguyên. Tuy nhiên, cách chọn key phụ thuộc vào resource type và mức độ AWS Backup quản lý tài nguyên.

| Trường hợp | Khóa mã hóa của bản copy |
|---|---|
| Resource fully managed by AWS Backup | Có thể chọn customer managed key hoặc AWS Backup managed key của vault đích |
| Resource không fully managed by AWS Backup | Vault đích cần customer managed key hoặc AWS service managed key của dịch vụ sở hữu tài nguyên, tùy loại resource |
| Cross-account copy của resource không fully managed | Cần customer managed key có key policy cho phép tài khoản đích sử dụng |
| Copy sang Region khác | Dùng key thuộc Region đích |

Ví dụ, khi copy EC2/EBS backup, không thể mặc định dùng AWS Backup managed key aws/backup trong mọi trường hợp. Với resource không fully managed, có thể cần CMK hoặc AWS managed key của dịch vụ gốc như aws/ebs. Hãy kiểm tra bảng encryption support cho đúng resource type.

IAM role chạy backup/copy và KMS key policy phải cho phép các thao tác cần thiết. Các quyền thường liên quan gồm kms:CreateGrant, kms:GenerateDataKey và kms:Decrypt. Nếu key policy có Deny, cần kiểm tra điều kiện và allowlist role backup/restore. Một job có thể báo trạng thái thành công nhưng đối tượng cụ thể không được backup/restore như mong đợi nếu quyền KMS chưa đầy đủ; vì vậy cần kiểm tra chi tiết job và dữ liệu thực tế.

## 5. Tự động copy bằng Backup Plan

Backup plan định nghĩa lịch tạo recovery point, vault nguồn và lifecycle. Mỗi rule có thể có một hoặc nhiều CopyActions để đưa bản backup sang destination vault.

Ví dụ backup plan JSON tạo backup hằng ngày và copy sang Region DR:

~~~json
{
  "BackupPlanName": "DailyBackupWithDRCopy",
  "Rules": [
    {
      "RuleName": "DailyDatabaseBackup",
      "TargetBackupVaultName": "primary-vault",
      "ScheduleExpression": "cron(0 18 ? * * *)",
      "StartWindowMinutes": 60,
      "CompletionWindowMinutes": 240,
      "Lifecycle": {
        "DeleteAfterDays": 35
      },
      "CopyActions": [
        {
          "DestinationBackupVaultArn": "arn:aws:backup:ap-southeast-2:111122223333:backup-vault:dr-vault",
          "Lifecycle": {
            "DeleteAfterDays": 120
          }
        }
      ]
    }
  ]
}
~~~

Trong ví dụ:

- Backup nguồn được lưu trong primary-vault tại Region nơi plan được tạo.
- Lịch cron chạy mỗi ngày lúc 18:00 UTC.
- Backup nguồn có retention 35 ngày.
- Bản copy tại dr-vault có retention 120 ngày.
- Lifecycle của bản copy được khai báo riêng với lifecycle của recovery point nguồn.

Nếu destination vault có Vault Lock min retention 90 ngày và max retention 365 ngày, thời gian 120 ngày của copy phù hợp với giới hạn đó. Nếu copy retention ngắn hơn min hoặc dài hơn max, copy job sẽ thất bại.

Tạo backup plan:

~~~bash
aws backup create-backup-plan \
  --backup-plan file://backup-plan.json \
  --region ap-southeast-1
~~~

Sau khi tạo plan, cần gán tài nguyên vào backup plan bằng resource assignment hoặc tag-based selection. Backup plan không tự bảo vệ mọi tài nguyên trong tài khoản nếu chưa có assignment phù hợp.

### 5.1. Copy recovery point theo yêu cầu

Nếu cần copy một recovery point hiện có, có thể dùng StartCopyJob:

~~~bash
aws backup start-copy-job \
  --recovery-point-arn arn:aws:backup:ap-southeast-1:111122223333:recovery-point:EXAMPLE-RECOVERY-POINT \
  --source-backup-vault-name primary-vault \
  --destination-backup-vault-arn arn:aws:backup:ap-southeast-2:111122223333:backup-vault:dr-vault \
  --iam-role-arn arn:aws:iam::111122223333:role/AWSBackupDefaultServiceRole \
  --region ap-southeast-1
~~~

Lệnh cần dùng recovery point ARN và vault nguồn thực tế. IAM role phải có trust policy cho AWS Backup và quyền thực hiện copy. Sau khi gọi API, lưu CopyJobId để theo dõi trạng thái.

Không chạy lặp lệnh on-demand một cách tùy tiện. Nếu cần retry do timeout phía client, dùng idempotency token phù hợp khi gọi API StartCopyJob trực tiếp để tránh tạo các yêu cầu trùng lặp.

## 6. Cross-account copy và tách biệt tài khoản lưu trữ

Một bản copy ở Region khác giúp tách biệt địa lý. Để tăng khả năng chống xâm phạm tài khoản nguồn, có thể copy tiếp sang tài khoản backup riêng trong AWS Organizations.

Ví dụ mô hình:

~~~mermaid
flowchart LR
    subgraph PROD["Production account"]
      A[Application resources]
      B[Primary backup vault]
      A --> B
    end
    subgraph DR["Backup account"]
      C[DR backup vault]
      D[Vault Lock Compliance]
      C --> D
    end
    B -->|Cross-Region / cross-account copy| C
    C --> E[Restore in DR account and Region]
~~~

Để thiết lập cross-account copy:

1. Hai tài khoản phải thuộc cùng AWS Organizations organization.
2. Management account phải bật tính năng cross-account backup.
3. Tạo backup vault trong destination account và Region đích.
4. Cấu hình encryption key cho destination vault.
5. Gắn resource-based access policy cho vault đích, cho phép backup:CopyIntoBackupVault.
6. IAM role phía nguồn cần quyền backup:CopyFromBackupVault và backup:CopyIntoBackupVault.
7. Nếu resource nguồn được mã hóa bằng customer managed KMS key, chia sẻ quyền sử dụng key cho destination account theo chính sách phù hợp.
8. Giới hạn tài khoản và vault được phép nhận bản copy bằng IAM, vault access policy và SCP.

Default backup vault không thể dùng làm destination vault cho cross-account copy vì khóa mặc định của vault không thể chia sẻ giữa các tài khoản. Nên tạo vault riêng với encryption key được quản trị rõ ràng.

Đối với resource fully managed by AWS Backup, destination vault có thể dùng customer managed key hoặc AWS Backup managed key theo hỗ trợ dịch vụ. Với các resource khác, destination vault cần CMK vì AWS managed key không thể chia sẻ cross-account. Cần kiểm tra encryption documentation cho từng resource type.

AWS Backup hỗ trợ copy khác account trong cùng organization. Nếu destination account rời organization sau đó, tài khoản đích vẫn giữ backup đã nhận. Tổ chức nên kiểm soát quyền organizations:LeaveOrganization bằng SCP nếu chính sách yêu cầu tài khoản lưu trữ luôn thuộc organization. Cũng cần giới hạn các tài khoản có thể copy vào vault đích để tránh biến vault thành nơi nhận backup ngoài dự kiến.

## 7. AWS Backup Vault Lock là gì?

AWS Backup Vault Lock là tính năng WORM (write once, read many) áp dụng cho backup vault. Khi recovery point nằm trong vault đã khóa, các thao tác xóa hoặc thay đổi lifecycle trái với retention policy sẽ bị AWS Backup từ chối.

Vault Lock giúp:

- Ngăn người dùng xóa recovery point trước thời hạn lưu giữ.
- Bảo vệ backup trước thao tác nhầm hoặc tài khoản có quyền cao bị xâm phạm.
- Thực thi retention tối thiểu và tối đa cho backup/copy job mới.
- Tạo lớp bảo vệ bổ sung cho yêu cầu lưu trữ dài hạn và kiểm toán.

Mỗi backup vault chỉ có thể có một Vault Lock. Vault Lock không phải là Amazon S3 Object Lock hay Amazon Glacier Vault Lock; đây là cơ chế riêng của AWS Backup.

Có hai chế độ:

| Đặc điểm | Governance mode | Compliance mode |
|---|---|---|
| Mục tiêu | Quản trị có kiểm soát | Lưu giữ bất biến theo chính sách |
| Ai có thể gỡ lock? | Principal có IAM permissions phù hợp | Không ai sau khi hết grace period |
| Có grace period? | Không | Có |
| Thời gian grace | Không áp dụng | Tối thiểu 3 ngày (72 giờ), tối đa 36.500 ngày |
| Sau khi lock có hiệu lực | Có thể thay đổi bởi principal đủ quyền | Vault lock trở nên immutable |
| Phù hợp | Quy trình backup cần quản trị linh hoạt | Hồ sơ cần chống xóa hoặc sửa trong thời gian lưu giữ |

### 7.1. Governance mode

Governance mode giới hạn việc thay đổi vault cho các principal có quyền IAM phù hợp. Người có quyền cao vẫn có thể gỡ hoặc cập nhật Vault Lock. Chế độ này phù hợp khi tổ chức muốn có quy trình phê duyệt và tách quyền, nhưng vẫn cần khả năng điều chỉnh retention khi chính sách thay đổi.

Governance mode không phải bảo đảm bất biến trước mọi administrator hoặc root user. Nếu tài khoản bị chiếm quyền và attacker có đủ IAM permissions, họ có thể gỡ lock. Hãy kết hợp IAM least privilege, SCP, tách tài khoản backup và giám sát CloudTrail.

### 7.2. Compliance mode

Compliance mode hướng tới yêu cầu WORM nghiêm ngặt. Khi tạo lock, cần đặt ChangeableForDays làm grace period. Trong thời gian grace, có thể điều chỉnh hoặc xóa lock. Sau khi grace period hết hạn, vault lock trở thành immutable và không thể thay đổi hoặc gỡ bởi bất kỳ user nào, kể cả root user hoặc AWS.

Nếu vault còn recovery points, vault không thể bị xóa sau khi Compliance mode đã khóa bất biến. Nếu vault rỗng, có thể xóa vault theo điều kiện của AWS Backup.

Compliance mode phù hợp khi retention đã được phê duyệt và không còn cần thay đổi. Không bật chế độ này trên vault production trước khi kiểm thử lifecycle, restore, KMS, policy và chi phí.

## 8. Min retention, max retention và grace period

Vault Lock có thể cấu hình hai giới hạn thời gian:

- **MinRetentionDays:** số ngày lưu giữ tối thiểu. Backup hoặc copy job mới có retention ngắn hơn giá trị này sẽ thất bại.
- **MaxRetentionDays:** số ngày lưu giữ tối đa. Backup hoặc copy job mới có retention dài hơn giá trị này sẽ thất bại.
- **ChangeableForDays:** thời gian grace của Compliance mode. Khi khai báo tham số này, Vault Lock được tạo ở Compliance mode.

Các giá trị:

| Thuộc tính | Giới hạn |
|---|---|
| MinRetentionDays | Tối thiểu 1 ngày |
| MaxRetentionDays | Tối đa 36.500 ngày |
| ChangeableForDays | Từ 3 đến 36.500 ngày |

MinRetentionDays và MaxRetentionDays là tùy chọn trong API, nhưng MinRetentionDays là bắt buộc trong một số cách khai báo CloudFormation. Nếu không cấu hình max retention, Vault Lock không giới hạn thời gian tối đa; recovery point có retention Always có thể được giữ vô thời hạn.

Một điểm quan trọng: min/max retention của Vault Lock không tự thay đổi retention của recovery points đã tồn tại trước khi tạo lock. Các recovery point cũ tiếp tục theo lifecycle được định nghĩa lúc tạo. Giới hạn min/max áp dụng cho backup và copy job mới sau khi Vault Lock được cấu hình.

Ví dụ chính sách:

- Destination vault chỉ nhận backup có retention từ 90 đến 365 ngày.
- Copy action của backup plan đặt DeleteAfterDays là 120.
- Backup job mới có retention 30 ngày sẽ bị từ chối khi ghi vào vault này.
- Copy job có retention 400 ngày cũng bị từ chối.
- Recovery point đã có trong vault trước khi lock được tạo không tự động đổi thành 90 hoặc 365 ngày.

Nếu dùng Compliance mode, hãy kiểm tra kỹ mọi lifecycle trong backup plan, copy action và các backup plan do Organizations quản lý trước khi bắt đầu grace period. Nếu có job đặt retention Always hoặc thời hạn quá dài, recovery point có thể không bao giờ được xóa và tạo chi phí lưu trữ kéo dài.

## 9. Tạo Vault Lock bằng AWS CLI

Ví dụ tạo Governance mode với retention từ 90 đến 365 ngày:

~~~bash
aws backup put-backup-vault-lock-configuration \
  --backup-vault-name dr-vault \
  --min-retention-days 90 \
  --max-retention-days 365 \
  --region ap-southeast-2
~~~

Không truyền ChangeableForDays thì Vault Lock được tạo ở Governance mode.

Ví dụ tạo Compliance mode với grace period 7 ngày:

~~~bash
aws backup put-backup-vault-lock-configuration \
  --backup-vault-name dr-vault \
  --changeable-for-days 7 \
  --min-retention-days 90 \
  --max-retention-days 365 \
  --region ap-southeast-2
~~~

Trong ví dụ, sau khi tạo lock, tổ chức có 7 ngày để kiểm tra và điều chỉnh cấu hình. Sau thời điểm này, Vault Lock trở nên bất biến. Grace period tối thiểu là 3 ngày; chọn 7 ngày chỉ là ví dụ, không phải mặc định bắt buộc.

Kiểm tra cấu hình vault:

~~~bash
aws backup describe-backup-vault \
  --backup-vault-name dr-vault \
  --region ap-southeast-2
~~~

Các trường quan trọng gồm:

- Locked: cho biết Vault Lock đã được áp dụng.
- MinRetentionDays: retention tối thiểu.
- MaxRetentionDays: retention tối đa.
- LockDate: thời điểm UTC kết thúc grace period và lock trở nên bất biến.
- NumberOfRecoveryPoints: số recovery points trong vault.

Nếu đang trong grace period và phát hiện sai cấu hình, có thể cập nhật bằng PutBackupVaultLockConfiguration hoặc xóa lock bằng DeleteBackupVaultLockConfiguration. Sau khi grace period hết, không thể thay đổi hay gỡ Compliance mode lock.

Không đưa các lệnh này vào pipeline tự động mà không có phê duyệt change management. Đặc biệt, lệnh tạo Compliance mode có thể tạo ra ràng buộc không thể đảo ngược sau grace period.

## 10. Kết hợp cross-Region copy với Vault Lock

Một kiến trúc tham khảo:

1. Tạo backup plan tại Region nguồn.
2. Tạo backup vault ở Region nguồn và Region đích.
3. Tạo KMS key phù hợp tại từng Region.
4. Tạo copy action trỏ tới destination vault.
5. Kiểm tra copy job thành công và recovery point xuất hiện ở Region đích.
6. Kiểm thử restore từ Region đích.
7. Đặt Vault Lock Governance mode trong giai đoạn đầu nếu cần thử nghiệm.
8. Kiểm tra retention, restore, chi phí, quyền và quy trình vận hành.
9. Sau khi chính sách được phê duyệt, chuyển destination vault sang Compliance mode trong một thay đổi có kiểm soát.
10. Giám sát copy jobs và restore tests liên tục.

Sơ đồ:

~~~mermaid
flowchart TD
    A[Production resources] --> B[Backup plan]
    B --> C[Primary backup vault]
    C --> D[Copy job]
    D --> E[Destination vault in another Region]
    E --> F[Vault Lock]
    F --> G[Immutable recovery points after grace period]
    G --> H[Restore test]
    H --> I[DR workload]
    D --> J[EventBridge copy job event]
    J --> K[Alarm, ticket and operations]
~~~

Nếu copy action đặt retention 120 ngày, destination Vault Lock có min 90 và max 365 ngày thì copy job đáp ứng giới hạn. Nếu backup plan thay đổi retention xuống 30 ngày, copy action sẽ không còn phù hợp và job có thể thất bại. Do đó, thay đổi backup plan phải được kiểm tra cùng retention policy của vault đích.

Vault Lock bảo vệ recovery point trong vault qua AWS Backup. Tuy nhiên, với một số loại tài nguyên, các thao tác trực tiếp qua API dịch vụ nguồn có thể nằm ngoài phạm vi Vault Lock hoặc vault access policy. Ví dụ, EBS snapshot có thể được chia sẻ hoặc chuyển storage tier qua EC2 APIs như ModifySnapshotAttribute và ModifySnapshotTier. Nếu cần ngăn các thao tác này, hãy bổ sung IAM/SCP Deny có ngoại lệ thích hợp cho role mà AWS Backup dùng, vì AWS Backup cũng cần các quyền này để thực hiện cross-account copy hoặc cold storage transition.

Ngoài ra, một AMI bị disable có thể làm gián đoạn restore dù recovery point vẫn tồn tại trong locked vault. Cần bảo vệ các thao tác như ec2:DisableImage theo chính sách IAM/SCP phù hợp.

## 11. Giám sát backup và copy jobs

AWS Backup gửi sự kiện trạng thái backup, copy và restore job tới Amazon EventBridge. EventBridge nhận các sự kiện này theo cơ chế best effort, thường mỗi 5 phút. Không nên dựa duy nhất vào một event để chứng minh backup đã hoàn tất; hãy đối chiếu với AWS Backup API hoặc console.

Các trạng thái copy job thường gặp:

| Trạng thái | Ý nghĩa |
|---|---|
| CREATED | Job đã được tạo |
| RUNNING | Đang thực hiện copy |
| COMPLETED | Copy hoàn tất |
| FAILED | Copy thất bại |

Có thể lọc copy job failure bằng EventBridge event pattern:

~~~json
{
  "source": [
    "aws.backup"
  ],
  "detail-type": [
    "Copy Job State Change"
  ],
  "detail": {
    "state": [
      "FAILED"
    ]
  }
}
~~~

Rule có thể gửi thông báo tới SNS, tạo ticket, gọi Lambda hoặc chuyển sự kiện tới hệ thống vận hành. Nên bao gồm account, Region, resource ARN, source vault, destination vault, copy job ID và status message trong ticket.

Theo dõi thêm:

- Tỷ lệ backup job và copy job thành công.
- Thời gian từ backup completion đến copy completion.
- Tuổi của recovery point gần nhất ở Region đích.
- Số recovery point trong destination vault.
- Copy job failure theo resource type, Region và KMS key.
- Tỷ lệ restore test thành công.
- Chi phí lưu trữ warm/cold và chi phí chuyển dữ liệu.

Có thể xem job bằng CLI:

~~~bash
aws backup list-copy-jobs \
  --by-state FAILED \
  --region ap-southeast-1
~~~

Xem chi tiết một copy job:

~~~bash
aws backup describe-copy-job \
  --copy-job-id COPY_JOB_ID \
  --region ap-southeast-1
~~~

Copy job không có SLA hoàn tất. Nếu copy job kéo dài hơn kỳ vọng, cần kiểm tra trạng thái, resource type, dung lượng dữ liệu, KMS permissions, service quotas và các thông báo lỗi.

## 12. Restore testing và diễn tập DR

Một backup hoặc copy job thành công chỉ chứng minh recovery point đã được tạo. Nó chưa chứng minh ứng dụng có thể hoạt động sau khi restore.

AWS Backup Restore Testing hỗ trợ lập lịch kiểm thử restore từ recovery points được chọn. Có thể chọn source vault, khoảng thời gian recovery point, tần suất kiểm thử và resource selection. Khi thiết kế DR, hãy kiểm thử recovery point tại Region đích để xác nhận bản copy thực sự dùng được.

Một quy trình restore test:

1. Chọn recovery point trong destination vault.
2. Chạy restore test vào môi trường cô lập hoặc VPC kiểm thử.
3. Xác nhận tài nguyên được tạo thành công.
4. Kiểm tra dữ liệu, schema, encryption, IAM role, security group và cấu hình mạng.
5. Khởi chạy ứng dụng phụ thuộc vào tài nguyên đã restore.
6. Chạy smoke test và kiểm tra tính toàn vẹn dữ liệu.
7. Ghi lại thời gian restore, lỗi và RTO thực tế.
8. Dọn dẹp tài nguyên kiểm thử theo quy trình và giữ báo cáo.

Ví dụ, khôi phục database RDS từ bản copy tại Region DR. Sau khi restore, nhóm cần kiểm tra engine version, parameter group, option group, subnet group, security group, secrets, endpoint cấu hình trong ứng dụng và quyền truy cập. Snapshot có thể tồn tại nhưng ứng dụng không khởi động được nếu thiếu các dependency này.

Restore testing plan có thể chọn recovery point mới nhất hoặc một recovery point ngẫu nhiên trong khoảng thời gian đã chỉ định. Thử nghiệm ngẫu nhiên hữu ích để kiểm tra khả năng khôi phục từ nhiều thời điểm khác nhau. Nếu cần xác nhận RTO, đo cả thời gian provision, restore, cấu hình và xác minh nghiệp vụ, không chỉ thời gian AWS Backup báo restore job completed.

Sau mỗi lần diễn tập, cập nhật runbook, danh sách dependency, quota DR và ước lượng RTO/RPO thực tế.

## 13. Xử lý lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Copy job không được tạo | Resource type hoặc Region không hỗ trợ | Kiểm tra Feature availability by resource và by Region |
| Copy job FAILED do AccessDenied | IAM role thiếu quyền hoặc trust policy sai | Kiểm tra role của AWS Backup và action cần thiết |
| Copy job FAILED do KMS | Key policy thiếu CreateGrant/GenerateDataKey/Decrypt hoặc có Deny | Kiểm tra IAM policy, KMS key policy và grants |
| Destination vault không nhận bản copy | ARN vault sai, vault không tồn tại hoặc Region/account sai | Kiểm tra destination vault ARN và account/Region |
| Copy bị từ chối do retention | Lifecycle ngắn hơn MinRetentionDays hoặc dài hơn MaxRetentionDays | Đồng bộ retention của copy action với Vault Lock |
| Copy không incremental | EBS copy dùng KMS key khác hoặc resource không hỗ trợ incremental | Kiểm tra resource type và key ở destination vault |
| Copy cold-tier không chạy | Recovery point nguồn đã ở cold/archive tier | Copy trước khi chuyển cold hoặc dùng native feature phù hợp |
| RDS copy thất bại với option group | Region đích thiếu custom option group cần thiết | Tạo option group tương ứng trước khi copy |
| Restore job thất bại | Thiếu service-linked role, quota, subnet hoặc KMS access | Kiểm tra restore metadata, role và cấu hình Region đích |
| Vault Lock không thể gỡ | Compliance grace period đã hết | Kiểm tra LockDate và chế độ lock trước khi thay đổi |
| Vault không thể xóa | Compliance lock còn recovery points | Xác minh retention và chính sách lưu giữ |
| Storage cost tăng bất thường | Recovery point retention quá dài hoặc Always | Kiểm tra lifecycle, Min/Max retention và số recovery points |

Khi xử lý lỗi, hãy ghi lại BackupJobId, CopyJobId hoặc RestoreJobId, recovery point ARN, account, Region, resource type và status message. Không xóa backup hoặc thay đổi retention để thử sửa lỗi khi vault đã bị Compliance lock.

## 14. Bảo mật và phân quyền

Một kiến trúc backup an toàn cần tách biệt quyền tạo backup, copy, restore, quản trị vault và thay đổi retention.

Các nguyên tắc:

- Dùng IAM role riêng cho AWS Backup với trust policy cho backup.amazonaws.com.
- Cấp quyền tối thiểu theo resource type, vault và Region.
- Tách quyền tạo backup khỏi quyền xóa recovery point.
- Giới hạn ai được gọi PutBackupVaultLockConfiguration, DeleteBackupVaultLockConfiguration và DeleteRecoveryPoint.
- Dùng destination account riêng nếu cần giảm blast radius.
- Bảo vệ KMS key policy và kiểm soát quyền tạo grant.
- Dùng SCP hoặc vault access policy để giới hạn thao tác phá hủy.
- Ghi lại các thay đổi qua CloudTrail.
- Kiểm tra restore permission riêng; quyền tạo backup không tự động bảo đảm có thể restore.

Vault Lock chỉ kiểm soát hành vi qua AWS Backup theo phạm vi tính năng. Hãy kiểm tra các API trực tiếp của dịch vụ sở hữu resource để đảm bảo không có đường vòng ngoài ý muốn. Với EBS, cần xem xét quyền chia sẻ snapshot và thay đổi storage tier. Với AMI, cần ngăn thao tác disable nếu nó có thể ảnh hưởng restore.

## 15. Chi phí và tối ưu hóa

Cross-Region copy tạo chi phí bổ sung so với chỉ giữ backup ở Region nguồn. Các khoản cần xem xét:

- Storage charges của recovery point tại Region nguồn.
- Storage charges của bản copy tại Region đích.
- Data transfer hoặc copy charges theo bảng giá của dịch vụ và Region.
- KMS key usage và các thao tác mã hóa/giải mã.
- Chi phí cold storage nếu resource type hỗ trợ và lifecycle chuyển tier.
- Chi phí restore test và tài nguyên được tạo trong quá trình kiểm thử.
- Chi phí vận hành của môi trường DR nếu duy trì compute, database hoặc network sẵn sàng.

AWS Backup Vault Lock không có phụ phí riêng, nhưng storage charges vẫn áp dụng cho recovery points trong vault đã khóa. Do không thể xóa sớm recovery point, cấu hình retention sai có thể tạo chi phí kéo dài. Đặc biệt, retention Always trong Compliance mode có thể khiến dữ liệu được giữ vô thời hạn.

Biện pháp tối ưu:

1. Phân loại workload theo RPO, RTO và retention.
2. Chỉ copy những resource type và dữ liệu cần thiết cho DR hoặc compliance.
3. Dùng retention khác nhau cho operational backup và long-term backup.
4. Kiểm tra incremental copy và tác động của KMS key tới EBS.
5. Dùng cold storage khi resource type hỗ trợ và thời gian lưu đủ điều kiện.
6. Đặt lifecycle phù hợp với MinRetentionDays/MaxRetentionDays.
7. Theo dõi số lượng recovery point và chi phí theo Region, account, vault.
8. Kiểm thử restore theo lịch để tránh lưu bản backup không thể dùng.

## 16. Bài thực hành: bảo vệ database bằng bản copy khác Region

Một hệ thống bán hàng chạy RDS tại ap-southeast-1. Tổ chức yêu cầu giữ backup 35 ngày tại Region chính, có bản copy 120 ngày ở ap-southeast-2 và bảo vệ bản copy khỏi xóa trước hạn.

Thiết kế đề xuất:

| Thành phần | Cấu hình minh họa |
|---|---|
| Region nguồn | ap-southeast-1 |
| Region DR | ap-southeast-2 |
| Source vault | primary-vault |
| Destination vault | dr-vault |
| Source retention | 35 ngày |
| Copy retention | 120 ngày |
| Vault Lock min retention | 90 ngày |
| Vault Lock max retention | 365 ngày |
| Vault Lock mode | Compliance sau giai đoạn thử nghiệm |
| Grace period | 7 ngày |
| Restore test | Hằng tháng |

Các bước:

1. Xác nhận loại RDS engine, version và Region đích được AWS Backup hỗ trợ copy.
2. Tạo KMS key và dr-vault ở ap-southeast-2.
3. Cấu hình quyền IAM/KMS cho backup và copy.
4. Tạo backup plan với backup rule hằng ngày và CopyActions có DeleteAfterDays 120.
5. Chạy thử backup và copy job, xác minh recovery point ở dr-vault.
6. Restore thử database tại Region đích và kiểm tra ứng dụng.
7. Tạo Vault Lock Governance mode trong giai đoạn đầu hoặc kiểm tra retention ở một vault thử nghiệm.
8. Xác nhận không có backup/copy job nào vi phạm retention.
9. Khi chính sách được phê duyệt, tạo Compliance mode lock với grace period 7 ngày.
10. Trong grace period, theo dõi LockDate, job status và chi phí.
11. Sau khi lock bất biến, tiếp tục giám sát copy jobs và restore testing.

Tình huống kiểm tra:

- Backup nguồn hoàn tất nhưng copy job FAILED do KMS key policy.
- Copy action có retention 60 ngày trong khi destination vault yêu cầu tối thiểu 90 ngày.
- Nhóm vận hành muốn xóa recovery point trước hạn.
- RDS restore thành công nhưng ứng dụng không kết nối được do security group.
- Copy job kéo dài hơn kỳ vọng và không có SLA hoàn tất.
- Destination Region thiếu option group hoặc quota DB instance.

Học viên cần xác định bước điều tra, dữ liệu cần thu thập, vai trò chịu trách nhiệm và cách khôi phục an toàn cho từng tình huống.

## Kết luận

AWS Backup cross-Region copy tạo recovery point ở một Region khác để hỗ trợ khôi phục khi Region nguồn gặp sự cố. Copy có thể được thực hiện theo yêu cầu hoặc tự động qua CopyActions trong backup plan. Khả năng hỗ trợ, mã hóa, incremental behavior và lifecycle phụ thuộc resource type, Region và KMS key của vault đích.

AWS Backup Vault Lock bảo vệ recovery points khỏi xóa sớm và thực thi retention tối thiểu/tối đa cho backup/copy job mới. Governance mode cho phép principal đủ quyền thay đổi lock; Compliance mode trở nên bất biến sau grace period tối thiểu 72 giờ. Trước khi dùng Compliance mode, phải kiểm tra retention, lifecycle, restore, quyền và chi phí.

Một thiết kế DR đáng tin cậy cần kết hợp bản copy khác Region, vault được bảo vệ, mã hóa KMS, IAM least privilege, giám sát copy job và restore testing định kỳ. Chỉ khi restore test thành công và ứng dụng đáp ứng RPO/RTO thì bản backup mới chứng minh được giá trị phục hồi.

## Tài liệu tham khảo

- [Creating backup copies across AWS Regions](https://docs.aws.amazon.com/aws-backup/latest/devguide/cross-region-backup.html)
- [Backup and tag copy](https://docs.aws.amazon.com/aws-backup/latest/devguide/recov-point-create-a-copy.html)
- [AWS Backup feature availability](https://docs.aws.amazon.com/aws-backup/latest/devguide/backup-feature-availability.html)
- [Encryption for backups in AWS Backup](https://docs.aws.amazon.com/aws-backup/latest/devguide/encryption.html)
- [AWS Backup Vault Lock](https://docs.aws.amazon.com/aws-backup/latest/devguide/vault-lock.html)
- [Creating backup copies across AWS accounts](https://docs.aws.amazon.com/aws-backup/latest/devguide/create-cross-account-backup.html)
- [Managing AWS Backup resources across multiple AWS accounts](https://docs.aws.amazon.com/aws-backup/latest/devguide/manage-cross-account.html)
- [Vault access policies](https://docs.aws.amazon.com/aws-backup/latest/devguide/create-vault-access-policy.html)
- [CreateBackupPlan API and CopyActions](https://docs.aws.amazon.com/aws-backup/latest/devguide/API_CreateBackupPlan.html)
- [StartCopyJob API](https://docs.aws.amazon.com/aws-backup/latest/APIReference/API_StartCopyJob.html)
- [Monitoring AWS Backup events using Amazon EventBridge](https://docs.aws.amazon.com/aws-backup/latest/devguide/eventbridge.html)
- [AWS Backup monitoring](https://docs.aws.amazon.com/aws-backup/latest/devguide/monitoring.html)
- [AWS Backup Restore Testing](https://docs.aws.amazon.com/aws-backup/latest/devguide/restore-testing.html)
- [AWS Backup pricing](https://aws.amazon.com/backup/pricing/)

