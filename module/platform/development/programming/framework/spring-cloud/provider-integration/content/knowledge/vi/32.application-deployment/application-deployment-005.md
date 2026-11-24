# Cấp quyền CI/CD bằng liên kết danh tính thay cho khóa dài hạn

Pipeline CI/CD cần xác thực với cloud để tạo hạ tầng, đẩy container image, cập nhật ứng dụng hoặc phát hành artifact. Cách làm cũ thường lưu access key, client secret hoặc service account key trong CI variables rồi truyền credential đó cho mỗi job. Credential dài hạn có thể tồn tại lâu hơn vòng đời pipeline, bị sao chép qua log/artifact, được dùng lại ngoài runner hoặc tiếp tục hoạt động sau khi người tạo job đã rời nhóm.

OpenID Connect (OIDC) workload identity federation cho phép pipeline chứng minh danh tính bằng token ngắn hạn do nền tảng CI phát hành. Cloud provider xác minh issuer, audience và subject/claims của token, sau đó cấp credential tạm thời hoặc access token cho principal đã được cấu hình. Pipeline không phải lưu khóa cloud dài hạn. Quyền triển khai vẫn được kiểm soát bằng IAM/RBAC trên resource cụ thể và bằng điều kiện trust giới hạn repository, branch, environment hoặc service connection được phép yêu cầu token.

Bài học thuộc chương **Triển khai ứng dụng** của mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**. Mô-đun thực hành tích hợp Spring Boot với dịch vụ managed của AWS, Azure và Google Cloud qua các thư viện Spring Cloud tương ứng; học cấu hình danh tính và quyền, truy cập storage, messaging, dữ liệu, bảo vệ secret, kiểm thử tích hợp và đánh giá khác biệt giữa các cloud provider. Bài này tập trung vào cấp quyền cho CI/CD runner bằng OIDC federation, thay thế khóa dài hạn, giới hạn trust policy và phân tách quyền pipeline với danh tính runtime của ứng dụng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích rủi ro của access key, client secret và service account key được lưu trong CI/CD.
- Mô tả luồng OIDC token exchange từ GitHub Actions, GitLab CI hoặc Azure DevOps tới cloud provider.
- Phân biệt issuer, subject, audience, claim, federated credential và cloud principal.
- Thiết lập AWS IAM OIDC provider và role trust policy cho GitHub Actions.
- Dùng Microsoft Entra federated identity credential cho GitHub Actions hoặc Azure DevOps service connection.
- Tạo Google Cloud Workload Identity Pool/Provider và cấp quyền qua service account impersonation hoặc direct resource access.
- Giới hạn trust theo repository ID, owner ID, project ID, branch, environment và workflow.
- Thiết kế quyền deployer tối thiểu theo account, subscription, project và resource.
- Tách danh tính CI/CD khỏi workload identity mà Spring Boot dùng khi chạy.
- Xử lý token, credential file, log và artifact an toàn.
- Kiểm thử cả trường hợp được phép và bị từ chối, đồng thời chẩn đoán lỗi federation.

## 2. Vì sao không lưu khóa cloud dài hạn trong pipeline?

Một khóa dài hạn thường có thể dùng lặp lại cho tới khi bị thu hồi hoặc hết hạn theo cấu hình. Nếu khóa được lưu trong CI variable, người có quyền sửa pipeline hoặc job có thể tìm cách đọc, chuyển tiếp hoặc sử dụng khóa đó ngoài mục đích ban đầu.

Các rủi ro thường gặp:

- Secret bị in ra log khi shell bật trace hoặc lệnh debug in toàn bộ environment.
- Credential bị copy vào artifact, cache, Docker build argument hoặc image layer.
- Một job chạy từ pull request không tin cậy tìm cách đọc biến môi trường có quyền production.
- Runner tự quản lý bị xâm nhập và lưu lại credential để dùng sau.
- Khóa dùng chung cho nhiều repository khiến khó xác định job nào đã sử dụng.
- Khóa không được thu hồi khi nhân sự, repository hoặc pipeline thay đổi.
- Quyền của khóa thường rộng hơn mức cần thiết để triển khai một service.

OIDC federation thay đổi cách pipeline chứng minh danh tính: job nhận một JWT có thời hạn ngắn từ CI platform; cloud xác minh token theo cấu hình tin cậy; sau đó cấp credential tạm thời. Trust policy và IAM role vẫn tồn tại, nhưng không cần cất private key/access key dài hạn trong CI.

### 2.1. So sánh hai cách xác thực

| Tiêu chí | Khóa dài hạn | OIDC workload identity federation |
|---|---|---|
| Credential lưu trong CI | Access key, client secret hoặc JSON key | Không cần lưu khóa cloud |
| Thời hạn | Có thể kéo dài tới khi rotate/revoke | Token và credential trao đổi có thời hạn ngắn |
| Ràng buộc repository/job | Thường dựa vào nơi lưu secret và quyền CI | Có thể ràng buộc issuer, subject, audience và claims |
| Rotation | Phải tạo, phân phối và thu hồi khóa | CI platform phát token mới cho từng job |
| Audit | Khó phân biệt người/job nếu dùng chung key | Có thể truy vết subject, role session và workflow |
| Rủi ro còn lại | Secret leak và reuse | Trust policy quá rộng, runner/job bị xâm nhập, quyền IAM quá lớn |

OIDC không tự động làm pipeline an toàn. Nếu trust policy cho phép mọi repository trong một issuer công khai, hoặc workflow production chạy code tùy ý từ pull request, kẻ tấn công vẫn có thể xin token hợp lệ. Phải giới hạn trust và kiểm soát mã chạy trong job.

## 3. Luồng OIDC từ CI runner tới cloud

~~~mermaid
sequenceDiagram
    participant CI as CI platform
    participant Job as CI runner/job
    participant Cloud as Cloud identity provider
    participant IAM as IAM / RBAC
    participant API as Deployment API

    CI->>Job: Cấp OIDC ID token cho job
    Job->>Cloud: Gửi JWT (issuer, audience, subject, claims)
    Cloud->>Cloud: Xác minh chữ ký, issuer, expiry, audience
    Cloud->>Cloud: So khớp subject và trust conditions
    Cloud->>Job: Cấp credential ngắn hạn hoặc federated token
    Job->>IAM: Gọi API bằng principal đã xác thực
    IAM->>IAM: Kiểm tra role, action và resource scope
    IAM->>API: Cho phép hoặc từ chối thao tác
~~~

Các bước cần phân biệt:

1. **CI identity token:** CI platform phát JWT đại diện cho job/workflow/service connection.
2. **Federation trust:** cloud xác minh token có issuer được tin cậy, audience đúng và subject/claims khớp.
3. **Cloud credential:** AWS cấp temporary credentials qua STS; Microsoft Entra cấp access token; Google Cloud STS cấp federated token, có thể impersonate service account.
4. **Authorization:** IAM/RBAC kiểm tra principal được làm gì trên resource nào.

Token OIDC của CI không phải token truy cập trực tiếp vào mọi dịch vụ cloud. Nó là bằng chứng để cloud cấp credential theo trust đã cấu hình.

## 4. Bốn trường OIDC cần hiểu

| Trường | Ý nghĩa | Ví dụ |
|---|---|---|
| Issuer (iss) | Nền tảng phát hành token | https://token.actions.githubusercontent.com |
| Audience (aud) | Token được phát hành để dùng với đối tượng nhận nào | sts.amazonaws.com, api://AzureADTokenExchange |
| Subject (sub) | Workflow/repository/branch/environment/service connection đang yêu cầu quyền | repo:org/repo:ref:refs/heads/main |
| Claims | Metadata khác dùng để giới hạn trust | repository_id, repository_owner_id, ref, environment, project_id |

Cloud provider xác minh chữ ký bằng khóa công khai của issuer và kiểm tra các trường theo cấu hình. Không tự giải mã JWT rồi tin các giá trị claim mà không xác minh chữ ký, issuer, audience và thời hạn.

### 4.1. Audience phải khớp chính xác

Audience ngăn token được phát hành cho một dịch vụ bị dùng ở dịch vụ khác. Ví dụ:

- GitHub Actions với AWS official credentials action thường dùng sts.amazonaws.com.
- GitHub Actions với Microsoft Entra login thường dùng api://AzureADTokenExchange.
- GitHub Actions với Google Cloud Workload Identity Federation dùng audience của Workload Identity Provider theo cấu hình action.
- GitLab ID token cho Google Cloud thường đặt audience là URL GitLab instance; Google STS exchange request dùng resource name của provider làm audience.

Không sao chép audience từ ví dụ provider khác. So sánh giá trị mà CI job thực sự phát hành với audience đã đăng ký ở cloud.

### 4.2. Subject phải giới hạn đúng nguồn

Subject thường thay đổi theo trigger:

- Push branch: repository và branch.
- Tag: repository và tag.
- Pull request: repository và pull_request event.
- Job dùng GitHub Environment: repository và environment.
- Azure DevOps: service connection cụ thể.
- GitLab: project, ref type, ref và environment tùy token.

Không dùng wildcard rộng như repo:org/* hoặc điều kiện chỉ kiểm tra issuer nếu job chỉ cần deploy một repository production. Dùng subject/claims cụ thể và chỉ mở rộng khi có lý do vận hành rõ ràng.

## 5. Thiết kế trust boundary trước khi tạo federation

Trước khi tạo OIDC provider hoặc federated credential, xác định:

- Repository nào sở hữu source code.
- Branch hoặc tag nào được phép deploy.
- Environment production có approval/protection rule nào.
- Workflow nào được quyền dùng reusable workflow triển khai.
- Runner là hosted hay self-hosted; ai có thể sửa runner.
- Job nào có quyền đọc artifact hoặc secret.
- Cloud account/subscription/project đích.
- Resource và action cần cho build, push image, provision và deploy.
- Ai được tạo/sửa OIDC provider, trust policy và role assignment.

Một trust boundary tốt thường ràng buộc tối thiểu: organization/owner, repository ID, branch hoặc environment, audience và workflow được phê duyệt. Với GitHub, ưu tiên ID bất biến khi provider hỗ trợ claim đó. Với GitLab, dùng group/project ID thay cho chỉ dựa vào tên project có thể đổi.

### 5.1. Subject theo branch hay environment?

| Cách ràng buộc | Khi phù hợp | Lưu ý |
|---|---|---|
| Branch main | Chỉ branch chính được phép deploy | Branch protection phải chặn push trực tiếp và review phù hợp |
| Tag release | Chỉ tag đã phát hành được deploy | Bảo vệ quyền tạo tag và kiểm soát ai có thể sửa tag |
| GitHub Environment | Cần approval, reviewer và protection rule cho production | Subject dùng environment name thay vì branch |
| Reusable workflow | Muốn chuẩn hóa quy trình deploy ở workflow dùng chung | Có thể kiểm tra job_workflow_ref khi cloud hỗ trợ |
| GitLab environment | Tách quyền deploy theo environment | Kiểm tra environment và ref_path trong token |

Một workflow có thể dùng environment production nhưng environment đó phải có deployment branch/tag restrictions và reviewer. Chỉ đưa tên production vào subject không tự tạo approval.

## 6. Lưu ý quan trọng: GitHub immutable subject claims từ 15/07/2026

GitHub đã thay đổi định dạng mặc định của OIDC sub cho repository mới tạo sau ngày 15/07/2026; repository được rename hoặc transfer sau mốc đó cũng chuyển sang định dạng bất biến. Repository cũ giữ định dạng theo tên cho tới khi opt in. Định dạng mới chứa cả owner ID và repository ID, giúp tránh trường hợp repository/organization bị xóa rồi tên được người khác đăng ký lại.

Ví dụ subject theo tên cũ:

~~~text
repo:octo-org/octo-repo:ref:refs/heads/main
~~~

Ví dụ subject bất biến:

~~~text
repo:octo-org@123456/octo-repo@456789:ref:refs/heads/main
~~~

Với job dùng GitHub Environment, phần cuối của subject là environment:production; subject bất biến sẽ có dạng:

~~~text
repo:octo-org@123456/octo-repo@456789:environment:production
~~~

Trước khi tạo trust policy, kiểm tra token claim thực tế của repository/workflow. Không đoán subject từ tên branch hoặc copy một policy cũ. GitHub Enterprise Server không hỗ trợ immutable subject format này theo tài liệu hiện hành.

Sự thay đổi này ảnh hưởng trực tiếp tới AWS IAM trust condition, Microsoft Entra federated credential và Google Cloud attribute condition. Nếu repository chuyển định dạng subject, cập nhật trust policy có kiểm soát và xác minh pipeline trước khi xóa cấu hình cũ.

## 7. Tách identity của build, deploy và ứng dụng runtime

Một pipeline có thể thực hiện nhiều công việc nhưng không nên dùng một principal có quyền không giới hạn cho tất cả:

| Identity | Công việc | Ví dụ quyền |
|---|---|---|
| Build identity | Tải dependency, build JAR, test | Đọc artifact cache/private package nếu cần |
| Registry identity | Push image | ECR push, ACR push, Artifact Registry writer |
| Provisioner identity | Tạo/cập nhật hạ tầng | Quyền IaC trong scope riêng |
| Deployer identity | Deploy revision hoặc update service | Quyền triển khai trên compute target |
| Runtime identity | Ứng dụng đang chạy truy cập storage/messaging/database | S3 read, Blob data contributor, Pub/Sub publisher |

CI/CD deployer không cần quyền đọc tất cả dữ liệu production chỉ vì nó deploy ứng dụng. Ngược lại, Spring Boot runtime không cần quyền sửa IAM role hoặc tạo storage account.

Có thể dùng một CI identity cho một service/environment nếu quyền rất hẹp; production và non-production nên tách identity để giảm blast radius. Với hệ thống lớn, build/publish/provision/deploy có thể dùng các role riêng và pipeline chỉ assume đúng role ở stage tương ứng.

## 8. AWS: tạo OIDC provider và IAM role cho GitHub Actions

AWS Security Token Service (STS) hỗ trợ AssumeRoleWithWebIdentity. GitHub Actions phát ID token; IAM OIDC provider đại diện issuer; IAM role trust policy giới hạn subject/audience; role permissions policy xác định thao tác được phép.

### 8.1. Tạo IAM OIDC provider

Với GitHub Actions:

- Provider URL: https://token.actions.githubusercontent.com
- Audience/client ID list: sts.amazonaws.com

Tạo provider một lần trong AWS account, hoặc kiểm tra provider đã tồn tại trước khi tạo. Không tạo lại provider cho từng pipeline nếu issuer giống nhau.

### 8.2. Trust policy giới hạn repository và branch

Ví dụ dưới đây dành cho repository đang dùng subject format cũ. Chỉ workflow từ branch main của repository cụ thể được assume role:

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
          "token.actions.githubusercontent.com:sub": "repo:octo-org/octo-repo:ref:refs/heads/main"
        }
      }
    }
  ]
}
~~~

Với repository dùng immutable subject format, thay sub bằng giá trị thực tế, ví dụ:

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
          "token.actions.githubusercontent.com:sub": "repo:octo-org@123456/octo-repo@456789:ref:refs/heads/main"
        }
      }
    }
  ]
}
~~~

Không giữ cả subject cũ và mới trong cùng trust policy nếu không cần hỗ trợ giai đoạn chuyển đổi. Một subject cũ rộng có thể giữ lại lỗ hổng subject recycling sau khi repository đã chuyển sang định dạng bất biến.

Nếu job dùng GitHub Environment production, subject phải khớp environment:

~~~json
{
  "StringEquals": {
    "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
    "token.actions.githubusercontent.com:sub": "repo:octo-org@123456/octo-repo@456789:environment:production"
  }
}
~~~

Trong trường hợp đó, bảo vệ GitHub Environment bằng required reviewers và deployment branch/tag rules.

### 8.3. Permission policy tách khỏi trust policy

Trust policy chỉ trả lời "ai được assume role?". Permission policy trả lời "role được làm gì?". Ví dụ deployer chỉ push image vào một ECR repository có thể cần các action ECR push trên repository đó; role cập nhật ECS service có thêm quyền deploy liên quan.

Không cấp AdministratorAccess cho role chỉ để pipeline chạy thành công. Bắt đầu từ các API call thực tế, gán action/resource cụ thể và mở rộng sau khi có bằng chứng cần thiết. Một số thao tác ECR lấy authorization token ở scope *; quyền upload layer/put image có thể giới hạn theo repository ARN; xem policy service-specific.

### 8.4. GitHub Actions workflow cho AWS

Ví dụ workflow dùng role đã cấu hình. Thay placeholder action ref bằng full commit SHA đã được tổ chức xác minh và pin; không dùng tag mutable làm căn cứ supply-chain duy nhất.

~~~yaml
name: deploy-aws

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
      - name: Checkout
        uses: actions/checkout@VERIFIED_FULL_COMMIT_SHA

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@VERIFIED_FULL_COMMIT_SHA
        with:
          role-to-assume: arn:aws:iam::123456789012:role/orders-ci-deployer
          aws-region: ap-southeast-1
          role-session-name: orders-ci

      - name: Verify caller identity
        run: aws sts get-caller-identity

      - name: Deploy
        run: ./scripts/deploy-aws.sh
~~~

id-token: write chỉ cho phép job yêu cầu OIDC token từ GitHub; nó không cấp quyền ghi source repository. AWS role mới là nơi quyết định quyền cloud. Giữ permission ở job cần deploy, không cấp id-token: write cho mọi job trong workflow nếu không cần.

Lệnh aws sts get-caller-identity giúp xác nhận principal/session đang dùng. Không in token, secret hoặc toàn bộ credential environment.

## 9. AWS với GitLab CI/CD

GitLab CI/CD hỗ trợ id_tokens để mỗi job yêu cầu JWT có audience cụ thể. Với AWS, tạo IAM OIDC provider cho issuer của GitLab instance và trust policy giới hạn subject, audience hoặc claim phù hợp.

Ví dụ job chỉ yêu cầu token:

~~~yaml
deploy_aws:
  stage: deploy
  id_tokens:
    AWS_OIDC_TOKEN:
      aud: sts.amazonaws.com
  script:
    - ./scripts/exchange-gitlab-oidc-with-aws.sh
    - ./scripts/deploy-aws.sh
  rules:
    - if: '$CI_COMMIT_BRANCH == "main"'
~~~

Script exchange cần gọi STS AssumeRoleWithWebIdentity với token trong biến AWS_OIDC_TOKEN, role ARN và session name; sau đó export temporary credentials cho các lệnh tiếp theo. Dùng thư viện/CLI hoặc script đã được review, không echo token ra stdout.

Với GitLab.com, issuer thường là https://gitlab.com; GitLab Self-Managed dùng URL issuer của instance. Trust policy cần khớp claim thực tế của phiên bản GitLab và audience được khai báo trong id_tokens. Dùng project/group ID nếu provider hỗ trợ để tránh chỉ tin vào tên group/project có thể đổi.

GitLab đã loại bỏ CI_JOB_JWT và CI_JOB_JWT_V2 từ GitLab 17.0; dùng ID tokens. Không xây pipeline mới dựa trên biến JWT cũ.

## 10. Azure: Federated Identity Credential trong Microsoft Entra

Microsoft Entra Workload Identity Federation cho phép app registration hoặc user-assigned Managed Identity tin cậy token từ GitHub Actions, GitLab hoặc Azure DevOps. Khi GitHub job cần deploy Azure resource, Entra xác minh issuer, subject và audience của token rồi cấp access token cho service principal/Managed Identity.

Các giá trị thường dùng cho GitHub Actions:

- Issuer: https://token.actions.githubusercontent.com
- Audience: api://AzureADTokenExchange
- Subject: subject claim thực tế của repository/workflow.

### 10.1. Tạo federated credential cho GitHub Actions

Ví dụ JSON dùng subject immutable của repository và branch main:

~~~json
{
  "name": "orders-github-main",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:octo-org@123456/octo-repo@456789:ref:refs/heads/main",
  "audiences": [
    "api://AzureADTokenExchange"
  ]
}
~~~

Tạo credential trên user-assigned Managed Identity:

~~~bash
az identity federated-credential create \
  --name orders-github-main \
  --identity-name orders-ci-deployer \
  --resource-group rg-identity-prod \
  --issuer https://token.actions.githubusercontent.com \
  --subject 'repo:octo-org@123456/octo-repo@456789:ref:refs/heads/main' \
  --audiences api://AzureADTokenExchange
~~~

JSON ở trên mô tả cùng bộ giá trị issuer, subject và audiences. Với app registration, tạo federated credential trên application object bằng Microsoft Graph hoặc công cụ quản trị hỗ trợ đối tượng đó. Đảm bảo object ID truyền cho lệnh/API là application object ID; app/client ID là giá trị khác.

Đối với repository còn dùng subject cũ, subject có thể là repo:octo-org/octo-repo:ref:refs/heads/main. Với job dùng GitHub Environment, subject kết thúc bằng environment:production. Phải kiểm tra token claim thực tế trước khi tạo credential.

### 10.2. Flexible federated identity credentials

Microsoft Entra có Flexible Federated Identity Credentials (hiện được tài liệu đánh dấu Preview) cho phép dùng biểu thức match và một số immutable claims bổ sung. Với GitHub, điều kiện cần match sub và repository_id hoặc repository_owner_id; có thể thêm job_workflow_ref để ràng buộc reusable workflow.

Ví dụ biểu thức minh họa:

~~~text
claims['sub'] matches 'repo:octo-org@123456/octo-repo@456789:ref:refs/heads/*'
and claims['repository_id'] eq '456789'
and claims['repository_owner_id'] eq '123456'
~~~

Biểu thức trên dành cho repository đang phát immutable subject. Repository cũ chưa opt in có subject theo tên; thay phần sub bằng đúng token thực tế. Tính năng này đang ở trạng thái Preview và khả năng quản lý phụ thuộc loại identity, API và phiên bản công cụ. Trước khi dùng, kiểm tra tài liệu hiện hành cho đúng đối tượng (app registration hay user-assigned Managed Identity) và xác minh thao tác create/read/update đều được hỗ trợ. Không giả định mọi phiên bản Azure CLI, PowerShell hoặc Terraform provider đều hiểu claimsMatchingExpression. Với cấu hình cơ bản, federated credential exact-match issuer, subject, audiences dễ kiểm soát hơn.

### 10.3. Gán Azure RBAC cho deployer

Sau khi federation hoạt động, gán role cho Managed Identity hoặc service principal ở scope cần triển khai. Ví dụ nếu pipeline chỉ upload container image vào Azure Container Registry, cấp AcrPush ở đúng registry; nếu triển khai App Service, dùng role triển khai thích hợp ở scope app/resource group.

Role Contributor ở subscription thường quá rộng cho pipeline của một ứng dụng. Tách:
- Quyền quản lý resource group và IaC.
- Quyền push image vào registry.
- Quyền deploy application revision.
- Quyền tạo role assignment, vốn nhạy cảm và nên thuộc một pipeline/platform identity riêng.

Federated credential chỉ xác minh pipeline; nó không tự cấp Azure RBAC permission.

### 10.4. GitHub Actions workflow cho Azure

Ví dụ dùng Azure Login action. Pin action bằng full commit SHA đã xác minh:

~~~yaml
name: deploy-azure

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
      - name: Checkout
        uses: actions/checkout@VERIFIED_FULL_COMMIT_SHA

      - name: Azure login with OIDC
        uses: azure/login@VERIFIED_FULL_COMMIT_SHA
        with:
          client-id: ${{ vars.AZURE_CLIENT_ID }}
          tenant-id: ${{ vars.AZURE_TENANT_ID }}
          subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}

      - name: Verify identity
        run: az account show

      - name: Deploy
        run: ./scripts/deploy-azure.sh
~~~

Client ID, tenant ID và subscription ID là định danh cấu hình, không phải secret. Credential được cấp sau OIDC exchange. Không tạo AZURE_CLIENT_SECRET chỉ để làm Azure Login khi federation đã được cấu hình.

Nếu dùng user-assigned Managed Identity, client ID phải thuộc đúng identity có federated credential. Gán role assignment cho identity đó ở scope resource cần thiết.

## 11. Azure DevOps: Workload Identity Federation service connection

Azure DevOps dùng service connection để pipeline nhận token và xác thực với Microsoft Entra. Khi tạo Azure Resource Manager service connection, chọn credential type Workload identity federation thay vì secret hoặc certificate.

Issuer và subject phụ thuộc loại service connection và thời điểm tạo. Tài liệu Azure DevOps hiện phân biệt:

| Kiểu service connection | Issuer | Subject |
|---|---|---|
| Kiểu cũ | https://vstoken.dev.azure.com/<organization-id> | sc://<organization>/<project>/<service-connection> |
| Service connection mới | https://login.microsoftonline.com/<tenant-id>/v2.0 | <prefix>/sc/<organization-id>/<service-connection-id> |

Không tự ghép các trường này từ tên organization. Lấy issuer và subject identifier trực tiếp từ trang Workload Identity federation details của service connection và dùng đúng cặp đó trong federated credential.

Các lưu ý vận hành:

- Tạo service connection riêng cho từng ứng dụng và environment.
- Giới hạn service connection ở subscription/resource group cần thiết.
- Bật approval/check trên chính service connection nếu chính sách tổ chức yêu cầu.
- Kiểm tra pipeline task/extension đang dùng có hỗ trợ workload identity federation.
- Nếu token exchange báo không tìm thấy federated identity, kiểm tra issuer và subject khớp chính xác.
- Giảm quyền subscription mặc định mà wizard có thể cấp; gán role hẹp hơn sau khi tạo.

## 12. Google Cloud: Workload Identity Federation cho CI/CD

Google Cloud Workload Identity Federation (WIF) tạo trust với external OIDC provider. Workload Pool chứa provider; provider xác minh issuer và claims; attribute mapping biến claim thành Google principal/attributes; attribute condition giới hạn nguồn token.

Có thể cấp quyền theo hai cách:

- **Direct resource access:** gán IAM role trực tiếp cho federated principal/principalSet trên resource.
- **Service account impersonation:** cấp roles/iam.workloadIdentityUser cho federated principal trên một service account; service account nhận role trên resource đích.

Google khuyến nghị direct resource access khi API hỗ trợ. Service account impersonation hữu ích khi công cụ/action hoặc API cần service account identity.

### 12.1. Tạo Workload Identity Pool

Ví dụ tạo pool dành cho GitHub Actions:

~~~bash
gcloud iam workload-identity-pools create github-ci \
  --location=global \
  --display-name="GitHub Actions CI" \
  --description="Federated identities for approved deployment workflows"
~~~

Pool ID là định danh ổn định xuất hiện trong principal URI. Nên quản lý pool/provider trong project nền tảng hoặc project identity riêng, không phân tán provider tùy tiện trên nhiều project.

### 12.2. Tạo OIDC provider với attribute mapping và condition

Ví dụ mapping claim GitHub:

~~~bash
gcloud iam workload-identity-pools providers create-oidc github \
  --location=global \
  --workload-identity-pool=github-ci \
  --display-name="GitHub Actions" \
  --issuer-uri="https://token.actions.githubusercontent.com/" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository_id=assertion.repository_id,attribute.repository_owner_id=assertion.repository_owner_id,attribute.ref=assertion.ref" \
  --attribute-condition="assertion.repository_owner_id=='123456' && assertion.repository_id=='456789' && assertion.ref=='refs/heads/main'"
~~~

Thay ID bằng giá trị thực tế trong token. Attribute condition chỉ cho phép repository/owner/branch được chỉ định. GitHub, GitLab SaaS và HCP Terraform dùng issuer chung cho nhiều tenant; chỉ kiểm tra issuer là không đủ. Google khuyến nghị attribute condition để giới hạn organization/group/workspace đáng tin cậy.

Không dùng repository hoặc repository_owner dạng tên nếu có thể dùng repository_id và repository_owner_id bất biến. Mỗi attribute được dùng trong condition phải có mapping tương ứng. google.subject phải định danh duy nhất một workload.

### 12.3. Cho phép federated principal impersonate service account

Ví dụ cấp Workload Identity User cho đúng repository ID:

~~~bash
gcloud iam service-accounts add-iam-policy-binding \
  orders-ci-deployer@PROJECT_ID.iam.gserviceaccount.com \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github-ci/attribute.repository_id/456789"
~~~

PROJECT_NUMBER là project number chứa Workload Identity Pool, không phải project ID. Role roles/iam.workloadIdentityUser cho phép principal federation impersonate service account; nó không cấp quyền deploy resource. Gán role deploy riêng cho service account trên Artifact Registry, Cloud Run, GKE hoặc resource cần cập nhật.

Nếu dùng direct resource access, bỏ bước impersonation và gán role trực tiếp cho principalSet trên resource hỗ trợ IAM allow policy. Không cấp cả hai mô hình nếu không có lý do rõ ràng.

### 12.4. GitHub Actions workflow cho Google Cloud

Ví dụ dùng service account impersonation:

~~~yaml
name: deploy-gcp

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
      - name: Checkout
        uses: actions/checkout@VERIFIED_FULL_COMMIT_SHA

      - name: Authenticate to Google Cloud
        uses: google-github-actions/auth@VERIFIED_FULL_COMMIT_SHA
        with:
          workload_identity_provider: projects/123456789/locations/global/workloadIdentityPools/github-ci/providers/github
          service_account: orders-ci-deployer@PROJECT_ID.iam.gserviceaccount.com

      - name: Set up gcloud
        uses: google-github-actions/setup-gcloud@VERIFIED_FULL_COMMIT_SHA

      - name: Verify identity
        run: gcloud auth list

      - name: Deploy
        run: ./scripts/deploy-gcp.sh
~~~

Giá trị workload_identity_provider dùng project number và provider ID. Action yêu cầu job có id-token: write; service account cần policy binding roles/iam.workloadIdentityUser cho federated principal. Nếu dùng direct resource access, cấu hình auth action theo hướng dẫn direct federation và cấp IAM role trực tiếp cho principal.

## 13. GitLab CI/CD với Google Cloud WIF

GitLab ID tokens cho phép mỗi job khai báo audience. Với GitLab.com, issuer là https://gitlab.com; với self-managed, dùng URL của GitLab instance. Google Cloud cần provider mapping và condition giới hạn group/project.

Ví dụ mapping cho GitLab:

~~~text
google.subject=assertion.sub
attribute.namespace_id=assertion.namespace_id
attribute.project_id=assertion.project_id
attribute.ref_path=assertion.ref_path
attribute.environment=assertion.environment
~~~

Condition có thể giới hạn project và branch:

~~~text
assertion.namespace_id=='123456'
&& assertion.project_id=='987654'
&& assertion.ref_path=='refs/heads/main'
~~~

Ví dụ GitLab job khai báo ID token:

~~~yaml
deploy_gcp:
  stage: deploy
  id_tokens:
    GCP_OIDC_TOKEN:
      aud: https://gitlab.com
  script:
    - ./scripts/deploy-gcp-with-wif.sh
  rules:
    - if: '$CI_COMMIT_BRANCH == "main"'
~~~

Token được cấp theo job; script đổi token qua Google STS và có thể impersonate service account. Không dùng biến CI_JOB_JWT_V2; GitLab đã loại bỏ biến này từ phiên bản 17.0. Dùng id_tokens và audience khớp provider configuration.

### 13.1. Vì sao phải dùng group/project ID?

GitLab SaaS dùng issuer chung cho nhiều group. Nếu chỉ kiểm tra iss=https://gitlab.com và subject dạng tên project, một project khác có thể tạo claim cùng cấu trúc tên sau khi namespace được tái sử dụng. Dùng namespace_id và project_id giúp ràng buộc danh tính vào ID ổn định hơn.

## 14. Azure DevOps dùng Google Cloud WIF

Azure DevOps có thể phát ID token từ Azure Resource Manager workload identity service connection. Khi cấu hình Google provider:

- Lấy issuer và subject identifier từ service connection.
- Với Azure DevOps service connection, Google docs khuyến nghị mapping google.subject từ phần subject sau /sc/ nếu subject tổng dài hơn giới hạn 127 ký tự.
- Map oid hoặc claim định danh service connection/application để tạo attribute condition.
- Gán quyền cho đúng principal/subject, không cấp theo toàn bộ pool.

Ví dụ mapping theo hướng dẫn Google Cloud:

~~~text
google.subject=assertion.sub.split('/sc/')[1]
~~~

Condition nên kiểm tra object ID của Azure DevOps application/service principal theo claim phù hợp:

~~~text
assertion.oid=='APPLICATION_OBJECT_ID'
~~~

Với provider Azure DevOps, audience cho connection mới theo tài liệu Google là fixed application ID của Azure Token Exchange Endpoint. Không sử dụng audience GitHub hoặc GitLab cho service connection này.

Azure DevOps có thể tự cấp role trên Azure subscription khi tạo service connection. Nếu mục tiêu là Google Cloud, bỏ hoặc giảm role assignment Azure mặc định sau khi xác nhận service connection không cần truy cập Azure resource.

## 15. Quyền CI/CD theo từng cloud

| Provider | Identity federation | Credential sau exchange | Quyền deploy |
|---|---|---|---|
| AWS | IAM OIDC provider + role trust policy | STS temporary access key/session token | IAM permission policy trên AWS resource |
| Azure | Microsoft Entra federated identity credential | Entra access token | Azure RBAC role trên subscription/resource group/resource |
| Google Cloud | Workload Identity Pool + OIDC provider | Federated token hoặc impersonated service account credentials | IAM role trên resource hoặc service account |

Không nhầm:
- AWS role trust policy với AWS permission policy.
- Entra federated credential với Azure RBAC role assignment.
- Google WIF provider condition với IAM role binding.
- roles/iam.workloadIdentityUser với quyền deploy thực tế.

Mỗi provider tách authentication và authorization theo cách riêng; pipeline phải hoàn thành cả hai.

## 16. Phân quyền pipeline theo stage

Một pipeline có thể tách role theo giai đoạn:

| Stage | Quyền cần | Không cần |
|---|---|---|
| Test | Đọc dependency, chạy unit/integration test | Quyền cloud production |
| Build image | Đọc source và dependency, build container | Quyền sửa IAM |
| Push image | Push vào một registry/repository | Quyền xóa subscription/project |
| IaC plan | Đọc state và mô phỏng thay đổi | Quyền runtime đọc dữ liệu production |
| IaC apply | Tạo/cập nhật resource trong scope được giao | Owner/Administrator toàn account |
| Deploy | Cập nhật service/revision | Quyền đọc mọi secret |
| Smoke test | Gọi endpoint/health check, thao tác test tối thiểu | Quyền quản trị resource |

Nếu IaC cần tạo role assignment, tách stage đó khỏi deploy ứng dụng hoặc dùng permission elevation có approval. Quyền iam:PassRole, Microsoft.Authorization/roleAssignments/write, resourcemanager.projects.setIamPolicy và các quyền IAM tương đương có thể cho phép pipeline mở rộng quyền đáng kể; chỉ cấp khi thật sự cần.

### 16.1. Tách production và non-production

Tạo trust/role riêng cho:
- Dev/test.
- Staging.
- Production.

Production role chỉ tin cậy branch/tag/environment được bảo vệ. Không dùng role production cho pull request từ fork. Không cho phép job có thể sửa workflow tùy ý nhưng vẫn nhận được token production.

## 17. Quản lý token, credential và file tạm trong runner

OIDC token và credential sau exchange vẫn là dữ liệu nhạy cảm, dù thời hạn ngắn.

- Không echo JWT, access token, temporary secret key hoặc credential file.
- Không bật shell trace trong đoạn xử lý token.
- Không upload token/credential file vào artifact hoặc cache.
- Xóa file credential tạm sau job nếu action/tool không tự dọn.
- Không truyền token qua output giữa job nếu job sau có thể tự xin token riêng.
- Hạn chế GITHUB_TOKEN permission; OIDC id-token: write chỉ cấp ở job cần.
- Trên self-hosted runner, làm sạch workspace và credential cache giữa các job.
- Không chạy job không tin cậy trên runner có quyền truy cập metadata hoặc network nội bộ production.
- Dùng thời hạn role session phù hợp với thời gian deploy; không đặt session duration tối đa chỉ để tránh refresh.

Credential ngắn hạn giảm thời gian lạm dụng sau leak nhưng không loại bỏ rủi ro trong lúc job đang chạy. Runner bị xâm nhập có thể dùng token hiện tại trước khi hết hạn.

## 18. Bảo vệ workflow khỏi pull request và dependency độc hại

Kẻ tấn công có thể sửa workflow, script build hoặc dependency để lấy quyền cloud của pipeline. Cần kiểm soát cả nguồn code lẫn quyền OIDC.

- Không cấp OIDC production cho pull_request từ fork.
- Tách workflow kiểm thử pull request khỏi workflow deploy.
- Dùng protected branch và required review.
- Dùng GitHub Environment với required reviewers và branch restrictions.
- Pin third-party action bằng full commit SHA đã xác minh.
- Kiểm tra action có thực sự cần id-token: write không.
- Với reusable workflow, ràng buộc job_workflow_ref khi cloud provider hỗ trợ.
- Hạn chế workflow_dispatch và workflow_call từ nguồn không tin cậy.
- Kiểm tra script deploy và dependency lockfile trước khi cấp quyền production.
- Với GitLab, bảo vệ protected branches/environments và giới hạn ai có quyền chạy protected job.
- Với Azure DevOps, bảo vệ service connection bằng approvals/checks và governed pipeline templates.

Không cấp OIDC permission ở workflow top-level nếu chỉ một deploy job cần. Job build/test không nên có khả năng lấy token cloud production.

## 19. GitHub Actions Environment và reusable workflow

Nếu trust policy dùng environment subject, workflow cần khai báo environment đúng tên:

~~~yaml
jobs:
  deploy:
    environment: production
    permissions:
      contents: read
      id-token: write
~~~

GitHub Environment có thể yêu cầu reviewer, giới hạn branch/tag và bảo vệ secrets. Subject sẽ chứa environment name; trust policy phải dùng đúng tên, kể cả chữ hoa/chữ thường.

Với reusable workflow, claim job_workflow_ref có thể xác định workflow dùng chung đang thực thi. Điều này giúp organization tập trung logic deploy ở một repository được quản trị. Tuy nhiên, reusable workflow cần được pin version/commit và cloud trust phải khớp đúng claim mà GitHub phát hành.

Không giả định việc gọi reusable workflow tự tạo security boundary. Repository gọi workflow vẫn phải được tin cậy và quyền OIDC phải cấp đúng job.

## 20. Azure DevOps service connection approvals và governed pipelines

Azure DevOps service connection là trust boundary riêng. Nếu user có thể sửa pipeline YAML và sử dụng service connection production không qua kiểm soát, OIDC chỉ loại bỏ secret dài hạn chứ không ngăn họ deploy.

Nên:
- Tạo service connection riêng theo ứng dụng và environment.
- Bật approval/check trên service connection production.
- Giới hạn service connection chỉ cho pipeline cần thiết.
- Dùng branch policy và required reviewers cho pipeline template.
- Dùng governed pipeline template để ngăn job tự ý thêm thao tác quản trị.
- Không để service connection production được dùng bởi mọi project.
- Kiểm tra task/extension có hỗ trợ workload identity federation.

Azure DevOps có các task phiên bản cũ chưa hỗ trợ WIF. Nếu lỗi token acquisition, kiểm tra compatibility task và phiên bản Azure CLI trước khi sửa federated credential.

## 21. GitLab protected environments và token audience

GitLab job có thể chỉ phát ID token cho một audience cụ thể. Hãy đặt aud đúng với cloud provider và dùng protected branch/environment cho deploy job.

Ví dụ điều kiện pipeline:

~~~yaml
deploy_production:
  stage: deploy
  environment:
    name: production
  rules:
    - if: '$CI_COMMIT_BRANCH == "main"'
      when: manual
    - when: never
  id_tokens:
    CLOUD_OIDC_TOKEN:
      aud: https://gitlab.com
  script:
    - ./scripts/deploy-production.sh
~~~

Đối chiếu claim token thực tế với trust condition. GitLab sub có thể bao gồm project path, ref type và ref; dùng project ID/namespace ID nếu provider hỗ trợ. Không tin tất cả token từ cùng GitLab issuer.

## 22. Kiểm thử OIDC federation trước production

Kiểm thử phải chứng minh đúng workload được nhận identity và workload ngoài phạm vi bị từ chối.

| Kịch bản | Cách kiểm thử | Kết quả mong đợi |
|---|---|---|
| Đúng repository, branch | Chạy workflow từ branch được phép | Token exchange thành công |
| Sai repository | Chạy từ repository khác trong cùng org | Trust condition từ chối |
| Sai owner/group | Chạy từ organization/group khác | Provider condition từ chối |
| Sai branch | Chạy từ feature branch | Không assume được production role |
| Sai environment | Dùng environment name khác | Subject không khớp |
| Sai audience | Yêu cầu token với audience khác | Cloud từ chối exchange |
| Subject cũ/mới | Kiểm tra token sau khi opt in immutable subject | Trust policy khớp định dạng mới |
| Pull request từ fork | Chạy workflow test không có quyền deploy | Không lấy được cloud role |
| Thiếu IAM permission | Trust thành công nhưng role thiếu action | Cloud API trả AccessDenied/403 |
| Token hết hạn | Dùng token đã hết hạn trong test | Exchange thất bại |
| Credential refresh | Job chạy lâu hơn credential lifetime | Tool/SDK lấy credential mới hoặc fail rõ |
| Runner bị tái sử dụng | Chạy job kế tiếp trên self-hosted runner | Không còn credential/file từ job trước |
| Azure DevOps issuer sai | Thử service connection metadata cũ/mới | Federation không tìm thấy credential |
| Google WIF claim mapping sai | Xóa mapping hoặc condition attribute | STS từ chối token |
| GCP service account binding thiếu | Federation thành công nhưng thiếu workloadIdentityUser | Không impersonate được service account |

Dùng account/subscription/project test và resource không chứa dữ liệu production. Không thực hiện negative test bằng cách thu hồi role của workload production đang phục vụ.

### 22.1. Xác minh principal thực tế

- AWS: aws sts get-caller-identity cho biết ARN/session đang dùng.
- Azure: az account show xác minh tenant/subscription context; xem service principal/Managed Identity đã đăng nhập.
- Google Cloud: gcloud auth list và gcloud config list kiểm tra account/project context; audit log cho biết principal đã gọi API.

Không in raw JWT hoặc access token để xác minh. Kiểm tra principal và audit log là đủ cho phần lớn tình huống.

## 23. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| GitHub job không lấy được ID token | Thiếu id-token: write ở job | Cấp permission đúng job |
| AWS Not authorized to perform sts:AssumeRoleWithWebIdentity | Issuer/audience/subject sai hoặc role trust thiếu điều kiện phù hợp | So khớp OIDC provider ARN, aud và sub |
| AWS AccessDenied sau khi assume role | Permission policy thiếu action/resource | Kiểm tra role policy và resource policy |
| AWS trust policy đột nhiên fail sau rename | GitHub subject đã chuyển sang immutable format | Cập nhật sub theo token mới |
| Azure không tìm thấy federated identity | Issuer, subject hoặc audience không khớp | Lấy metadata/token claim thực tế và so sánh từng trường |
| Azure login thành công nhưng deploy 403 | Service principal/Managed Identity thiếu Azure RBAC | Gán role đúng scope |
| Azure DevOps task không hỗ trợ WIF | Task/extension phiên bản cũ | Nâng task hoặc dùng task có hỗ trợ |
| Google STS invalid_target/audience error | Provider audience không khớp | Kiểm tra audience của ID token và provider |
| Google invalid_grant | Issuer, signature, subject hoặc attribute condition sai | Kiểm tra issuer URL, clock, claims và CEL condition |
| Google impersonation bị từ chối | Thiếu roles/iam.workloadIdentityUser trên service account | Gán role cho principalSet/subject chính xác |
| Google deploy 403 | Service account/federated principal thiếu role resource | Cấp IAM role deploy trên resource |
| GitLab job không có token | Chưa khai báo id_tokens hoặc sai audience | Thêm token declaration và đúng aud |
| Credential file còn trên self-hosted runner | Cleanup không hoàn tất hoặc workspace dùng chung | Xóa workspace/cache và cô lập runner |
| Pipeline có quyền rộng bất thường | Role được gán ở scope account/project/subscription quá lớn | Thu hẹp scope và tách identity theo stage |

Không khắc phục lỗi trust bằng cách thay sub thành wildcard cho mọi repository. Xác định claim thực tế rồi sửa điều kiện tối thiểu cần thiết.

## 24. Chuyển đổi từ static credential sang OIDC

Có thể chuyển theo từng service và environment:

1. Liệt kê credential dài hạn hiện đang dùng trong CI variables, variable groups, secret store, runner và deployment scripts.
2. Xác định pipeline nào thực sự cần cloud access và thao tác cụ thể của từng pipeline.
3. Tạo OIDC provider/federated credential ở cloud.
4. Tạo deployer role/service principal/service account riêng cho ứng dụng và environment.
5. Gán IAM/RBAC permission tối thiểu.
6. Thêm OIDC permission và login step vào một pipeline staging.
7. Xác minh principal thực tế và chạy deploy/smoke test.
8. Chuyển production qua environment/service connection có approval.
9. Xác minh không còn lệnh đọc static credential trong workflow.
10. Thu hồi khóa cũ, xóa CI variables và secret mounts không còn dùng; rotate ngay nếu nghi ngờ khóa từng bị lộ.
11. Kiểm tra log/audit sau chuyển đổi để phát hiện principal hoặc key cũ vẫn được sử dụng.

Không xóa credential cũ trước khi xác minh pipeline mới chạy ổn. Nhưng cần đặt thời hạn kết thúc chuyển đổi để tránh duy trì song song hai đường xác thực vô thời hạn.

## 25. Mô hình release đề xuất cho Spring Boot đa cloud

Một release pipeline có thể được tổ chức như sau:

~~~mermaid
flowchart TD
    SRC["Protected source branch / release tag"] --> TEST["Build and test"]
    TEST --> IMAGE["Build OCI image"]
    IMAGE --> SCAN["Scan and publish image"]
    SCAN --> OIDC["Request CI OIDC token"]
    OIDC --> FED["Exchange token with AWS / Entra / Google STS"]
    FED --> DEPLOYER["Obtain short-lived deployer credential"]
    DEPLOYER --> INFRA["Provision or update infrastructure"]
    INFRA --> DEPLOY["Deploy Spring Boot revision"]
    DEPLOY --> SMOKE["Smoke test and verify principal"]
    SMOKE --> APPROVE["Production environment approval"]
    APPROVE --> TRAFFIC["Promote / enable traffic"]
~~~

Các điểm kiểm soát:

- Build artifact một lần rồi promote cùng image digest qua môi trường.
- OIDC token chỉ được yêu cầu trong deploy job.
- Deployer identity chỉ có quyền triển khai resource/service được giao.
- Workload identity của Spring Boot được cấu hình độc lập trong compute platform.
- Runtime secret được đọc từ secret manager bằng workload identity, không chuyển qua CI job.
- IaC provisioner có quyền riêng nếu cần tạo resource hoặc role assignment.
- Production deploy cần approval/protection phù hợp.

## 26. Checklist trước production

- **Issuer:** Đã đăng ký đúng issuer URL của CI platform.
- **Audience:** Khớp chính xác audience mà job phát hành.
- **Subject:** Ràng buộc đúng repository, branch, environment hoặc service connection.
- **Immutable claims:** Đã kiểm tra GitHub subject format hiện tại; dùng repository/owner ID khi provider hỗ trợ.
- **Attribute condition:** Google/GitLab/Azure provider đã giới hạn tenant, group, project và branch.
- **Trust policy:** Không dùng wildcard rộng hoặc chỉ kiểm tra issuer.
- **Role permissions:** Chỉ cấp action cần thiết trên resource/scope cụ thể.
- **Identity separation:** Tách build, provisioner, deployer và runtime identity.
- **GitHub:** id-token: write chỉ ở job cần; action pin full commit SHA; environment có protection rules.
- **GitLab:** Dùng id_tokens, không dùng JWT variable đã deprecated/removed; protected branch/environment được cấu hình.
- **Azure DevOps:** Service connection dùng workload identity federation; issuer/subject lấy từ metadata thực tế; có approval/check.
- **AWS:** OIDC provider, aud, sub, trust policy và permission policy đã được kiểm thử.
- **Azure:** Federated credential và Azure RBAC được kiểm tra riêng.
- **Google Cloud:** Workload Identity Pool/Provider mapping, attribute condition và service account binding đã được kiểm tra.
- **Token handling:** Không log JWT, access token hoặc credential file; có cleanup.
- **Runner:** Self-hosted runner được cô lập và làm sạch giữa các job.
- **Pull request:** Workflow từ fork/untrusted branch không nhận token production.
- **Audit:** Có thể truy vết role session/principal và deployment run.
- **Migration:** Static key cũ đã có kế hoạch thu hồi và xóa khỏi CI.
- **Recovery:** Có thể thu hồi federated credential/role association khi pipeline hoặc repository bị xâm nhập.

## 27. Tổng kết

OIDC workload identity federation cho phép CI/CD pipeline xác thực với cloud bằng token ngắn hạn do GitHub Actions, GitLab hoặc Azure DevOps phát hành. AWS xác minh token qua IAM OIDC provider và cấp STS temporary credentials; Microsoft Entra dùng federated identity credential để cấp access token; Google Cloud dùng Workload Identity Pool/Provider và STS để cấp federated credential hoặc impersonate service account.

Việc thay khóa dài hạn chỉ là một phần của bảo mật. Trust policy phải giới hạn issuer, audience, repository, owner, branch, environment hoặc service connection; IAM/RBAC phải cấp đúng quyền triển khai; workflow và runner phải được bảo vệ khỏi code không tin cậy. Tách deployer identity khỏi workload identity giúp Spring Boot chạy với quyền dữ liệu tối thiểu, trong khi pipeline chỉ có quyền phát hành phiên bản mới. Khi có negative test, audit log và quy trình thu hồi credential cũ, việc triển khai ứng dụng đa cloud trở nên dễ kiểm soát và kiểm toán hơn.

## Tài liệu tham khảo

- [GitHub Actions OpenID Connect reference](https://docs.github.com/en/actions/reference/security/oidc)
- [Configuring OpenID Connect in Amazon Web Services](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws)
- [AWS IAM OIDC provider and role trust policy for GitHub Actions](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers_create_oidc.html)
- [AWS STS AssumeRoleWithWebIdentity](https://docs.aws.amazon.com/STS/latest/APIReference/API_AssumeRoleWithWebIdentity.html)
- [Microsoft Entra federated identity credentials](https://learn.microsoft.com/en-us/entra/workload-id/workload-identity-federation)
- [Azure CLI: az identity federated-credential](https://learn.microsoft.com/en-us/cli/azure/identity/federated-credential)
- [Flexible federated identity credentials](https://learn.microsoft.com/en-us/entra/workload-id/workload-identities-flexible-federated-identity-credentials)
- [Migrate GitHub Actions federated credentials to immutable subjects](https://learn.microsoft.com/en-us/entra/workload-id/workload-identities-github-immutable-subjects)
- [Azure DevOps workload identity federation troubleshooting](https://learn.microsoft.com/en-us/azure/devops/pipelines/release/troubleshoot-workload-identity)
- [Google Cloud Workload Identity Federation with deployment pipelines](https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines)
- [Google Cloud Workload Identity Federation best practices](https://docs.cloud.google.com/iam/docs/best-practices-for-using-workload-identity-federation)
- [GitLab CI/CD: Connect to cloud services](https://docs.gitlab.com/ci/cloud_services/)
- [GitLab CI/CD: Configure OpenID Connect with Google Cloud](https://docs.gitlab.com/ci/cloud_services/google_cloud/)

