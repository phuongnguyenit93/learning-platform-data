# Kiểm tra policy, secret và cấu hình an toàn trong IaC

Một nhóm triển khai ứng dụng Java trên AWS bằng CloudFormation. Template tạo IAM role cho Lambda, S3 bucket lưu tài liệu, DynamoDB table, RDS database, security groups và các secret mà ứng dụng cần. Template chạy được chưa có nghĩa là hạ tầng an toàn: một IAM policy có thể cấp quyền quá rộng, bucket có thể public, security group có thể mở cổng quản trị ra Internet, hoặc mật khẩu có thể bị commit vào Git.

Infrastructure as Code (IaC) biến hạ tầng thành mã nguồn có thể review, kiểm thử và tái tạo. Điều đó cũng có nghĩa một lỗi bảo mật trong template có thể được triển khai lặp lại trên nhiều môi trường. Vì vậy, kiểm tra bảo mật cần trở thành một phần của vòng đời phát triển: từ lúc viết template, qua pull request, trước khi tạo change set và trong quá trình vận hành.

Bài học thuộc chương **Hạ tầng dưới dạng mã** của module **CLOUD_PROVIDERS_AWS**. Chúng ta tập trung vào ba nhóm kiểm soát:

- **Policy:** IAM identity/resource policies, trust policies, quyền KMS, security group và guardrails.
- **Secret:** mật khẩu, API key, token, private key, dynamic references và vòng đời rotation.
- **Secure configuration:** encryption, public access, network exposure, logging, backup, validation và policy-as-code.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao template IaC phải được kiểm tra bảo mật trước khi triển khai.
2. Phân biệt identity policy, resource policy, trust policy, permissions boundary và SCP.
3. Thiết kế IAM policy theo least privilege và giới hạn quyền iam:PassRole.
4. Nhận diện wildcard, public principal, trust relationship và confused deputy risks.
5. Quản lý secret bằng AWS Secrets Manager, Systems Manager Parameter Store và CloudFormation dynamic references.
6. Giải thích giới hạn của NoEcho và vì sao không nên truyền secret qua parameter hoặc output.
7. Thiết kế rotation, runtime retrieval, caching và quyền đọc secret.
8. Thiết lập encryption, S3 public access block, TLS, security group và logging an toàn.
9. Dùng cfn-lint, CloudFormation Guard, IAM Access Analyzer và CloudFormation change sets để kiểm tra.
10. Tổ chức policy-as-code, security gates và xử lý ngoại lệ có thời hạn.
11. Phát hiện secret bị lộ trong Git, template, CI logs hoặc CloudFormation outputs.
12. Lập checklist bảo mật trước khi triển khai IaC lên production.

## 2. IaC security: kiểm tra từ mã nguồn đến runtime

Một template CloudFormation có thể hợp lệ về cú pháp nhưng vẫn tạo ra cấu hình nguy hiểm. Ví dụ, property SecurityGroupIngress có thể mở SSH cho toàn Internet; một role có thể được cấp s3:* trên mọi bucket; hoặc Lambda environment variable có thể chứa token được hard-code.

Nên kiểm tra ở nhiều giai đoạn:

| Giai đoạn | Kiểm tra | Mục tiêu |
|---|---|---|
| Authoring | Secure defaults, module dùng lại, review | Ngăn lỗi xuất hiện trong template |
| Pull request | Lint, policy-as-code, secret scan, IAM validation | Phát hiện lỗi trước merge |
| Pre-deployment | Change set, policy review, deployment role | Hiểu rõ thay đổi sắp áp dụng |
| Deployment | CloudFormation Hooks, SCP, IAM, permissions boundary | Chặn cấu hình không đạt yêu cầu |
| Runtime | AWS Config, Security Hub, CloudTrail, drift detection | Phát hiện drift và vi phạm sau triển khai |
| Incident response | Rotate/revoke secret, rollback, audit | Giảm tác động và khôi phục |

Không có một công cụ đơn lẻ phát hiện mọi lỗi. Linter tìm lỗi cấu trúc và một số cấu hình; policy-as-code kiểm tra quy tắc tổ chức; IAM Access Analyzer kiểm tra policy semantics; runtime controls phát hiện trạng thái thực tế.

## 3. Mô hình policy trong AWS

Trước khi viết policy, cần biết policy đó gắn ở đâu và bảo vệ điều gì.

| Loại policy | Gắn với | Mục đích |
|---|---|---|
| Identity-based policy | IAM user, group, role | Quy định principal được gọi action nào trên resource nào |
| Resource-based policy | S3 bucket, KMS key, SQS queue, Lambda function... | Quy định principal nào được truy cập resource |
| Trust policy | IAM role | Quy định principal nào được AssumeRole |
| Permissions boundary | IAM user/role | Giới hạn quyền tối đa mà identity policy có thể cấp |
| Service Control Policy (SCP) | AWS Organizations account/OU/root | Đặt giới hạn quyền tối đa cho account/member account |
| Session policy | STS session | Thu hẹp quyền của session cụ thể |

IAM evaluation có nhiều lớp. Explicit Deny luôn thắng Allow. Một Allow trong identity policy không đảm bảo request thành công nếu resource policy, permissions boundary, SCP, session policy hoặc điều kiện khác không cho phép.

SCP không tự cấp quyền. SCP đặt trần quyền cho principal trong member account; identity/resource policy vẫn cần cấp quyền phù hợp. SCP không áp dụng theo cách tương tự cho management account và một số service-linked roles có ngoại lệ theo tài liệu AWS.

## 4. Least privilege cho IAM identity policy

Nguyên tắc least privilege là chỉ cấp đúng action, resource và condition cần thiết cho workload.

Một policy quá rộng:

    {
      "Version": "2012-10-17",
      "Statement": [
        {
          "Effect": "Allow",
          "Action": "*",
          "Resource": "*"
        }
      ]
    }

Policy này cho principal quyền trên rất nhiều dịch vụ và tài nguyên. Nếu credentials bị lộ hoặc workload bị xâm nhập, phạm vi thiệt hại có thể rất lớn.

Ví dụ role chỉ cần đọc object trong một bucket:

    {
      "Version": "2012-10-17",
      "Statement": [
        {
          "Sid": "ReadInvoiceObjects",
          "Effect": "Allow",
          "Action": [
            "s3:GetObject"
          ],
          "Resource": "arn:aws:s3:::company-invoices-prod/*"
        }
      ]
    }

Nếu workload cần liệt kê bucket, cần thêm s3:ListBucket trên ARN bucket, thường kèm điều kiện prefix nếu phù hợp. S3 bucket ARN và object ARN là hai loại resource khác nhau.

### 4.1. Wildcard không phải lúc nào cũng sai, nhưng phải có lý do

Một số action không hỗ trợ resource-level permissions và buộc phải dùng Resource: "*". Một số service yêu cầu wildcard cho một phạm vi action nhất định. Vì vậy, không áp dụng quy tắc máy móc rằng mọi dấu sao đều là lỗi.

Khi thấy wildcard, reviewer cần hỏi:

- Action có hỗ trợ resource-level permission không?
- Có thể giới hạn theo ARN, account, Region, tag hoặc condition không?
- Có cần quyền ghi/xóa hay workload chỉ cần đọc?
- Quyền có áp dụng cho mọi môi trường và tenant không?
- Có thể tách statement theo resource/action để giảm phạm vi không?

Dùng policy theo chức năng của workload, không dùng AdministratorAccess cho ứng dụng chỉ để tránh lỗi AccessDenied.

### 4.2. Tách quyền quản trị và quyền runtime

Một Lambda xử lý hóa đơn thường chỉ cần đọc object, ghi log và truy cập secret cụ thể. Nó không cần quyền tạo IAM role, sửa bucket policy hoặc xóa database.

Tách các vai trò:

- Deployment role: tạo và cập nhật resource trong phạm vi stack.
- Runtime role: quyền ứng dụng cần khi chạy.
- Break-glass/admin role: quyền quản trị đặc biệt, có kiểm soát và audit.
- Read-only/audit role: kiểm tra cấu hình và log.

Không tái sử dụng deployment role làm execution role của ứng dụng.

## 5. Trust policy và quyền AssumeRole

Trust policy quyết định ai được phép nhận temporary credentials của role. Ví dụ role cho Lambda service:

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

Trust policy không phải permission policy. Nó không cấp quyền truy cập S3 hoặc DynamoDB; nó chỉ xác định principal nào được assume role.

### 5.1. Cross-account access

Khi một role ở account A được assume từ account B, cần cấu hình cả hai phía:

1. Trust policy của role ở account A cho phép principal/role ở account B.
2. Identity policy của principal ở account B cho phép sts:AssumeRole tới role ARN ở account A.
3. Các condition như ExternalId, MFA hoặc source identity được dùng nếu phù hợp với mô hình trust.

Với third-party SaaS truy cập account của khách hàng, ExternalId giúp giảm confused deputy risk. Không dùng một ExternalId cố định chung cho mọi khách hàng nếu mỗi tenant cần định danh riêng.

### 5.2. Service principal và confused deputy

Khi cho AWS service principal truy cập resource, giới hạn nguồn gọi bằng condition nếu service hỗ trợ. Ví dụ resource policy hoặc role trust policy có thể dùng aws:SourceArn và aws:SourceAccount để ràng buộc resource/account được phép gọi.

Không thêm condition một cách máy móc: tên condition và khả năng hỗ trợ phụ thuộc service và integration. Đối chiếu tài liệu của service cụ thể trước khi áp dụng.

## 6. Kiểm soát iam:PassRole

iam:PassRole cho phép principal truyền một IAM role cho AWS service để service chạy workload bằng role đó. Nếu quyền này quá rộng, người triển khai có thể tạo hoặc sửa resource để sử dụng một role có quyền cao hơn.

Một policy có phạm vi hẹp:

    {
      "Version": "2012-10-17",
      "Statement": [
        {
          "Effect": "Allow",
          "Action": "iam:PassRole",
          "Resource": "arn:aws:iam::123456789012:role/app-lambda-runtime",
          "Condition": {
            "StringEquals": {
              "iam:PassedToService": "lambda.amazonaws.com"
            }
          }
        }
      ]
    }

Thay account ID và role ARN bằng giá trị của môi trường triển khai. Không cấp iam:PassRole trên mọi role nếu deployment chỉ cần truyền một số role xác định.

Review cả quyền iam:CreateRole, iam:AttachRolePolicy, iam:PutRolePolicy và iam:UpdateAssumeRolePolicy. Một principal có thể tạo một role mới, gắn quyền mạnh rồi pass role đó cho service nếu các quyền này không được kiểm soát.

## 7. Resource policy: kiểm tra Principal và Condition

Resource policy thường gặp ở S3, KMS, SQS, SNS, Lambda và Secrets Manager.

Ví dụ S3 bucket policy chỉ cho phép request qua HTTPS:

    {
      "Version": "2012-10-17",
      "Statement": [
        {
          "Sid": "DenyInsecureTransport",
          "Effect": "Deny",
          "Principal": "*",
          "Action": "s3:*",
          "Resource": [
            "arn:aws:s3:::company-invoices-prod",
            "arn:aws:s3:::company-invoices-prod/*"
          ],
          "Condition": {
            "Bool": {
              "aws:SecureTransport": "false"
            }
          }
        }
      ]
    }

Principal wildcard trong statement Deny ở ví dụ này không mở public access; nó từ chối request không dùng TLS. Khi review policy, phải đọc cả Effect, Principal, Action, Resource và Condition thay vì chỉ tìm ký tự "*".

Với policy có Effect Allow và Principal "*", cần xác minh rất kỹ điều kiện truy cập. Public access có thể xuất hiện từ bucket policy, ACL hoặc cấu hình khác. Với S3 hiện đại, bật Block Public Access và Bucket owner enforced ownership controls khi phù hợp.

## 8. KMS key policy và quyền giải mã

KMS key policy quyết định principal nào có thể sử dụng hoặc quản trị customer managed key. Identity policy có Allow kms:Decrypt nhưng key policy không cho phép principal đó thì thao tác vẫn có thể bị từ chối.

Tách quyền:

- Key administrators: quản lý key policy, rotation, enable/disable và lifecycle.
- Key users: sử dụng key cho Encrypt/Decrypt/GenerateDataKey trong phạm vi cần thiết.
- Application role: chỉ dùng key của resource/workload cụ thể.

Ví dụ giới hạn việc giải mã chỉ qua Secrets Manager ở Region phù hợp:

    {
      "Effect": "Allow",
      "Action": [
        "kms:Decrypt"
      ],
      "Resource": "arn:aws:kms:ap-southeast-1:123456789012:key/11111111-2222-3333-4444-555555555555",
      "Condition": {
        "StringEquals": {
          "kms:ViaService": "secretsmanager.ap-southeast-1.amazonaws.com"
        }
      }
    }

Đây là minh họa cho một workload cụ thể. KMS key policy, grants, encryption context và service integration phải được thiết kế đồng bộ. Không copy ARN/Region ví dụ vào production.

Không cấp kms:* trên mọi key cho runtime role. Cũng cần bảo vệ quyền sửa key policy: một người có thể tự mở rộng quyền nếu được phép thay key policy không kiểm soát.

## 9. Secrets: nhận diện và phân loại dữ liệu nhạy cảm

Secret là dữ liệu cho phép xác thực, ký hoặc truy cập hệ thống:

- Database password.
- API key và OAuth client secret.
- Access key dài hạn.
- Private key, certificate private material.
- Signing key, webhook secret.
- Token của dịch vụ bên thứ ba.

Không phải mọi cấu hình đều là secret. Region, table name, feature flag và endpoint nội bộ thường là configuration; tuy nhiên vẫn cần đánh giá xem chúng có tiết lộ thông tin nhạy cảm hay không.

Phân loại giúp chọn cách lưu trữ và quyền truy cập:

| Dữ liệu | Nơi lưu phù hợp |
|---|---|
| Password/API key cần rotation và audit | AWS Secrets Manager |
| Giá trị cấu hình thường | SSM Parameter Store String |
| Secret đơn giản cần mã hóa bằng KMS | SSM Parameter Store SecureString |
| Database master password cho RDS được hỗ trợ | RDS managed master user password với Secrets Manager |
| Certificate/private key | Secrets Manager hoặc dịch vụ quản lý certificate phù hợp |
| Temporary AWS credentials | IAM role/STS, không lưu thành secret tĩnh |

Không lưu AWS access key dài hạn trong template hoặc file cấu hình ứng dụng. Workload trên Lambda, ECS, EKS hoặc EC2 nên dùng IAM role/workload identity để nhận temporary credentials.

## 10. AWS Secrets Manager và Parameter Store

### 10.1. AWS Secrets Manager

Secrets Manager phù hợp khi cần:

- Lưu secret có cấu trúc hoặc secret string.
- Kiểm soát truy cập bằng IAM và resource policy.
- Mã hóa bằng AWS KMS.
- Audit việc truy cập qua CloudTrail.
- Rotation tự động hoặc rotation workflow tùy secret/service.
- Quản lý version và staging labels như AWSCURRENT, AWSPREVIOUS.

Một template có thể tạo secret với giá trị được sinh tự động:

    Resources:
      ApplicationDatabaseSecret:
        Type: AWS::SecretsManager::Secret
        Properties:
          Name: app/prod/database
          GenerateSecretString:
            SecretStringTemplate: '{"username":"appuser"}'
            GenerateStringKey: password
            PasswordLength: 32
            ExcludePunctuation: true

Template không chứa mật khẩu tĩnh. Secrets Manager tạo secret string theo cấu hình và lưu giá trị được sinh. Quyền đọc secret cần được cấp riêng cho runtime role.

### 10.2. Systems Manager Parameter Store

Parameter Store phù hợp cho configuration tập trung. Parameter có thể là String, StringList hoặc SecureString tùy cách tạo và API sử dụng.

- String/ StringList: cấu hình không bí mật.
- SecureString: giá trị được mã hóa bằng KMS.
- Parameter hierarchy: nhóm cấu hình theo ứng dụng, môi trường và thành phần.
- IAM: giới hạn path và action như ssm:GetParameter, ssm:GetParameters.

SecureString không tự tạo rotation workflow như Secrets Manager. Nếu password/API key cần tự động rotation và quản lý version/staging lifecycle, cân nhắc Secrets Manager.

Không lưu secret trong parameter name hoặc tag. Metadata cũng có thể bị lộ qua quyền đọc mô tả resource.

## 11. CloudFormation parameters và giới hạn của NoEcho

CloudFormation hỗ trợ NoEcho để che giá trị parameter trong một số API responses và giao diện hiển thị.

    Parameters:
      DatabasePassword:
        Type: String
        NoEcho: true
        MinLength: 16

NoEcho không phải secret manager:

- Nó không mã hóa giá trị trong template.
- Nó không xóa secret khỏi Git, CI logs hoặc shell history.
- Nó không bảo vệ giá trị nếu được ghi vào Metadata hoặc Outputs.
- Nó không biến mọi resource property nhận giá trị thành nơi lưu trữ bí mật an toàn.
- Người có quyền truy cập runtime/resource có thể vẫn đọc được giá trị qua service API hoặc ứng dụng.

Không đặt password mặc định trong Parameters. Không truyền secret qua command line nếu có thể tránh vì process arguments và shell history có thể bị ghi lại.

Không đưa secret vào Outputs, Metadata, tags, resource names hoặc stack descriptions. Hãy dùng secret store và chỉ tham chiếu tới secret khi service/property hỗ trợ.

## 12. CloudFormation dynamic references

Dynamic references cho phép CloudFormation lấy giá trị từ Secrets Manager hoặc Systems Manager Parameter Store khi triển khai resource property. Template giữ reference string thay vì chứa trực tiếp secret value.

### 12.1. Secrets Manager dynamic reference

Cú pháp tổng quát:

    {{resolve:secretsmanager:secret-id:SecretString:json-key:version-stage:version-id}}

Ví dụ lấy trường password từ secret JSON:

    Resources:
      LegacyDatabase:
        Type: AWS::RDS::DBInstance
        Properties:
          Engine: mysql
          DBInstanceClass: db.t3.micro
          MasterUsername: appuser
          MasterUserPassword: '{{resolve:secretsmanager:app/prod/database:SecretString:password}}'

Secret cần tồn tại và deployment principal/CloudFormation service role phải có quyền đọc secret cùng quyền KMS cần thiết. Ví dụ chỉ minh họa dynamic reference; production RDS nên cân nhắc tích hợp quản lý master password trực tiếp.

### 12.2. SSM SecureString dynamic reference

Cú pháp:

    {{resolve:ssm-secure:parameter-name:version}}

Ví dụ:

    MasterUserPassword: '{{resolve:ssm-secure:/app/prod/database/password:7}}'

Version là tùy chọn. Khi không chỉ định version, CloudFormation dùng version hiện hành theo cơ chế dynamic reference của Parameter Store.

### 12.3. Dynamic references không phải runtime secret retrieval

CloudFormation phân giải dynamic reference trong quá trình tạo hoặc cập nhật resource property. Ứng dụng đang chạy không tự động gọi CloudFormation để lấy secret mới.

Khi secret rotation diễn ra:

- Secret trong Secrets Manager có thể đã chuyển AWSCURRENT sang version mới.
- Resource nhận secret qua dynamic reference không nhất thiết tự được cập nhật ngay.
- CloudFormation không tự tạo stack update chỉ vì secret version thay đổi.
- Với resource cần password đồng bộ, phải có rotation integration phù hợp hoặc workflow cập nhật resource an toàn.

Dynamic references cũng không được hỗ trợ trong mọi ngữ cảnh và mọi resource property. Kiểm tra giới hạn của dynamic references, đặc biệt với custom resources và các trường metadata/init, trước khi dùng.

### 12.4. Khi nào nên dùng RDS managed master password?

Với RDS DB instance hỗ trợ, có thể để RDS quản lý master password qua Secrets Manager:

    Resources:
      ApplicationDatabase:
        Type: AWS::RDS::DBInstance
        Properties:
          Engine: postgres
          DBInstanceClass: db.t3.micro
          AllocatedStorage: "20"
          MasterUsername: dbadmin
          ManageMasterUserPassword: true
          StorageEncrypted: true
          PubliclyAccessible: false

Cách này tránh truyền master password qua template. RDS tạo và quản lý secret liên kết. Cần kiểm tra engine, version và loại DB instance hỗ trợ property này. Với Aurora, cấu hình quản lý mật khẩu ở resource DB cluster phù hợp.

## 13. Ứng dụng lấy secret lúc runtime

Đối với ứng dụng Java, thường nên để workload identity/IAM role đọc secret khi cần, thay vì đưa password vào template hoặc build artifact.

Luồng tham khảo:

    Spring Boot service
        |
        | AWS SDK for Java 2.x
        v
    AWS Secrets Manager
        |
        | GetSecretValue
        v
    Secret value (in memory)
        |
        v
    Database connection pool

Runtime role chỉ cần secretsmanager:GetSecretValue trên secret ARN cụ thể. Nếu dùng customer managed KMS key, cần quyền kms:Decrypt theo key policy và condition phù hợp.

### 13.1. Caching và rotation

Không gọi Secrets Manager cho mọi SQL query. Dùng cache có TTL hợp lý hoặc AWS Secrets Manager caching client phù hợp ngôn ngữ. TTL cần cân bằng chi phí, latency và tốc độ nhận secret mới sau rotation.

Khi secret rotation:
1. Tạo credential/version mới.
2. Cập nhật database hoặc hệ thống đích theo rotation workflow.
3. Chuyển staging label/current version theo quy trình.
4. Ứng dụng lấy secret mới khi cache hết hạn hoặc refresh.
5. Connection pool cần xử lý connection cũ và tạo connection mới.
6. Chỉ vô hiệu hóa credential cũ sau khi xác minh workload đã chuyển.

Đừng cache vô thời hạn. Đừng log secret khi parse lỗi hoặc khi kết nối database thất bại. Không đưa secret vào exception message, metrics label hoặc tracing baggage.

## 14. Secret scanning và xử lý secret bị lộ

Secret scan nên chạy trên cả diff và repository history. Công cụ có thể phát hiện AWS access key pattern, private key, token phổ biến và entropy cao, nhưng false positives vẫn có thể xảy ra.

Các lựa chọn gồm:

- GitHub secret scanning hoặc công cụ tương đương trong nền tảng Git.
- Gitleaks.
- TruffleHog.
- Secret scanning của CI/security platform.

Khi phát hiện secret trong Git:

1. Xác định secret loại gì, môi trường nào và quyền nào được cấp.
2. Revoke hoặc rotate credential ngay theo mức độ rủi ro.
3. Kiểm tra CloudTrail/service logs để xác định dấu hiệu sử dụng bất thường.
4. Thay ứng dụng sang secret mới và xác minh.
5. Xóa secret khỏi source và history theo quy trình tổ chức; lưu ý rewrite history không làm credential cũ mất hiệu lực.
6. Kiểm tra fork, artifact, CI logs, cache và bản sao repository.
7. Ghi nhận incident và nguyên nhân gốc để bổ sung rule.

**Xóa một dòng khỏi Git không làm secret cũ an toàn trở lại.** Rotation/revocation là bước quan trọng nhất.

## 15. Secure defaults cho S3

S3 bucket thường lưu dữ liệu nhạy cảm, nên template nên đặt các kiểm soát rõ ràng:

    Resources:
      PrivateDocumentsBucket:
        Type: AWS::S3::Bucket
        Properties:
          PublicAccessBlockConfiguration:
            BlockPublicAcls: true
            IgnorePublicAcls: true
            BlockPublicPolicy: true
            RestrictPublicBuckets: true
          OwnershipControls:
            Rules:
              - ObjectOwnership: BucketOwnerEnforced
          BucketEncryption:
            ServerSideEncryptionConfiguration:
              - ServerSideEncryptionByDefault:
                  SSEAlgorithm: aws:kms
                  KMSMasterKeyID: !Ref DataEncryptionKey
                BucketKeyEnabled: true
          VersioningConfiguration:
            Status: Enabled

Các property trên giúp giảm nguy cơ public access, ACL ownership ambiguity và lưu object không mã hóa theo yêu cầu. Encryption at rest không thay access control; principal vẫn cần quyền phù hợp.

### 15.1. TLS-only bucket policy

Có thể thêm explicit Deny với aws:SecureTransport=false để từ chối request không dùng TLS. Đảm bảo bucket policy bao gồm bucket ARN và object ARN phù hợp.

### 15.2. Logging và data protection

Cân nhắc CloudTrail data events cho object-level audit, access logging theo yêu cầu, Versioning, lifecycle cho noncurrent versions và Object Lock khi cần retention bất biến. Data events có thể làm tăng chi phí; bật theo phạm vi bucket/prefix và nhu cầu audit.

## 16. Secure defaults cho database, queue và volume

| Resource | Kiểm soát nên xem xét |
|---|---|
| RDS | StorageEncrypted, KmsKeyId, PubliclyAccessible=false, private subnets, DeletionProtection, backup retention, security group hẹp |
| DynamoDB | SSESpecification, PITR, IAM table/index ARN, condition và backup |
| EBS | Encrypted=true, KmsKeyId nếu cần CMK, snapshot policy, volume gắn đúng AZ |
| SQS | SSE/KMS khi cần, queue policy hẹp, TLS enforcement, DLQ/redrive policy |
| SNS | KMS encryption khi phù hợp, topic policy hẹp, TLS và subscription control |
| ECR | Image scanning, encryption, immutable tags nếu quy trình hỗ trợ |
| Lambda | Execution role least privilege, environment không chứa secret tĩnh, VPC chỉ khi cần, logging và tracing |
| EC2 | Instance profile, IMDSv2, EBS encryption, private networking và security group hẹp |

Ví dụ RDS cần tránh public access:

    Resources:
      AppDatabase:
        Type: AWS::RDS::DBInstance
        Properties:
          PubliclyAccessible: false
          StorageEncrypted: true
          DeletionProtection: true

Không phải mọi resource đều dùng cùng property hoặc cùng cơ chế encryption. Đối chiếu resource specification và service documentation trước khi copy cấu hình.

## 17. Network security trong IaC

Security group là stateful firewall ở cấp network interface/resource. Rule cần phản ánh luồng thực sự của ứng dụng.

Ví dụ database chỉ nhận kết nối PostgreSQL từ security group của application:

    Resources:
      DatabaseIngress:
        Type: AWS::EC2::SecurityGroupIngress
        Properties:
          GroupId: !Ref DatabaseSecurityGroup
          IpProtocol: tcp
          FromPort: 5432
          ToPort: 5432
          SourceSecurityGroupId: !Ref ApplicationSecurityGroup

Tránh các rule như:

- SSH TCP/22 từ 0.0.0.0/0 hoặc ::/0.
- RDP TCP/3389 từ Internet.
- Database port mở tới toàn Internet.
- All traffic mở tới mọi CIDR mà không có lý do.
- Egress unrestricted trong môi trường yêu cầu egress control chặt chẽ.

Không phải mọi workload đều cần subnet public. Database và internal services thường đặt ở private subnets; public entry point có thể là ALB/API Gateway/WAF theo kiến trúc.

Dùng VPC endpoints khi phù hợp để workload truy cập AWS services qua private connectivity. Endpoint policy và resource policy vẫn cần được review.

## 18. Kiểm tra CloudFormation template bằng cfn-lint

cfn-lint kiểm tra template theo CloudFormation resource specifications và các rule về cấu trúc, property, intrinsic functions và một số best practices.

Cài đặt và chạy trong môi trường phát triển/CI theo quy trình của dự án:

    pip install cfn-lint
    cfn-lint template.yaml

Có thể chỉ định template nhiều file hoặc format khác theo phiên bản công cụ. Không dùng lint pass làm bằng chứng template an toàn: cfn-lint không thay IAM review, secret scan, threat modeling hoặc policy-as-code.

CloudFormation cũng có lệnh validate-template:

    aws cloudformation validate-template \
      --template-body file://template.yaml

Lệnh này giúp kiểm tra template có thể được CloudFormation đọc/validate ở mức cơ bản. Nó không đảm bảo mọi resource sẽ provision thành công và không chứng minh cấu hình bảo mật đạt yêu cầu.

## 19. Policy-as-code với CloudFormation Guard

CloudFormation Guard cho phép viết rule để kiểm tra template theo quy định tổ chức. Ví dụ, yêu cầu S3 bucket có public access block:

    let s3_buckets = Resources.*[ Type == "AWS::S3::Bucket" ]

    rule s3_buckets_block_public_access when %s3_buckets !empty {
      %s3_buckets.Properties.PublicAccessBlockConfiguration.BlockPublicAcls == true
      %s3_buckets.Properties.PublicAccessBlockConfiguration.IgnorePublicAcls == true
      %s3_buckets.Properties.PublicAccessBlockConfiguration.BlockPublicPolicy == true
      %s3_buckets.Properties.PublicAccessBlockConfiguration.RestrictPublicBuckets == true
    }

Một rule khác có thể yêu cầu encryption:

    rule s3_buckets_use_encryption when %s3_buckets !empty {
      %s3_buckets.Properties.BucketEncryption.ServerSideEncryptionConfiguration[*].ServerSideEncryptionByDefault.SSEAlgorithm
        IN ["AES256", "aws:kms"]
    }

Chạy validate:

    cfn-guard validate \
      --rules security-rules.guard \
      --data template.yaml

Rule có thể cần điều chỉnh theo version Guard, cấu trúc template, conditional resources và quy ước tổ chức. Kiểm thử rule bằng positive/negative fixtures để bảo đảm rule bắt được lỗi cần bắt mà không chặn nhầm template hợp lệ.

### 19.1. Ví dụ rule cho RDS

Tổ chức có thể yêu cầu DB instance không public và bật storage encryption:

    let db_instances = Resources.*[ Type == "AWS::RDS::DBInstance" ]

    rule rds_instances_are_private when %db_instances !empty {
      %db_instances.Properties.PubliclyAccessible == false
      %db_instances.Properties.StorageEncrypted == true
    }

Không áp dụng rule cho loại resource không có property tương ứng. Với điều kiện hoặc giá trị kế thừa từ parameter, rule cần được viết để xử lý đúng cách; không coi thiếu property luôn đồng nghĩa an toàn.

## 20. IAM policy validation với Access Analyzer

IAM Access Analyzer có chức năng validate policy để phát hiện lỗi grammar, security warnings, general warnings và suggestions.

Ví dụ kiểm tra identity policy:

    aws accessanalyzer validate-policy \
      --policy-document file://runtime-policy.json \
      --policy-type IDENTITY_POLICY

Với resource-based policy, chọn policy type tương ứng và cung cấp resource type nếu API yêu cầu. Kết quả cần được đọc theo finding type:

- ERROR: policy có lỗi cần xử lý.
- SECURITY_WARNING: có rủi ro bảo mật cần review.
- WARNING: vấn đề hoặc hành vi cần chú ý.
- SUGGESTION: đề xuất cải thiện.

Access Analyzer validation không thay kiểm thử quyền thực tế. Dùng IAM policy simulator, staging account và integration tests để xác minh workload vẫn có đủ quyền tối thiểu.

## 21. CloudFormation Hooks và guardrails khi triển khai

Policy-as-code trong CI giúp phát hiện sớm, nhưng một người có thể deploy từ một pipeline khác. CloudFormation Hooks có thể kiểm tra resource trước các lifecycle operation được hỗ trợ và đưa ra cảnh báo hoặc chặn operation tùy cấu hình hook.

Các lớp guardrail nên kết hợp:

- CI lint/Guard/Access Analyzer.
- CloudFormation Hooks ở môi trường deployment.
- SCP/permissions boundary để giới hạn quyền.
- IAM deployment role theo least privilege.
- AWS Config rules hoặc conformance packs để phát hiện drift/vi phạm.
- Security Hub để tổng hợp security findings.

Không giả định một Guard rule trong CI tự động được áp dụng cho mọi CloudFormation stack. Phải bảo vệ đường triển khai và kiểm tra cả những thay đổi được thực hiện ngoài pipeline chuẩn.

## 22. Secret và policy trong pipeline CI/CD

Pipeline có thể trở thành đường rò rỉ secret nếu:

- In toàn bộ environment variables.
- Bật shell tracing với lệnh chứa token.
- Truyền secret qua command-line argument.
- Upload file cấu hình đã render vào artifact công khai.
- Lưu plan/template với secret đã nội suy.
- Dùng credential dài hạn của IAM user.
- Chạy job từ fork/untrusted pull request nhưng vẫn cấp quyền production.

Thiết kế pipeline:

1. Dùng OIDC/federated identity để lấy temporary AWS credentials nếu nền tảng CI hỗ trợ.
2. Dùng role riêng cho build, test và deploy.
3. Không cấp production secrets cho pull request từ fork hoặc untrusted branch.
4. Lấy secret vào runtime của job khi cần, giới hạn thời gian tồn tại và quyền đọc.
5. Tắt shell debug/tracing ở đoạn xử lý secret.
6. Mask secret trong log, nhưng không coi masking là biện pháp bảo vệ duy nhất.
7. Không lưu secret trong artifact, cache hoặc test report.
8. Audit CloudTrail và CI job identity.

## 23. Change set và review bảo mật trước deployment

Change set cho biết CloudFormation dự định thêm, sửa, xóa hoặc thay thế resource. Đây là điểm kiểm tra quan trọng trước khi apply.

Review các thay đổi:

- IAM role/policy mới có tăng quyền không?
- Trust policy có thêm principal hoặc bỏ condition không?
- Resource policy có mở public/cross-account access không?
- Secret reference có bị thay bằng plaintext không?
- Encryption key có đổi hoặc bị bỏ không?
- S3 bucket có thay đổi PublicAccessBlock, ACL, ownership hoặc policy không?
- RDS có thành public hoặc tắt deletion protection không?
- Security group có mở thêm port/CIDR không?
- Resource dữ liệu có bị replacement/deletion không?
- KMS key policy/grant có bị mở rộng không?

Change set không phát hiện mọi vấn đề bảo mật và không đảm bảo runtime outcome. Kết hợp change set với lint, Guard, Access Analyzer và review thủ công.

## 24. Drift detection và kiểm tra cấu hình runtime

IaC mô tả trạng thái mong muốn; người vận hành hoặc service có thể thay đổi resource trực tiếp. CloudFormation drift detection giúp so sánh một số property thực tế với template.

Drift detection có giới hạn:

- Không phải mọi resource/property đều hỗ trợ drift detection.
- Một số property bị loại trừ hoặc không thể so sánh.
- Dynamic references không có nghĩa drift detection sẽ phát hiện secret rotation hay so sánh được plaintext đã phân giải.
- Drift detection không thay thế AWS Config, CloudTrail hoặc service-specific audit.

Dùng AWS Config để kiểm tra các yêu cầu như S3 public access, encryption, security group exposure, RDS public access và logging. Kiểm tra coverage và recording scope của Config; một rule không thể đánh giá resource nếu resource type chưa được ghi nhận.

## 25. Ngoại lệ policy và quy trình xử lý

Có thể có workload cần quyền hoặc cấu hình đặc biệt. Không nên tạo exception vĩnh viễn chỉ vì một template không qua gate.

Mỗi exception nên có:

- Resource/stack/account/Region cụ thể.
- Rule bị vi phạm và lý do nghiệp vụ.
- Người chịu trách nhiệm.
- Phạm vi ảnh hưởng và đánh giá rủi ro.
- Biện pháp bù trừ.
- Ngày hết hạn hoặc ngày review.
- Bằng chứng kiểm thử và phê duyệt.

Ví dụ, một S3 bucket cần public read để phân phối nội dung tĩnh phải có architecture review, WAF/CDN strategy và phạm vi object rõ ràng. Nếu CloudFront là điểm phân phối, ưu tiên Origin Access Control và bucket private thay vì mở bucket trực tiếp.

## 26. Quy trình xử lý sự cố secret hoặc policy bị lộ

### 26.1. Secret bị lộ

1. Revoke/rotate secret hoặc access key.
2. Xác định principal, resource, account và thời gian có thể bị ảnh hưởng.
3. Kiểm tra CloudTrail, Secrets Manager access events và service logs.
4. Kiểm tra dấu hiệu persistence hoặc resource bất thường.
5. Cập nhật ứng dụng và xác minh credential mới hoạt động.
6. Xóa secret khỏi template, Git, artifact và CI logs theo quy trình.
7. Thêm secret scan và policy gate để ngăn tái diễn.

### 26.2. IAM policy cấp quyền quá rộng

1. Xác định role/user và resource/action bị cấp rộng.
2. Kiểm tra CloudTrail để tìm quyền đã được sử dụng.
3. Tạo policy hẹp hơn dựa trên workload access thực tế.
4. Kiểm thử trong staging và triển khai có kiểm soát.
5. Thu hồi policy cũ và xác minh ứng dụng vẫn hoạt động.
6. Kiểm tra các role khác có cùng pattern.
7. Thêm rule tự động cho lỗi đã phát hiện.

Không xóa quyền đang dùng trong production mà chưa hiểu dependency. Trong incident nghiêm trọng, containment có thể ưu tiên hơn availability; quyết định cần theo incident response process của tổ chức.

## 27. Ví dụ pipeline kiểm tra IaC

Một pipeline đơn giản có thể chạy các bước sau trước deployment:

    1. Checkout source
    2. Secret scan trên diff và repository
    3. cfn-lint template.yaml
    4. cfn-guard validate --rules security-rules.guard --data template.yaml
    5. IAM Access Analyzer validate-policy cho từng IAM policy
    6. CloudFormation validate-template
    7. Tạo change set
    8. Review findings và change set
    9. Approve deployment
    10. Execute change set
    11. AWS Config / runtime security checks

Mỗi gate nên có output có thể truy vết: commit SHA, template version, rule-set version, tool version, findings, exception ID và deployment identity.

Không bỏ qua finding chỉ để pipeline xanh. Nếu finding được chấp nhận, phải ghi exception có owner và thời hạn.

## 28. Bài tập tình huống

### Bài A — IAM policy có Action: "*" và Resource: "*"

Một Lambda chỉ cần đọc object từ một bucket nhưng role được cấp toàn quyền.

**Đáp án:** thay bằng s3:GetObject trên object ARN cần thiết và s3:ListBucket nếu ứng dụng thật sự cần liệt kê bucket. Tách quyền log và secret thành statements riêng.

### Bài B — Trust policy cho phép Principal "*"

Một role có trust policy cho phép mọi principal trong policy.

**Đáp án:** xác định workload principal cụ thể, giới hạn account/role và thêm condition phù hợp. Nếu cross-account third-party, đánh giá ExternalId và confused deputy risk.

### Bài C — iam:PassRole trên mọi role

Deployment role có iam:PassRole Resource "*".

**Đáp án:** giới hạn role ARN được phép pass và dùng iam:PassedToService khi phù hợp. Review cả quyền tạo/sửa role và gắn policy.

### Bài D — Password nằm trong template

Một developer ghi password trực tiếp trong CloudFormation Properties.

**Đáp án:** rotate nếu đã commit/chia sẻ; chuyển secret sang Secrets Manager hoặc SSM SecureString và dùng dynamic reference/runtime retrieval phù hợp.

### Bài E — NoEcho được bật

Parameter có NoEcho: true nhưng secret vẫn xuất hiện trong Outputs.

**Đáp án:** xóa secret khỏi Outputs. NoEcho không che giá trị được lưu trong Outputs hoặc Metadata và không thay secret manager.

### Bài F — Secrets Manager rotation

Database secret đã rotate nhưng ứng dụng vẫn dùng password cũ.

**Đáp án:** kiểm tra cache TTL, connection pool, rotation workflow và cách ứng dụng refresh secret. Dynamic reference trong CloudFormation không tự cập nhật resource chỉ vì secret đã rotate.

### Bài G — S3 bucket public

Template có bucket policy Allow Principal "*" và không có giới hạn.

**Đáp án:** xác định nhu cầu public thực sự; ưu tiên bucket private với CloudFront Origin Access Control. Bật Block Public Access và giới hạn policy.

### Bài H — S3 request không dùng TLS

Bucket policy không từ chối insecure transport.

**Đáp án:** thêm explicit Deny với điều kiện aws:SecureTransport=false cho bucket và object ARN, sau khi kiểm tra client compatibility.

### Bài I — RDS public access

DB instance production có PubliclyAccessible: true và security group mở 5432 cho 0.0.0.0/0.

**Đáp án:** chuyển DB vào private subnet, đặt PubliclyAccessible false và chỉ cho phép nguồn application security group.

### Bài J — KMS decrypt bị AccessDenied

IAM role có kms:Decrypt nhưng KMS key policy không cho phép principal hoặc delegation phù hợp.

**Đáp án:** review key policy, grants, encryption context và ViaService. Không cấp kms:* trên tất cả key để xử lý nhanh.

### Bài K — CloudFormation Guard báo thiếu encryption

Template cũ không có BucketEncryption.

**Đáp án:** đánh giá tác động và thêm encryption configuration theo chuẩn. Nếu bucket hiện có dữ liệu, kiểm tra hành vi của object hiện tại và cách mã hóa default/bucket policy trước khi rollout.

### Bài L — Secret scan phát hiện access key trong Git history

Developer xóa dòng chứa key khỏi commit mới.

**Đáp án:** revoke/rotate key, audit CloudTrail, xóa secret khỏi history/artifact theo quy trình và thêm secret scanning. Xóa khỏi commit mới không vô hiệu hóa key đã lộ.

### Bài M — Change set thay role runtime

Change set thay execution role của Lambda bằng role có quyền rộng hơn.

**Đáp án:** so sánh trust policy và permission policy, xác minh resource/action/condition, kiểm tra iam:PassRole và chỉ approve khi quyền đáp ứng least privilege.

### Bài N — Dynamic reference cho secret

Template chứa Secrets Manager dynamic reference nhưng CloudFormation service role không có quyền đọc secret.

**Đáp án:** cấp secretsmanager:GetSecretValue trên secret cụ thể và kms:Decrypt nếu cần CMK, sau khi xác minh principal thực sự phân giải reference.

### Bài O — Drift detection không thấy secret rotation

Secret được rotate nhưng drift detection không báo khác biệt.

**Đáp án:** không coi drift detection là cơ chế phát hiện rotation. Theo dõi Secrets Manager version/staging label và kiểm tra ứng dụng/resource integration riêng.

## 29. Câu hỏi ôn tập

1. Vì sao template hợp lệ về cú pháp vẫn có thể không an toàn?
2. Identity policy và resource policy khác nhau ở đâu?
3. Trust policy của IAM role quyết định điều gì?
4. SCP có tự cấp quyền cho principal không?
5. Explicit Deny được đánh giá như thế nào so với Allow?
6. Vì sao không nên dùng AdministratorAccess cho runtime role?
7. Khi nào wildcard Resource có thể cần thiết?
8. S3 bucket ARN khác object ARN như thế nào?
9. iam:PassRole cho phép hành động gì?
10. Condition iam:PassedToService giúp giới hạn điều gì?
11. ExternalId giải quyết rủi ro nào?
12. Vì sao KMS key policy quan trọng dù IAM policy đã có kms:Decrypt?
13. Khi nào nên dùng Secrets Manager thay Parameter Store String?
14. SecureString có tự cung cấp rotation workflow không?
15. NoEcho có mã hóa secret trong template không?
16. Vì sao không nên đưa secret vào Outputs hoặc Metadata?
17. Dynamic reference được phân giải vào thời điểm nào?
18. Secret rotation có tự kích hoạt CloudFormation update không?
19. Vì sao ứng dụng runtime nên dùng IAM role thay access key tĩnh?
20. Cache secret quá lâu gây rủi ro gì?
21. S3 Versioning có thay Block Public Access không?
22. Encryption at rest có thay IAM authorization không?
23. Vì sao database security group nên nhận traffic từ application security group?
24. cfn-lint có thay IAM Access Analyzer không?
25. CloudFormation Guard kiểm tra điều gì?
26. CloudFormation Hooks khác CI policy check ở điểm nào?
27. Change set giúp reviewer phát hiện thay đổi nào?
28. Drift detection có kiểm tra được mọi resource/property không?
29. Khi secret bị lộ, vì sao xóa khỏi Git chưa đủ?
30. Một policy exception cần thông tin gì?

**Đáp án nhanh:** (1) có thể sai quyền/cấu hình; (2) một loại gắn identity, một loại gắn resource; (3) principal được AssumeRole; (4) không; (5) Deny thắng; (6) giảm blast radius; (7) khi action không hỗ trợ resource-level hoặc service yêu cầu; (8) bucket ARN và object ARN dùng cho action khác nhau; (9) truyền role cho AWS service; (10) giới hạn service nhận role; (11) confused deputy; (12) KMS authorization gồm key policy/grant; (13) secret cần lifecycle/rotation/audit; (14) không; (15) không; (16) NoEcho không che chúng; (17) khi CloudFormation xử lý resource property; (18) không; (19) temporary credentials; (20) chậm nhận secret mới; (21) không; (22) không; (23) thu hẹp nguồn network; (24) không; (25) rule tùy chỉnh trên template; (26) Hook có thể chặn ở lifecycle deployment; (27) Add/Modify/Remove/Replace; (28) không; (29) credential vẫn có thể dùng; (30) scope, lý do, owner, rủi ro, biện pháp bù trừ và ngày hết hạn.

## 30. Checklist production

- [ ] IAM identity policies chỉ cấp action/resource/condition cần thiết.
- [ ] Trust policies giới hạn principal và có condition phù hợp.
- [ ] iam:PassRole giới hạn role ARN và service nhận role.
- [ ] Resource policies không vô tình mở public hoặc cross-account access.
- [ ] KMS key policy tách key administrators và key users.
- [ ] Không có secret plaintext trong template, source, metadata, output hoặc tag.
- [ ] NoEcho không được dùng như giải pháp thay secret manager.
- [ ] Secrets Manager/SSM SecureString có IAM/KMS access hẹp.
- [ ] Runtime workload dùng IAM role/temporary credentials.
- [ ] Secret rotation, cache refresh và connection pool đã được kiểm thử.
- [ ] Dynamic references chỉ dùng ở property/context được hỗ trợ.
- [ ] S3 Block Public Access và encryption được cấu hình.
- [ ] TLS được yêu cầu cho data access phù hợp.
- [ ] RDS/DynamoDB/EBS encryption, backup và deletion controls đáp ứng yêu cầu.
- [ ] Security groups không mở cổng quản trị/database ra Internet.
- [ ] cfn-lint, CloudFormation Guard và IAM Access Analyzer chạy trong CI.
- [ ] Secret scanning kiểm tra cả thay đổi và repository history.
- [ ] Change set được review trước production deployment.
- [ ] CloudFormation Hooks/SCP/IAM guardrails bảo vệ đường deploy.
- [ ] AWS Config, CloudTrail và Security Hub có coverage phù hợp.
- [ ] Drift detection limitations được hiểu và có runtime checks bổ sung.
- [ ] Policy exceptions có owner, justification, compensating control và expiry.
- [ ] Có quy trình rotate/revoke, audit và phục hồi khi secret/policy bị lộ.

## 31. Tổng kết

Kiểm tra policy, secret và cấu hình an toàn trong IaC là quá trình bảo vệ hạ tầng từ source code đến runtime:

- IAM policy phải theo least privilege; trust policy, resource policy, permissions boundary và SCP có vai trò khác nhau.
- Wildcard, public principal và iam:PassRole cần được review theo action, resource, condition và workload thực tế.
- Secret phải được lưu trong Secrets Manager hoặc SSM SecureString phù hợp; runtime nên dùng IAM role và temporary credentials.
- NoEcho chỉ che một số hiển thị của parameter; nó không mã hóa template hoặc bảo vệ secret trong Outputs/Metadata.
- Dynamic references giúp tránh plaintext trong template nhưng được phân giải khi CloudFormation xử lý resource property; rotation không tự kích hoạt stack update.
- S3, RDS, DynamoDB, EBS, KMS và network resources cần secure defaults phù hợp service.
- cfn-lint, CloudFormation Guard, IAM Access Analyzer, secret scanning, change sets và CloudFormation Hooks tạo thành nhiều lớp kiểm tra.
- Runtime controls như AWS Config, CloudTrail và Security Hub giúp phát hiện drift và vi phạm sau triển khai.
- Khi secret bị lộ, revoke/rotate credential và audit việc sử dụng quan trọng hơn chỉ xóa dòng khỏi Git.

IaC an toàn cần làm cho quyền truy cập rõ ràng, secret có vòng đời được kiểm soát và cấu hình bảo mật có thể kiểm tra tự động trước mỗi lần triển khai.

### Tài liệu AWS chính thức

1. IAM policies and permissions: https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies.html
2. IAM policy evaluation logic: https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic.html
3. IAM best practices: https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html
4. Grant a user permissions to pass a role to an AWS service: https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_use_passrole.html
5. IAM Access Analyzer policy validation: https://docs.aws.amazon.com/IAM/latest/UserGuide/access-analyzer-policy-validation.html
6. CloudFormation dynamic references: https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/dynamic-references.html
7. CloudFormation NoEcho parameters: https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/parameters-section-structure.html
8. AWS Secrets Manager best practices: https://docs.aws.amazon.com/secretsmanager/latest/userguide/best-practices.html
9. Secrets Manager rotation: https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotating-secrets.html
10. Systems Manager Parameter Store SecureString: https://docs.aws.amazon.com/systems-manager/latest/userguide/secure-string-parameter-kms-encryption.html
11. CloudFormation Guard: https://docs.aws.amazon.com/cfn-guard/latest/ug/what-is-guard.html
12. cfn-lint: https://github.com/aws-cloudformation/cfn-lint
13. CloudFormation Hooks: https://docs.aws.amazon.com/cloudformation-cli/latest/hooks-userguide/what-is-cloudformation-hooks.html
14. S3 Block Public Access: https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-control-block-public-access.html
15. S3 Object Ownership: https://docs.aws.amazon.com/AmazonS3/latest/userguide/about-object-ownership.html
16. RDS encryption: https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Overview.Encryption.html
17. DynamoDB encryption at rest: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/EncryptionAtRest.html
18. AWS Config managed rules: https://docs.aws.amazon.com/config/latest/developerguide/managed-rules-by-aws-config.html
19. AWS CloudTrail: https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-user-guide.html
20. AWS Well-Architected Security Pillar: https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/welcome.html
