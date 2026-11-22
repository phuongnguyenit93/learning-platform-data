# IAM user, group, role và policy

> **Chương:** IAM và phân quyền  
> **Module:** CLOUD_PROVIDERS_AWS — khám phá hệ sinh thái AWS từ Region/Availability Zone (AZ), IAM và VPC đến compute, storage, database, integration, serverless; thực hành chọn dịch vụ, thiết kế ứng dụng an toàn, có giám sát, phục hồi và kiểm soát chi phí.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **IAM user**, **IAM group**, **IAM role** và **IAM policy**; giải thích vai trò của từng thành phần trong quản trị quyền AWS.
2. Phân tích sự khác nhau giữa danh tính dài hạn và phiên truy cập tạm thời từ AWS Security Token Service (STS).
3. Đọc và viết các policy JSON cơ bản, xác định rõ **Effect**, **Action**, **Resource** và **Condition**.
4. Phân biệt **permissions policy** với **trust policy** và giải thích cách dịch vụ hoặc account khác có thể assume role.
5. Dự đoán kết quả phân quyền qua quy tắc mặc định từ chối, allow, explicit deny và những giới hạn như SCP, permissions boundary, session policy.
6. Thiết kế quyền tối thiểu cho người vận hành và ứng dụng sử dụng S3, EC2, Lambda, RDS trong VPC; biết cách kiểm tra cấu hình và tìm nguyên nhân AccessDenied.

## 1. IAM giải quyết vấn đề gì?

Khi mới sử dụng AWS, một người có thể tạo máy EC2, đọc object S3, thay đổi bảng dữ liệu RDS hoặc triển khai Lambda từ cùng một tài khoản. Nếu mọi người đều dùng chung thông tin đăng nhập có toàn quyền, hệ thống sẽ khó kiểm soát việc ai thực hiện thao tác nào, dễ lộ thông tin xác thực và gây thiệt hại khi một tài khoản bị chiếm quyền.

**AWS Identity and Access Management (IAM)** là dịch vụ giúp xác định **ai hoặc workload nào được phép thực hiện hành động nào trên tài nguyên nào, trong điều kiện gì**. IAM có hai nhóm khái niệm trọng tâm:

- **Danh tính (identity/principal):** người dùng hoặc phần mềm gửi yêu cầu tới AWS. Danh tính có thể là IAM user hoặc phiên được cấp từ IAM role, cùng những loại principal khác mà AWS hỗ trợ.
- **Chính sách (policy):** các quy tắc mô tả quyền được phép hoặc bị từ chối đối với hành động trên tài nguyên cụ thể.

Ví dụ, API xử lý đơn hàng chạy trên Lambda chỉ cần đọc hóa đơn ở một prefix trong S3. Thay vì gắn quyền quản trị, ta tạo role chuyên dụng và cấp đúng quyền **s3:GetObject** trên các object cần đọc.

Một câu hỏi thiết kế quan trọng là: **Ai cần quyền gì để làm công việc, trong thời gian nào và với phạm vi nhỏ đến đâu?** Đây là nguyên tắc **least privilege**.

### IAM là dịch vụ toàn cục, nhưng quyền truy cập có thể liên quan từng Region

IAM user, group, role và policy của một AWS account không được tạo riêng cho từng Region theo cách EC2 instance hay subnet được tạo. Tuy nhiên, quyền một identity có thể áp dụng đến tài nguyên có ARN theo Region, và vẫn có những giới hạn theo chính sách, tổ chức, dịch vụ hoặc điều kiện truy cập. Chuyển Region trong AWS Console không làm phát sinh một hệ IAM user mới.

IAM là một phần trong **Shared Responsibility Model**: AWS vận hành nền tảng IAM; khách hàng quyết định danh tính, thông tin xác thực, policy, MFA và cách sử dụng quyền trong môi trường của mình.

## 2. Bốn thành phần cốt lõi

| Thành phần | Bản chất | Có tự đăng nhập/gửi yêu cầu tới AWS? | Nơi cấp hoặc gắn quyền thường gặp |
| --- | --- | --- | --- |
| **IAM user** | Danh tính lâu dài trong một AWS account; có thể có mật khẩu console và/hoặc access key. | Có, nếu được cấp thông tin xác thực phù hợp. | Policy trực tiếp hoặc nhận policy qua group. |
| **IAM group** | Tập hợp IAM user để quản lý quyền theo nhóm. | **Không**. Group không phải principal đăng nhập hay được assume. | Policy gắn vào group được áp dụng cho các user thành viên. |
| **IAM role** | Danh tính chứa quyền được một principal được tin cậy **assume** để nhận phiên truy cập tạm thời. | Có, thông qua phiên role/temporary credentials; bản thân role không có mật khẩu hoặc access key dài hạn. | Permissions policy gắn vào role, kết hợp trust policy quyết định ai được assume. |
| **IAM policy** | Tài liệu chính sách, thường ở định dạng JSON, định nghĩa allow/deny và điều kiện. | Không. | Có thể gắn vào identity, tài nguyên được hỗ trợ hoặc dùng làm chính sách giới hạn/tin cậy tùy loại. |

Không nên hiểu **group là một loại role**, hoặc **role chỉ dành cho máy chủ**. Group tổ chức quyền cho IAM user; role có thể được assume bởi dịch vụ AWS, một IAM principal, hoặc người dùng đăng nhập qua cơ chế liên kết danh tính phù hợp.

~~~mermaid
flowchart LR
    U["IAM user"] -->|"là thành viên"| G["IAM group"]
    G -->|"gắn"| GP["Permissions policy"]
    U -->|"có thể gắn trực tiếp"| UP["Permissions policy"]
    X["Ứng dụng / người dùng / principal tin cậy"] -->|"STS: assume role"| R["IAM role"]
    T["Trust policy"] -->|"xác định ai được assume"| R
    R -->|"gắn"| RP["Permissions policy"]
    GP --> RES["Quyền truy cập tài nguyên AWS"]
    UP --> RES
    RP --> RES
~~~

Sơ đồ minh họa quan hệ; **quyền truy cập thực tế còn phụ thuộc các policy liên quan và những điều kiện kiểm soát khác**, không phải cứ có một policy Allow là chắc chắn được phép.

## 3. IAM user: danh tính dài hạn trong một account

IAM user đại diện cho một danh tính được quản lý trực tiếp trong AWS account. User có thể có:

- **Console password** để đăng nhập AWS Management Console.
- **Access key ID và secret access key** để ký các yêu cầu API/CLI/SDK theo cơ chế access key.
- **MFA** và các thiết lập bảo mật bổ sung.
- Policy được gắn trực tiếp hoặc được kế thừa thông qua các IAM group.

**Không phải IAM user nào cũng cần cả console password và access key.** Cấp thêm thông tin xác thực khi không cần thiết làm tăng bề mặt tấn công.

Ví dụ, một hệ thống cũ chỉ hỗ trợ thông tin xác thực dài hạn có thể cần IAM user riêng trong trường hợp chưa thể dùng role/federation. Nhóm vận hành phải bảo vệ secret, giới hạn policy, giám sát việc sử dụng và có kế hoạch thay thế bằng temporary credentials khi khả thi.

### Tài khoản root khác IAM user

Khi tạo AWS account, tài khoản có **root user** gắn với tài khoản đó. Root user không phải IAM user thông thường và có khả năng thực hiện những tác vụ nhạy cảm ở cấp account. Hãy bảo vệ root bằng MFA, không chia sẻ thông tin xác thực, tránh tạo access key root và chỉ dùng khi thực sự cần các tác vụ dành riêng cho root.

### Lựa chọn cho người dùng doanh nghiệp: IAM Identity Center

Với con người thường xuyên đăng nhập môi trường AWS, AWS khuyến nghị ưu tiên **federation và temporary credentials**. AWS IAM Identity Center hỗ trợ cấp quyền người dùng đến nhiều AWS account và ứng dụng thông qua **permission set**. Khi đăng nhập, người dùng nhận phiên truy cập dựa trên vai trò phù hợp; không cần mỗi nhân viên sở hữu một IAM user với access key dài hạn trong từng account.

**Phân biệt:** IAM Identity Center user/group thuộc hệ thống danh tính quản lý bởi Identity Center hoặc nguồn danh tính kết nối; không đồng nhất với IAM user/group được tạo trực tiếp trong một AWS account.

## 4. IAM group: quản lý quyền theo nhóm công việc

Group giúp gộp các user cùng nhu cầu truy cập. Ví dụ:

| Group minh họa | Quyền mong muốn | Không cần cấp |
| --- | --- | --- |
| **S3ReportReaders** | Đọc báo cáo trong bucket được chỉ định. | Xóa bucket, sửa policy, tạo EC2. |
| **SupportViewers** | Xem thông tin vận hành cần thiết. | Sửa hạ tầng production. |
| **BillingReviewers** | Xem dữ liệu billing/cost đã được cấp. | Thay đổi IAM hoặc tài nguyên ứng dụng. |

Khi policy gắn vào group, thành viên nhận các quyền do policy group quy định, chịu tác động của mọi giới hạn và deny khác áp dụng cho người dùng đó. Nếu người dùng rời group thì các quyền bắt nguồn từ group ấy không còn, nhưng họ có thể vẫn có quyền từ policy khác.

Các điểm cần nhớ:

1. Group chỉ chứa **IAM user** trong AWS account đó, không chứa role hoặc group khác.
2. Group **không** có mật khẩu, access key, trust policy và không thể được assume.
3. Group quản lý quyền hiệu quả khi có nhiều IAM user; trong tổ chức dùng Identity Center, nên quản trị nhóm/permission set ở cơ chế Identity Center tương ứng.
4. Sử dụng group không tự động bảo đảm least privilege: policy gắn vào group vẫn có thể quá rộng.

## 5. IAM role: quyền theo phiên truy cập tạm thời

Role chứa một tập quyền nhưng không có thông tin xác thực dài hạn như IAM user. Một principal được tin cậy có thể **assume role** để nhận temporary credentials, thông thường thông qua AWS STS. Phiên này có thời hạn và thể hiện trong CloudTrail bằng thông tin danh tính của role session.

Các tình huống tiêu biểu:

- **Lambda execution role** cho phép function ghi log và truy cập S3/DynamoDB/RDS hoặc dịch vụ khác theo yêu cầu.
- **EC2 instance role** cho ứng dụng đang chạy trên EC2 lấy temporary credentials qua instance profile/instance metadata, thay vì nhúng access key vào mã nguồn.
- **ECS task role** trao quyền riêng cho ứng dụng trong task; phân biệt với task execution role phục vụ những thao tác ECS/Fargate cần thực hiện.
- **Cross-account role** cho một principal ở AWS account A assume role thuộc account B.
- **Federated access** cho nhân viên đăng nhập qua cơ chế xác thực ngoài AWS rồi nhận phiên role được cấp.

### 5.1. Role có hai loại policy quan trọng

**Trust policy** (role trust policy) trả lời câu hỏi: **principal nào được phép assume role và qua hành động/điều kiện nào?**

**Permissions policy** trả lời câu hỏi: **sau khi assume thành công, phiên role có thể thực hiện những hành động gì trên tài nguyên nào?**

Hai policy này bổ trợ nhau. **Trust rộng** có thể cho nhiều principal assume được role; **permissions rộng** có thể khiến role làm được quá nhiều việc. Thiết kế an toàn cần giới hạn cả hai.

### 5.2. Ví dụ: execution role của Lambda

Giả sử function **InvoiceReader** đọc các hóa đơn trong S3. Trust policy của role có thể là:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

- **Principal** xác định dịch vụ Lambda được phép assume role theo cơ chế của dịch vụ.
- **Action** là **sts:AssumeRole**; đây là quyền assume role, không phải quyền đọc S3.
- Khi gắn role cho function, người triển khai cũng phải có các quyền tạo/cập nhật function và quyền **iam:PassRole** thích hợp; việc có PassRole riêng lẻ không đồng nghĩa có quyền assume role.

Permissions policy gắn vào chính role:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadInvoicesOnly",
      "Effect": "Allow",
      "Action": ["s3:GetObject"],
      "Resource": [
        "arn:aws:s3:::example-private-invoices/approved/*"
      ]
    }
  ]
}
~~~

Role này chỉ nhận quyền **s3:GetObject** đối với object bên dưới prefix **approved/** trong bucket minh họa. Nó không tự động có quyền xóa object, liệt kê bucket, đọc bucket khác hoặc sửa IAM. Nếu function còn cần ghi log hoặc gọi dịch vụ khác, phải xem xét và cấp các quyền phù hợp riêng, chẳng hạn thông qua policy ghi CloudWatch Logs có phạm vi thích hợp.

**Bucket ARN và object ARN khác nhau:**

- **arn:aws:s3:::example-private-invoices** trỏ tới bucket.
- **arn:aws:s3:::example-private-invoices/approved/*** trỏ tới tập object có key bắt đầu bằng **approved/**.

Trong một identity-based policy, **s3:ListBucket** thường yêu cầu ARN cấp bucket; **s3:GetObject** yêu cầu ARN cấp object. Nhầm lẫn hai loại ARN là nguyên nhân rất phổ biến gây AccessDenied.

### 5.3. Quy trình assume role

~~~mermaid
sequenceDiagram
    participant P as Principal / ứng dụng
    participant S as AWS STS
    participant R as IAM role
    participant A as Dịch vụ AWS
    P->>S: Yêu cầu assume role
    S->>R: Kiểm tra trust và các điều kiện liên quan
    R-->>S: Được phép assume?
    S-->>P: Temporary credentials nếu hợp lệ
    P->>A: Gửi API request được ký bằng credentials của role session
    A-->>P: Allow hoặc AccessDenied theo policy evaluation
~~~

Role không phải một “tài khoản đăng nhập” với mật khẩu cố định. Một role có thể được nhiều phiên assume và mỗi phiên có thời hạn. Khi phiên hết hạn, ứng dụng cần nhận phiên mới theo cơ chế được dịch vụ/SDK hỗ trợ.

### 5.4. Truy cập khác account (cross-account)

Giả sử hệ thống triển khai ở account **111122223333** cần đọc một số tài nguyên trong account **444455556666**. Mô hình thường dùng:

1. Trong account đích, tạo role **ReportReader** với **permissions policy** cho phép đúng hành động trên đúng tài nguyên.
2. Trust policy của role ở account đích cho phép một principal cụ thể từ account nguồn assume role.
3. Principal nguồn có quyền **sts:AssumeRole** đối với role đích và thỏa các điều kiện liên quan.
4. Principal nguồn assume role, nhận temporary credentials rồi dùng quyền của role đích.

Ví dụ trust policy ở account đích giới hạn quyền assume cho role **DeployOperator** thuộc account nguồn:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::111122223333:role/DeployOperator"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

Đây là ví dụ minh họa với account ID giả định. Với nhà cung cấp thứ ba, có thể cần điều kiện **sts:ExternalId** và biện pháp kiểm soát bổ sung để giảm rủi ro confused deputy. Nên trust một principal phù hợp và tránh mở rộng không cần thiết tới cả account.

## 6. IAM policy: mô tả quyền bằng JSON

IAM policy là tài liệu chính sách gồm các statement. Cú pháp cơ bản:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ViewOneObjectPrefix",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject"
      ],
      "Resource": [
        "arn:aws:s3:::example-training-data/tutorials/*"
      ]
    }
  ]
}
~~~

| Thành phần | Ý nghĩa | Điều cần chú ý |
| --- | --- | --- |
| **Version** | Phiên bản ngôn ngữ policy của IAM. | **2012-10-17** là phiên bản cú pháp thông dụng, **không** phải ngày tạo policy. |
| **Statement** | Một hoặc nhiều quy tắc. | Mỗi statement có Effect, Action/NotAction, Resource/NotResource theo loại policy. |
| **Sid** | Mã nhận diện statement tùy chọn. | Đặt tên giúp review và điều tra. |
| **Effect** | **Allow** hoặc **Deny**. | Explicit Deny có ưu tiên rất cao trong đánh giá quyền. |
| **Action** | API/operation được điều khiển, chẳng hạn **s3:GetObject**. | Tên permission action không phải lúc nào cũng giống hoàn toàn tên API. |
| **Resource** | ARN của tài nguyên được tác động. | Không phải mọi action đều hỗ trợ giới hạn resource; cần xem tài liệu action của dịch vụ. |
| **Condition** | Điều kiện bổ sung, ví dụ prefix, tags, VPC endpoint, MFA hoặc principal attributes khi được hỗ trợ. | Chọn đúng condition key và hiểu dữ liệu ngữ cảnh AWS thực sự cung cấp. |
| **Principal** | Principal được chỉ định trong các resource-based policy/trust policy. | Thông thường **không** đặt Principal trong identity-based permissions policy. |

Chính sách có thể chứa nhiều statement. Viết nhiều statement nhỏ, đặt tên và giới hạn scope cụ thể thường dễ audit hơn một statement với nhiều action và resource không liên quan.

### 6.1. Hai quyền S3 trông giống nhau nhưng khác phạm vi

Giả sử một công cụ xem báo cáo cần liệt kê **chỉ prefix reports/2026/** và đọc các object trong đó:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ListOnlyReportPrefix",
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::example-private-reports",
      "Condition": {
        "StringLike": {
          "s3:prefix": [
            "reports/2026/",
            "reports/2026/*"
          ]
        }
      }
    },
    {
      "Sid": "ReadOnlyReportObjects",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::example-private-reports/reports/2026/*"
    }
  ]
}
~~~

Cách đọc policy:

- **ListBucket** tác động ở **cấp bucket**, bị giới hạn theo tiền tố request.
- **GetObject** tác động ở **cấp object**, chỉ đọc được object theo mẫu ARN cho phép.
- Policy không cấp **s3:PutObject**, **s3:DeleteObject** hay **s3:PutBucketPolicy**.
- Quyền thực tế có thể còn bị chặn bởi policy của bucket, SCP, KMS key policy hoặc các giới hạn khác.

**Condition s3:prefix chỉ kiểm soát yêu cầu liệt kê khi action và ngữ cảnh hỗ trợ condition đó**; không thể dùng thay cho giới hạn object ARN của GetObject.

### 6.2. Managed policy và inline policy

| Loại | Đặc điểm | Khi nào phù hợp |
| --- | --- | --- |
| **AWS managed policy** | AWS tạo và duy trì; có thể dùng nhanh cho các vai trò phổ biến. | Học cách hoạt động hoặc xây nền quyền ban đầu; cần review vì có thể rộng hơn nhu cầu thực. |
| **Customer managed policy** | Khách hàng tự tạo, quản lý phiên bản và có thể gắn cho nhiều IAM identity. | Phù hợp khi cần tái sử dụng tập quyền được kiểm soát cụ thể. |
| **Inline policy** | Policy nằm gắn trực tiếp và có vòng đời gắn với một user, group hoặc role. | Quyền đặc thù chỉ dành cho một identity và muốn gắn chặt với identity đó. |

Một policy gắn vào IAM user/group/role là **identity-based policy**. Một policy gắn trên tài nguyên như S3 bucket hoặc AWS KMS key có thể là **resource-based policy**. Hai nhóm này khác về chỗ đặt policy, principal và cách tham gia đánh giá quyền.

### 6.3. Trust policy là trường hợp đặc biệt của resource-based policy

Role trust policy khai báo principal nào có thể assume role. Nó không trao quyền thao tác S3 hay EC2 sau khi assume. Permissions policy gắn vào role lại mô tả các hành động trong phiên đó. Chỉ khi cả điều kiện assume role và điều kiện thực hiện API sau khi assume đều được đáp ứng thì workflow mới chạy thành công.

## 7. AWS đánh giá một yêu cầu truy cập ra sao?

Quy tắc nền tảng:

1. **Mặc định từ chối (implicit deny):** nếu không tìm được quyền cho phép phù hợp, yêu cầu bị từ chối.
2. **Explicit Allow:** một statement cho phép action trên resource trong ngữ cảnh phù hợp có thể mở đường cho yêu cầu.
3. **Explicit Deny:** nếu có chính sách áp dụng từ chối tường minh, yêu cầu bị từ chối, ngay cả khi chính sách khác có Allow.
4. **Giới hạn cấp cao:** các loại policy như permissions boundary, SCP/RCP trong AWS Organizations và session policy có thể giới hạn quyền hiệu lực; riêng chúng **không tự cấp quyền**.
5. **Kiểm soát của dịch vụ:** điều kiện của resource policy, KMS key policy, ownership, mạng hoặc yêu cầu cụ thể của dịch vụ vẫn có thể ảnh hưởng khả năng hoàn thành thao tác.

### 7.1. Mô hình khái quát

~~~mermaid
flowchart TD
    Q["API request: principal + action + resource + context"] --> D{"Có explicit Deny áp dụng?"}
    D -->|"Có"| NO["Deny"]
    D -->|"Không"| A{"Có Allow hợp lệ?"}
    A -->|"Không"| NO
    A -->|"Có"| L{"Thỏa các giới hạn như SCP, boundary, session policy và quy tắc dịch vụ?"}
    L -->|"Không"| NO
    L -->|"Có"| YES["Có thể Allow"]
~~~

Sơ đồ này là **mô hình học tập**, không thay thế thuật toán đầy đủ của AWS: quyền từ identity-based và resource-based policy thường được xét theo cơ chế kết hợp; ngoại lệ phụ thuộc kiểu principal, quyền cấp trực tiếp cho role session hoặc user, loại resource policy và mô hình cross-account. Với cross-account, còn cần quyền phù hợp ở cả phía caller và resource/account đích tùy hình thức truy cập. Khi cần kết luận cuối cùng, phải đối chiếu **Policy evaluation logic** của AWS cho đúng trường hợp.

### 7.2. Các loại policy thường gặp trong một request

| Chính sách | Dùng để làm gì? | Có tự cấp quyền sử dụng tài nguyên không? |
| --- | --- | --- |
| **Identity-based permissions policy** | Cấp hoặc deny action cho user, group hoặc role. | Có thể cấp Allow, nếu không bị chặn bởi chính sách/điều kiện khác. |
| **Resource-based policy** | Cấp hoặc deny quyền truy cập tài nguyên được hỗ trợ, xác định principal phù hợp. | Có thể cấp Allow theo cơ chế dịch vụ/loại principal. |
| **Role trust policy** | Xác định ai được phép assume role. | Chỉ liên quan quyền assume role, không tự cấp quyền làm việc với dịch vụ khác. |
| **Service control policy (SCP)** | Đặt giới hạn quyền tối đa cho account/principal chịu quản lý bởi AWS Organizations theo phạm vi áp dụng. | Không. |
| **Resource control policy (RCP)** | Hạn chế quyền tối đa có thể truy cập tài nguyên thuộc phạm vi áp dụng trong Organizations, theo loại tài nguyên hỗ trợ. | Không. |
| **Permissions boundary** | Giới hạn quyền mà identity-based policy có thể cấp cho IAM user hoặc role. | Không. |
| **Session policy** | Có thể giới hạn thêm quyền của một role/federated session khi tạo phiên. | Không. |
| **KMS key policy** | Xác định ai có thể quản lý hoặc sử dụng khóa KMS; cùng các cơ chế quyền KMS khác. | Có thể cấp quyền trong ngữ cảnh KMS, theo mô hình riêng của KMS. |

### 7.3. Ví dụ đối chiếu Allow và Deny

Một user được gắn policy Allow **s3:GetObject** trên tất cả object trong bucket A. Nhưng bucket policy có explicit Deny đối với một điều kiện truy cập mà request của user này vi phạm. Kết quả: **AccessDenied**. Cách suy luận “user đã được Allow nên chắc đọc được” là sai vì phải xét mọi chính sách áp dụng.

Ví dụ khác: role có policy Allow **ec2:TerminateInstances**, nhưng SCP của organization không cho action ấy trong account liên quan. Permission policy của role không thể vượt qua giới hạn từ SCP.

### 7.4. Policy là kiểm soát truy cập, không phải tất cả bảo mật

Có quyền gọi API không có nghĩa kết nối mạng sẽ thành công hoặc dữ liệu sẽ sử dụng được:

- **VPC/Security Group** có thể chặn kết nối tới RDS dù IAM cho phép thao tác control-plane liên quan.
- **KMS** có thể yêu cầu quyền sử dụng key và cấu hình key policy phù hợp để giải mã object đã mã hóa bằng KMS key.
- **Cơ sở dữ liệu** có thể cần thông tin xác thực và GRANT/REVOKE ở tầng DB, tùy kiểu xác thực.
- **Ứng dụng** vẫn phải kiểm tra quyền nghiệp vụ người dùng cuối, tránh nhầm IAM của workload với authorization trong ứng dụng.

## 8. IAM trong kiến trúc AWS thực tế

Xét ứng dụng quản lý đơn hàng chạy ở hai AZ:

- ALB xử lý HTTPS phía trước dịch vụ.
- EC2 chạy API trong private subnet, hoặc có thể chuyển sang Lambda khi thiết kế phù hợp.
- RDS lưu dữ liệu đơn hàng; S3 lưu chứng từ.
- CloudWatch/CloudTrail theo dõi hoạt động; KMS hỗ trợ bảo vệ dữ liệu theo yêu cầu.
- Đội triển khai dùng IAM Identity Center để truy cập AWS account thông qua role được cấp.

~~~mermaid
flowchart TB
    H["Kỹ sư vận hành"] -->|"SSO / temporary credentials"| IIC["IAM Identity Center"]
    IIC -->|"permission set / role session"| DEP["Deployment role"]
    DEP -->|"triển khai tài nguyên phù hợp"| APP["Ứng dụng EC2 hoặc Lambda"]
    APP -->|"temporary credentials từ runtime role"| IAM["Application IAM role"]
    IAM -->|"s3:GetObject giới hạn prefix"| S3["S3 chứng từ"]
    IAM -->|"quyền AWS API nếu cần"| DB["RDS / dịch vụ AWS khác"]
    OBS["CloudTrail / CloudWatch"] -.->|"ghi nhận hoạt động phù hợp cấu hình"| IAM
~~~

Lưu ý mũi tên từ role sang RDS chỉ mô tả **quyền gọi các API AWS liên quan**; kết nối SQL đến database là luồng mạng và xác thực riêng, không tự sinh từ IAM role (trừ khi chủ động sử dụng cơ chế IAM database authentication được hỗ trợ).

### Chia role theo chức năng

| Workload/người dùng | Role/quyền đề xuất | Lý do |
| --- | --- | --- |
| Nhân viên phát triển | Role qua Identity Center cho môi trường dev, quyền production theo quy trình kiểm soát. | Không để access key lâu dài trong máy cá nhân hoặc cấp quyền admin không cần thiết. |
| CI/CD pipeline | Deployment role riêng, trust giới hạn bên triển khai và điều kiện phiên; PassRole đúng role cần triển khai. | Giới hạn khả năng thay đổi hạ tầng và nguy cơ leo thang đặc quyền. |
| EC2 API | Instance role chỉ dùng S3 prefix, secret và API thật sự cần. | Ứng dụng nhận temporary credentials, không nhúng secret AWS. |
| Lambda xử lý chứng từ | Execution role với quyền đọc/ghi tài nguyên liên quan; logging phù hợp. | Tách quyền từng function và dễ truy vết. |
| Nhóm hỗ trợ | Role chỉ đọc metric/log cần thiết trong phạm vi được phân công. | Hỗ trợ sự cố mà không cần sửa hạ tầng hoặc dữ liệu. |

**Tách role theo môi trường:** Dev, staging và production có mục tiêu, dữ liệu và mức rủi ro khác nhau. Phân tách IAM role/policy và khi cần cả AWS account giúp hạn chế tác động của sai sót.

**Tách quyền deploy và quyền runtime:** Pipeline có thể cần quyền cập nhật function và PassRole, còn Lambda khi chạy không cần quyền tạo IAM role. Không gộp chúng thành một role toàn quyền.

### Sử dụng IAM để kiểm soát chi phí và phục hồi

IAM không trực tiếp quyết định mức sử dụng tài nguyên hay giá dịch vụ, nhưng giới hạn ai được tạo loại tài nguyên đắt tiền, xóa backup, sửa logging hoặc thay đổi chính sách có thể giúp bảo vệ các biện pháp kiểm soát chi phí và phục hồi. Các công cụ như AWS Budgets, Cost Explorer, CloudTrail và quy trình phê duyệt vẫn cần được cấu hình phù hợp bên cạnh IAM.

## 9. Thực hành đọc và kiểm tra quyền

Phần này dùng **AWS CLI ở chế độ đọc và mô phỏng**; không tự tạo hoặc xóa IAM user, role, policy. Bạn cần AWS CLI đã cấu hình, một identity được phép gọi các lệnh tương ứng và thay tên giả định bằng tài nguyên đã được cấp quyền trong môi trường thực hành.

### 9.1. Xác định phiên danh tính hiện tại

~~~bash
aws sts get-caller-identity
~~~

Ví dụ khi CLI đang sử dụng một role session, ARN trả về có thể mang dạng:

~~~text
arn:aws:sts::111122223333:assumed-role/ReportingReader/session-name
~~~

Nó cho biết CLI đang dùng phiên của role **ReportingReader**, khác với ARN định nghĩa role:

~~~text
arn:aws:iam::111122223333:role/ReportingReader
~~~

AWS CLI và SDK có thể lấy temporary credentials tự động từ role gắn với môi trường chạy, profile SSO hay cơ chế federation thích hợp; không nên copy secret vào mã nguồn hoặc commit credentials vào Git.

### 9.2. Kiểm tra user, group và role hiện có

~~~bash
# Liệt kê IAM user, group và role (cần quyền iam:List* phù hợp).
aws iam list-users
aws iam list-groups
aws iam list-roles

# Kiểm tra một user đang là thành viên của những group nào.
aws iam list-groups-for-user --user-name ExampleAnalyst

# Xem thông tin role, bao gồm AssumeRolePolicyDocument (trust).
aws iam get-role --role-name ReportingReader

# Liệt kê managed policy gắn vào role.
aws iam list-attached-role-policies --role-name ReportingReader

# Liệt kê inline policy gắn vào role.
aws iam list-role-policies --role-name ReportingReader
~~~

Các lệnh có thể bị **AccessDenied** do chính phiên người học không có quyền xem IAM. Đó là giới hạn quyền hợp lệ, không phải bằng chứng danh tính hoặc tài nguyên không tồn tại.

### 9.3. Đọc phiên bản một managed policy

~~~bash
# Kiểm tra metadata, đặc biệt DefaultVersionId.
aws iam get-policy \
  --policy-arn arn:aws:iam::111122223333:policy/ReadReports

# Thay v1 bằng DefaultVersionId thu được từ lệnh trên.
aws iam get-policy-version \
  --policy-arn arn:aws:iam::111122223333:policy/ReadReports \
  --version-id v1
~~~

Một customer managed policy có thể có nhiều version; version mặc định mới là phiên bản áp dụng. Không suy đoán chỉ từ tên policy; hãy đọc nội dung JSON thực tế và các giới hạn khác.

### 9.4. Mô phỏng một request

~~~bash
aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::111122223333:role/ReportingReader \
  --action-names s3:GetObject s3:DeleteObject \
  --resource-arns arn:aws:s3:::example-private-reports/reports/2026/demo.pdf
~~~

Trong kết quả, kiểm tra **EvalDecision** theo action và resource. Kết quả có thể là **allowed**, **implicitDeny** hoặc **explicitDeny** trong các trường hợp mô phỏng phù hợp.

**Giới hạn của mô phỏng:** IAM policy simulator không mô phỏng đầy đủ mọi loại policy, ngữ cảnh, cơ chế ủy quyền hoặc điều kiện trong thực tế (đặc biệt một số trường hợp resource policy, cross-account, SCP/RCP, service-specific control). Kết quả mô phỏng không thay thế việc chạy kiểm thử an toàn bằng identity phù hợp và kiểm tra quyền truy cập thực tế. Trước khi kết luận, đọc cả cảnh báo/chi tiết trả về từ công cụ.

### 9.5. Đọc lỗi AccessDenied có hệ thống

Khi một chương trình bị từ chối quyền, hãy trả lời theo thứ tự:

1. **Ai gửi request?** Xem identity từ **sts get-caller-identity** tại đúng môi trường phát sinh lỗi. Trong Lambda/EC2, xác nhận role đang được workload sử dụng.
2. **Action bị từ chối là gì?** Phân biệt permission action trong thông báo lỗi với lệnh API mà ứng dụng gọi.
3. **Resource ARN có chính xác không?** Kiểm tra account, Region (nếu resource có Region), loại tài nguyên, tên bucket, prefix hoặc path.
4. **Có Allow cần thiết không?** Xem managed/inline policy, group membership, phiên bản policy, condition và tags.
5. **Có Deny hoặc giới hạn khác không?** Kiểm tra SCP, boundary, session policy, resource policy, KMS key policy và điều kiện service-specific phù hợp.
6. **Nếu đang assume role:** Kiểm tra trust policy, quyền sts:AssumeRole của caller, điều kiện ExternalId/MFA/session tags, và thời hạn phiên.
7. **Xác minh lại bằng bằng chứng:** Đối chiếu CloudTrail, log ứng dụng và cách tái hiện an toàn. Không chữa lỗi bằng cách tạm cấp AdministratorAccess cho mọi principal.

**Tình huống thường gặp:** Một Lambda có quyền GetObject trong policy nhưng vẫn không đọc được S3 object mã hóa bằng customer managed KMS key. Ngoài quyền S3 và những resource policy liên quan, cần xem khả năng **kms:Decrypt** và key policy/điều kiện sử dụng key; thêm s3:* không giải quyết đúng nguyên nhân.

## 10. Sai lầm phổ biến và cách tránh

| Sai lầm | Vì sao nguy hiểm hoặc gây lỗi | Cách làm phù hợp |
| --- | --- | --- |
| Dùng tài khoản root để chạy script. | Quá nhiều đặc quyền; khó giới hạn phạm vi. | Dùng role/temporary credentials với quyền tối thiểu. |
| Nhúng access key vào source code, image hoặc environment không kiểm soát. | Secret có thể lộ qua Git, log, artefact hoặc cấu hình. | Ưu tiên role/STS; quản lý secret theo thiết kế khi thực sự cần. |
| Dùng **Action: "*"**, **Resource: "*"** để hết AccessDenied. | Cấp quyền quá rộng và che khuất nguyên nhân. | Xác định chính xác action/resource/condition; thêm quyền cần thiết có kiểm chứng. |
| Coi IAM group là danh tính có thể assume. | Sai mô hình; group không thể tạo role session. | Dùng group cấp quyền cho IAM user; role cho phiên truy cập. |
| Chỉ kiểm tra permissions policy mà bỏ trust policy. | Caller không được phép assume role dù role có quyền S3. | Kiểm tra cả trust và permissions, cùng quyền của caller. |
| Coi trust policy tương đương cấp toàn quyền. | Trust chỉ là quan hệ được assume, không phải quyền S3/EC2. | Xét riêng trust policy và quyền hiệu lực sau assume. |
| Cấp **iam:PassRole** với phạm vi rộng. | Có thể giúp principal triển khai dịch vụ chạy bằng role có quyền cao. | Giới hạn role có thể pass và dịch vụ nhận role khi phù hợp. |
| Chỉ xét IAM mà bỏ S3 bucket policy/KMS key policy. | Resource policy hoặc quyền khóa có thể chặn hay mở truy cập. | Đánh giá đầy đủ các policy áp dụng và cơ chế của dịch vụ. |
| Cấp cùng một role cho deploy pipeline và runtime application. | Workload có thể mang quyền triển khai không cần thiết. | Tách quyền quản trị/triển khai khỏi quyền runtime. |
| Nhầm IAM user/group với user/group của Identity Center. | Dễ cấp sai quyền và quản trị trùng lặp. | Chọn cơ chế danh tính chính cho nhân viên; dùng permission set đúng phạm vi. |
| Coi Allow trong simulator là bảo đảm end-to-end. | Mô phỏng không phản ánh đủ mọi điều kiện và lớp ứng dụng. | Kết hợp review policy, kiểm thử giới hạn và log thực tế. |

## 11. Tình huống thực hành

### Tình huống A — Nhân viên chỉ cần xem báo cáo trên S3

**Yêu cầu:** Nhân viên phân tích xem các file trong **reports/2026/**, không được xóa hoặc xem tài liệu nhân sự.

**Thiết kế:** Với tổ chức đang dùng Identity Center, cấp permission set tương ứng cho nhóm nhân sự thích hợp. Nếu môi trường thực sự sử dụng IAM user, nhóm **S3ReportReaders** có thể gắn customer managed policy chỉ cho phép ListBucket có điều kiện prefix và GetObject trên object ARN cùng prefix. Không dùng group để chứa các role.

**Kiểm tra:** Người dùng đọc thành công đúng prefix; thử DeleteObject hoặc đọc prefix khác phải bị từ chối. Kiểm tra bucket policy và quyền mã hóa nếu object dùng KMS.

### Tình huống B — Lambda chỉ ghi một loại hóa đơn

**Yêu cầu:** Lambda tạo hóa đơn PDF và ghi vào **invoices/generated/**.

**Thiết kế:** Execution role trust **lambda.amazonaws.com**, permissions policy có **s3:PutObject** vào object ARN của prefix và những quyền logging cần thiết. Nếu function cần KMS key, cấp thêm quyền khóa phù hợp. Người deploy có **iam:PassRole** chính xác role được cho phép gắn cho Lambda.

**Kiểm tra:** Function chỉ tạo được object trong prefix yêu cầu, không tự đọc bucket bí mật khác và không sửa policy IAM. Thêm quyền chỉ khi có yêu cầu nghiệp vụ được xác minh.

### Tình huống C — Đọc log từ account khác

**Yêu cầu:** Nhóm giám sát ở account A đọc log đã được cấp quyền ở account B.

**Thiết kế:** Account B có role trust principal cụ thể của account A; account A có quyền assume role đích; role đích được cấp quyền đọc đúng nguồn log. Tất cả yêu cầu đều qua temporary credentials. Nếu log mã hóa bằng KMS key, cần quyền dùng key tương ứng.

**Kiểm tra:** Assume thành công khi principal được phép và thất bại với principal khác; action đọc giới hạn đúng nguồn log. Đối chiếu CloudTrail từ các account liên quan khi phù hợp.

### Tình huống D — Ứng dụng EC2 bị AccessDenied khi đọc S3

**Hiện tượng:** EC2 vẫn hoạt động nhưng SDK báo lỗi S3 AccessDenied.

**Quy trình:** Kiểm tra instance có instance profile gắn role phù hợp chưa; SDK đang dùng profile/credentials nào; policy cho phép GetObject đúng object ARN chưa; bucket policy có Deny không; object có dùng KMS key cần Decrypt không. Việc EC2 và S3 nằm “cùng Region” hoặc tài nguyên EC2 được đặt trong private subnet không tự trao quyền đọc S3.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Một IAM group có thể được Lambda assume không?  
**Đáp án:** Không. Group chỉ tổ chức các IAM user và policy của họ. Lambda assume execution role được trust phù hợp.

**Câu 2.** Role trust policy cho phép lambda.amazonaws.com assume role. Vậy function có tự đọc được mọi bucket S3 không?  
**Đáp án:** Không. Trust chỉ cho phép Lambda sử dụng role; các quyền cụ thể của role và những chính sách/điều kiện khác mới xác định request S3 có được chấp nhận không.

**Câu 3.** Vì sao cần phân biệt ARN bucket và ARN object khi phân quyền S3?  
**Đáp án:** Action như ListBucket áp dụng cấp bucket; GetObject áp dụng cấp object. Chọn sai ARN có thể dẫn tới implicit deny dù policy trông có vẻ đúng.

**Câu 4.** User có một policy Allow GetObject nhưng resource policy explicit Deny trên request đang xét. Kết quả?  
**Đáp án:** Deny; explicit Deny áp dụng thắng Allow.

**Câu 5.** Permissions boundary hoặc SCP có thể tự cấp quyền GetObject không?  
**Đáp án:** Không. Chúng giới hạn quyền hiệu lực trong phạm vi áp dụng; principal vẫn cần một nguồn Allow phù hợp và không bị chặn bởi chính sách khác.

**Câu 6.** Khi ứng dụng EC2 cần gọi AWS API, tại sao dùng instance role thường tốt hơn lưu access key trong source code?  
**Đáp án:** Instance role cung cấp temporary credentials qua cơ chế AWS, giảm nhu cầu quản lý và rò rỉ secret dài hạn, đồng thời dễ giới hạn quyền theo workload.

**Câu 7.** Quyền **iam:PassRole** có đồng nghĩa caller được quyền assume role không?  
**Đáp án:** Không. PassRole cho phép chuyển một role cho dịch vụ được hỗ trợ trong một số thao tác triển khai, còn assume role do trust policy và cơ chế STS/quyền liên quan quyết định.

**Câu 8.** Có nên tạo IAM user riêng với access key dài hạn cho mỗi nhân viên ở mọi AWS account?  
**Đáp án:** Thông thường không. Với con người, nên ưu tiên liên kết danh tính/IAM Identity Center và temporary credentials; IAM user chỉ nên dùng khi có nhu cầu được xác minh và phải kiểm soát chặt thông tin xác thực.

## 13. Ghi nhớ

- **User** là danh tính IAM có thể được cấp thông tin xác thực dài hạn.
- **Group** là cách gom IAM user để quản lý policy; group không phải principal.
- **Role** là danh tính được assume bởi principal được tin cậy, thường cung cấp temporary credentials cho phiên làm việc.
- **Policy** diễn đạt quyền theo **Effect + Action + Resource + Condition**; phải phân biệt trust policy và permissions policy.
- **Implicit deny** là trạng thái mặc định; **explicit deny** có ưu tiên; quyền thực tế còn bị ảnh hưởng bởi những giới hạn khác và quy tắc dịch vụ.
- **Least privilege** cần được kiểm chứng theo từng workload, từng môi trường và từng thao tác, kết hợp IAM với VPC, mã hóa, giám sát và quy trình vận hành.

Khi thiết kế ứng dụng AWS, hãy chọn loại danh tính phù hợp với chủ thể (con người, pipeline hay workload), xác định ranh giới trust, cấp quyền nhỏ nhất có thể kiểm chứng, tránh lưu credential dài hạn và thường xuyên rà soát bằng log, công cụ phân tích policy và thử nghiệm có kiểm soát.

### Tài liệu AWS nên đọc thêm

- [AWS IAM User Guide](https://docs.aws.amazon.com/IAM/latest/UserGuide/introduction.html) — tổng quan IAM và các loại danh tính.
- [IAM identities: users, user groups, and roles](https://docs.aws.amazon.com/IAM/latest/UserGuide/id.html) — đặc điểm user, group và role.
- [IAM JSON policy elements reference](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_elements.html) — cú pháp, Action, Resource, Condition, Principal.
- [Policy evaluation logic](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic.html) — cách AWS kết hợp quyền và các giới hạn.
- [AWS IAM best practices](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html) — khuyến nghị về federation, role, quyền tối thiểu và bảo vệ credentials.

