# Xác thực pipeline với cloud bằng OIDC federation

Pipeline CI/CD cần quyền truy cập cloud để triển khai function, cập nhật cấu hình, phát hành version hoặc thay đổi hạ tầng. Cách truyền thống thường lưu access key, service principal secret hoặc service account key trong secret store của CI. Những credential dài hạn này có thể bị lộ qua log, workflow bị xâm nhập, artifact hoặc cấu hình sai; chúng cũng cần được rotation và thu hồi.

**OpenID Connect (OIDC) federation** cho phép pipeline chứng minh danh tính của job với cloud identity provider rồi đổi token đó lấy credential ngắn hạn. Cloud chỉ cấp quyền khi token được ký bởi issuer đã tin cậy và các claim như audience, subject, repository, branch hoặc environment thỏa điều kiện trust policy. Pipeline không cần lưu private key hoặc client secret dài hạn để đăng nhập cloud.

Trong Java serverless, pipeline có thể dùng OIDC để deploy ZIP/JAR lên AWS Lambda, Azure Functions hoặc Google Cloud Functions/Run. OIDC chỉ giải quyết xác thực workload; IAM/RBAC vẫn quyết định pipeline được cập nhật function nào, tạo tài nguyên nào và có thể truy cập dữ liệu gì. Một token hợp lệ không đồng nghĩa pipeline được quyền triển khai toàn bộ account hoặc subscription.

## 1. Vấn đề của credential dài hạn trong CI/CD

Một pipeline thường chạy tự động trên runner dùng chung hoặc runner được tạo mới cho mỗi job. Nếu lưu access key dài hạn trong repository secret, bất kỳ workflow nào có thể đọc secret cũng trở thành một con đường để lấy credential đó.

Các rủi ro thường gặp:

- Secret bị ghi ra log do bật debug hoặc dùng shell không an toàn.
- Workflow từ pull request không tin cậy chạy được bước có quyền đọc secret.
- Action bên thứ ba bị xâm nhập và lấy credential từ environment.
- Credential bị sao chép vào file, cache, artifact hoặc runner không được dọn sạch.
- Secret không được rotation đúng hạn hoặc vẫn còn hiệu lực sau khi người phụ trách rời nhóm.
- Một key dùng chung cho nhiều repository khiến khó xác định nguồn phát sinh hành động.
- Key có quyền quá rộng, làm tăng phạm vi ảnh hưởng khi bị lộ.

OIDC thay đổi mô hình này. Thay vì pipeline giữ một secret dùng lâu dài, CI provider phát hành một identity token có thời hạn ngắn cho đúng job. Cloud xác minh token và cấp credential tạm thời theo role hoặc identity đã cấu hình.

| Credential dài hạn | OIDC federation |
|---|---|
| Secret/key được lưu trong CI | Job yêu cầu token từ issuer đã tin cậy |
| Có thể tồn tại nhiều tháng hoặc nhiều năm | Token và credential trao đổi có thời hạn ngắn |
| Phải rotation và thu hồi thủ công | Mỗi job nhận token mới; thu hồi bằng trust policy hoặc quyền cloud |
| Khó ràng buộc key với branch/job cụ thể | Có thể ràng buộc repository, branch, workflow hoặc environment |
| Một key có thể bị dùng ngoài pipeline | Token gắn với issuer, audience, subject và thời điểm phát hành |

OIDC không loại bỏ mọi secret. Pipeline vẫn có thể cần secret để truy cập registry, ký artifact hoặc gọi dịch vụ không hỗ trợ federation. Mục tiêu là loại bỏ credential dài hạn cho việc xác thực vào cloud khi cloud provider và CI provider hỗ trợ OIDC.

## 2. OIDC federation hoạt động như thế nào?

OIDC là lớp định danh xây trên OAuth 2.0. CI provider đóng vai trò OpenID Provider (issuer), phát hành JSON Web Token (JWT) mô tả danh tính của job. Cloud provider đóng vai trò relying party, xác minh token và trao đổi nó lấy credential dùng cho API của cloud.

Luồng khái niệm:

~~~mermaid
sequenceDiagram
    participant J as CI job
    participant I as OIDC issuer của CI
    participant C as Cloud STS / identity service
    participant R as Cloud resource API
    J->>I: Yêu cầu ID token cho audience
    I-->>J: JWT có iss, aud, sub và claims
    J->>C: Gửi JWT để federation / token exchange
    C->>C: Kiểm tra chữ ký, issuer, audience, expiry và trust conditions
    C-->>J: Credential cloud ngắn hạn
    J->>R: Gọi API bằng credential tạm thời
    R->>R: Kiểm tra IAM / RBAC permissions
    R-->>J: Kết quả thao tác
~~~

Các bước:

1. Job chạy trong CI provider với một identity cụ thể, ví dụ repository org/orders-api, branch main và environment production.
2. Workflow yêu cầu CI provider phát hành OIDC ID token.
3. Issuer ký JWT bằng khóa riêng; public key được công bố qua JWKS endpoint.
4. Job gửi token tới dịch vụ federation của cloud.
5. Cloud xác minh issuer, chữ ký, thời hạn, audience và các claim mà trust policy yêu cầu.
6. Nếu điều kiện hợp lệ, cloud cấp credential ngắn hạn hoặc cho phép impersonate một role/service identity.
7. Job dùng credential đó gọi API triển khai.
8. Cloud tiếp tục kiểm tra permission policy/RBAC ở từng tài nguyên.

JWT là token được ký, không phải token được mã hóa. Người có token có thể đọc payload claim; vì vậy không đưa secret, password hoặc dữ liệu nhạy cảm vào claim. Token là bearer credential trong thời hạn hiệu lực: ai lấy được token có thể thử dùng token đó cho tới khi hết hạn hoặc bị từ chối bởi policy.

## 3. Các claim quan trọng trong OIDC token

JWT thường có header, payload và signature. Payload chứa các claim mà cloud dùng để quyết định có tin job hay không.

| Claim | Ý nghĩa | Ví dụ |
|---|---|---|
| iss | Issuer đã phát hành token | https://token.actions.githubusercontent.com |
| aud | Audience mà token được phát hành cho | sts.amazonaws.com |
| sub | Subject, định danh ngữ cảnh job | Repository + branch hoặc environment |
| iat | Thời điểm phát hành | Unix timestamp |
| nbf | Thời điểm sớm nhất token có hiệu lực | Unix timestamp |
| exp | Thời điểm token hết hạn | Unix timestamp |
| jti | Định danh token | JWT identifier |
| repository | Repository đang chạy workflow | org/orders-api |
| repository_id | ID ổn định của repository | ID dạng số |
| repository_owner_id | ID ổn định của owner | ID dạng số |
| ref | Git ref kích hoạt workflow | refs/heads/main |
| environment | GitHub Environment gắn với job | production |
| workflow_ref | Đường dẫn workflow và ref | .github/workflows/deploy.yml@refs/heads/main |
| job_workflow_ref | Reusable workflow được job sử dụng | Repository, file và ref của workflow dùng lại |

Không phải mọi CI provider phát hành cùng một tập claim hoặc cùng định dạng sub. Cần xem tài liệu issuer và token thực tế của pipeline. Cloud chỉ có thể kiểm tra những claim mà provider phát hành và cloud provider hỗ trợ ánh xạ.

### Issuer và audience phải khớp chính xác

iss xác định ai phát hành token. Cloud chỉ nên tin đúng issuer đã đăng ký. aud xác định token dành cho dịch vụ nào. Một token được phát hành cho AWS STS không nên được chấp nhận như token dành cho Azure hoặc Google Cloud.

Audience thường khác nhau theo provider:

| Cloud | Audience thường dùng với GitHub Actions |
|---|---|
| AWS | sts.amazonaws.com |
| Microsoft Entra / Azure Login | api://AzureADTokenExchange |
| Google Cloud Workload Identity Federation | Audience của workload identity provider; action có thể tự cấu hình theo provider resource |

Không sao chép audience từ ví dụ cloud này sang cloud khác. Nếu audience trong token không khớp cấu hình federation, token sẽ bị từ chối dù issuer và subject đúng.

### Subject cần ràng buộc chặt

sub là một trong các điều kiện quan trọng nhất. Nó có thể xác định repository, branch, tag, pull request hoặc environment. Ví dụ định dạng truyền thống của GitHub:

~~~text
repo:ORG/REPO:ref:refs/heads/main
repo:ORG/REPO:environment:production
repo:ORG/REPO:pull_request
~~~

Khi job sử dụng GitHub Environment, sub chứa environment thay vì branch. Do đó, policy kiểm tra environment phải kết hợp với deployment branch rules và required reviewers của chính environment để giới hạn branch được phép deploy.

## 4. Thay đổi quan trọng: GitHub immutable subject claims từ tháng 7/2026

Từ ngày **15/07/2026**, repository GitHub mới mặc định sử dụng định dạng subject bất biến có thêm ID của owner và repository. Repository cũ giữ định dạng trước đó trừ khi tổ chức hoặc repository bật tùy chọn immutable subject; repository được rename hoặc transfer sau mốc này cũng chuyển sang định dạng mới. Tính năng này không áp dụng cho GitHub Enterprise Server.

Ví dụ:

| Loại | Subject |
|---|---|
| Định dạng cũ | repo:octo-org/octo-repo:ref:refs/heads/main |
| Định dạng bất biến | repo:octo-org@123456/octo-repo@456789:ref:refs/heads/main |
| Environment cũ | repo:octo-org/octo-repo:environment:production |
| Environment bất biến | repo:octo-org@123456/octo-repo@456789:environment:production |

Thay đổi này giúp ngăn một namespace đã bị xóa hoặc đổi tên được một owner khác đăng ký lại rồi tạo ra subject giống repository cũ. Khi trust policy chỉ dựa vào tên repository, việc tái sử dụng namespace có thể tạo ra rủi ro nhận nhầm danh tính.

Trước khi cấu hình federation:

1. Kiểm tra subject format thực tế của repository.
2. Xác định repository đã bật immutable subject hay chưa.
3. Lấy owner ID và repository ID từ GitHub.
4. Cập nhật trust policy ở cloud để khớp subject mới.
5. Kiểm thử token từ workflow đúng branch/environment.
6. Chỉ sau khi policy mới hoạt động mới bật immutable subject hoặc đổi repository.

Không đoán sub từ tên repository. GitHub có trang tài liệu và endpoint xem claim; trust policy phải khớp chính xác định dạng thực tế. Với AWS, có thể bổ sung điều kiện repository_id, repository_owner_id và ref nếu các claim này được hỗ trợ trong trust policy. Với Google Cloud, ánh xạ các claim ID thành attribute và dùng attribute condition. Với Azure federated credential, subject phải khớp chính xác giá trị token đang phát hành.

Tham khảo [GitHub OpenID Connect reference](https://docs.github.com/en/actions/reference/security/oidc) để kiểm tra claim format hiện hành.

## 5. OIDC token khác gì cloud access token?

Một lỗi thiết kế phổ biến là coi GitHub OIDC ID token như access token có thể gọi trực tiếp mọi API cloud. Thực tế, ID token mô tả danh tính job và được dùng trong quá trình federation. Cloud STS hoặc identity service xác minh token rồi cấp credential theo cơ chế của nền tảng.

| Loại token/credential | Vai trò |
|---|---|
| CI OIDC ID token | Chứng minh danh tính job với cloud federation endpoint |
| AWS STS credentials | Access key, secret key và session token tạm thời để gọi AWS API |
| Azure access token | Token OAuth được Microsoft Entra cấp cho resource/API |
| Google federated access token | Credential ngắn hạn được STS cấp; có thể dùng để impersonate service account |
| Service account key / client secret dài hạn | Credential tĩnh; thường không cần nếu OIDC federation được hỗ trợ |

Không lưu OIDC token hoặc credential tạm thời vào artifact, cache hay log. Không truyền token qua output giữa các job nếu job đích có thể tự yêu cầu token mới theo identity của nó. Hạn chế phạm vi token trong đúng job cần triển khai.

## 6. Phân biệt trust policy và permission policy

OIDC federation có hai quyết định độc lập:

- **Trust / federation policy:** identity nào được phép đổi token để nhận credential hoặc assume role?
- **Permission policy:** sau khi nhận credential, identity được phép làm gì trên tài nguyên cloud?

Ví dụ, một workflow thuộc repository org/orders-api, branch main, environment production có thể được phép assume một IAM role. Nhưng role đó chỉ nên có quyền cập nhật function orders-api, publish version và cập nhật alias cần thiết.

Không cấp quyền quản trị account chỉ vì pipeline cần deploy một function. Tách role theo môi trường và nhiệm vụ:

| Identity pipeline | Quyền phù hợp |
|---|---|
| Build/test | Không cần cloud deployment role |
| Deploy dev | Cập nhật function và tài nguyên dev |
| Deploy staging | Cập nhật tài nguyên staging, chạy smoke test |
| Deploy production | Quyền release production có kiểm soát |
| IaC plan | Quyền đọc/plan cần thiết, không có quyền apply nếu không cần |
| IaC apply | Quyền thay đổi hạ tầng theo stack và môi trường |

Nếu dùng cùng một role cho dev và production, một workflow dev bị xâm nhập có thể có đường nâng quyền sang production. Tách account, subscription hoặc project theo môi trường giúp giới hạn blast radius.

## 7. Thiết kế pipeline an toàn với GitHub Actions

Một pipeline nên tách build/test khỏi deploy. Job build thường không cần quyền cloud; chỉ job deploy được cấp id-token: write. Điều này giảm số bước có thể yêu cầu token và giới hạn quyền cho mã được thực thi trong deployment job.

Ví dụ cấu trúc:

~~~yaml
name: deploy-serverless

on:
  push:
    branches:
      - main

permissions:
  contents: read

jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "21"
          cache: maven
      - run: mvn -B clean verify
      - name: Package function
        run: ./scripts/package-function.sh
      - uses: actions/upload-artifact@v4
        with:
          name: function-package
          path: target/function.zip

  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment: production
    concurrency:
      group: production-deploy
      cancel-in-progress: false
    permissions:
      contents: read
      id-token: write
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: function-package
          path: drop
      # Cloud login and deploy steps go here.
~~~

Đây là skeleton; script package cần được định nghĩa theo project. Các action trong ví dụ dùng version tag để dễ đọc; trong production nên pin action vào full commit SHA đã review, theo dõi cập nhật bảo mật và quản lý dependency của workflow.

id-token: write cho phép job yêu cầu OIDC token từ GitHub. Quyền này **không tự cấp quyền AWS/Azure/GCP**. Cloud vẫn phải xác minh token và cấp quyền qua trust policy cùng permission policy.

Nếu job dùng environment production, hãy cấu hình GitHub Environment với:

- Required reviewers hoặc approval phù hợp.
- Deployment branches/tags chỉ cho phép nhánh hoặc tag được bảo vệ.
- Environment secrets/variables chỉ dành cho môi trường đó.
- Quy tắc ngăn deploy đồng thời nếu release không được phép chạy chồng.
- Audit log cho lần approval và deployment.

Không cấp id-token: write cho test job hoặc workflow xử lý pull request không tin cậy. Không dùng pull_request_target để checkout và chạy code từ fork trong job có quyền cloud. Workflow có quyền deploy phải chạy từ source và ref được bảo vệ.

## 8. AWS: GitHub Actions OIDC với IAM role và STS

AWS IAM hỗ trợ OIDC identity provider. Với GitHub Actions, cấu hình một IAM OIDC provider cho issuer https://token.actions.githubusercontent.com, sau đó tạo IAM role có trust policy cho phép sts:AssumeRoleWithWebIdentity.

Audience thường dùng là sts.amazonaws.com. Trust policy phải giới hạn sub; AWS yêu cầu subject không được để wildcard trống hoặc chỉ wildcard. Nên giới hạn repository, branch hoặc environment, đồng thời dùng immutable repository claims khi có thể.

### Trust policy cho branch được bảo vệ

Ví dụ dùng subject bất biến của GitHub repository mới:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::AWS_ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
          "token.actions.githubusercontent.com:sub": "repo:ORG@OWNER_ID/REPO@REPO_ID:ref:refs/heads/main",
          "token.actions.githubusercontent.com:repository_owner_id": "OWNER_ID",
          "token.actions.githubusercontent.com:repository_id": "REPO_ID",
          "token.actions.githubusercontent.com:ref": "refs/heads/main"
        }
      }
    }
  ]
}
~~~

Thay các giá trị mẫu bằng account ID, owner ID, repository ID và subject thực tế. Với repository vẫn dùng định dạng subject cũ, thay giá trị sub bằng định dạng cũ. Không thêm wildcard rộng chỉ để làm policy dễ hoạt động.

### Trust policy cho GitHub Environment

Nếu job sử dụng environment production, subject sẽ chứa environment:

~~~text
repo:ORG@OWNER_ID/REPO@REPO_ID:environment:production
~~~

Trong trường hợp đó, policy có thể kiểm tra sub theo environment và kiểm tra thêm claim ref nếu AWS condition key hỗ trợ:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::AWS_ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
          "token.actions.githubusercontent.com:sub": "repo:ORG@OWNER_ID/REPO@REPO_ID:environment:production",
          "token.actions.githubusercontent.com:repository_id": "REPO_ID",
          "token.actions.githubusercontent.com:repository_owner_id": "OWNER_ID",
          "token.actions.githubusercontent.com:ref": "refs/heads/main"
        }
      }
    }
  ]
}
~~~

Khi subject là environment, vẫn cần cấu hình deployment branch rules và reviewers trên GitHub Environment. Trust policy cloud và protection rule của GitHub bổ sung cho nhau.

### Permission policy cho role deploy

Trust policy chỉ xác định ai có thể assume role. Permission policy giới hạn hành động deploy. Ví dụ, role có thể được cấp quyền cập nhật code và publish version của một Lambda function cụ thể; nếu pipeline cập nhật alias thì cần thêm quyền alias tương ứng. Nếu artifact được upload lên S3 trước khi deploy, role cần quyền đọc đúng object/prefix đó.

Không gắn AdministratorAccess cho deployment role. Dùng ARN cụ thể và chỉ cấp các action thực sự cần cho quy trình.

### GitHub Actions workflow cho AWS

~~~yaml
deploy-aws:
  needs: build
  runs-on: ubuntu-latest
  environment: production
  permissions:
    contents: read
    id-token: write
  steps:
    - uses: actions/download-artifact@v4
      with:
        name: function-package
        path: drop

    - name: Configure AWS credentials with OIDC
      uses: aws-actions/configure-aws-credentials@v4
      with:
        role-to-assume: arn:aws:iam::AWS_ACCOUNT_ID:role/orders-function-deploy
        aws-region: ap-southeast-1

    - name: Deploy Lambda package
      run: |
        aws lambda update-function-code \
          --function-name orders-api \
          --zip-file fileb://drop/function.zip
~~~

Action cấu hình AWS credentials yêu cầu GitHub OIDC token và trao đổi nó lấy STS credentials. Ví dụ trên chỉ minh họa cập nhật code; production có thể cần chờ update hoàn tất, publish version, cập nhật alias hoặc dùng CodeDeploy để phát hành dần. Role chỉ nên có quyền tương ứng với các thao tác đó.

## 9. Azure: Microsoft Entra federated identity credential

Azure sử dụng Microsoft Entra để tạo liên kết federation giữa issuer của CI và một identity trong Entra. Identity có thể là app registration/service principal hoặc user-assigned managed identity tùy mô hình tích hợp.

Một federated identity credential thường gồm ba giá trị:

- **Issuer:** https://token.actions.githubusercontent.com
- **Subject:** subject claim chính xác của repository/branch hoặc environment.
- **Audience:** thường là api://AzureADTokenExchange trên Azure public cloud.

Azure kiểm tra issuer, subject và audience trước khi cấp access token. Sau đó, Azure RBAC quyết định identity có thể triển khai Function App, đọc storage hay thay đổi resource nào.

### Tạo federated identity credential

Với job dùng GitHub Environment, subject có thể là:

~~~text
repo:ORG@OWNER_ID/REPO@REPO_ID:environment:production
~~~

Với repository cũ chưa dùng immutable subject, subject có thể vẫn ở dạng:

~~~text
repo:ORG/REPO:environment:production
~~~

Giá trị subject phải khớp đúng token GitHub phát hành. Nếu workflow dùng branch subject thay vì environment, subject sẽ có dạng repo:ORG/REPO:ref:refs/heads/main hoặc dạng immutable tương ứng.

Gắn Azure RBAC role ở scope nhỏ nhất có thể, ví dụ Function App hoặc resource group chứa ứng dụng. Identity triển khai không cần quyền Owner hoặc Contributor trên toàn subscription nếu chỉ cập nhật một Function App.

### GitHub Actions workflow cho Azure

~~~yaml
deploy-azure:
  needs: build
  runs-on: ubuntu-latest
  environment: production
  permissions:
    contents: read
    id-token: write
  steps:
    - uses: actions/download-artifact@v4
      with:
        name: function-package
        path: drop

    - name: Azure login with OIDC
      uses: azure/login@v3
      with:
        client-id: ${{ vars.AZURE_CLIENT_ID }}
        tenant-id: ${{ vars.AZURE_TENANT_ID }}
        subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}

    - name: Deploy Azure Function
      uses: Azure/functions-action@v1
      with:
        app-name: ${{ vars.AZURE_FUNCTIONAPP_NAME }}
        package: drop/function.zip
~~~

Các giá trị AZURE_CLIENT_ID, AZURE_TENANT_ID, AZURE_SUBSCRIPTION_ID và AZURE_FUNCTIONAPP_NAME được đọc từ GitHub Environment variables; có thể dùng secrets nếu chính sách nội bộ yêu cầu. Client ID, tenant ID và subscription ID là các định danh cấu hình, không phải client secret. OIDC loại bỏ nhu cầu lưu client secret dài hạn cho bước đăng nhập.

Nếu dùng Azure Government, Azure China hoặc cloud sovereign khác, audience và environment cần theo endpoint tương ứng; không dùng mặc định của public cloud một cách máy móc.

## 10. Google Cloud: Workload Identity Federation

Google Cloud dùng Workload Identity Federation (WIF) để tin cậy external identity provider mà không cần service account key dài hạn. Với GitHub Actions, cấu hình gồm:

1. Workload identity pool.
2. OIDC provider trong pool, issuer là GitHub Actions.
3. Attribute mapping từ claim GitHub sang attribute của Google.
4. Attribute condition giới hạn repository/owner/branch/environment.
5. Quyền truy cập trực tiếp tới resource hoặc quyền impersonate service account.

Google khuyến nghị dùng attribute condition với issuer dùng chung cho nhiều organization như GitHub. Chỉ kiểm tra issuer là chưa đủ, vì token từ nhiều repository khác nhau cùng được phát hành bởi một issuer.

### Tạo provider và ánh xạ claim

Ví dụ dùng claim ID bất biến:

~~~bash
gcloud iam workload-identity-pools providers create-oidc github-actions \
  --location="global" \
  --workload-identity-pool="ci-pool" \
  --issuer-uri="https://token.actions.githubusercontent.com/" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository_id=assertion.repository_id,attribute.repository_owner_id=assertion.repository_owner_id,attribute.ref=assertion.ref" \
  --attribute-condition="assertion.repository_owner_id == 'OWNER_ID' && assertion.repository_id == 'REPO_ID' && assertion.ref == 'refs/heads/main'"
~~~

Tên pool, provider, owner ID và repository ID là giá trị mẫu. Attribute condition là CEL expression. Có thể thêm điều kiện cho assertion.environment nếu deployment job dùng GitHub Environment; kiểm tra token claims thực tế trước khi viết condition.

### Cho phép federated identity impersonate service account

Nếu dịch vụ hoặc công cụ deploy cần service account impersonation, cấp roles/iam.workloadIdentityUser trên service account cho đúng principal set của repository:

~~~bash
gcloud iam service-accounts add-iam-policy-binding \
  "orders-deployer@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/ci-pool/attribute.repository_id/REPO_ID"
~~~

Service account sau đó nhận IAM roles cần thiết trên Function, Cloud Run hoặc resource cụ thể. Nếu API hỗ trợ cấp quyền trực tiếp cho federated principal, có thể dùng direct resource access và bỏ bước impersonation. Google khuyến nghị direct access khi sản phẩm hỗ trợ; service account impersonation dùng khi API hoặc công cụ có giới hạn tương thích.

### GitHub Actions workflow cho Google Cloud

~~~yaml
deploy-gcp:
  needs: build
  runs-on: ubuntu-latest
  environment: production
  permissions:
    contents: read
    id-token: write
  steps:
    - uses: actions/download-artifact@v4
      with:
        name: function-package
        path: drop

    - name: Authenticate to Google Cloud
      uses: google-github-actions/auth@v2
      with:
        workload_identity_provider: projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/ci-pool/providers/github-actions
        service_account: orders-deployer@PROJECT_ID.iam.gserviceaccount.com

    - name: Setup gcloud
      uses: google-github-actions/setup-gcloud@v2

    - name: Deploy function
      run: |
        gcloud functions deploy orders-api \
          --gen2 \
          --runtime=java21 \
          --region=asia-southeast1 \
          --source=drop \
          --entry-point=com.example.functions.OrderFunction \
          --trigger-http
~~~

Ví dụ deploy giả định thư mục artifact drop có cấu trúc source/deployment mà Google Functions build system mong đợi và Java entry point đúng với ứng dụng. Tùy pipeline, có thể deploy từ source đã build hoặc image đã push; cần cấp quyền Cloud Build, Artifact Registry và Function runtime theo đúng quy trình sử dụng.

## 11. So sánh cấu hình federation giữa các cloud

| Khái niệm | AWS | Azure | Google Cloud |
|---|---|---|---|
| Nơi đăng ký issuer | IAM OIDC provider | Microsoft Entra federated identity credential | Workload Identity Pool Provider |
| Issuer GitHub | https://token.actions.githubusercontent.com | https://token.actions.githubusercontent.com | https://token.actions.githubusercontent.com/ theo cấu hình provider |
| Audience mẫu | sts.amazonaws.com | api://AzureADTokenExchange | Provider audience/resource |
| Ràng buộc subject | IAM role trust policy | Federated identity credential | Attribute mapping/condition |
| Cấp credential | AWS STS AssumeRoleWithWebIdentity | Microsoft Entra token exchange | Google STS, có thể impersonate service account |
| Quyền sau federation | IAM permissions policy | Azure RBAC | IAM allow policy |
| GitHub action phổ biến | configure-aws-credentials | azure/login | google-github-actions/auth |

Cùng một GitHub workflow có thể phát hành token khác audience cho từng cloud. Không dùng một token với audience AWS rồi gửi nguyên token đó sang Azure hoặc Google. Mỗi bước login cần yêu cầu token đúng audience và chỉ chạy khi job có quyền cần thiết.

## 12. Dùng OIDC với GitLab CI và Azure DevOps

OIDC không chỉ dành cho GitHub Actions. Nhiều CI provider phát hành ID token với claim riêng:

- GitLab CI dùng id_tokens trong job để yêu cầu JWT với audience xác định. Cloud provider kiểm tra issuer https://gitlab.com và claim về project, namespace, branch hoặc environment.
- Azure DevOps có workload identity federation trong service connection; pipeline lấy token từ service connection rồi dùng federation để truy cập cloud.
- Các hệ thống CI khác có thể hỗ trợ OIDC hoặc SAML federation, nhưng issuer, audience và subject format phải lấy từ tài liệu của chính provider.

Ví dụ cấu trúc GitLab CI:

~~~yaml
deploy:
  stage: deploy
  id_tokens:
    CLOUD_OIDC_TOKEN:
      aud: https://example-cloud-token-exchange
  script:
    - ./scripts/federated-login.sh
    - ./scripts/deploy-function.sh
  rules:
    - if: '$CI_COMMIT_BRANCH == "main"'
~~~

aud và cách gửi token trong script phải khớp với cloud provider. Không giả định claim GitLab tương tự claim GitHub. Với Azure DevOps, dùng service connection được cấu hình workload identity federation thay vì tự tạo một client secret trong variable group.

## 13. Bảo vệ workflow và deployment environment

OIDC chỉ an toàn khi workflow được cấp token là workflow đáng tin. Nếu attacker có thể sửa workflow trên branch được trust, họ có thể thêm step yêu cầu OIDC token và sử dụng quyền cloud hợp lệ.

Các biện pháp nên áp dụng:

- Bảo vệ branch production bằng branch protection và required reviews.
- Dùng GitHub Environment cho production, bật required reviewers và deployment branch rules.
- Chỉ cấp id-token: write cho job deploy.
- Không cấp quyền cloud cho pull request từ fork hoặc code chưa review.
- Tránh pull_request_target nếu workflow checkout/chạy code không tin cậy.
- Pin third-party action vào full commit SHA; review action update.
- Ưu tiên reusable deployment workflow đã được bảo vệ và có thể giới hạn bằng job_workflow_ref nếu provider hỗ trợ.
- Tách role dev, staging và production.
- Giới hạn permission policy theo resource ARN, scope và action.
- Dùng concurrency group để tránh hai release production chạy chồng.
- Không cho workflow tự chọn role hoặc subscription qua input tùy ý.
- Không ghi token, access token hoặc credential tạm thời ra log.

Nếu workflow được trigger bởi pull request, GitHub subject có thể là pull_request. Đừng cấp subject này quyền deploy production. Với môi trường production, chỉ cho phép branch/tag được bảo vệ thông qua GitHub Environment rules và trust condition tương ứng.

## 14. Bảo vệ artifact và tách build khỏi deploy

OIDC chứng minh danh tính job, không chứng minh artifact đã được kiểm tra hoặc an toàn. Một workflow có quyền deploy vẫn có thể đưa nhầm JAR hoặc ZIP bị sửa đổi lên cloud.

Nên thiết kế pipeline theo hướng:

1. Build và test trên commit cụ thể.
2. Tạo artifact một lần.
3. Tính checksum và lưu metadata commit/build.
4. Upload artifact vào artifact store có kiểm soát.
5. Deployment job tải đúng artifact đã được build.
6. Xác minh checksum hoặc provenance trước khi deploy.
7. Deploy vào môi trường đã được phê duyệt.
8. Lưu release ID, artifact digest và cloud deployment ID.

Không build lại ở job production nếu cần bảo đảm artifact đã kiểm thử chính là artifact được phát hành. Nếu cần build khác theo môi trường, phải có quy tắc rõ ràng về cấu hình tách khỏi binary và xác minh tính toàn vẹn.

Không đưa OIDC token vào artifact hoặc cache. Credential chỉ cần tồn tại trong job deploy và phải bị xóa khỏi workspace khi job kết thúc theo cơ chế của action/runtime.

## 15. Quyền tối thiểu cho Java serverless deployment

Một pipeline Java thường cần các quyền sau tùy nền tảng:

| Công việc | Quyền có thể cần |
|---|---|
| Upload artifact | Ghi đúng bucket/container hoặc registry |
| Deploy function package | Cập nhật code của đúng function |
| Cập nhật cấu hình | Chỉ cập nhật setting được pipeline quản lý |
| Publish version | Tạo version mới của function |
| Update alias/traffic | Cập nhật alias hoặc deployment slot/revision |
| Tạo infrastructure | Quyền IaC giới hạn trong stack/resource group/project |
| Đọc trạng thái deploy | Quyền đọc deployment/function status |
| Ghi log/audit | Chỉ khi pipeline thực sự cần |

Không cấp quyền runtime của function cho pipeline nếu pipeline chỉ cần deploy. Ngược lại, execution role/service identity của function không phải deployment identity. Hai danh tính có vòng đời và mục đích khác nhau.

Với Terraform hoặc CloudFormation, cần tính tới quyền tạo, cập nhật, xóa tài nguyên và quyền đọc state/backend. Tách quyền plan và apply nếu quy trình yêu cầu approval. OIDC role cho IaC có thể có phạm vi lớn hơn role deploy một function; cần tách role và environment tương ứng.

## 16. Token lifetime, session và rotation

OIDC token và cloud credential đều có thời hạn. Thời gian hiệu lực phụ thuộc issuer, cloud provider và cấu hình role/session. Không giả định mọi provider có cùng TTL.

Các nguyên tắc:

- Yêu cầu token gần thời điểm cần deploy.
- Không lấy token từ một job cũ rồi dùng lại trong job mới.
- Nếu session hết hạn giữa pipeline, yêu cầu federation lại theo cơ chế của action.
- Không lưu token vào file lâu hơn thời gian cần thiết.
- Không in token để debug; JWT payload có thể đọc được và token là bearer credential.
- Thu hồi trust bằng cách disable provider, xóa federated credential hoặc sửa trust condition.
- Thu hồi quyền deploy bằng cách sửa IAM/RBAC permission policy.
- Nếu nghi token bị lộ, chặn trust/role trước, kiểm tra audit log và đánh giá các hành động đã thực hiện.

OIDC giảm gánh nặng rotation secret dài hạn, nhưng không loại bỏ nhu cầu quản lý trust policy, issuer, audience và quyền cloud. Khi đổi repository, branch, environment hoặc workflow, phải rà soát điều kiện federation.

## 17. Quan sát và audit hoạt động federation

Cần biết job nào đã nhận credential, role/service identity nào được sử dụng và tài nguyên nào bị thay đổi.

Theo dõi:

- GitHub workflow run ID, repository, commit SHA, branch và environment.
- Cloud identity/role/service account được assume.
- Thời điểm federation và session duration.
- Cloud audit log cho thao tác deploy, update function và IAM/RBAC.
- Artifact digest và release ID.
- Các lần federation bị từ chối do issuer, audience hoặc subject mismatch.
- Các thao tác nhạy cảm như tạo role, đổi trust policy hoặc thêm federated credential.

Không log raw JWT. Nếu cần debug claim, giải mã payload trong môi trường kiểm soát và chỉ ghi các claim không nhạy cảm cần thiết như iss, aud, sub, ref, repository ID và expiry. Chữ ký token cần được cloud xác minh; việc decode payload bằng công cụ local không chứng minh token hợp lệ.

Có thể tạo correlation ID từ workflow run ID và release ID để nối log pipeline với cloud audit log. Điều này giúp điều tra sự cố mà không cần lưu credential.

## 18. Chẩn đoán lỗi OIDC federation

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Không lấy được OIDC token từ GitHub | Thiếu id-token: write hoặc job không có quyền | Kiểm tra permissions ở workflow/job |
| audience mismatch | Action yêu cầu audience khác provider cho phép | So sánh aud trong token với cấu hình cloud |
| subject mismatch | Sai repository, branch, tag hoặc environment | Kiểm tra sub thực tế và trust condition |
| Token issuer không được tin | Issuer URL hoặc provider chưa đăng ký đúng | So sánh iss và issuer URL |
| GitHub repo mới không assume role | Subject đã chuyển sang immutable format | Kiểm tra owner/repository ID và cập nhật trust |
| AWS Not authorized to perform sts:AssumeRoleWithWebIdentity | Trust policy sai, audience/sub không khớp | Kiểm tra IAM OIDC provider, role trust policy và action |
| AWS assume role thành công nhưng deploy AccessDenied | Permission policy thiếu action/resource | Kiểm tra IAM permissions policy và ARN |
| Azure federated credential not found | Issuer, subject hoặc audience không khớp | Kiểm tra FIC trên đúng app/managed identity |
| Azure login thành công nhưng deploy bị 403 | Azure RBAC scope/role không đủ | Kiểm tra role assignment và scope Function App/resource group |
| Google invalid_grant | Provider condition, issuer hoặc audience sai | Kiểm tra pool/provider, attribute mapping và token claims |
| Google Permission denied khi impersonate | Thiếu Workload Identity User binding | Kiểm tra principalSet và service account IAM policy |
| Google auth thành công nhưng deploy thất bại | Service account thiếu quyền deploy hoặc API chưa bật | Kiểm tra IAM roles, APIs và target resource |
| Pipeline chạy từ fork không có token | Workflow context không được cấp quyền | Không mở quyền production; chỉ deploy từ protected source |

Hãy phân biệt lỗi federation và lỗi authorization. Federation thất bại nghĩa là cloud chưa cấp credential. Authorization thất bại nghĩa là credential đã được cấp nhưng không có quyền thực hiện hành động. Hai loại lỗi cần kiểm tra ở hai policy khác nhau.

## 19. Quy trình rollout OIDC an toàn

Không nên xóa access key cũ ngay khi mới tạo OIDC provider. Có thể chuyển đổi theo từng bước:

1. Kiểm kê mọi pipeline đang dùng static key, client secret hoặc service account key.
2. Xác định repository, workflow, branch, environment và tài nguyên cloud mà mỗi pipeline cần.
3. Tạo OIDC provider/federated credential và role với permission tối thiểu.
4. Cấu hình trust condition theo issuer, audience, subject và immutable claims nếu hỗ trợ.
5. Thử trên môi trường dev hoặc staging.
6. Kiểm tra cloud audit log để xác nhận đúng principal và role.
7. Chuyển production pipeline sang OIDC sau khi có approval.
8. Theo dõi một vài chu kỳ release.
9. Thu hồi static credential cũ và kiểm tra không còn pipeline phụ thuộc.
10. Định kỳ rà soát trust policy, action pinning, branch protection và quyền cloud.

Trong giai đoạn chuyển tiếp, không để cả OIDC role và key cũ cùng có quyền quản trị rộng hơn mức cần thiết. Ghi lại owner, mục đích, ngày chuyển đổi và quy trình rollback.

## 20. Checklist production cho OIDC federation

Trước khi bật pipeline production, xác nhận:

1. CI issuer đã được đăng ký chính xác ở cloud?
2. Audience của token khớp với federation provider?
3. Subject giới hạn đúng repository và branch hoặc environment?
4. Đã xác minh GitHub subject format cũ hay immutable theo repository thực tế?
5. Nếu dùng GitHub Environment, deployment branch rules và reviewers đã bật?
6. id-token: write chỉ cấp cho job deploy?
7. Pull request từ fork và workflow không tin cậy không có quyền deploy?
8. Third-party actions được pin và review?
9. Trust policy và permission policy được tách riêng?
10. Role chỉ có quyền trên function, resource group, project hoặc stack cần thiết?
11. Dev, staging và production dùng identity riêng?
12. Artifact được build một lần, kiểm tra digest và chuyển đúng sang deploy job?
13. Token/credential không bị ghi vào log, artifact hoặc cache?
14. Cloud audit log ghi nhận được role/service identity và thao tác deploy?
15. Có quy trình cập nhật trust khi repository rename, transfer hoặc bật immutable subject?
16. Có quy trình thu hồi federation và static credential cũ?
17. Đã kiểm thử lỗi audience, subject, permission và token expiry?
18. Có owner chịu trách nhiệm rà soát trust policy định kỳ?

## Tài liệu tham khảo

- [GitHub Actions OpenID Connect reference](https://docs.github.com/en/actions/reference/security/oidc)
- [GitHub: Immutable subject claims for OIDC tokens](https://github.blog/changelog/2026-04-23-immutable-subject-claims-for-github-actions-oidc-tokens/)
- [AWS IAM: Create a role for OIDC federation](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_create_for-idp_oidc.html)
- [AWS IAM: OIDC condition context keys](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_iam-condition-keys.html)
- [Microsoft Learn: Authenticate to Azure from GitHub Actions by OIDC](https://learn.microsoft.com/azure/developer/github/connect-from-azure-openid-connect)
- [Google Cloud: Workload Identity Federation with deployment pipelines](https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines)
- [Google Cloud: Best practices for Workload Identity Federation](https://docs.cloud.google.com/iam/docs/best-practices-for-using-workload-identity-federation)

## Kết luận

OIDC federation cho phép pipeline CI/CD chứng minh danh tính với cloud bằng token ngắn hạn, sau đó nhận credential tạm thời để triển khai Java function và hạ tầng liên quan. Cách này giảm phụ thuộc vào access key, client secret và service account key dài hạn.

Để federation an toàn, hãy giới hạn issuer, audience, subject, repository và branch/environment; tách trust policy khỏi permission policy; chỉ cấp id-token: write cho deployment job; bảo vệ branch và environment; và cấp quyền cloud tối thiểu cho từng pipeline. Với AWS dùng IAM role và STS, Azure dùng Microsoft Entra federated identity credential cùng RBAC, còn Google Cloud dùng Workload Identity Pool/Provider và IAM. Đặc biệt, phải kiểm tra định dạng GitHub sub thực tế, bao gồm immutable subject claims được triển khai từ tháng 7/2026. Khi pipeline, artifact và quyền cloud được quản lý cùng nhau, việc phát hành serverless có thể tự động hóa mà không phải giữ credential dài hạn trong CI.

