# Permission boundary, session policy và quan hệ với SCP

> **Chương:** IAM và phân quyền  
> **Module:** CLOUD_PROVIDERS_AWS — hệ sinh thái AWS, từ Region/AZ, IAM, VPC đến dịch vụ tính toán, lưu trữ, cơ sở dữ liệu, tích hợp và serverless.

## Mục tiêu bài học

Khi thiết kế ứng dụng trên AWS, một quyền được ghi `Allow` trong IAM policy **chưa chắc đã được phép thực thi**. AWS còn xét các cơ chế giới hạn khác tại cấp danh tính, phiên đăng nhập và tổ chức. Hiểu được các lớp này giúp thiết kế phân quyền an toàn, ủy quyền quản trị mà không vượt giới hạn, chẩn đoán `AccessDenied` và bảo vệ môi trường thực hành lẫn production.

Sau bài này, bạn có thể:

1. Giải thích sự khác nhau giữa **identity-based policy**, **permissions boundary**, **session policy**, **Service Control Policy (SCP)** và **resource-based policy**.
2. Dự đoán quyền hiệu lực khi có nhiều lớp `Allow`/`Deny`, phân biệt **implicit deny** và **explicit deny**.
3. Hiểu khi nào boundary được gắn vào IAM user/role, khi nào session policy được truyền vào AWS STS và khi nào SCP áp dụng cho AWS account.
4. Thiết kế ví dụ ủy quyền IAM role an toàn, giới hạn phiên thao tác dữ liệu và hạn chế dịch vụ có thể gây chi phí.
5. Nhận diện các **ngoại lệ về resource-based policy**, quản trị nhiều account và phương pháp kiểm tra lỗi phân quyền.

## 1. Vì sao cần nhiều lớp giới hạn quyền?

Giả sử một đội phát triển đang xây dựng ứng dụng serverless:

- IAM role của Lambda được phép đọc và ghi object vào S3.
- Người vận hành muốn tạo thêm role để chạy bài thực hành, nhưng không được cấp quyền vượt khung đã duyệt.
- Một phiên hỗ trợ khách hàng chỉ nên có quyền đọc, dù role mà phiên đó đảm nhận có quyền ghi.
- Đơn vị quản trị AWS Organizations muốn ngăn tài khoản thực hành tạo một số dịch vụ hoặc cấu hình tốn kém.

Nếu chỉ xét một IAM policy gắn trên role, rất khó đáp ứng đồng thời các nhu cầu. AWS sử dụng các lớp chính sau:

| Cơ chế | Gắn hoặc cấu hình ở đâu? | Tác dụng | Có tự cấp quyền không? |
|---|---|---|---|
| **Identity-based policy** | IAM user, group hoặc role | Cấp/khước từ thao tác của danh tính | **Có thể cấp** qua `Allow` |
| **Permissions boundary** | IAM user hoặc IAM role | Định nghĩa trần quyền từ identity-based policies | **Không** |
| **Session policy** | Truyền khi tạo một số phiên STS tạm thời | Thu hẹp quyền của phiên so với danh tính nền | **Không** |
| **SCP** | Root/OU/account trong AWS Organizations | Giới hạn quyền cao nhất cho principal thuộc member account | **Không** |
| **Resource-based policy** | Tài nguyên như S3 bucket, KMS key; IAM role trust policy là trường hợp riêng | Cho phép/khước từ principal truy cập tài nguyên hoặc assume role | **Có thể cấp**, tùy loại tài nguyên và ngữ cảnh |
| **RCP** (*Resource Control Policy*) | Root/OU/account trong Organizations, tác động lên tài nguyên thuộc account | Giới hạn quyền đối với tài nguyên tại account chịu quản lý | **Không** |

Bài học tập trung vào **permissions boundary, session policy và SCP**; những cơ chế như RCP, VPC endpoint policy, ACL và yêu cầu riêng của KMS được nhắc để người học biết rằng thực tế có thể còn thêm điều kiện.

### 1.1. Sơ đồ tư duy về các giới hạn

~~~mermaid
flowchart TD
    A[Yêu cầu API: principal + action + resource + context] --> B{Có explicit Deny áp dụng?}
    B -- Có --> X[Từ chối]
    B -- Không --> C{Có đường cấp Allow hợp lệ?}
    C -- Không --> X
    C -- Có --> D[Đánh giá các lớp giới hạn áp dụng]
    D --> E[Permissions boundary nếu có]
    D --> F[Session policy nếu được truyền]
    D --> G[SCP tại member account]
    D --> H[RCP / chính sách riêng của dịch vụ nếu áp dụng]
    E --> I{Đủ điều kiện để cho phép?}
    F --> I
    G --> I
    H --> I
    I -- Có --> Y[Cho phép]
    I -- Không --> X
~~~

**Sơ đồ mô tả cách suy luận ở mức khái niệm**, không phải mô phỏng đầy đủ thứ tự nội bộ AWS. Đặc biệt, **resource-based policy cấp quyền trực tiếp cho một số loại principal** có thể thay đổi cách áp dụng implicit deny của boundary/session policy; xem mục 6.

### 1.2. Quy tắc quan trọng nhất

- **Mặc định là từ chối** (*implicit deny*): nếu không có quyền `Allow` hợp lệ, yêu cầu không được cấp.
- **Explicit Deny luôn thắng** `Allow` trong bất kỳ policy nào có hiệu lực với yêu cầu.
- **Boundary, session policy và SCP đều là giới hạn**, nên chỉ viết `Allow` trong một cơ chế giới hạn không làm xuất hiện quyền mới.
- Với đường cấp quyền bằng **identity-based policy**, khi các giới hạn cùng áp dụng, thao tác chỉ được phép nếu **identity-based policy, boundary, session policy và SCP** tương ứng cho phép, đồng thời không bị một lớp chính sách khác chặn.
- Tác động của `Condition`, principal, resource ARN, Region và loại yêu cầu vẫn phải được xét; việc chỉ so tên action chưa đủ để kết luận.

## 2. Permissions boundary: trần quyền của IAM user hoặc role

### 2.1. Khái niệm và vòng đời

**Permissions boundary** là một **IAM managed policy** được chọn làm ranh giới quyền cho một **IAM user hoặc IAM role**. Nó giới hạn các quyền mà identity-based policy có thể cấp cho thực thể đó.

- Mỗi user/role có thể được gắn **một** permissions boundary tại một thời điểm.
- Boundary sử dụng **managed policy**, không phải inline policy gắn trực tiếp dưới dạng boundary.
- Boundary không gắn trên IAM group và không cấp quyền độc lập.
- Khi thay đổi managed policy đang làm boundary, các user/role sử dụng boundary đó có thể thay đổi quyền hiệu lực; cần quản trị phiên bản và quy trình duyệt.
- Boundary vẫn gắn với user/role sau khi một người dùng assume role; trong trường hợp thông thường, nó tiếp tục giới hạn quyền được cấp qua identity-based policy của role.

**Ví dụ:** Role `aws-lab-dev-operator` có identity policy cho phép `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject`. Boundary chỉ cho phép `GetObject` và `PutObject`. Kết quả: `DeleteObject` bị **implicit deny bởi boundary**, mặc dù identity policy có `Allow`.

Cách suy luận đơn giản:

~~~text
Quyền từ identity-based policy
                ∩
        Permissions boundary
                =
Quyền qua đường identity-based policy sau boundary
~~~

### 2.2. Ví dụ IAM managed policy làm boundary

Giả sử bucket thực hành có tên `aws-lab-demo-data`. Policy dưới đây có thể được tạo thành customer managed policy `aws-lab-boundary` và gắn làm boundary cho IAM role:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ListTrainingBucket",
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::aws-lab-demo-data"
    },
    {
      "Sid": "ReadWriteTrainingObjects",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject"
      ],
      "Resource": "arn:aws:s3:::aws-lab-demo-data/*"
    }
  ]
}
~~~

Đây là **giới hạn quyền cho mục đích minh họa**, chưa phải bộ quyền đầy đủ để vận hành một ứng dụng. Ví dụ identity-based policy của role cũng có `s3:DeleteObject`; boundary trên không cho phép `DeleteObject`, nên role không thể xóa object qua đường quyền identity-based.

Lưu ý khi đọc JSON:

- `s3:ListBucket` sử dụng **ARN của bucket**; `s3:GetObject` và `s3:PutObject` sử dụng **ARN của object** với `/*`.
- `Allow` ở boundary chỉ đặt mức tối đa; nếu role không có `Allow` tương ứng trong identity-based policy thì vẫn không có quyền.
- Boundary phải xét đầy đủ action mà ứng dụng thực sự dùng, kể cả action phụ trợ liên quan đến mã hóa KMS, tagging hoặc truy cập các tài nguyên khác.
- Các `Deny` tường minh trong boundary vẫn có hiệu lực theo logic đánh giá policy.

### 2.3. Ủy quyền quản lý role nhưng bắt buộc có boundary

Tình huống phổ biến: đội nền tảng muốn cho đội ứng dụng tự tạo role cho workload, nhưng mọi role mới phải bị giới hạn bởi `aws-lab-boundary`. Người được ủy quyền cần quyền tạo role với điều kiện boundary bắt buộc.

Ví dụ một statement trong **identity-based policy của người được ủy quyền**:

~~~json
{
  "Sid": "CreateRolesOnlyWithApprovedBoundary",
  "Effect": "Allow",
  "Action": "iam:CreateRole",
  "Resource": "arn:aws:iam::111122223333:role/aws-lab-dev-*",
  "Condition": {
    "StringEquals": {
      "iam:PermissionsBoundary": "arn:aws:iam::111122223333:policy/aws-lab-boundary"
    }
  }
}
~~~

**Account ID `111122223333` chỉ là giá trị minh họa**. Ví dụ trên ràng buộc thao tác **CreateRole**; để xây dựng cơ chế ủy quyền hoàn chỉnh, quản trị viên còn phải:

1. Giới hạn quyền `iam:AttachRolePolicy`, `iam:PutRolePolicy`, `iam:UpdateAssumeRolePolicy` và các thao tác liên quan theo nhóm role được phép quản lý.
2. Ngăn người được ủy quyền **gỡ hoặc thay boundary** thành boundary yếu hơn bằng cách kiểm soát `iam:DeleteRolePermissionsBoundary`, `iam:PutRolePermissionsBoundary` và quyền sửa managed policy đang được dùng làm boundary.
3. Kiểm soát `iam:PassRole` và đối tượng role có thể chuyển cho EC2/Lambda để tránh con đường leo thang đặc quyền.
4. Kiểm tra trust policy: **ai được assume role** là câu hỏi khác với **role được phép gọi API gì**.

**Sai lầm cần tránh:** cho rằng chỉ cần buộc boundary lúc tạo role là không còn đường vượt quyền. Một người có quyền thay boundary, thay chính sách liên quan hoặc pass một role đặc quyền có thể phá vỡ ý định ban đầu.

## 3. Session policy: thu hẹp quyền của một phiên tạm thời

### 3.1. Session policy hoạt động khi nào?

**Session policy** là JSON policy được truyền vào một số API **AWS Security Token Service (STS)** khi tạo phiên thông qua role hoặc federation, ví dụ:

- `AssumeRole`
- `AssumeRoleWithSAML`
- `AssumeRoleWithWebIdentity`
- `GetFederationToken` (với quy tắc riêng)

Với `AssumeRole`, có thể truyền một **inline session policy** qua tham số `Policy`, và/hoặc ARN của tối đa **10 managed session policies** qua `PolicyArns`; cần kiểm tra thêm giới hạn dung lượng plaintext và packed policy của API. Managed session policies được tham chiếu phải nằm trong cùng account với role.

Session policy **không sửa** IAM role, chỉ giới hạn quyền của **phiên STS vừa được tạo**. Các phiên khác assume cùng role nhưng không truyền session policy này có thể có mức quyền khác, tùy các chính sách áp dụng.

> **Không phải mọi phiên tạm thời đều có session policy do người dùng truyền.** Nếu không có session policy bổ sung, không có lớp thu hẹp tương ứng từ chính tham số này; role vẫn chịu IAM, boundary, SCP, resource policy và các cơ chế liên quan.

### 3.2. Ví dụ hạ quyền một phiên xử lý S3

Giả sử role `aws-lab-dev-operator` có quyền đọc và ghi object trong bucket. Trong một phiên hỗ trợ, người dùng chỉ cần đọc. Tạo tệp nội dung `session-read-only.json`:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadOnlyTrainingObjects",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::aws-lab-demo-data/*"
    }
  ]
}
~~~

Nếu principal hiện tại được phép assume role và role trust policy cho phép, có thể gọi:

~~~bash
aws sts assume-role \
  --role-arn arn:aws:iam::111122223333:role/aws-lab-dev-operator \
  --role-session-name training-read-only \
  --policy file://session-read-only.json \
  --query '{SessionArn:AssumedRoleUser.Arn,Expires:Credentials.Expiration}' \
  --output json
~~~

Lệnh minh họa chỉ **hiển thị ARN và thời điểm hết hạn**, tránh in các trường credentials ra terminal. Để thực sự gọi S3 bằng phiên mới, client phải sử dụng bộ temporary credentials do STS trả về thông qua cơ chế xử lý bảo mật; không chép access key/secret/session token vào bài tập, repository, log hoặc màn hình chia sẻ.

Một số điểm phải phân biệt:

- Role trust policy quyết định principal có thể **assume role** hay không; identity policy hoặc quyền tương ứng của caller còn có thể cần cho `sts:AssumeRole`.
- Session policy này chỉ cho phép `s3:GetObject`; nó không cho phép `s3:PutObject` dù role có `Allow`.
- Nếu role không có `Allow` cho `s3:GetObject`, session policy không thể tự mở quyền đọc.
- Nếu boundary hoặc SCP chặn `GetObject`, session policy `Allow` vẫn không làm thao tác thành công.
- Với đường cấp quyền bằng resource-based policy cho **ARN phiên STS**, quy tắc có ngoại lệ, xem mục 6.

### 3.3. Session policy khác permission boundary ở điểm nào?

| Tiêu chí | Permission boundary | Session policy |
|---|---|---|
| Đối tượng giới hạn | IAM user/role | Phiên STS cụ thể |
| Cách gắn | Chọn managed policy làm boundary trên IAM entity | Truyền inline/managed policies khi tạo phiên |
| Thời điểm tác động | Trong vòng đời entity còn gắn boundary | Chỉ trong thời hạn phiên tạm thời |
| Có thay role policy không? | Không | Không |
| Dùng cho | Ủy quyền quản trị an toàn, khung quyền dài hạn | Chỉ cấp quyền cần thiết cho một phiên công việc |
| Có mở quyền không? | Không | Không |

**Ví dụ dễ nhớ:** boundary giống **hàng rào cố định quanh role**, còn session policy giống **phạm vi thao tác được chấp thuận cho một phiên làm việc**. Cả hai không thay thế việc cấp quyền trong identity-based policy.

## 4. SCP: hàng rào tại cấp AWS Organizations

### 4.1. SCP áp dụng ở đâu?

**Service Control Policy (SCP)** được quản trị từ **AWS Organizations**, yêu cầu tổ chức bật **all features**. SCP có thể được gắn vào **organization root, Organizational Unit (OU) hoặc member account**.

~~~mermaid
flowchart TD
    R[Organization root: SCP] --> O[OU Sandbox: SCP]
    R --> P[OU Production: SCP]
    O --> A[Member account Lab A]
    O --> B[Member account Lab B]
    P --> C[Member account Prod]
    A --> U[IAM users, roles, root tại Lab A]
~~~

Với các member account, SCP ở mỗi tầng tổ chức liên quan đều có thể giới hạn quyền. Cơ chế này giúp đội nền tảng áp quy tắc chung: ví dụ cấm tạo tài nguyên ở Region chưa được duyệt, chặn dịch vụ không dùng, bảo vệ logging hoặc hạn chế thao tác có rủi ro chi phí.

**Giới hạn phạm vi cần nhớ:**

- SCP tác động đến **IAM users và roles trong member accounts**, bao gồm **root user** của member account, trừ các ngoại lệ được AWS nêu.
- SCP **không áp dụng cho principals trong management account**.
- SCP **không giới hạn service-linked roles**.
- SCP không trực tiếp giới hạn principal thuộc account khác chỉ vì tài nguyên đích nằm trong member account có SCP; xem thêm tình huống cross-account và RCP.
- SCP **không cấp quyền**, kể cả khi có `"Effect": "Allow", "Action": "*"`.

### 4.2. Allow-list và deny-list với SCP

AWS Organizations thường có managed SCP `FullAWSAccess` gắn mặc định khi bật SCP. Trong mô hình **deny-list**, các SCP `Deny` bổ sung giới hạn các hành động; phần còn lại vẫn cần IAM cho phép.

Ví dụ SCP **không cho tạo EC2 instance và NAT Gateway** trong OU sandbox:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "BlockSelectedComputeAndNetworkCreation",
      "Effect": "Deny",
      "Action": [
        "ec2:RunInstances",
        "ec2:CreateNatGateway"
      ],
      "Resource": "*"
    }
  ]
}
~~~

Đoạn trên **chỉ minh họa một phần guardrail**. Trước khi triển khai thực tế, cần đánh giá tác động đến workflow, cơ chế ngoại lệ, dịch vụ gọi thay mặt người dùng và quyền của quản trị viên. SCP không tự dừng tài nguyên đang chạy hay tạo trần ngân sách.

Với mô hình **allow-list**, tổ chức chủ động chỉ cho phép một tập hành động nhất định. Để một quyền được phép, các cấp thích hợp trên đường **root → OU → account** phải cho phép quyền đó; một `Allow` ở account không khắc phục được thiếu `Allow` ở OU hoặc root.

**Ví dụ:** SCP ở root cho `s3:*` nhưng không cho `ec2:RunInstances`. Dù IAM role ở member account có `AdministratorAccess`, nó không thể chạy EC2 thông qua quyền được SCP giới hạn.

### 4.3. SCP và permission boundary khác nhau thế nào?

| Góc nhìn | SCP | Permission boundary |
|---|---|---|
| Đơn vị quản trị | Organizations: root/OU/account | IAM entity: user hoặc role |
| Ai đặt? | Quản trị tổ chức, người được ủy quyền hợp lệ | Quản trị IAM có quyền tương ứng |
| Đối tượng | Principal thuộc member accounts, với ngoại lệ AWS quy định | User/role được gắn boundary |
| Có giới hạn root user? | Có, root của **member account** | Không gắn trực tiếp boundary vào root |
| Có giới hạn role service-linked? | Không | Không phải một cơ chế áp boundary lên service-linked role theo cách thông thường |
| Có cấp quyền? | Không | Không |
| Mục đích điển hình | Governance, Region/dịch vụ/quy định chung | Delegated administration, khung quyền per user/role |

Không thể dùng permission boundary của một role để thay thế chính sách bắt buộc cho toàn bộ account. Ngược lại, SCP thường quá rộng để thay thế việc thu hẹp quyền khác nhau giữa từng role hoặc phiên.

## 5. Ba lớp kết hợp với identity-based policy như thế nào?

### 5.1. Công thức tư duy cho trường hợp thông thường

Đối với **quyền được cấp qua identity-based policy** của role đã assume, nếu có boundary, session policy và SCP tương ứng:

~~~text
Effective Allow (qua identity-based policy)
    = Identity Allow
      ∩ Boundary Allow       (nếu gắn boundary)
      ∩ Session Allow        (nếu đã truyền session policy)
      ∩ SCP Allow            (nếu SCP áp dụng)
      ∩ Các giới hạn khác     (nếu áp dụng)
      - Bất kỳ explicit Deny áp dụng nào
~~~

Ký hiệu `∩` ở đây là **giao của các quyền**. Nó là cách ghi nhớ cho trường hợp điển hình; không mô tả hết các quy tắc **resource-based policy** đặc biệt hoặc kiểm tra cross-account. Một policy với `Condition` cần được đánh giá theo ngữ cảnh thực tế thay vì coi là tập action tĩnh.

### 5.2. Tình huống tổng hợp có bốn thao tác

Role `aws-lab-dev-operator` trong sandbox có bốn quyền được identity-based policy cho phép:

~~~text
s3:GetObject
s3:PutObject
s3:DeleteObject
s3:ListBucket
~~~

Có các giới hạn:

- **Boundary:** cho phép `GetObject`, `PutObject`, `DeleteObject`; không cho `ListBucket`.
- **Session policy:** chỉ cho phép `GetObject`, `DeleteObject`; không cho `PutObject` hoặc `ListBucket`.
- **SCP:** cho phép S3 nói chung, nhưng có **explicit Deny** đối với `s3:DeleteObject`.

Giả sử action, ARN và `Condition` đều khớp, không có đường cấp quyền khác từ resource policy:

| Action | Identity | Boundary | Session | SCP | Kết quả |
|---|---|---|---|---|---|
| `s3:GetObject` | Allow | Allow | Allow | Allow | **Allow** |
| `s3:PutObject` | Allow | Allow | Thiếu Allow | Allow | **Deny — session policy** |
| `s3:DeleteObject` | Allow | Allow | Allow | **Explicit Deny** | **Deny — SCP** |
| `s3:ListBucket` | Allow | Thiếu Allow | Thiếu Allow | Allow | **Deny — boundary và session** |
| `ec2:RunInstances` | Thiếu Allow | Thiếu Allow | Thiếu Allow | Tùy SCP | **Deny — không có quyền gốc** |

Đây là nguyên nhân phổ biến của câu hỏi **“IAM role có Allow rồi, tại sao AWS vẫn báo AccessDenied?”**. Để xác định lớp nào từ chối, cần xem **chính sách thực sự áp dụng cho request** và thông báo lỗi hoặc CloudTrail, không chỉ policy trực tiếp gắn trên role.

### 5.3. Explicit Deny khác implicit deny

| Loại | Xuất hiện khi nào? | Điều gì xảy ra nếu có Allow ở nơi khác? |
|---|---|---|
| **Implicit deny** | Không có `Allow` phù hợp trong lớp cần cho phép; hoặc thiếu quyền gốc | Không được cấp qua đường quyền đó; quy tắc còn phụ thuộc resource policy |
| **Explicit deny** | Có statement `"Effect": "Deny"` khớp principal/action/resource/condition | **Từ chối**, ngay cả khi nhiều policy khác có `Allow` |

Ví dụ `Deny` rõ ràng cho `s3:DeleteObject` trong SCP là giới hạn có chủ đích. Một boundary chỉ liệt kê `GetObject` và `PutObject` tạo **implicit deny** cho `DeleteObject` trên đường cấp quyền identity-based.

## 6. Ngoại lệ quan trọng: resource-based policy và ARN principal

Các công thức giao quyền ở trên **không bao quát mọi trường hợp**. Trong cùng một AWS account, một số resource-based policy có thể cấp quyền **trực tiếp** cho một principal, làm thay đổi tác dụng của *implicit deny* trong identity-based policy, boundary hoặc session policy.

### 6.1. Phân biệt role ARN và role-session ARN

Hai ARN sau **không đồng nghĩa**:

~~~text
IAM role ARN:
arn:aws:iam::111122223333:role/aws-lab-dev-operator

STS assumed-role session ARN:
arn:aws:sts::111122223333:assumed-role/aws-lab-dev-operator/training-read-only
~~~

Khi sử dụng credentials của role đã assume, AWS xác định principal phiên STS. Resource policy có thể chỉ định **role** hoặc **phiên role** làm principal; kết quả giới hạn quyền có thể khác.

| Principal được resource-based policy cho phép trực tiếp (trong cùng account) | Vai trò của implicit deny trong boundary/session policy |
|---|---|
| **IAM user ARN** (không phải federated user session) | Implicit deny trong identity policy hoặc boundary thường **không chặn** quyền được cấp trực tiếp theo cách này |
| **IAM role ARN** | Implicit deny trong boundary hoặc session policy **vẫn có thể chặn** quyền được cấp tới role |
| **STS assumed-role session ARN** | Quyền được cấp **trực tiếp cho session ARN** thường **không bị giới hạn bởi implicit deny** trong identity policy, boundary hoặc session policy |
| **STS federated user session ARN** | Quy tắc có điểm riêng theo principal được chỉ định; phải đối chiếu tài liệu AWS cho trường hợp cụ thể |

Trong mọi trường hợp, **explicit Deny phù hợp vẫn thắng**. SCP tác động đến principal thuộc member account trong phạm vi áp dụng; các lớp khác như **RCP, KMS key policy, VPC endpoint policy, service-specific authorization** cũng có thể hạn chế request.

**Tình huống cần cẩn trọng:** Một S3 bucket policy cho phép trực tiếp `arn:aws:sts::111122223333:assumed-role/aws-lab-dev-operator/training-read-only` đọc object. Quyền trực tiếp này có thể không bị thu hẹp bởi implicit deny của session policy như khi cấp quyền cho IAM role ARN. Do đó, không nên coi permissions boundary hoặc session policy là cách duy nhất để khóa mọi quyền có thể được cấp từ resource-based policy.

AWS khuyến nghị dùng **IAM role principal** thay cho **role session principal** khi phù hợp, kết hợp `Condition` để giới hạn đối tượng và ngữ cảnh. Với resource policy sử dụng wildcard principal kèm `aws:PrincipalArn`, các quy tắc giới hạn cũng có sắc thái riêng; luôn đọc logic đánh giá IAM trước khi thiết kế đường cấp quyền nhạy cảm.

### 6.2. Quan hệ với SCP trong truy cập cross-account

Giả sử **account A** trong tổ chức sở hữu S3 bucket, còn **account B** bên ngoài tổ chức có một principal cần truy cập:

- SCP gắn trên **account A** không trực tiếp áp dụng cho principal thuộc **account B** chỉ vì nó gọi API lên bucket ở A.
- Principal ở B phải đáp ứng chính sách ở **phía danh tính/caller** (và SCP của B nếu có), đồng thời chính sách tài nguyên ở A phải cho phép truy cập phù hợp; có thể còn điều kiện riêng của dịch vụ.
- Nếu account A chịu **RCP**, policy đó có thể giới hạn quyền truy cập vào tài nguyên thuộc A. RCP là cơ chế khác SCP.
- Nếu principal thuộc **member account A** thì SCP áp dụng cho principal đó, kể cả khi truy cập tài nguyên ở account khác theo phạm vi AWS định nghĩa.

Vì vậy, khi phân tích cross-account, cần tách rõ **account sở hữu principal**, **account sở hữu tài nguyên** và những policy có hiệu lực ở từng phía.

## 7. Thiết kế thực tế: guardrail nhiều lớp cho môi trường AWS

### 7.1. Mô hình vai trò và mục tiêu

Giả sử tổ chức có account **sandbox**, account **production** và đội **platform** quản trị. Ứng dụng sử dụng VPC, Lambda, S3 và RDS; đội phát triển có thể triển khai thử nghiệm, nhưng không được tự mở toàn bộ quyền quản trị.

~~~mermaid
flowchart LR
    A[Platform / AWS Organizations] -->|SCP cho sandbox OU| B[Sandbox account]
    B --> C[Workload role]
    B --> D[Role tạo bởi developer]
    E[Managed permissions boundary] --> D
    F[Identity policy / deployment permissions] --> D
    G[STS session policy] --> H[Phiên hỗ trợ chỉ đọc]
    D --> H
    C --> I[S3 / Lambda / VPC / RDS]
    H --> I
~~~

Áp dụng phân tầng:

1. **SCP:** kiểm soát cấp tổ chức, chẳng hạn chặn tạo NAT Gateway trong sandbox hoặc hạn chế Region không được duyệt. SCP không kiểm soát chi phí theo một ngưỡng tiền; dùng thêm AWS Budgets, cảnh báo và chính sách dọn tài nguyên.
2. **Permissions boundary:** mọi role do developer được phép tạo phải nằm trong khung quyền, ví dụ chỉ thao tác các tài nguyên dự án và không quản lý IAM ngoài phạm vi được phép.
3. **Identity-based policy:** mỗi workload role chỉ có những action thực sự cần: Lambda đọc S3, worker gửi message SQS, ứng dụng kết nối RDS theo phương thức phù hợp.
4. **Session policy:** trong phiên kiểm tra sự cố, operator chỉ nhận quyền đọc log hoặc object cần điều tra; tránh thao tác thay đổi production trong phiên hỗ trợ.
5. **Resource-based policy và các điều kiện khác:** bucket policy, KMS key policy, trust policy, network và các biện pháp quản trị phụ trợ được rà soát để không vô tình tạo đường cấp quyền ngoài dự kiến.

### 7.2. Phân biệt trách nhiệm của các chính sách

| Yêu cầu | Công cụ chính phù hợp | Vì sao? |
|---|---|---|
| Mọi member account sandbox không được tạo NAT Gateway | SCP ở OU sandbox | Ràng buộc nhiều account nhất quán |
| Developer được tạo role nhưng role không vượt khung quyền | Permissions boundary + kiểm soát API IAM | Bảo đảm các role tự tạo chịu giới hạn đã duyệt |
| Phiên hỗ trợ trong 30 phút chỉ đọc object | Session policy + giới hạn thời lượng STS | Thu hẹp theo từng phiên |
| Lambda chỉ được đọc prefix `incoming/` | Identity-based policy và/hoặc bucket policy | Cấp đúng quyền cho workload |
| Chỉ nguồn đã xác thực có thể assume deployment role | Trust policy và điều kiện danh tính | Kiểm soát đường vào role |
| Bảo vệ dữ liệu giữa các account và theo chủ sở hữu tài nguyên | Resource-based policy, RCP và các cơ chế liên quan | Kiểm soát tài nguyên và quyền truy cập từ bên ngoài |

**Nguyên tắc:** áp dụng lớp bảo vệ tại đúng cấp mà nó quản trị, sau đó thử nghiệm quyền hiệu lực qua các kịch bản thực tế. Một policy quá rộng và nhiều tầng guardrail thiếu kiểm thử thường khiến hệ thống khó vận hành hơn mà chưa chắc an toàn hơn.

## 8. Thực hành có hướng dẫn: suy luận và quan sát quyền

Bài thực hành có **hai lựa chọn**. Người học chưa có sandbox hoặc quyền quản trị IAM có thể hoàn thành **phần A trên giấy**. Phần B sử dụng các lệnh **chỉ đọc**, áp dụng khi tổ chức đã cấp role phù hợp.

### 8.1. Phần A — Tính quyền hiệu lực

Giả sử có policy như sau:

- Role identity policy: `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject`.
- Boundary: chỉ `s3:GetObject` và `s3:PutObject`.
- Session policy: chỉ `s3:GetObject`.
- SCP tại member account: `FullAWSAccess` có hiệu lực, nhưng `Deny s3:DeleteObject`.
- Không có resource-based `Allow` đặc biệt hoặc các giới hạn khác ảnh hưởng đến ví dụ.

**Hãy xác định** liệu phiên có thể gọi ba action trên không. Đáp án:

| Action | Kết quả | Giải thích |
|---|---|---|
| `s3:GetObject` | **Allow** | Mọi lớp cần thiết đều cho phép |
| `s3:PutObject` | **Deny** | Session policy không cho phép |
| `s3:DeleteObject` | **Deny** | Boundary không cho phép, session policy không cho phép và SCP explicit deny |

Thử thay đổi từng biến: nếu **bỏ session policy**, `PutObject` có thể được phép qua role và boundary; nếu **tăng identity policy** thành `s3:*`, boundary và SCP vẫn không tự mở rộng; nếu **gỡ boundary**, cần xem lại session/SCP và resource policy trước khi kết luận.

### 8.2. Phần B — Xem chính sách của một role được cấp

**Điều kiện:** bạn đã có profile AWS CLI và được cho phép xem IAM role trong sandbox. **Không sử dụng root, không tạo/xóa role hay thay policy chỉ để làm bài học này.** Thay `aws-lab-dev-operator` bằng tên role thực sự do quản trị viên cấp.

~~~bash
aws sts get-caller-identity --profile aws-lab-dev

aws iam get-role \
  --role-name aws-lab-dev-operator \
  --profile aws-lab-dev \
  --query 'Role.{Arn:Arn,Trust:AssumeRolePolicyDocument,Boundary:PermissionsBoundary}'

aws iam list-attached-role-policies \
  --role-name aws-lab-dev-operator \
  --profile aws-lab-dev

aws iam list-role-policies \
  --role-name aws-lab-dev-operator \
  --profile aws-lab-dev
~~~

Đọc kết quả:

- **STS identity:** account/ARN có đúng phiên bạn định kiểm tra không? ARN kiểu `arn:aws:sts::...:assumed-role/...` là **session**, không phải ARN định danh role trong IAM.
- **Trust:** role cho principal nào assume và đặt điều kiện gì?
- **Boundary:** trường `PermissionsBoundary` có xuất hiện không? Nếu có, đọc nội dung managed policy với quyền phù hợp; nếu không, role hiện không có boundary.
- **Identity policy:** các managed/inline policies nào cấp quyền?
- **Session policy:** không suy ra đầy đủ chỉ từ `get-role`; cần biết request STS đã dùng để cấp phiên, vì session policy có thể được truyền khi tạo phiên.
- **SCP:** muốn xem SCP cần quyền AWS Organizations tương ứng; trong môi trường tổ chức, nhờ quản trị viên xác nhận các SCP ở root/OU/account.

**Không chạy lệnh thay đổi trên account đang dùng chung hoặc production** khi chưa có quy trình được phê duyệt.

### 8.3. Kiểm tra quyền bằng công cụ phù hợp

- **IAM Policy Simulator:** hỗ trợ mô phỏng nhiều tình huống của policy gắn user/role và boundary, nhưng có giới hạn; không mặc định tái hiện toàn bộ session policies, SCP phức tạp, resource policy và ngữ cảnh dịch vụ.
- **IAM Access Analyzer:** giúp rà soát quyền truy cập, kiểm tra policy và phát hiện truy cập ngoài ý muốn theo phạm vi tính năng.
- **CloudTrail:** xác định principal và API thực tế đã gọi, xem thời điểm/yêu cầu bị từ chối, tùy việc ghi nhận loại event.
- **Lỗi trả về từ API:** đôi khi có thông tin `because no permissions boundary allows...`, `because no session policy allows...` hoặc `explicit deny in a service control policy`; thông tin chi tiết phụ thuộc ngữ cảnh và dịch vụ.
- **Kiểm thử trên sandbox:** chỉ với action không gây tác động lớn, và phải kiểm tra account/Region/role trước khi thử.

## 9. Chẩn đoán AccessDenied theo từng lớp

Khi một lệnh bị từ chối, hãy kiểm tra theo trình tự:

1. **Ai gọi API?** Dùng `sts:GetCallerIdentity` để đối chiếu ARN phiên, role và account.
2. **Yêu cầu nào?** Ghi action, resource ARN, Region và điều kiện liên quan (ví dụ tag, VPC endpoint, MFA, encryption).
3. **Quyền gốc có không?** Xem identity-based policy/trust policy, resource-based policy và các `Deny` áp dụng.
4. **Có boundary không?** Xem IAM user/role và managed policy đang được dùng làm boundary.
5. **Có session policy không?** Kiểm tra cơ chế federation/STS phát hành credentials, điều kiện của phiên và khoảng thời gian hiệu lực.
6. **Có SCP hay RCP không?** Xem cấu trúc Organizations và liên hệ tổ chức quản lý nếu bạn không có quyền truy cập.
7. **Có ràng buộc chuyên biệt?** Ví dụ bucket policy, KMS key policy, yêu cầu cross-account, VPC endpoint policy hoặc điều kiện từ service.
8. **Khắc phục tối thiểu:** chỉ cấp quyền còn thiếu hoặc điều chỉnh guardrail theo quy trình duyệt; ghi lại nguyên nhân, không thêm `Action: "*"` để né lỗi.

| Triệu chứng | Nguyên nhân đáng kiểm tra | Bước tiếp theo |
|---|---|---|
| Role có `s3:PutObject` nhưng vẫn bị từ chối | Boundary hoặc session policy thiếu `PutObject`; SCP/resource policy có `Deny` | Đối chiếu cả ba lớp với object ARN |
| Dùng `AdministratorAccess` mà không tạo được EC2 | SCP hoặc giới hạn khác tại account | Kiểm tra thông báo lỗi và liên hệ quản trị Organizations |
| Một phiên assume role đọc được, phiên khác không | Session policy/role-session context khác nhau | So request STS, principal ARN và policy được truyền |
| Không thể assume role | Trust policy, `sts:AssumeRole`, MFA, `ExternalId` hoặc điều kiện liên quan | Kiểm tra quyền caller và trust policy của role |
| Tạo role không được dù có `iam:CreateRole` | Điều kiện `iam:PermissionsBoundary` hoặc đường dẫn/tên role không khớp | Dùng đúng ARN boundary và role path được phép |
| Bucket policy cho quyền ngoài dự kiến dù boundary giới hạn | Resource policy cấp trực tiếp cho IAM user hoặc session ARN | Kiểm tra principal cụ thể và quy tắc resource-based policy |
| Quyền bất ngờ thay đổi trên nhiều role | Managed boundary policy được sửa; SCP cấp OU bị thay đổi | So lịch sử thay đổi policy và CloudTrail |

## 10. Các lỗi hiểu sai phổ biến

**“Tôi gắn boundary có `Allow s3:*`, vậy role đã có quyền S3.”** Sai. Boundary không cấp quyền; identity-based policy hoặc đường cấp quyền hợp lệ khác vẫn phải cho phép.

**“SCP `FullAWSAccess` giống IAM `AdministratorAccess`.”** Sai. `FullAWSAccess` chỉ không giới hạn thêm ở lớp SCP tương ứng; nó không tự cấp API permissions.

**“Session policy ghi `Allow ec2:RunInstances` có thể vượt boundary.”** Sai đối với quyền được cấp qua identity-based policy. Session policy không mở rộng role permissions, và boundary/SCP vẫn giới hạn.

**“SCP gắn với account chứa bucket luôn chặn được mọi user ngoài tổ chức đọc bucket.”** Sai. SCP theo principal thuộc member account; để kiểm soát tài nguyên từ bên ngoài còn phải kiểm tra bucket policy, RCP và các cơ chế liên quan.

**“Boundary và session policy luôn chặn được mọi `Allow` ở resource policy.”** Sai trong một số tình huống grant trực tiếp cho IAM user ARN hoặc STS session ARN trong cùng account. Phân biệt loại principal và `Deny` tường minh là thiết yếu.

**“Mọi `AccessDenied` đều sửa được bằng cách thêm `Allow` cho role.”** Sai. Một `Deny` ở SCP, boundary, session/resource policy hoặc một ràng buộc dịch vụ có thể chặn dù identity policy đã đủ rộng.

## 11. Tự kiểm tra

1. Permissions boundary dùng loại policy nào và có thể gắn cho IAM group không?
2. Nếu identity-based policy cho `s3:GetObject`, session policy cũng cho nhưng SCP ở OU explicit deny, kết quả thế nào?
3. Khi developer có `iam:CreateRole`, cần kiểm soát thêm những API nào để boundary không bị gỡ hoặc thay?
4. Điểm khác giữa `arn:aws:iam::...:role/...` và `arn:aws:sts::...:assumed-role/.../session-name` là gì, và vì sao nó ảnh hưởng resource-based policy?
5. Vì sao SCP của account sở hữu S3 bucket chưa đủ để kiểm soát principal ở account bên ngoài?
6. Cần kiểm tra ở đâu nếu hai phiên assume cùng role có quyền hiệu lực khác nhau?
7. Trong bài toán ứng dụng Lambda đọc S3, policy nào trực tiếp **cấp** quyền đọc, còn policy nào chỉ **giới hạn**?

**Tiêu chí hoàn thành:** Bạn có thể chỉ ra lớp nào đang cấp quyền, lớp nào giới hạn quyền và lý do `Allow` ở một nơi chưa đủ. Với một yêu cầu AWS cụ thể, bạn biết xác minh principal, action, resource, các policy áp dụng và cách kết luận `Allow`/`Deny` mà không mở quyền quá mức.

## Tài liệu AWS chính thức

- [Permissions boundaries for IAM entities](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_boundaries.html)
- [Policies and permissions in IAM](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies.html)
- [Policy evaluation logic](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic.html)
- [Policy evaluation: deny and allow](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic_policy-eval-denyallow.html)
- [AWS STS AssumeRole API](https://docs.aws.amazon.com/STS/latest/APIReference/API_AssumeRole.html)
- [Service control policies in AWS Organizations](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_scps.html)
- [Troubleshoot access denied errors](https://docs.aws.amazon.com/IAM/latest/UserGuide/troubleshoot_access-denied.html)

> **Lưu ý khi áp dụng:** Ví dụ sử dụng account ID và tên bucket giả định; không thực thi policy minh họa trên production khi chưa phân tích tác động. Cơ chế IAM, Organizations, giới hạn API và hỗ trợ mô phỏng có thể thay đổi theo dịch vụ; luôn đối chiếu tài liệu AWS hiện hành trước khi triển khai.
