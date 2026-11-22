# SSO, AssumeRole và tự động làm mới credential

## Mục tiêu học tập

Sau bài học, người học có thể:

- Phân biệt **authentication** (xác thực danh tính) và **authorization** (quyền được phép thực hiện hành động).
- Giải thích cách **AWS IAM Identity Center (SSO)** cấp quyền vào AWS account thông qua **permission set** và IAM role được provision.
- Cấu hình **SSO token provider profile** trong `~/.aws/config`, đăng nhập bằng AWS CLI và sử dụng profile từ AWS SDK for Java 2.x.
- Phân biệt SSO access token, AWS role credentials, STS session credentials, long-term access keys và credential provider.
- Hiểu **STS AssumeRole**, source credentials, trust policy, identity policy, cross-account access và role chaining.
- Thiết kế profile dùng `source_profile`, `role_arn`, `credential_source`, `external_id`, `role_session_name` và giới hạn hỗ trợ riêng của Java SDK 2.x.
- Dùng `ProfileCredentialsProvider`, `DefaultCredentialsProvider` và `StsAssumeRoleCredentialsProvider` trong Java; cấu hình refresh/cache/prefetch.
- Giải thích vì sao không nên lấy credentials một lần rồi giữ trong `StaticCredentialsProvider`, tự ghi access key/secret/session token hoặc tự refresh bằng timer.
- Tách credentials theo môi trường local, EC2, ECS, EKS và CI/CD; chọn federation/role phù hợp thay vì IAM user keys.
- Chẩn đoán `Unable to load credentials`, `ExpiredToken`, `InvalidGrant`, `AccessDenied`, `IDPRejectedClaim`, `RegionDisabled` và lỗi trust/permission.
- Kiểm tra danh tính bằng STS `GetCallerIdentity`, audit session qua CloudTrail, bảo vệ SSO cache và đóng providers/clients đúng vòng đời.

**Bối cảnh module:** Bài thuộc chương **AWS SDK cho Java** trong `CLOUD_PROVIDERS_AWS`. Người học khám phá AWS từ Region/AZ, IAM, VPC đến compute, storage, database, integration và serverless. Ứng dụng Java cần lấy credentials an toàn, refresh trước khi hết hạn, giới hạn quyền và duy trì audit trail trên máy cá nhân hoặc AWS runtime.

> **Phạm vi:** Ví dụ sử dụng **AWS SDK for Java 2.x**, AWS CLI v2, IAM Identity Center và AWS STS. Tên profile, account ID, role ARN, URL, Region và bucket là dữ liệu giả lập. Bài không yêu cầu tạo IAM user access keys. API, giới hạn phiên và cấu hình có thể khác theo phiên bản SDK/CLI, permission set và tổ chức.

## 1. Bài toán: vì sao ứng dụng chạy được một giờ rồi đột nhiên báo ExpiredToken?

Một ứng dụng Java gọi S3 để tải báo cáo. Lúc khởi động, developer lấy credentials tạm thời từ AWS access portal rồi đưa ba giá trị vào cấu hình:

- Access key ID;
- Secret access key;
- Session token.

Ứng dụng chạy được, nhưng một lúc sau bắt đầu lỗi `ExpiredToken`. Developer khởi động lại ứng dụng để lấy credentials mới. Khi triển khai production, vấn đề trở thành outage định kỳ.

~~~mermaid
flowchart LR
    Dev[Developer / CI] -->|SSO login| Portal[IAM Identity Center]
    Portal -->|Temporary role credentials| App[Java application]
    App --> S3[(Amazon S3)]
    App -->|Credentials hết hạn| Fail[ExpiredToken]
    Fail --> Restart[Restart thủ công]
    Restart --> Portal
~~~

Nguyên nhân không nằm ở S3. Ứng dụng đã **giữ một bộ credentials tạm thời như thể chúng là vĩnh viễn**.

Giải pháp đúng là để **credential provider** quản lý vòng đời:

1. Xác định nguồn credentials (SSO, profile, EC2 instance role, ECS task role, EKS web identity hoặc STS AssumeRole).
2. Provider lấy credentials tạm thời và cache trong bộ nhớ theo cơ chế SDK.
3. Provider kiểm tra thời điểm hết hạn và refresh trước khi cần.
4. Service client dùng provider cho mỗi request, không giữ access key/secret cứng trong business code.
5. Nếu phiên đăng nhập gốc đã hết hạn hoặc bị revoke, ứng dụng báo lỗi xác thực để người dùng/operator đăng nhập hoặc cấp lại quyền.

~~~mermaid
sequenceDiagram
    participant App as Java application
    participant P as Credentials provider
    participant SSO as IAM Identity Center / STS
    participant S3 as Amazon S3
    App->>P: resolveCredentials()
    P->>SSO: Get/refresh temporary credentials
    SSO-->>P: Credentials + expiration
    P-->>App: Current cached credentials
    App->>S3: Signed API request
    Note over P: Prefetch / refresh before expiry
    App->>P: resolveCredentials() on later request
    P-->>App: Refreshed credentials
    App->>S3: Signed request with current credentials
~~~

**Điểm cốt lõi:** `AwsCredentialsProvider` là nguồn credentials sống theo vòng đời ứng dụng. `AwsCredentials` chỉ là một bộ giá trị tại một thời điểm.

## 2. Authentication, authorization và credentials

Ba khái niệm cần tách biệt:

| Khái niệm | Câu hỏi | Ví dụ AWS |
| --- | --- | --- |
| **Authentication** | Bạn là ai? | Người dùng đăng nhập IAM Identity Center; workload nhận IAM role |
| **Authorization** | Bạn được làm gì? | IAM policies cho phép `s3:GetObject` trên một bucket |
| **Credentials** | Request được chứng minh danh tính bằng gì? | Access key ID + secret access key + session token |

AWS SDK ký request bằng **AWS Signature Version 4 (SigV4)**. Với temporary credentials, session token cũng phải được gửi trong quá trình ký/xác thực. Không thể chỉ copy access key ID và secret access key rồi bỏ session token.

### Long-term credentials và temporary credentials

| Loại | Thành phần | Vòng đời | Nên dùng |
| --- | --- | --- | --- |
| IAM user access key | Access key ID + secret | Dài hạn cho tới khi rotate/revoke | Chỉ trong ngoại lệ legacy được kiểm soát |
| STS credentials | Access key ID + secret + session token | Có expiration | Workload/user federation |
| IAM Identity Center credentials | SSO token và role credentials được cấp qua portal | Theo phiên Identity Center và role session | Developer, operator, human access |
| EC2 instance profile | Credentials từ IAM role qua IMDS | SDK tự refresh | Workload EC2 |
| ECS task role | Credentials từ container credential endpoint | SDK tự refresh | Workload ECS |
| EKS web identity | OIDC token đổi qua STS AssumeRoleWithWebIdentity | Token/role session có thời hạn | Pod cần IAM permissions |

**Không đặt access keys dài hạn trong source code, Git, Docker image, AMI, user data, build logs hoặc file cấu hình được commit.** Temporary credentials giảm thời gian một credential bị lộ có thể được sử dụng; least privilege vẫn là yêu cầu riêng.

## 3. IAM Identity Center: SSO cấp quyền qua permission set như thế nào?

**AWS IAM Identity Center** là dịch vụ quản lý truy cập tập trung cho người dùng và nhóm. Administrator gán một **permission set** cho user/group trên một hoặc nhiều AWS accounts.

Khi user đăng nhập AWS access portal và chọn account + permission set:

1. Identity Center xác thực user theo identity source/MFA policy của tổ chức.
2. Permission set xác định permissions, session duration và cấu hình liên quan.
3. AWS provision IAM role tương ứng trong account đích (thường có tên dạng `AWSReservedSSO_...`).
4. Portal cấp short-term credentials cho role session.
5. CLI/SDK dùng credentials này để ký request tới AWS services.

~~~mermaid
flowchart TB
    User[User / Group] --> IdP[Identity source + MFA]
    IdP --> Center[IAM Identity Center]
    Admin[Administrator] --> Assign[Assign permission set to account]
    Assign --> Center
    Center --> Portal[AWS access portal]
    Portal --> Account[Target AWS account]
    Account --> Role[IAM role provisioned from permission set]
    Role --> Policies[Identity-based permissions]
    Role --> Temp[Temporary role credentials]
    Temp --> SDK[AWS SDK for Java]
    SDK --> Service[S3 / DynamoDB / other services]
~~~

### Permission set không phải một credentials file

Permission set là **định nghĩa quyền và phiên truy cập**. User không nhận access key vĩnh viễn trong portal. Khi login, hệ thống cấp temporary role credentials theo quyền được gán.

### IAM Identity Center Region và application Region có thể khác

- `sso_region`: Region nơi IAM Identity Center instance được cấu hình.
- `region` trong profile hoặc service client: Region của AWS service mà ứng dụng gọi.

Ví dụ Identity Center ở `us-east-1`, còn S3 bucket nằm ở `ap-southeast-1`. Hai giá trị có thể khác nhau. Đặt nhầm `sso_region` theo Region của bucket là lỗi cấu hình phổ biến.

## 4. SSO token và AWS role credentials là hai lớp khác nhau

Với cấu hình SSO token provider mới, có hai lớp credential:

1. **IAM Identity Center access token**: chứng minh phiên đăng nhập với Identity Center; được cache trên máy theo SSO session.
2. **AWS role credentials**: access key ID, secret access key và session token của role/permission set trong AWS account; được cấp khi SDK/CLI yêu cầu.

~~~mermaid
sequenceDiagram
    participant User as Developer
    participant CLI as AWS CLI
    participant Cache as SSO token cache
    participant Portal as IAM Identity Center
    participant Role as AWS account role
    participant SDK as Java SDK
    User->>CLI: aws sso login
    CLI->>Portal: Browser/device authorization
    Portal-->>CLI: Access token + refresh token
    CLI->>Cache: Store SSO token cache
    SDK->>Cache: Read valid SSO token
    SDK->>Portal: Request account role credentials
    Portal->>Role: Resolve permission set role
    Role-->>SDK: Temporary AWS role credentials
    SDK->>SDK: Cache credentials until refresh window
~~~

**Access token không phải session token của SigV4.** Khi gọi dịch vụ AWS thông thường như S3/DynamoDB, SDK dùng AWS role credentials; access token SSO là lớp xác thực để nhận những credentials đó.

### Khi nào phải đăng nhập lại?

Với cấu hình SSO token provider mới:

- AWS role credentials được refresh khi gần hết hạn nếu SSO session còn hợp lệ.
- SSO access token được refresh bằng refresh token trong thời gian phiên được phép.
- Khi refresh token/extended session hết hạn, bị revoke hoặc cần xác thực lại theo policy, user phải đăng nhập lại bằng `aws sso login`.
- `aws sso logout` xóa các SSO cached credentials của user; ứng dụng đang dựa vào phiên đó sẽ không thể tiếp tục lấy credentials mới.

**Tự động refresh không có nghĩa đăng nhập vĩnh viễn hoặc bỏ qua MFA/reauthentication policy.**

## 5. Shared AWS config: cấu hình SSO token provider hiện đại

AWS CLI và SDK đọc cấu hình chung, thường ở:

- Linux/macOS: `~/.aws/config` và `~/.aws/credentials`.
- Windows: `%USERPROFILE%\.aws\config` và `%USERPROFILE%\.aws\credentials`.
- Có thể tùy biến đường dẫn bằng các biến môi trường hỗ trợ.

Cấu hình SSO token provider mới tách phần phiên SSO vào section `[sso-session ...]` và gắn profile với session đó.

~~~ini
[profile dev-sso]
sso_session = company-dev
sso_account_id = 111122223333
sso_role_name = DeveloperAccess
region = ap-southeast-1
output = json

[sso-session company-dev]
sso_start_url = https://example.awsapps.com/start
sso_region = us-east-1
sso_registration_scopes = sso:account:access
~~~

Ý nghĩa:

| Key | Mục đích |
| --- | --- |
| `sso_session` | Tên section SSO session mà profile sử dụng |
| `sso_start_url` | AWS access portal URL hoặc issuer URL phù hợp |
| `sso_region` | Region chứa IAM Identity Center instance |
| `sso_account_id` | AWS account đích |
| `sso_role_name` | Tên permission set/role được provision trong account |
| `sso_registration_scopes` | OAuth scopes; `sso:account:access` cho account/role access |
| `region` | Region mặc định cho AWS service calls |
| `output` | Output format của CLI, không ảnh hưởng authorization |

Có thể dùng cùng một `[sso-session company-dev]` cho nhiều profiles nếu cùng phiên Identity Center nhưng chọn account/permission set khác nhau.

### Tại sao cần `sso_registration_scopes`?

`sso:account:access` là scope cơ bản cho việc liệt kê account/role và lấy refresh token theo cấu hình SSO token provider. Nếu tổ chức có yêu cầu scopes bổ sung, chỉ thêm theo hướng dẫn admin và dịch vụ thực sự cần.

## 6. Cấu hình và đăng nhập bằng AWS CLI v2

### 6.1. Tạo profile

~~~bash
aws --version
aws configure sso --profile dev-sso
~~~

Wizard sẽ hỏi những thông tin như:

- SSO session name;
- SSO start URL/issuer URL;
- SSO Region;
- Registration scopes;
- Account và permission set/role;
- Default service Region;
- Output format;
- Profile name.

Từ AWS CLI v2.22.0, **PKCE authorization là flow mặc định** cho thiết bị có browser. Nếu môi trường phù hợp device authorization, có thể dùng tùy chọn `--use-device-code` theo chính sách tổ chức.

### 6.2. Đăng nhập

~~~bash
aws sso login --profile dev-sso
~~~

CLI mở browser (hoặc in hướng dẫn authorization nếu không mở được), người dùng xác thực và phê duyệt quyền truy cập. Sau đó CLI lưu SSO token cache ở vị trí do AWS CLI quản lý.

### 6.3. Kiểm tra danh tính thực tế

~~~bash
aws sts get-caller-identity --profile dev-sso
aws s3 ls --profile dev-sso --region ap-southeast-1
~~~

`get-caller-identity` trả về account, user/role ARN và user ID của **danh tính đang được dùng thật**. Hãy kiểm tra account ID/role ARN trước khi chạy lệnh thay đổi dữ liệu.

### 6.4. Kết thúc phiên

~~~bash
aws sso logout
~~~

Lệnh logout xóa SSO cached credentials của các sessions liên quan trên máy. Không dùng logout trong một shell/process chia sẻ đang phục vụ người dùng khác.

## 7. Legacy SSO profile: vì sao không nên tạo cấu hình mới theo cách cũ?

Cấu hình cũ đặt trực tiếp các keys SSO trong profile:

~~~ini
[profile legacy-dev]
sso_start_url = https://example.awsapps.com/start
sso_region = us-east-1
sso_account_id = 111122223333
sso_role_name = DeveloperAccess
region = ap-southeast-1
output = json
~~~

Cấu hình legacy có **fixed session (thường 8 giờ)** và không hỗ trợ tự động refresh SSO token như cấu hình SSO token provider mới. Khi phiên hết hạn, ứng dụng không lấy được credentials mới cho tới khi user đăng nhập lại.

| Đặc điểm | SSO token provider mới | Legacy SSO profile |
| --- | --- | --- |
| Cấu trúc | `sso-session` + profile reference | SSO settings nằm trực tiếp trong profile |
| Refresh token flow | Có | Không hỗ trợ auto token refresh |
| Extended session | Theo policy/setting Identity Center | Fixed session cũ |
| Khuyến nghị cho cấu hình mới | **Có** | Không |

Nếu đang kế thừa legacy config, hãy chuyển theo wizard `aws configure sso` và kiểm tra ứng dụng có SDK version/dependencies hỗ trợ SSO token provider mới. Đừng sửa tay file cache token để kéo dài session.

## 8. Java SDK 2.x: thêm dependency SSO, SSO OIDC và STS

Để SDK Java đọc profile SSO và AssumeRole, project cần những modules phù hợp. Ví dụ Maven dùng AWS SDK BOM để các artifacts cùng version:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <aws.sdk.version>2.x.y</aws.sdk.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>software.amazon.awssdk</groupId>
            <artifactId>bom</artifactId>
            <version>${aws.sdk.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>s3</artifactId>
    </dependency>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>sso</artifactId>
    </dependency>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>ssooidc</artifactId>
    </dependency>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>sts</artifactId>
    </dependency>
</dependencies>
~~~

`2.x.y` là placeholder. Chọn **một version AWS SDK for Java 2.x đang được hỗ trợ**, thay placeholder bằng version thực và giữ BOM cùng version cho mọi SDK modules. Không trộn ngẫu nhiên artifacts 2.x khác versions.

Nếu dùng profile SSO, `sso` và `ssooidc` là dependencies quan trọng. Khi dùng `StsAssumeRoleCredentialsProvider`, cần `sts`. Thêm service artifact (`s3`, `dynamodb`, `sqs`...) tương ứng những clients mà application gọi.

## 9. Sử dụng SSO profile từ Java bằng ProfileCredentialsProvider

Cách đơn giản cho local development: dùng đúng profile đã đăng nhập bằng CLI.

~~~java
package com.example.aws;

import software.amazon.awssdk.auth.credentials.ProfileCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.ListBucketsResponse;

public final class SsoS3Example {
    public static void main(String[] args) {
        try (ProfileCredentialsProvider credentials =
                 ProfileCredentialsProvider.create("dev-sso");
             S3Client s3 = S3Client.builder()
                 .region(Region.AP_SOUTHEAST_1)
                 .credentialsProvider(credentials)
                 .build()) {

            ListBucketsResponse response = s3.listBuckets();
            response.buckets().forEach(
                bucket -> System.out.println(bucket.name())
            );
        }
    }
}
~~~

Trình tự:

1. Chạy `aws sso login --profile dev-sso`;
2. `ProfileCredentialsProvider` đọc shared config;
3. Provider nhận diện SSO token provider profile;
4. SDK dùng `sso`/`ssooidc` modules để lấy AWS role credentials;
5. `S3Client` ký request bằng credentials hiện hành;
6. Provider duy trì/refresh credentials theo cơ chế hỗ trợ.

**Không cần tự đọc `~/.aws/sso/cache`, parse JSON token hoặc gọi SSO API thủ công.** Cache là chi tiết implementation được AWS CLI/SDK quản lý.

### Chọn profile bằng môi trường

Nếu muốn dùng profile theo môi trường thay vì hardcode tên profile:

~~~bash
# Linux/macOS
export AWS_PROFILE=dev-sso

# Windows PowerShell
$env:AWS_PROFILE = "dev-sso"
~~~

Khi dùng `DefaultCredentialsProvider`, SDK có thể đọc profile được chọn qua `AWS_PROFILE` ở giai đoạn profile provider. Tuy nhiên, credentials ở những bước ưu tiên cao hơn có thể được chọn trước profile; xem mục 10.

## 10. Default credentials provider chain: thứ tự và bẫy precedence

Nếu không chỉ định provider, service client Java SDK 2.x dùng **default credentials provider chain**. SDK tìm nguồn credentials theo thứ tự chính:

1. Java system properties;
2. Environment variables;
3. Web identity token;
4. Shared AWS `config`/`credentials` profile;
5. ECS container credentials;
6. EC2 instance profile credentials.

~~~mermaid
flowchart TD
    Start[Service client needs credentials] --> Sys[Java system properties]
    Sys -->|No complete credentials| Env[Environment variables]
    Env -->|No complete credentials| Web[Web identity token]
    Web -->|No complete credentials| Profile[Shared profile files]
    Profile -->|No complete credentials| ECS[ECS container endpoint]
    ECS -->|No complete credentials| EC2[EC2 instance metadata]
    EC2 -->|No provider succeeds| Error[SdkClientException: unable to load credentials]
~~~

### Bẫy: profile SSO đã login nhưng Java vẫn dùng credentials khác

Ví dụ máy developer đã chạy `aws sso login --profile dev-sso`, nhưng shell vẫn còn:

~~~bash
AWS_ACCESS_KEY_ID=OLD_ACCESS_KEY
AWS_SECRET_ACCESS_KEY=OLD_SECRET_KEY
AWS_SESSION_TOKEN=OLD_SESSION_TOKEN
AWS_PROFILE=dev-sso
~~~

Vì environment variables đứng trước profile, SDK có thể dùng **credentials môi trường cũ**, không phải SSO profile. `AWS_PROFILE` không đảo precedence của provider chain.

Cách kiểm tra:

- Xem biến `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` và JVM `-Daws.*` có đang set không.
- Chạy `aws sts get-caller-identity --profile dev-sso` để xác minh profile.
- Trong Java, tạm chỉ định `ProfileCredentialsProvider.create("dev-sso")` khi cần chứng minh nguồn.
- Không log secret/session token để debug.

### Chọn provider theo môi trường

| Runtime | Provider nên ưu tiên |
| --- | --- |
| Local developer | `ProfileCredentialsProvider` với SSO token provider |
| CI/CD | OIDC federation hoặc workload role được runner assume |
| EC2 | Instance profile qua `DefaultCredentialsProvider` |
| ECS | Task role/container credentials |
| EKS | Pod identity hoặc IRSA/web identity theo cấu hình cluster |
| Cross-account | Source provider + `StsAssumeRoleCredentialsProvider` hoặc assume-role profile |
| External IdP | Web identity/SAML federation theo kiến trúc đã duyệt |

Không ép mọi môi trường dùng chung một profile SSO của developer. Runtime AWS nên dùng workload identity/role, tránh phụ thuộc cache trên máy cá nhân.
## 11. STS AssumeRole: nhận credentials của một role khác

**AWS Security Token Service (STS)** có API `AssumeRole` để đổi source credentials hiện tại lấy một bộ **temporary security credentials** của IAM role mục tiêu:

- Access key ID;
- Secret access key;
- Session token;
- Expiration timestamp.

~~~mermaid
sequenceDiagram
    participant App as Java application
    participant Source as Source credentials
    participant STS as AWS STS
    participant Role as Target IAM role
    participant S3 as Amazon S3
    App->>Source: Resolve current credentials
    Source-->>App: Source temporary credentials
    App->>STS: AssumeRole(target role ARN)
    STS->>Role: Evaluate trust + caller permissions
    Role-->>STS: Role permissions / session constraints
    STS-->>App: Temporary role credentials
    App->>S3: SigV4 request using assumed role
    S3-->>App: Response if authorized
~~~

### Ví dụ thực tế

Một developer có SSO permission set `DeveloperAccess` trong account A, nhưng cần đọc log bucket ở account B. Thay vì cấp thêm quyền trực tiếp vào user/permission set, administrator có thể:

1. Tạo role `CrossAccountLogReader` trong account B;
2. Cấu hình trust policy cho phép principal phù hợp từ account A assume role;
3. Cấp quyền `sts:AssumeRole` cho source principal ở account A;
4. Gắn quyền đọc đúng bucket/prefix cho target role;
5. Java SDK assume role và dùng credentials mới để gọi S3.

**AssumeRole không cộng dồn quyền source và target.** Khi dùng target role, request được đánh giá theo permissions của target session, cùng các giới hạn như session policy, permissions boundary, SCP và explicit denies.

## 12. Hai policy phải khớp: trust policy và caller identity policy

Đây là nguồn lỗi `AccessDenied` phổ biến nhất khi assume cross-account.

### 12.1. Trust policy ở account đích

Trust policy trả lời: **principal nào được phép assume role này?**

Ví dụ target role ở account `222233334444` tin một role nguồn cụ thể ở account `111122223333`:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "TrustSourceDeveloperRole",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::111122223333:role/SourceDeveloperRole"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

Trong tổ chức dùng IAM Identity Center, source role thường được provision với tên dạng `AWSReservedSSO_<PermissionSet>_<suffix>` và path có thể chứa Region. Không đoán ARN từ tên permission set; lấy ARN thực từ account/CloudTrail/IAM console và kiểm tra thay đổi khi permission set được provision lại.

### 12.2. Identity policy ở account nguồn

Source principal cũng cần được cho phép gọi `sts:AssumeRole` tới ARN mục tiêu (đặc biệt trong cross-account):

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AssumeLogReaderRole",
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": "arn:aws:iam::222233334444:role/CrossAccountLogReader"
    }
  ]
}
~~~

### 12.3. Target role permissions policy

Role đích cần có policy cho phép những thao tác mà ứng dụng sẽ thực hiện. Ví dụ đọc object trong một prefix:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadApplicationLogs",
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket"
      ],
      "Resource": "arn:aws:s3:::company-logs",
      "Condition": {
        "StringLike": {
          "s3:prefix": [
            "application/orders/*"
          ]
        }
      }
    },
    {
      "Sid": "GetApplicationLogObjects",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::company-logs/application/orders/*"
    }
  ]
}
~~~

**Ba lớp trên có nhiệm vụ khác nhau:**

| Thành phần | Được cấu hình ở đâu? | Trả lời câu hỏi |
| --- | --- | --- |
| Trust policy | Role đích | Ai được assume role? |
| Identity policy của source | User/role nguồn | Source có được gọi `sts:AssumeRole` tới ARN này? |
| Permissions policy của target | Role đích | Sau khi assume, session được làm gì? |

Với cross-account, kiểm tra cả hai phía: target account phải tin source principal, source principal phải được cho phép assume. Với same-account, có một số cách cấp quyền qua trust/resource policy; vẫn phải đánh giá toàn bộ policy evaluation.

## 13. Dùng `source_profile` và `role_arn` trong shared config

Một profile có thể tham chiếu profile khác để lấy source credentials rồi assume role.

~~~ini
[profile dev-sso]
sso_session = company-dev
sso_account_id = 111122223333
sso_role_name = DeveloperAccess
region = ap-southeast-1

[sso-session company-dev]
sso_start_url = https://example.awsapps.com/start
sso_region = us-east-1
sso_registration_scopes = sso:account:access

[profile target-log-reader]
role_arn = arn:aws:iam::222233334444:role/CrossAccountLogReader
source_profile = dev-sso
role_session_name = java-log-reader
region = ap-southeast-1
external_id = unique-value-from-target-admin
~~~

Khi Java/CLI dùng profile `target-log-reader`:

1. Đọc profile `dev-sso`;
2. Lấy source credentials từ IAM Identity Center;
3. Gọi STS `AssumeRole` với `role_arn`;
4. Dùng temporary credentials của `CrossAccountLogReader` cho service calls.

`external_id` chỉ đưa vào khi trust policy của target yêu cầu. Với third-party access, external ID do bên sở hữu account đích cung cấp và được kiểm tra trong trust policy; không tự tạo giá trị tùy ý rồi mong IAM tự tin nó.

### `source_profile` và `credential_source` khác nhau

| Setting | Dùng khi |
| --- | --- |
| `source_profile` | Source credentials nằm trong một named profile khác (SSO, profile role, process...) |
| `credential_source = Environment` | Lấy source credentials từ environment/system settings |
| `credential_source = Ec2InstanceMetadata` | Lấy source credentials từ EC2 instance profile |
| `credential_source = EcsContainer` | Lấy source credentials từ ECS container role endpoint |
| `web_identity_token_file` | Dùng OIDC token file để gọi AssumeRoleWithWebIdentity |

**Không khai báo đồng thời `source_profile` và `credential_source` trong cùng một role profile.**

### Java SDK 2.x có khác biệt so với AWS CLI

Theo support matrix của AWS SDKs and Tools Reference Guide, cấu hình assume-role profile của **AWS SDK for Java 2.x có một số giới hạn**:

- `mfa_serial` không được hỗ trợ qua shared assume-role profile config;
- `duration_seconds` không được hỗ trợ qua shared assume-role profile config;
- các setting khác như `role_arn`, `source_profile`, `external_id`, `role_session_name` có support theo profile provider.

Vì vậy, **không copy nguyên một CLI profile có MFA hoặc `duration_seconds` sang Java rồi mặc định SDK hiểu giống CLI**. Nếu cần điều khiển session duration trong Java, dùng `StsAssumeRoleCredentialsProvider` và cấu hình `AssumeRoleRequest` rõ ràng. Nếu cần MFA interactive, thiết kế luồng xác thực phù hợp thay vì hardcode mã TOTP.

## 14. Java SDK 2.x: `StsAssumeRoleCredentialsProvider` tự cache và refresh

Đây là cách explicit để:

- Chọn source credentials provider;
- Chọn STS Region;
- Chọn target role ARN/session name;
- Đặt session duration trong request;
- Prefetch credentials trước khi hết hạn;
- Bật refresh nền để request không phải chờ lấy credentials ở thời điểm cuối.

~~~java
package com.example.aws;

import java.time.Duration;

import software.amazon.awssdk.auth.credentials.ProfileCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.sts.StsClient;
import software.amazon.awssdk.services.sts.auth.StsAssumeRoleCredentialsProvider;

public final class AssumeRoleS3Example {

    public static void main(String[] args) {
        try (ProfileCredentialsProvider source =
                 ProfileCredentialsProvider.create("dev-sso");
             StsClient sts = StsClient.builder()
                 .region(Region.AP_SOUTHEAST_1)
                 .credentialsProvider(source)
                 .build();
             StsAssumeRoleCredentialsProvider assumed =
                 StsAssumeRoleCredentialsProvider.builder()
                     .stsClient(sts)
                     .refreshRequest(r -> r
                         .roleArn("arn:aws:iam::222233334444:role/CrossAccountLogReader")
                         .roleSessionName("java-log-reader")
                         .durationSeconds(3600))
                     .prefetchTime(Duration.ofMinutes(10))
                     .staleTime(Duration.ofMinutes(5))
                     .asyncCredentialUpdateEnabled(true)
                     .build();
             S3Client s3 = S3Client.builder()
                 .region(Region.AP_SOUTHEAST_1)
                 .credentialsProvider(assumed)
                 .build()) {

            s3.listObjectsV2(b -> b
                .bucket("company-logs")
                .prefix("application/orders/"))
              .contents()
              .forEach(object -> System.out.println(object.key()));
        }
    }
}
~~~

### Đọc code theo thứ tự

1. `ProfileCredentialsProvider` lấy source credentials từ profile SSO đã đăng nhập.
2. `StsClient` dùng source provider để ký request STS.
3. `StsAssumeRoleCredentialsProvider` gọi `AssumeRole` và cache credentials nhận được.
4. `prefetchTime(10 phút)` yêu cầu bắt đầu lấy credentials mới trước expiration theo cửa sổ cấu hình.
5. `staleTime(5 phút)` xác định khi nào credentials được coi là stale và cần refresh.
6. `asyncCredentialUpdateEnabled(true)` bật background refresh.
7. `S3Client` luôn nhận credentials thông qua provider, không cần business code tự đọc expiration hay cập nhật access key.

### Vòng đời provider và client

- Tạo provider/client **một lần theo vòng đời application**, ví dụ singleton bean hoặc service resource.
- Không tạo `StsClient` và `StsAssumeRoleCredentialsProvider` cho từng HTTP request.
- Đóng service client, assume-role provider, STS client và source provider khi application shutdown.
- Trong ví dụ try-with-resources, Java đóng tài nguyên theo thứ tự ngược với thứ tự khai báo.
- Nếu provider được chia sẻ bởi nhiều service clients, không đóng provider cho tới khi mọi clients ngừng dùng nó.

**Không tự gọi `AssumeRole` trong mỗi business operation.** Provider có cache và refresh strategy để giảm STS calls, latency và nguy cơ throttling.

## 15. Khi nào nên dùng AssumeRole profile, khi nào dùng provider tường minh?

| Tiêu chí | Assume-role profile | `StsAssumeRoleCredentialsProvider` |
| --- | --- | --- |
| Cấu hình role ARN/source profile | Shared `config` file | Java builder/request |
| Dễ dùng cho CLI và local tooling | **Rất phù hợp** | Phải viết code |
| Session duration tùy chỉnh | Java SDK 2.x profile có giới hạn `duration_seconds` | Có thể đặt trong `AssumeRoleRequest` |
| MFA trong shared profile | Java SDK 2.x không hỗ trợ `mfa_serial` theo support matrix | Có thể truyền MFA parameters khi luồng ứng dụng xử lý được |
| Dynamic session tags/source identity | Khả năng profile phụ thuộc shared settings | Có thể cấu hình trong request |
| Explicit lifecycle/refresh behavior | Do profile provider quản lý | Có stale/prefetch/async options rõ ràng |
| Phù hợp | Cross-account role đơn giản | App cần custom AssumeRole behavior |

### Dùng profile trong Java

Nếu role profile chỉ cần `role_arn`, `source_profile`, `external_id` và `role_session_name`, có thể:

~~~java
try (ProfileCredentialsProvider credentials =
         ProfileCredentialsProvider.create("target-log-reader");
     S3Client s3 = S3Client.builder()
         .region(Region.AP_SOUTHEAST_1)
         .credentialsProvider(credentials)
         .build()) {

    s3.listBuckets();
}
~~~

## 16. Session duration, expiration và role chaining

### Thời lượng STS AssumeRole

Theo STS API:

- Giá trị DurationSeconds tối thiểu: **900 giây (15 phút)**.
- Mặc định nếu không chỉ định: **3.600 giây (1 giờ)**.
- Tối đa: **giới hạn maximum session duration của target role**, có thể được cấu hình từ 1 đến 12 giờ.
- Nếu request dài hơn giới hạn của role, STS từ chối.

### Role chaining bị giới hạn một giờ

**Role chaining** xảy ra khi một role session dùng credentials tạm thời của nó để assume một role khác.

Ví dụ:

~~~text
IAM Identity Center permission set role
          |
          | AssumeRole
          v
CrossAccountLogReader role
          |
          | AssumeRole
          v
EmergencyReadOnly role
~~~

Nếu source credentials đã là assumed-role credentials, lần AssumeRole tiếp theo bị giới hạn tối đa **1 giờ**, kể cả khi target role cho phép session 12 giờ. Không thể tăng giới hạn chaining bằng cách đặt duration_seconds = 43200.

### Phân biệt ba loại thời gian

| Thời gian | Điều khiển bởi | Ý nghĩa |
| --- | --- | --- |
| IAM Identity Center session | Identity Center session duration/policy | Bao lâu user còn phiên SSO và refresh token hợp lệ |
| STS role session | DurationSeconds và maximum session duration của role | Bao lâu temporary role credentials còn hợp lệ |
| Credential provider refresh window | prefetchTime, staleTime, provider implementation | Khi nào SDK lấy credentials mới trước expiration |

**Không cộng thời lượng của các lớp lại với nhau.** Một role session 1 giờ không tự kéo dài SSO session; SSO session hết hạn có thể khiến provider không còn source token để lấy role credentials mới.

## 17. MFA, ExternalId, session tags và source identity

### 17.1. MFA trong AssumeRole

Target role có thể yêu cầu MFA qua trust policy:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::111122223333:role/SourceDeveloperRole"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "Bool": {
          "aws:MultiFactorAuthPresent": "true"
        }
      }
    }
  ]
}
~~~

Khi gọi STS API trực tiếp, request có thể cần:

- SerialNumber: ARN/serial của MFA device;
- TokenCode: mã TOTP hiện hành.

MFA code có thời hạn ngắn. **Không hardcode token code trong source/config, không ghi nó vào logs và không lưu mã TOTP như secret dùng lâu dài.**

Đối với Java SDK 2.x, mfa_serial không được hỗ trợ qua shared assume-role profile config theo support matrix hiện hành. Nếu target role yêu cầu MFA, chọn flow xác thực được hỗ trợ (ví dụ Identity Center/MFA policy) hoặc xây provider/request flow có tương tác và bảo mật phù hợp; không mong profile Java tự bật prompt giống AWS CLI.

### 17.2. ExternalId

External ID thường được dùng khi **third-party service provider** assume role trong account khách hàng. Bên sở hữu account đích cung cấp một giá trị duy nhất; trust policy kiểm tra giá trị đó qua sts:ExternalId.

External ID:

- Không thay thế trust policy hoặc least privilege;
- Không phải mật khẩu người dùng;
- Không cần tự thêm vào mọi AssumeRole cùng tổ chức;
- Nên được cấp/định danh theo từng customer relationship trong mô hình third-party access.

### 17.3. Session tags và ABAC

STS có thể gắn **session tags** vào role session. IAM policy có thể sử dụng principal/session tags cho **attribute-based access control (ABAC)**.

Ví dụ tags:

~~~json
{
  "Tags": [
    {
      "Key": "Environment",
      "Value": "Development"
    },
    {
      "Key": "Team",
      "Value": "Orders"
    }
  ],
  "TransitiveTagKeys": [
    "Team"
  ]
}
~~~

Để truyền tags, caller cần quyền sts:TagSession khi policy yêu cầu; trust policy có thể giới hạn keys/values được phép. Transitive tags có thể đi tiếp qua role chain nếu được cấu hình.

### 17.4. SourceIdentity và RoleSessionName

- **RoleSessionName** giúp phân biệt session trong assumed-role ARN và CloudTrail.
- **SourceIdentity** giúp truy vết danh tính nguồn qua role chaining; target trust policy và caller permissions phải cho phép sts:SetSourceIdentity theo yêu cầu.
- Không đưa email, số điện thoại, customer secret hoặc dữ liệu cá nhân không cần thiết vào session name/tags.

Một session name rõ ràng như orders-api-prod hoặc audit-job-20261120 dễ điều tra hơn session1, nhưng không nên chứa PII.

## 18. Quyền thực tế sau AssumeRole: session policy chỉ thu hẹp

Khi STS cấp temporary credentials, quyền hiệu lực không đơn giản là hợp nhất mọi policies.

Có thể hình dung:

~~~text
Effective permissions
  = target role identity permissions
  intersect session policy (nếu có)
  intersect permissions boundary / organization guardrails
  intersect resource policy evaluation
  minus explicit denies
~~~

- **Target role policy** xác định quyền role có thể nhận.
- **Session policy** (inline hoặc managed policy ARN) có thể giới hạn thêm quyền của session.
- Session policy **không thể cấp thêm quyền vượt target role policy**.
- SCP, permissions boundary, resource policy, KMS key policy và explicit deny vẫn có thể chặn request.

### Ví dụ

Role đích có s3:GetObject trên toàn bộ bucket company-logs, nhưng session policy giới hạn prefix application/orders/. Session chỉ đọc được phần prefix đó.

**Không coi session policy là cách sửa trust policy sai.** Nếu STS không cho assume role, phải sửa trust/caller permissions; nếu assume thành công nhưng S3 từ chối, kiểm tra target role/session/resource/KMS policies.

## 19. Credentials refresh trong SDK Java 2.x hoạt động thế nào?

Nhiều provider có cache credentials nội bộ và tự refresh. Ví dụ:

- StsAssumeRoleCredentialsProvider;
- StsAssumeRoleWithWebIdentityCredentialsProvider;
- WebIdentityTokenFileCredentialsProvider;
- ContainerCredentialsProvider;
- InstanceProfileCredentialsProvider;
- ProfileCredentialsProvider khi profile dùng SSO hoặc AssumeRole.

### Stale time và prefetch time

- **Prefetch time:** thời điểm provider bắt đầu cố lấy credentials mới trước khi credentials hiện tại hết hạn.
- **Stale time:** thời điểm credentials được coi là stale; provider cần refresh để có thể tiếp tục cung cấp credentials hợp lệ.
- **Async update:** refresh nền, giúp giảm khả năng request đầu tiên sau refresh boundary phải chờ STS.

Ví dụ:

~~~text
Temporary credentials expire at 12:00

11:50  Prefetch window begins (10 minutes before expiry)
11:55  Credentials considered stale (5 minutes before expiry)
12:00  Old credentials expire

The provider tries to refresh before the expiration boundary.
~~~

Đây là cấu hình minh họa, không phải SLA đảm bảo STS luôn trả credentials mới đúng một thời điểm. Network, STS throttling, permission changes hoặc SSO session expiration có thể khiến refresh thất bại.

### Java SDK 2.x và refresh mặc định

- Provider STS-based cache temporary credentials.
- SDK có refresh behavior trước expiration; mặc định có cửa sổ prefetch/stale riêng.
- Asynchronous refresh **không tự bật cho mọi provider trong SDK Java 2.x**; cấu hình builder khi muốn refresh nền.
- Nếu background refresh gặp lỗi, provider có thể tiếp tục dùng credentials hiện hành trong giới hạn hợp lệ; sau expiration, request có thể thất bại.
- Giữ provider lâu dài để cache được tái sử dụng; tạo provider liên tục làm tăng STS calls và có thể tăng latency.

**Không cần tự gọi resolveCredentials() theo timer.** Service client gọi provider trong quá trình ký request và provider chịu trách nhiệm trả credentials phù hợp.

## 20. Anti-pattern: các cách làm dễ tạo outage hoặc lộ secret

| Anti-pattern | Vì sao nguy hiểm | Cách làm đúng |
| --- | --- | --- |
| Hardcode access key/secret trong Java | Lộ qua Git/image/logs, khó rotate | SSO/workload role/credential provider |
| Lấy STS credentials một lần lúc startup | Credentials hết hạn nhưng app vẫn giữ bản cũ | Dùng provider có cache/refresh |
| Tạo STS provider cho từng request | Nhiều AssumeRole calls, tăng latency/throttling | Singleton/provider theo application lifecycle |
| Dùng StaticCredentialsProvider với STS values | Provider không tự biết cần refresh session mới | Dùng StsAssumeRoleCredentialsProvider |
| Ghi session token vào logs | Token là một phần credential có thể bị lạm dụng | Log identity ARN, request ID, expiration metadata cần thiết |
| Dùng legacy SSO profile cho process chạy dài | SSO token không tự refresh | SSO token provider config mới |
| Coi AWS_PROFILE luôn thắng env vars | Environment credentials có precedence cao hơn | Xóa env vars stale hoặc chọn explicit provider |
| Cấp AdministratorAccess để chữa AccessDenied | Mở quyền quá rộng, che sai policy | Phân tích trust, identity, target, resource và KMS policies |
| Dùng 12h duration trong role chaining | STS giới hạn role chaining tối đa 1h | Thiết kế chain ngắn, refresh theo provider |
| Copy MFA TOTP vào file config | Mã ngắn hạn bị lộ/không còn hợp lệ | Dùng authentication flow được hỗ trợ |
| Dùng một role session name chung cho mọi workload | Khó audit CloudTrail | Session name có ý nghĩa, không chứa PII |
| Đóng provider khi service client vẫn đang dùng | Request sau đó không còn credentials provider hợp lệ | Quản lý lifecycle ở DI/application scope |

## 21. Local development, CI/CD và AWS runtime: chọn đúng nguồn credentials

### Local developer

Dùng IAM Identity Center SSO token provider profile:

~~~text
aws configure sso
aws sso login --profile dev-sso
Java → ProfileCredentialsProvider("dev-sso")
~~~

Mỗi developer đăng nhập bằng identity cá nhân, permission set được cấp đúng công việc. Không chia sẻ SSO cache hoặc credentials giữa nhiều người.

### CI/CD

Ưu tiên OIDC federation hoặc role do CI runner được phép assume:

~~~text
CI job → OIDC identity token
       → STS AssumeRoleWithWebIdentity
       → Temporary role credentials
       → Deploy AWS resources
~~~

Cấu hình trust policy giới hạn issuer, audience và subject/repository/environment theo provider. Không lưu IAM user secret key lâu dài trong repository secrets nếu có federation phù hợp.

### Amazon EC2

Gắn IAM role qua instance profile. Java SDK dùng DefaultCredentialsProvider/InstanceProfileCredentialsProvider, lấy credentials qua IMDS và refresh theo SDK.

### Amazon ECS

Gán **task role** cho ECS task. Container credentials endpoint cung cấp credentials riêng cho application task. Không nhầm task role với **task execution role** dùng cho ECS agent kéo image, ghi logs hoặc lấy secrets khởi tạo container.

### Amazon EKS

Dùng **EKS Pod Identity** hoặc **IAM Roles for Service Accounts (IRSA)** theo kiến trúc cluster. SDK nhận web identity token/credentials từ môi trường được thiết lập. Không mount long-term keys vào Kubernetes Secret nếu không có ngoại lệ được kiểm soát.

### Cross-account workload

Nếu ECS task role hoặc EC2 instance role cần truy cập account khác:

1. Gán role tối thiểu cho workload nguồn;
2. Target role trust workload role ARN/account phù hợp;
3. Source role cho phép sts:AssumeRole;
4. Dùng StsAssumeRoleCredentialsProvider hoặc profile credential_source phù hợp;
5. Đặt session name/audit, duration và resource permissions đúng.

## 22. Lab 1: SSO login và xác minh account trước khi chạy Java

> **Điều kiện:** AWS CLI v2, Java 17+ (hoặc version phù hợp project), Maven và permission set được tổ chức cấp. Lab chỉ đọc danh tính/list buckets; không yêu cầu tạo hoặc xóa tài nguyên AWS.

### Bước 1: cấu hình SSO profile

~~~bash
aws configure sso --profile dev-sso
~~~

Hoàn tất wizard với start URL, SSO Region, account, permission set, service Region và profile name.

### Bước 2: đăng nhập

~~~bash
aws sso login --profile dev-sso
~~~

### Bước 3: kiểm tra identity

~~~bash
aws sts get-caller-identity --profile dev-sso
aws configure list --profile dev-sso
~~~

Kiểm tra account ID và ARN. Nếu account/role không đúng, dừng trước khi chạy lệnh có side effects.

### Bước 4: chạy Java example

Chạy SsoS3Example ở mục 9 sau khi thêm dependencies sso, ssooidc, s3. Nếu tổ chức không cấp s3:ListAllMyBuckets, thay ví dụ bằng một API read-only mà permission set thực sự cho phép.

## 23. Lab 2: kiểm tra AssumeRole bằng CLI và Java

### Bước 1: dùng source SSO profile

~~~bash
aws sts get-caller-identity --profile dev-sso
~~~

### Bước 2: thử AssumeRole bằng CLI

~~~bash
aws sts assume-role \
  --profile dev-sso \
  --role-arn arn:aws:iam::222233334444:role/CrossAccountLogReader \
  --role-session-name lab-log-reader \
  --duration-seconds 3600
~~~

Nếu target yêu cầu external ID, thêm --external-id với giá trị do administrator account đích cung cấp. Không đưa MFA TOTP hoặc external ID vào logs.

**CLI response chứa secret/session token.** Không paste output lên chat, ticket hoặc log. Chỉ kiểm tra response có credentials/expiration; dùng --query để giới hạn output khi cần.

### Bước 3: kiểm tra Java provider

Dùng AssumeRoleS3Example ở mục 14 với target role và bucket/prefix lab. Provider tự lấy credentials và refresh; không export output STS thành environment variables.

### Bước 4: xác minh danh tính sau AssumeRole

Trong Java, tạo một StsClient dùng cùng assumed provider rồi gọi getCallerIdentity() để xem ARN/account của **target role session**. So sánh với source identity từ profile ban đầu.

~~~java
GetCallerIdentityResponse identity = stsClient.getCallerIdentity();
System.out.println("Account: " + identity.account());
System.out.println("Arn: " + identity.arn());
~~~

Không in access key, secret key hoặc session token.

## 24. Lab 3: quan sát refresh mà không chờ credentials hết hạn

Trong môi trường lab, cấu hình explicit provider:

- Session duration: 900 giây hoặc 3600 giây theo target role;
- prefetchTime: 5–10 phút;
- staleTime: 1–5 phút;
- asyncCredentialUpdateEnabled(true).

Ghi log **thời điểm provider lấy credentials/STS request ID/expiration metadata** qua logging phù hợp, không ghi credential values. Theo dõi CloudTrail AssumeRole events để xác nhận lần refresh xảy ra.

~~~text
Application starts
  → First service call resolves credentials
  → STS AssumeRole event appears
  → Provider caches expiration
  → Prefetch window begins
  → Provider requests new credentials
  → Later service calls use refreshed session
~~~

**Không tạo load test bằng cách gọi AssumeRole liên tục.** Provider được thiết kế để cache; hãy kiểm tra refresh bằng một session lab ngắn hoặc quan sát log/CloudTrail ở tần suất thấp.

## 25. CloudTrail và audit: biết ai đang dùng role nào

STS AssumeRole tạo sự kiện audit trong CloudTrail. Khi điều tra, kiểm tra:

- Source principal (ai/role nào gọi STS);
- Target role ARN;
- Role session name;
- Source identity (nếu có);
- External ID condition/assume context theo event;
- Thời điểm, Region, source IP và user agent;
- Service API calls sau khi role được assume;
- AccessDenied/explicit deny ở target service hoặc KMS.

**RoleSessionName không phải một cơ chế authorization.** Nó giúp định danh session trong log; trust policy và permissions policy mới quyết định ai được assume và làm được gì.
## 26. Troubleshooting: từ nguồn credentials tới quyền của service

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra/khắc phục |
| --- | --- | --- |
| Unable to load credentials from any provider | Không có source credentials, sai profile/path, thiếu SSO modules, chưa login | Kiểm tra AWS_PROFILE, config path, dependencies sso/ssooidc/sts, chạy aws sso login |
| Profile SSO hoạt động với CLI nhưng Java lỗi | SDK Java dependency/version thiếu SSO support hoặc profile name khác | Thêm sso + ssooidc, kiểm tra BOM/version, dùng ProfileCredentialsProvider đúng profile |
| Java dùng nhầm account/role | System properties hoặc environment variables đứng trước profile | Kiểm tra AWS_ACCESS_KEY_ID, AWS_SESSION_TOKEN, JVM -Daws.*, gọi GetCallerIdentity |
| InvalidGrant / refresh token invalid | SSO session hết hạn, bị revoke hoặc token cache không còn hợp lệ | Đăng nhập lại bằng aws sso login; không sửa token cache bằng tay |
| ExpiredToken | Static credentials đã hết hạn, provider không refresh, hoặc source session đã hết hạn | Dùng provider có cache/refresh; kiểm tra SSO session và role expiration |
| AccessDenied khi gọi sts:AssumeRole | Source role thiếu sts:AssumeRole hoặc target trust không tin source | Kiểm tra hai phía policy, principal ARN, account, SCP và permissions boundary |
| AssumeRole thành công nhưng S3/DynamoDB AccessDenied | Target role policy, resource policy, bucket policy, KMS key policy hoặc session policy thiếu quyền | Xác minh target caller ARN và resource-level permissions |
| Role chaining duration validation error | DurationSeconds lớn hơn 3600 khi source đã là role session | Giảm session về tối đa 1 giờ hoặc giảm số role hops |
| Invalid external ID | ExternalId không khớp trust policy hoặc không được cung cấp khi required | Lấy đúng giá trị từ account owner; kiểm tra spelling/condition |
| MFA serial not supported trong Java profile | Java SDK 2.x không hỗ trợ mfa_serial qua shared assume-role profile | Dùng flow xác thực phù hợp hoặc explicit STS request nếu ứng dụng quản lý MFA an toàn |
| STS request RegionDisabled | STS Region/endpoint chưa được bật hoặc cấu hình endpoint sai trong account | Kiểm tra Region STS, regional endpoint, account settings và network |
| SignatureDoesNotMatch / RequestTimeTooSkewed | Đồng hồ máy/container lệch, proxy sửa request hoặc region/signing mismatch | Đồng bộ NTP, kiểm tra Region và HTTPS proxy |
| SSO login được nhưng app không gọi được endpoint | Egress/DNS/proxy tới IAM Identity Center, SSO OIDC hoặc STS bị chặn | Kiểm tra DNS, TLS, outbound HTTPS và proxy config |
| Refresh liên tục gọi STS | Provider được tạo nhiều lần, stale/prefetch cấu hình quá sát hoặc nhiều replicas không chia sẻ cache | Dùng provider singleton theo process; xem CloudTrail và refresh settings |
| Credentials refresh chạy nền nhưng vẫn lỗi | Refresh bị deny/network failure, SSO session hết hạn hoặc target role đã đổi trust | Kiểm tra exception gốc, CloudTrail AssumeRole, SSO login và role policy |
| Logout xong ứng dụng không lấy được credentials | aws sso logout xóa cached session | Đăng nhập lại; không logout phiên đang được app dùng chung |
| CloudTrail khó phân biệt caller | RoleSessionName chung hoặc thiếu SourceIdentity | Dùng session name có ý nghĩa, SourceIdentity/session tags khi policy cho phép |

### Quy trình điều tra theo thứ tự

~~~text
1. Xác định app đang chạy local, EC2, ECS, EKS hay CI/CD.
2. Gọi GetCallerIdentity để xác minh account và ARN thực.
3. Kiểm tra provider cụ thể hoặc default chain precedence.
4. Nếu SSO: kiểm tra sso-session config, login status, sso_region,
   sso/ssooidc dependencies và refresh-token session.
5. Nếu AssumeRole: kiểm tra source credentials, target trust policy,
   source sts:AssumeRole permission, role ARN và session duration.
6. Nếu target service AccessDenied: kiểm tra target role policy,
   resource policy, KMS key policy, session policy và explicit denies.
7. Nếu ExpiredToken: xác minh provider có refresh hay đang giữ static values.
8. Kiểm tra STS Region/network, clock sync và CloudTrail event.
9. Sửa đúng lớp lỗi trong lab/staging, không cấp quyền admin để thử.
10. Xác minh lại identity ARN, successful service call và refresh behavior.
~~~

## 27. Bảo mật credentials và IAM role trong production

### Least privilege cho cả hai role

- Source role chỉ cần quyền assume đúng target role ARN.
- Target role chỉ cấp actions/resources cần thiết.
- Giới hạn trust principal; không trust toàn bộ account nếu chỉ cần một workload/user role.
- Dùng condition keys phù hợp như aws:PrincipalOrgID, aws:PrincipalArn, aws:MultiFactorAuthPresent hoặc ExternalId khi kiến trúc thực sự hỗ trợ.
- Kiểm tra SCP, permissions boundary, session policies và resource policies; explicit deny luôn cần được xử lý.

### Bảo vệ SSO cache và source credentials

- SSO cache nằm trên máy user; bảo vệ account OS, filesystem permissions, endpoint encryption và malware posture.
- Không copy thư mục SSO cache lên shared drive, container image hoặc repository.
- Không gửi token, access key, secret key hay session token qua ticket/chat/email.
- Không bật debug logging có thể in Authorization headers hoặc credentials.
- Trên shared workstation, đăng xuất khi kết thúc và không dùng chung user profile.
- Không đọc hoặc parse token cache trong business code.

### STS, network và thời gian hệ thống

- Dùng STS regional endpoints theo Region/architecture được phê duyệt.
- Cho phép outbound HTTPS/TLS tới IAM Identity Center, SSO OIDC, STS và AWS service endpoints cần thiết.
- Đồng bộ thời gian máy/container bằng NTP; SigV4 phụ thuộc timestamp.
- Dùng TLS certificate validation; không tắt hostname verification để sửa lỗi proxy/certificate.
- Theo dõi CloudTrail và cảnh báo các AssumeRole từ principal/Region/session name bất thường.

### Quản lý session tags và audit

Session tags có thể là attributes dùng trong ABAC; chỉ cho phép keys/values có kiểm soát. SourceIdentity và RoleSessionName hỗ trợ điều tra, nhưng không thay thế permissions. Tránh ghi PII hoặc bí mật trong session metadata vì metadata có thể xuất hiện trong logs/audit.

## 28. Mẫu kiến trúc credential theo môi trường

| Nhu cầu | Thiết kế khuyến nghị | Lý do |
| --- | --- | --- |
| Developer chạy Java trên laptop | IAM Identity Center + SSO token provider + ProfileCredentialsProvider | Không cần IAM user access keys; refresh trong thời gian SSO session còn hiệu lực |
| Java service chạy ECS | ECS task role + DefaultCredentialsProvider | Container credentials được cấp/refresh bởi runtime |
| Java service chạy EC2 | Instance profile + DefaultCredentialsProvider | Không lưu keys trong instance |
| Java service chạy EKS | Pod Identity hoặc IRSA/web identity | Credentials gắn với workload/service account |
| CI/CD deploy account khác | OIDC identity + AssumeRoleWithWebIdentity hoặc runner role + AssumeRole | Federation, không cần long-term key |
| Developer cần đọc dữ liệu account khác | SSO source profile + target role profile/provider | Tách permission set cá nhân và quyền target |
| Third-party vendor truy cập account khách hàng | Cross-account role + ExternalId + least privilege + CloudTrail | Giảm confused-deputy risk và audit được |
| Break-glass support | Role riêng, MFA/approval, thời lượng ngắn, session audit | Truy cập khẩn cấp có kiểm soát |

### Một nguyên tắc thiết kế quan trọng

**Con người đăng nhập bằng federation; workload nhận role từ runtime.** Không dùng SSO cache của developer để vận hành ECS/EKS/EC2 production, và không dùng static access keys để thay role cho workload AWS khi runtime role phù hợp.

## 29. Bài tập áp dụng và câu hỏi tự kiểm tra

### Bài tập 1 — SSO token provider

Một developer cấu hình profile có sso_start_url, sso_region, sso_account_id và sso_role_name trực tiếp trong profile. Ứng dụng Java chạy 8 giờ rồi lỗi xác thực.

**Yêu cầu:** Giải thích legacy profile không hỗ trợ auto refresh; viết lại cấu hình có sso-session, sso_registration_scopes, profile reference và các lệnh login/get-caller-identity.

### Bài tập 2 — Credentials precedence

Máy đã login SSO profile dev-sso nhưng Java vẫn truy cập account cũ. Shell có AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY và AWS_SESSION_TOKEN.

**Yêu cầu:** Giải thích thứ tự provider chain, cách kiểm tra JVM system properties/environment variables và khi nào nên dùng ProfileCredentialsProvider trực tiếp.

### Bài tập 3 — Cross-account AssumeRole

Account A có source role SourceDeveloperRole; account B có CrossAccountLogReader. STS trả AccessDenied.

**Yêu cầu:** Kiểm tra trust policy account B, source identity policy account A, target permissions policy và các guardrails SCP/permissions boundary/resource policy. Vẽ flow source → STS → target role → S3.

### Bài tập 4 — Role chaining duration

Developer dùng SSO credentials để assume Role A, sau đó Role A assume Role B. Target Role B cho phép max session 12 giờ, nhưng STS từ chối request duration 7200 giây.

**Yêu cầu:** Giải thích role chaining max 1 giờ và đề xuất giảm số hops hoặc đặt duration phù hợp.

### Bài tập 5 — Java SDK refresh

Một service tạo StsAssumeRoleCredentialsProvider trong mỗi HTTP request và gọi AssumeRole mỗi lần.

**Yêu cầu:** Mô tả STS call amplification, latency/throttling; viết lại provider singleton với prefetchTime, staleTime, asyncCredentialUpdateEnabled và lifecycle close.

### Bài tập 6 — MFA và ExternalId

Target role yêu cầu MFA và ExternalId. Team thêm mfa_serial vào Java shared profile và kỳ vọng SDK prompt TOTP.

**Yêu cầu:** Nêu giới hạn support matrix Java SDK 2.x; phân biệt MFA serial/token code với ExternalId; đề xuất flow interactive/federated phù hợp và cách không log secrets.

### Bài tập 7 — Production trên ECS

Java app chạy ECS Fargate, nhưng developer copy SSO config/cache từ laptop vào container để lấy quyền account khác.

**Yêu cầu:** Thiết kế lại bằng task role làm source credentials và assume target cross-account role. Phân biệt task role với task execution role; xác định quyền STS và trust policy.

### Bài tập 8 — CloudTrail audit

CloudTrail ghi nhiều AssumeRole events có session name generic là app-session.

**Yêu cầu:** Đề xuất RoleSessionName, SourceIdentity và session tags phù hợp để truy vết service/team/environment mà không đưa PII hoặc secret vào metadata.

### Câu hỏi ngắn

1. **AWS IAM Identity Center permission set là gì?** Bộ quyền được gán cho user/group trên AWS account.
2. **SSO access token có phải session token SigV4 không?** Không.
3. **SSO token provider profile mới khác legacy thế nào?** Có refresh-token flow; legacy không tự refresh SSO token.
4. **AWS SDK Java 2.x cần modules nào cho SSO profile?** sso và ssooidc.
5. **Default credentials provider chain kiểm tra env trước hay profile trước?** Environment variables trước profile.
6. **ProfileCredentialsProvider dùng làm gì?** Đọc một named profile và resolve source/SSO/role credentials.
7. **AssumeRole trả về gì?** Access key ID, secret access key, session token và expiration.
8. **Cross-account cần kiểm tra những phía nào?** Target trust policy và source sts:AssumeRole permission, cùng effective permissions.
9. **Role chaining tối đa bao lâu?** Một giờ.
10. **AssumeRole duration tối thiểu là bao nhiêu?** 900 giây.
11. **Target role max duration có thể lên bao nhiêu?** Tối đa 12 giờ nếu role setting cho phép và không bị role chaining giới hạn.
12. **Session policy có thể mở rộng quyền target role không?** Không; nó chỉ thu hẹp.
13. **ExternalId có phải password không?** Không; nó là identifier chống confused-deputy cho third-party access.
14. **Java SDK 2.x shared assume-role profile hỗ trợ mfa_serial không?** Không theo support matrix hiện hành.
15. **Java SDK 2.x shared assume-role profile hỗ trợ duration_seconds không?** Không theo support matrix hiện hành.
16. **StsAssumeRoleCredentialsProvider có cache credentials không?** Có.
17. **Async refresh có luôn bật mặc định trong Java SDK 2.x không?** Không; cấu hình builder khi cần.
18. **Có nên tạo credentials provider cho từng request không?** Không; tái sử dụng theo application lifecycle.
19. **EC2/ECS có cần copy access keys vào app không?** Không; dùng instance/task role.
20. **AWS_PROFILE luôn thắng AWS_ACCESS_KEY_ID không?** Không; environment credentials có precedence cao hơn profile stage.

## 30. Checklist trước production

- [ ] Local developer sử dụng IAM Identity Center SSO token provider config mới, không tạo access keys dài hạn.
- [ ] Đã cấu hình đúng sso_start_url, sso_region, sso_account_id, sso_role_name và sso_registration_scopes.
- [ ] Đã phân biệt SSO access token với AWS role credentials/session token.
- [ ] Java project có BOM/version thống nhất và dependencies sso, ssooidc, sts cùng service modules cần thiết.
- [ ] Đã xác minh provider đang dùng đúng account/role bằng GetCallerIdentity.
- [ ] Đã kiểm tra system properties/environment variables có ghi đè profile SSO ngoài ý muốn không.
- [ ] Cross-account role có trust policy đúng principal, source sts:AssumeRole permission và target permissions tối thiểu.
- [ ] ExternalId chỉ dùng khi target trust policy yêu cầu và giá trị do account owner cung cấp.
- [ ] MFA requirements được thiết kế theo flow hỗ trợ; không giả định mfa_serial hoạt động trong Java shared profile.
- [ ] RoleSessionName/SourceIdentity/session tags có ích cho audit và không chứa PII/secret.
- [ ] Role chaining không yêu cầu duration quá 1 giờ.
- [ ] Session duration không vượt maximum session duration của target role.
- [ ] StsAssumeRoleCredentialsProvider được tái sử dụng, có cache, prefetch/stale settings và async refresh khi phù hợp.
- [ ] Provider/client lifecycle được đóng đúng thứ tự khi application shutdown.
- [ ] Runtime EC2/ECS/EKS dùng workload role/identity; không copy SSO cache từ laptop.
- [ ] CI/CD dùng OIDC/workload federation nếu có thể, không phụ thuộc long-term IAM user keys.
- [ ] CloudTrail ghi nhận AssumeRole events; session names/source identity giúp truy vết.
- [ ] IAM policies được rà soát least privilege, resource policy, KMS key policy, SCP và permissions boundary.
- [ ] SSO cache/token/session token không xuất hiện trong Git, logs, tickets hoặc container images.
- [ ] Network/DNS/TLS/STS regional endpoint và system clock được kiểm tra.
- [ ] Có runbook xử lý SSO session expired, AssumeRole AccessDenied, ExpiredToken và credential refresh failures.
- [ ] Đã test refresh trong lab bằng session ngắn, quan sát CloudTrail và xác nhận service calls vẫn hoạt động.
- [ ] AWS SDK modules được pin cùng version qua BOM; không trộn SDK versions.
- [ ] Có cơ chế reauthentication rõ ràng khi SSO extended session hết hạn hoặc bị revoke.

## 31. Tổng kết

**SSO** xác thực người dùng và cung cấp đường lấy temporary role credentials theo permission set. **STS AssumeRole** cho phép source identity chuyển sang một role khác khi trust relationship và caller permissions cho phép. **Credential provider** nối hai bước này với service client và quản lý cache/refresh credentials.

Những điểm cần nhớ:

1. Với local development, ưu tiên **IAM Identity Center SSO token provider profile** dùng sso-session; legacy SSO profile không hỗ trợ auto token refresh.
2. AWS SDK for Java 2.x cần các modules **sso** và **ssooidc** cho SSO profile; cần **sts** khi dùng STS provider.
3. Default credentials chain kiểm tra system properties và environment variables trước shared profile; credentials stale ở env có thể khiến SDK dùng nhầm account.
4. Cross-account AssumeRole cần target trust policy và source sts:AssumeRole permission; target role permissions quyết định actions sau khi assume.
5. Role chaining bị giới hạn một giờ; duration của một role không tự kéo dài SSO session hoặc source session.
6. StsAssumeRoleCredentialsProvider cache credentials và có thể prefetch/refresh nền; giữ provider lâu dài thay vì tự lưu access key/secret/session token.
7. Trên EC2/ECS/EKS/CI, ưu tiên workload identity và federation; không dùng SSO cache cá nhân hoặc long-term keys cho production workload.
8. Least privilege, CloudTrail, session metadata, TLS, network access và secret hygiene là phần bắt buộc của thiết kế credentials.

### Tài liệu AWS chính thức để đối chiếu

- [AWS SDK for Java 2.x — Using credentials](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials.html)
- [Default credentials provider chain](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials-chain.html)
- [Specify a credentials provider](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials-providers.html)
- [Credentials caching in Java SDK 2.x](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credential-caching.html)
- [Access credentials for interactive development](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials-temporary.html)
- [IAM Identity Center credential provider](https://docs.aws.amazon.com/sdkref/latest/guide/feature-sso-credentials.html)
- [Configure IAM Identity Center with AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sso.html)
- [AWS CLI IAM Identity Center concepts](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sso-concepts.html)
- [Assume role credential provider settings](https://docs.aws.amazon.com/sdkref/latest/guide/feature-assume-role-credentials.html)
- [AWS STS AssumeRole API](https://docs.aws.amazon.com/STS/latest/APIReference/API_AssumeRole.html)
- [STS examples using AWS SDK for Java 2.x](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/java_sts_code_examples.html)
- [AWS IAM role chaining and session duration](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles.html)
- [AWS SDK for Java 2.x troubleshooting](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/troubleshooting.html)

**Lưu ý vận hành:** SDK/CLI version, SSO session duration, role maximum session duration, permission set, STS Region và provider refresh behavior có thể thay đổi theo tổ chức/account. Đối chiếu support matrix của SDK Java 2.x đang dùng, test trên account lab và xác minh danh tính/expiration bằng STS/CloudTrail trước khi đưa vào production.
