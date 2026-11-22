# Bucket policy, Access Point và Block Public Access

> **Chương:** Lưu trữ đối tượng S3  
> **Module:** CLOUD_PROVIDERS_AWS — tìm hiểu AWS từ Region/AZ, IAM và VPC đến compute, storage, database, tích hợp và serverless; thực hành chọn dịch vụ, bảo vệ dữ liệu, giám sát, phục hồi và kiểm soát chi phí.

## Mục tiêu học tập

Amazon Simple Storage Service (**Amazon S3**) có thể chứa tài liệu, ảnh, dữ liệu phân tích, bản sao lưu và nhiều dữ liệu nghiệp vụ. Rủi ro thường không nằm ở thao tác upload mà ở câu hỏi: **Ai có thể đọc hoặc thay đổi object, đi qua đường truy cập nào, và một cấu hình vô tình có thể khiến dữ liệu công khai hay không?**

Ba cơ chế trung tâm của bài này là:

- **Bucket policy:** chính sách tài nguyên gắn với S3 bucket, kiểm soát những yêu cầu hợp lệ dựa trên principal, action, resource và condition.
- **S3 Access Point:** điểm truy cập có tên, gắn với một nguồn dữ liệu như general purpose bucket, có chính sách và cấu hình nguồn mạng riêng để đơn giản hóa quyền theo ứng dụng/nhóm.
- **S3 Block Public Access (BPA):** hàng rào bảo vệ giúp ngăn quyền truy cập công khai được cấp qua ACL và resource policy, với nhiều cấp cấu hình.

Sau bài, bạn sẽ có thể:

1. Đọc, viết và kiểm tra bucket policy theo nguyên tắc **least privilege**.
2. Phân biệt IAM identity policy, bucket policy, Access Point policy và Block Public Access.
3. Giải thích bốn cờ `BlockPublicAcls`, `IgnorePublicAcls`, `BlockPublicPolicy` và `RestrictPublicBuckets`.
4. Thiết kế Access Point cho từng nhóm ứng dụng, có thể hạn chế theo VPC và hiểu quan hệ với bucket policy.
5. Kiểm tra quyền bằng AWS Console, IAM Access Analyzer, AWS CLI và dấu vết truy cập.
6. Thực hiện lab sandbox: xác minh trạng thái bảo vệ, tạo bucket thử nghiệm riêng tư, tạo Access Point theo tùy chọn và dọn tài nguyên.
7. Nhận diện các tình huống dễ bị `AccessDenied` hoặc mở nhầm quyền công khai, từ đó có phương án khắc phục an toàn.

## 1. Quyền truy cập S3 được quyết định ở đâu?

### 1.1. Luồng xử lý ở mức khái niệm

Một ứng dụng trên EC2, Lambda hoặc máy cá nhân gửi request tới S3, chẳng hạn `s3:GetObject`. AWS xem danh tính đang gọi, resource đích và các chính sách liên quan. Nếu có **explicit Deny** áp dụng, request bị từ chối. Khi cần các `Allow`, chúng phải phù hợp với mô hình identity/resource policy và không bị SCP, permissions boundary, session policy hoặc cơ chế khác chặn.

~~~mermaid
flowchart TD
    A[Ứng dụng / IAM principal] --> B[Yêu cầu GetObject / PutObject / ListBucket]
    B --> C{Đi qua Access Point?}
    C -->|Có| D[Access Point: network origin + policy + BPA]
    C -->|Không| E[Bucket endpoint thông thường]
    D --> F[Underlying bucket policy]
    E --> F
    F --> G[Kiểm tra IAM và chính sách liên quan]
    G --> H[Block Public Access có áp dụng?]
    H --> I{Yêu cầu được phép?}
    I -->|Có| J[Đọc/ghi object]
    I -->|Không| K[AccessDenied / từ chối]
~~~

Sơ đồ mô tả các **điểm kiểm soát**, không phải thứ tự xử lý nội bộ chính xác của dịch vụ. Một resource-based policy đôi khi cấp quyền trực tiếp cho principal trong cùng account, còn cross-account có yêu cầu riêng. Điều chắc chắn là **BPA không tự tạo `Allow`**, Access Point cũng không bỏ qua bucket policy.

### 1.2. Bốn cơ chế thường bị nhầm

| Cơ chế | Được gắn ở đâu? | Mục tiêu | Có tự cấp quyền không? |
|---|---|---|---|
| **IAM identity-based policy** | IAM user, group, role | Principal có thể gọi những API nào | Có thể cấp bằng `Allow` |
| **S3 bucket policy** | Bucket | Định nghĩa principal, thao tác, tài nguyên và điều kiện truy cập bucket/object | Có thể cấp bằng `Allow` hoặc chặn bằng `Deny` |
| **S3 Access Point policy** | Một Access Point cụ thể | Giới hạn/cấp quyền khi request đi **qua Access Point đó** | Có thể cấp trong phạm vi Access Point, nhưng underlying bucket cũng phải cho phép |
| **S3 Block Public Access** | Organization, account, bucket, Access Point | Chặn cấu hình/quyền **public** có nguy cơ lộ dữ liệu | Không; chỉ giới hạn public access |

Ngoài ra, còn **bucket Object Ownership**, ACL, **VPC endpoint policy**, **KMS key policy** nếu dùng SSE-KMS, chính sách Organizations và các kiểm soát tổ chức khác. Không xem bốn cơ chế trên là toàn bộ hệ thống ủy quyền.

## 2. Bucket policy: ngôn ngữ quyền ở cấp tài nguyên

### 2.1. Cấu trúc JSON

Bucket policy là JSON theo cú pháp policy của AWS. Mỗi statement có thể có các phần:

| Thành phần | Chức năng | Ví dụ |
|---|---|---|
| `Version` | Phiên bản ngôn ngữ policy | `2012-10-17` |
| `Statement` | Danh sách quy tắc | Một hoặc nhiều statement |
| `Sid` | Tên dễ đọc cho quy tắc | `AllowReaderGetReports` |
| `Effect` | `Allow` hoặc `Deny` | `Allow` |
| `Principal` | Danh tính áp dụng; bucket policy là resource-based policy | ARN role hoặc AWS service principal |
| `Action` | Hành động API được kiểm soát | `s3:GetObject` |
| `Resource` | ARN bucket và/hoặc object | `arn:aws:s3:::bucket-name/reports/*` |
| `Condition` | Điều kiện trên request | `aws:SecureTransport`, `aws:PrincipalOrgID`, `s3:ExistingObjectTag`... |

**Phân biệt ARN bucket và object:**

~~~text
Bucket ARN:
arn:aws:s3:::aws-lab-private-demo

Object ARN:
arn:aws:s3:::aws-lab-private-demo/reports/2026/report.csv

Tất cả object trong prefix reports/:
arn:aws:s3:::aws-lab-private-demo/reports/*
~~~

- `s3:ListBucket` thường dùng **bucket ARN**.
- `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject` thường dùng **object ARN**.
- Các thao tác khác như liệt kê version, quản lý policy, multipart upload, tagging có quyền riêng; không tự suy đoán bằng tên API.

### 2.2. Ví dụ 1 — Chỉ cấp quyền đọc một prefix cho một role

Giả sử bucket giả định `aws-lab-private-demo` chứa dữ liệu báo cáo ở prefix `reports/`. Role `aws-lab-report-reader` trong account `111122223333` chỉ cần đọc object tại prefix này:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowReportReaderRole",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::111122223333:role/aws-lab-report-reader"
      },
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::aws-lab-private-demo/reports/*"
    }
  ]
}
~~~

Đây là ví dụ về **resource policy**, chỉ cho role nêu trên đọc object trong prefix. Để role có thể **liệt kê** object, cần thêm quyền `s3:ListBucket` trên ARN bucket và giới hạn theo `s3:prefix` nếu muốn. Để dùng SSE-KMS, principal còn phải có quyền KMS tương ứng và key policy phải cho phép.

Trong cùng account, bucket policy có thể tạo đường cấp quyền ngoài identity-based policy, theo quy tắc đánh giá của AWS. Với **cross-account**, người gọi thường cần quyền tương ứng ở phía account nguồn và bucket policy tại account đích phải cho phép. Không áp dụng giản lược “mọi chính sách đều có `Allow`” cho mọi loại principal mà không xét ngữ cảnh.

### 2.3. Ví dụ 2 — Chặn request HTTP không dùng TLS

Một statement bảo vệ thường gặp là chặn yêu cầu không có HTTPS:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyInsecureTransport",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:*",
      "Resource": [
        "arn:aws:s3:::aws-lab-private-demo",
        "arn:aws:s3:::aws-lab-private-demo/*"
      ],
      "Condition": {
        "Bool": {
          "aws:SecureTransport": "false"
        }
      }
    }
  ]
}
~~~

Statement này không cấp quyền nào; nó từ chối những request khớp điều kiện không dùng TLS. Đối với AWS service-to-service calls, một số context key liên quan mạng có thể bị lược bỏ; khi thiết kế các `Deny` dựa trên điều kiện mạng, cần đọc hướng dẫn dành cho **AWS service principals** để không làm hỏng logging, replication hoặc tích hợp.

**Nguyên tắc khi thay policy:** bucket chỉ có **một bucket policy document** tại một thời điểm. Thao tác `PutBucketPolicy` ghi một bản policy hoàn chỉnh và có thể thay thế policy cũ. Khi triển khai, **hợp nhất statement vào policy hiện có** và kiểm tra kết quả trước; không ghi đè nguyên policy production bằng JSON ví dụ.

### 2.4. Conditions giúp thu hẹp quyền

| Condition key | Ý nghĩa thường dùng | Lưu ý |
|---|---|---|
| `aws:SecureTransport` | Kiểm tra HTTPS/TLS | Bảo vệ traffic nếu điều kiện phù hợp |
| `aws:PrincipalOrgID` | Giới hạn principal thuộc AWS Organization được chỉ định | Không thay thế chính sách cho từng principal; xem service principals |
| `aws:SourceVpce` | Yêu cầu đi qua một VPC endpoint cụ thể | Có thể khiến Console hoặc service integration không truy cập được |
| `aws:SourceVpc` | Nhận diện VPC nguồn ở request được hỗ trợ | Chỉ có khi context phù hợp |
| `s3:prefix` | Giới hạn prefix khi `ListBucket` | Không dùng thay ARN object cho `GetObject` |
| `s3:ExistingObjectTag/<key>` | Kiểm tra tag hiện có trên object cho API hỗ trợ | Object tag không phải bucket tag |
| `s3:DataAccessPointArn` | Kiểm soát request qua Access Point cụ thể | Hữu ích khi ủy quyền qua Access Point |
| `s3:DataAccessPointAccount` | Kiểm soát account sở hữu Access Point | Phù hợp delegation đến Access Point cùng account |
| `s3:AccessPointNetworkOrigin` | Kiểm tra origin `VPC` hay `Internet` của Access Point | Không đồng nghĩa route table hoặc VPC endpoint policy |

Nên sử dụng **ARN và giá trị cố định** cho những ràng buộc nhạy cảm. Cần hiểu sự khác nhau giữa `StringEquals`, `StringNotEquals`, `ArnEquals`, `Bool` và toán tử `IfExists`; condition sai có thể vô tình chặn dịch vụ hợp lệ hoặc mở hơn dự định.

### 2.5. Explicit Deny và nguy cơ khóa chính mình

Ví dụ nhiều nhóm dùng bucket policy để buộc request qua `aws:SourceVpce`:

~~~json
{
  "Sid": "DenyOutsideApprovedVpce",
  "Effect": "Deny",
  "Principal": "*",
  "Action": "s3:*",
  "Resource": [
    "arn:aws:s3:::aws-lab-private-demo",
    "arn:aws:s3:::aws-lab-private-demo/*"
  ],
  "Condition": {
    "StringNotEquals": {
      "aws:SourceVpce": "vpce-0123456789abcdef0"
    }
  }
}
~~~

Đây chỉ là **một statement minh họa**, không phải policy sẵn dùng. Console, nhiều ứng dụng hoặc các dịch vụ AWS không đi qua endpoint đó nên có thể bị từ chối, kể cả người quản trị. Với kiến trúc thật, cần thiết kế ngoại lệ có kiểm soát cho quản trị/khôi phục, xem xét service principals và **kiểm thử trước khi áp đặt Deny**.

## 3. Block Public Access: bốn cờ cần phân biệt

### 3.1. “Public” trong S3 nghĩa là gì?

Quyền public thường liên quan đến ACL cấp cho các nhóm mặc định như **AllUsers/AuthenticatedUsers** hoặc resource policy mà S3 xác định cho phép truy cập công khai. **`Principal: "*"` không phải lúc nào cũng tự động làm policy thành public**: AWS còn xét điều kiện đáng tin cậy có giá trị cố định, ví dụ một principal hoặc tổ chức được xác định cụ thể theo quy tắc phân loại policy.

Tuy nhiên, `Principal: "*"` là dấu hiệu phải **đánh giá kỹ**. Không suy luận policy an toàn chỉ vì đã có một `Condition` bất kỳ. Dùng **IAM Access Analyzer for S3** và các công cụ kiểm tra policy của AWS để xác định truy cập public/cross-account.

### 3.2. Bảng so sánh chính xác bốn thiết lập

| Cờ Block Public Access | Khi bật `true` | Có xóa ACL/policy cũ không? |
|---|---|---|
| **BlockPublicAcls** | Từ chối các API đặt **ACL công khai mới** trên bucket/object và upload có ACL công khai | **Không** |
| **IgnorePublicAcls** | Bỏ qua ACL công khai khi đánh giá quyền, kể cả ACL có từ trước | **Không**, ACL vẫn có thể tồn tại |
| **BlockPublicPolicy** | Từ chối tạo/cập nhật **bucket policy hoặc access point policy được nhận diện là public** trong phạm vi có hiệu lực | **Không**, không xóa policy cũ |
| **RestrictPublicBuckets** | Nếu bucket/access point có policy public, giới hạn quyền truy cập công khai và phần lớn cross-account theo quy tắc dịch vụ | **Không**, hạn chế hiệu lực truy cập |

**Hai cờ về ACL khác nhau:** `BlockPublicAcls` ngăn thêm ACL công khai mới; `IgnorePublicAcls` khiến S3 **không dùng** ACL công khai khi ra quyết định. Vì vậy, bật cả hai tạo lớp bảo vệ bổ sung, dù S3 đã có cấu hình Object Ownership làm ACL vô hiệu.

**Hai cờ về policy cũng khác nhau:** `BlockPublicPolicy` ngăn đưa vào một policy công khai mới nhưng **không tự sửa policy public đang tồn tại**; `RestrictPublicBuckets` hạn chế truy cập khi một policy đang bị đánh giá là public, kể cả các delegation cross-account vốn có thể hợp lệ trong policy đó. Đây là lý do bật cả bốn là mặc định an toàn cho dữ liệu riêng tư.

### 3.3. Block Public Access có hiệu lực theo nhiều cấp

Trong thiết kế AWS hiện hành, BPA có thể được đặt tại:

1. **AWS Organizations**: quản trị viên có thể sử dụng S3 policy ở cấp tổ chức để áp Block Public Access cho member accounts. Cấu hình ở cấp tổ chức áp dụng **cả bốn cờ đồng thời** theo chế độ `all` hoặc `none`.
2. **AWS account**: bảo vệ các bucket và Access Point của account trên toàn bộ các Region theo quy tắc S3.
3. **Bucket**: bảo vệ bucket và các Access Point tương ứng.
4. **Access Point**: bảo vệ request đi qua Access Point cụ thể.

~~~mermaid
flowchart TD
    O[AWS Organizations: S3 Block Public Access policy nếu có]
    O --> A[Account-level Block Public Access]
    A --> B[Bucket-level Block Public Access]
    B --> P[Access Point-level Block Public Access]
    B --> Q[Request trực tiếp đến bucket]
    P --> R[Request qua Access Point]
    Q --> S[Áp dụng giới hạn chặt nhất]
    R --> S
~~~

**Nguyên tắc:** S3 thực thi **tổ hợp hạn chế nhất** của các thiết lập BPA áp dụng. Một Access Point không thể tự tắt bảo vệ được account/bucket/tổ chức áp đặt. Nếu bucket-level tắt nhưng account-level bật, request vẫn chịu bảo vệ account-level. Một cấu hình ở cấp tổ chức có thể không cho phép người quản trị account hạ các thiết lập đang bị quản lý tập trung.

**Lưu ý:** Thay BPA không xóa nội dung policy/ACL đang tồn tại. Nếu tắt cờ bảo vệ sau đó, quyền public cũ có thể **có hiệu lực trở lại**. Vì vậy cần audit policy, ACL và kiểm tra luồng truy cập trước mọi thay đổi.

### 3.4. Mặc định của bucket mới và Object Ownership

Với **S3 general purpose bucket mới**, AWS mặc định bật **bốn Block Public Access settings** và chọn **Object Ownership: Bucket owner enforced**, khiến ACL bị vô hiệu hóa trong việc kiểm soát truy cập. Trong mô hình này:

- Chủ sở hữu bucket kiểm soát object theo cơ chế Object Ownership.
- Quản trị quyền bằng **IAM policy, bucket policy và Access Point policy** thay vì dựa vào ACL.
- API cố đặt object ACL không được hỗ trợ có thể báo lỗi, chẳng hạn `AccessControlListNotSupported`.
- Không tắt Block Public Access hoặc đổi Object Ownership chỉ để giải quyết một lỗi upload trước khi hiểu nguyên nhân.

Các bucket được tạo từ lâu có thể giữ cấu hình khác, do đó **kiểm tra cấu hình thực** thay vì giả định mọi bucket đều theo mặc định hiện nay.

## 4. S3 Access Point: chia quyền theo ứng dụng và nguồn mạng

### 4.1. Vì sao Access Point hữu ích?

Giả sử một bucket chứa ba vùng dữ liệu:

~~~text
aws-lab-shared-datasets/
├── analytics/
│   └── events-2026.json
├── finance/
│   └── invoices.csv
└── exports/
    └── daily-summary.json
~~~

Nếu nhiều ứng dụng và nhóm sử dụng một bucket, bucket policy đơn lẻ có thể ngày càng dài, khó bảo trì. Một giải pháp là tạo các Access Point:

- **`ap-analytics-read`**: chỉ cho ứng dụng phân tích đọc `analytics/`.
- **`ap-finance-private`**: chỉ cho vai trò tài chính đọc hoặc ghi `finance/` từ một VPC.
- **`ap-exports-write`**: cho worker xuất báo cáo ghi vào `exports/`.

Mỗi Access Point có **tên, ARN, access point policy, network origin và BPA** riêng. Nó không sao chép dữ liệu sang một bucket mới: các Access Point vẫn trỏ tới **nguồn dữ liệu nền**.

~~~mermaid
flowchart LR
    A[Ứng dụng analytics] --> P1[Access Point analytics-read]
    B[Ứng dụng finance trong VPC] --> P2[Access Point finance-private]
    C[Export worker] --> P3[Access Point exports-write]
    P1 --> S[(Bucket: shared datasets)]
    P2 --> S
    P3 --> S
    D[Bucket policy + IAM + BPA] -. Kiểm soát .-> S
~~~

### 4.2. Access Point ARN khác bucket ARN

Ví dụ Access Point tên `ap-analytics-read` ở Region `ap-southeast-1` và account `111122223333`:

~~~text
Access Point ARN:
arn:aws:s3:ap-southeast-1:111122223333:accesspoint/ap-analytics-read

Object ARN qua Access Point:
arn:aws:s3:ap-southeast-1:111122223333:accesspoint/ap-analytics-read/object/analytics/events-2026.json

Object prefix qua Access Point:
arn:aws:s3:ap-southeast-1:111122223333:accesspoint/ap-analytics-read/object/analytics/*
~~~

Đối chiếu:

~~~text
Bucket ARN:
arn:aws:s3:::aws-lab-shared-datasets

Object ARN trực tiếp qua bucket:
arn:aws:s3:::aws-lab-shared-datasets/analytics/events-2026.json
~~~

**Đừng dùng nhầm ARN bucket làm Resource trong Access Point policy**. Với action trên object qua Access Point, Resource thường là ARN có đường dẫn `accesspoint/.../object/...`; với `s3:ListBucket` qua Access Point, dùng **Access Point ARN** phù hợp.

S3 cũng cấp **Access Point alias** cho general purpose bucket. Alias có thể sử dụng trong một số data operations như tên bucket; tuy nhiên alias **không thay cho ARN trong IAM policy**. Năng lực API qua Access Point có giới hạn: ví dụ không dùng Access Point để xóa bucket hoặc cấu hình replication cho bucket.

### 4.3. Network origin: Internet và VPC

Khi tạo Access Point cho S3 general purpose bucket, bạn chọn một trong hai **network origin**:

| Network origin | Ý nghĩa | Lựa chọn khi nào? |
|---|---|---|
| **Internet** | Request có thể đến Access Point qua các đường mạng hỗ trợ nếu IAM/resource policy cho phép | Ứng dụng không bị ràng buộc riêng một VPC; **không đồng nghĩa public/anonymous** |
| **VPC** | Chỉ chấp nhận request qua mạng từ **VPC đã chỉ định**, theo cơ chế và điều kiện AWS | Workload riêng trong một VPC, cần cô lập đường truy cập |

Với Access Point origin **VPC**, các request không xuất phát từ VPC được cấu hình sẽ bị S3 từ chối, kể cả khi có IAM `Allow`. Cần thiết kế **VPC endpoint phù hợp**, DNS, routing, endpoint policy và IAM/resource policy cho đường đi thực tế.

**Giới hạn không thể sửa tùy ý sau tạo:** network origin và VPC ID của Access Point, cũng như **bốn BPA settings của Access Point**, không thể chỉnh lại sau khi Access Point được tạo. Nếu lựa chọn ban đầu sai, phải xóa và tạo Access Point mới với cấu hình mong muốn, đồng thời đánh giá tác động đến client và chính sách.

**Không nhầm Access Point với VPC endpoint:**

- **S3 Access Point** là điểm truy cập có tên và chính sách của S3.
- **S3 gateway VPC endpoint** định tuyến traffic từ VPC đến S3 qua route table; **S3 interface VPC endpoint** có private IP qua AWS PrivateLink trong những trường hợp được hỗ trợ.
- Access Point có origin VPC cần luồng mạng hợp lệ từ VPC đã chọn; một Access Point không tự tạo NAT Gateway, VPC endpoint hay route table.

### 4.4. Access Point policy và underlying bucket policy phải phối hợp

AWS yêu cầu **Access Point và bucket nền cùng cho phép** request theo mô hình cấp quyền phù hợp. Access Point policy chỉ áp dụng cho request **đi qua Access Point đó**; request trực tiếp đến bucket hoặc Access Point khác vẫn được đánh giá theo đường truy cập tương ứng.

Hai cách triển khai thông dụng:

1. **Delegation:** bucket policy ủy quyền một tập thao tác cho Access Point hoặc Access Points được duyệt, sau đó Access Point policy giới hạn principal và object prefix.
2. **Quyền tương ứng:** bucket policy cho cùng principal thao tác lên tài nguyên nền; Access Point policy tiếp tục giới hạn request đi qua nó.

Đối với bài học này, chúng ta dùng mô hình **delegation tới đúng một Access Point**, dễ kiểm tra đường cấp quyền và giới hạn scope.

## 5. Ví dụ phối hợp Bucket Policy và Access Point Policy

### 5.1. Mục tiêu

Một nhóm phân tích cần đọc dữ liệu dưới prefix `analytics/` trong bucket `aws-lab-shared-datasets`. Quy định:

- Chỉ role `aws-lab-analytics-reader` của account `111122223333` được dùng Access Point `ap-analytics-read`.
- Chỉ cấp thao tác `s3:GetObject` vào prefix `analytics/`.
- Bucket cho phép request **thông qua đúng Access Point ARN** này; Access Point policy giới hạn principal.
- Bật cả bốn BPA ở bucket/account/Access Point.
- Nếu cần list objects, bổ sung riêng `s3:ListBucket` cùng `s3:prefix` cho phù hợp.

**Ví dụ 1 — Bucket policy ủy quyền GetObject qua Access Point:**

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DelegateAnalyticsReadToOneAccessPoint",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::aws-lab-shared-datasets/analytics/*",
      "Condition": {
        "ArnEquals": {
          "s3:DataAccessPointArn": "arn:aws:s3:ap-southeast-1:111122223333:accesspoint/ap-analytics-read"
        }
      }
    }
  ]
}
~~~

Vì `Principal` có dấu `*`, **điều kiện cố định trên Access Point ARN là thành phần bảo vệ thiết yếu**. AWS đánh giá một policy có public hay không theo quy tắc chi tiết; trước khi ghi policy cần kiểm tra IAM Access Analyzer và Block Public Access. Không gỡ `Condition` trong ví dụ này.

**Ví dụ 2 — Access Point policy giới hạn role và prefix:**

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReaderOnlyAnalyticsObjects",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::111122223333:role/aws-lab-analytics-reader"
      },
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:ap-southeast-1:111122223333:accesspoint/ap-analytics-read/object/analytics/*"
    }
  ]
}
~~~

**Kết quả mong đợi:** Request `GetObject` vào `analytics/sample.json` qua Access Point từ role được cấp có thể được phép nếu các cơ chế IAM/boundary/session/SCP/BPA/KMS/network còn lại cũng cho phép. Request `GetObject` vào `finance/invoices.csv` hoặc role không được cấp sẽ không có đường `Allow` tương ứng từ Access Point policy này.

**Vấn đề thực tế cần nhớ:**

- Bucket policy cần được **hợp nhất** với những quy tắc đang có; không áp chính sách demo như một bản thay thế trong production.
- Access Point policy **không tự đóng đường truy cập trực tiếp tới bucket** nếu bucket vẫn có policy/identity permissions khác cho phép. Muốn bắt buộc dùng Access Point, phải xây dựng guardrail có chủ đích và kiểm tra tương thích tính năng S3.
- Nếu sử dụng SSE-KMS, cần xem **KMS key policy/IAM permissions**; quyền `GetObject` chưa đủ trong mọi trường hợp.
- Quản trị viên Access Point chưa chắc là bucket owner, nhất là **cross-account Access Points**. Bucket owner có quyền kiểm soát cuối cùng đối với dữ liệu qua bucket policy.
- Object có thể được cấp quyền qua các đường khác nhau; không dùng chỉ một JSON statement để kết luận toàn bộ quyền hiệu lực.

### 5.2. Tình huống cross-account

Giả sử Access Point do **Account B** sở hữu, bucket do **Account A** sở hữu. Khi đó:

1. Access Point B được tạo gắn với bucket A theo API và yêu cầu phù hợp.
2. **Bucket owner A** phải cho phép request từ Access Point B qua bucket policy.
3. Access Point policy B và chính sách danh tính của bên gọi phải cho phép thao tác phù hợp.
4. SCP, BPA, RCP nếu có, KMS và điều kiện network phải được xem xét theo account/principal/resource.
5. Bộ phận A vẫn quyết định dữ liệu nào được chia sẻ; riêng việc B tạo Access Point không tạo quyền tự động trên bucket A.

S3 Access Point không phải cách bỏ qua ranh giới tài khoản hay thay thế quy trình phê duyệt chia sẻ dữ liệu.

## 6. Hướng dẫn chọn mô hình truy cập

| Nhu cầu | Thiết kế đề xuất | Lý do |
|---|---|---|
| Một ứng dụng nội bộ, ít principal, một bucket | IAM role + bucket policy khi cần | Ít lớp quản lý, rõ phạm vi |
| Nhiều ứng dụng truy cập prefix khác nhau của cùng bucket | Nhiều **S3 Access Points** với policy riêng | Giảm độ phức tạp khi một bucket policy phục vụ nhiều nhóm |
| Chỉ ứng dụng trong VPC được dùng một đường truy cập | **VPC-origin Access Point** + VPC endpoint và policy phù hợp | Giới hạn nguồn mạng, kiểm soát riêng từng ứng dụng |
| Bắt buộc không công khai dữ liệu | **BPA bật cả bốn** ở cấp account/bucket, cân nhắc cấp organization | Bảo vệ trước public ACL/policy không mong muốn |
| Chia sẻ object tạm thời cho người dùng đã được xác minh | **Presigned URL** hoặc cơ chế phân phối được duyệt | URL ký có thời hạn và quyền theo signer; không biến bucket thành public |
| Phân phối file công khai trên web | **CloudFront + Origin Access Control (OAC)** với bucket S3 riêng tư | Cho phép phân phối qua CDN/HTTPS trong khi S3 origin giữ private |
| Chia sẻ cho đối tác account khác | Role/cross-account bucket policy hoặc cross-account Access Point được duyệt | Trách nhiệm và principal được chỉ định rõ |
| Dữ liệu dùng cho batch analytics nhiều account | Đánh giá Access Point, data governance, Lake Formation nếu phù hợp | Phân quyền cần kết hợp quản trị tập dữ liệu, không chỉ quyền object |

**Không bắt buộc tạo Access Point cho mọi bucket.** Nếu một bucket chỉ phục vụ một ứng dụng và policy đơn giản, việc thêm Access Point có thể tăng chi phí quản trị mà chưa đem lại lợi ích. Ngược lại, bucket chứa dữ liệu nhiều nhóm thường hưởng lợi từ việc phân tách các đường truy cập và quyền.

## 7. Thực hành AWS CLI trên sandbox

> Thực hành chỉ dành cho account được cấp phép. Các lệnh tạo và xóa tài nguyên thật; trước khi thực thi, xác minh đúng account/Region, không dùng dữ liệu riêng tư và làm đủ bước dọn. Bucket, API request, dữ liệu lưu trữ, logging và các thành phần mạng có thể phát sinh phí. Ví dụ sử dụng **Bash** và **AWS CLI v2**.

### 7.1. Chuẩn bị danh tính

Nếu được cấp IAM Identity Center, đăng nhập bằng profile sandbox:

~~~bash
aws sso login --profile aws-lab-dev

export AWS_PROFILE=aws-lab-dev
export AWS_DEFAULT_REGION=ap-southeast-1
REGION=ap-southeast-1

aws sts get-caller-identity
~~~

Kiểm tra `Account` và `Arn` trả về thuộc **sandbox** mong muốn. Nếu sử dụng **AWS CloudShell** dưới phiên Console đã đăng nhập mà không có profile `aws-lab-dev`, bỏ bước `aws sso login` và `export AWS_PROFILE`, sử dụng credentials phiên hiện tại.

Để chạy toàn bộ lab, danh tính cần được cấp đúng quyền cho bucket, object, BPA và (nếu thực hiện phần Access Point) S3 Control APIs; không tự gán `AdministratorAccess` để vượt lỗi `AccessDenied`.

### 7.2. Bước 1 — Kiểm tra BPA account hiện có (chỉ đọc)

~~~bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

aws s3control get-public-access-block \
  --account-id "$ACCOUNT_ID"
~~~

Nếu nhận `NoSuchPublicAccessBlockConfiguration`, điều đó cho biết **không có cấu hình account-level BPA trả về từ API này**; không kết luận toàn bộ tài nguyên đều public hoặc thiếu các thiết lập ở cấp tổ chức/bucket. Nếu account thuộc Organizations có S3 policy, quyền đọc/chỉnh account-level setting có thể bị quản trị tập trung.

**Mục tiêu học:** biết account đang có bảo vệ BPA nào, khác với việc chỉ xem bucket trong Console.

### 7.3. Bước 2 — Tạo general purpose bucket riêng tư

Đặt tên bucket duy nhất và không chứa thông tin nhạy cảm:

~~~bash
BUCKET="aws-lab-policy-$(date +%s)-$RANDOM"
echo "$BUCKET"

aws s3api create-bucket \
  --bucket "$BUCKET" \
  --region "$REGION" \
  --create-bucket-configuration "LocationConstraint=$REGION"
~~~

Lệnh trên dành cho **ap-southeast-1**. Với **us-east-1**, cú pháp tạo general purpose bucket có điểm khác: thường **bỏ** `LocationConstraint`. Tên bucket phải đáp ứng quy tắc S3 và không trùng namespace áp dụng; nếu `BucketAlreadyExists`, hãy chọn tên khác.

**Không tắt BPA của account để tạo lab.** Bucket mới mặc định riêng tư; tiếp theo cấu hình rõ ràng để kiểm tra trạng thái mong muốn.

### 7.4. Bước 3 — Bật bốn cờ BPA ở bucket

~~~bash
aws s3api put-public-access-block \
  --bucket "$BUCKET" \
  --public-access-block-configuration \
    "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

aws s3api get-public-access-block \
  --bucket "$BUCKET"

aws s3api get-bucket-ownership-controls \
  --bucket "$BUCKET"
~~~

Kết quả mong đợi: bốn cờ trả về `true`; với bucket mới, Object Ownership thường ở chế độ **Bucket owner enforced**. Nếu một trong các lệnh `get` báo `AccessDenied`, kiểm tra quyền đọc cấu hình; không kết luận BPA đang tắt chỉ vì bạn không xem được.

### 7.5. Bước 4 — Upload object thử nghiệm

~~~bash
printf 'S3 policy training data\n' > s3-training.txt

aws s3api put-object \
  --bucket "$BUCKET" \
  --key "analytics/sample.txt" \
  --body s3-training.txt

aws s3api head-object \
  --bucket "$BUCKET" \
  --key "analytics/sample.txt"
~~~

Object được upload với credentials đang dùng, không cần public ACL. Một bucket riêng tư vẫn có thể được đọc/ghi bởi principal có quyền hợp lệ. Đây là điểm khác biệt giữa **private** và **“không ai truy cập được”**.

### 7.6. Bước 5 — Kiểm tra bucket policy và trạng thái public (chỉ đọc)

~~~bash
aws s3api get-bucket-policy \
  --bucket "$BUCKET"

aws s3api get-bucket-policy-status \
  --bucket "$BUCKET"
~~~

Bucket mới chưa gắn policy có thể trả lỗi `NoSuchBucketPolicy` ở lệnh đầu; điều này bình thường. Với lệnh kiểm tra policy status, dữ liệu có thể khác khi không có policy, quyền thiếu hoặc tính năng đang được quản trị ở cấp khác. Trong mọi trường hợp, kết hợp **BPA + IAM + bucket policy + IAM Access Analyzer** thay vì dùng một lệnh làm bằng chứng tuyệt đối.

Bài lab **không yêu cầu ghi bucket policy public**. Nếu muốn luyện viết JSON, hãy lưu ví dụ policy trong tài liệu, phân tích hiệu lực và chỉ triển khai trong sandbox có quy trình review.

### 7.7. Bước 6 (tùy chọn) — Tạo Access Point chỉ cho phép nguồn VPC

**Điều kiện bổ sung:** bạn được cấp một VPC sandbox thực sự, có quyền tạo S3 Access Point và biết cách truy cập S3 qua VPC/network hợp lệ. Đừng dùng VPC ID minh họa như một tài nguyên có thật.

~~~bash
VPC_ID=vpc-0123456789abcdef0
AP_NAME="aws-lab-analytics-$RANDOM"

aws s3control create-access-point \
  --account-id "$ACCOUNT_ID" \
  --name "$AP_NAME" \
  --bucket "$BUCKET" \
  --vpc-configuration "VpcId=$VPC_ID" \
  --public-access-block-configuration \
    "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

aws s3control get-access-point \
  --account-id "$ACCOUNT_ID" \
  --name "$AP_NAME"
~~~

Kiểm tra `NetworkOrigin` là `VPC`, `VpcConfiguration.VpcId` đúng và bốn cờ BPA đã bật.

**Cảnh báo về mục tiêu lab:** vừa tạo Access Point không có nghĩa bạn đã có quyền đọc object **qua Access Point**. Cần có **bucket policy và Access Point policy phù hợp**, IAM role có quyền, đường mạng từ VPC và nếu dùng SSE-KMS thì quyền KMS. Việc dựng một policy hợp lệ cho bài học nên được kiểm tra trước, dựa trên ví dụ ở mục 5; không thử mở public để “cho chạy nhanh”.

Để xem Access Point policy nếu đã có:

~~~bash
aws s3control get-access-point-policy \
  --account-id "$ACCOUNT_ID" \
  --name "$AP_NAME"
~~~

Nếu `NoSuchAccessPointPolicy`, Access Point chưa có policy riêng; đây là trạng thái có thể xảy ra ngay sau khi tạo. Với Access Point origin VPC, gọi API từ CloudShell/laptop ngoài VPC không phải phép thử hợp lệ cho đường truy cập này.

### 7.8. Bước 7 — Dọn tài nguyên đúng thứ tự

Nếu đã tạo Access Point và có quyền xóa, xóa Access Point **trước**:

~~~bash
aws s3control delete-access-point \
  --account-id "$ACCOUNT_ID" \
  --name "$AP_NAME"
~~~

Chỉ chạy bước trên nếu bạn **thực sự đã tạo** Access Point có tên trong biến `AP_NAME`. Sau đó xóa object và bucket của lab:

~~~bash
aws s3api delete-object \
  --bucket "$BUCKET" \
  --key "analytics/sample.txt"

aws s3api delete-bucket \
  --bucket "$BUCKET" \
  --region "$REGION"
~~~

Bucket phải **trống** để xóa. Nếu bạn bật versioning, tạo thêm object, multipart uploads hoặc replication, cần xem vòng đời và dọn thêm theo quy trình tương ứng. Có thể xóa file `s3-training.txt` trên máy sau khi không còn cần. Kiểm tra lại trên Console/CLI để bảo đảm Access Point và bucket lab đã biến mất.

**Không xóa Access Point hoặc bucket đang dùng chung**. Ghi tên/ID tài nguyên đã tạo trước khi đóng terminal; việc làm mất biến shell không khiến tài nguyên AWS tự biến mất.

## 8. Cách chẩn đoán AccessDenied và cấu hình bị public

### 8.1. Quy trình đọc lỗi theo tầng

1. **Danh tính:** dùng `aws sts get-caller-identity` để xác nhận IAM principal/role session và account.
2. **Đường truy cập:** request đi **trực tiếp qua bucket** hay **qua Access Point ARN/alias**?
3. **Mạng:** với VPC-origin Access Point, client có thực sự đến từ VPC được chỉ định? VPC endpoint, route, DNS và endpoint policy đúng chưa?
4. **Hành động và ARN:** `ListBucket` đang dùng bucket/access point ARN đúng loại? `GetObject` đang dùng object ARN đúng prefix?
5. **Quyền:** kiểm tra IAM identity policy, bucket policy, Access Point policy, permissions boundary, session policy, SCP/RCP khi áp dụng, và KMS key policy nếu dùng SSE-KMS.
6. **Block Public Access:** có public ACL/policy bị chặn? Account/organization đã áp cờ chặt hơn chưa?
7. **Dấu vết:** đọc AWS error message, CloudTrail (bao gồm data events nếu đã bật), S3 server access logging khi cấu hình, IAM Access Analyzer findings và AWS Config/Security Hub nếu tổ chức sử dụng.
8. **Khắc phục tối thiểu:** sửa đúng lớp thiếu quyền hoặc cấu hình sai; không dùng `Principal: "*"` hay tắt BPA để bỏ qua lỗi.

### 8.2. Bảng tình huống

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `PutBucketPolicy` báo policy public bị chặn | `BlockPublicPolicy` bật ở bucket/account/organization | Xem statement có wildcard/condition chưa đáng tin cậy; thiết kế policy non-public |
| `PutObject` kèm `public-read` bị từ chối | `BlockPublicAcls` hoặc Object Ownership Bucket owner enforced | Bỏ public ACL; quản trị quyền bằng policy |
| ACL cũ ghi `AllUsers` nhưng object không đọc công khai được | `IgnorePublicAcls` hoặc giới hạn public khác | Giữ bảo vệ và loại bỏ ACL công khai cũ theo quy trình |
| Bucket policy cho phép account đối tác nhưng cross-account vẫn bị từ chối | `RestrictPublicBuckets` vì policy được S3 nhận diện public, hoặc IAM/SCP/KMS thiếu quyền | Kiểm tra `get-bucket-policy-status`, sửa policy thành non-public và xác minh cross-account |
| Access Point policy đã `Allow` nhưng vẫn `AccessDenied` | Underlying bucket policy chưa cho phép request qua AP hoặc IAM/KMS/BPA hạn chế | Đối chiếu hai policy và ARN object/access point |
| VPC-origin Access Point không dùng được từ laptop/CloudShell | Client không thuộc VPC đã chỉ định | Kiểm thử từ workload trong VPC qua network path hợp lệ |
| Gọi S3 trực tiếp vẫn đọc được dù Access Point chỉ cho một nhóm | Bucket/identity policy đang cho phép đường trực tiếp | Rà soát toàn bộ đường cấp quyền; cân nhắc buộc truy cập qua AP khi phù hợp |
| `GetBucketPolicy` trả `NoSuchBucketPolicy` | Chưa có bucket policy | Không nhầm với Block Public Access tắt hoặc bucket public |
| Tên bucket/Access Point bị lỗi hoặc trùng | Vi phạm quy tắc tên, namespace hoặc Region | Kiểm tra quy tắc tên và Region hỗ trợ |
| Không đổi được network origin hoặc BPA của Access Point | Những thuộc tính này cố định lúc tạo | Lập kế hoạch xóa/tạo lại AP và cập nhật client |
| Truy cập SSE-KMS object bị 403 dù có `s3:GetObject` | KMS permissions/key policy/condition không khớp | Kiểm tra `kms:Decrypt` và KMS key policy phù hợp |
| Access Analyzer cho thấy external access ngoài dự kiến | Bucket policy, Access Point policy hoặc ACL có đường cấp quyền rộng | Xác nhận principal/đường cấp, điều chỉnh non-public policy và BPA |

### 8.3. Phân biệt sự cố kết nối với sự cố quyền

- **Timeout/DNS failure:** ưu tiên kiểm tra VPC DNS, endpoint, route table, security group và mạng.
- **HTTP 403 AccessDenied:** kết nối đến dịch vụ thường đã thiết lập; phân tích policy và tính hợp lệ của request.
- **`NoSuchKey` hoặc 404:** kiểm tra object key, bucket/Region và quyền; vì lý do bảo mật, S3 có thể trả lỗi khác nhau tùy quyền `ListBucket` của principal.
- **`AccessControlListNotSupported`:** kiểm tra Object Ownership Bucket owner enforced và logic upload có gửi ACL hay không.

Không kết luận nguyên nhân chỉ từ mã HTTP mà không đọc đầy đủ context.

## 9. Bảo mật theo mô hình phòng thủ nhiều lớp

### 9.1. Mẫu kiến trúc ứng dụng dùng S3 riêng tư

~~~mermaid
flowchart LR
    U[Người dùng ứng dụng] --> A[API Gateway / ALB]
    A --> W[Lambda / EC2 application role]
    W --> V[VPC endpoint nếu dùng VPC]
    V --> P[S3 Access Point origin VPC]
    P --> B[(Private S3 bucket)]
    I[IAM least privilege] -.-> W
    E[Access Point policy] -.-> P
    C[Bucket policy + BPA + SSE-KMS] -.-> B
    M[CloudTrail / Access Analyzer / CloudWatch] -. Giám sát .-> B
~~~

Các lớp nên có:

1. **Identity-based IAM**: cấp cho ứng dụng đúng API và object prefix cần dùng.
2. **Access Point**: tách luồng truy cập giữa các thành phần; dùng VPC-origin nếu đường mạng riêng là yêu cầu.
3. **Bucket policy**: ủy quyền Access Point được duyệt và chặn những hành vi không phù hợp.
4. **Block Public Access**: bật cả bốn ở cấp account/bucket/AP, cân nhắc cấp tổ chức; không mở public vì tiện trong lúc phát triển.
5. **Encryption**: S3 mặc định mã hóa phía server cho các object mới; nếu yêu cầu kiểm soát khóa thì chọn SSE-KMS theo chính sách.
6. **Audit**: dùng CloudTrail management events và S3 **data events** khi cần kiểm tra object operations; data events có thể phát sinh phí nếu bật, không phải mọi object GET/PUT đều nằm trong Event history mặc định.
7. **Data protection**: versioning, replication, lifecycle, Object Lock hoặc AWS Backup khi phù hợp RPO/RTO và yêu cầu lưu giữ.
8. **Cost governance**: theo dõi storage class, request count, lifecycle transitions, replication, KMS requests, logs và data transfer.

S3 được thiết kế có độ bền cao, nhưng **độ bền không bảo vệ khỏi tất cả thao tác xóa nhầm, ghi đè, sai chính sách hoặc yêu cầu compliance**. Cần lựa chọn biện pháp dữ liệu theo mục tiêu phục hồi.

### 9.2. CloudFront và Presigned URL

Đối với trang web cần phục vụ ảnh/tệp:

- Giữ S3 bucket **private**.
- Dùng **Amazon CloudFront Origin Access Control (OAC)** để CloudFront đọc bucket theo policy giới hạn, kết hợp cache, TLS và các biện pháp CDN phù hợp.
- Dùng **presigned URL** khi muốn cấp quyền truy cập tạm thời cho object cụ thể; URL mang chữ ký theo credentials của người ký và có thời hạn, cần bảo vệ khỏi bị lộ.
- **CORS** chỉ kiểm soát hành vi truy cập qua trình duyệt, không phải IAM authorization hay cơ chế công khai object.

Không tắt Block Public Access chỉ để đưa một ảnh lên frontend; trước tiên xem mô hình phân phối tệp phù hợp.

## 10. Bài tập thiết kế và suy luận quyền hiệu lực

### 10.1. Tình huống

Một công ty dùng một bucket `school-content` chứa:

~~~text
school-content/
├── public-preview/
├── student-reports/
├── teacher-materials/
└── exports/
~~~

Có ba workload:

- **Student API:** đọc `student-reports/` theo quy tắc ứng dụng; mỗi học viên chỉ được thấy dữ liệu của mình.
- **Teacher Portal:** đọc `teacher-materials/` và một số báo cáo.
- **Export worker:** chỉ ghi object mới vào `exports/` từ một VPC.
- **Public preview:** nội dung xem trước cho người dùng web, muốn phân phối qua CDN.

Yêu cầu: không cho anonymous S3 access; quản lý tách quyền nhóm; chi phí có thể theo dõi; audit thay đổi quyền; có khả năng phục hồi khi xóa nhầm object.

### 10.2. Đề xuất thiết kế

| Thành phần | Quyết định | Lý do |
|---|---|---|
| Bucket | `school-content`, private, BPA cả bốn bật | Mặc định khóa public access |
| Student API | Role riêng + Access Point chỉ cho prefix phù hợp | Tách quyền ứng dụng; vẫn phải enforce quyền **từng học viên** ở tầng nghiệp vụ |
| Teacher Portal | Role riêng + Access Point với policy giới hạn | Tránh dùng role chung với Student API |
| Export worker | VPC-origin Access Point và IAM chỉ có `PutObject` vào `exports/` | Hạn chế network origin và quyền ghi |
| Public preview | CloudFront + OAC | Phân phối công khai qua CDN nhưng S3 origin private |
| Audit | IAM Access Analyzer, CloudTrail data events khi cần, kiểm tra policy định kỳ | Phát hiện quyền ngoài dự kiến |
| Recovery | Versioning và lifecycle/backup theo RPO/RTO | Giảm rủi ro xóa nhầm, kiểm soát chi phí lưu version |
| Cost | Tags, AWS Budgets, S3 Storage Lens/Cost Explorer nếu phù hợp | Theo dõi dung lượng, request, chuyển class và CDN |

**Chú ý:** S3 IAM/bucket policy dựa vào principal và context AWS; **không tự biết học viên nào đang đăng nhập vào ứng dụng** nếu nhiều học viên cùng đi qua một IAM role backend. Backend phải xác thực người dùng và kiểm soát tenant/student ID trước khi đọc object, hoặc thiết kế cách ánh xạ danh tính và object keys được kiểm thử kỹ.

### 10.3. Câu hỏi thực hành

1. Tại sao `s3:ListBucket` cần ARN khác `s3:GetObject`?
2. Nếu bucket policy có `Allow` cho role A nhưng Access Point policy chỉ cho role B, request của A qua Access Point đó có thành công không? Vì sao?
3. Nếu account-level BPA bật cả bốn nhưng bucket-level BPA tắt, object có tự thành public không?
4. Access Point origin `Internet` có nghĩa mọi người trên Internet được xem object hay không?
5. Vì sao không nên tắt `BlockPublicPolicy` chỉ để áp một bucket policy chứa `Principal: "*"`?
6. Nếu muốn dùng `aws:SourceVpce` trong bucket policy, điều gì cần kiểm thử trước khi dùng `Deny` rộng?
7. Bucket policy delegation cho Access Point có ngăn mọi request trực tiếp đến bucket không?
8. Tại sao presigned URL không tương đương “mở bucket public”?
9. Khi Student API dùng chung một IAM role cho tất cả học viên, IAM có tự bảo vệ object của từng học viên không?
10. Dữ liệu đã bị xóa nhầm cần cơ chế phục hồi nào ngoài Block Public Access?

## 11. Checklist trước khi đưa S3 vào production

### 11.1. Quyền truy cập

- [ ] Chủ sở hữu bucket, account, Region và loại bucket đã được xác định.
- [ ] Bucket/Object Ownership được cấu hình phù hợp, hạn chế sử dụng ACL.
- [ ] Account/bucket/Access Point có BPA phù hợp; cân nhắc bảo vệ cấp Organizations.
- [ ] Bucket policy và Access Point policy đã được review bằng IAM Access Analyzer.
- [ ] Principal dùng role tạm thời và least privilege; không nhúng access key vào code.
- [ ] Các object ARN, prefix, tags và điều kiện IAM khớp đúng workload.
- [ ] Cross-account access được duyệt và bucket owner cho phép rõ ràng.
- [ ] Nếu dùng VPC-origin AP, đã kiểm tra đúng VPC endpoint, DNS, routing, network origin và chính sách.
- [ ] Nếu dùng SSE-KMS, KMS key policy và IAM permissions đã được kiểm thử.

### 11.2. Vận hành

- [ ] CloudTrail logs, data events và Access Analyzer được cấu hình theo yêu cầu audit.
- [ ] Có cơ chế phát hiện public access/cross-account access ngoài ý muốn.
- [ ] Có versioning/backup/replication/Object Lock khi dữ liệu đòi hỏi, và đã thử restore.
- [ ] Có tagging, lifecycle, cost allocation và cảnh báo ngân sách phù hợp.
- [ ] Có phương án thay policy an toàn, khôi phục khi tự khóa quyền và kiểm thử trước thay đổi lớn.
- [ ] Có quy trình thu hồi Access Point, chính sách và object khi ứng dụng ngừng sử dụng.

## Tài liệu AWS chính thức

- [S3 bucket policies and examples](https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucket-policies.html)
- [Bucket policy examples](https://docs.aws.amazon.com/AmazonS3/latest/userguide/example-bucket-policies.html)
- [Blocking public access to S3 storage](https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-control-block-public-access.html)
- [Configuring account-level Block Public Access](https://docs.aws.amazon.com/AmazonS3/latest/userguide/configuring-block-public-access-account.html)
- [S3 Object Ownership](https://docs.aws.amazon.com/AmazonS3/latest/userguide/about-object-ownership.html)
- [Managing access to shared datasets with S3 Access Points](https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-points.html)
- [Access Point policy examples and delegation](https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-points-policies.html)
- [Creating VPC-restricted S3 Access Points](https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-points-vpc.html)
- [Managing Access Point Block Public Access settings](https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-points-bpa-settings.html)
- [Troubleshooting S3 403 AccessDenied](https://docs.aws.amazon.com/AmazonS3/latest/userguide/troubleshoot-403-errors.html)
- [IAM Access Analyzer for S3](https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-analyzer.html)
- [AWS Organizations S3 policies](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_s3_syntax.html)

> **Lưu ý khi áp dụng:** Tên bucket, account ID, VPC ID, role ARN và Access Point ARN trong bài đều là ví dụ. Không sao chép policy minh họa vào production khi chưa hợp nhất với cấu hình đang có và kiểm tra hiệu lực thật. Tài liệu AWS được cập nhật theo thời gian; trước khi triển khai, hãy xác minh hỗ trợ tính năng, hành vi policy, chi phí và hạn mức hiện hành trong Region/account của bạn.
