# AWS STS và thông tin xác thực tạm thời

Một ứng dụng cần truy cập S3, RDS, DynamoDB hay một người quản trị cần kiểm tra VPC/EC2 đều phải chứng minh **danh tính** và có **quyền phù hợp**. Cách nhúng AWS access key dài hạn vào mã nguồn, container hoặc pipeline làm tăng nguy cơ rò rỉ, khó xoay vòng khóa và khó kiểm soát phạm vi truy cập. **AWS Security Token Service (AWS STS)** giúp cấp **temporary security credentials** cho các phiên truy cập có thời hạn, gắn với IAM role, identity federation hoặc các cơ chế cấp phiên khác.

Đây là bài học trong chương **IAM và phân quyền** của mô-đun **CLOUD_PROVIDERS_AWS**. Kiến thức STS kết nối trực tiếp với hạ tầng AWS theo account/Region/AZ; triển khai ứng dụng an toàn trên EC2, ECS, EKS và Lambda; phân quyền đối với mạng VPC, lưu trữ S3, cơ sở dữ liệu; truy vết bằng CloudTrail và kiểm soát tác động vận hành, chi phí.

> **Thông điệp chính:** Hãy cho người dùng và workload **nhận credentials ngắn hạn từ cơ chế danh tính được quản lý**, dùng IAM role với quyền tối thiểu, thay vì phân phối access key cố định. Temporary credentials vẫn là bí mật có thể bị lạm dụng trong suốt thời gian hiệu lực.

## 1. Kết quả học tập

Sau bài này, người học có thể:

1. Giải thích AWS STS và khác biệt giữa khóa dài hạn với temporary credentials.
2. Nhận diện `AccessKeyId`, `SecretAccessKey`, `SessionToken` và `Expiration`.
3. Phân biệt `AssumeRole`, `AssumeRoleWithWebIdentity`, `AssumeRoleWithSAML`, `GetSessionToken`, `GetFederationToken` và `GetCallerIdentity`.
4. Mô tả ba bước khi đổi quyền cross-account: **quyền caller**, **trust policy**, **permissions policy của role đích**.
5. Thực hành AWS CLI dùng profile assume role và kiểm tra principal mà không cần sao chép secrets.
6. Giải thích role chaining, session duration, session policies, MFA và ExternalId.
7. Ứng dụng mô hình STS vào Java/Spring Boot và workload EC2, ECS, Lambda, EKS, CI/CD.
8. Xử lý các lỗi sai identity, hết hạn token hoặc bị chặn quyền theo một trình tự rõ ràng.

## 2. Temporary security credentials là gì?

### 2.1. So sánh với access key dài hạn

| Tiêu chí | Access key của IAM user | Temporary security credentials |
|---|---|---|
| Thành phần | Access key ID và secret access key | Access key ID, secret access key, **session token** và thời điểm hết hạn |
| Thời hạn | Không tự hết hạn theo từng key | Có `Expiration`; sau đó AWS từ chối request ký bằng bộ credentials cũ |
| Được cấp bằng | Tạo và quản lý trên IAM user | AWS STS hoặc dịch vụ AWS tích hợp với role/federation |
| Quyền | IAM user và policy/guardrail liên quan | IAM role/session hoặc nguồn tạo phiên, kèm các giới hạn liên quan |
| Phù hợp | Một số trường hợp legacy/bất khả kháng | Người dùng qua IAM Identity Center; workload qua IAM role |
| Vấn đề bảo mật | Khóa có thể bị quên và tiếp tục hợp lệ | Giảm cửa sổ rủi ro, nhưng vẫn phải giữ kín khi token còn hiệu lực |

**Temporary không có nghĩa là vô hại.** Một bộ key và session token bị lộ có thể dùng để thao tác với tài nguyên AWS được cấp quyền, cho đến khi hết hạn hoặc quyền bị chặn. Không đưa secret/token vào commit, log, issue tracker, shell history, ảnh chụp màn hình hay kênh chat công khai.

### 2.2. Cấu trúc credentials

Một phản hồi STS điển hình gồm:

~~~json
{
  "Credentials": {
    "AccessKeyId": "ASIA...EXAMPLE",
    "SecretAccessKey": "<REDACTED>",
    "SessionToken": "<REDACTED>",
    "Expiration": "2030-01-01T12:00:00Z"
  }
}
~~~

*Đây là dữ liệu minh họa, không dùng để xác thực.*

- `AccessKeyId`: mã nhận diện của access key; temporary keys thường bắt đầu bằng `ASIA`.
- `SecretAccessKey`: bí mật dùng để ký request AWS Signature Version 4 cùng access key ID.
- `SessionToken`: bằng chứng của phiên tạm thời, cần được gửi kèm request, thường trong header `X-Amz-Security-Token`.
- `Expiration`: thời điểm hết hạn theo UTC. Sau mốc này phải lấy credentials mới.

Nếu thiếu session token, dù access key ID và secret access key đúng, request dùng temporary credentials cũng không hợp lệ. Ngược lại, credentials hợp lệ chưa đủ: IAM vẫn phải cho phép **action** trên **resource** tương ứng.

### 2.3. Luồng cấp và sử dụng credentials

~~~mermaid
sequenceDiagram
    participant W as Người dùng / Workload
    participant I as Identity provider / Nguồn IAM
    participant S as AWS STS
    participant P as IAM policy evaluation
    participant A as AWS service API
    W->>I: Xác thực danh tính hoặc nhận role từ runtime
    I-->>W: Danh tính/token hợp lệ
    W->>S: Xin phiên AssumeRole / Federation
    S->>P: Kiểm tra trust và điều kiện
    P-->>S: Allow hoặc Deny
    S-->>W: Temporary credentials + Expiration
    W->>A: Gửi signed request và session token
    A->>P: Đánh giá action/resource của phiên
    P-->>A: Allow hoặc Deny
    A-->>W: Kết quả API
~~~

Sơ đồ là **mô hình khái niệm**. Với EC2, ECS, Lambda và các tích hợp IAM Identity Center, AWS runtime/CLI/SDK thường tự xử lý việc cấp, cache và làm mới credentials. Ứng dụng không nhất thiết phải trực tiếp gọi `AssumeRole`.

## 3. Những API AWS STS quan trọng

| API | Khi nào sử dụng | Điều cần nhớ |
|---|---|---|
| `AssumeRole` | Principal AWS đã có quyền cần đảm nhận một IAM role, trong cùng hoặc khác account | Cần trust policy phù hợp; trong cross-account thông thường còn cần caller được phép `sts:AssumeRole` |
| `AssumeRoleWithWebIdentity` | Federation dùng OIDC/JWT từ nhà cung cấp danh tính được tin cậy, ví dụ CI hoặc một số mô hình EKS | STS xác minh token/claim và trust conditions; request không cần access key AWS nguồn |
| `AssumeRoleWithSAML` | Federation doanh nghiệp dựa trên SAML 2.0 | Dùng SAML assertion và trust policy |
| `GetSessionToken` | IAM user cần credentials tạm thời, thường để truy cập API yêu cầu MFA | Phiên giữ quyền IAM user, **không chuyển** sang một IAM role mới |
| `GetFederationToken` | Custom identity broker tạo phiên federated user | Session policy giới hạn quyền của phiên |
| `GetCallerIdentity` | Kiểm tra account ID, principal ARN và UserId của caller | **Không tạo credentials mới** |

### 3.1. AssumeRole và role session

Giả sử đội vận hành đang có identity hợp lệ trong account A. Họ cần truy vấn VPC ở account B mà không muốn có IAM user/access key riêng tại B. Quản trị viên B tạo IAM role `InventoryViewer`, cho role nguồn cụ thể của A quyền được assume, rồi cấp cho `InventoryViewer` những quyền đọc EC2 cần thiết.

AWS STS tạo một **assumed-role session**. Trong phiên đó, các request được đánh giá theo quyền của role B (và các policy khác có hiệu lực). Quyền của caller A không tự động cộng vào quyền của role B.

### 3.2. Federation: OIDC và SAML

Nhà cung cấp danh tính (IdP) có thể xác thực người dùng/workload **bên ngoài AWS**. Với OIDC, STS kiểm tra token JWT từ IdP đã cấu hình, sau đó đánh giá `aud`, `sub` hoặc các claim/điều kiện trust phù hợp. Một token OIDC hợp lệ **không tự động được assume mọi IAM role**.

Ví dụ: GitHub Actions có thể trao đổi OIDC token lấy role phục vụ triển khai, thay vì lưu AWS secret key dài hạn trong CI. Trust policy nên ràng buộc repository/nhánh hoặc environment, audience và các điều kiện phù hợp. Với SAML, AWS xử lý assertion theo trust của SAML provider.

### 3.3. GetSessionToken và GetFederationToken

`GetSessionToken` được dùng chủ yếu bởi IAM user trong trường hợp cần chương trình xác thực MFA; temporary credentials nhận được kế thừa quyền của IAM user và chịu giới hạn riêng với một số API IAM/STS. `GetFederationToken` phục vụ custom identity broker, có session policies để khống chế quyền của federated user.

Hai API này hữu ích khi gặp hệ thống legacy, nhưng ứng dụng mới thường ưu tiên IAM Identity Center cho nhân sự và IAM role cho workload. Không giả định mọi temporary credentials đều được quyền tiếp tục gọi các API STS khác như `GetSessionToken` hay `GetFederationToken`.

## 4. Thời hạn phiên, làm mới và thu hồi

### 4.1. Các mốc thời gian

| API / cơ chế | Giới hạn liên quan |
|---|---|
| `AssumeRole` | Từ **15 phút** đến `MaxSessionDuration` của role; thời hạn mặc định request thường **1 giờ** |
| `MaxSessionDuration` của IAM role | Có thể cấu hình từ **1 đến 12 giờ** |
| **Role chaining**: role session assume role khác | `AssumeRole` tiếp theo có tối đa **1 giờ** |
| `AssumeRoleWithWebIdentity` / `AssumeRoleWithSAML` | Thông thường 15 phút đến mức tối đa của role, tùy điều kiện áp dụng |
| `GetSessionToken` của IAM user | 15 phút đến **36 giờ**, mặc định thường 12 giờ |
| `GetFederationToken` của IAM user | 15 phút đến **36 giờ**, mặc định thường 12 giờ |

**Tình huống:** Role đích cho phép phiên tối đa 12 giờ, nhưng caller đã sử dụng một assumed-role session và gọi `AssumeRole` với `--duration-seconds 7200` (2 giờ). Request bị từ chối bởi **role chaining 1 giờ**. Giảm thời hạn xuống `3600` giây hoặc thiết kế lại luồng giả định role.

Thời hạn của AWS access portal, phiên đăng nhập IAM Identity Center, token IdP và STS role session có thể **khác nhau**. Người dùng còn đăng nhập được Console không bảo đảm credentials cũ trong SDK vẫn còn hạn.

### 4.2. Cơ chế làm mới

- AWS CLI có thể tự dùng `role_arn` và `source_profile` để gọi `AssumeRole`, lưu credentials trong cache và làm mới khi cần.
- AWS SDK dùng **credentials provider** để tự tải/cache/refresh, thay vì tạo access key tĩnh trong code.
- EC2 instance role, ECS task role, Lambda execution role và các tích hợp của EKS cung cấp temporary credentials qua môi trường runtime.
- Khi phiên nguồn (ví dụ IAM Identity Center) hết hạn, người dùng có thể cần đăng nhập lại trước khi CLI xin role session mới.

Không nên gọi STS cho từng request tới S3/DynamoDB vì tạo thêm độ trễ và tiêu tốn quota. Tái sử dụng SDK client/provider và để runtime quản lý vòng đời.

### 4.3. Token hết hạn và sự cố lộ credentials

Sau `Expiration`, AWS không chấp nhận bộ credentials cũ. Khi nghi có rò rỉ **trước thời điểm này**, cần ứng phó ngay: điều tra, giảm/chặn quyền, xem xét cơ chế **Revoke active sessions** của IAM role và rà soát CloudTrail. Xóa key/token khỏi máy của developer không vô hiệu hóa bản sao đã bị người khác lấy. Việc thay đổi policy/trust và cơ chế thu hồi phải được đánh giá theo mô hình quyền IAM thực tế.

## 5. Quy tắc quyền khi AssumeRole

Trong luồng **cross-account** thường có ba phần:

1. **Caller permission policy** ở account A cho phép `sts:AssumeRole` vào role B.
2. **Role trust policy** ở account B tin cậy caller A và kiểm tra các điều kiện có liên quan.
3. **Role permissions policy** ở account B cho phép những AWS API actions mà phiên sau khi assume được thực hiện.

~~~mermaid
flowchart LR
    C["Account A / caller TeamOperator"] --> CP["Policy cho phép sts:AssumeRole"]
    CP --> T{"Trust policy role InventoryViewer tại Account B"}
    T -->|Deny| X["AccessDenied"]
    T -->|Allow| S["AWS STS cấp role session"]
    S --> R["Role permissions và session restrictions"]
    R --> E["Đánh giá SCP / boundary / resource policies"]
    E --> A["Đọc EC2 / VPC APIs"]
~~~

AWS có nhiều loại policy: identity-based, resource-based, session policies, permissions boundary, service control policies (SCP), resource control policies (RCP) khi áp dụng. **Explicit deny** thắng những allow. Còn có các trường hợp resource-based policy cấp quyền trực tiếp cho **role session ARN**, dẫn đến cách tính implicit deny đặc biệt. Vì vậy, hãy dùng ba phần ở trên làm mô hình nền tảng và kiểm tra policy evaluation khi xây hệ thống thật.

## 6. Ví dụ IAM cross-account: đọc tài nguyên mạng

Giả định:

- **Account A:** `111122223333`, IAM role nguồn `TeamOperator`.
- **Account B:** `444455556666`, IAM role đích `InventoryViewer`.
- **Mục tiêu:** `TeamOperator` được assume `InventoryViewer` để đọc VPC, subnet, instance; không tạo/xóa tài nguyên.
- **Region thực hành:** `ap-southeast-1` (Singapore).

Các account ID và role đều là **dữ liệu giả định**. Các policy chỉ phục vụ học tập; việc triển khai trong hệ thống thật cần quản trị viên xác minh ARN/điều kiện và áp dụng qua quy trình thay đổi được kiểm soát.

### 6.1. Policy nguồn: cho phép gọi AssumeRole

Identity-based policy gắn với `TeamOperator` trong account A:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AssumeInventoryViewer",
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": "arn:aws:iam::444455556666:role/InventoryViewer"
    }
  ]
}
~~~

Policy này cho phép **gửi yêu cầu AssumeRole** lên role đích, chưa cấp trực tiếp quyền `ec2:DescribeVpcs` của account B.

### 6.2. Trust policy đích: ai được assume?

Trust relationship của `InventoryViewer` ở account B:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "TrustTeamOperator",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::111122223333:role/TeamOperator"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

Trust policy này nói rằng role nguồn cụ thể được phép assume; nó **không** quyết định role sau khi assume sẽ được dùng những EC2 APIs nào. Cross-account access thông thường cần cả trust lẫn quyền cho caller, và có thể còn bị giới hạn bởi SCP, permission boundary và policy liên quan.

### 6.3. Role permissions policy đích: được làm gì?

Permissions policy cho `InventoryViewer`:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadEc2VpcMetadata",
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeVpcs",
        "ec2:DescribeSubnets",
        "ec2:DescribeInstances"
      ],
      "Resource": "*"
    }
  ]
}
~~~

Một số thao tác `Describe*` của EC2 sử dụng `Resource: "*"` theo mô hình authorization của API. Điều này không trao mọi action. Có thể kết hợp điều kiện Region, tổ chức hoặc các guardrail khác khi thiết kế hệ thống.

### 6.4. Vì sao vẫn bị AccessDenied?

| Tình huống | Hệ quả |
|---|---|
| Caller có `sts:AssumeRole` nhưng trust không tin caller | STS từ chối AssumeRole |
| Trust tin caller nhưng caller cross-account thiếu `sts:AssumeRole` | STS từ chối AssumeRole |
| Assume thành công, role đích không cho `ec2:DescribeVpcs` | Request đọc VPC bị từ chối |
| Role có allow nhưng tổ chức áp dụng explicit deny phù hợp | Request vẫn có thể bị chặn |
| Caller và role cùng account, trust cấp trực tiếp cho IAM principal | Có những quy tắc resource-based đặc biệt; không áp dụng máy móc kết luận cross-account |

**Lưu ý với IAM Identity Center:** Role do Identity Center cấp thường có ARN chứa `AWSReservedSSO_...`. Không lấy tên `TeamOperator` trong ví dụ làm ARN nguồn nếu thực tế principal của bạn là một SSO role khác. Cần kiểm tra role ARN thật, account ID và quyền trước khi thiết lập trust.

## 7. AWS CLI: sử dụng STS mà không chép temporary key thủ công

### 7.1. Kiểm tra profile nguồn

Cài AWS CLI v2 và chuẩn bị profile `source-team` đã có credentials hợp lệ để truy cập vai trò nguồn. Mở terminal:

~~~bash
aws --version
aws configure list --profile source-team

aws sts get-caller-identity \
  --profile source-team \
  --region ap-southeast-1 \
  --query '{Account:Account,Arn:Arn}' \
  --output json
~~~

Ví dụ minh họa nếu nguồn thực sự đang là role `TeamOperator`:

~~~json
{
  "Account": "111122223333",
  "Arn": "arn:aws:sts::111122223333:assumed-role/TeamOperator/source-session"
}
~~~

`GetCallerIdentity` cho biết **account** và **principal ARN** đang gọi. Giá trị `assumed-role/...` là ARN của role **session**, khác ARN IAM role gốc `arn:aws:iam::...:role/...` dùng trong trust policy.

### 7.2. Định nghĩa profile assume role

Trong `~/.aws/config` (Windows thường là `%UserProfile%\.aws\config`), tạo profile sau:

~~~ini
[profile inventory-read]
role_arn = arn:aws:iam::444455556666:role/InventoryViewer
source_profile = source-team
role_session_name = sts-training-006
region = ap-southeast-1
output = json
~~~

`source-team` phải là profile nguồn đã được cấu hình và được role đích tin cậy. AWS CLI sẽ sử dụng credentials nguồn để gọi STS, nhận credentials của role `InventoryViewer`, cache rồi tự lấy phiên mới khi cần và khi nguồn còn hợp lệ. **Không ghi các khóa tạm thời** vào file `~/.aws/credentials` thủ công.

Nếu `source-team` đang là role session thì đây là **role chaining**, phiên tiếp theo có tối đa 1 giờ.

### 7.3. Xác nhận account đích

~~~bash
aws sts get-caller-identity \
  --profile inventory-read \
  --region ap-southeast-1 \
  --query '{Account:Account,Arn:Arn}' \
  --output json

aws ec2 describe-vpcs \
  --profile inventory-read \
  --region ap-southeast-1 \
  --query 'Vpcs[].{Id:VpcId,Cidr:CidrBlock,Default:IsDefault}' \
  --output table
~~~

`Account` của lệnh đầu sẽ là **444455556666** nếu quyền và trust đúng. ARN có dạng `arn:aws:sts::444455556666:assumed-role/InventoryViewer/sts-training-006`. Lệnh thứ hai dùng role đích để đọc VPC; danh sách rỗng có thể là kết quả hợp lệ.

### 7.4. Xem metadata AssumeRole trực tiếp

Lệnh `aws sts assume-role` trả cả credentials, nên **không in nguyên phản hồi ra màn hình/ticket**. Có thể giới hạn output chỉ còn tên phiên và expiration:

~~~bash
aws sts assume-role \
  --role-arn arn:aws:iam::444455556666:role/InventoryViewer \
  --role-session-name sts-training-manual \
  --duration-seconds 900 \
  --profile source-team \
  --region ap-southeast-1 \
  --query '{RoleArn:AssumedRoleUser.Arn,ExpiresAt:Credentials.Expiration}' \
  --output json
~~~

Ví dụ:

~~~json
{
  "RoleArn": "arn:aws:sts::444455556666:assumed-role/InventoryViewer/sts-training-manual",
  "ExpiresAt": "2030-01-01T12:00:00Z"
}
~~~

Lệnh này **không tự chuyển** các lệnh tiếp theo trong terminal sang role đích. Cách bền vững là dùng profile `inventory-read` ở phần trước hoặc credentials provider trong SDK.

### 7.5. Trường hợp nguồn đăng nhập IAM Identity Center

Một người dùng trong tổ chức thường lấy credentials nguồn bằng SSO:

~~~bash
aws configure sso --profile company-sso
aws sso login --profile company-sso
aws sts get-caller-identity --profile company-sso
~~~

Tài khoản và role được chọn qua IAM Identity Center phải có quyền cần thiết; role đích phải trust **IAM role nguồn thực tế**. Nếu đúng và được quản trị viên chấp thuận, profile đích có thể sử dụng `source_profile = company-sso`. Nếu bị từ chối, không tạo IAM user và access key dài hạn để “vượt qua” quy trình.

## 8. Session policy, session tags và điều kiện trust

### 8.1. Session policy chỉ có thể giới hạn phạm vi

`AssumeRole` hỗ trợ **inline session policy** hoặc **managed session policy ARNs**. Thông thường effective permissions của role session là giao giữa quyền trong identity-based policies của role và session policy, còn phải tính các guardrail khác.

Ví dụ `InventoryViewer` vốn được đọc VPC, subnet và instance, nhưng phiên phục vụ một tác vụ chỉ muốn đọc VPC:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "OnlyDescribeVpcs",
      "Effect": "Allow",
      "Action": "ec2:DescribeVpcs",
      "Resource": "*"
    }
  ]
}
~~~

Session policy **không nâng quyền**. Tuy nhiên, không dùng câu “giao hai policy” làm công thức tuyệt đối cho mọi tình huống: resource-based policy cấp trực tiếp cho role session ARN có thể có cách xử lý giới hạn implicit deny khác nhau. Cần kiểm tra policy evaluation của thiết kế cụ thể.

### 8.2. RoleSessionName, SourceIdentity, session tags

- **`RoleSessionName`**: tên phiên hiển thị trong assumed-role ARN, hữu ích khi truy vết CloudTrail. Chọn tên phản ánh workload/job, tránh nhúng thông tin cá nhân nhạy cảm.
- **`SourceIdentity`**: cho phép ghi dấu danh tính gốc khi được cấu hình và cấp quyền, có thể tồn tại qua các bước role chaining để hỗ trợ kiểm toán.
- **Session tags**: cặp key/value (ví dụ `team=platform`, `env=dev`) có thể được dùng trong Attribute-Based Access Control (ABAC). Việc truyền tags phải được kiểm soát bằng trust/`sts:TagSession` và chính sách liên quan.

Ví dụ ABAC: một role chỉ đọc resource có tag `environment=dev` nếu principal/session tag `environment` cũng là `dev`. Không để caller tùy ý đặt tag `environment=prod` khi danh tính đó không được chấp thuận truy cập production.

### 8.3. MFA

Với IAM users/roles phù hợp, `AssumeRole` hoặc `GetSessionToken` có thể gắn trạng thái MFA và trust/permissions policy có thể kiểm tra điều kiện như `aws:MultiFactorAuthPresent`. Federation qua IAM Identity Center hay OIDC có quy trình MFA tại IdP; **không được mặc định** mọi phiên federated đều mang cùng ngữ cảnh MFA mà IAM có thể kiểm tra trực tiếp.

### 8.4. ExternalId và bài toán confused deputy

Nhà cung cấp SaaS được nhiều khách hàng cho phép assume role vào account của họ có thể bị lợi dụng để làm “người trung gian bị đánh lừa” (*confused deputy*). `sts:ExternalId` trong trust policy giảm nguy cơ này bằng cách yêu cầu ID do **nhà cung cấp dịch vụ sinh/kiểm soát riêng cho từng khách hàng** khi gọi `AssumeRole`.

`ExternalId` **không phải** mật khẩu thay thế xác thực và cũng không cấp quyền; vẫn cần trust/permission policy và kiểm soát nhà cung cấp. Với OIDC CI/CD, các điều kiện `sub`, `aud`, repository/branch/environment có vai trò tương tự ở lớp giới hạn đối tượng được trust.

## 9. STS và AWS Region

STS có **global endpoint** lịch sử `https://sts.amazonaws.com` và nhiều **regional endpoints** như `https://sts.ap-southeast-1.amazonaws.com`. AWS khuyến nghị chọn regional endpoint phù hợp để cải thiện độ trễ và khả năng cô lập sự cố.

~~~bash
aws sts get-caller-identity \
  --profile source-team \
  --region ap-southeast-1
~~~

Region mà STS **cấp credentials** không nhất thiết là Region bạn sẽ truy vấn EC2/VPC sau đó. Bộ credentials có thể sử dụng ở những Region hợp lệ theo chính sách IAM, trạng thái kích hoạt Region và loại token/endpoint. Token từ **regional STS endpoints** được hỗ trợ ở tất cả AWS Regions. Token từ global endpoint có quy tắc tương thích riêng với Region được kích hoạt thủ công; cần cấu hình phù hợp nếu hệ thống dùng opt-in Region.

**Ví dụ:** Một worker đặt tại Singapore nhận STS credentials qua regional endpoint, rồi truy vấn CloudWatch hoặc S3 ở một Region khác được doanh nghiệp cho phép. Lệnh gọi dịch vụ vẫn cần chỉ định đúng Region API tương ứng. IAM role tồn tại ở phạm vi account, trong khi EC2/VPC là dịch vụ theo Region.

## 10. Ứng dụng với EC2, ECS, Lambda, EKS và CI/CD

### 10.1. EC2 instance profile

Ứng dụng Spring Boot chạy trên EC2 cần đọc S3 và truy vấn Secrets Manager:

1. Tạo IAM role với trust principal EC2 và permission đúng S3 bucket/secret cần dùng.
2. Gắn role với EC2 qua **instance profile**.
3. AWS cung cấp temporary credentials qua **Instance Metadata Service (IMDS)**.
4. SDK dùng credentials provider để nhận và làm mới chúng; ứng dụng không phải lưu access key trong `application.yml`.

Nên dùng IMDSv2 và kiểm soát quyền truy cập metadata phù hợp. Việc cấp role quá rộng cho instance sẽ mở rộng ảnh hưởng của mọi tiến trình có thể truy cập credentials trên máy.

### 10.2. ECS task role so với task execution role

- **Task role**: quyền cho **mã ứng dụng** chạy trong container, ví dụ `dynamodb:GetItem` hay `s3:GetObject`.
- **Task execution role**: quyền cho ECS runtime/agent kéo ECR image, gửi logs hoặc bước khởi tạo khác.

Nếu container nhận `AccessDenied` khi truy vấn DynamoDB, cần rà soát **task role** chứ không chỉ task execution role.

### 10.3. Lambda execution role

AWS Lambda runtime cấp temporary credentials của **execution role** cho function. Ví dụ function nhận thông báo từ S3, ghi DynamoDB và phát log/metrics vào CloudWatch. Role chỉ nên có quyền trên các resource, actions cần thiết; không đặt access key lâu dài vào environment variables hoặc zip/JAR triển khai.

### 10.4. EKS workload identity

Trên Kubernetes/EKS, không nên cho mọi Pod dựa vào quyền lớn của EC2 node instance profile. Có thể sử dụng **IAM Roles for Service Accounts (IRSA)** dựa trên OIDC/web identity hoặc **EKS Pod Identity**, tùy kiến trúc cluster, để mỗi service account/workload được ánh xạ sang role thích hợp. SDK nhận credentials từ cơ chế tích hợp thay vì từ file keys trong image.

### 10.5. CI/CD ngoài AWS

Các workflow GitHub Actions hoặc nền tảng hỗ trợ OIDC có thể lấy temporary AWS credentials qua federation, không cần đặt IAM user long-term keys vào CI secrets. Trust cần gắn chặt repository, nhánh/environment và audience. Role triển khai nên có quyền trên dịch vụ, stack và Region cần thiết.

| Môi trường | Nguồn credentials ưu tiên | Tránh |
|---|---|---|
| Người dùng AWS CLI | IAM Identity Center và SSO profile | Chia sẻ IAM user key |
| Spring Boot trên EC2 | Instance role qua IMDS | Secret key trong mã nguồn/JAR |
| Container ECS | ECS task role | Lạm dụng task execution role |
| Lambda | Execution role | Khóa tĩnh trong function |
| EKS | IRSA hoặc EKS Pod Identity | Dùng chung node role cho mọi Pod |
| CI/CD bên ngoài AWS | OIDC federation vào role | AWS keys dài hạn trong CI |
| Đọc tập trung nhiều account | Cross-account AssumeRole | Phân phối credentials quyền cao cho từng account |

## 11. AWS SDK for Java 2.x và credentials provider chain

AWS SDK for Java 2.x có **DefaultCredentialsProvider**. Nếu tạo service client mà không truyền credentials provider tùy chỉnh, SDK tự tìm credentials theo chuỗi nguồn có thứ tự như system properties, environment variables, web identity, shared profiles (gồm SSO/assume role) và providers của container/instance.

Ví dụ kiểm tra danh tính STS bằng Java 2.x (cần dependency `software.amazon.awssdk:sts`, quản lý phiên bản qua AWS SDK BOM):

~~~java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sts.StsClient;
import software.amazon.awssdk.services.sts.model.GetCallerIdentityResponse;

public class AwsCaller {
    public static void main(String[] args) {
        try (StsClient sts = StsClient.builder()
                .region(Region.AP_SOUTHEAST_1)
                .build()) {

            GetCallerIdentityResponse result = sts.getCallerIdentity();
            System.out.println("Account: " + result.account());
            System.out.println("Principal: " + result.arn());
        }
    }
}
~~~

Mã này **không hardcode key** và không giả định có quyền administrator. Nếu chạy trên laptop với `AWS_PROFILE`/SSO profile đúng, SDK sẽ đọc profile tương ứng; trên EC2/ECS, SDK có thể lấy role credentials của runtime.

Khi ứng dụng cần quyền của **role đích khác** trong thời gian dài, nên sử dụng `StsAssumeRoleCredentialsProvider` để SDK cache và làm mới phiên. Nếu gọi `StsClient.assumeRole()` rồi gắn bộ key vào `StaticCredentialsProvider`, ứng dụng chạy lâu sẽ gặp `ExpiredToken` nếu không tự triển khai refresh. Đối với ứng dụng serverless/container đang có execution/task role đủ quyền, thường không cần assume lại **chính role đang có** chỉ để làm mới credentials.

**Lưu ý:** Một environment variable cũ như `AWS_ACCESS_KEY_ID` hoặc `AWS_SESSION_TOKEN` có thể được provider chain ưu tiên trước instance role. Khi kết quả sai identity, kiểm tra thứ tự provider và các biến môi trường thay vì sửa permissions policy ngay lập tức.

## 12. Truy vết, giám sát và bảo vệ session

### 12.1. AWS CloudTrail

CloudTrail có thể ghi sự kiện `AssumeRole` và những API calls thực hiện bằng assumed-role session theo phạm vi event logging. Metadata có thể bao gồm `userIdentity.type = AssumedRole`, role/session ARN, request action, Region và các thông tin source identity/session tags tùy cấu hình.

Ví dụ nhóm trực vận hành cần tìm ai đã đổi security group:

1. Xác định account, Region, thời điểm, API action như `AuthorizeSecurityGroupIngress`.
2. Tìm sự kiện CloudTrail và principal/session đã ký request.
3. Liên hệ session với role trust, caller gốc, source identity và quy trình triển khai.
4. Kiểm tra quyền IAM cùng thay đổi hạ tầng để xác định nguồn và tác động.

Không ghi lại `SecretAccessKey`/`SessionToken` trong log nghiệp vụ để truy vết: ARN/session metadata là điểm bắt đầu phù hợp hơn.

### 12.2. Bảo vệ temporary credentials

- Cấp quyền tối thiểu và trust đúng caller/IdP; tách role dev, staging và production.
- Khuyến khích MFA/federation cho con người; workload dùng role của môi trường.
- Tránh lộ secrets qua logs, CLI output, shell history, repository, container image hoặc hệ thống ticket.
- Có runbook xử lý sự cố trong thời gian token còn hiệu lực, không mặc định “đợi hết hạn là đủ”.
- Dùng session name/source identity/session tags theo chính sách để truy vết.
- Theo dõi dấu hiệu role assume bất thường và các hoạt động thay đổi tài nguyên nhạy cảm.

### 12.3. Chi phí và quy trình thay đổi

STS cấp quyền, không khóa hóa đơn. Một session tồn tại 15 phút vẫn có thể tạo một EC2 instance chạy liên tục nhiều ngày nếu role được cấp `ec2:RunInstances`. Vì vậy, cần phối hợp least privilege, IAM/SCP, AWS Budgets/cảnh báo chi phí, quota, tagging và vòng đời dọn dẹp tài nguyên. Bài thực hành này chỉ dùng lệnh đọc, không yêu cầu tạo tài nguyên tính phí.

## 13. Sự cố STS thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
|---|---|---|
| `AccessDenied` khi `AssumeRole` | Caller thiếu `sts:AssumeRole`; role trust sai principal; điều kiện MFA/ExternalId/tags không thỏa | Kiểm tra `get-caller-identity` nguồn, trust, IAM policy và các guardrail |
| `AccessDenied` khi `DescribeVpcs` | Assume đã thành công nhưng permissions policy đích không đủ hoặc có deny | Kiểm tra caller role đích và effective permissions |
| `ExpiredToken` | Temporary credentials đã hết hạn | Đăng nhập lại SSO nếu cần, để CLI/SDK provider xin phiên mới |
| `InvalidClientTokenId` hoặc invalid token | Thiếu/sai session token, lẫn nguồn credentials, token không tương thích endpoint/Region theo cấu hình | Kiểm tra provider và `aws configure list`; không in secrets |
| Request session 2 giờ thất bại dù role tối đa 12 giờ | Role chaining chỉ tối đa 1 giờ | Dùng `--duration-seconds 3600` hoặc thiết kế lại luồng |
| `Unable to locate credentials` | CLI/SDK không tìm thấy nguồn hợp lệ | Kiểm tra profile, SSO login, IMDS/container provider |
| SSO đăng nhập thành công nhưng role đích không assume được | Role nguồn IAM Identity Center khác ARN được trust hoặc thiếu quyền | Kiểm tra role nguồn thật và cập nhật cấu hình thông qua admin |
| Lệnh API trả dữ liệu khác Console | Sai account/role/Region hoặc bộ lọc Console | So sánh `get-caller-identity`, `--region` và filter |
| Static credentials hoạt động rồi lỗi sau một lúc | Không có cơ chế refresh | Dùng role profile hoặc SDK STS credentials provider |
| OIDC federation thất bại | Issuer/audience/subject hoặc trust condition không khớp | Kiểm tra OIDC provider, token claims và trust policy |

### 13.1. Bộ lệnh kiểm tra không làm thay đổi tài nguyên

~~~bash
aws --version
aws configure list-profiles

# Kiểm tra nguồn cấu hình cho profile
aws configure list --profile source-team

# Principal trước khi assume role
aws sts get-caller-identity \
  --profile source-team \
  --region ap-southeast-1 \
  --output json

# Principal sau khi assume role
aws sts get-caller-identity \
  --profile inventory-read \
  --region ap-southeast-1 \
  --output json
~~~

`aws configure list` có thể cho biết loại/nguồn cấu hình, nhưng vẫn phải rà soát output trước khi chia sẻ. `aws sts assume-role` **mặc định in cả secret và session token**, nên cần dùng `--query` chỉ chọn metadata trong demo. `--debug` có thể làm lộ thông tin request nhạy cảm; chỉ dùng trong môi trường kiểm soát.

## 14. Bài thực hành tự kiểm tra

**Điều kiện:** Người học có hai profile nguồn/đích đã được quản trị viên cấp. Nếu chưa có môi trường, dùng JSON mô phỏng và phân tích quyền theo ví dụ ở phần 6; không cần tạo IAM role, EC2 hay S3 bucket.

### Bước A – xác định identity nguồn

~~~bash
aws sts get-caller-identity \
  --profile source-team \
  --region ap-southeast-1 \
  --query '{Account:Account,Arn:Arn}' \
  --output json
~~~

Ghi **account ID** và role/session ARN. Chỉ ra phần nào thể hiện IAM role gốc và phần nào thể hiện tên phiên.

### Bước B – xác định identity đích

~~~bash
aws sts get-caller-identity \
  --profile inventory-read \
  --region ap-southeast-1 \
  --query '{Account:Account,Arn:Arn}' \
  --output json
~~~

Nếu tài khoản thay đổi, mô tả điều gì đã xảy ra với principal sau `AssumeRole`. Nếu lỗi `AccessDenied`, xác định đây là lỗi ở bước xin role, không phải lỗi đọc VPC.

### Bước C – chỉ đọc metadata VPC

~~~bash
aws ec2 describe-vpcs \
  --profile inventory-read \
  --region ap-southeast-1 \
  --query 'Vpcs[].{VpcId:VpcId,CIDR:CidrBlock,Default:IsDefault}' \
  --output table
~~~

Dữ liệu trống là hợp lệ nếu account/Region không có VPC. Nếu lệnh này bị từ chối nhưng bước B thành công, kiểm tra quyền `ec2:DescribeVpcs` của role đích.

### Bước D – phân tích quyền và thời hạn

Tự giải thích các tình huống:

1. Caller có `sts:AssumeRole` nhưng trust policy role đích không tin caller: lỗi ở đâu?
2. Role trust caller nhưng permissions policy không cho `s3:GetObject`: sau khi assume có đọc được object không?
3. Role đích cho `MaxSessionDuration = 12 giờ`, nhưng nguồn đã là role session; xin 2 giờ có hợp lệ không?
4. Developer copy output JSON đầy đủ của `AssumeRole` lên issue: những trường nào cần coi là bí mật và cần xử lý sự cố như thế nào?
5. Một role chỉ tồn tại 15 phút nhưng có thể chạy `ec2:RunInstances`: vì sao tài nguyên tạo ra vẫn gây chi phí về sau?

### Bước E – vận dụng vào ứng dụng Java

Thiết kế một ứng dụng Spring Boot chạy trong ECS cần đọc một DynamoDB table và phát log CloudWatch. Chỉ ra role nào phải cấp `dynamodb:GetItem` cho **mã ứng dụng**, role nào phục vụ ECS runtime, cách SDK lấy credentials và vì sao không cần lưu access key dài hạn vào config.

## 15. Tự đánh giá kiến thức

Bạn đã sẵn sàng chuyển sang các bài AWS networking/compute/storage/serverless nếu có thể:

- Diễn giải đầy đủ luồng **caller → trust → STS session → resource authorization**.
- Đọc đúng account/ARN từ `GetCallerIdentity` và biết lệnh này không tạo credentials.
- Phân biệt IAM role tồn tại lâu dài với **một phiên giả định role** có expiration.
- Nêu được role chaining tối đa **1 giờ**, cùng cách CLI/SDK tự làm mới credentials.
- Giải thích vì sao session policy chỉ thu hẹp quyền và cần chú ý resource-based policies.
- Chọn đúng role/provider cho EC2, ECS, Lambda, EKS và OIDC CI/CD.
- Nhận biết rủi ro rò rỉ temporary credentials trong suốt thời gian hiệu lực.
- Kết nối quyền IAM/STS với CloudTrail, giảm rủi ro bảo mật và kiểm soát chi phí.

## Tài liệu chính thức

1. [Temporary security credentials in IAM](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_temp.html) — Nền tảng và lợi ích của credentials tạm thời.
2. [Request temporary security credentials](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_temp_request.html) — Các thao tác STS.
3. [Compare AWS STS credentials](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_sts-comparison.html) — So sánh API, thời hạn và hạn chế.
4. [AWS STS API: AssumeRole](https://docs.aws.amazon.com/STS/latest/APIReference/API_AssumeRole.html) — Tham số, thời hạn, role chaining và session policies.
5. [AWS CLI: Using an IAM role](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-role.html) — `role_arn`, `source_profile`, tự cache/refresh.
6. [IAM: Switch to a role with AWS CLI](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_use_switch-role-cli.html) — Cross-account IAM role.
7. [IAM policies and permissions](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies.html) — Cách đánh giá effective permissions.
8. [AWS STS and Regions](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_temp_enable-regions.html) — Regional endpoints và token compatibility.
9. [AWS SDK for Java 2.x: Default credentials provider chain](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials-chain.html) — Tự động nhận credentials.
10. [AWS SDK for Java 2.x: Credential caching](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credential-caching.html) — Cache/làm mới credentials.
11. [IAM: The confused deputy problem](https://docs.aws.amazon.com/IAM/latest/UserGuide/confused-deputy.html) — `ExternalId` trong cross-account trust.

> **Ghi nhớ:** STS cung cấp thông tin xác thực **có thời hạn**. Hạ tầng an toàn còn cần **trust rõ ràng, quyền tối thiểu, tự làm mới credentials, kiểm toán CloudTrail và kiểm soát thao tác thay đổi tài nguyên/chi phí**.

