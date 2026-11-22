# Giới thiệu OIDC và liên kết danh tính với dịch vụ đích

Một pipeline CI/CD thường cần truy cập dịch vụ bên ngoài để tải dependency, đẩy container image, lưu artifact, triển khai ứng dụng hoặc đọc secret. Cách làm cũ thường lưu access key, mật khẩu hoặc client secret dài hạn trong cấu hình CI rồi cấp cho job khi chạy. Nếu credential bị lộ trong log, script hoặc runner, người khác có thể tiếp tục sử dụng nó cho đến khi credential bị thu hồi hoặc hết hạn.

**OpenID Connect (OIDC)** cho phép một workload chứng minh danh tính của mình với dịch vụ đích thông qua token do một identity provider phát hành. Trong CI/CD, hệ thống CI có thể cấp một OIDC token ngắn hạn cho job. Dịch vụ đích xác minh token và các claim, sau đó trao quyền truy cập tạm thời cho đúng repository, workflow, nhánh hoặc môi trường được tin cậy.

Cách làm này thường được gọi là **workload identity federation** hoặc liên kết danh tính workload. Pipeline không cần giữ một credential dùng chung lâu dài cho dịch vụ đích. Quyền truy cập được quyết định bởi quan hệ tin cậy giữa issuer, các claim trong token và chính sách của dịch vụ nhận token.

## 1. OIDC là gì?

OIDC là một lớp định danh xây dựng trên OAuth 2.0. Nó chuẩn hóa cách một bên phát hành token mô tả danh tính và cách bên nhận xác minh danh tính đó. Trong nhiều luồng CI/CD, token được cấp là JSON Web Token (JWT), chứa các claim về issuer, subject, audience và thời hạn.

Các claim thường gặp:

| Claim | Ý nghĩa | Vai trò khi liên kết danh tính |
|---|---|---|
| iss | Issuer, tổ chức hoặc dịch vụ phát hành token | Xác định nguồn danh tính được tin cậy |
| sub | Subject, đối tượng mà token đại diện | Phân biệt repository, workflow, branch hoặc environment theo quy tắc issuer |
| aud | Audience, bên nhận dự kiến của token | Ngăn token được dùng cho một dịch vụ khác |
| exp | Thời điểm token hết hạn | Giới hạn thời gian sử dụng |
| iat | Thời điểm token được phát hành | Kiểm tra tính mới và điều tra |
| nbf | Thời điểm token bắt đầu có hiệu lực | Ngăn dùng token trước thời điểm được phép |
| jti | Định danh token nếu issuer cung cấp | Hỗ trợ ghi nhận và kiểm soát việc sử dụng token |

Issuer có thể cung cấp thêm claim như repository, organization, branch/ref, commit SHA, workflow, environment hoặc actor. Dịch vụ đích chỉ nên dựa vào những claim mà issuer cam kết và nền tảng nhận token thực sự kiểm tra.

### OIDC token không phải credential có toàn quyền

OIDC token là bằng chứng danh tính được phát hành bởi issuer. Nó không tự động cấp quyền đọc bucket, đẩy image hay triển khai production. Dịch vụ đích phải có cấu hình tin cậy và chính sách quyền riêng:

1. Token đến từ issuer được chấp nhận.
2. Token dành cho đúng audience.
3. Subject và các claim thỏa điều kiện tin cậy.
4. Token còn hiệu lực và chữ ký hợp lệ.
5. Danh tính đã xác minh được ánh xạ vào principal hoặc role.
6. Principal chỉ được thực hiện những hành động được cấp quyền.

Vì vậy, cần phân biệt **xác thực danh tính** (authentication) với **ủy quyền** (authorization). OIDC trả lời workload là ai; policy của dịch vụ đích quyết định workload được làm gì.

## 2. Vì sao CI/CD nên dùng workload identity federation?

Credential dài hạn tạo ra gánh nặng quản lý:

- Phải tạo, lưu, phân phối và xoay vòng secret.
- Secret có thể bị sao chép sang nhiều repository hoặc môi trường.
- Khó xác định chính xác job nào đã sử dụng credential.
- Credential bị lộ có thể tiếp tục dùng ngoài thời gian chạy pipeline.
- Một runner hoặc workflow bị chiếm quyền có thể làm lộ nhiều dịch vụ cùng lúc.

Với OIDC federation, job yêu cầu token khi cần, dùng token để đổi lấy quyền truy cập ngắn hạn và kết thúc công việc. Dịch vụ đích kiểm tra danh tính theo claim thay vì dựa vào một chuỗi secret tĩnh được lưu trong CI.

Lợi ích chính:

| Lợi ích | Ý nghĩa thực tế |
|---|---|
| Không phải lưu shared secret dài hạn | Giảm số credential có thể bị đánh cắp |
| Token có thời hạn ngắn | Giới hạn cửa sổ sử dụng nếu token bị lộ |
| Trust policy theo claim | Giới hạn repository, branch, workflow hoặc environment |
| Quyền tạm thời | Có thể cấp role hoặc credential ngắn hạn theo nhiệm vụ |
| Truy vết | Log của issuer, STS và dịch vụ đích giúp xác định workload |
| Tách biệt môi trường | Job production có thể có danh tính riêng với job test |

OIDC không loại bỏ mọi bí mật. Một số dịch vụ vẫn cần secret riêng, signing key hoặc thông tin cấu hình nhạy cảm. Mục tiêu là tránh dùng credential dài hạn khi dịch vụ hỗ trợ xác thực workload bằng federation.

## 3. Các thành phần trong luồng OIDC

Một luồng CI/CD điển hình có các thành phần:

- **Workload:** job hoặc runner đang thực hiện build/deploy.
- **OIDC issuer:** nền tảng CI phát hành token và công bố public keys để xác minh chữ ký.
- **OIDC token:** JWT đại diện cho workload trong một ngữ cảnh cụ thể.
- **Federation endpoint hoặc STS:** dịch vụ nhận token và đổi nó lấy quyền truy cập tạm thời.
- **Trust policy:** điều kiện xác định issuer, audience, subject và claim nào được chấp nhận.
- **Target service:** dịch vụ đích mà job cần truy cập, ví dụ cloud API, registry, Vault hoặc Kubernetes API.
- **Role/service account:** danh tính được ánh xạ sau khi token được xác minh.

Luồng tổng quát:

~~~text
CI job
  |
  | 1. Yêu cầu OIDC token
  v
OIDC issuer
  |
  | 2. Phát hành JWT có chữ ký
  v
CI job
  |
  | 3. Gửi token tới federation endpoint / STS
  v
Target identity service
  |
  | 4. Kiểm tra chữ ký, issuer, audience,
  |    subject, thời hạn và trust policy
  v
Role / service account
  |
  | 5. Cấp credential hoặc token tạm thời
  v
Target service
  |
  | 6. Thực hiện hành động trong phạm vi quyền
  v
Artifact / cloud resource / deployment target
~~~

Một số nền tảng gộp bước federation và cấp credential vào một API. Một số nền tảng có bước ánh xạ danh tính riêng. Dù triển khai thế nào, dịch vụ đích phải xác minh token trước khi cấp quyền.

## 4. Token được xác minh như thế nào?

JWT thường gồm header, payload và chữ ký. Payload có thể đọc được nếu có token, vì vậy không được coi nội dung JWT là bí mật. Chữ ký cho phép bên nhận xác minh token do issuer tương ứng phát hành và nội dung chưa bị sửa.

Quy trình xác minh thường bao gồm:

1. Đọc issuer từ claim iss và đối chiếu với issuer đã cấu hình.
2. Lấy public key phù hợp từ JWKS endpoint của issuer hoặc bộ khóa đã tin cậy.
3. Xác minh chữ ký theo thuật toán được chấp nhận.
4. Kiểm tra audience có khớp dịch vụ nhận token không.
5. Kiểm tra thời hạn exp, thời điểm hiệu lực nbf và các điều kiện thời gian liên quan.
6. Đánh giá subject và các claim khác theo trust policy.
7. Ánh xạ danh tính hợp lệ sang role, service account hoặc principal.

Issuer thường công bố metadata OIDC discovery và JWKS để bên nhận tìm endpoint cũng như public key. Dịch vụ đích cần xử lý việc xoay vòng key và cache khóa đúng cách. Không tự chấp nhận một JWT chỉ vì payload chứa tên repository hoặc một claim có vẻ hợp lệ.

### Ba trường cần kiểm tra đầu tiên

**Issuer (iss)** trả lời: token do hệ thống nào phát hành? Chỉ tin issuer cụ thể đã được cấu hình, không chấp nhận một URL bất kỳ do request gửi lên.

**Audience (aud)** trả lời: token được phát hành cho dịch vụ nào? Một token dành cho AWS STS không nên được dùng để truy cập một dịch vụ khác nếu dịch vụ đó không phải audience được dự kiến.

**Subject (sub)** trả lời: token đại diện cho workload nào? Subject nên đủ hẹp để phân biệt repository và ngữ cảnh được phép, ví dụ một branch hoặc environment cụ thể.

### Thời hạn và thời gian hệ thống

Token có exp và có thể có nbf. Máy chạy CI và dịch vụ xác minh cần đồng bộ thời gian hợp lý. Sai lệch đồng hồ có thể khiến token bị từ chối dù workflow vừa yêu cầu token. Không nên khắc phục bằng cách bỏ kiểm tra thời hạn; hãy xử lý đồng bộ thời gian và giới hạn clock skew theo khả năng của dịch vụ.

Token ngắn hạn giảm thời gian lạm dụng khi bị lộ, nhưng không thay thế việc bảo vệ runner và log. Một kẻ tấn công đang kiểm soát job có thể yêu cầu token mới trong lúc job còn quyền.

## 5. Liên kết danh tính với repository, branch và environment

Một trust policy quá rộng có thể cho phép nhiều workflow không liên quan truy cập cùng một role. Ví dụ, chỉ kiểm tra issuer của GitHub Actions mà không giới hạn subject có thể tin mọi repository hoặc mọi branch thuộc issuer đó, tùy cách cấu hình provider.

Hãy chọn claim theo ranh giới tin cậy:

| Ngữ cảnh | Điều kiện có thể dùng |
|---|---|
| Một repository | Repository owner và repository name |
| Một branch | Repository và ref cụ thể, ví dụ refs/heads/main |
| Một tag phát hành | Repository và tag pattern được cho phép |
| Một environment | Repository và environment name |
| Một workflow tái sử dụng | Workflow reference hoặc claim riêng nếu issuer hỗ trợ |
| Một tổ chức | Organization claim, kết hợp thêm giới hạn repository và ref |

Chỉ giới hạn organization thường chưa đủ nếu mọi repository trong tổ chức không được phép triển khai production. Hãy chọn điều kiện hẹp nhất phù hợp với cách vận hành.

### Subject phụ thuộc cấu hình issuer

Định dạng subject không giống nhau giữa các identity provider. Với GitHub Actions, subject mặc định thường chứa repository và ref; nếu job tham chiếu GitHub Environment, subject có thể chứa tên environment thay cho ref. GitHub cũng hỗ trợ tùy chỉnh subject template trong một số cấu hình.

Do đó, hãy xem token claim thực tế hoặc tài liệu của issuer trước khi viết trust policy. Không suy luận subject từ tên branch hoặc tên environment mà chưa xác minh định dạng được phát hành.

### Dùng environment có bảo vệ cho production

Một workflow có thể yêu cầu GitHub Environment tên production trước khi chạy bước triển khai. Environment có thể áp dụng reviewer, branch/tag restriction và các quy tắc bảo vệ khác. Trust policy ở dịch vụ đích có thể chỉ chấp nhận subject gắn với environment đó.

Khi dùng environment làm ranh giới, cần bảo đảm:

- Chỉ branch/tag được phép mới có thể tham chiếu environment.
- Reviewer và quy tắc phê duyệt được cấu hình ở repository.
- Chỉ job cần quyền production mới có quyền yêu cầu OIDC token.
- Role production có quyền tối thiểu và không được dùng cho test job.

Environment name là một phần của subject theo quy tắc issuer; nó không tự chứng minh rằng mọi approval đã được thực hiện nếu cấu hình môi trường không yêu cầu approval.

## 6. Ví dụ: GitHub Actions lấy token OIDC

GitHub Actions có issuer OIDC tại:

~~~text
https://token.actions.githubusercontent.com
~~~

Job cần quyền yêu cầu ID token phải được cấp permission id-token: write. Permission này cho phép job yêu cầu token từ GitHub; nó không tự cấp quyền truy cập AWS, Azure, GCP hoặc dịch vụ khác. Quyền thực tế phụ thuộc trust policy và role/service account phía đích.

Ví dụ workflow chỉ cho phép job triển khai chạy từ branch main:

~~~yaml
name: Deploy

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
        uses: actions/checkout@v4

      - name: Authenticate to target service
        run: |
          echo "Use the provider-specific OIDC action or SDK here."

      - name: Deploy
        run: ./scripts/deploy.sh
~~~

Đây là khung workflow minh họa. Bước xác thực cần được thay bằng action hoặc SDK chính thức của nhà cung cấp đích. Trong repository phát hành, nên pin action theo full commit SHA theo chính sách tổ chức, review quyền của action và giới hạn quyền token ở đúng job cần dùng.

### Kiểm tra quyền ở mức job

Không cấp id-token: write cho mọi job chỉ vì một job deploy cần nó. Đặt permission tại job triển khai giúp giới hạn phạm vi. Những job chạy test, lint hoặc xử lý pull request không cần truy cập production thì không nên có quyền yêu cầu token cho dịch vụ đó.

## 7. Ví dụ: GitHub Actions liên kết với AWS IAM Role

AWS có thể tin một OIDC provider và cho phép workload gọi STS AssumeRoleWithWebIdentity để nhận temporary security credentials.

Các bước cấu hình khái quát:

1. Tạo OIDC identity provider trong AWS IAM với URL issuer của GitHub Actions.
2. Cấu hình audience được phép, thường là sts.amazonaws.com cho AWS STS.
3. Tạo IAM role với trust policy giới hạn audience và subject.
4. Gắn permission policy tối thiểu cho role.
5. Trong GitHub Actions, yêu cầu OIDC token và dùng action AWS credentials để assume role.

Ví dụ trust policy giới hạn repository và branch main:

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
          "token.actions.githubusercontent.com:sub": "repo:acme/payments-api:ref:refs/heads/main"
        }
      }
    }
  ]
}
~~~

Các giá trị account ID, organization và repository là ví dụ. Provider trong IAM phải được tạo trước và client ID list phải khớp audience mà workflow yêu cầu. Subject phải khớp định dạng token thực tế.

Trust policy quyết định ai được assume role. Permission policy gắn với role quyết định role được làm gì. Hai chính sách phải được review riêng. Ví dụ role deploy chỉ nên có quyền cập nhật đúng bucket, cluster hoặc dịch vụ cần thiết; không nên cấp AdministratorAccess chỉ để workflow chạy được.

Workflow sử dụng action AWS credentials có thể có dạng:

~~~yaml
permissions:
  contents: read
  id-token: write

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::123456789012:role/payments-production-deploy
          aws-region: ap-southeast-1

      - name: Verify caller identity
        run: aws sts get-caller-identity

      - name: Deploy
        run: ./scripts/deploy.sh
~~~

Ví dụ minh họa. Trong môi trường thực tế, pin action theo commit SHA, giới hạn branch/environment, kiểm tra role trust policy và xác minh lệnh deploy chỉ tác động tài nguyên được phép. Không lưu AWS access key dài hạn trong repository secrets nếu OIDC federation đã đáp ứng nhu cầu.

### Khi dùng GitHub Environment

Nếu job tham chiếu environment production, subject có thể có dạng:

~~~text
repo:acme/payments-api:environment:production
~~~

Khi đó trust policy cần dùng đúng subject của environment và repository. Vì subject có thể không còn chứa branch ref theo định dạng mặc định, hãy dùng branch/tag protection của environment để giới hạn nguồn triển khai. Có thể bổ sung claim hoặc custom subject template nếu kiến trúc cần ràng buộc nhiều thuộc tính.

## 8. Liên kết với Google Cloud và Azure

Các nhà cung cấp cloud dùng thuật ngữ và cấu hình riêng, nhưng mô hình chung vẫn là issuer, audience, subject/attributes, trust mapping và quyền tạm thời.

### Google Cloud Workload Identity Federation

Google Cloud Workload Identity Federation cho phép workload bên ngoài Google Cloud trao đổi token OIDC lấy danh tính được ánh xạ trong Workload Identity Pool. Sau đó workload có thể được cấp quyền trực tiếp hoặc impersonate service account theo chính sách IAM.

Các thành phần cần cấu hình:

- Workload Identity Pool.
- OIDC provider trỏ tới issuer của CI.
- Attribute mapping để ánh xạ claim từ token sang thuộc tính Google.
- Attribute condition để giới hạn repository, ref hoặc workflow.
- IAM binding cho principal hoặc service account được phép sử dụng.

Ví dụ mapping ở mức khái niệm:

~~~text
google.subject = assertion.sub
attribute.repository = assertion.repository
attribute.ref = assertion.ref
~~~

Một điều kiện có thể yêu cầu repository đúng và ref là nhánh chính. Cú pháp và claim thực tế cần khớp provider đã cấu hình. Không dùng một điều kiện chỉ kiểm tra organization nếu nhiều repository trong tổ chức không được phép triển khai.

Workflow có thể gọi action xác thực Google Cloud với workload identity provider và service account đã được cấu hình. Quyền id-token: write vẫn cần thiết để GitHub Actions cấp token. Service account chỉ nên có vai trò tối thiểu cần cho nhiệm vụ deploy.

### Microsoft Entra ID và Azure

Azure hỗ trợ federated identity credential để liên kết issuer, subject và audience của workload với một application hoặc managed identity trong Microsoft Entra ID. Khi token hợp lệ, workload có thể lấy access token cho tài nguyên Azure mà không phải giữ client secret dài hạn.

Một federated credential cần khớp:

- Issuer URL của hệ thống CI.
- Subject đại diện cho repository/ref/environment.
- Audience được cấu hình cho token exchange, thường là api://AzureADTokenExchange trong luồng GitHub Actions.

Workflow có thể dùng azure/login với client ID, tenant ID và subscription ID; action dùng OIDC khi quyền id-token được cấp. Role assignment ở Azure quyết định workload được phép quản lý tài nguyên nào.

Subject và audience phải được kiểm tra theo federated credential thực tế. Một application có federated credential quá rộng có thể cho nhiều workflow không liên quan lấy access token.

## 9. Dùng OIDC với registry, Vault và Kubernetes

Không chỉ cloud provider mới có thể dùng OIDC. Một số dịch vụ khác cũng hỗ trợ workload identity:

### Container registry

Registry có thể chấp nhận token từ identity provider hoặc nhận credential tạm thời qua cloud identity. CI dùng danh tính được liên kết để push image vào đúng repository. Nên giới hạn quyền push theo project hoặc namespace và chỉ cho workflow phát hành tin cậy sử dụng.

### Secret manager hoặc Vault

Vault có thể xác minh JWT/OIDC token qua auth method, kiểm tra issuer, audience và bound claims rồi ánh xạ vào Vault role. Role có thể giới hạn repository, branch hoặc workflow và chỉ cấp policy đọc các secret path cần thiết.

Không nên cấp quyền đọc toàn bộ secret store cho mọi job trong một repository. Tạo role riêng cho test, staging và production với policy khác nhau.

### Kubernetes

Kubernetes có thể xác thực service account token theo OIDC trong một số kiến trúc, hoặc dùng cloud workload identity để ánh xạ service account sang IAM principal. Với CI deploy vào cluster, nên giới hạn quyền theo namespace và Kubernetes RBAC. Token có quyền cluster-admin không nên được cấp cho workflow build thông thường.

## 10. Thiết kế trust policy theo nguyên tắc least privilege

Một trust policy tốt cần giới hạn cả danh tính được tin và hành động được phép. Hãy kiểm tra các câu hỏi:

1. Issuer có đúng nền tảng CI dự kiến không?
2. Audience có đúng dịch vụ nhận token không?
3. Subject có giới hạn repository cụ thể không?
4. Branch, tag hoặc environment có được giới hạn không?
5. Workflow tái sử dụng hoặc workflow gọi từ nơi khác có được nhận diện không?
6. Token có được cấp cho pull request từ fork hoặc mã không tin cậy không?
7. Role/service account có quyền tối thiểu không?
8. Credential tạm thời có thời hạn phù hợp không?
9. Log có đủ thông tin để truy vết mà không làm lộ token không?

### Tránh wildcard quá rộng

Điều kiện dạng repo:acme/* có thể cho phép mọi repository trong tổ chức, tùy cách dịch vụ đích đánh giá subject. Nếu chỉ một repository cần deploy, hãy giới hạn đúng repository. Nếu chỉ nhánh main được phép, hãy thêm điều kiện branch/ref hoặc dùng environment có bảo vệ.

Wildcard có thể cần thiết cho một số mô hình nhiều repository, nhưng phải được thiết kế có chủ đích, có kiểm kê và review. Không dùng wildcard để xử lý lỗi cấu hình tạm thời.

### Tách role theo nhiệm vụ và môi trường

Một số role nên được tách:

| Role | Nguồn được phép | Quyền |
|---|---|---|
| CI read dependencies | Workflow kiểm tra được tin cậy | Đọc dependency hoặc registry |
| Image publisher | Workflow phát hành trên nhánh/tag được bảo vệ | Push image vào repository cụ thể |
| Staging deployer | Workflow staging | Triển khai staging |
| Production deployer | Workflow production qua environment có approval | Triển khai production |
| Release signer | Workflow phát hành được kiểm soát | Ký artifact/provenance theo phạm vi |

Tách role giúp một job bị chiếm quyền không tự động có quyền trên mọi môi trường.

## 11. Bảo vệ workflow và runner

OIDC giúp giảm credential dài hạn nhưng không ngăn một workflow độc hại tự yêu cầu token nếu job được cấp quyền. Kẻ tấn công có thể sửa workflow, chèn script, thay action hoặc khai thác runner để sử dụng danh tính được tin cậy.

Các biện pháp quan trọng:

- Chỉ cấp id-token: write cho job thực sự cần.
- Bảo vệ branch và workflow file bằng review bắt buộc.
- Dùng environment protection và reviewer cho production.
- Pin third-party action theo full commit SHA và review cập nhật.
- Không chạy mã pull request không tin cậy trong job có quyền deploy hoặc quyền OIDC production.
- Tránh dùng pull_request_target để checkout và thực thi mã do fork kiểm soát trong ngữ cảnh có quyền cao.
- Giới hạn quyền ghi của GITHUB_TOKEN và credential tạm thời.
- Dùng runner cô lập cho job nhạy cảm; tránh runner self-hosted dùng chung với workload không tin cậy.
- Không in JWT, access token hoặc response chứa credential vào log.
- Giới hạn network egress và quyền trên runner khi phù hợp.

### Cẩn trọng với pull request từ fork

Pull request từ fork có thể chứa thay đổi workflow hoặc script do người ngoài kiểm soát. Không cấp danh tính có quyền production cho mã chưa được review. Nếu cần kiểm tra pull request, dùng job quyền thấp chỉ build và test trong sandbox; việc deploy hoặc ký artifact phải diễn ra trong workflow tin cậy sau khi thay đổi được chấp nhận.

### Không chia sẻ token giữa các job nếu không cần

Token OIDC nên được yêu cầu ngay tại job cần dùng. Tránh tạo token ở một job rồi truyền qua artifact, output hoặc log cho job khác. Nếu job khác cần truy cập, hãy để job đó có quyền và trust policy riêng phù hợp với danh tính của nó.

## 12. Thời hạn, phạm vi và vòng đời credential tạm thời

OIDC token và credential được đổi từ token có thể có thời hạn khác nhau:

- OIDC token có exp do issuer đặt.
- STS hoặc cloud provider cấp access key/token tạm thời với thời hạn riêng.
- Dịch vụ đích có thể áp dụng thêm session policy hoặc giới hạn phiên.

Không giả định credential đích luôn hết hạn cùng lúc với OIDC token. Hãy xem thời hạn và cơ chế thu hồi của cả hai phía. Chọn thời gian đủ để hoàn thành tác vụ nhưng không dài hơn cần thiết.

Khi nghi ngờ workflow bị xâm phạm:

1. Vô hiệu hóa hoặc thu hẹp trust relationship liên quan.
2. Thu hồi session/credential tạm thời nếu dịch vụ hỗ trợ.
3. Dừng workflow và cô lập runner có dấu hiệu bị chiếm quyền.
4. Kiểm tra audit log của issuer, STS và target service.
5. Xác định repository, commit, run ID và tài nguyên đã bị truy cập.
6. Xoay vòng các secret khác có thể đã bị lộ.
7. Khôi phục trust policy sau khi nguyên nhân được xử lý.

Credential tạm thời vẫn có thể bị lạm dụng trong thời gian còn hiệu lực. Least privilege, thời hạn ngắn và audit log vẫn rất quan trọng.

## 13. Chẩn đoán lỗi OIDC federation

Khi token exchange thất bại, hãy kiểm tra theo lớp thay vì nới trust policy ngay:

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Không lấy được token | Job thiếu permission id-token: write | Kiểm tra quyền workflow/job và event |
| Issuer không khớp | URL issuer sai hoặc provider chưa đăng ký | So sánh iss với cấu hình provider |
| Audience mismatch | Token yêu cầu aud khác với dịch vụ đích | Kiểm tra audience trong action và trust policy |
| Subject mismatch | Repository, ref hoặc environment khác điều kiện | Đối chiếu sub thực tế với policy |
| Signature invalid | JWKS/key rotation hoặc token không đến từ issuer tin cậy | Kiểm tra discovery/JWKS và nguồn token |
| Token expired/not yet valid | Token cũ hoặc đồng hồ lệch | Yêu cầu token mới, kiểm tra thời gian |
| Assume role denied | Trust policy không cho phép principal hoặc claim | Kiểm tra provider ARN và điều kiện trust |
| Access denied sau khi assume | Role được xác thực nhưng thiếu quyền tài nguyên | Kiểm tra permission policy/RBAC |
| Chỉ lỗi trên environment | Subject thay đổi khi job tham chiếu environment | Kiểm tra subject format và protection rules |
| Chỉ lỗi với pull request | Event hoặc claim khác với push trên branch | Kiểm tra payload và trust boundary của PR |

### Không giải quyết lỗi bằng cách mở rộng wildcard

Nếu subject mismatch, trước tiên xác định token đang đại diện cho repository, ref, environment hoặc workflow nào. Sau đó sửa đúng điều kiện. Mở rộng policy cho mọi repository hoặc mọi branch có thể làm pipeline chạy được nhưng tạo ra quyền vượt phạm vi.

### Ghi log đủ nhưng không lộ token

Có thể log issuer, audience, subject đã được kiểm soát và mã lỗi từ STS để điều tra. Không ghi toàn bộ JWT hoặc access token vào log. Nếu cần xem claim để debug, dùng môi trường thử nghiệm, loại bỏ dữ liệu nhạy cảm và bảo đảm token không còn khả năng sử dụng.

## 14. Lộ trình triển khai OIDC trong nhóm

Một cách triển khai có kiểm soát:

1. **Kiểm kê credential hiện tại.** Xác định repository, workflow, secret và dịch vụ đích đang dùng credential dài hạn.
2. **Chọn workload cần chuyển trước.** Bắt đầu với một pipeline deploy ít rủi ro hoặc một môi trường staging.
3. **Đăng ký issuer/provider.** Cấu hình issuer và audience đúng theo nền tảng CI.
4. **Thiết kế trust policy hẹp.** Giới hạn repository, branch, workflow hoặc environment.
5. **Tạo role/service account riêng.** Cấp quyền tối thiểu cho đúng nhiệm vụ.
6. **Cấu hình job yêu cầu token.** Cấp permission OIDC chỉ ở job cần dùng và dùng action/SDK chính thức.
7. **Kiểm tra danh tính và quyền.** Gọi lệnh xác minh principal, thử hành động được phép và xác nhận hành động ngoài phạm vi bị từ chối.
8. **Bật audit và cảnh báo.** Theo dõi token exchange, assume role và truy cập tài nguyên.
9. **Loại bỏ credential dài hạn cũ.** Chỉ xóa sau khi luồng OIDC đã được xác minh và có phương án khôi phục.
10. **Mở rộng theo môi trường.** Tạo danh tính riêng cho staging, production, signing và các tác vụ khác.

Không nên chuyển tất cả repository cùng lúc nếu trust policy, runner và quy trình phê duyệt chưa được chuẩn hóa. Thử nghiệm theo phạm vi nhỏ giúp phát hiện claim mapping và quyền thừa trước khi mở rộng.

## 15. Checklist review một cấu hình OIDC

- [ ] Issuer là URL chính xác của identity provider đã được đăng ký.
- [ ] Audience chỉ dành cho dịch vụ đích dự kiến.
- [ ] Subject giới hạn đúng repository và branch/tag/environment.
- [ ] Claim mapping được kiểm tra bằng token thực tế hoặc tài liệu issuer.
- [ ] Chữ ký, thời hạn và key rotation được dịch vụ đích xác minh.
- [ ] Role/service account chỉ có quyền cần cho tác vụ.
- [ ] Credential tạm thời có thời hạn phù hợp.
- [ ] Chỉ job cần truy cập mới được cấp quyền yêu cầu token.
- [ ] Workflow production có branch protection và environment approval.
- [ ] Pull request không tin cậy không thể lấy danh tính có quyền cao.
- [ ] Action và runner được kiểm soát, log không chứa token.
- [ ] Audit log đủ để truy vết issuer, principal, run và tài nguyên.
- [ ] Có quy trình xử lý khi workflow hoặc runner bị xâm phạm.
- [ ] Credential dài hạn cũ được loại bỏ sau khi federation hoạt động ổn định.

OIDC giúp CI/CD chứng minh danh tính workload theo từng lần chạy và nhận quyền tạm thời từ dịch vụ đích. Khi issuer, audience, subject và trust policy được giới hạn đúng, pipeline có thể triển khai hoặc truy cập tài nguyên mà không cần lưu credential dài hạn dùng chung. Giá trị bảo mật đến từ toàn bộ chuỗi: bảo vệ workflow và runner, xác minh token, ánh xạ role chính xác, cấp quyền tối thiểu và ghi lại hoạt động để truy vết.
