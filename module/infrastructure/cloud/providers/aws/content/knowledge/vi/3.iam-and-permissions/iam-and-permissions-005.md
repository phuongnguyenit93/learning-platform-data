# Trust policy và cơ chế assume role trong AWS IAM

## Mục tiêu học tập

Sau bài học này, người học có thể:

- Giải thích **IAM role**, **trust policy** và **permissions policy** khác nhau ở đâu; xác định quyền của **người nhận role** và quyền của **phiên làm việc sau khi nhận role**.
- Mô tả luồng **AWS Security Token Service (STS) AssumeRole**, loại thông tin xác thực tạm thời được trả về và cách dịch vụ AWS sử dụng chúng.
- Viết và đọc trust policy cho trường hợp **cùng tài khoản**, **khác tài khoản (cross-account)**, **dịch vụ AWS**, và **đăng nhập liên kết bằng OIDC/SAML**.
- Kiểm tra các điều kiện bảo mật như **MFA**, **ExternalId**, **SourceArn/SourceAccount**, **session tags** và **source identity** khi chúng phù hợp.
- Xử lý các lỗi phổ biến như AccessDenied, principal không đúng, session hết hạn; kiểm tra phiên và giám sát bằng CloudTrail.
- Vận dụng assume role trong hệ thống AWS có Region/AZ, IAM, VPC, ứng dụng EC2/ECS/Lambda, lưu trữ S3, cơ sở dữ liệu, tích hợp sự kiện và yêu cầu phục hồi, giám sát, kiểm soát chi phí.

> **Phạm vi:** Bài tập trung vào **trust policy và assume role** thuộc chương **IAM và phân quyền** của module **CLOUD_PROVIDERS_AWS**. Đây là nền tảng nhận dạng và cấp quyền an toàn để triển khai các kiến trúc AWS; trust policy tự nó không thay thế cấu hình mạng, mã hóa, sao lưu hay giám sát.

## 1. IAM role giải quyết vấn đề gì?

Giả sử ứng dụng đặt trên Amazon EC2 cần đọc dữ liệu từ một bucket S3; hoặc một tác vụ ở **tài khoản AWS A** cần xem tài nguyên trong **tài khoản AWS B**. Có hai cách tiếp cận:

- Cấp access key dài hạn cho ứng dụng rồi lưu key trên máy chủ/CI: khó luân chuyển, dễ lộ, và thường bị tái sử dụng quá rộng.
- Tạo **IAM role** có quyền được xác định rõ; thực thể được tin cậy **assume role** để lấy **thông tin xác thực tạm thời** và thực hiện đúng các thao tác đã cho phép.

Phương án dùng role phù hợp với nguyên tắc **least privilege**, giảm phụ thuộc vào khóa dài hạn và hỗ trợ quản lý truy cập qua môi trường, tài khoản, dịch vụ và workload.

**IAM role** là một **IAM identity** trong tài khoản AWS, không gắn mặc định với một con người hay một máy chủ cố định. Một principal hợp lệ có thể sử dụng role nếu được cơ chế tin cậy và kiểm soát quyền cho phép. Khi assume thành công, principal làm việc dưới một **assumed-role session** với thông tin xác thực tạm thời.

### Những thuật ngữ cần phân biệt

| Thuật ngữ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Principal** | Thực thể gọi hoặc được xác thực để gọi AWS | IAM user, IAM role, service principal, danh tính liên kết |
| **IAM role** | Danh tính có thể được assume; mang quyền và cấu hình tin cậy | InventoryReadRole |
| **Trust policy** | Chính sách gắn với role, xác định **ai/cái gì được phép assume role**, bằng hành động STS và điều kiện nào | Chỉ tin cậy role từ account A |
| **Identity-based permissions policy** | Chính sách cấp quyền cho IAM identity thực hiện các API trên tài nguyên | Quyền sts:AssumeRole của caller; hoặc s3:GetObject của role |
| **Resource-based policy** | Chính sách gắn trực tiếp với tài nguyên; role trust policy là một dạng resource-based policy của IAM role | Bucket policy; role trust policy |
| **STS** | Dịch vụ phát hành thông tin xác thực bảo mật tạm thời | API AssumeRole |
| **Role session** | Ngữ cảnh tạm thời sau khi nhận role; có tên phiên, thông tin theo dõi và thời hạn | assumed-role/InventoryReadRole/report-2026 |
| **Session policy** | Chính sách thu hẹp quyền truyền khi tạo một số phiên STS | Chỉ cho đọc một prefix trong bucket |
| **Permissions boundary / SCP** | Lớp kiểm soát giới hạn quyền, tùy phạm vi sử dụng | Boundary của role; SCP của AWS Organizations |

Mấu chốt là **role có hai mặt**:

1. **Trust policy (cửa vào):** Ai có thể nhận role?
2. **Permission policies (quyền sau cửa):** Khi đã nhận role, phiên có thể làm gì?

Một trust policy cho phép một principal assume role **không tự động cấp** principal đó quyền đọc S3 hay sửa EC2. Tương tự, việc role có quyền rất mạnh **không có nghĩa** mọi người có thể nhận role.

## 2. Luồng STS AssumeRole hoạt động ra sao?

~~~mermaid
sequenceDiagram
    participant Caller as Principal nguồn
    participant STS as AWS STS
    participant IAM as IAM Policy Evaluation
    participant Service as Dịch vụ đích (ví dụ S3)
    Caller->>STS: AssumeRole(RoleArn, RoleSessionName, ...)
    STS->>IAM: Kiểm tra trust, quyền caller và điều kiện
    alt Được phép
        STS-->>Caller: AccessKeyId + SecretAccessKey + SessionToken + Expiration
        Caller->>Service: Gọi API đã ký bằng session credentials
        Service->>IAM: Đánh giá quyền hiệu lực của phiên trên tài nguyên
        IAM-->>Service: Allow hoặc Deny
        Service-->>Caller: Kết quả API
    else Không được phép
        STS-->>Caller: AccessDenied / lỗi điều kiện
    end
~~~

Các bước cụ thể:

1. **Caller có danh tính khởi đầu:** Có thể là người đăng nhập hợp lệ, workload đang mang role, dịch vụ AWS hay danh tính liên kết. Không phải nguồn nào cũng dùng đúng API STS tên **AssumeRole**.
2. **Caller xin nhận role:** Với trường hợp chuẩn, gọi **sts:AssumeRole** cùng role ARN và role session name; có thể kèm duration, MFA, ExternalId, session tags, source identity, session policy.
3. **AWS kiểm tra quyền:** Trust policy của role, quyền liên quan phía caller, điều kiện và các giới hạn tổ chức cùng tham gia việc cho phép hoặc từ chối.
4. **STS cấp credentials tạm thời:** Gồm **AccessKeyId**, **SecretAccessKey**, **SessionToken** và thời điểm **Expiration**. Đây là bộ thông tin cần thiết để ký yêu cầu AWS của phiên.
5. **Ứng dụng dùng credentials của phiên:** Các API về sau được đánh giá theo quyền hiệu lực của assumed role session và chính sách tài nguyên liên quan.
6. **Phiên hết hạn:** Ứng dụng cần lấy phiên mới theo luồng hợp lệ; không nên kỳ vọng credentials tạm thời dùng mãi được.

Tùy mô hình danh tính, AWS có các API STS liên quan như **AssumeRole**, **AssumeRoleWithWebIdentity** và **AssumeRoleWithSAML**. Việc workload lấy credentials từ metadata/endpoint riêng thường được SDK xử lý tự động theo cơ chế role được gắn với dịch vụ.

### ARN của role và ARN của phiên

Role được tham chiếu bằng ARN như:

~~~text
arn:aws:iam::444455556666:role/InventoryReadRole
~~~

Sau khi assume, danh tính phiên thường hiển thị với dạng:

~~~text
arn:aws:sts::444455556666:assumed-role/InventoryReadRole/report-2026
~~~

Hai ARN **khác nhau**: cái đầu định danh **role**; cái sau định danh **một phiên đã assume role**. Điều này quan trọng khi đọc CloudTrail, viết điều kiện dựa trên principal và xử lý sự cố phân quyền.

## 3. Cấu trúc trust policy

Trust policy được đặt trực tiếp trên **IAM role**, ở phần **Trust relationships / Assume role policy**. Cú pháp giống tài liệu JSON policy của IAM nhưng thường có phần **Principal** xác định ai được tin cậy.

Ví dụ role trong tài khoản B tin cậy một role xác định từ tài khoản A:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowBuildRunnerFromAccountA",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::111122223333:role/BuildAuditRunner"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

Ý nghĩa của từng trường:

| Trường | Cách đọc |
| --- | --- |
| **Version** | Phiên bản ngôn ngữ policy JSON của IAM, thường là 2012-10-17; **không phải** phiên bản tài liệu do người dùng tự tăng |
| **Statement** | Danh sách từng quy tắc |
| **Sid** | Nhãn giúp nhận diện quy tắc, không làm thay đổi quyền |
| **Effect** | Allow hoặc Deny |
| **Principal** | Ai được áp dụng quy tắc tin cậy, ví dụ AWS role hoặc service principal |
| **Action** | STS operation cho phép, ví dụ sts:AssumeRole hoặc sts:AssumeRoleWithWebIdentity |
| **Condition** | Điều kiện bổ sung dựa trên khóa context như sts:ExternalId, aws:MultiFactorAuthPresent |

**Cẩn trọng:** Nếu dùng một ARN có dạng **arn:aws:iam::111122223333:root** làm AWS principal trong trust policy, ý nghĩa thường là **ủy quyền cho tài khoản** để tài khoản ấy quyết định principal nào được assume bằng identity-based permissions; nó **không chỉ định riêng root user**. Chỉ rõ role ARN khi muốn thu hẹp người nhận role. Tránh dùng principal mở rộng (đặc biệt ký tự đại diện) khi không có điều kiện phòng vệ được kiểm tra cẩn thận.

Trust policy có thể chứa nhiều statement và điều kiện. Khi debug, cần xem **toàn bộ** statement, bao gồm Deny rõ ràng, chứ không chỉ một dòng Allow.

## 4. Cross-account assume role: hai phía phải phối hợp

Xét bài toán công ty tách tài khoản để giảm phạm vi ảnh hưởng:

- **Account A — 111122223333:** nơi có role **BuildAuditRunner**, chạy tác vụ báo cáo.
- **Account B — 444455556666:** nơi chứa bucket báo cáo **audit-inventory-example**, role **InventoryReadRole** và dữ liệu cần đọc.
- Mục tiêu: tác vụ từ A tạm nhận role trong B để **xem danh sách và đọc object** trong bucket của B, không cần chia sẻ access key IAM user của B.

### 4.1. Phía B: Trust policy cho ai nhận role

Trên **InventoryReadRole** trong B, gắn trust policy:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "TrustBuildAuditRunner",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::111122223333:role/BuildAuditRunner"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

Từ đó role trong A là một principal được tin cậy **ở cửa vào** của role trong B.

### 4.2. Phía A: Cho phép caller gọi AssumeRole

Gắn identity-based policy sau vào **BuildAuditRunner** trong A:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "MayAssumeInventoryReadRole",
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": "arn:aws:iam::444455556666:role/InventoryReadRole"
    }
  ]
}
~~~

Trong tình huống **cross-account** thông thường, quyền AssumeRole phải được **phía tài khoản nguồn** cho phép và **trust policy tài khoản đích** chấp nhận. Nếu thiếu một phía, AssumeRole có thể bị từ chối. SCP, permissions boundary hoặc Deny rõ ràng còn có thể giới hạn thêm.

**Lưu ý nâng cao:** Đối với một số trường hợp **cùng tài khoản**, việc trust policy trực tiếp liệt kê IAM principal có thể đủ để cấp quyền assume role mà không cần identity policy Allow riêng, tùy loại principal và cách cấp quyền. Đừng máy móc áp dụng quy tắc “luôn bắt buộc hai Allow” cho mọi loại principal; phải đánh giá theo ngữ cảnh.

### 4.3. Phía B: Cho role làm gì sau khi nhận

Identity-based permissions policy gắn với **InventoryReadRole** trong B:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ListOnlyReportBucket",
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::audit-inventory-example"
    },
    {
      "Sid": "ReadOnlyObjectsInReportBucket",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::audit-inventory-example/*"
    }
  ]
}
~~~

Bây giờ phiên nhận role có quyền đọc bucket theo ví dụ trên, **nhưng không có quyền ghi object, xóa bucket hay quản trị IAM**. Nếu bucket có bucket policy Deny, cơ chế mã hóa bằng KMS hoặc các kiểm soát khác, quyền thực tế còn phụ thuộc những lớp đó.

Ba tài liệu policy cần nhớ:

| Tại đâu | Policy | Trả lời câu hỏi |
| --- | --- | --- |
| Account B, InventoryReadRole | **Trust policy** | Principal nào từ A được assume role? |
| Account A, BuildAuditRunner | **Identity policy** | Caller có quyền gọi sts:AssumeRole cho ARN này không? |
| Account B, InventoryReadRole | **Permissions policy** | Sau khi assume, phiên được thao tác với tài nguyên nào? |

Đây là mô hình phổ biến cho **CI/CD liên tài khoản**, **quản trị tập trung**, **đọc dữ liệu báo cáo**, hoặc **workload một account gọi tài nguyên account khác**.

## 5. Thực hành đọc và dùng role bằng AWS CLI

**Điều kiện tiên quyết:** có hai tài khoản lab được phép sử dụng; có quyền tạo hoặc cập nhật role/policy trong môi trường học; cấu hình AWS CLI từ một nguồn danh tính hợp lệ. Các ARN, account ID và bucket bên dưới là **giá trị minh họa**, phải thay bằng tài nguyên thật của môi trường lab. Không dùng tài khoản sản xuất để thử chính sách học tập.

### 5.1. Xác nhận principal nguồn

Đầu tiên, kiểm tra cấu hình profile dùng để gọi AssumeRole:

~~~bash
aws sts get-caller-identity --profile runner-a
~~~

Kỳ vọng principal là **BuildAuditRunner** trong tài khoản A, có thể xuất hiện dưới dạng assumed-role ARN nếu profile nguồn cũng đang dùng một role. Nếu là principal khác, trust policy tại B sẽ cần được điều chỉnh cho đúng danh tính thực sự và được cấp phép; đừng nới Principal thành ký tự đại diện để né lỗi.

### 5.2. Gọi STS trực tiếp để hiểu kết quả

~~~bash
aws sts assume-role \
  --profile runner-a \
  --role-arn arn:aws:iam::444455556666:role/InventoryReadRole \
  --role-session-name inventory-lab-01 \
  --duration-seconds 3600
~~~

Một phản hồi rút gọn có dạng:

~~~json
{
  "Credentials": {
    "AccessKeyId": "ASIA...EXAMPLE",
    "SecretAccessKey": "***",
    "SessionToken": "***",
    "Expiration": "2026-11-20T04:00:00+00:00"
  },
  "AssumedRoleUser": {
    "Arn": "arn:aws:sts::444455556666:assumed-role/InventoryReadRole/inventory-lab-01"
  }
}
~~~

Giá trị trên chỉ minh họa cấu trúc, **không phải credentials có thể dùng**. Trong vận hành thật, **không gửi kết quả lệnh chứa SecretAccessKey và SessionToken vào chat, log, ticket hay repository**. Cẩn trọng cả với terminal history, CI output và việc copy JSON ra file.

AWS CLI/SDK có thể tự tạo và làm mới phiên bằng profile assume-role, giảm nhu cầu thao tác thủ công với secret. Ví dụ cấu hình trong **AWS CLI config**:

~~~ini
[profile inventory-read]
role_arn = arn:aws:iam::444455556666:role/InventoryReadRole
source_profile = runner-a
role_session_name = inventory-lab-01
region = ap-southeast-1
~~~

Sau khi profile **runner-a** đã được cấu hình và có quyền hợp lệ:

~~~bash
aws sts get-caller-identity --profile inventory-read
aws s3 ls s3://audit-inventory-example --profile inventory-read
~~~

Lệnh đầu giúp xác nhận đã ở **assumed role** trong B. Lệnh thứ hai xác minh quyền S3 thực tế. Nếu thao tác thất bại, xem thông báo và các lớp policy trước khi thay đổi quyền.

### 5.3. Quan sát audit trail

Trong **AWS CloudTrail**, lọc sự kiện STS có tên **AssumeRole** quanh thời điểm thực hành; kiểm tra role ARN, principal nguồn, tên phiên và kết quả. Đối với API tài nguyên, có thể nhìn thấy **assumed-role session** là caller của yêu cầu. Phạm vi sự kiện CloudTrail được ghi và cách truy vấn phụ thuộc cấu hình trail/event data store, loại sự kiện và dịch vụ. Không mặc định rằng mọi data event của S3 đã được bật.

**Sau lab:** Xóa hoặc thu hồi các role/policy và tài nguyên demo bằng quy trình được phép của môi trường; kiểm tra chi phí liên quan, đặc biệt các dịch vụ đi kèm nếu dùng tới.

## 6. Tin cậy dịch vụ AWS: EC2, Lambda và ECS

Workload trên AWS nên dùng **IAM role gắn với dịch vụ** để SDK lấy credentials ngắn hạn tự động, thay vì đưa access key vào image, biến môi trường hoặc file cấu hình.

### 6.1. EC2 instance role

Ví dụ trust policy của một role dành cho EC2:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ec2.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

Role được gắn với EC2 thông qua **instance profile**. Ứng dụng trên máy có thể sử dụng AWS SDK default credential chain để lấy credentials từ **Instance Metadata Service (IMDS)**, thay vì tự quản lý key. Bật và ưu tiên **IMDSv2** theo cấu hình bảo mật phù hợp; giới hạn truy cập metadata và không cho tất cả tiến trình trong một máy cùng sở hữu quyền quá rộng nếu chúng cần ranh giới riêng.

### 6.2. Lambda execution role

Ví dụ trust policy:

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

**Execution role** cấp quyền để hàm Lambda gọi tài nguyên AWS và ghi log khi được cấp quyền phù hợp. Nếu hàm cần đọc DynamoDB và ghi object vào S3, cấp đúng các action/resource cần thiết. **Resource-based policy của Lambda** cho phép một dịch vụ khác **invoke hàm** là vấn đề khác với **execution role** của hàm.

### 6.3. ECS task role và task execution role

Trong Amazon ECS, đừng nhầm hai vai trò:

- **Task role:** Danh tính mà **mã trong container** sử dụng để gọi S3, SQS, DynamoDB, Secrets Manager (nếu cần).
- **Task execution role:** Quyền dùng bởi thành phần thực thi tác vụ để làm các việc như **kéo image từ ECR, gửi log** và một số bước khởi tạo tích hợp theo cấu hình.

Cả hai thường sử dụng **ecs-tasks.amazonaws.com** trong trust policy, nhưng **permissions policy phải khác theo nhiệm vụ**. Nếu task cần đọc bucket, quyền đó thường thuộc **task role**, không nên nhét vào execution role chỉ vì container cũng chạy trong ECS.

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ecs-tasks.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

### 6.4. EKS: danh tính của Pod

Với Amazon EKS, hai mô hình thường gặp là **IAM Roles for Service Accounts (IRSA)** thông qua OIDC và **EKS Pod Identity**. Mỗi mô hình có cơ chế trust và điều kiện riêng. Trong IRSA, Kubernetes ServiceAccount thường tương ứng với điều kiện **sub** trong OIDC token. Với EKS Pod Identity, trust dùng service principal tương ứng và các hành động STS cần thiết, còn liên kết Pod Identity được quản lý qua EKS.

**Không sao chép nguyên trust policy của EC2, Lambda hoặc ECS sang EKS**: principal, token và điều kiện xác thực khác nhau. Việc chọn giải pháp còn phụ thuộc loại cluster, khả năng tương thích của workload và cách quản trị danh tính.

## 7. Federation: AssumeRoleWithWebIdentity và AssumeRoleWithSAML

Trong hệ thống nhiều nhóm/phần mềm, người dùng hoặc CI/CD có thể đã được định danh bởi một **identity provider (IdP)** khác AWS. Federation giảm nhu cầu tạo IAM user cùng long-term access key.

### 7.1. OIDC cho CI/CD hoặc workload

Ví dụ GitHub Actions dùng OIDC để nhận role trong tài khoản AWS. Account AWS cần có IAM OIDC provider đúng nhà phát hành, audience phù hợp và trust policy giới hạn claim:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "GithubMainBranchOnly",
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::444455556666:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:sample-org/sample-repo:ref:refs/heads/main"
        }
      }
    }
  ]
}
~~~

Ví dụ này chỉ cho luồng mang **subject claim đúng repository và nhánh main** được xem xét assume role. Trong một số sự kiện GitHub, định dạng **sub** thay đổi khi dùng environment, pull request hoặc cấu hình claim tùy chỉnh; cần xác nhận giá trị claim thực tế trước khi thiết lập trust.

**Không dùng** điều kiện quá rộng kiểu repo:* hoặc bỏ qua audience/subject nếu không có lý do rõ ràng. OIDC chỉ chứng minh nguồn token và các claim được chấp nhận; **permission policy của role vẫn cần giới hạn** quyền deploy hoặc đọc tài nguyên.

### 7.2. SAML và đăng nhập doanh nghiệp

Với SAML 2.0, role trust thường có **Federated principal** là SAML provider trong IAM, action **sts:AssumeRoleWithSAML** và điều kiện về audience hoặc các attribute cần thiết. Cấu hình cần thống nhất giữa IdP và AWS.

Khi triển khai đăng nhập cho nhân viên qua **AWS IAM Identity Center**, thường quản lý quyền bằng **permission set** và cơ chế gán account/group/user do dịch vụ cung cấp. Không nên tự tay sửa trust policy của các role do IAM Identity Center quản lý nếu không có quy trình chính thức.

### Phân biệt ba kiểu gọi STS

| API / cách nhận role | Dùng cho | Đầu vào xác thực nổi bật |
| --- | --- | --- |
| **AssumeRole** | Principal AWS đã được xác thực muốn chuyển sang role khác | Credentials của caller, role ARN, session name; có thể có MFA/ExternalId |
| **AssumeRoleWithWebIdentity** | Token OIDC/web identity từ IdP được tin cậy | ID token, role ARN, session name; trust kiểm tra issuer/audience/subject |
| **AssumeRoleWithSAML** | Danh tính SAML được liên kết với AWS | SAML assertion và principal/role phù hợp |
| **Credentials do dịch vụ tự cấp** | EC2/ECS/Lambda/EKS theo cơ chế tích hợp | Role được gắn với workload; SDK lấy/refresh theo credential provider chain |

## 8. Điều kiện trust policy để giảm rủi ro

Cho phép đúng principal mới chỉ là lớp đầu. Điều kiện giúp tránh việc role bị assume trong bối cảnh không mong muốn.

### 8.1. MFA cho hoạt động quản trị của con người

Với tình huống IAM principal dùng STS AssumeRole và bắt buộc có MFA, trust policy có thể yêu cầu:

~~~json
"Condition": {
  "Bool": {
    "aws:MultiFactorAuthPresent": "true"
  }
}
~~~

Điều kiện này cần được áp dụng đúng loại danh tính/luồng xác thực. Một workload tự động hoặc federation không mang context key MFA như IAM caller có thể bị từ chối. Không nên chèn điều kiện MFA một cách máy móc vào role của EC2/Lambda hoặc OIDC.

### 8.2. ExternalId cho bên thứ ba và vấn đề confused deputy

Tình huống: công ty thuê một nhà cung cấp SaaS quản lý tài nguyên trong AWS account của khách hàng. Nhiều khách hàng có thể tin cậy cùng một principal của nhà cung cấp. Nếu không ràng buộc đúng, kẻ xấu có thể cố khiến nhà cung cấp dùng quyền của một khách hàng khác: **confused deputy**.

Trong kịch bản nhà cung cấp **AssumeRole**, thêm điều kiện:

~~~json
"Condition": {
  "StringEquals": {
    "sts:ExternalId": "tenant-customer-unique-value"
  }
}
~~~

Nhà cung cấp truyền cùng giá trị trong tham số **ExternalId** của AssumeRole. ExternalId nên được **gán duy nhất cho quan hệ khách hàng**, do bên cung cấp dịch vụ quản lý theo thiết kế tích hợp. **ExternalId không phải mật khẩu bí mật**, không thay IAM principal restriction hoặc quyền caller; nó là một ràng buộc ngữ cảnh giảm nguy cơ nhầm khách hàng.

### 8.3. SourceArn và SourceAccount cho dịch vụ AWS

Với một số kịch bản dịch vụ AWS thay mặt tài nguyên của bạn gọi role/service, các điều kiện như **aws:SourceArn** và **aws:SourceAccount** giúp hạn chế nguồn phát sinh yêu cầu và giảm nguy cơ confused deputy.

Ví dụ mẫu **chỉ để minh họa cấu trúc**:

~~~json
"Condition": {
  "StringEquals": {
    "aws:SourceAccount": "444455556666"
  },
  "ArnLike": {
    "aws:SourceArn": "arn:aws:some-service:ap-southeast-1:444455556666:some-resource/example"
  }
}
~~~

**Không đưa nguyên ví dụ này lên môi trường thật:** tiền tố ARN, loại nguồn và context key khả dụng khác nhau theo dịch vụ. Kiểm tra tài liệu của **đúng dịch vụ** để biết có hỗ trợ các key này trong trust policy và cách điền ARN.

### 8.4. Source identity và session tags

- **Source identity:** Với luồng STS hỗ trợ, định danh nguồn có thể gắn vào phiên để hỗ trợ truy vết xuyên qua các lần assume role. Quyền dùng **sts:SetSourceIdentity** cần được cho phép trong trust policy liên quan; kiểm tra thêm các yêu cầu khi role chaining.
- **Session tags:** Đính kèm thuộc tính phiên như project, team, environment. Để truyền tags trong AssumeRole, trust policy phải cho phép thao tác liên quan **sts:TagSession**; có thể giới hạn key/value bằng các điều kiện STS/AWS phù hợp.
- **ABAC (Attribute-Based Access Control):** Role permissions có thể dựa vào principal tag, resource tag và điều kiện nhất quán. Nhưng **session tags do caller tự gửi không tự động đáng tin**. Hãy kiểm soát ai được đặt tag nào và có thể ghi đè tag nào.
- **RoleSessionName:** Hữu ích để đọc audit log, có thể ràng buộc bằng **sts:RoleSessionName** khi cần quy ước đặt tên. Tránh đưa dữ liệu cá nhân/bí mật vào tên phiên.

Source identity, session name và session tags phục vụ các mục đích liên quan nhưng khác nhau: **truy vết nguồn**, **phân biệt phiên** và **thuộc tính cấp quyền**.

## 9. Quyền hiệu lực của phiên: vì sao AssumeRole thành công vẫn AccessDenied?

AssumeRole chỉ hoàn thành bước **đổi/ngữ cảnh danh tính**. Khi phiên gọi S3, DynamoDB, KMS, EC2, CloudWatch hoặc bất kỳ API khác, AWS lại đánh giá **authorization**.

Các lớp thường tham gia:

1. **Identity-based permissions** gắn với role: Allow nào được cấp cho action/resource?
2. **Session policies**, nếu được truyền: giới hạn thêm quyền của phiên; không thể tự cộng quyền vượt role.
3. **Permissions boundary**, nếu áp dụng cho role: giới hạn phần quyền cấp qua identity policy.
4. **AWS Organizations SCP** (và các lớp kiểm soát tổ chức tương ứng): đặt giới hạn quyền đối với principal thuộc account/member chịu tác động; SCP không tự cấp Allow.
5. **Resource-based policy**: có thể cho phép hoặc từ chối tùy tài nguyên và principal; cách tương tác với implicit deny trong identity/boundary/session policy có các ngoại lệ theo loại principal được chỉ định, nhất là khi policy cấp trực tiếp cho **assumed-role session ARN**.
6. **Explicit Deny và các policy đặc thù**: explicit Deny ở lớp policy liên quan thường thắng Allow; còn có thể có VPC endpoint policy, KMS key policy, dịch vụ điều kiện khác.

Ví dụ: role InventoryReadRole có s3:GetObject nhưng object S3 được mã hóa bằng **SSE-KMS**. Đọc object có thể vẫn thất bại nếu phiên thiếu quyền KMS thích hợp hoặc key policy không cho phép. Tương tự, bucket policy có một Deny theo điều kiện network/identity vẫn có thể chặn truy cập.

**Không suy luận quyền chỉ từ một policy JSON.** Cần xem action, resource ARN, principal ở thời điểm gọi, request context, session policy và tất cả lớp kiểm soát áp dụng. Với mô hình nhiều tài khoản, xem cả phía tài nguyên lẫn phía principal.

### Session policy để thu hẹp quyền

Khi gọi AssumeRole, caller có thể truyền **inline session policy** hoặc **managed session policy ARN** theo khả năng API cho phép. Ví dụ role có quyền đọc toàn bucket, nhưng một phiên chỉ nên đọc prefix báo cáo:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::audit-inventory-example/reports/2026/*"
    }
  ]
}
~~~

Phiên nhận role chỉ có tập quyền nằm trong phần giao nhau giữa quyền role và session policy, subject to các lớp kiểm soát khác. Session policy **không thể cấp s3:PutObject** nếu role vốn không có quyền tương ứng. Nếu cung cấp session policy quá hẹp, lệnh trước đây được phép có thể bắt đầu nhận AccessDenied.

## 10. Thời hạn phiên, làm mới và role chaining

- Mỗi STS session có **Expiration**. Người dùng/ứng dụng cần làm mới trước khi dùng tiếp; SDK và AWS CLI credential provider thường tự quản lý khi được cấu hình đúng.
- Với **AssumeRole**, thông số **DurationSeconds** và **maximum session duration** của role chi phối thời gian hợp lệ. Role có thể cấu hình maximum session duration trong khoảng thường gặp **1–12 giờ**, nhưng API/luồng cụ thể có giới hạn riêng.
- **Role chaining** là dùng credentials của một assumed role để assume một role khác. Với STS AssumeRole trong role chaining, thời hạn phiên mới tối đa **1 giờ**, ngay cả khi role đích cho phép lâu hơn.
- Thời hạn của role credentials do các dịch vụ AWS tự cung cấp có cơ chế riêng; đừng tự áp mọi quy tắc duration CLI vào mọi service integration.
- Thu hồi quyền: sửa trust policy có thể chặn **những lần assume mới**, nhưng **credentials đã phát hành vẫn có thể còn hiệu lực cho tới khi hết hạn** trừ khi thực hiện các cơ chế vô hiệu hóa/thu hồi phiên phù hợp. Khi phản ứng sự cố, phải xử lý cả phiên đang hoạt động.

### Vì sao không lưu temporary credentials dài hạn?

Credentials tạm thời vẫn là **bí mật có thể bị lạm dụng trong thời gian còn hiệu lực**. Không ghi vào Git, Docker image, CI logs, URL, thư mục chia sẻ; tránh hiển thị kết quả lệnh STS trên màn hình chia sẻ. Dùng IAM role gắn workload và AWS SDK/CLI credential providers để giảm việc phải tự xử lý bộ ba access key, secret key, session token.

## 11. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| **AccessDenied tại AssumeRole** | Trust policy không tin cậy đúng principal; caller thiếu quyền sts:AssumeRole; Deny/SCP/boundary; thiếu MFA/ExternalId | Gọi sts:GetCallerIdentity; đọc trust, caller identity policy, Condition và giới hạn tổ chức |
| **AccessDenied khi đọc S3 sau khi AssumeRole thành công** | Role thiếu s3:GetObject/ListBucket; resource policy Deny; KMS key policy/permission; session policy bó hẹp | Xác nhận ARN phiên; đối chiếu action/resource thực tế và các policy theo tài nguyên |
| **The security token included in the request is expired/invalid** | Hết thời hạn; thiếu SessionToken; dùng lẫn credentials từ nhiều profile | Kiểm tra Expiration, credential source/provider chain và clock; refresh phiên |
| **Principal ARN không khớp** | Trust tin cậy role khác, IAM principal đã thay đổi, role được xóa rồi tạo lại | Xem GetCallerIdentity, ARN và trust relationship; cập nhật đúng principal hợp lệ |
| **OIDC AssumeRoleWithWebIdentity bị từ chối** | Issuer, audience, subject, token expiry hoặc IAM OIDC provider không khớp | Kiểm tra token claims, trust Condition, provider và workflow thực tế |
| **Phiên chỉ chạy tối đa một giờ** | Caller đang role chaining bằng AssumeRole | Xác định chuỗi vai trò và thiết kế lại cách cấp credentials phù hợp |
| **Dịch vụ AWS không dùng được role** | Sai service principal, role chưa được gắn đúng, thiếu instance profile hoặc role mapping | Kiểm tra loại role và cấu hình tích hợp EC2/ECS/Lambda/EKS |
| **CloudTrail không hiển thị API dữ liệu mong muốn** | Chưa bật đúng loại data event / phạm vi ghi | Xem cấu hình trail hoặc event data store, account và Region |

### Quy trình xử lý ngắn gọn

~~~text
1. Xác nhận principal thực bằng sts:GetCallerIdentity.
2. Lỗi xảy ra ở lời gọi STS AssumeRole hay lời gọi dịch vụ sau đó?
   ├─ Ở STS: xem trust policy, sts:AssumeRole của caller,
   │         principal, Condition, SCP/boundary và loại STS API.
   └─ Ở dịch vụ: xem quyền phiên, session policy, resource policy,
                 key policy và request context của tài nguyên.
3. Dò đúng request/time/account trong CloudTrail và log ứng dụng.
4. Tạo thay đổi nhỏ, tăng đúng quyền còn thiếu, không mở wildcard vô tội vạ.
5. Kiểm tra lại thành công và xác nhận quyền ngoài phạm vi vẫn bị từ chối.
~~~

Khi nghi có xung đột policy phức tạp, có thể sử dụng **IAM Policy Simulator** hoặc **IAM Access Analyzer** để hỗ trợ đánh giá trong phạm vi công cụ hỗ trợ, kết hợp thử nghiệm thực tế trong môi trường kiểm soát. Kết quả mô phỏng không thể thay thế mọi điều kiện runtime của từng dịch vụ.

## 12. Một ví dụ hệ thống nhiều thành phần

Một ứng dụng xử lý đơn hàng triển khai trong Region đã chọn, qua hai Availability Zone để tăng khả dụng:

~~~mermaid
flowchart TB
    C[Khách hàng] --> ALB[Application Load Balancer]
    ALB --> ECS[ECS task: Order API]
    ECS --> D[(RDS: đơn hàng)]
    ECS --> S3[S3: hóa đơn]
    ECS --> Q[SQS: yêu cầu xuất hóa đơn]
    Q --> L[Lambda: tạo hóa đơn]
    subgraph IAM[Quyền và trust role]
        T1[ECS task role]
        T2[Lambda execution role]
        T3[Cross-account reporting role]
    end
    ECS -. SDK credentials .-> T1
    L -. SDK credentials .-> T2
    L --> S3
    Rep[Job báo cáo account A] --> STS[STS AssumeRole]
    STS --> T3
    T3 -. Đọc báo cáo có kiểm soát .-> S3
    ECS --> CW[CloudWatch]
    L --> CW
~~~

**Thiết kế quyền ví dụ:**

| Thành phần | Trust / danh tính | Quyền tối thiểu cần suy xét |
| --- | --- | --- |
| ECS Order API | Task role trust **ecs-tasks.amazonaws.com** | Chỉ action SQS cần gửi, S3 cần tạo/đọc hóa đơn; xác thực RDS theo mô hình chọn |
| Lambda tạo hóa đơn | Execution role trust **lambda.amazonaws.com** | Chỉ đọc input và ghi đúng prefix S3; quyền log CloudWatch phù hợp |
| Job báo cáo trong account A | Role từ A assume một reporting role tại account B | Quyền AssumeRole giới hạn ARN; role đích chỉ đọc prefix báo cáo S3 |
| CI/CD triển khai | Role trust OIDC hoặc giải pháp federation đã kiểm soát | Chỉ cập nhật các resource cần deploy; thêm điều kiện repo/branch/environment |

**Các giới hạn của IAM:** IAM quyết định API AWS nào được phép; IAM **không tự bảo vệ** lưu lượng giữa container và database, không tự thiết lập subnet private, Multi-AZ, phục hồi backup hoặc cảnh báo lỗi. Để đạt yêu cầu an toàn và tin cậy của hệ thống, vẫn phải cấu hình VPC/security group, TLS, database credentials, logging, CloudWatch alarm, phương án backup/restore và AWS Budgets. Khi Lambda hoặc ECS mở rộng theo tải, quyền role giữ nguyên nhưng **số phiên/gọi API** có thể tăng, cần chú ý quota và chi phí tương ứng.

## 13. Checklist kiểm tra trust policy trước khi triển khai

- [ ] Xác định rõ role thuộc **account nào**, ai cần assume và vì sao.
- [ ] **Principal** được giới hạn đến role/user/service/IdP chính xác, tránh mở rộng không cần thiết.
- [ ] **Action STS** khớp luồng thực tế: AssumeRole, AssumeRoleWithWebIdentity hay AssumeRoleWithSAML.
- [ ] Với cross-account, kiểm tra **cả trust phía đích và quyền AssumeRole của caller phía nguồn**.
- [ ] Với dịch vụ AWS, kiểm tra **service principal** và phương thức attach role đúng (EC2 instance profile, Lambda execution role, ECS task role...).
- [ ] Áp dụng **MFA, ExternalId, OIDC aud/sub, SourceArn/SourceAccount, source identity/session tags** ở những kịch bản được hỗ trợ và có nhu cầu.
- [ ] Role permissions chỉ chứa các **action/resource cần thiết**, giảm wildcard; đánh giá session policy, boundary, SCP và resource policy.
- [ ] Credentials tạm thời được làm mới an toàn; không lưu secret vào source control hay logs.
- [ ] Có CloudTrail, cảnh báo/kiểm tra thay đổi role trust và cách điều tra principal đã nhận role.
- [ ] Đã thử **đường thành công** và ít nhất một **đường bị từ chối** để chứng minh giới hạn quyền thực sự hoạt động.
- [ ] Đã xét chi phí và vận hành của các dịch vụ mà role được dùng để truy cập, ví dụ S3, KMS, CloudWatch hoặc hệ thống chạy ở nhiều AZ.

## 14. Câu hỏi tự kiểm tra và bài tập

**Câu hỏi 1.** Một Lambda đã assume execution role thành công nhưng gọi S3 GetObject bị AccessDenied. Việc nào nên làm trước: sửa trust policy của Lambda hay kiểm tra permissions policy của role, bucket policy và KMS? **Gợi ý:** xác định lỗi ở bước nhận role hay bước gọi API S3.

**Câu hỏi 2.** Account A có policy cho role A gọi sts:AssumeRole tới B. Role B chưa tin cậy principal A. Cuộc gọi sẽ thế nào? **Gợi ý:** có quyền gọi API ở nguồn chưa đủ để vượt qua cổng trust ở đích.

**Câu hỏi 3.** Một CI pipeline sử dụng GitHub OIDC. Vì sao nên giới hạn aud, repository và branch/environment trong trust policy? **Gợi ý:** cùng nhà cung cấp token có nhiều repository và workflow khác nhau.

**Bài tập thực hành có kiểm soát:**

1. Dùng hai account lab hoặc hai role ở môi trường học được cấp phép. Tạo role **ReportReadRole** với trust giới hạn một principal cụ thể.
2. Cho principal nguồn quyền **sts:AssumeRole** tới đúng role ARN và gắn policy chỉ đọc một bucket/prefix thử nghiệm cho role đích.
3. Dùng AWS CLI profile để assume, kiểm tra **GetCallerIdentity** và thử đọc object cho phép.
4. Thử gọi **s3:PutObject** hoặc đọc prefix ngoài phạm vi và ghi nhận **AccessDenied** như bằng chứng least privilege.
5. Xem sự kiện **AssumeRole** trong CloudTrail; ghi lại role ARN, session name, account nguồn/đích mà không lưu secret.
6. Đổi một điều kiện trust có kiểm soát để tạo một lần AssumeRole bị từ chối, sau đó khôi phục chính sách hợp lệ và xác minh lại.

**Tiêu chí hoàn thành:** Người học giải thích được **ai tin cậy ai**, **ai được gọi STS**, **phiên nhận role được làm gì**, và **vì sao một request có thể bị từ chối** sau khi AssumeRole thành công.

## 15. Tổng kết

**Trust policy** là **cửa vào của IAM role**. **AssumeRole và các cơ chế federation liên quan** cung cấp danh tính phiên với **credentials tạm thời**. **Permissions policy**, session policy, resource policy và các lớp kiểm soát khác quyết định phiên **có thể thực hiện những API nào**. Với AWS thực tế, lựa chọn an toàn là xác định principal chính xác, giới hạn trust và quyền, để dịch vụ/SDK quản lý credentials, kiểm tra CloudTrail và thử quyền trên môi trường thật.

Kiến thức này liên kết trực tiếp với các bài toán chọn dịch vụ, thiết kế hệ thống Region/AZ, chạy workload trên EC2/ECS/Lambda, truy cập S3/RDS, tích hợp SQS và giám sát chi phí. Role chỉ giải quyết **danh tính và phân quyền**; kiến trúc hoàn chỉnh vẫn cần networking, backup, độ tin cậy, observability và kiểm soát chi phí.

**Nguồn tra cứu chính thức khi triển khai:** Tài liệu AWS IAM về *Role trust policies*, *IAM roles*, *Policy evaluation logic*; tài liệu AWS STS về *AssumeRole*, *AssumeRoleWithWebIdentity*, *AssumeRoleWithSAML*, *Session policies* và *Role chaining*; hướng dẫn *Cross-account access*, *AWS Well-Architected Security Pillar* và *AWS CloudTrail*. Hãy kiểm tra chính sách mới nhất, context keys và giới hạn dịch vụ theo loại principal và Region trước khi áp dụng vào production.
