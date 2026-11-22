# DeletionPolicy, UpdateReplacePolicy và bảo vệ tài nguyên dữ liệu

Một stack AWS CloudFormation đang quản lý hệ thống bán hàng: Amazon S3 lưu hóa đơn, Amazon DynamoDB lưu đơn hàng và Amazon RDS lưu dữ liệu thanh toán. Sau vài tháng, nhóm phát triển cần đổi cấu hình database, tách stack hoặc loại bỏ một resource không còn dùng. Một thao tác cập nhật tưởng như nhỏ có thể khiến CloudFormation thay thế resource và xóa physical resource cũ. Nếu không thiết kế chính sách vòng đời, dữ liệu quan trọng có thể biến mất cùng stack hoặc trong lúc update.

CloudFormation cung cấp hai thuộc tính để quyết định điều gì xảy ra với resource khi resource bị xóa hoặc bị thay thế:

- **DeletionPolicy** quyết định CloudFormation xử lý resource như thế nào khi xóa stack hoặc khi resource bị loại khỏi template trong một stack update.
- **UpdateReplacePolicy** quyết định CloudFormation xử lý physical resource cũ như thế nào khi một thay đổi buộc resource phải được thay thế bằng physical resource mới.

Hai thuộc tính này là lớp bảo vệ vòng đời ở cấp template. Để bảo vệ dữ liệu production, cần kết hợp chúng với backup/PITR, versioning, deletion protection, stack policy, termination protection và IAM.

Bài học thuộc chương **Hạ tầng dưới dạng mã** của module **CLOUD_PROVIDERS_AWS**. Nội dung tập trung vào cách dự đoán hành vi CloudFormation, chọn policy cho S3/DynamoDB/RDS/EBS, đọc change set, xử lý resource được retain và thiết kế quy trình thay đổi an toàn.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích sự khác nhau giữa DeletionPolicy và UpdateReplacePolicy.
2. Nhận biết ba tình huống: xóa stack, bỏ resource khỏi template và thay thế resource khi update.
3. Chọn Delete, Retain, RetainExceptOnCreate hoặc Snapshot đúng ngữ cảnh.
4. Hiểu vì sao Snapshot chỉ áp dụng cho một số loại resource.
5. Cấu hình policy cho S3 bucket, DynamoDB table và RDS DB instance.
6. Giải thích tác động của retained resource đối với CloudFormation ownership và chi phí.
7. Kết hợp policy với RDS deletion protection, DynamoDB PITR, S3 Versioning/Object Lock và EBS snapshots.
8. Phân biệt stack policy, termination protection và IAM.
9. Dùng change set để nhận diện replacement trước khi triển khai.
10. Lập quy trình backup, update, rollback và phục hồi khi có nguy cơ mất dữ liệu.

## 2. CloudFormation quản lý logical resource và physical resource

Trong template, bạn khai báo một resource bằng logical ID, ví dụ ProductionDatabase. Khi tạo stack, CloudFormation tạo resource thật trên AWS và gắn một physical ID cho nó, chẳng hạn DB instance identifier hoặc bucket name.

Cần phân biệt:

- **Logical ID:** tên resource trong template, được các resource khác tham chiếu.
- **Physical resource:** tài nguyên thực tế tồn tại trong AWS.
- **Physical ID:** định danh của tài nguyên thực tế.
- **Stack ownership:** quan hệ quản lý giữa resource và CloudFormation stack.

Khi update template, CloudFormation so sánh template mới với trạng thái stack. Tùy thuộc thuộc tính được thay đổi, resource có thể được cập nhật tại chỗ hoặc phải thay thế.

Nếu update tại chỗ, physical ID thường được giữ nguyên. Nếu thay thế, CloudFormation tạo resource mới với physical ID mới, cập nhật tham chiếu phụ thuộc rồi xử lý resource cũ theo UpdateReplacePolicy.

Nếu resource được Retain, nó vẫn tồn tại trong AWS nhưng bị loại khỏi phạm vi quản lý của stack. Việc giữ resource không có nghĩa CloudFormation tiếp tục quản lý nó.

## 3. Ba tình huống vòng đời cần phân biệt

| Tình huống | CloudFormation thực hiện | Policy chi phối |
|---|---|---|
| Xóa toàn bộ stack | Xóa các resource thuộc stack theo chính sách của chúng | DeletionPolicy |
| Xóa một resource khỏi template rồi update stack | Resource không còn được khai báo trong template mới | DeletionPolicy |
| Thay đổi property yêu cầu Replacement | Tạo resource mới, chuyển tham chiếu, xử lý resource cũ | UpdateReplacePolicy |
| Thay đổi property được cập nhật tại chỗ | Cập nhật resource hiện tại | Không policy nào trong hai policy này được kích hoạt |

Điểm dễ nhầm nhất là **DeletionPolicy không bảo vệ resource cũ trong một thao tác replacement**. Nếu thuộc tính thay đổi yêu cầu Replacement, hãy dùng UpdateReplacePolicy.

Ngược lại, UpdateReplacePolicy không quyết định điều gì xảy ra khi xóa stack. Khi xóa stack, CloudFormation dùng DeletionPolicy.

## 4. DeletionPolicy

DeletionPolicy là thuộc tính đặt trực tiếp trên resource trong template. Nó kiểm soát việc giữ lại, tạo snapshot hoặc xóa resource khi CloudFormation xóa stack hay loại resource khỏi template trong một stack update.

Ví dụ giữ một S3 bucket khi stack bị xóa:

    Resources:
      InvoiceBucket:
        Type: AWS::S3::Bucket
        DeletionPolicy: Retain

Khi stack deletion hoàn tất, bucket vẫn tồn tại. Khi một update loại InvoiceBucket khỏi template, CloudFormation cũng giữ bucket và xóa resource đó khỏi phạm vi quản lý của stack.

### 4.1. Các giá trị của DeletionPolicy

| Giá trị | Hành vi | Khi phù hợp |
|---|---|---|
| Delete | Xóa physical resource | Resource tạm thời, dữ liệu có thể tái tạo |
| Retain | Giữ resource và nội dung, loại khỏi stack | Bucket, database hoặc tài nguyên cần sống lâu hơn stack |
| RetainExceptOnCreate | Giống Retain, ngoại trừ rollback của thao tác tạo ban đầu | Resource mới được tạo nhưng stack create thất bại |
| Snapshot | Tạo snapshot trước khi xóa, nếu resource hỗ trợ | Volume/database cần bản backup tại thời điểm xóa |

Nếu không khai báo DeletionPolicy, mặc định là Delete, ngoại trừ:

- AWS::RDS::DBCluster mặc định dùng Snapshot.
- AWS::RDS::DBInstance không khai báo DBClusterIdentifier mặc định dùng Snapshot.

Không nên dựa vào ngoại lệ mặc định cho resource dữ liệu production. Khai báo policy tường minh giúp người review hiểu ý định và tránh phụ thuộc vào default khác nhau giữa các loại resource.

### 4.2. RetainExceptOnCreate

RetainExceptOnCreate hữu ích khi template tạo một resource dữ liệu mới nhưng stack create có thể rollback.

Ví dụ, pipeline tạo stack mới và provision một bucket. Nếu quá trình create thất bại, bucket vừa tạo có thể rỗng và không được ứng dụng sử dụng. Nếu dùng Retain, bucket có thể bị giữ lại sau rollback, tạo resource mồ côi. RetainExceptOnCreate cho phép CloudFormation xóa resource trong rollback của chính thao tác create ban đầu, nhưng giữ resource trong các stack operations khác.

    Resources:
      NewImportBucket:
        Type: AWS::S3::Bucket
        DeletionPolicy: RetainExceptOnCreate

RetainExceptOnCreate là một giá trị của DeletionPolicy; nó không phải giá trị của UpdateReplacePolicy.

### 4.3. Snapshot

Snapshot tạo bản chụp dữ liệu của resource trước khi CloudFormation xóa resource. Snapshot tồn tại độc lập sau khi stack deletion hoàn tất và tiếp tục phát sinh chi phí lưu trữ cho đến khi được xóa.

DeletionPolicy Snapshot hiện hỗ trợ các loại resource được AWS liệt kê như:

- AWS::DocDB::DBCluster
- AWS::EC2::Volume
- AWS::ElastiCache::CacheCluster
- AWS::ElastiCache::ReplicationGroup
- AWS::Neptune::DBCluster
- AWS::RDS::DBCluster
- AWS::RDS::DBInstance
- AWS::Redshift::Cluster

Không được giả định mọi resource đều có snapshot. Ví dụ DynamoDB table không dùng DeletionPolicy Snapshot; hãy dùng Retain và DynamoDB Point-in-Time Recovery hoặc backup phù hợp.

## 5. UpdateReplacePolicy

UpdateReplacePolicy điều khiển số phận của **physical resource cũ** khi một stack update yêu cầu CloudFormation thay thế resource.

Ví dụ, một số thay đổi property của RDS DB instance yêu cầu Replacement. CloudFormation tạo DB instance mới, chuyển các dependency tham chiếu sang resource mới rồi xử lý instance cũ.

    Resources:
      ProductionDatabase:
        Type: AWS::RDS::DBInstance
        DeletionPolicy: Retain
        UpdateReplacePolicy: Retain
        Properties:
          # Các thuộc tính database được khai báo tại đây

Ở đây hai policy bảo vệ hai sự kiện khác nhau:

- DeletionPolicy Retain giữ database khi stack bị xóa hoặc resource bị loại khỏi template.
- UpdateReplacePolicy Retain giữ database cũ nếu một update buộc CloudFormation thay thế nó.

### 5.1. Các giá trị của UpdateReplacePolicy

| Giá trị | Hành vi khi resource bị thay thế |
|---|---|
| Delete | Xóa physical resource cũ |
| Retain | Giữ physical resource cũ, loại nó khỏi stack |
| Snapshot | Tạo snapshot cho resource cũ nếu loại resource hỗ trợ, sau đó xóa resource cũ |

Nếu không khai báo UpdateReplacePolicy, mặc định là Delete. Không có giá trị RetainExceptOnCreate cho thuộc tính này.

Nếu khai báo Snapshot cho resource không hỗ trợ snapshot, CloudFormation quay về hành vi mặc định Delete. Vì vậy, không dùng Snapshot như một policy chung cho tất cả resource.

Danh sách resource được AWS tài liệu hóa cho UpdateReplacePolicy Snapshot gồm:

- AWS::EC2::Volume
- AWS::ElastiCache::CacheCluster
- AWS::ElastiCache::ReplicationGroup
- AWS::Neptune::DBCluster
- AWS::RDS::DBCluster
- AWS::RDS::DBInstance
- AWS::Redshift::Cluster

Danh sách này khác danh sách DeletionPolicy Snapshot; ví dụ AWS::DocDB::DBCluster có trong danh sách DeletionPolicy nhưng không có trong danh sách UpdateReplacePolicy hiện hành. Hãy kiểm tra tài liệu thuộc tính đúng với sự kiện bạn cần bảo vệ.

## 6. Bảng quyết định: chọn policy nào?

| Resource và mục đích | DeletionPolicy | UpdateReplacePolicy |
|---|---|---|
| S3 bucket chứa hóa đơn cần giữ lâu dài | Retain | Retain |
| DynamoDB table chứa đơn hàng | Retain | Retain |
| RDS database cần lưu dữ liệu khi xóa/thay thế | Snapshot hoặc Retain theo quy trình | Snapshot hoặc Retain theo quy trình |
| EBS volume cần lưu dữ liệu để phục hồi | Snapshot hoặc Retain | Snapshot hoặc Retain |
| Log bucket dùng trong môi trường test, có lifecycle rõ | Delete | Delete |
| Bucket mới tạo trong stack có thể rollback khi create thất bại | RetainExceptOnCreate | Retain hoặc Delete tùy yêu cầu replacement |

Không có một policy đúng cho tất cả resource. Hãy quyết định dựa trên giá trị dữ liệu, khả năng tạo lại, thời gian lưu giữ, chi phí, yêu cầu audit và quy trình phục hồi.

## 7. Bảo vệ Amazon S3 bucket

S3 bucket có thể chứa dữ liệu mà vòng đời dài hơn ứng dụng hoặc stack. Một cấu hình cơ bản:

    Resources:
      InvoiceBucket:
        Type: AWS::S3::Bucket
        DeletionPolicy: Retain
        UpdateReplacePolicy: Retain
        Properties:
          VersioningConfiguration:
            Status: Enabled
          BucketEncryption:
            ServerSideEncryptionConfiguration:
              - ServerSideEncryptionByDefault:
                  SSEAlgorithm: AES256
          PublicAccessBlockConfiguration:
            BlockPublicAcls: true
            IgnorePublicAcls: true
            BlockPublicPolicy: true
            RestrictPublicBuckets: true

### 7.1. Versioning và Retain giải quyết vấn đề khác nhau

- Versioning lưu nhiều version của object, giúp khôi phục object bị ghi đè hoặc xóa nhầm.
- DeletionPolicy Retain giữ bucket khi stack hoặc resource bị xóa khỏi CloudFormation.
- UpdateReplacePolicy Retain giữ bucket cũ khi CloudFormation thay thế bucket.
- Encryption bảo vệ dữ liệu lưu trữ, nhưng không ngăn thao tác xóa.
- Lifecycle policy quản lý vòng đời version cũ và chi phí lưu trữ.

Versioning không ngăn mọi hình thức xóa vĩnh viễn. Người có quyền phù hợp vẫn có thể xóa một version cụ thể. Đối với dữ liệu cần bất biến theo thời hạn, xem S3 Object Lock.

### 7.2. Object Lock

S3 Object Lock cung cấp mô hình WORM (write once, read many) để bảo vệ object version khỏi bị xóa hoặc ghi đè trong thời hạn retention. Object Lock yêu cầu bucket có Versioning.

Hai chế độ thường gặp:

- **Governance mode:** phần lớn principal không thể xóa hoặc thay đổi retention; principal có quyền bypass đặc biệt có thể vượt qua governance retention.
- **Compliance mode:** object version không thể bị xóa hoặc rút ngắn thời hạn retention bởi bất kỳ user nào, kể cả root user trong account, trong thời gian bảo vệ.

Legal hold không có ngày hết hạn tự động; nó tồn tại cho đến khi được gỡ. Retention và legal hold áp dụng trên object version cụ thể. Chúng không ngăn một version mới hoặc delete marker xuất hiện trên cùng key.

Object Lock không thay DeletionPolicy. DeletionPolicy giữ bucket resource; Object Lock bảo vệ object versions bên trong bucket.

### 7.3. S3 bucket có dữ liệu không thể xóa trực tiếp

S3 chỉ cho phép xóa bucket rỗng. Nếu DeletionPolicy hoặc UpdateReplacePolicy là Delete nhưng bucket vẫn có object, thao tác xóa có thể thất bại. Với bucket bật Versioning, cần xử lý cả object versions và delete markers theo đúng quy trình.

Đừng thiết kế pipeline giả định CloudFormation tự dọn sạch mọi object. Nếu dữ liệu cần giữ, dùng Retain; nếu cần xóa, xây dựng bước archive/empty có kiểm soát và phê duyệt.

### 7.4. Bucket name và replacement

Nếu template khai báo BucketName tường minh, CloudFormation không thể thay thế bucket bằng cùng một tên toàn cục. AWS yêu cầu dùng tên mới khi cần replacement. UpdateReplacePolicy Retain không giải quyết xung đột tên bucket.

Khi đổi cấu hình buộc replacement, cần thiết kế bucket đích với tên duy nhất, copy dữ liệu, cập nhật ứng dụng/DNS/policy tham chiếu, xác minh dữ liệu rồi mới xử lý bucket cũ.

## 8. Bảo vệ Amazon DynamoDB table

DynamoDB table không hỗ trợ DeletionPolicy Snapshot theo danh sách resource snapshot của CloudFormation. Đối với table quan trọng, thường kết hợp Retain với Point-in-Time Recovery (PITR).

    Resources:
      OrdersTable:
        Type: AWS::DynamoDB::Table
        DeletionPolicy: Retain
        UpdateReplacePolicy: Retain
        Properties:
          BillingMode: PAY_PER_REQUEST
          AttributeDefinitions:
            - AttributeName: pk
              AttributeType: S
          KeySchema:
            - AttributeName: pk
              KeyType: HASH
          PointInTimeRecoverySpecification:
            PointInTimeRecoveryEnabled: true
            RecoveryPeriodInDays: 35

PITR tạo continuous backups được DynamoDB quản lý. Recovery period có thể cấu hình từ 1 đến 35 ngày; mặc định là 35 ngày nếu không khai báo. Khi restore, DynamoDB tạo một table mới, không ghi đè table nguồn.

### 8.1. Chọn cơ chế bảo vệ

- Retain bảo vệ table khỏi việc CloudFormation xóa table khi stack/resource bị xóa.
- UpdateReplacePolicy Retain giữ table cũ nếu update yêu cầu replacement.
- PITR bảo vệ dữ liệu trước thao tác ghi/xóa nhầm trong cửa sổ phục hồi.
- On-demand backup phù hợp với mốc backup cụ thể hoặc yêu cầu lưu trữ riêng.
- IAM giới hạn principal nào được phép xóa table, thay đổi backup hoặc tắt PITR.

PITR không thay thế DeletionPolicy. Ngược lại, Retain không giúp khôi phục một item đã bị ghi đè hoặc xóa trong table vẫn đang hoạt động. Hai cơ chế giải quyết hai loại rủi ro khác nhau.

## 9. Bảo vệ Amazon RDS database

RDS có nhiều lớp bảo vệ:

- DeletionPolicy quyết định resource được giữ, xóa hay snapshot khi stack/resource bị xóa.
- UpdateReplacePolicy quyết định số phận DB instance cũ khi replacement.
- DeletionProtection ngăn xóa database khi tính năng này đang bật.
- BackupRetentionPeriod cấu hình thời gian giữ automated backups cho DB instance phù hợp.
- Snapshot thủ công cung cấp một mốc phục hồi độc lập.

Ví dụ fragment cho một RDS DB instance:

    Resources:
      ProductionDatabase:
        Type: AWS::RDS::DBInstance
        DeletionPolicy: Snapshot
        UpdateReplacePolicy: Snapshot
        Properties:
          Engine: mysql
          DBInstanceClass: db.t3.micro
          AllocatedStorage: "20"
          MasterUsername: dbadmin
          ManageMasterUserPassword: true
          StorageEncrypted: true
          BackupRetentionPeriod: 7
          DeletionProtection: true

Đây là fragment minh họa. Trong stack thực tế, cần khai báo thêm network/subnet/security group, tags, engine version và các thuộc tính phù hợp với engine, Region, workload và tiêu chuẩn bảo mật.

### 9.1. DeletionProtection không phải DeletionPolicy

DeletionProtection là thuộc tính ở cấp RDS. Khi bật, RDS không cho xóa database. Nếu CloudFormation cần xóa resource, thao tác có thể thất bại cho đến khi deletion protection được tắt có chủ đích.

DeletionPolicy Snapshot không tự động tắt DeletionProtection. Khi cần xóa database có bảo vệ, quy trình phải được kiểm soát: xác nhận backup, thay đổi DeletionProtection, review change set và thực hiện thao tác xóa theo phê duyệt.

Đối với Aurora, deletion protection được quản lý ở DB cluster. DB instance thành viên không dùng thuộc tính DeletionProtection giống DB instance độc lập.

### 9.2. Replacement có thể làm mất dữ liệu

AWS khuyến nghị tạo snapshot database trước khi update stack nếu thay đổi yêu cầu replacement. Với RDS DB instance, một số property có update behavior là Replacement. Hãy kiểm tra cột Update requires trong resource reference cho từng property.

Trong replacement, CloudFormation tạo DB instance mới, chuyển dependency rồi xóa instance cũ. Automated snapshots có thể bị xóa khi DB instance bị xóa hoặc thay thế; manual snapshots được giữ lại. Không nên coi automated backup là bản sao lưu cuối cùng cho một replacement quan trọng.

### 9.3. Snapshot và phục hồi

Snapshot chỉ tạo điểm phục hồi; nó không tự động đưa ứng dụng sang database mới hoặc xác minh dữ liệu đúng. Sau snapshot, cần xác định:

1. Snapshot identifier và thời điểm tạo.
2. KMS key dùng mã hóa snapshot và quyền truy cập key.
3. Cách restore thành DB instance/cluster mới.
4. Cách chuyển endpoint/secret/config của ứng dụng.
5. Cách kiểm tra dữ liệu, schema và quyền truy cập.
6. Khi nào được phép xóa database cũ.

Snapshot và retained DB tiếp tục phát sinh chi phí cho đến khi được xóa.

## 10. Bảo vệ Amazon EBS volume

EBS volume chứa filesystem, database files hoặc dữ liệu ứng dụng gắn với EC2. Nếu stack xóa volume, dữ liệu có thể mất theo volume lifecycle.

Ví dụ:

    Resources:
      DataVolume:
        Type: AWS::EC2::Volume
        DeletionPolicy: Snapshot
        UpdateReplacePolicy: Snapshot
        Properties:
          AvailabilityZone: !Ref AvailabilityZone
          Size: 100
          VolumeType: gp3
          Encrypted: true

Snapshot policy giúp giữ bản chụp volume trước khi xóa hoặc replacement. Tuy nhiên, snapshot của một volume đang được ghi không tự đảm bảo tính nhất quán ứng dụng. Với database hoặc filesystem nhiều volume, cần quiesce writes, flush dữ liệu hoặc dùng quy trình backup nhất quán phù hợp.

## 11. Stack policy bảo vệ resource khỏi update ngoài ý muốn

DeletionPolicy và UpdateReplacePolicy quy định cách xử lý resource khi CloudFormation xóa hoặc thay thế. Chúng không ngăn mọi stack update.

**Stack policy** là JSON policy gắn với stack, dùng để từ chối các loại update action trên logical resource được bảo vệ. Ví dụ, cho phép update các resource khác nhưng ngăn replacement và deletion của ProductionDatabase:

    {
      "Statement": [
        {
          "Effect": "Allow",
          "Action": "Update:*",
          "Principal": "*",
          "Resource": "*"
        },
        {
          "Effect": "Deny",
          "Action": [
            "Update:Replace",
            "Update:Delete"
          ],
          "Principal": "*",
          "Resource": "LogicalResourceId/ProductionDatabase"
        }
      ]
    }

Các action thường gặp:

| Action | Ý nghĩa |
|---|---|
| Update:Modify | Thay đổi property, có thể không gián đoạn hoặc gián đoạn một phần |
| Update:Replace | Tạo resource mới thay resource hiện tại |
| Update:Delete | Loại resource khỏi stack |
| Update:* | Tất cả update actions |

Stack policy chỉ áp dụng trong stack update. Nó không thay IAM policy và không ngăn ai đó gọi API dịch vụ để thay đổi resource trực tiếp. Sau khi gắn stack policy, các update không được cho phép tường minh sẽ bị từ chối; Deny luôn ưu tiên Allow.

## 12. Termination protection và IAM

Hai lớp bảo vệ bổ sung thường dùng cho stack production:

### 12.1. Termination protection

Termination protection ngăn thao tác xóa toàn bộ stack. Tính năng này mặc định tắt. Khi bật, yêu cầu DeleteStack thất bại và stack giữ nguyên trạng thái.

Có thể bật bằng AWS CLI:

    aws cloudformation update-termination-protection \
      --stack-name production-data \
      --enable-termination-protection

Termination protection chỉ bảo vệ thao tác xóa stack. Nó không ngăn một stack update loại resource khỏi template. Nếu update xóa một resource, DeletionPolicy vẫn quyết định hành vi của resource đó.

### 12.2. IAM

IAM kiểm soát principal nào được phép gọi CloudFormation và các service APIs. Dùng least privilege cho các hành động như UpdateStack, DeleteStack, SetStackPolicy, UpdateTerminationProtection, DeleteDBInstance, DeleteTable, DeleteBucket và các quyền backup/restore liên quan.

Stack policy là guardrail trong update workflow. IAM là lớp kiểm soát quyền truy cập. Cả hai cần được thiết kế cùng nhau.

## 13. So sánh các cơ chế bảo vệ

| Cơ chế | Bảo vệ điều gì? | Không bảo vệ điều gì? |
|---|---|---|
| DeletionPolicy | Resource khi stack bị xóa hoặc bị loại khỏi template | Replacement do property update |
| UpdateReplacePolicy | Physical resource cũ khi replacement | Stack deletion |
| Resource deletion protection | Ngăn service xóa resource khi bật | Mất dữ liệu do ghi/xóa object hoặc item |
| Stack policy | Một số update actions của resource trong stack | DeleteStack hoặc thao tác trực tiếp qua service API |
| Termination protection | Xóa toàn bộ stack | Resource removal qua stack update |
| IAM | Ai được gọi API/action | Sai sót logic từ principal vẫn được cấp quyền |
| Backup/PITR/Versioning | Khả năng phục hồi dữ liệu | Không tự ngăn mọi thao tác xóa resource |

Không có một thuộc tính đơn lẻ nào tạo ra data protection đầy đủ. Hãy kết hợp lớp vòng đời, lớp quyền, lớp backup và lớp vận hành.

## 14. Quy trình review change set trước khi update

Trước khi triển khai template có thay đổi resource dữ liệu:

1. Tạo change set cho stack hiện tại.
2. Đọc danh sách resource sẽ Add, Modify, Remove hoặc Replace.
3. Tìm mọi resource dữ liệu có Replacement.
4. Mở resource reference để xác nhận property nào yêu cầu Replacement.
5. Kiểm tra DeletionPolicy và UpdateReplacePolicy của resource đó.
6. Xác minh snapshot/PITR/versioning và KMS key có thể truy cập.
7. Kiểm tra stack policy có chặn update không.
8. Ước tính chi phí của retained resource và snapshots.
9. Xác nhận ứng dụng có thể chuyển sang resource mới.
10. Chỉ thực thi change set sau khi review và phê duyệt.

Change set giúp dự đoán thay đổi, nhưng không đảm bảo update chắc chắn thành công. Một số lỗi chỉ xuất hiện trong quá trình thực thi, ví dụ quota, dependency, permission, tên resource bị trùng hoặc resource protection đang bật.

## 15. Resource được Retain: quản lý sau khi tách khỏi stack

Khi CloudFormation Retain một resource:

- Physical resource vẫn tồn tại trong account và Region.
- Resource không còn thuộc phạm vi quản lý của stack cũ.
- Resource tiếp tục phát sinh chi phí.
- Stack không tự động cập nhật resource đó trong những lần update tiếp theo.
- Nếu muốn quản lý lại bằng CloudFormation, cần dùng quy trình resource import nếu loại resource hỗ trợ và đáp ứng điều kiện import.

Sau khi retain, ghi lại physical ID, ARN, Region, owner, dữ liệu, backup policy, KMS key và cách vận hành. Đặt tag thể hiện trạng thái ownership để tránh resource mồ côi bị bỏ quên.

Đừng xem Retain là một thao tác cleanup. Nó chuyển trách nhiệm quản lý resource sang một quy trình hoặc owner khác.

## 16. Tình huống thực tế

### Tình huống A — Xóa stack ứng dụng nhưng giữ bucket hóa đơn

Stack ứng dụng sắp bị giải thể nhưng hóa đơn phải được giữ lại.

**Cách xử lý:** đặt DeletionPolicy Retain cho bucket. Bật Versioning và lifecycle phù hợp. Sau khi stack bị xóa, xác nhận bucket vẫn tồn tại, xác định owner mới và theo dõi chi phí.

### Tình huống B — Thay đổi property khiến RDS replacement

Một property trên DB instance có update behavior là Replacement.

**Cách xử lý:** tạo snapshot/backup có thể phục hồi, đặt UpdateReplacePolicy Snapshot hoặc Retain theo quy trình, kiểm tra change set, chuẩn bị endpoint cutover và giữ resource cũ cho đến khi dữ liệu mới được xác minh.

### Tình huống C — Bỏ DynamoDB table khỏi template

Nhóm phát triển chuyển table sang stack riêng.

**Cách xử lý:** dùng DeletionPolicy Retain để table không bị xóa khi bị loại khỏi template cũ. Sau đó import table vào stack mới nếu loại resource và trạng thái đáp ứng điều kiện import. Kiểm tra PITR và quyền trước/sau khi chuyển.

### Tình huống D — Stack create thất bại sau khi tạo bucket

Pipeline tạo bucket xong nhưng một resource khác lỗi khiến stack rollback.

**Cách xử lý:** nếu bucket mới không cần giữ khi create rollback, dùng RetainExceptOnCreate. Nếu dữ liệu có thể đã được ghi vào bucket trong quá trình bootstrap, đánh giá kỹ trước khi chọn.

### Tình huống E — S3 bucket không xóa được

Change set dự kiến xóa bucket nhưng bucket còn object versions.

**Cách xử lý:** xác định chính sách dữ liệu, archive/retention và xử lý version/delete marker đúng quy trình. Nếu bucket phải được giữ, đổi policy thành Retain theo một stack update đã review. Không xóa hàng loạt object chỉ để làm cho stack deletion thành công.

### Tình huống F — RDS DeletionProtection đang bật

CloudFormation cần xóa database nhưng RDS từ chối vì deletion protection.

**Cách xử lý:** xác minh backup và phê duyệt, tắt deletion protection qua thay đổi có kiểm soát, rồi thực hiện thao tác xóa với DeletionPolicy phù hợp. Không xóa bảo vệ chỉ để xử lý một lỗi pipeline mà chưa xác minh dữ liệu.

### Tình huống G — UpdateReplacePolicy Snapshot trên resource không hỗ trợ

Một resource không thuộc danh sách snapshot-supported được khai báo UpdateReplacePolicy Snapshot.

**Cách xử lý:** CloudFormation quay về Delete cho replacement. Chọn Retain hoặc backup mechanism riêng của service; không dựa vào Snapshot nếu resource không hỗ trợ.

## 17. Checklist bảo vệ dữ liệu production

- [ ] Mọi S3 bucket chứa dữ liệu quan trọng có DeletionPolicy phù hợp.
- [ ] Resource có thể bị replacement đã được đánh giá UpdateReplacePolicy.
- [ ] Không dùng Snapshot cho resource không hỗ trợ.
- [ ] S3 Versioning được bật khi cần phục hồi object versions.
- [ ] S3 Object Lock được dùng khi cần WORM/retention bất biến.
- [ ] DynamoDB PITR được bật và recovery period đáp ứng RPO.
- [ ] RDS automated backups và manual snapshot có retention rõ ràng.
- [ ] RDS DeletionProtection được bật cho database quan trọng.
- [ ] EBS volume quan trọng có backup/snapshot nhất quán ứng dụng.
- [ ] KMS key của backup/snapshot được bảo vệ và có quyền restore.
- [ ] Stack policy ngăn replacement/deletion ngoài ý muốn với resource trọng yếu.
- [ ] Termination protection được bật cho stack production cần bảo vệ.
- [ ] IAM giới hạn quyền xóa stack, table, bucket, database và backup.
- [ ] Change set được review trước thay đổi có khả năng Replacement.
- [ ] Retained resource có owner, tag, inventory và kế hoạch chi phí.
- [ ] Đã diễn tập restore, cutover và cleanup sau phục hồi.

## 18. Câu hỏi ôn tập

1. DeletionPolicy được áp dụng trong những tình huống nào?
2. UpdateReplacePolicy được áp dụng khi nào?
3. Thay đổi property cập nhật tại chỗ có kích hoạt hai policy này không?
4. Nếu không khai báo DeletionPolicy, hành vi mặc định thường là gì?
5. Hai loại RDS resource nào có default DeletionPolicy Snapshot đặc biệt?
6. Retain có xóa resource khỏi AWS không?
7. Khi Retain, resource còn thuộc phạm vi quản lý của stack không?
8. RetainExceptOnCreate xử lý rollback của stack create như thế nào?
9. UpdateReplacePolicy có hỗ trợ RetainExceptOnCreate không?
10. Snapshot có áp dụng cho mọi resource CloudFormation không?
11. Vì sao DeletionPolicy không bảo vệ resource cũ trong replacement?
12. Vì sao cần UpdateReplacePolicy cho database?
13. S3 Versioning giải quyết vấn đề gì?
14. S3 Object Lock yêu cầu tính năng nào được bật trên bucket?
15. Object Lock Compliance khác Governance ở điểm nào?
16. Vì sao Retain không thay PITR của DynamoDB?
17. DynamoDB PITR có thể phục hồi trong tối đa bao nhiêu ngày?
18. RDS DeletionProtection có thể làm stack deletion thất bại không?
19. Stack policy có thay IAM không?
20. Termination protection có chặn stack update xóa resource khỏi template không?
21. Vì sao S3 bucket có dữ liệu không xóa được khi policy là Delete?
22. UpdateReplacePolicy Snapshot trên resource không hỗ trợ dẫn tới hành vi gì?
23. Change set giúp phát hiện loại thay đổi nào?
24. Resource được retain tiếp tục phát sinh chi phí không?
25. Khi nào nên dùng RetainExceptOnCreate?

**Đáp án nhanh:** (1) stack deletion và resource removal trong update; (2) replacement; (3) không; (4) Delete, trừ ngoại lệ RDS được nêu; (5) DBCluster và DBInstance không có DBClusterIdentifier; (6) không; (7) không; (8) xóa resource mới tạo khi rollback thao tác create ban đầu; (9) không; (10) không; (11) replacement dùng UpdateReplacePolicy; (12) giữ hoặc snapshot physical database cũ; (13) lưu nhiều object versions; (14) Versioning; (15) Governance có quyền bypass đặc biệt, Compliance không thể bypass trong retention; (16) Retain không phục hồi thay đổi dữ liệu; (17) 35 ngày; (18) có; (19) không; (20) không; (21) S3 chỉ xóa bucket rỗng; (22) quay về Delete; (23) Add/Modify/Remove/Replace; (24) có; (25) khi resource mới cần được xóa nếu stack create rollback nhưng cần giữ trong các lần xóa sau.

## 19. Tổng kết

DeletionPolicy và UpdateReplacePolicy giải quyết hai thời điểm khác nhau trong vòng đời CloudFormation:

- DeletionPolicy áp dụng khi xóa stack hoặc loại resource khỏi template.
- UpdateReplacePolicy áp dụng khi một update buộc resource phải được thay thế.
- Delete xóa resource; Retain giữ resource ngoài stack; Snapshot tạo bản snapshot nếu resource hỗ trợ.
- RetainExceptOnCreate chỉ thuộc DeletionPolicy và hữu ích cho rollback của lần tạo stack ban đầu.
- RDS, DynamoDB, S3 và EBS cần kết hợp policy với backup và bảo vệ riêng của service.
- Stack policy bảo vệ update; termination protection bảo vệ thao tác xóa stack; IAM kiểm soát ai được phép gọi API.
- Retained resources và snapshots tiếp tục phát sinh chi phí và cần owner quản lý.
- Luôn review change set, xác minh replacement behavior và kiểm thử restore trước khi thay đổi resource dữ liệu production.

Một thiết kế IaC an toàn làm rõ **resource nào được phép xóa, dữ liệu nào phải giữ, replacement sẽ tạo ra điều gì và ai chịu trách nhiệm phục hồi**.

### Tài liệu AWS chính thức

1. DeletionPolicy attribute: https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-attribute-deletionpolicy.html
2. UpdateReplacePolicy attribute: https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-attribute-updatereplacepolicy.html
3. CloudFormation best practices: https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/best-practices.html
4. Prevent updates to stack resources: https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/protect-stack-resources.html
5. Protect CloudFormation stacks from being deleted: https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-protect-stacks.html
6. AWS::RDS::DBInstance resource: https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-rds-dbinstance.html
7. DynamoDB point-in-time recovery: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Point-in-time-recovery.html
8. DynamoDB PointInTimeRecoverySpecification: https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-properties-dynamodb-table-pointintimerecoveryspecification.html
9. AWS::S3::Bucket resource: https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-s3-bucket.html
10. S3 Object Lock: https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html
11. Deleting an Amazon RDS DB instance: https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_DeleteInstance.html
12. Amazon DynamoDB backup and restore: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Backup-and-Restore.html
