# Chẩn đoán lỗi IAM, STS và credential hết hạn

Ứng dụng gọi AWS API phải xác định được **principal nào đang gửi request**, chứng minh request được ký bằng credential hợp lệ và có đủ quyền thực hiện hành động trên tài nguyên đích. Một lỗi xác thực (authentication) thường liên quan đến access key, secret key, session token, thời hạn credential hoặc chữ ký SigV4. Một lỗi phân quyền (authorization) xảy ra khi AWS nhận diện được principal nhưng chính sách không cho phép hành động đó.

AWS Identity and Access Management (IAM) quản lý danh tính và quyền truy cập. AWS Security Token Service (AWS STS) phát hành temporary security credentials để ứng dụng, người dùng liên kết danh tính hoặc workload có thể truy cập AWS trong một khoảng thời gian giới hạn. Khi credential hết hạn, request được ký bằng bộ credential cũ không còn hợp lệ. Khi credential còn hiệu lực nhưng thiếu quyền, việc cấp một bộ credential mới thường không giải quyết được lỗi `AccessDenied`.

Bài học này trình bày cách phân biệt hai nhóm lỗi, xác định credential provider thực tế, kiểm tra IAM policy và role trust, xử lý STS session hết hạn, cấu hình tự làm mới credential trong AWS CLI và AWS SDK for Java 2.x, đồng thời xây dựng quy trình điều tra có thể áp dụng cho EC2, ECS, EKS, Lambda và môi trường CI/CD.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt authentication, authorization, IAM principal và STS session.
- Nhận diện cấu trúc temporary security credentials và trường `Expiration`.
- Giải thích cách AWS đánh giá identity policy, resource policy, trust policy, permissions boundary, session policy, SCP, RCP và VPC endpoint policy.
- Kiểm tra chính xác principal mà AWS CLI hoặc ứng dụng đang sử dụng.
- Chẩn đoán các lỗi `ExpiredToken`, `InvalidClientTokenId`, `AccessDenied`, `SignatureDoesNotMatch` và lỗi credential provider chain.
- Cấu hình IAM Identity Center, AssumeRole, web identity, instance profile và container credentials.
- Dùng credential provider có khả năng cache và refresh trong AWS SDK for Java 2.x.
- Điều tra request thất bại bằng CloudTrail, IAM Policy Simulator và authorization details khi có hỗ trợ.
- Thiết kế quy trình credential an toàn, có khả năng tự phục hồi và dễ kiểm toán.

## 1. Authentication và authorization trong một AWS request

Một request AWS thường đi qua hai giai đoạn logic:

1. **Authentication:** AWS xác định request được ký bởi credential nào, credential có hợp lệ không, session token có đầy đủ không, chữ ký có đúng không và thời điểm ký có nằm trong cửa sổ chấp nhận không.
2. **Authorization:** sau khi xác định principal, AWS đánh giá các policy áp dụng cho action, resource và request context. Nếu không có quyền cho phép hoặc có explicit deny, request bị từ chối.

```mermaid
flowchart TD
    A[Ứng dụng / AWS CLI gửi request] --> B[Credential provider lấy credential]
    B --> C[Ký request bằng SigV4]
    C --> D{Authentication hợp lệ?}
    D -->|Không| E[Invalid token / ExpiredToken / Signature error]
    D -->|Có| F[Nhận diện IAM principal]
    F --> G[Đánh giá policy và request context]
    G --> H{Authorization cho phép?}
    H -->|Không| I[AccessDenied / UnauthorizedOperation]
    H -->|Có| J[Thực thi API]
```

Ví dụ, nếu AWS trả `ExpiredToken`, request chưa vượt qua bước xác thực bằng temporary credential. Nếu trả `AccessDenied` với thông tin `not authorized to perform: s3:GetObject`, credential có thể hoàn toàn hợp lệ nhưng principal chưa có quyền đọc object hoặc bị một policy khác giới hạn.

Hai lỗi có thể xuất hiện liên tiếp. Một ứng dụng trước tiên có thể dùng credential đã hết hạn; sau khi refresh thành công, request tiếp theo lại gặp `AccessDenied` vì role mới không có quyền trên bucket. Hãy kiểm tra từng lớp thay vì coi mọi lỗi truy cập là cùng một nguyên nhân.

## 2. IAM principal và temporary security credentials

### 2.1 Principal là ai?

Principal là danh tính thực hiện request. Trong AWS, principal thường là:

- IAM user hoặc IAM role.
- Assumed-role session được tạo qua AWS STS.
- Federated user hoặc web identity session.
- AWS service principal khi một dịch vụ gọi dịch vụ khác.
- Root principal của AWS account.

Trong hệ thống hiện đại, workload thường nên dùng IAM role và temporary credentials thay vì access key dài hạn của IAM user. Ví dụ EC2 dùng instance profile, ECS dùng task role, EKS dùng EKS Pod Identity hoặc IAM Roles for Service Accounts (IRSA), Lambda dùng execution role và pipeline CI/CD có thể dùng OIDC federation.

### 2.2 Cấu trúc credential

Một bộ temporary security credentials do STS cấp có bốn trường chính:

| Trường | Ý nghĩa |
|---|---|
| `AccessKeyId` | Định danh access key của session |
| `SecretAccessKey` | Bí mật dùng để tạo chữ ký request |
| `SessionToken` | Token bổ sung chứng minh credential thuộc temporary session |
| `Expiration` | Thời điểm credential hết hiệu lực, thường biểu diễn theo UTC |

Ví dụ cấu trúc response đã lược bỏ giá trị nhạy cảm:

```json
{
  "Credentials": {
    "AccessKeyId": "ASIAEXAMPLEACCESSKEY",
    "SecretAccessKey": "REDACTED_SECRET_VALUE",
    "SessionToken": "REDACTED_SESSION_TOKEN",
    "Expiration": "2026-11-20T10:00:00Z"
  }
}
```

Access key ID, secret key và session token phải được sử dụng như một bộ. Khi dùng temporary credentials, thiếu `SessionToken` hoặc ghép session token của một session với access key/secret key của session khác có thể khiến AWS trả `InvalidClientTokenId` hoặc lỗi xác thực tương tự.

Không ghi các giá trị này vào log, ticket, source control, chat hoặc ảnh chụp màn hình. Khi chia sẻ log điều tra, chỉ giữ principal ARN, thời điểm hết hạn, tên profile và phần credential đã được che.

### 2.3 Temporary credential khác long-term access key

Long-term access key của IAM user không có trường `Expiration` do STS cấp. Access key có trạng thái Active/Inactive và có thể bị xoay vòng hoặc xóa. Temporary credentials được cấp động, có thời hạn và không thể dùng lại sau khi hết hạn.

Do đó, khi gặp lỗi hết hạn:

- Nếu ứng dụng dùng STS/role/SSO/web identity, hãy làm mới session hoặc khôi phục credential source.
- Nếu ứng dụng dùng IAM user access key dài hạn, kiểm tra key có bị inactive, xóa, thay đổi hoặc cấu hình sai; không xử lý nó như STS session.
- Không tạo access key IAM user mới chỉ để né việc refresh temporary credentials.

## 3. AWS STS và thời hạn session

AWS STS cung cấp các API tạo temporary credentials cho nhiều kịch bản.

| STS API | Trường hợp sử dụng |
|---|---|
| `AssumeRole` | Người dùng hoặc workload đã xác thực nhận quyền của IAM role, thường dùng cho cross-account hoặc tách quyền |
| `AssumeRoleWithWebIdentity` | Nhận quyền từ OIDC token, ví dụ workload EKS hoặc CI/CD federation |
| `AssumeRoleWithSAML` | Liên kết danh tính qua SAML 2.0 identity provider |
| `GetSessionToken` | Tạo session tạm thời cho IAM user, thường dùng khi cần MFA |
| `GetFederationToken` | Tạo federated user session qua custom identity broker |

### 3.1 Thời hạn AssumeRole

Với `AssumeRole`, `DurationSeconds` có thể từ 900 giây (15 phút) đến giá trị Maximum session duration được cấu hình cho role. Role có thể được cấu hình tối đa 12 giờ. Mức mặc định của role thường là một giờ nếu quản trị viên không thay đổi.

**Role chaining** là dùng temporary credentials của một role session để assume một role khác. Khi chaining, session mới bị giới hạn tối đa một giờ, kể cả khi role đích được cấu hình maximum session duration dài hơn. Nếu yêu cầu 12 giờ trong một chuỗi role, STS sẽ từ chối.

Ví dụ: một người dùng đăng nhập IAM Identity Center, assume role `Developer`, rồi từ session đó assume role `ProductionReadOnly`. Session thứ hai là role chaining và không thể kéo dài quá một giờ. Thiết kế chuỗi role ngắn, rõ ràng và để provider tự refresh khi còn đủ quyền.

### 3.2 Credential hết hạn không tự gia hạn

STS không kéo dài một credential đã hết hạn. Ứng dụng phải yêu cầu một session mới bằng credential source vẫn còn hiệu lực. Nếu source là IAM Identity Center, cần session đăng nhập còn hợp lệ; nếu source là instance profile, metadata service phải truy cập được; nếu source là OIDC, token file phải được cấp mới và trust relationship phải cho phép assume role.

Một provider có thể refresh trước khi hết hạn, nhưng điều đó chỉ hoạt động khi:

- Provider biết cách lấy lại credential từ source.
- Source credential hoặc token vẫn có thể được làm mới.
- Role trust policy và caller permission vẫn cho phép tạo session mới.
- Ứng dụng giữ provider sống đủ lâu và không thay thế nó bằng credential tĩnh.

### 3.3 STS Region

STS có global endpoint và regional endpoints. Có thể gọi STS tại Region gần workload để giảm độ trễ và phù hợp yêu cầu vận hành theo Region. Temporary credentials được phát hành bởi STS có thể được dùng để gọi các AWS service trên phạm vi toàn cầu, tùy chính sách và khả năng của service.

Khi gặp lỗi chỉ ở một Region, kiểm tra Region của service request, Region của STS endpoint, trạng thái Region trong account và cấu hình endpoint. Không nhầm Region dùng để ký request với Region đã tạo ra credential.

## 4. IAM policy evaluation và nguồn gây AccessDenied

IAM mặc định từ chối request nếu không có quyền phù hợp. Một `Allow` có thể cho phép request, nhưng một explicit `Deny` áp dụng cho request sẽ thắng mọi `Allow` khác.

### 4.1 Các loại policy cần kiểm tra

| Policy | Câu hỏi chẩn đoán | Vai trò |
|---|---|---|
| Identity-based policy | User/role có được phép gọi action trên resource không? | Cấp quyền cho principal |
| Resource-based policy | Bucket, key, queue, secret hoặc resource có cho principal truy cập không? | Cấp quyền trực tiếp trên resource |
| Role trust policy | Principal nguồn có được phép assume role đích không? | Kiểm soát ai được nhận role |
| Permissions boundary | Boundary có giới hạn quyền tối đa thấp hơn identity policy không? | Giới hạn quyền của IAM user/role |
| Session policy | Session có bị giới hạn khi STS tạo credential không? | Thu hẹp quyền của session |
| Service control policy (SCP) | AWS Organizations có giới hạn action của principal không? | Giới hạn quyền tối đa trong organization |
| Resource control policy (RCP) | Organization có giới hạn quyền trên resource không? | Giới hạn quyền tối đa đối với resource |
| VPC endpoint policy | Request đi qua endpoint có bị endpoint policy chặn không? | Kiểm soát request qua VPC endpoint |

Các policy được đánh giá tùy theo loại request và service. Không phải request nào cũng có đủ mọi loại policy. Hãy xem error context, CloudTrail và authorization details nếu có để xác định policy thực sự tham gia đánh giá.

### 4.2 Explicit deny và implicit deny

- **Explicit deny:** có statement `Effect: Deny` khớp action, resource và condition của request. Một explicit deny áp dụng sẽ chặn request dù có policy khác cho phép.
- **Implicit deny:** không có explicit deny, nhưng không có `Allow` phù hợp trong các policy cần thiết. Ví dụ role chỉ được `s3:GetObject` trên prefix `reports/`, nhưng ứng dụng đọc `archive/`.

Thông báo lỗi mới có thể chỉ ra policy type hoặc ARN của policy gây explicit deny, chẳng hạn SCP, RCP, permissions boundary, session policy hoặc identity policy. Không phải mọi service đều trả cùng định dạng và nếu có nhiều policy cùng từ chối, message có thể chỉ hiển thị một phần ngữ cảnh.

### 4.3 Cross-account access

Khi truy cập resource ở account khác, cần phân biệt hai mô hình:

1. **Assume role vào account đích:** principal nguồn cần được phép gọi `sts:AssumeRole`, trust policy của role đích phải tin principal đó và role đích phải có quyền cần thiết sau khi assume. Với cross-account, cả policy phía caller lẫn trust policy phía role đích đều phải cho phép. Trong cùng account, có thể cấp quyền bằng identity policy khi trust policy tin account, hoặc khai báo principal cụ thể trực tiếp trong trust policy; nếu principal có permissions boundary thì boundary vẫn phải cho phép `sts:AssumeRole`.
2. **Truy cập trực tiếp resource cross-account:** policy ở phía principal và resource policy ở account sở hữu resource phải phối hợp cấp quyền theo cơ chế của service. Ví dụ S3 bucket policy có thể cho role ở account khác đọc object, trong khi identity policy của role cũng cần cho phép action.

Nếu dùng AssumeRole, kiểm tra cả hai phía: policy của caller và trust policy của role đích. Một role có policy `s3:GetObject` không có nghĩa mọi người đều được assume role đó.

### 4.4 Trust policy và `iam:PassRole` là hai việc khác nhau

`sts:AssumeRole` cho phép principal yêu cầu một role session. `iam:PassRole` cho phép người cấu hình truyền một IAM role cho AWS service sử dụng, ví dụ gắn execution role vào Lambda hoặc task role vào ECS task. `iam:PassRole` không tạo temporary credential cho người gọi và không thay thế trust policy.

Khi nhận lỗi `not authorized to perform: iam:PassRole`, hãy kiểm tra quyền PassRole của người tạo tài nguyên, ARN role được truyền và service principal trong trust policy. Khi nhận lỗi `sts:AssumeRole`, tập trung vào quyền của caller, trust relationship và các điều kiện của trust policy.

## 5. Credential provider chain: ứng dụng lấy credential ở đâu?

AWS CLI và AWS SDK tìm credential từ nhiều nguồn. Nguồn được chọn đầu tiên có thể khác với điều mà lập trình viên mong đợi. Một biến môi trường cũ có thể khiến ứng dụng tiếp tục dùng credential sai dù profile đã được sửa.

### 5.1 AWS CLI

AWS CLI có thể lấy credential từ:

- Command-line/profile selection và environment variables.
- IAM role được cấu hình trong profile qua `source_profile` hoặc `credential_source`.
- Web identity token.
- IAM Identity Center (SSO).
- Shared credentials/config files.
- `credential_process`.
- ECS container credential endpoint.
- EC2 instance metadata service.

Thứ tự và ưu tiên cấu hình phụ thuộc provider. Đặc biệt, `AWS_ACCESS_KEY_ID` và `AWS_SECRET_ACCESS_KEY` trong environment có thể ghi đè credential trong profile được chọn bằng `AWS_PROFILE` hoặc `--profile`. Vì vậy, chỉ định `--profile dev` không đảm bảo CLI đang dùng access key nằm trong profile đó.

Các biến môi trường thường gặp:

| Biến | Mục đích |
|---|---|
| `AWS_PROFILE` | Chọn named profile mặc định |
| `AWS_ACCESS_KEY_ID` | Access key ID |
| `AWS_SECRET_ACCESS_KEY` | Secret access key |
| `AWS_SESSION_TOKEN` | Session token của temporary credentials |
| `AWS_REGION` / `AWS_DEFAULT_REGION` | Region mặc định cho request |
| `AWS_SHARED_CREDENTIALS_FILE` | Đường dẫn credentials file |
| `AWS_CONFIG_FILE` | Đường dẫn config file |
| `AWS_EC2_METADATA_DISABLED` | Tắt truy cập EC2 metadata provider khi đặt `true` |

`aws configure list` cho biết profile, credential source và Region CLI đang chọn. Giá trị access key/secret được che một phần; lệnh này hữu ích để tìm nguồn credential mà không cần in bí mật ra terminal.

### 5.2 AWS SDK for Java 2.x

`DefaultCredentialsProvider` của AWS SDK for Java 2.x tìm credential theo thứ tự tổng quát sau:

1. Java system properties (`aws.accessKeyId`, `aws.secretAccessKey`, `aws.sessionToken`).
2. Environment variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`).
3. Web identity token và role ARN.
4. Shared `credentials` và `config` files, bao gồm profile, IAM Identity Center, AssumeRole và `credential_process`.
5. ECS container credentials.
6. EC2 instance profile credentials qua metadata service.

Provider chain dừng tại nguồn đầu tiên tìm được cấu hình hợp lệ. Vì vậy, Java system property hoặc environment variables cũ có thể che mất profile SSO, web identity hoặc instance role mà bạn định dùng.

Không giả định thứ tự provider của mọi ngôn ngữ SDK giống hệt nhau. Hãy dùng tài liệu của SDK đang chạy và kiểm tra credential source thực tế trong đúng tiến trình/container.

### 5.3 Static provider và refreshable provider

Static credentials provider chỉ giữ giá trị được truyền vào. Nếu giá trị đó là temporary credential, provider không tự gọi STS để lấy session mới. Khi credential hết hạn, client tiếp tục ký request bằng giá trị cũ và nhận lỗi.

Các provider chuẩn cho STS, web identity, container và instance profile có cơ chế cache/refresh. Khi ứng dụng dùng provider chuẩn và không tự copy credential thành chuỗi cố định, SDK có thể lấy credential mới trước khi session hiện tại hết hạn.

## 6. Kiểm tra danh tính thực tế bằng AWS CLI

Trước khi thay đổi policy, hãy xác nhận CLI đang dùng principal nào.

```bash
aws --version
aws configure list
aws sts get-caller-identity
```

Với named profile:

```bash
aws configure list --profile dev
aws sts get-caller-identity --profile dev
```

`get-caller-identity` trả về `Account`, `Arn` và `UserId`. ARN giúp nhận biết request đang dùng IAM user, assumed role hay federated session. Ví dụ:

```json
{
  "UserId": "AROAXXXXXXXXXXXXX:build-session",
  "Account": "111122223333",
  "Arn": "arn:aws:sts::111122223333:assumed-role/DeploymentRole/build-session"
}
```

API `GetCallerIdentity` không cần cấp quyền IAM riêng để trả về danh tính đang gọi. Dù vậy, kết quả chỉ xác nhận principal; nó không chứng minh principal có quyền với service/resource khác.

### 6.1 Kiểm tra environment variables mà không in secret

Trên PowerShell, có thể chỉ liệt kê tên biến:

```powershell
Get-ChildItem Env:AWS_* | Select-Object -ExpandProperty Name
```

Trên Bash:

```bash
env | cut -d= -f1 | grep '^AWS_'
```

Nếu tìm thấy biến credential cũ, hãy xác minh nguồn cấp rồi xóa khỏi đúng shell/session hoặc cấu hình CI/CD. Không in toàn bộ environment vào log vì có thể làm lộ secret.

### 6.2 Làm sạch environment tạm thời

PowerShell:

```powershell
Remove-Item Env:AWS_ACCESS_KEY_ID -ErrorAction SilentlyContinue
Remove-Item Env:AWS_SECRET_ACCESS_KEY -ErrorAction SilentlyContinue
Remove-Item Env:AWS_SESSION_TOKEN -ErrorAction SilentlyContinue
$env:AWS_PROFILE = 'dev'
aws sts get-caller-identity
```

Bash:

```bash
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN
export AWS_PROFILE=dev
aws sts get-caller-identity
```

Các lệnh trên chỉ thay đổi environment của shell hiện tại. Nếu biến được khai báo trong profile shell, IDE, service unit hoặc CI runner, cần sửa tại nơi khởi tạo tiến trình để lỗi không quay lại.

## 7. Cấu hình IAM Identity Center và AssumeRole trong AWS CLI

### 7.1 IAM Identity Center

Với tổ chức dùng AWS IAM Identity Center, cấu hình profile SSO:

```bash
aws configure sso
```

Sau khi hoàn tất cấu hình, đăng nhập và kiểm tra danh tính:

```bash
aws sso login --profile dev
aws sts get-caller-identity --profile dev
```

CLI lưu cache đăng nhập và tự lấy temporary credentials từ permission set khi cần. Nếu IAM Identity Center session đã hết hạn, cần đăng nhập lại bằng `aws sso login`. Việc AWS role credentials được tự làm mới không đồng nghĩa token đăng nhập SSO gốc có thể tồn tại vô hạn.

### 7.2 Profile assume role

Có thể cấu hình một profile dùng source profile để assume role ở account khác:

```ini
[profile dev]
region = ap-southeast-1
output = json

[profile prod-readonly]
role_arn = arn:aws:iam::444455556666:role/ProductionReadOnly
source_profile = dev
role_session_name = analyst-session
region = ap-southeast-1
duration_seconds = 3600
```

Sau khi đăng nhập profile nguồn nếu cần, chạy:

```bash
aws sso login --profile dev
aws sts get-caller-identity --profile prod-readonly
aws s3 ls s3://company-prod-reports/ --profile prod-readonly
```

CLI tự gọi STS để assume role và cache temporary credentials. Khi credential session hết hạn, CLI có thể yêu cầu lại credential từ source profile và assume role lần nữa. Nếu source profile là SSO và SSO session hết hạn, phải đăng nhập SSO lại.

### 7.3 Dùng instance role làm source

Trên EC2, có thể cấu hình role đích dùng credential từ instance profile:

```ini
[profile audit-reader]
role_arn = arn:aws:iam::444455556666:role/AuditReadOnly
credential_source = Ec2InstanceMetadata
region = ap-southeast-1
```

`credential_source` có các giá trị phổ biến `Environment`, `Ec2InstanceMetadata` và `EcsContainer`. Không đặt đồng thời `source_profile` và `credential_source` trong cùng profile. Với workload đã có instance/task role phù hợp, thường không cần assume role thêm một lần.

## 8. Tự làm mới credential trong AWS SDK for Java 2.x

### 8.1 Dùng default credentials provider

Đối với ứng dụng chạy trên máy phát triển, EC2, ECS, EKS hoặc Lambda, cách đơn giản là để SDK sử dụng default provider chain. Không truyền access key/secret key trực tiếp vào source code.

```java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

public class S3AccessExample {
    public static void main(String[] args) {
        try (S3Client s3 = S3Client.builder()
                .region(Region.AP_SOUTHEAST_1)
                .build()) {
            s3.listBuckets().buckets().forEach(
                    bucket -> System.out.println(bucket.name()));
        }
    }
}
```

SDK tự dùng `DefaultCredentialsProvider` nếu client không chỉ định provider khác. Trong môi trường AWS, hãy gắn role phù hợp cho workload và để provider lấy credential từ runtime.

### 8.2 AssumeRole bằng refreshable provider

Khi ứng dụng cần assume một role khác, dùng `StsAssumeRoleCredentialsProvider`. Provider cache session và lấy session mới trước khi credential hiện tại hết hạn khi source credential còn hợp lệ.

```java
import java.time.Duration;

import software.amazon.awssdk.auth.credentials.StsAssumeRoleCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.sts.StsClient;
import software.amazon.awssdk.services.sts.model.AssumeRoleRequest;

public class AssumeRoleS3Example {
    public static void main(String[] args) {
        StsClient sts = StsClient.builder()
                .region(Region.AP_SOUTHEAST_1)
                .build();

        StsAssumeRoleCredentialsProvider credentials =
                StsAssumeRoleCredentialsProvider.builder()
                        .stsClient(sts)
                        .refreshRequest(AssumeRoleRequest.builder()
                                .roleArn("arn:aws:iam::444455556666:role/ReportReader")
                                .roleSessionName("report-service")
                                .durationSeconds(3600)
                                .build())
                        .prefetchTime(Duration.ofMinutes(10))
                        .staleTime(Duration.ofMinutes(2))
                        .asyncCredentialUpdateEnabled(true)
                        .build();

        try (S3Client s3 = S3Client.builder()
                .region(Region.AP_SOUTHEAST_1)
                .credentialsProvider(credentials)
                .build()) {
            s3.listObjectsV2(request -> request
                    .bucket("company-prod-reports")
                    .maxKeys(10));
        } finally {
            credentials.close();
            sts.close();
        }
    }
}
```

Ví dụ cần dependency `software.amazon.awssdk:sts` và `software.amazon.awssdk:s3` cùng phiên bản AWS SDK for Java 2.x. `prefetchTime` cho phép provider bắt đầu lấy session mới trước khi hết hạn; `staleTime` xác định khi nào credential được coi là cũ. Bật asynchronous refresh có thể tránh để request đầu tiên sau thời gian chờ phải đồng bộ chờ STS, nhưng vẫn cần xử lý lỗi khi source credential không còn hợp lệ.

### 8.3 Những lỗi thường gặp khi viết Java

- Tạo `StaticCredentialsProvider` từ STS response rồi giữ client chạy lâu dài: provider không tự gọi STS để refresh.
- Tự cache `AwsSessionCredentials` trong singleton mà không lưu expiration và không có refresh logic.
- Tạo `StsAssumeRoleCredentialsProvider` nhưng source credentials đã hết hạn hoặc thiếu quyền `sts:AssumeRole`.
- Đặt environment variables credential tĩnh trong container khiến chúng được chọn trước web identity hoặc container provider.
- Tạo một STS client hoặc credentials provider mới cho từng request, làm tăng latency và số lần gọi STS.
- Không đóng provider/client khi ứng dụng shutdown, gây rò rỉ thread hoặc connection.

Nên dùng một credentials provider dùng chung trong vòng đời ứng dụng, để AWS SDK quản lý cache và refresh. Khi cần kiểm soát profile cụ thể, có thể dùng `ProfileCredentialsProvider`; khi chạy trong EKS/ECS/EC2, ưu tiên provider chuẩn của runtime.

## 9. Credential source theo môi trường chạy

| Môi trường | Credential source nên dùng | Điểm cần kiểm tra khi lỗi |
|---|---|---|
| Máy lập trình viên | IAM Identity Center hoặc named profile | SSO login, `AWS_PROFILE`, environment variables và profile path |
| Amazon EC2 | Instance profile / instance role | Role gắn vào instance, IMDSv2, route và `AWS_EC2_METADATA_DISABLED` |
| Amazon ECS | Task role | Task definition, task role ARN, container credential endpoint và network |
| Amazon EKS với IRSA | OIDC web identity token + IAM role | ServiceAccount annotation, OIDC provider, trust policy `aud`/`sub`, token file |
| Amazon EKS Pod Identity | EKS Pod Identity association và agent | Association namespace/service account, agent và role trust |
| AWS Lambda | Execution role | Execution role ARN, quyền policy và credential provider trong runtime |
| CI/CD bên ngoài AWS | OIDC federation hoặc credential broker | OIDC issuer, audience, subject claim, trust policy và thời hạn token |
| CI/CD chạy trên AWS | Instance/task role hoặc role chaining | Source role, `sts:AssumeRole`, trust policy và session duration |

### 9.1 EC2 Instance Metadata Service

EC2 instance profile cung cấp temporary credentials qua Instance Metadata Service (IMDS). Nên dùng IMDSv2 và giới hạn truy cập metadata endpoint theo thiết kế bảo mật của instance. Nếu ứng dụng không lấy được credential, kiểm tra:

- IAM role đã được gắn vào instance profile chưa.
- Instance có truy cập được metadata endpoint không.
- IMDSv2 token flow có bị firewall, proxy hoặc cấu hình host chặn không.
- Hop limit có phù hợp với ứng dụng trong container hay không.
- `AWS_EC2_METADATA_DISABLED=true` có vô tình tắt provider không.

Không cần copy credential từ metadata endpoint rồi ghi vào file. SDK và CLI có provider tự lấy và refresh credential.

### 9.2 ECS task role

Trong ECS, phân biệt task role và task execution role. Task role cấp quyền cho code chạy bên trong container. Task execution role cho ECS agent thực hiện các thao tác như pull image hoặc gửi log. Nếu ứng dụng trong container gọi S3 nhưng chỉ cấp quyền vào execution role, ứng dụng vẫn có thể nhận `AccessDenied`.

SDK/CLI lấy credential từ container credential endpoint do ECS agent cung cấp. Nếu endpoint hoặc authorization token file không truy cập được, kiểm tra task metadata environment variables, task definition và agent.

### 9.3 EKS IRSA và Pod Identity

IRSA dùng OIDC token của Kubernetes ServiceAccount để gọi `AssumeRoleWithWebIdentity`. Trust policy của role cần khớp OIDC provider, `aud` và `sub` (namespace/service account). Nếu token file không được mount hoặc service account không gắn đúng role, SDK có thể rơi sang provider tiếp theo hoặc báo không tìm được credential.

EKS Pod Identity dùng association và agent để cấp credential cho pod. Hãy xác nhận association trỏ đúng cluster, namespace, service account và role. Tránh để access key tĩnh trong environment variables của pod vì chúng có thể che mất credential từ IRSA/Pod Identity.

## 10. Bảng chẩn đoán lỗi credential và IAM

| Error / triệu chứng | Nguyên nhân thường gặp | Hướng xử lý đầu tiên |
|---|---|---|
| `ExpiredToken` / `ExpiredTokenException` | STS credential đã hết hạn hoặc ứng dụng giữ session cũ | Làm mới source session; kiểm tra provider có refresh hay đang dùng static credentials |
| `InvalidClientTokenId` | Access key/session token không hợp lệ, thiếu token hoặc ghép sai bộ credential | Chạy `aws configure list`; kiểm tra profile và `AWS_SESSION_TOKEN` mà không in secret |
| `InvalidAccessKeyId` | Access key không tồn tại, đã xóa hoặc cấu hình nhầm | Xác định credential source, key status và profile thực tế |
| `UnrecognizedClientException` | Credential hoặc token không được AWS nhận diện | Kiểm tra bộ key/token, profile, source credential và signing request |
| `AccessDenied` / `AccessDeniedException` | Principal hợp lệ nhưng policy không cho phép hoặc có explicit deny | Xác định action/resource/principal rồi rà soát mọi policy liên quan |
| `not authorized to perform: sts:AssumeRole` | Caller thiếu quyền assume hoặc trust policy không cho phép | Kiểm tra cả identity policy nguồn và trust policy role đích |
| `not authorized to perform: iam:PassRole` | Người tạo resource không được truyền role cho service | Kiểm tra `iam:PassRole` trên đúng role ARN và trust relationship |
| `SignatureDoesNotMatch` | Secret sai, session token không khớp, canonical request sai hoặc clock skew | Kiểm tra credential source, Region/service signing và đồng bộ thời gian |
| `RequestExpired` | Timestamp request nằm ngoài khoảng AWS chấp nhận | Kiểm tra NTP/system clock, proxy và thời điểm ký |
| `InvalidIdentityToken` | OIDC token hết hạn, issuer/audience không khớp hoặc provider/trust sai | Kiểm tra token file, OIDC provider và condition `aud`/`sub` |
| `SdkClientException: Unable to load credentials from any of the providers in the chain` | SDK không tìm thấy credential source hợp lệ | Kiểm tra provider chain, profile path, SSO, container endpoint hoặc IMDS |
| Hoạt động được ở local nhưng lỗi trong container | Local profile có quyền khác task/pod role; environment variables che provider | Xác nhận principal bằng `get-caller-identity` trong đúng container |
| Chạy được một lúc rồi lỗi | Session hết hạn, source token hết hạn hoặc refresh provider không hoạt động | Kiểm tra expiration, provider type, refresh logs và source session |

Không sửa policy chỉ vì thấy `AccessDenied`. Trước hết phải xác nhận request đang chạy bằng principal nào và action/resource nào bị từ chối.

## 11. Quy trình điều tra ExpiredToken và InvalidClientTokenId

Thực hiện theo thứ tự sau để khoanh vùng nhanh.

### Bước 1: Xác nhận credential source

```bash
aws configure list
aws sts get-caller-identity
```

Nếu lệnh thứ hai báo expired/invalid token, vấn đề nằm ở credential source hoặc signing/authentication trước khi cần điều tra quyền S3, EC2 hay service đích.

### Bước 2: Kiểm tra profile và environment

- Xác nhận `AWS_PROFILE` hoặc `--profile` đúng.
- Kiểm tra `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` có bị khai báo cũ không.
- Xác nhận credentials/config file đúng user, container hoặc service account.
- Kiểm tra `AWS_SHARED_CREDENTIALS_FILE` và `AWS_CONFIG_FILE` nếu dùng đường dẫn tùy chỉnh.
- Xác nhận không có profile tĩnh ghi đè SSO hoặc role provider.

### Bước 3: Refresh theo loại source

| Source | Cách khôi phục |
|---|---|
| IAM Identity Center | Chạy `aws sso login --profile <profile>` |
| CLI AssumeRole profile | Refresh source profile, sau đó CLI tự assume role lại |
| EC2 instance profile | Kiểm tra metadata endpoint, role attachment và IAM instance profile |
| ECS task role | Kiểm tra task role và container credential endpoint |
| EKS IRSA | Kiểm tra projected token file, OIDC trust và service account |
| EKS Pod Identity | Kiểm tra association, agent và role trust |
| Java STS provider | Dùng refreshable provider; xác nhận STS source credential vẫn hoạt động |
| IAM user access key dài hạn | Kiểm tra key status, secret, profile và quy trình rotation; đây không phải STS expiry |

### Bước 4: Xác nhận lại principal

Sau khi refresh, chạy lại `aws sts get-caller-identity` trong đúng shell, container hoặc runtime. Nếu ARN thay đổi, hãy xác nhận principal mới đúng với thiết kế và có policy cần thiết.

### Bước 5: Kiểm tra request service đích

Chỉ sau khi `get-caller-identity` thành công mới thử request tới service đích. Nếu request đó trả `AccessDenied`, chuyển sang quy trình phân tích authorization ở phần tiếp theo.

## 12. Quy trình điều tra AccessDenied

### Bước 1: Đọc đầy đủ error context

Ghi lại các trường:

- Principal ARN trong thông báo lỗi.
- Action bị từ chối, ví dụ `s3:GetObject` hoặc `kms:Decrypt`.
- Resource ARN.
- Policy type được nêu trong câu `because ...` hoặc `with an explicit deny ...`.
- Policy ARN nếu AWS cung cấp.
- Region, thời điểm, request ID và source IP/network path nếu có.

Ví dụ:

```text
User: arn:aws:sts::111122223333:assumed-role/ReportReader/job-42
is not authorized to perform: s3:GetObject
on resource: arn:aws:s3:::company-prod-reports/finance/q4.csv
because no identity-based policy allows the s3:GetObject action
```

Thông báo này chỉ rõ assumed role session và action cần kiểm tra. Hãy xem policy gắn với IAM role `ReportReader`, policy boundary, session policy và các policy khác có thể áp dụng.

### Bước 2: Kiểm tra role và trust relationship

Với role assumption, kiểm tra:

1. Principal nguồn có được phép gọi `sts:AssumeRole` theo mô hình trust đang dùng không? Với cross-account, caller policy phải cho phép; trong cùng account, trust policy có thể cấp trực tiếp cho principal cụ thể.
2. Trust policy của role đích có cho principal/service/OIDC provider đó assume không?
3. Condition có yêu cầu MFA, ExternalId, source IP, principal tag, `aws:SourceArn`, `aws:SourceAccount`, `aud` hoặc `sub` không?
4. Role có bị SCP/RCP hoặc explicit deny khác giới hạn không?
5. `DurationSeconds` có vượt maximum session duration hoặc giới hạn role chaining một giờ không?

Ví dụ trust policy tối giản cho một role được một IAM role khác assume:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::111122223333:role/BuildRole"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

Ví dụ chỉ minh họa trust relationship. Trong production, giới hạn principal cụ thể, thêm condition phù hợp và kiểm tra policy phía `BuildRole` cho phép `sts:AssumeRole` trên role đích.

### Bước 3: Rà soát policy hiệu lực

Kiểm tra identity policy, resource policy, permissions boundary, session policy, SCP, RCP và VPC endpoint policy theo request. Đừng chỉ đọc một policy đính kèm role rồi kết luận.

Các condition thường gây lỗi:

- `aws:RequestedRegion` không khớp Region request.
- `aws:SourceIp` hoặc `aws:VpcSourceIp` không khớp đường mạng.
- `aws:MultiFactorAuthPresent` yêu cầu MFA nhưng session không có MFA context.
- `aws:PrincipalTag` hoặc `aws:ResourceTag` không khớp.
- `aws:RequestTag` hoặc `aws:TagKeys` thiếu tag khi tạo resource.
- `kms:EncryptionContext` không khớp encryption context của request.
- `sts:ExternalId`, `aws:SourceArn` hoặc `aws:SourceAccount` không khớp trust policy.

### Bước 4: Dùng IAM Policy Simulator

IAM Policy Simulator có thể kiểm tra kết quả cho action/resource và policy context được hỗ trợ mà không gửi request thay đổi resource thật.

Ví dụ CLI:

```bash
aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::111122223333:role/ReportReader \
  --action-names s3:GetObject \
  --resource-arns arn:aws:s3:::company-prod-reports/finance/q4.csv
```

Xem `EvalDecision`, `MatchedStatements` và context evaluation. Kết quả simulator có thể khác môi trường thực tế vì simulator không tự tái tạo mọi context key, resource policy, service behavior hoặc điều kiện runtime. Dùng nó để thu hẹp nguyên nhân rồi xác nhận bằng request thực tế có kiểm soát.

### Bước 5: Dùng authorization ID nếu AWS cung cấp

Một số AccessDenied response được hỗ trợ có thể kèm authorization ID và liên kết đến phần giải thích policy evaluation. Thông tin này cho biết từng check như SCP, RCP, VPC endpoint, resource, principal, permissions boundary và session đã được đánh giá ra sao tại thời điểm request thất bại.

Nếu có authorization ID, mở phần authorization details trong IAM console hoặc dùng lệnh IAM Toolbox tại cùng Region (nếu account/CLI đã có tính năng này):

```bash
aws iam-toolbox get-request-authorization-details \
  --region ap-southeast-1 \
  --authorization-id AUTHORIZATION_ID_FROM_ERROR
```

Authorization ID không được bảo đảm xuất hiện trong mọi lỗi hoặc mọi service. Nếu không có ID, tiếp tục dùng error context, CloudTrail và Policy Simulator.

### Bước 6: Kiểm tra CloudTrail

CloudTrail giúp xác định principal, session issuer, action, resource, thời điểm và request context của nhiều API management event. Tìm event liên quan như `AssumeRole`, `AssumeRoleWithWebIdentity` hoặc API service bị từ chối. Đối chiếu:

- `userIdentity.type`, `userIdentity.arn` và `sessionContext.sessionIssuer.arn`.
- `accessKeyId` để liên hệ request với credential/session (không phải secret key).
- `eventSource`, `eventName`, `awsRegion`, `sourceIPAddress` và `errorCode`.
- `requestParameters` và resource ARN nếu được ghi nhận.

CloudTrail không lưu secret access key hay session token. Một số data event cần bật data event logging riêng; không phải mọi loại request bị từ chối đều xuất hiện trong Event history. Hãy kiểm tra loại event và cấu hình trail trước khi kết luận rằng không có log nghĩa là request chưa xảy ra.

## 13. Clock skew và chữ ký SigV4

AWS Signature Version 4 đưa timestamp, credential scope và nội dung request vào quá trình ký. Nếu đồng hồ hệ điều hành lệch đáng kể so với AWS, request có thể bị từ chối dù access key đúng.

Các nguyên nhân thường gặp:

- Máy ảo resume từ sleep/hibernate nhưng chưa đồng bộ lại thời gian.
- Container hoặc host có đồng hồ sai.
- NTP service bị tắt hoặc không truy cập được time source.
- Proxy/gateway sửa đổi request hoặc header.
- Ứng dụng ký bằng Region/service scope không đúng endpoint.
- Secret key bị biến đổi bởi script hoặc shell quoting.
- Temporary credential được dùng mà không gửi session token.

Kiểm tra thời gian:

```bash
date -u
timedatectl status
```

Trên Windows PowerShell:

```powershell
Get-Date -AsUTC
w32tm /query /status
```

Nếu đồng hồ lệch, đồng bộ qua NTP hoặc dịch vụ time synchronization được tổ chức quản lý. Không sửa timestamp bằng cách hardcode một giá trị trong ứng dụng. Với `SignatureDoesNotMatch`, ngoài clock skew hãy kiểm tra credential source, signing Region, service endpoint, canonical headers và proxy.

## 14. Xoay vòng IAM access key và credential hygiene

IAM user access key dài hạn không có thời điểm STS expiration. Nếu tổ chức còn dùng loại key này, cần có quy trình rotation và kiểm tra mức độ sử dụng.

Các lệnh kiểm tra metadata key:

```bash
aws iam list-access-keys --user-name legacy-app-user
aws iam get-access-key-last-used --access-key-id AKIAEXAMPLEACCESSKEY
```

Credential report cung cấp trạng thái MFA, key active, thời điểm rotation và lần sử dụng gần nhất cho các IAM user trong account. Thông tin last-used có độ trễ và không phải telemetry thời gian thực.

Quy trình rotation an toàn:

1. Xác định ứng dụng, owner và workload đang dùng key cũ.
2. Tạo key mới trong giới hạn IAM user cho phép.
3. Cập nhật secret store hoặc hệ thống phân phối credential.
4. Kiểm tra request bằng key mới và xác nhận principal/permission đúng.
5. Chuyển workload hoàn toàn sang key mới.
6. Deactivate key cũ, theo dõi lỗi trong khoảng thời gian xác nhận.
7. Xóa key cũ sau khi chắc chắn không còn workload phụ thuộc.

Với kiến trúc mới, ưu tiên thay long-term keys bằng IAM role, IAM Identity Center, web identity hoặc workload identity. Không commit key vào Git, Docker image, AMI, Terraform state không được bảo vệ hoặc file cấu hình chia sẻ.

## 15. Bảo mật khi điều tra lỗi

Debugging có thể làm lộ credential nếu log quá chi tiết. AWS CLI `--debug` hữu ích để xem request flow, endpoint, retry và response, nhưng output có thể chứa header, request metadata hoặc thông tin nhạy cảm.

Nguyên tắc khi điều tra:

- Không gửi `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`, presigned URL hoặc raw authorization header vào ticket/chat.
- Che account ID, role ARN hoặc resource name nếu chính sách bảo mật yêu cầu.
- Chỉ bật debug trong thời gian ngắn và giới hạn quyền truy cập log.
- Không bật log HTTP wire-level trong production nếu chưa đánh giá rủi ro.
- Xóa log tạm chứa dữ liệu nhạy cảm theo chính sách retention.
- Nếu phát hiện secret bị lộ, vô hiệu hóa/rotate credential và điều tra phạm vi sử dụng ngay.
- Không nới rộng policy thành `Action: "*"`, `Resource: "*"` để thử xem lỗi có hết không.

## 16. Case study: ứng dụng Java trên ECS bị ExpiredToken sau vài giờ

Một dịch vụ Java chạy trên ECS gọi S3 để đọc báo cáo. Ứng dụng hoạt động ngay sau khi deploy, nhưng sau vài giờ bắt đầu nhận `ExpiredToken`.

### Bước 1: Xác nhận principal trong container

Chạy `aws sts get-caller-identity` trong cùng task/container (nếu CLI có sẵn) hoặc log ARN principal an toàn từ ứng dụng. Xác nhận request dùng task role, không phải IAM user access key.

### Bước 2: Kiểm tra provider chain

Kiểm tra environment variables. Nếu container có `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` và `AWS_SESSION_TOKEN` được inject từ secret cũ, chúng có thể được chọn trước container credential provider. Xóa cơ chế inject credential tĩnh và để SDK dùng task role.

### Bước 3: Kiểm tra Java client

Nếu ứng dụng khởi tạo `StaticCredentialsProvider` từ một lần gọi `AssumeRole`, client sẽ giữ credential đó cho đến khi process restart. Thay bằng `DefaultCredentialsProvider` để SDK lấy credential từ ECS task role hoặc dùng `StsAssumeRoleCredentialsProvider` nếu thực sự cần assume role thêm.

### Bước 4: Kiểm tra IAM role

Đảm bảo task definition gắn đúng task role, role có quyền `s3:GetObject` trên prefix cần đọc và bucket policy không chặn. Nếu role assume một role khác, kiểm tra caller permission và trust policy.

### Bước 5: Kiểm thử sau sửa

Chạy task đủ lâu để vượt qua chu kỳ credential ban đầu, theo dõi refresh log và thực hiện các thao tác S3 định kỳ. Xác nhận request vẫn thành công sau nhiều lần refresh. Nếu lỗi đổi thành `AccessDenied`, credential đã được làm mới nhưng role/session policy chưa có quyền trên resource.

## 17. Checklist vận hành và phòng ngừa

- [ ] Xác định principal bằng `aws sts get-caller-identity` trong đúng runtime.
- [ ] Kiểm tra credential source bằng `aws configure list` và environment variables.
- [ ] Dùng IAM role hoặc federation thay vì long-term IAM user keys khi có thể.
- [ ] Temporary credentials luôn được sử dụng cùng session token.
- [ ] Session duration phù hợp workload; role chaining không vượt quá một giờ.
- [ ] AWS SDK dùng provider có khả năng refresh, không tự giữ STS credentials trong static provider.
- [ ] EC2/ECS/EKS/Lambda được gắn đúng workload role.
- [ ] IAM role trust policy chỉ tin đúng principal/service/OIDC identity.
- [ ] Identity policy, resource policy, boundary, session policy, SCP/RCP và endpoint policy được rà soát khi có AccessDenied.
- [ ] Kiểm tra Region, system clock, SigV4 và proxy khi có lỗi chữ ký.
- [ ] CloudTrail logging và retention đủ để điều tra request quan trọng.
- [ ] Policy Simulator được dùng như công cụ hỗ trợ, sau đó xác nhận bằng request thực tế.
- [ ] Secret không xuất hiện trong log, source control hoặc debug output chia sẻ.
- [ ] IAM access key cũ có owner, rotation plan và theo dõi last-used.
- [ ] Có cảnh báo và runbook cho `ExpiredToken`, `AccessDenied` và lỗi credential provider chain.

## 18. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| `ExpiredToken` nghĩa là IAM policy thiếu quyền | Đây là lỗi temporary credential hết hạn; trước tiên phải refresh credential source |
| Cấp thêm `AdministratorAccess` sẽ sửa được credential hết hạn | Policy không làm cho session token cũ sống lại |
| Access key ID và secret key là đủ cho STS session | Temporary credentials còn bắt buộc có session token |
| `AWS_PROFILE` luôn ghi đè environment credentials | Environment credentials có thể được ưu tiên hơn profile |
| `GetCallerIdentity` thành công nghĩa là có quyền S3 | Nó chỉ xác nhận principal đang gọi |
| Role có `s3:GetObject` nghĩa là ai cũng assume được role | Caller permission và role trust policy vẫn phải cho phép assume |
| `iam:PassRole` và `sts:AssumeRole` giống nhau | Một quyền truyền role cho service; quyền còn lại tạo role session |
| Tăng role session duration giải quyết mọi lỗi hết hạn | Source session có thể hết hạn trước; role chaining bị giới hạn một giờ |
| AWS SDK tự refresh mọi loại credential | Static/environment/system property providers không tự lấy lại credential từ STS |
| AccessDenied luôn do identity policy | Resource policy, boundary, session policy, SCP/RCP, trust hoặc VPC endpoint cũng có thể gây deny |
| Policy Simulator bảo đảm request production thành công | Simulator không tái hiện mọi context và service behavior |
| `SignatureDoesNotMatch` luôn là secret key sai | Clock skew, Region/service scope, proxy hoặc canonical request cũng có thể gây lỗi |

## Tài liệu tham khảo

- [Troubleshoot access denied error messages](https://docs.aws.amazon.com/IAM/latest/UserGuide/troubleshoot_access-denied.html)
- [Troubleshoot access denied using authorization ID](https://docs.aws.amazon.com/IAM/latest/UserGuide/troubleshoot_access-denied-authorization-id.html)
- [IAM policy evaluation logic](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic.html)
- [Access management for AWS resources](https://docs.aws.amazon.com/IAM/latest/UserGuide/access.html)
- [Temporary security credentials in IAM](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_temp.html)
- [Request temporary security credentials](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_temp_request.html)
- [Compare AWS STS credentials](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_sts-comparison.html)
- [Troubleshoot IAM roles](https://docs.aws.amazon.com/IAM/latest/UserGuide/troubleshoot_roles.html)
- [AssumeRole API reference](https://docs.aws.amazon.com/STS/latest/APIReference/API_AssumeRole.html)
- [IAM roles and role chaining](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles.html)
- [AWS CLI troubleshooting](https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-troubleshooting.html)
- [AWS CLI configuration and credentials precedence](https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-configure.html)
- [Using IAM roles in the AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-role.html)
- [IAM Identity Center authentication with the AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sso.html)
- [Credential and configuration files](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-files.html)
- [Default credentials provider chain for Java 2.x](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials-chain.html)
- [Credentials caching in AWS SDK for Java 2.x](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credential-caching.html)
- [AWS SDK for Java 2.x credentials providers](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials-providers.html)
- [IAM policy simulator](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_testing-policies.html)
- [Generate IAM credential reports](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_getting-report.html)
- [Get the last use of an access key](https://docs.aws.amazon.com/IAM/latest/UserGuide/access-keys-admin-managed.html)
- [AWS Signature Version 4](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_sigv.html)
- [AWS STS regional endpoints](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_temp_enable-regions.html)
