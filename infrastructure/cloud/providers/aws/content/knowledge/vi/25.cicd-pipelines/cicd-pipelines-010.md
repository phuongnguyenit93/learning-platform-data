# CI/CD liên tài khoản và xác thực OIDC từ hệ thống ngoài AWS

Một pipeline CI/CD chạy bên ngoài AWS vẫn cần quyền gọi AWS APIs để đẩy artifact, cập nhật hạ tầng, triển khai container hoặc phát hành ứng dụng. Cách cấp quyền ảnh hưởng trực tiếp đến security posture của toàn bộ quy trình release. Lưu access key dài hạn trong repository secrets có thể khiến credential bị lộ qua log, runner, workflow hoặc bản sao lưu và tạo ra một credential khó gắn với từng lần chạy.

**OpenID Connect (OIDC) federation** cho phép một nền tảng CI/CD đã xác thực workflow phát hành ID token có thời hạn ngắn. AWS Security Token Service (STS) xác minh token và trả temporary credentials cho IAM role nếu trust policy chấp nhận issuer, audience và subject claims. Pipeline sử dụng temporary credentials đó để gọi AWS APIs mà không cần lưu AWS access key dài hạn.

Với môi trường nhiều AWS accounts, có thể cho pipeline assume deployment role trực tiếp ở từng account hoặc assume một role trong tooling account rồi role-chain sang các workload accounts. Cả hai mô hình đều cần ràng buộc trust chặt chẽ, permissions least privilege, audit và kiểm soát đường triển khai.

Bài thuộc chương **CI/CD trên AWS**, mô-đun **CLOUD_PROVIDERS_AWS**. Nội dung kết nối IAM, STS, AWS Organizations, artifact storage, ECR, CloudFormation, ECS/EKS và các môi trường triển khai để xây dựng pipeline an toàn, có thể quan sát và kiểm soát.

> **Nguyên tắc:** OIDC xác minh danh tính của workflow; trust policy quyết định workflow nào được assume role; permissions policy quyết định role session được làm gì. Ba lớp này cần được thiết kế riêng và kiểm tra cùng nhau.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích OIDC federation và phân biệt ID token, access token, AWS temporary credentials.
2. Mô tả luồng GitHub Actions/GitLab CI lấy token và gọi AWS STS.
3. Phân biệt IAM OIDC identity provider, role trust policy và role permissions policy.
4. Giới hạn role assumption theo issuer, audience, repository/project, branch, tag hoặc protected environment.
5. Thiết lập OIDC trust cho GitHub Actions và GitLab CI/CD.
6. Giải thích vì sao không nên lưu AWS access key dài hạn trong CI secrets.
7. Thiết kế cross-account deployment bằng direct federation hoặc hub-and-spoke role chaining.
8. Cấu hình source role và target role cho cross-account AssumeRole.
9. Hiểu tác động của session duration, role chaining, session policies và SCP.
10. Thiết kế least-privilege permissions cho build, artifact publish và deployment.
11. Bảo vệ workflow khỏi untrusted pull requests, dependency/action compromise và token leakage.
12. Dùng CloudTrail, STS caller identity và CI logs để audit/troubleshoot.
13. Xây dựng quy trình onboarding, rotation, decommission và incident response cho OIDC roles.
14. Thực hành thiết lập OIDC deployment role trên AWS sandbox.

## 2. OIDC federation trong CI/CD là gì?

OpenID Connect là một lớp định danh dựa trên OAuth 2.0. Trong CI/CD, identity provider (IdP) phát hành một **ID token** dạng JSON Web Token (JWT) để mô tả danh tính và ngữ cảnh của job/workflow đang chạy.

Một OIDC token thường chứa các claims:

| Claim | Ý nghĩa | Ví dụ |
|---|---|---|
| `iss` | Issuer, nơi phát hành token | `https://token.actions.githubusercontent.com` |
| `aud` | Audience, hệ thống mà token được phát hành cho | `sts.amazonaws.com` |
| `sub` | Subject, danh tính workflow/project/ref/environment | Repository + branch hoặc GitLab project + ref |
| `iat` | Thời điểm token được phát hành | Unix timestamp |
| `exp` | Thời điểm token hết hạn | Unix timestamp |
| `jti` | Token identifier nếu IdP phát hành claim này | Unique token ID |

AWS không tin token chỉ vì runner gửi token tới STS. AWS kiểm tra chữ ký bằng public keys từ IdP JWKS, issuer, audience, thời hạn và các điều kiện trong IAM role trust policy. Nếu hợp lệ, STS trả về bộ credentials tạm thời gồm access key ID, secret access key và session token.

### 2.1. Phân biệt ba loại credential

| Thành phần | Ai phát hành? | Mục đích | Có phải AWS credential? |
|---|---|---|---|
| OIDC ID token | GitHub, GitLab hoặc IdP | Chứng minh identity/claims của job | Không |
| AWS STS temporary credentials | AWS STS | Ký AWS API requests | Có |
| Long-lived IAM access key | IAM | Credential dài hạn của IAM user | Có |

OIDC token là bằng chứng identity. STS credentials là quyền truy cập AWS được cấp sau khi token được xác minh. Không đưa OIDC token hoặc STS credentials vào logs, artifacts, cache hoặc output không cần thiết.

### 2.2. Luồng xác thực

~~~mermaid
sequenceDiagram
    participant CI as External CI runner
    participant IdP as OIDC provider
    participant STS as AWS STS
    participant IAM as IAM role
    participant AWS as AWS services
    CI->>IdP: Request job ID token
    IdP-->>CI: Signed JWT (iss, aud, sub, exp)
    CI->>STS: AssumeRoleWithWebIdentity
    STS->>STS: Verify signature, issuer, audience, expiry
    STS->>IAM: Evaluate role trust policy
    IAM-->>STS: Allow / Deny
    STS-->>CI: Temporary AWS credentials
    CI->>AWS: Signed API request
    AWS->>IAM: Evaluate role permissions and guardrails
    AWS-->>CI: API response
~~~

Các điểm cần nhớ:

- CI runner yêu cầu token từ IdP bằng cơ chế native của nền tảng.
- Token được phát hành cho audience cụ thể; token cho một service khác không nên được dùng để assume AWS role.
- AWS role trust policy phải tin đúng IAM OIDC provider và giới hạn claims.
- STS credentials có expiration; runner phải kết thúc job hoặc refresh theo cơ chế an toàn nếu workflow chạy dài.
- AWS authorization tiếp tục áp dụng identity policy, resource policy, permissions boundary, session policy, SCP và các policy controls khác.

### 2.3. Vì sao OIDC giảm rủi ro credential?

- Không cần lưu IAM user access key trong GitHub/GitLab secrets.
- Mỗi job nhận credential tạm thời gắn với một role.
- Trust policy có thể giới hạn repo/project, branch, tag hoặc environment.
- Có thể thu hồi quyền bằng cách cập nhật trust/permission policy hoặc IdP configuration.
- CloudTrail ghi nhận role session và STS federation events để điều tra.
- Temporary credentials hết hạn tự nhiên, giảm thời gian hữu dụng nếu bị lộ.

OIDC không làm pipeline tự động an toàn. Nếu attacker kiểm soát workflow được trust, runner hoặc dependency trong job, họ có thể sử dụng token/credentials trong thời gian job còn hiệu lực. Phải bảo vệ source code, workflow files, runner và dependencies.

## 3. Ba thành phần IAM cần cấu hình

### 3.1. IAM OIDC identity provider

IAM OIDC provider mô tả issuer mà AWS chấp nhận. Cấu hình gồm:

- Provider URL/issuer chính xác, dùng HTTPS.
- Audience/client IDs được phép.
- Endpoint discovery document và JWKS công khai để AWS xác minh token.
- Certificate chain/endpoint verification theo yêu cầu của IdP.

Ví dụ GitHub Actions provider:

| Trường | Giá trị |
|---|---|
| Provider type | OpenID Connect |
| Provider URL | `https://token.actions.githubusercontent.com` |
| Audience | `sts.amazonaws.com` |

Ví dụ GitLab.com provider:

| Trường | Giá trị |
|---|---|
| Provider type | OpenID Connect |
| Provider URL | `https://gitlab.com` |
| Audience | `sts.amazonaws.com` (nếu job ID token dùng audience này) |

Với GitLab Self-Managed, issuer URL phải khớp chính xác URL public của instance và discovery endpoint phải truy cập được từ AWS. OIDC URL có thể có path theo OIDC standard; không tự bỏ path hoặc thay đổi issuer.

**Lưu ý quan trọng cho cross-account:** IAM OIDC identity provider được tham chiếu trong role trust policy phải nằm trong cùng AWS account với role đó. Nếu pipeline assume role trực tiếp ở nhiều target accounts, mỗi target account cần có OIDC provider tương ứng. Nếu dùng hub-and-spoke, chỉ tooling account cần OIDC provider; các target accounts trust IAM role của tooling account bằng `sts:AssumeRole`.

### 3.2. Role trust policy

Trust policy là resource-based policy gắn với IAM role, xác định principal nào được phép assume role và bằng STS action nào.

Đối với OIDC federation, action thường là:

~~~text
sts:AssumeRoleWithWebIdentity
~~~

Trust policy phải giới hạn tối thiểu:

- Federated principal là đúng OIDC provider ARN.
- `aud` đúng với audience đã đăng ký trong IAM provider.
- `sub` chỉ đúng repository/project và branch/tag/environment được phép.
- Có thể thêm claims ổn định khác nếu IdP và AWS hỗ trợ condition keys.

Không dùng trust policy chỉ có issuer mà thiếu subject restriction. Với GitHub OIDC, AWS yêu cầu `sub` condition không được null hoặc chỉ là wildcard. Wildcard quá rộng có thể cho phép workflow ngoài phạm vi triển khai assume role.

### 3.3. Role permissions policy

Permissions policy xác định role session được gọi AWS APIs nào trên resource nào. Ví dụ:

- Build role: ghi artifact vào prefix cụ thể.
- Deploy role: cập nhật ECS service hoặc tạo CloudFormation stack change.
- Release role: đọc image metadata, publish release và ghi trạng thái deployment.
- Read-only verification role: đọc CloudWatch/ELB/ECS deployment status.

Không nhầm trust policy với permissions policy:

| Policy | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Trust policy | Ai được assume role? | GitHub repository `my-org/my-service`, branch `main` |
| Permissions policy | Role session được làm gì? | `s3:PutObject` vào release artifact prefix |

Role chỉ được assume nếu trust policy cho phép. Sau đó AWS vẫn kiểm tra effective permissions của role session khi gọi từng service API.

## 4. Thiết kế CI/CD liên tài khoản

Một tổ chức có thể chia AWS accounts theo môi trường hoặc chức năng:

| Account | Vai trò |
|---|---|
| Tooling / Shared Services | CI runners, artifact registry, pipeline coordination |
| Development | Workload development |
| Staging | Integration/performance test |
| Production | Workload production và dữ liệu quan trọng |
| Security / Log Archive | Central audit, CloudTrail, security tooling |

Mục tiêu là pipeline có thể triển khai đúng workload account mà không cần một credential có quyền quản trị toàn tổ chức.

### 4.1. Mô hình A — OIDC trực tiếp vào từng target account

~~~mermaid
flowchart TD
    CI["GitHub Actions / GitLab CI"]
    CI -->|"OIDC JWT"| DEV["AWS Dev account<br/>OIDC provider + DevDeployRole"]
    CI -->|"OIDC JWT"| STG["AWS Staging account<br/>OIDC provider + StagingDeployRole"]
    CI -->|"OIDC JWT"| PROD["AWS Production account<br/>OIDC provider + ProdDeployRole"]
    DEV --> DRES["Dev resources"]
    STG --> SRES["Staging resources"]
    PROD --> PRES["Production resources"]
~~~

Mỗi account:

1. Tạo IAM OIDC provider cho cùng IdP.
2. Tạo deploy role với trust policy giới hạn claims.
3. Attach permissions policy riêng theo môi trường.
4. Cấp role ARN cho pipeline tương ứng.

Ưu điểm:

- Không có role chaining.
- Trust policy và permission scope nằm trong account đích.
- Dễ phân biệt role cho Dev/Staging/Production.

Đánh đổi:

- Phải tạo và quản lý OIDC provider trong mỗi account.
- Cần đồng bộ cấu hình trust/IdP khi thay đổi issuer hoặc audience.
- Quản lý nhiều account có thể tạo nhiều bản policy tương tự; nên dùng IaC module và AWS Organizations governance.

### 4.2. Mô hình B — Hub-and-spoke qua tooling account

~~~mermaid
flowchart TD
    CI["External CI runner"] -->|"OIDC token"| IDP["Tooling account<br/>OIDC provider"]
    IDP --> HUB["CICD-FederationRole"]
    HUB -->|"sts:AssumeRole"| DEV["Dev DeploymentRole"]
    HUB -->|"sts:AssumeRole"| STG["Staging DeploymentRole"]
    HUB -->|"sts:AssumeRole"| PROD["Production DeploymentRole"]
    DEV --> D["Dev resources"]
    STG --> S["Staging resources"]
    PROD --> P["Production resources"]
~~~

Mô hình này có hai bước:

1. External CI assume `CICD-FederationRole` trong tooling account bằng `AssumeRoleWithWebIdentity`.
2. Tooling role gọi `AssumeRole` để vào deployment role ở account đích.

Tooling role cần identity policy cho phép `sts:AssumeRole` tới đúng target role ARNs. Mỗi target role cần trust policy cho phép source tooling role. Target role có permissions policy riêng cho workload account.

Ưu điểm:

- Một OIDC provider tập trung trong tooling account.
- Centralize onboarding và audit entry point.
- Có thể tách quyền bootstrap, release và deployment theo team.

Đánh đổi:

- Có thêm role assumption hop.
- Cần quản lý source policy và target trust policy đồng thời.
- Role chaining giới hạn session tối đa một giờ; tính toán thời gian deployment và refresh credentials.
- Nếu tooling role bị compromise, blast radius phụ thuộc danh sách target roles mà nó assume được.

### 4.3. Chọn mô hình

| Tiêu chí | Direct OIDC per account | Hub-and-spoke |
|---|---|---|
| Số OIDC providers | Một mỗi account cần federate | Một ở tooling account |
| Số lần assume role | Một | Hai |
| Central governance | IaC/module đồng bộ nhiều account | Tập trung source role |
| Session duration | Theo OIDC role max duration | Chặng thứ hai tối đa 1 giờ |
| Blast radius | Theo role ở từng account | Theo target role ARNs mà hub được assume |
| Phù hợp | Ít accounts hoặc tách trust rõ | Nhiều accounts, muốn centralize CI federation |

Không có mô hình đúng cho mọi tổ chức. Quyết định dựa trên account count, trust boundary, deployment duration, team ownership và khả năng vận hành IAM policies.

## 5. Chuẩn bị trước khi cấu hình OIDC

Trước khi tạo provider hoặc role, xác nhận:

1. External IdP là GitHub.com, GitLab.com, GitLab Self-Managed hay một OIDC provider khác.
2. Issuer URL và discovery endpoint chính xác, public và sử dụng HTTPS.
3. Audience mà job token sẽ phát hành; audience này phải nằm trong IAM OIDC provider client ID list.
4. `sub` claim thực tế của workflow/job, bao gồm repository/project, branch/tag hoặc environment.
5. Các claims khác mà AWS IAM hỗ trợ làm condition keys cho IdP đó.
6. AWS account ID và Region đích; OIDC provider là IAM global resource trong account.
7. Role ARN, maximum session duration và required AWS actions/resources.
8. Pipeline event nào được phép deploy (push main, protected tag, manual approval, release environment).
9. Runner là ephemeral hay persistent, có isolation và cleanup không.
10. Ai sở hữu workflow, IAM provider, trust policy và deployment permission changes.

Không tự dựng `sub` từ tên repo/branch rồi giả định token sẽ có giá trị đó. Kiểm tra tài liệu IdP và token claim format của đúng repository/project; đặc biệt chú ý GitHub subject claim immutable và GitHub Environment.

## 6. Cấu hình GitHub Actions OIDC với AWS

GitHub Actions cung cấp OIDC token riêng cho workflow/job. Để job có thể yêu cầu token, workflow cần cấp permission `id-token: write`. Permission này chỉ cho phép job yêu cầu ID token từ GitHub; nó **không tự cấp quyền truy cập AWS**. AWS vẫn quyết định bằng IAM provider, trust policy và permissions policy.

### 6.1. Tạo GitHub OIDC provider trong AWS account

Có thể tạo provider bằng AWS CLI:

~~~bash
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com
~~~

Lệnh này là thao tác thay đổi IAM và chỉ cần chạy một lần trong mỗi account sử dụng mô hình direct OIDC. Nếu provider đã tồn tại, kiểm tra URL và audience thay vì tạo trùng.

Provider ARN có dạng:

~~~text
arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com
~~~

### 6.2. GitHub subject claim và immutable IDs

Subject claim phụ thuộc workflow context. Với repository tạo từ ngày 15/07/2026 trở đi, repository đã opt-in immutable subject claims, hoặc repository cũ được rename sau mốc này, GitHub có thể phát hành subject chứa immutable numeric IDs của organization và repository. Dạng ví dụ:

~~~text
repo:my-org@123456/my-service@789012:ref:refs/heads/main
~~~

Repository cũ chưa opt-in có thể vẫn dùng dạng legacy:

~~~text
repo:my-org/my-service:ref:refs/heads/main
~~~

Nếu job dùng GitHub Environment, subject chuyển sang dạng environment, ví dụ:

~~~text
repo:my-org@123456/my-service@789012:environment:production
~~~

Vì vậy, trước khi viết trust policy, xác minh subject thực tế trong cấu hình/claim của repository. Không copy legacy format vào repository đã phát immutable claim; STS sẽ từ chối nếu `sub` không khớp.

### 6.3. Trust policy giới hạn repository và branch

Ví dụ role chỉ được assume từ branch `main` của repository đã phát immutable subject claim:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "TrustGitHubMainBranch",
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
          "token.actions.githubusercontent.com:sub": "repo:my-org@123456/my-service@789012:ref:refs/heads/main"
        }
      }
    }
  ]
}
~~~

Thay account ID, organization ID, repository ID và tên tương ứng bằng giá trị thực của môi trường. Nếu repository vẫn dùng legacy claim, thay `sub` bằng exact legacy value đã xác minh.

Không dùng `StringLike` với `repo:my-org/*` cho production deployment nếu không có lý do rõ ràng; điều đó có thể cho phép nhiều repository trong organization assume role. Exact `StringEquals` cho repository/branch hoặc environment thường là lựa chọn an toàn hơn.

### 6.4. Trust policy khi dùng GitHub Environment

Nếu workflow có:

~~~yaml
jobs:
  deploy:
    environment: production
~~~

Subject cần khớp environment name, không phải branch ref:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
          "token.actions.githubusercontent.com:sub": "repo:my-org@123456/my-service@789012:environment:production"
        }
      }
    }
  ]
}
~~~

Khi dùng Environment, cấu hình protection rules trong GitHub: deployment branches/tags, required reviewers và các rules cần thiết. Trust policy chỉ kiểm tra subject; Environment protection kiểm soát workflow được phép vào environment.

### 6.5. Permissions policy tối thiểu cho artifact upload

Ví dụ role chỉ được ghi object vào một prefix release artifact:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PublishReleaseArtifacts",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject"
      ],
      "Resource": "arn:aws:s3:::company-release-artifacts/apps/my-service/*"
    }
  ]
}
~~~

Đây chỉ là ví dụ cho upload object đơn giản. Nếu pipeline cần multipart, list, read-after-upload hoặc KMS encryption, bổ sung đúng actions/resources theo API thực tế. Nếu bucket dùng SSE-KMS, role còn cần KMS permissions phù hợp và key policy phải cho phép principal. Không gắn `AdministratorAccess` chỉ để làm pipeline chạy được.

### 6.6. GitHub Actions workflow

Ví dụ workflow deploy từ branch `main` bằng `aws-actions/configure-aws-credentials`:

~~~yaml
name: Deploy to AWS

on:
  push:
    branches:
      - main

permissions:
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      id-token: write
    steps:
      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v6.3.0
        with:
          role-to-assume: arn:aws:iam::123456789012:role/GitHubActionsDeployRole
          aws-region: ap-southeast-1
          role-session-name: gha-${{ github.run_id }}

      - name: Verify AWS identity
        run: aws sts get-caller-identity

      - name: Deploy
        run: |
          echo "Run the approved deployment command here"
~~~

Trong production, pin third-party actions theo full commit SHA đã review và cập nhật có kiểm soát. Phiên bản hiển thị ở ví dụ là version tham khảo; kiểm tra release đã được tổ chức phê duyệt trước khi dùng. Không chạy deploy role trên `pull_request` từ fork hoặc workflow chưa được bảo vệ.

### 6.7. GitHub workflow dùng reusable workflow

Nếu tổ chức chuẩn hóa deployment bằng reusable workflow, có thể giới hạn trust thêm theo claim `job_workflow_ref` khi GitHub và AWS IAM hỗ trợ. Điều này giúp buộc deployment đi qua workflow đã review trong repository trung tâm, thay vì tin mọi workflow có thể được sửa trong ứng dụng. Trust conditions phải khớp token claims thực tế và không nên thay thế điều kiện subject repository/environment.



## 7. Cấu hình GitLab CI/CD OIDC với AWS

GitLab CI/CD có thể phát hành ID token bằng keyword `id_tokens`. Dùng ID token hiện hành; biến `CI_JOB_JWT_V2` cũ đã bị loại bỏ từ GitLab 17.0.

### 7.1. Tạo IAM OIDC provider

Với GitLab.com, provider URL là:

~~~text
https://gitlab.com
~~~

Audience cần thống nhất giữa GitLab job ID token và IAM provider client ID list. Ví dụ chọn `sts.amazonaws.com`:

~~~bash
aws iam create-open-id-connect-provider \
  --url https://gitlab.com \
  --client-id-list sts.amazonaws.com
~~~

Với GitLab Self-Managed/Dedicated, thay URL bằng issuer public chính xác của instance và xác minh discovery/JWKS endpoint. AWS cần truy cập được issuer metadata và public keys theo yêu cầu OIDC.

### 7.2. Trust policy giới hạn project và branch

GitLab.com hỗ trợ thêm condition keys ổn định `namespace_id` và `project_id`. Ví dụ trust policy chỉ chấp nhận project ID 67890 trong namespace ID 12345, branch `main`:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "TrustGitLabMainProject",
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::123456789012:oidc-provider/gitlab.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "gitlab.com:aud": "sts.amazonaws.com",
          "gitlab.com:sub": "project_path:mygroup/myproject:ref_type:branch:ref:main",
          "gitlab.com:namespace_id": "12345",
          "gitlab.com:project_id": "67890"
        }
      }
    }
  ]
}
~~~

`project_id` ổn định ngay cả khi project được rename hoặc chuyển namespace; `namespace_id` thay đổi khi project được transfer sang namespace khác. Hai condition này là tính năng dành cho GitLab.com. Với GitLab Self-Managed và GitLab Dedicated, AWS condition keys được hỗ trợ trong hướng dẫn này chỉ gồm `sub` và `aud`; hãy giới hạn subject theo project/ref và kiểm tra tài liệu phiên bản GitLab đang dùng.

### 7.3. GitLab CI job lấy temporary credentials

Khai báo token với audience đúng:

~~~yaml
deploy:
  image:
    name: amazon/aws-cli:2
    entrypoint: [""]
  id_tokens:
    AWS_ID_TOKEN:
      aud: sts.amazonaws.com
  variables:
    AWS_DEFAULT_REGION: ap-southeast-1
  script:
    - |
      set -eu
      TOKEN_FILE="$CI_PROJECT_DIR/web-identity-token"
      trap 'rm -f "$TOKEN_FILE"' EXIT
      printf '%s' "$AWS_ID_TOKEN" > "$TOKEN_FILE"
      chmod 600 "$TOKEN_FILE"

      export AWS_WEB_IDENTITY_TOKEN_FILE="$TOKEN_FILE"
      export AWS_ROLE_SESSION_NAME="gitlab-$CI_PROJECT_ID-$CI_PIPELINE_ID"

      aws sts get-caller-identity
      echo "Run the approved deployment command here"
  rules:
    - if: '$CI_COMMIT_BRANCH == "main"'
~~~

`AWS_ROLE_ARN` được cung cấp qua GitLab CI/CD variable theo project/group/environment. Đây không phải secret; role trust policy là lớp kiểm soát authorization. AWS CLI sử dụng web identity token file và role ARN để gọi STS theo credential provider chain.

Trap sẽ xóa token file khi shell kết thúc bình thường. Với runner persistent, cần thêm cleanup ở runner/workspace lifecycle để xử lý cả job bị force-cancel; bảo đảm workspace isolation giữa các jobs. Một cách khác là gọi `aws sts assume-role-with-web-identity` trực tiếp. Dù dùng cách nào, không echo token, không in response credentials vào log và không upload token file thành artifact.

## 8. Cross-account role assumption

Sau khi pipeline có credentials trong tooling account hoặc target account, cần thiết kế quyền triển khai theo account boundary. Hai điều kiện phải cùng đúng:

1. Source principal có identity policy cho phép gọi `sts:AssumeRole` tới target role.
2. Target role trust policy cho phép source principal assume role.

Một policy chỉ ở source hoặc chỉ ở target là chưa đủ cho cross-account role assumption.

### 8.1. Target deployment role trong workload account

Ví dụ target account `222222222222` có role `ProdDeploymentRole`. Trust policy cho hub role từ tooling account `111111111111`:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "TrustToolingFederationRole",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::111111111111:role/CICD-FederationRole"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

Source role trong tooling account cần identity policy:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AssumeProductionDeploymentRole",
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": "arn:aws:iam::222222222222:role/ProdDeploymentRole"
    }
  ]
}
~~~

Không dùng `Resource: "*"` nếu pipeline chỉ cần deploy vào một số accounts/roles đã xác định. Tách role theo môi trường và giới hạn target ARNs để giảm blast radius.

### 8.2. Target role permissions policy

Ví dụ target role được phép đọc artifact từ một prefix và cập nhật một ECS service. Policy thực tế cần được điều chỉnh theo API calls của deployment tool và resources cụ thể:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadReleaseArtifact",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject"
      ],
      "Resource": "arn:aws:s3:::company-release-artifacts/apps/my-service/*"
    },
    {
      "Sid": "UpdateSpecificEcsService",
      "Effect": "Allow",
      "Action": [
        "ecs:DescribeServices",
        "ecs:UpdateService",
        "ecs:DescribeTaskDefinition",
        "ecs:RegisterTaskDefinition"
      ],
      "Resource": "*"
    },
    {
      "Sid": "PassOnlyApprovedTaskRole",
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": "arn:aws:iam::222222222222:role/MyServiceTaskRole",
      "Condition": {
        "StringEquals": {
          "iam:PassedToService": "ecs-tasks.amazonaws.com"
        }
      }
    }
  ]
}
~~~

Một số ECS APIs không hỗ trợ resource-level permissions và cần `Resource: "*"`. Với những actions hỗ trợ resource scoping, hãy giới hạn cluster, service, task definition và condition keys theo AWS Service Authorization Reference. `iam:PassRole` chỉ nên cho phép pass task/execution roles cụ thể tới đúng AWS service; đây là quyền nhạy cảm vì có thể gián tiếp cấp quyền cao hơn cho workload.

### 8.3. GitHub Actions assume role thứ hai

Với hub-and-spoke, job đầu tiên assume tooling role bằng OIDC, job step tiếp theo assume target deployment role bằng credentials đã có:

~~~yaml
- name: Assume tooling federation role
  uses: aws-actions/configure-aws-credentials@v6.3.0
  with:
    role-to-assume: arn:aws:iam::111111111111:role/CICD-FederationRole
    aws-region: ap-southeast-1
    role-session-name: gha-tooling-${{ github.run_id }}

- name: Assume production deployment role
  uses: aws-actions/configure-aws-credentials@v6.3.0
  with:
    role-to-assume: arn:aws:iam::222222222222:role/ProdDeploymentRole
    aws-region: ap-southeast-1
    role-session-name: gha-prod-${{ github.run_id }}
    role-chaining: true

- name: Verify target account
  run: aws sts get-caller-identity
~~~

Action thứ hai sử dụng credentials từ role đầu để gọi `AssumeRole`. Trust policy của target role phải trust source role; identity policy của source role phải cho phép assume target role. Nếu cấu hình session tagging, bổ sung `sts:TagSession` ở trust/permissions tương ứng hoặc tắt session tagging ở bước chain theo cấu hình action.

### 8.4. Session duration và role chaining

- `AssumeRoleWithWebIdentity` mặc định cấp session 1 giờ; có thể yêu cầu từ 900 giây đến maximum session duration của role, tối đa 12 giờ.
- `AssumeRole` thông thường cũng có thể cấp session tới maximum role duration.
- Khi dùng **role chaining** (role session assume role thứ hai), session thứ hai tối đa **1 giờ**, bất kể target role được cấu hình maximum duration cao hơn.
- Chọn thời lượng ngắn phù hợp với build/deploy job; tránh cấp session 12 giờ chỉ vì job có thể kéo dài.
- Nếu job vượt thời lượng, thiết kế lại pipeline thành stages ngắn có credential refresh/re-assume rõ ràng.

Không đưa STS credentials vào job outputs, artifacts hoặc cache để truyền sang pipeline khác. Một pipeline/job mới nên lấy OIDC token mới và assume role mới theo trust policy.

### 8.5. Session policies, permissions boundary và SCP

Effective permissions của role session có thể bị giới hạn thêm bởi session policy, permissions boundary và AWS Organizations SCP. Các guardrails này thường **giới hạn** quyền; chúng không cấp thêm permissions mà role không có.

- Role permissions policy: quyền nền tảng của role.
- Session policy: thu hẹp quyền của session cụ thể khi assume role.
- Permissions boundary: giới hạn quyền tối đa mà identity policy có thể cấp.
- SCP: giới hạn maximum permissions trong member accounts; SCP không cấp quyền.
- Resource policy: kiểm soát access trực tiếp vào resource nếu service hỗ trợ.

Khi pipeline bị AccessDenied, kiểm tra toàn bộ policy evaluation path. Không vội gắn AdministratorAccess hoặc gỡ SCP để vượt lỗi.

## 9. Bảo mật OIDC và CI runner

OIDC loại bỏ nhu cầu lưu AWS access key dài hạn trong CI secrets, nhưng token và runner vẫn là credential boundary. Nếu một job không đáng tin có thể yêu cầu token hoặc đọc temporary credentials, attacker có thể dùng role session để thực hiện hành động được cấp.

### 9.1. Giới hạn nơi có thể yêu cầu OIDC token

- Cấp id-token: write ở job cần deploy, không cấp rộng cho mọi job nếu không cần.
- Tách build/test job chạy code không tin cậy khỏi deploy job có AWS access.
- Không cấp deployment role cho workflow xử lý pull request từ fork.
- Dùng protected branch, protected tags và required reviewers.
- Với GitHub Environment, bật protection rules và giới hạn deployment branches/tags.
- Với GitLab, chỉ cho deploy từ protected branches/tags và environment được bảo vệ.
- Giới hạn trust policy theo exact repository/project, branch/tag/environment và stable IDs nếu IdP hỗ trợ.
- Nếu dùng reusable workflow, xác minh job_workflow_ref/claims để trust đúng workflow đã review.

### 9.2. Bảo vệ workflow và third-party actions

- Pin actions theo full commit SHA đã review; tag version có thể được di chuyển.
- Review permission changes trong workflow YAML, đặc biệt id-token: write, contents: write, packages: write và deployment secrets.
- Dùng dependency pinning, lockfiles, artifact signing/provenance và vulnerability scanning.
- Không chạy pull request code chưa tin cậy trong cùng job có OIDC permission.
- Tránh workflow trigger pull_request_target chạy code từ fork với privileged token.
- Hạn chế secrets và permissions của mỗi job; không để build job có deployment role.
- Reusable workflow trung tâm nên được review, version/pin và quản lý bởi team platform/security.

### 9.3. Runner isolation

Runner có thể đọc environment variables và file trong job. Nếu runner persistent được dùng chung giữa job không tin cậy và deploy job, token/credentials có thể bị truy cập ngoài ý muốn.

- Ưu tiên ephemeral runners hoặc runner isolation theo trust boundary.
- Không chạy untrusted fork PR và production deploy trên cùng persistent runner.
- Xóa workspace, token file, AWS credential files và temporary artifacts sau job.
- Không cache thư mục $HOME/.aws, web identity token files hoặc credential files.
- Không mount Docker socket/host filesystem rộng cho job không cần.
- Cập nhật runner image và hạn chế outbound network theo yêu cầu.
- Với self-hosted runner, bảo vệ control plane và giới hạn ai được sửa runner labels/config.

### 9.4. Bảo vệ token và temporary credentials

- Không echo OIDC JWT hoặc AWS credentials vào log.
- Không ghi credentials vào GitHub outputs, GitLab artifacts, cache hoặc build metadata.
- Không chuyển token qua job outputs; mỗi job cần identity riêng thì yêu cầu token riêng.
- Dùng STS session duration ngắn nhất phù hợp với deployment.
- Xác định role session name có thể truy vết đến workflow run/pipeline ID.
- Nếu token/credentials bị lộ, revoke session/role access theo incident procedure và điều tra CloudTrail.
- Không dùng OIDC sub chứa PII; subject có thể xuất hiện trong CloudTrail.

### 9.5. OIDC không thay thế authorization

Token chứng minh job thuộc identity đã được IdP xác thực. Nó không tự chứng minh artifact an toàn, code đã được review hoặc pipeline logic không độc hại. Bổ sung:

- Branch protection và code owner review cho workflow files.
- Required deployment approvals cho production.
- Policy-as-code kiểm tra IAM/network/storage configurations.
- Artifact signing, provenance verification và immutable release tags.
- Separation of duties giữa người merge code và người phê duyệt production.
- CloudTrail monitoring cho STS assumption và sensitive AWS API calls.

## 10. Artifact và resource access giữa các accounts

Cross-account deployment không chỉ là assume role. Artifact, container image, KMS key và deployment resource có thể nằm ở account khác; mỗi resource boundary cần authorization phù hợp.

### 10.1. S3 artifact bucket ở account trung tâm

Giả sử deployment role ở account 222222222222 cần đọc artifact từ bucket company-release-artifacts ở account 111111111111.

Cần cả hai:

1. Identity policy của deployment role cho phép s3:GetObject trên object ARN/prefix.
2. Bucket policy ở account chứa bucket cho phép đúng deployment role principal đọc prefix đó.

Ví dụ bucket policy:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowProductionDeploymentRead",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::222222222222:role/ProdDeploymentRole"
      },
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::company-release-artifacts/apps/my-service/*"
    }
  ]
}
~~~

Không mở bucket public để CI/CD đọc artifact. Nếu object được mã hóa SSE-KMS, key policy và KMS permissions cũng phải cho phép target role decrypt. S3 bucket policy không thay KMS key policy.

### 10.2. ECR image ở account khác

Nếu image được publish ở tooling account và workload account kéo image:

- ECR repository policy phải cho phép target principal/actions cần thiết.
- Với ECS, task execution role cần ECR pull permissions; với EKS, cấp quyền cho node role hoặc workload identity theo cơ chế pull image của cluster.
- Nếu pipeline push image, role publish cần ECR upload actions và ecr:GetAuthorizationToken.
- Không cấp quyền xóa repository/image nếu release workflow không cần.
- Pin image bằng digest khi triển khai để tránh tag bị thay đổi giữa build và deploy.

### 10.3. KMS key và secret access

Nếu pipeline cần đọc secret hoặc dùng KMS key ở account khác:

- Identity policy của source/target role phải cho phép action phù hợp.
- KMS key policy hoặc resource policy phải cho phép principal cross-account.
- Secrets Manager resource policy cần giới hạn role ARN, secret ARN và conditions cần thiết.
- Không truyền plaintext secrets qua workflow outputs hoặc artifacts.
- Chỉ cấp quyền đọc secret cho deploy job thực sự cần; build/test job thường không cần production secret.

### 10.4. Không nhầm ExternalId với OIDC

sts:ExternalId thường dùng trong cross-account access do third-party service assume role bằng sts:AssumeRole, đặc biệt để giảm confused-deputy risk. Với OIDC web identity, AWS xác minh token issuer/audience/subject bằng AssumeRoleWithWebIdentity; ExternalId không thay thế các claim conditions đó.

Nếu pipeline assume role lần hai bằng AssumeRole, target role trust policy kiểm tra source IAM role principal và có thể dùng conditions phù hợp với use case. Không thêm ExternalId theo thói quen nếu không có threat model và caller contract yêu cầu.

## 11. Audit, observability và governance

OIDC giúp gắn AWS access với một workflow identity. Cần giữ thông tin đủ để truy ngược mỗi deployment về repository/project, commit, actor và pipeline run.

### 11.1. CloudTrail và STS events

Theo dõi STS federation events như AssumeRoleWithWebIdentity và cross-account AssumeRole. CloudTrail giúp xác định:

- Role nào được assume và trong account nào.
- Thời điểm và source context của request.
- Role session name và assumed role ARN.
- Các AWS API calls tiếp theo được thực hiện bởi role session.
- Error code khi STS từ chối token/trust.

Đặt role-session-name có chứa run/pipeline ID (không chứa secret hoặc PII) để correlate CI run với CloudTrail. Với GitHub, github.run_id thường là một correlation value hữu ích; với GitLab có thể dùng project/pipeline ID.

### 11.2. Kiểm tra caller identity trong pipeline

Sau khi lấy credentials, chạy:

~~~bash
aws sts get-caller-identity
~~~

Lệnh trả account ID, ARN và user ID của principal đang được sử dụng. Trong cross-account flow, kiểm tra account ID đúng target account trước khi chạy deployment. Có thể fail fast nếu account không nằm trong allowlist của environment.

### 11.3. Metrics và alerts

| Signal | Mục tiêu |
|---|---|
| STS AssumeRoleWithWebIdentity success/failure | Phát hiện trust policy/token errors hoặc abuse |
| AssumeRole vào production ngoài release window | Phát hiện role usage bất thường |
| Sensitive API calls ngoài deployment role | Phát hiện thay đổi ngoài pipeline |
| AccessDenied tăng đột biến | Tìm permission drift hoặc credential misuse |
| Workflow deploy từ branch/tag ngoài allowlist | Phát hiện đường release không hợp lệ |
| Runner job duration và credential expiration | Phát hiện job chạy quá session lifetime |
| OIDC provider/role trust policy changes | Audit thay đổi federation boundary |

Dùng CloudTrail, EventBridge, CloudWatch alarms, centralized log archive và security findings để xây dựng alert. Không alert chỉ theo số lượng STS events mà bỏ qua principal, account, repository/project và environment context.

### 11.4. Onboarding và decommission

Mỗi OIDC deployment role cần metadata owner:

- IdP/provider URL và audience.
- Repository/project IDs và trusted branches/environments.
- AWS account, role ARN, permissions owner.
- CI workflow/reusable workflow owner.
- Maximum session duration và expected job duration.
- Last-used/CloudTrail review, ticket và approval.
- Contact/expiry cho temporary roles.

Khi repository/project bị archive, đổi tên, chuyển owner hoặc pipeline migration:

1. Xác nhận job mới và trust claims mới.
2. Update trust policy theo change review.
3. Test STS assume trên sandbox hoặc non-production role.
4. Chuyển workflow và xác minh CloudTrail/caller identity.
5. Remove old subject/role access sau khi migration hoàn tất.
6. Decommission provider/role không còn dùng theo dependency inventory.

## 12. Troubleshooting OIDC và cross-account deployment

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| `InvalidIdentityToken` | Issuer, chữ ký, JWKS, audience hoặc token expiry không hợp lệ | Provider URL, discovery document, JWKS, `aud`, clock và token lifetime |
| `IDPRejectedClaim` | IdP từ chối claim hoặc claim không thỏa yêu cầu | Subject/ref/environment, protected branch, GitLab project/namespace IDs |
| `AccessDenied` khi AssumeRoleWithWebIdentity | Trust policy không khớp, sai provider ARN hoặc thiếu điều kiện cần thiết | Federated principal, `aud`, `sub`, provider account, role trust |
| No OpenIDConnect provider found | Chưa tạo provider trong account chứa role hoặc ARN sai | `list-open-id-connect-providers`, provider ARN và target account |
| GitHub role assume fail sau đổi repo | Subject claim chuyển sang immutable ID format hoặc Environment | Kiểm tra actual `sub`, organization/repository IDs và environment name |
| GitHub job không có token | Job thiếu `id-token: write` hoặc action chạy ở context không hỗ trợ | Workflow/job permissions, trigger và job context |
| GitLab job không lấy được token | Dùng biến JWT cũ, `id_tokens` audience sai hoặc runner config | GitLab version, ID token declaration, `aud` và issuer |
| AssumeRole chặng hai bị AccessDenied | Source role thiếu `sts:AssumeRole` hoặc target trust không trust source role | Source identity policy, target trust policy, SCP/permissions boundary |
| Deploy role assume được nhưng AWS API bị deny | Permissions policy hoặc resource policy không đủ | Action, resource ARN, bucket/ECR/KMS policy, `iam:PassRole` |
| Job hết credentials giữa deploy | Session duration ngắn hoặc role chaining giới hạn 1 giờ | STS expiration, job duration, role chain và re-assume design |
| S3 cross-account GetObject bị deny | Thiếu identity policy, bucket policy hoặc KMS key policy | Cả ba policy boundaries và object encryption |
| OIDC provider hoạt động ở Dev nhưng fail ở Prod | Provider chỉ tồn tại ở một account, hoặc trust khác nhau | Provider trong cùng account với role, IaC drift và trust conditions |

### 12.1. Kiểm tra OIDC provider

~~~bash
aws iam list-open-id-connect-providers

aws iam get-open-id-connect-provider \
  --open-id-connect-provider-arn arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com
~~~

Xác minh provider URL, client ID list/audiences và account đang truy vấn. IAM OIDC provider là resource cấp account; không giả định provider ở tooling account tự động có hiệu lực trong target accounts.

### 12.2. Kiểm tra role và caller identity

~~~bash
aws iam get-role \
  --role-name GitHubActionsDeployRole

aws sts get-caller-identity
~~~

Đọc trust policy và permissions policies được attach vào role. Nếu `get-caller-identity` thành công, xác minh account ID/ARN trước khi gọi deployment API.

### 12.3. Kiểm tra discovery document

OIDC discovery document nằm tại đường dẫn `/.well-known/openid-configuration` trên issuer. Ví dụ:

~~~bash
curl -sS https://token.actions.githubusercontent.com/.well-known/openid-configuration
curl -sS https://gitlab.com/.well-known/openid-configuration
~~~

Đối chiếu `issuer`, `jwks_uri` và audience theo tài liệu IdP. AWS cần truy cập endpoint công khai để xác minh JWT; với private/self-managed IdP, làm theo hướng dẫn tích hợp tương ứng thay vì mở endpoint không kiểm soát.

### 12.4. Điều tra CloudTrail

Có thể tìm STS federation events trong CloudTrail Event history:

~~~bash
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=AssumeRoleWithWebIdentity \
  --max-results 20

aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=AssumeRole \
  --max-results 20
~~~

Đọc error code, role ARN, principal/session context và timestamp. Không xuất token hoặc temporary credentials từ CI logs để debug.

### 12.5. Phân biệt lỗi trust với lỗi permissions

- STS assume role thất bại: xem issuer/provider, audience, subject, trust policy và source identity.
- STS thành công nhưng service API thất bại: xem role permissions, session policy, resource policy, permissions boundary, SCP, KMS và VPC endpoint policy.
- AssumeRole chặng hai thất bại: xem source role identity policy và target role trust policy.
- `iam:PassRole` thất bại: xác minh role ARN, `iam:PassedToService` và resource scope.

Không giải quyết lỗi trust bằng cách đổi permissions policy của role. Hai policy kiểm soát hai bước authorization khác nhau.

## 13. Incident response khi OIDC role bị lạm dụng

Nếu phát hiện workflow/runner không tin cậy đã assume deployment role:

1. Xác định role ARN, AWS account, region, CloudTrail events và thời gian session.
2. Disable hoặc thu hẹp trust policy để ngăn token mới assume role; cân nhắc deny/permission reduction theo incident plan.
3. Tạm dừng pipeline/workflow và cô lập runner bị nghi ngờ.
4. Xác định repository/project, workflow file, branch/tag/environment, actor và commit liên quan.
5. Kiểm tra các API calls trong CloudTrail sau STS assume event; xác định resource bị đọc/sửa/xóa.
6. Thu hồi/revoke active sessions theo cơ chế IAM role session revocation phù hợp; lưu ý thay trust policy không tự làm mọi credentials đang phát hành hết hiệu lực ngay lập tức.
7. Rotate/revoke application secrets hoặc downstream credentials nếu pipeline có thể truy cập chúng.
8. Khôi phục resources, kiểm tra artifacts/images và phát hành build sạch nếu cần.
9. Sửa trust policy, permissions, workflow, runner isolation và dependency pins.
10. Re-enable pipeline sau khi test OIDC và cross-account access trong non-production.

Giữ audit evidence theo incident retention policy. Không xóa CloudTrail logs, runner logs hoặc artifacts liên quan trước khi hoàn tất điều tra.

## 14. Bài thực hành trên AWS sandbox

### 14.1. Lab A — GitHub Actions direct OIDC

1. Tạo GitHub OIDC provider trong AWS sandbox account.
2. Tạo role chỉ trust một repository và branch đã xác minh subject claim.
3. Attach policy chỉ cho phép ghi artifact vào một S3 prefix.
4. Tạo GitHub workflow với job-level `id-token: write`.
5. Dùng configure-aws-credentials để assume role.
6. Chạy `aws sts get-caller-identity` và xác minh account/role ARN.
7. Upload một artifact test vào đúng prefix; thử ghi sang prefix khác để xác nhận bị deny.
8. Kiểm tra CloudTrail event và role session name.

### 14.2. Lab B — GitLab CI OIDC

1. Tạo GitLab OIDC provider trong AWS sandbox account.
2. Chọn audience và thêm vào IAM provider client ID list.
3. Tạo role trust policy giới hạn project, namespace/project IDs và branch main (nếu GitLab.com).
4. Tạo CI job với `id_tokens` và đúng audience.
5. Cấu hình `AWS_ROLE_ARN` và web identity token file.
6. Chạy `aws sts get-caller-identity`.
7. Thử pipeline từ branch không được trust và quan sát STS deny.

### 14.3. Lab C — Hub-and-spoke cross-account

1. Tạo OIDC provider và `CICD-FederationRole` trong tooling account.
2. Giới hạn trust policy theo repo/project và production branch/environment.
3. Attach source identity policy chỉ cho phép assume Dev/Staging/Prod role ARNs đã định.
4. Tạo target roles trong Dev/Staging/Prod accounts; trust source role.
5. Attach permissions policy khác nhau cho từng target environment.
6. Dùng GitHub Action assume tooling role rồi assume target role.
7. Xác minh account ID sau mỗi chặng.
8. Đo thời gian job và kiểm tra role chaining không vượt một giờ.

### 14.4. Lab D — Artifact bucket cross-account

1. Đặt S3 artifact bucket ở tooling account.
2. Tạo deploy role ở workload account.
3. Cấp identity policy `s3:GetObject` trên prefix cần đọc.
4. Cấp bucket policy cho đúng role ARN.
5. Nếu dùng SSE-KMS, thêm KMS key policy/permissions phù hợp.
6. Test GetObject trong deployment job; thử đọc prefix khác để xác nhận bị deny.

### 14.5. Lab E — Negative security tests

Thử các trường hợp sau trong sandbox:

- Đổi `aud` trong job token.
- Đổi branch/ref khỏi branch được trust.
- Thử repo/project khác.
- Thử GitHub Environment không được trust.
- Tạm bỏ `id-token: write` ở job.
- Thử target role chưa được source role cấp `sts:AssumeRole`.
- Thử gọi service action ngoài permissions policy.
- Thử role chaining với session duration lớn hơn một giờ.

Ghi lại error code và policy condition khiến request bị từ chối. Negative tests giúp xác nhận trust policy có giới hạn đúng.

## 15. Checklist review OIDC và cross-account CI/CD

### Identity provider và trust

- [ ] Issuer URL chính xác, HTTPS và discovery/JWKS endpoint hợp lệ?
- [ ] Audience khớp giữa CI ID token và IAM provider?
- [ ] OIDC provider nằm trong cùng account với role trực tiếp trust nó?
- [ ] Trust policy có exact `aud` và `sub` restrictions?
- [ ] GitHub subject claim đã kiểm tra immutable IDs/Environment format?
- [ ] GitLab.com có thể pin `project_id`/`namespace_id` khi phù hợp?
- [ ] Self-managed GitLab dùng đúng issuer và claims được AWS hỗ trợ?
- [ ] Không có wildcard trust quá rộng hoặc subject rỗng?

### Permissions và account boundaries

- [ ] Role permissions theo least privilege và resource ARN/prefix?
- [ ] Source role có `sts:AssumeRole` tới đúng target ARNs?
- [ ] Target trust policy chỉ trust source role cần thiết?
- [ ] `iam:PassRole` giới hạn role và service được pass?
- [ ] Bucket/ECR/KMS resource policies cho phép đúng target principal?
- [ ] Session policy, permissions boundary và SCP được tính đến?
- [ ] Role chaining/session duration phù hợp thời gian job?

### CI workflow và runner

- [ ] `id-token: write` chỉ cấp cho job cần thiết?
- [ ] Workflow file được bảo vệ bằng branch protection/code review?
- [ ] Production Environment có required reviewers/protection rules?
- [ ] Không chạy untrusted fork PR trong job có AWS role?
- [ ] Third-party actions được pin và review?
- [ ] Runner isolation/ephemeral cleanup phù hợp?
- [ ] Token/credentials không xuất hiện trong logs, artifacts, cache hoặc outputs?

### Audit và operations

- [ ] Role session name có thể correlate với workflow run/pipeline ID?
- [ ] CloudTrail ghi nhận STS events và sensitive API calls?
- [ ] Có alert cho role assumption bất thường và trust policy changes?
- [ ] Có owner, ticket, expiry và decommission process cho role/provider?
- [ ] Có incident runbook và cách xử lý active role sessions?
- [ ] Negative tests xác nhận branch/repo/audience khác bị deny?



## 16. Câu hỏi tự đánh giá

1. OIDC federation giải quyết vấn đề nào trong CI/CD?
2. OIDC ID token khác AWS STS temporary credentials thế nào?
3. Ba claims `iss`, `aud`, `sub` có vai trò gì?
4. AWS xác minh OIDC token bằng những thông tin nào?
5. IAM OIDC provider mô tả điều gì?
6. Trust policy khác permissions policy thế nào?
7. Vì sao trust policy cần giới hạn `sub`?
8. `id-token: write` trong GitHub Actions cấp quyền gì và không cấp quyền gì?
9. Vì sao GitHub subject claim có thể chứa organization/repository IDs?
10. GitHub Environment làm thay đổi subject claim như thế nào?
11. Vì sao cần environment protection rules ngoài IAM trust policy?
12. GitLab ID token được khai báo bằng keyword nào?
13. Vì sao không nên dùng biến `CI_JOB_JWT_V2`?
14. GitLab.com có thể dùng `project_id` và `namespace_id` condition keys để làm gì?
15. GitLab Self-Managed có cùng AWS condition keys như GitLab.com không?
16. Vì sao IAM OIDC provider cần nằm cùng account với role trust nó?
17. Mô hình direct OIDC per account khác hub-and-spoke ra sao?
18. Cross-account AssumeRole cần những policy nào ở source và target?
19. Vì sao `sts:AssumeRole` không đủ nếu target trust policy không cho phép source role?
20. Role chaining giới hạn session duration tối đa bao lâu?
21. `sts:ExternalId` có thay thế OIDC subject/audience conditions không?
22. Khi nào cần `iam:PassRole` trong ECS deployment?
23. Vì sao `iam:PassRole` cần resource và service condition chặt chẽ?
24. Cross-account S3 GetObject cần identity policy và bucket policy như thế nào?
25. Nếu S3 artifact dùng SSE-KMS, cần kiểm tra thêm gì?
26. SCP có cấp quyền cho role session không?
27. Vì sao không nên cấp `id-token: write` cho mọi job?
28. Vì sao persistent runner dùng chung giữa untrusted PR và deploy job nguy hiểm?
29. CloudTrail giúp correlate OIDC workflow với AWS API calls như thế nào?
30. Khi token bị lộ, cần xử lý những lớp nào?
31. Vì sao thay trust policy không tự làm mọi active credentials hết hiệu lực ngay?
32. Những negative tests nào xác nhận trust policy không quá rộng?

### Định hướng đáp án

- **Identity:** IdP phát hành JWT; AWS STS xác minh và cấp temporary credentials.
- **Trust:** Provider xác định issuer; trust policy giới hạn principal/claims; permissions policy giới hạn AWS actions/resources.
- **GitHub/GitLab:** Audience phải khớp, subject phải giới hạn repository/project/ref/environment; GitHub immutable subject và GitLab stable project IDs cần được kiểm tra.
- **Cross-account:** Direct federation tạo provider trong mỗi account có role; hub-and-spoke dùng OIDC vào tooling role rồi AssumeRole sang target roles.
- **Security:** Least privilege, protected branch/environment, ephemeral runner, action pinning, không log token/credentials.
- **Audit:** CloudTrail STS events, role session name, caller identity và negative tests giúp xác minh đường truy cập.

## 17. Tài liệu AWS, GitHub và GitLab chính thức

1. [AWS IAM: Create an OpenID Connect identity provider](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers_create_oidc.html) — Provider URL, discovery document, JWKS, audiences and IAM provider setup.
2. [AWS IAM: Create a role for OIDC federation](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_create_for-idp_oidc.html) — Trust policy and OIDC role configuration.
3. [AWS IAM: Available keys for AWS OIDC federation](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_iam-condition-keys.html) — OIDC claims and condition keys.
4. [AWS STS: AssumeRoleWithWebIdentity API](https://docs.aws.amazon.com/STS/latest/APIReference/API_AssumeRoleWithWebIdentity.html) — Web identity token validation and temporary credentials.
5. [AWS STS: AssumeRole API](https://docs.aws.amazon.com/STS/latest/APIReference/API_AssumeRole.html) — Cross-account role assumption and role chaining.
6. [AWS IAM: Cross-account resource access](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies-cross-account-resource-access.html) — Source identity policy and target trust policy.
7. [AWS IAM: Role chaining](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles.html) — Session duration and role chaining constraints.
8. [AWS IAM: Secure-by-default controls for shared OIDC providers](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers_oidc_secure-by-default.html) — Required identity-provider claim controls.
9. [AWS IAM: Create and manage OIDC identity providers](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers_create_oidc.html) — Provider audiences and certificate verification.
10. [AWS CloudTrail user guide](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-user-guide.html) — STS and AWS API audit.
11. [GitHub Docs: Configuring OpenID Connect in AWS](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws) — GitHub issuer, audience, claims and trust policy.
12. [GitHub Docs: OIDC claims and scoping permissions](https://docs.github.com/en/actions/concepts/security/openid-connect) — Workflow identity and token claims.
13. [aws-actions/configure-aws-credentials](https://github.com/aws-actions/configure-aws-credentials) — Current GitHub Action usage, OIDC setup, role chaining and options.
14. [GitLab Docs: Configure OpenID Connect in AWS](https://docs.gitlab.com/ci/cloud_services/aws/) — GitLab ID tokens, AWS provider, trust policy and temporary credentials.
15. [GitLab Docs: ID token authentication](https://docs.gitlab.com/ci/secrets/id_token_authentication/) — ID token configuration and audience.
16. [GitLab Docs: Connect to cloud services](https://docs.gitlab.com/ci/cloud_services/) — Cloud federation and claim restrictions.
17. [AWS IAM: IAM policy evaluation logic](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic.html) — Identity, resource, boundary and organization policy evaluation.
18. [AWS IAM: PassRole](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_use_passrole.html) — Securely passing a role to an AWS service.

> **Ghi nhớ cuối bài:** OIDC giúp external CI nhận AWS temporary credentials mà không cần lưu access key dài hạn. Trust policy phải giới hạn đúng issuer, audience và subject; permissions policy phải giới hạn đúng actions/resources. Với nhiều AWS accounts, chọn direct OIDC hoặc hub-and-spoke, kiểm tra source/target trust và session duration. Bảo vệ workflow, runner, artifact và CloudTrail audit để mỗi deployment có thể truy vết và giới hạn blast radius.




