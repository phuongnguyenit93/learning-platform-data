# Thiết lập pipeline CI/CD liên tài khoản và rollback tự động

## Mục tiêu dự án

Một nhóm phát triển cần đưa ứng dụng lên AWS qua các môi trường dev, staging và production. Mỗi môi trường nằm trong một AWS account riêng để giới hạn blast radius, quyền truy cập và dữ liệu. Nhóm muốn mỗi lần merge vào nhánh chính đều được kiểm thử tự động, đóng gói thành một artifact duy nhất và triển khai lần lượt qua các account. Nếu bản phát hành lỗi hoặc metric sức khỏe vượt ngưỡng, hệ thống phải tự quay về phiên bản ổn định gần nhất.

Capstone này xây dựng pipeline bằng AWS CodePipeline, AWS CodeBuild, AWS CodeDeploy, Amazon S3, AWS KMS, IAM và Amazon CloudWatch. Account tooling giữ pipeline và artifact. Các account môi trường chứa ứng dụng, Auto Scaling group, CodeDeploy deployment group và alarm. CodePipeline dùng IAM role liên tài khoản để gọi hành động deploy trong từng account.

Bài học thuộc chương **Dự án tổng hợp AWS** của module CLOUD_PROVIDERS_AWS. Người học sẽ thiết kế và triển khai một release path có thể kiểm toán, có approval ở production và có hai lớp rollback ở cấp deployment và pipeline.

Sau dự án, người học có thể:

- Thiết kế mô hình AWS account riêng cho tooling, dev, staging và production.
- Tạo pipeline nguồn từ GitHub bằng AWS CodeConnections.
- Dùng CodeBuild để test, build và đóng gói artifact bất biến.
- Cấu hình artifact bucket S3 và customer-managed KMS key cho truy cập liên tài khoản.
- Thiết lập trust policy và IAM permission để CodePipeline assume role ở account đích.
- Triển khai ứng dụng lên EC2 bằng CodeDeploy.
- Cấu hình CloudWatch alarms và automatic rollback cho CodeDeploy.
- Cấu hình CodePipeline V2 stage rollback khi stage thất bại.
- Thêm smoke test, manual approval và promotion gates.
- Kiểm thử rollback, điều tra lỗi cross-account và quản lý artifact retention.
- Thiết kế migration database tương thích ngược để rollback ứng dụng an toàn.

## 1. Bài toán và tiêu chí nghiệm thu

Giả sử nhóm đang vận hành dịch vụ REST API quản lý đơn hàng. Ứng dụng được đóng gói thành file JAR, chạy trên EC2 Linux trong Auto Scaling group và nhận traffic qua Application Load Balancer. Mỗi môi trường có endpoint và dữ liệu riêng.

Pipeline phải đáp ứng các tiêu chí sau:

| Tiêu chí | Kết quả cần đạt |
|---|---|
| Source control | Merge vào nhánh main khởi chạy pipeline |
| Quality gate | Unit test, integration test phù hợp và kiểm tra package phải thành công |
| Artifact | Tạo đúng một artifact có version, commit SHA và checksum |
| Promotion | Cùng artifact được đưa qua dev, staging và production |
| Account isolation | Pipeline không dùng credential tĩnh hoặc quyền Administrator ở account đích |
| Approval | Production yêu cầu người có thẩm quyền phê duyệt |
| Deployment health | CloudWatch alarm theo dõi lỗi và sức khỏe ứng dụng trong deployment |
| Automatic rollback | CodeDeploy quay về revision ổn định khi deployment thất bại hoặc alarm kích hoạt |
| Pipeline rollback | CodePipeline có thể rollback stage về execution thành công gần nhất khi stage fail |
| Auditability | Có commit, build ID, artifact digest, deployment ID và CloudTrail events để truy vết |

Một pipeline chỉ báo trạng thái xanh chưa đủ để nghiệm thu. Cần chứng minh phiên bản đã triển khai đúng, health check thành công, artifact giống nhau giữa các account và rollback thực sự phục hồi được ứng dụng.

## 2. Kiến trúc nhiều account

Dùng một account cho tooling và ba account cho môi trường:

| Account | Trách nhiệm | Resource chính |
|---|---|---|
| Tooling | Điều phối CI/CD và giữ artifact | CodePipeline, CodeBuild, CodeConnections, S3 artifact bucket, KMS key |
| Development | Kiểm thử phiên bản mới đầu tiên | VPC, ALB, EC2 Auto Scaling group, CodeDeploy, CloudWatch |
| Staging | Kiểm thử gần production và kiểm tra release | VPC, ALB, EC2 Auto Scaling group, CodeDeploy, CloudWatch |
| Production | Phục vụ người dùng thật | VPC, ALB, EC2 Auto Scaling group, CodeDeploy, CloudWatch |

Ví dụ account ID dùng trong bài:

- Tooling: 111122223333
- Development: 444455556666
- Staging: 777788889999
- Production: 000011112222

Đây là ID giả lập để minh họa ARN và policy. Thay bằng account ID thật khi triển khai.

Mỗi môi trường có IAM role, security boundary, secret, network và dữ liệu riêng. Production không dùng chung database hoặc secret với staging. Dùng AWS Organizations và Service Control Policies để áp dụng guardrail cấp account nếu tổ chức có Organizations.

~~~mermaid
flowchart TB
    subgraph TOOL["Tooling account"]
      GH[GitHub repository]
      CON[CodeConnections]
      CP[CodePipeline V2]
      CB[CodeBuild]
      S3[S3 artifact bucket]
      KMS[KMS customer-managed key]
      GH --> CON --> CP
      CP --> CB
      CB --> S3
      S3 --- KMS
    end
    subgraph DEV["Development account"]
      DR[Cross-account deploy role]
      DC[CodeDeploy]
      DA[EC2 Auto Scaling group]
      DM[CloudWatch alarms]
      DR --> DC --> DA
      DC --> DM
    end
    subgraph STAGE["Staging account"]
      SR[Cross-account deploy role]
      SC[CodeDeploy]
      SA[EC2 Auto Scaling group]
      SM[CloudWatch alarms]
      SR --> SC --> SA
      SC --> SM
    end
    subgraph PROD["Production account"]
      PR[Cross-account deploy role]
      PC[CodeDeploy]
      PA[EC2 Auto Scaling group]
      PM[CloudWatch alarms]
      PR --> PC --> PA
      PC --> PM
    end
    CP -->|AssumeRole + artifact| DR
    CP -->|AssumeRole + artifact| SR
    CP -->|AssumeRole + artifact| PR
~~~

Pipeline và artifact nằm trong tooling account. Các account đích chỉ cấp quyền cần thiết cho pipeline role và CodeDeploy agent. Cách tổ chức này giảm số nơi có quyền tạo release và giúp tách quyền build khỏi quyền deploy production.

## 3. Luồng CI/CD đầu cuối

Pipeline thực hiện các bước theo thứ tự:

1. Developer tạo pull request và hoàn tất review.
2. Merge vào main kích hoạt source action qua CodeConnections.
3. CodeBuild chạy test, kiểm tra chất lượng và đóng gói artifact.
4. CodePipeline deploy artifact vào development account.
5. Smoke test xác minh endpoint, health check và luồng nghiệp vụ cơ bản.
6. Pipeline triển khai cùng artifact vào staging account.
7. Staging chạy integration test, acceptance test và kiểm tra hiệu năng phù hợp.
8. Manual approval yêu cầu release owner xem commit, test report, artifact digest và kết quả staging.
9. CodePipeline assume role trong production account và gọi CodeDeploy.
10. CodeDeploy triển khai theo deployment configuration, theo dõi CloudWatch alarms và tự rollback nếu điều kiện được kích hoạt.
11. Smoke test production xác minh release. Nếu stage thất bại, CodePipeline V2 có thể rollback stage về execution thành công trước đó.
12. Pipeline ghi lại deployment ID, artifact digest và kết quả cuối.

~~~mermaid
flowchart TD
    A[Merge to main] --> B[CodeConnections source]
    B --> C[CodeBuild: test, scan, package]
    C --> D[Immutable BuildArtifact]
    D --> E[Deploy dev account]
    E --> F[Dev smoke tests]
    F --> G[Deploy staging account]
    G --> H[Integration and acceptance tests]
    H --> I{Manual approval}
    I -->|Rejected| X[Stop release]
    I -->|Approved| J[Deploy production account]
    J --> K[CodeDeploy + CloudWatch alarms]
    K --> L[Production smoke tests]
    L --> M[Record release evidence]
    K -->|Deployment failure or alarm| R[CodeDeploy automatic rollback]
    L -->|Stage failure| S[CodePipeline stage rollback]
~~~

Pipeline chỉ build artifact một lần. Không build lại source code riêng cho staging hoặc production vì điều đó có thể tạo binary khác với binary đã được kiểm thử.

## 4. Phân chia trách nhiệm giữa các dịch vụ

| Dịch vụ | Vai trò trong dự án |
|---|---|
| AWS CodeConnections | Kết nối GitHub repository với CodePipeline bằng GitHub App |
| AWS CodePipeline | Điều phối source, build, approval, deploy và stage rollback |
| AWS CodeBuild | Chạy test, build package, tạo checksum và artifact |
| Amazon S3 | Lưu artifact được pipeline tạo |
| AWS KMS | Mã hóa artifact bằng customer-managed key |
| AWS IAM / STS | Cấp quyền và assume role liên tài khoản |
| AWS CodeDeploy | Triển khai revision lên EC2 và tự rollback |
| Amazon CloudWatch | Thu thập metrics, tạo alarm và hỗ trợ xác minh deployment |
| Amazon SNS | Gửi thông báo approval hoặc deployment event nếu được cấu hình |
| AWS CloudTrail | Ghi lại API calls và thay đổi quyền/cấu hình |

CodePipeline điều phối hành động. CodeDeploy quản lý quá trình thay revision trên compute target. CloudWatch cung cấp tín hiệu sức khỏe. IAM/STS kiểm soát danh tính và quyền truy cập giữa các account.

## 5. Chuẩn bị repository và cấu trúc artifact

Ví dụ cấu trúc repository:

~~~text
orders-api/
├── pom.xml
├── src/
│   ├── main/
│   └── test/
├── appspec.yml
├── buildspec.yml
└── scripts/
    ├── prepare.sh
    ├── configure.sh
    ├── start.sh
    └── validate.sh
~~~

Build output được đóng gói theo cấu trúc:

~~~text
BuildArtifact.zip
├── appspec.yml
├── SHA256SUMS
├── app/
│   └── orders-api.jar
└── scripts/
    ├── prepare.sh
    ├── configure.sh
    ├── start.sh
    └── validate.sh
~~~

Artifact phải chứa đủ những gì CodeDeploy cần. Không đưa AWS access key, password, database credential hoặc production configuration vào ZIP. Runtime lấy cấu hình theo môi trường từ Systems Manager Parameter Store hoặc Secrets Manager với IAM role của ứng dụng.

Đặt version theo commit SHA hoặc build ID. Ghi checksum SHA-256 để so sánh artifact được promotion qua các account.

## 6. Kết nối GitHub bằng CodeConnections

Trong tooling account:

1. Mở Developer Tools / Connections trong AWS Console.
2. Tạo connection tới GitHub bằng GitHub App.
3. Cấp quyền truy cập đúng organization và repository cần dùng.
4. Hoàn tất authorization và chờ connection ở trạng thái AVAILABLE.
5. Lưu connection ARN.
6. Tạo source action trong CodePipeline với repository, branch và connection ARN.

CodePipeline dùng action provider CodeStarSourceConnection cho GitHub App connection. Tên provider trong pipeline structure vẫn là CodeStarSourceConnection, dù giao diện dịch vụ hiện dùng tên CodeConnections.

Không lưu personal access token trong buildspec hoặc repository. Nếu connection không hỗ trợ Region đã chọn, kiểm tra danh sách Region hiện hành và chọn Region hỗ trợ trước khi thiết kế pipeline.

## 7. Thiết kế artifact store và mã hóa

CodePipeline dùng S3 bucket làm artifact store. Với cross-account actions, nên tạo customer-managed KMS key ở cùng Region với pipeline và artifact bucket.

Ví dụ:

- Bucket: codepipeline-ap-southeast-1-111122223333
- Key ARN: arn:aws:kms:ap-southeast-1:111122223333:key/11111111-2222-3333-4444-555555555555

Cấu hình bucket:

- Block Public Access bật.
- Bucket versioning bật.
- Default encryption dùng KMS customer-managed key.
- Bucket policy chỉ cho principal được xác định truy cập.
- Yêu cầu TLS khi truy cập.
- Lifecycle policy giữ artifact đủ lâu cho rollback và audit.
- Không xóa artifact của execution còn nằm trong cửa sổ rollback.

KMS key policy phải cho phép pipeline service role và các cross-account role cần đọc artifact. IAM identity policy của role đích cũng phải cho phép dùng key. Với cross-account KMS, chỉ thêm identity policy mà không cấu hình key policy là chưa đủ.

KMS key là regional resource. Nếu pipeline thực hiện cross-Region action, cần artifact bucket và key riêng trong từng Region thực thi action; CodePipeline quản lý việc sao chép artifact giữa các Region. Dự án này dùng một Region để giảm độ phức tạp.

## 8. Giới hạn artifact trong cross-account pipeline

CodePipeline có một quy tắc quan trọng: action ở account khác có thể tiêu thụ artifact được tạo trong pipeline account. Artifact cũng có thể được action dùng lại trong cùng account nơi nó được tạo. Không thể chuyển artifact trực tiếp giữa hai account đích nếu cả hai đều khác pipeline account.

Vì vậy, kiến trúc này giữ artifact gốc trong tooling account và cho các action ở dev, staging, production đọc cùng artifact đó. Không deploy vào dev rồi lấy artifact từ dev account để chuyển sang staging.

Khi một cross-account action cần artifact:

1. CodePipeline assume role ở account đích.
2. Role đích được phép đọc object trong artifact bucket.
3. Role đích được phép giải mã object bằng KMS key.
4. CodeDeploy nhận revision và triển khai vào target trong account đích.
5. CodeDeploy agent trên EC2 cũng cần quyền đọc artifact và decrypt key khi tải revision.

Phải kiểm tra cả action role lẫn EC2 instance profile. Chỉ cấp quyền cho action role có thể khiến pipeline tạo deployment thành công nhưng agent trên EC2 không tải được revision.

## 9. Thiết kế IAM role liên tài khoản

Có ít nhất bốn loại role:

| Role | Account | Trust principal | Nhiệm vụ |
|---|---|---|---|
| CodePipelineServiceRole | Tooling | codepipeline.amazonaws.com | Điều phối pipeline và assume role đích |
| CodePipelineDeployRole | Dev/Staging/Prod | CodePipelineServiceRole ở tooling | Cho phép action triển khai vào account đích |
| CodeDeployServiceRole | Dev/Staging/Prod | codedeploy.amazonaws.com | Quản lý deployment target và lifecycle |
| CodeDeployInstanceRole | Dev/Staging/Prod | ec2.amazonaws.com | Cho EC2 agent đọc artifact và gửi log |

Không dùng một role cho mọi nhiệm vụ. Pipeline role không cần quyền đăng nhập vào EC2; instance profile không cần quyền sửa pipeline; CodeDeploy service role không cần quyền đọc repository.

## 10. Trust policy của cross-account deploy role

Ví dụ trust policy trong production account chỉ tin cậy đúng pipeline service role của tooling account:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "TrustCentralCodePipeline",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::111122223333:role/CodePipelineServiceRole"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

Không để principal là toàn bộ account root nếu chỉ một pipeline service role được phép deploy. Trust policy xác định ai được assume role; permission policy của role xác định sau khi assume thì được làm gì.

CodePipeline service role trong tooling account cần identity policy cho phép sts:AssumeRole trên đúng ba deploy role:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AssumeEnvironmentDeployRoles",
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": [
        "arn:aws:iam::444455556666:role/CodePipelineDeployRole",
        "arn:aws:iam::777788889999:role/CodePipelineDeployRole",
        "arn:aws:iam::000011112222:role/CodePipelineDeployRole"
      ]
    }
  ]
}
~~~

Mỗi account đích có thể dùng cùng tên role nhưng ARN và policy phải gắn với resource của account đó. Trong production, chỉ cấp action cần thiết cho CodeDeploy application và deployment group tương ứng.

## 11. Permission của cross-account deploy role

Role trong account đích cần quyền để:

- Tạo deployment và đọc trạng thái deployment.
- Đọc application revision và deployment configuration.
- Đăng ký revision khi action provider yêu cầu.
- Đọc artifact object trong S3 bucket của tooling account.
- Gọi KMS Decrypt và DescribeKey trên artifact key.
- Truy cập các resource cần thiết của CodeDeploy theo ARN.

AWS CodePipeline có ví dụ policy cho CodeDeploy cross-account action. Một số CodeDeploy API yêu cầu resource scope rộng hơn các API khác. Hãy đối chiếu Service Authorization Reference và giới hạn resource theo application/deployment group khi action hỗ trợ.

CodeDeploy service role là role khác. Nó được service CodeDeploy assume và có quyền thực hiện lifecycle trên EC2/Auto Scaling/load balancer phù hợp deployment group.

## 12. S3 bucket policy cho artifact access

Bucket policy của tooling account cần cho phép các role đã xác định đọc artifact. Ví dụ rút gọn:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowTargetRolesReadArtifacts",
      "Effect": "Allow",
      "Principal": {
        "AWS": [
          "arn:aws:iam::444455556666:role/CodePipelineDeployRole",
          "arn:aws:iam::777788889999:role/CodePipelineDeployRole",
          "arn:aws:iam::000011112222:role/CodePipelineDeployRole",
          "arn:aws:iam::000011112222:role/CodeDeployInstanceRole"
        ]
      },
      "Action": [
        "s3:GetObject",
        "s3:GetObjectVersion"
      ],
      "Resource": "arn:aws:s3:::codepipeline-ap-southeast-1-111122223333/*"
    },
    {
      "Sid": "AllowTargetRolesListBucket",
      "Effect": "Allow",
      "Principal": {
        "AWS": [
          "arn:aws:iam::444455556666:role/CodePipelineDeployRole",
          "arn:aws:iam::777788889999:role/CodePipelineDeployRole",
          "arn:aws:iam::000011112222:role/CodePipelineDeployRole",
          "arn:aws:iam::000011112222:role/CodeDeployInstanceRole"
        ]
      },
      "Action": [
        "s3:ListBucket",
        "s3:GetBucketLocation"
      ],
      "Resource": "arn:aws:s3:::codepipeline-ap-southeast-1-111122223333"
    }
  ]
}
~~~

Đây là policy minh họa cho các role đọc artifact. Cần thêm hoặc điều chỉnh principal theo từng account và loại action thực tế. Pipeline service role vẫn cần quyền ghi artifact của chính pipeline. Không mở bucket cho anonymous hoặc toàn bộ account ngoài.

Nếu bucket dùng Object Ownership là Bucket owner enforced, không cần ACL cho object. Hãy kiểm tra tương thích với action/provider và bucket policy đang dùng trước khi thay đổi cấu hình bucket hiện hữu.

## 13. KMS key policy cho cross-account decryption

Trong tooling account, KMS key policy phải cấp quyền cho role ở account đích. Ví dụ phần statement cấp quyền giải mã artifact:

~~~json
{
  "Sid": "AllowEnvironmentRolesToDecryptPipelineArtifacts",
  "Effect": "Allow",
  "Principal": {
    "AWS": [
      "arn:aws:iam::444455556666:role/CodePipelineDeployRole",
      "arn:aws:iam::777788889999:role/CodePipelineDeployRole",
      "arn:aws:iam::000011112222:role/CodePipelineDeployRole",
      "arn:aws:iam::000011112222:role/CodeDeployInstanceRole"
    ]
  },
  "Action": [
    "kms:Decrypt",
    "kms:DescribeKey"
  ],
  "Resource": "*"
}
~~~

Trong policy hoàn chỉnh, giữ statement quản trị key và quyền sử dụng key của CodePipeline service role. Role đích cũng cần identity policy cho phép kms:Decrypt trên đúng key ARN. Không cấp quyền quản trị key cho deployment role.

Nếu CodePipeline action cần ghi output artifact từ account đích, phải bổ sung các quyền mã hóa/ghi cần thiết. Trong ví dụ CodeDeploy action không tạo output artifact, nên quyền đọc và giải mã là trọng tâm.

## 14. Chuẩn bị EC2 và CodeDeploy trong từng account

Mỗi môi trường cần:

1. VPC và subnet phù hợp.
2. Application Load Balancer và target group nếu ứng dụng nhận traffic qua ALB.
3. EC2 Auto Scaling group chứa application instances.
4. CodeDeploy agent được cài và chạy trên EC2.
5. EC2 instance profile có quyền đọc artifact từ S3 và decrypt KMS key.
6. CodeDeploy application và deployment group.
7. CodeDeploy service role cho phép quản lý target.
8. CloudWatch log group, metrics và alarms.
9. Security group chỉ cho phép traffic cần thiết.
10. Parameter Store/Secrets Manager cho cấu hình và secret theo môi trường.

CodeDeploy agent cần truy cập endpoint dịch vụ và artifact store. Kiểm tra route, DNS, NAT hoặc VPC endpoint phù hợp. Nếu EC2 ở private subnet, đảm bảo instance có đường truy cập S3 và các endpoint cần thiết.

Không nhúng credential vào user data hoặc AMI. EC2 instance profile cung cấp credential tạm thời qua metadata service.

## 15. Tạo CodeDeploy application và deployment group

Tạo một CodeDeploy application cho service orders-api trong mỗi account. Deployment group chọn EC2/On-Premises compute platform và gắn với Auto Scaling group hoặc tag group tương ứng.

Đối với capstone, có thể bắt đầu bằng in-place deployment với cấu hình OneAtATime để hạn chế số instance được cập nhật đồng thời. Khi cần giảm downtime hơn, đánh giá blue/green deployment và load balancer traffic control.

Các thành phần deployment group:

- ApplicationName: tên ứng dụng CodeDeploy.
- DeploymentGroupName: tên group theo môi trường.
- ServiceRoleArn: CodeDeploy service role trong account đích.
- DeploymentConfigName: ví dụ CodeDeployDefault.OneAtATime.
- Ec2TagFilters hoặc AutoScalingGroups: xác định instance mục tiêu.
- AlarmConfiguration: các CloudWatch alarms theo dõi deployment.
- AutoRollbackConfiguration: sự kiện kích hoạt rollback.
- DeploymentStyle: in-place hoặc blue/green tùy thiết kế.

Tên application có thể giống nhau giữa account, nhưng resource ARN khác nhau. Pipeline action dùng roleArn trong account đích để gọi đúng application và deployment group.

## 16. AppSpec và lifecycle hooks

CodeDeploy dùng AppSpec để biết file nào cần copy và script nào cần chạy ở từng lifecycle event.

Ví dụ appspec.yml cho Linux:

~~~yaml
version: 0.0
os: linux
files:
  - source: app/orders-api.jar
    destination: /opt/orders-api/

hooks:
  BeforeInstall:
    - location: scripts/prepare.sh
      timeout: 120
      runas: root

  AfterInstall:
    - location: scripts/configure.sh
      timeout: 120
      runas: root

  ApplicationStart:
    - location: scripts/start.sh
      timeout: 120
      runas: root

  ValidateService:
    - location: scripts/validate.sh
      timeout: 60
      runas: root
~~~

Ý nghĩa:

- BeforeInstall chuẩn bị thư mục và quyền file.
- AfterInstall cập nhật symlink hoặc cấu hình runtime.
- ApplicationStart khởi động service.
- ValidateService gọi health endpoint và trả exit code khác 0 nếu service không khỏe.

Script phải idempotent, có timeout, log rõ ràng và không xóa dữ liệu ứng dụng. Không ghi secret vào stdout vì CodeDeploy deployment logs có thể được nhiều người có quyền vận hành đọc.

## 17. Cấu hình CloudWatch alarms cho deployment

Alarm nên phản ánh customer impact hoặc sức khỏe của target. Ví dụ:

| Alarm | Tín hiệu | Hành động |
|---|---|---|
| orders-prod-5xx | HTTP 5xx tăng trên ALB hoặc application metric | Dừng deployment và rollback |
| orders-prod-latency | p95 response time vượt SLO | Dừng rollout |
| orders-prod-healthy-hosts | HealthyHostCount thấp hơn mức an toàn | Dừng deployment |
| orders-prod-process-errors | Application error metric tăng | Dừng deployment |

Dùng metric có baseline và evaluation period phù hợp. Alarm quá nhạy có thể rollback vì một spike ngắn; alarm quá lỏng có thể để lỗi ảnh hưởng người dùng lâu.

CodeDeploy deployment group có thể gắn CloudWatch alarms. Với EC2 deployment, theo dõi metric của instance hoặc Auto Scaling group; tùy kiến trúc có thể bổ sung metric ALB/application để quan sát trải nghiệm request.

Trước khi deploy, alarm phải tồn tại và ở trạng thái có thể đánh giá. Nếu yêu cầu an toàn nghiêm ngặt, không cấu hình deployment tiếp tục khi CodeDeploy không đọc được trạng thái alarm.

## 18. Automatic rollback của CodeDeploy

CodeDeploy có thể tự động rollback khi:

- Deployment thất bại.
- Một hoặc nhiều CloudWatch alarms được gắn với deployment group chuyển sang ALARM.

Rollback của CodeDeploy thực hiện bằng cách deploy lại revision đã triển khai thành công trước đó. Đây là một deployment mới với deployment ID mới, không phải tua ngược deployment ID cũ.

Ví dụ phần cấu hình deployment group:

~~~yaml
AlarmConfiguration:
  Enabled: true
  IgnorePollAlarmFailure: false
  Alarms:
    - Name: orders-prod-5xx
    - Name: orders-prod-latency

AutoRollbackConfiguration:
  Enabled: true
  Events:
    - DEPLOYMENT_FAILURE
    - DEPLOYMENT_STOP_ON_ALARM
~~~

Đây là phần cấu hình minh họa; đặt nó trong resource AWS::CodeDeploy::DeploymentGroup hoặc cấu hình deployment group tương ứng. Tạo alarm trước khi liên kết với group.

Nếu lần deploy đầu tiên chưa có revision thành công trước đó, CodeDeploy không có last-known-good revision để redeploy. Cần bootstrap một bản phát hành ổn định trước khi dựa vào automatic rollback.

## 19. Automatic stage rollback của CodePipeline V2

CodePipeline V2 hỗ trợ cấu hình stage rollback khi stage thất bại. Khi failure condition được kích hoạt, stage được rollback về execution thành công gần nhất của chính stage đó.

Ví dụ cấu hình stage:

~~~json
{
  "name": "DeployProduction",
  "actions": [
    {
      "name": "DeployOrdersApi",
      "actionTypeId": {
        "category": "Deploy",
        "owner": "AWS",
        "provider": "CodeDeploy",
        "version": "1"
      },
      "configuration": {
        "ApplicationName": "orders-api",
        "DeploymentGroupName": "orders-prod"
      },
      "inputArtifacts": [
        {
          "name": "BuildArtifact"
        }
      ],
      "outputArtifacts": [],
      "roleArn": "arn:aws:iam::000011112222:role/CodePipelineDeployRole",
      "runOrder": 1
    }
  ],
  "onFailure": {
    "result": "ROLLBACK"
  }
}
~~~

Đây là stage fragment, không phải toàn bộ pipeline definition. Cấu hình rollback thuộc pipeline structure V2.

Các điều kiện cần nhớ:

- Stage rollback chỉ hoạt động khi có execution thành công trước đó trong cùng pipeline structure version.
- Sau khi thêm hoặc thay đổi cấu trúc pipeline, cần có một execution thành công trước khi dựa vào automatic rollback của cấu trúc mới.
- Pipeline execution mode PARALLEL không hỗ trợ stage rollback. Dùng SUPERSEDED hoặc QUEUED nếu cần rollback.
- Rollback stage tạo một execution mới và dùng revision/artifact của execution đích.
- Stage rollback không phải cơ chế hoàn tác mọi side effect bên ngoài pipeline.

Trong capstone, dùng executionMode QUEUED để các release được xử lý tuần tự, tránh nhiều execution cùng tranh chấp production deployment.

## 20. Hai lớp rollback xử lý hai tình huống khác nhau

| Cơ chế | Kích hoạt | Phạm vi | Kết quả |
|---|---|---|---|
| CodeDeploy automatic rollback | Deployment failure hoặc CloudWatch alarm | Revision ứng dụng trong deployment group | Deploy lại revision tốt gần nhất |
| CodePipeline stage rollback | Stage thất bại | Stage của pipeline | Chạy lại stage bằng execution thành công trước |
| Manual rollback | Người vận hành quyết định | Deployment hoặc stage được chọn | Khôi phục revision đã chọn |
| Infrastructure rollback | CloudFormation resource update thất bại | Stack/resource được CloudFormation quản lý | CloudFormation rollback stack update theo cơ chế của stack |

CodeDeploy rollback nên là lớp bảo vệ chính cho deployment health. CodePipeline stage rollback bổ sung khả năng phục hồi stage nếu deploy action hoặc smoke test trong stage thất bại.

Đặt deploy action và smoke-test action trong cùng stage nếu muốn một smoke-test failure làm stage thất bại và kích hoạt stage rollback. Nếu smoke test nằm ở stage khác, rollback stage đó không tự động đảo ngược deployment stage trước đó.

## 21. Giới hạn rollback và database migration

Rollback application không đồng nghĩa rollback dữ liệu.

Ví dụ release mới thêm cột database hoặc đổi format message. Nếu ứng dụng cũ không đọc được schema mới, CodeDeploy có thể khôi phục binary cũ nhưng service vẫn lỗi.

Dùng chiến lược expand/contract:

1. **Expand:** thêm column/table/index mới theo cách tương thích với ứng dụng cũ.
2. Deploy code mới có thể đọc schema cũ và mới.
3. Chuyển dần read/write sang cấu trúc mới.
4. Theo dõi và xác minh dữ liệu.
5. **Contract:** chỉ xóa field hoặc schema cũ sau khi phiên bản cũ không còn cần rollback.

Không tự động rollback destructive database migration. Mọi migration có tác động dữ liệu phải có backup, compatibility review và recovery plan riêng.

CodeDeploy cũng không hoàn tác mọi side effect do lifecycle scripts tạo ra. Script tạo file ngoài danh sách được quản lý hoặc thay đổi database không tự được đảo ngược chỉ vì deployment rollback.

## 22. Build và test với CodeBuild

CodeBuild action nhận SourceArtifact, chạy buildspec trong build container và xuất BuildArtifact cho action tiếp theo.

Một buildspec mẫu cho ứng dụng Java Maven:

~~~yaml
version: 0.2

phases:
  install:
    runtime-versions:
      java: corretto21

  pre_build:
    commands:
      - mvn -B -ntp clean verify

  build:
    commands:
      - mkdir -p deploy/app deploy/scripts
      - cp target/orders-api.jar deploy/app/orders-api.jar
      - cp appspec.yml deploy/appspec.yml
      - cp scripts/prepare.sh deploy/scripts/prepare.sh
      - cp scripts/configure.sh deploy/scripts/configure.sh
      - cp scripts/start.sh deploy/scripts/start.sh
      - cp scripts/validate.sh deploy/scripts/validate.sh
      - sha256sum deploy/app/orders-api.jar > deploy/SHA256SUMS

reports:
  unit-tests:
    files:
      - target/surefire-reports/TEST-*.xml
    file-format: JUNITXML

artifacts:
  base-directory: deploy
  files:
    - "**/*"
  discard-paths: no
~~~

Ví dụ giả định Maven tạo file target/orders-api.jar. Điều chỉnh đường dẫn theo build output thực tế.

CodeBuild service role cần quyền đọc input artifact, ghi output artifact, ghi CloudWatch Logs và truy cập dependency repository. Không cấp quyền deploy production cho CodeBuild role nếu CodePipeline action role đảm nhiệm deploy.

## 23. Tạo CodePipeline V2

Pipeline cần các stage chính:

- Source: CodeStarSourceConnection.
- Build: CodeBuild.
- DeployDev: CodeDeploy action với dev cross-account role.
- DeployStaging: CodeDeploy action với staging cross-account role.
- ApproveProduction: Manual approval.
- DeployProduction: CodeDeploy action với production cross-account role và stage rollback.

Phần pipeline properties nên dùng:

~~~json
{
  "pipelineType": "V2",
  "executionMode": "QUEUED"
}
~~~

Đây là phần thuộc pipeline properties, không phải toàn bộ pipeline JSON. Khi tạo pipeline bằng CloudFormation hoặc CLI, kết hợp các properties này với roleArn, artifactStore và stage definitions.

Ví dụ source action:

~~~json
{
  "name": "GitHubSource",
  "actionTypeId": {
    "category": "Source",
    "owner": "AWS",
    "provider": "CodeStarSourceConnection",
    "version": "1"
  },
  "configuration": {
    "ConnectionArn": "arn:aws:codestar-connections:ap-southeast-1:111122223333:connection/11111111-2222-3333-4444-555555555555",
    "FullRepositoryId": "example-org/orders-api",
    "BranchName": "main",
    "OutputArtifactFormat": "CODE_ZIP"
  },
  "outputArtifacts": [
    {
      "name": "SourceArtifact"
    }
  ],
  "inputArtifacts": [],
  "runOrder": 1
}
~~~

Ví dụ Build action:

~~~json
{
  "name": "BuildAndTest",
  "actionTypeId": {
    "category": "Build",
    "owner": "AWS",
    "provider": "CodeBuild",
    "version": "1"
  },
  "configuration": {
    "ProjectName": "orders-api-build"
  },
  "inputArtifacts": [
    {
      "name": "SourceArtifact"
    }
  ],
  "outputArtifacts": [
    {
      "name": "BuildArtifact"
    }
  ],
  "runOrder": 1
}
~~~

Các JSON trên là action fragments. Khi ghép vào pipeline hoàn chỉnh, giữ đúng tên artifact giữa outputArtifacts và inputArtifacts.

## 24. Cross-account CodeDeploy action

Trong mỗi deploy stage, action dùng application/deployment group của account đích và roleArn của cross-account deploy role.

Ví dụ:

~~~json
{
  "name": "DeployStaging",
  "actions": [
    {
      "name": "DeployOrdersApi",
      "actionTypeId": {
        "category": "Deploy",
        "owner": "AWS",
        "provider": "CodeDeploy",
        "version": "1"
      },
      "configuration": {
        "ApplicationName": "orders-api",
        "DeploymentGroupName": "orders-staging"
      },
      "inputArtifacts": [
        {
          "name": "BuildArtifact"
        }
      ],
      "outputArtifacts": [],
      "roleArn": "arn:aws:iam::777788889999:role/CodePipelineDeployRole",
      "runOrder": 1
    }
  ],
  "onFailure": {
    "result": "ROLLBACK"
  }
}
~~~

Role ARN phải thuộc account sở hữu CodeDeploy application và deployment group. CodePipeline service role ở tooling account phải được phép assume role đó, và trust policy của role đích phải tin cậy đúng service role.

Không dùng một action role ở staging để deploy sang production. Mỗi account có role và resource scope riêng.

## 25. Manual approval trước production

Manual approval action tạo gate trước production stage. Người phê duyệt nên xem:

- Commit SHA và pull request đã được merge.
- Build ID và artifact checksum.
- Unit/integration test report.
- Kết quả deployment ở dev và staging.
- CloudWatch alarm state và smoke test.
- Release notes và thay đổi database.
- Rollback revision và owner trực ca.

Ví dụ action:

~~~json
{
  "name": "ApproveProduction",
  "actions": [
    {
      "name": "ReleaseApproval",
      "actionTypeId": {
        "category": "Approval",
        "owner": "AWS",
        "provider": "Manual",
        "version": "1"
      },
      "configuration": {
        "CustomData": "Review staging results, artifact digest, migration plan and rollback readiness.",
        "ExternalEntityLink": "https://example.invalid/release-review"
      },
      "inputArtifacts": [],
      "outputArtifacts": [],
      "runOrder": 1
    }
  ]
}
~~~

Thay link minh họa bằng trang release review nội bộ. Có thể cấu hình SNS topic để thông báo người phê duyệt. Approval không thay thế review code hoặc security gate.

## 26. Promotion cùng một artifact qua các account

Artifact được tạo trong Build stage và dùng lại cho mọi môi trường.

Ví dụ release metadata:

~~~json
{
  "service": "orders-api",
  "version": "1.8.4",
  "commit": "a1b2c3d4e5f6",
  "buildId": "orders-api:1042",
  "artifactSha256": "replace-with-real-sha256",
  "createdAt": "2026-11-20T08:30:00Z"
}
~~~

Pipeline có thể lưu metadata này cùng artifact hoặc đính kèm vào release record. Ở mỗi account, xác minh checksum của JAR khớp với artifact đã được build.

Không rebuild source code ở production stage. Nếu staging pass nhưng production build lại binary khác, kết quả staging không còn chứng minh được binary đang chạy production.

## 27. Quản lý cấu hình và secret theo môi trường

Tách application artifact khỏi environment configuration.

| Dữ liệu | Nơi lưu phù hợp |
|---|---|
| Database endpoint | Parameter Store hoặc configuration service |
| Database password | Secrets Manager |
| API token | Secrets Manager |
| Feature flag | AppConfig hoặc configuration store phù hợp |
| Public runtime setting | Parameter Store |
| Deployment metadata | Pipeline artifact hoặc release record |

Ứng dụng trên EC2 dùng instance profile để đọc đúng parameter/secret trong account và Region của môi trường. Không copy production secret sang dev hoặc staging.

Khi secret được rotate, kiểm tra ứng dụng có refresh credential và connection pool đúng cách. Secret rotation là một change riêng cần monitoring và rollback plan.

## 28. Quan sát pipeline và deployment

Theo dõi cả pipeline và ứng dụng:

| Tầng | Metrics / events | Mục đích |
|---|---|---|
| CodePipeline | PipelineExecution, stage/action status | Biết release dừng ở đâu |
| CodeBuild | Build duration, failed builds, report summary | Phát hiện test/build failure |
| CodeDeploy | Deployment status, lifecycle event, rollback event | Theo dõi deployment |
| EC2 / Auto Scaling | Healthy instances, CPU, memory, status checks | Xác định compute health |
| ALB | Target 5xx, target response time, HealthyHostCount | Đo sức khỏe request |
| Application | Error rate, p95/p99 latency, business success rate | Xác minh customer impact |
| IAM / audit | CloudTrail AssumeRole, CodeDeploy API calls | Truy vết principal và action |

Gắn release ID, commit SHA và deployment ID vào application logs/metrics nếu có thể. Khi alarm xảy ra, người trực có thể liên kết metric với đúng phiên bản đang chạy.

CloudTrail ghi lại các API calls như AssumeRole, CreateDeployment và thay đổi deployment group. CloudWatch Logs giữ application logs và lifecycle script output theo retention policy.

## 29. Kiểm thử cross-account permissions

Trước khi chạy pipeline đầy đủ, kiểm tra từng quyền:

1. CodePipeline service role có sts:AssumeRole trên deploy role đích.
2. Trust policy của deploy role chỉ tin cậy CodePipeline service role.
3. Deploy role đọc được artifact object trong S3.
4. Deploy role decrypt được artifact bằng KMS key.
5. CodeDeploy action gọi được application và deployment group.
6. EC2 instance profile đọc được artifact và decrypt key.
7. CodeDeploy service role có thể quản lý deployment target.
8. EC2 instance có thể gọi CodeDeploy endpoint và health dependencies.

Dùng STS để xác minh identity sau khi assume role. Nếu AssumeRole thành công nhưng deploy fail, kiểm tra permission policy của role đích và resource policy. Nếu CodeDeploy tạo deployment nhưng instance không tải revision, kiểm tra instance profile, S3 bucket policy, KMS key policy, route và agent logs.

## 30. Kiểm thử automatic rollback ở development hoặc staging

Không thử nghiệm rollback bằng cách cố ý phá production.

Kịch bản kiểm thử:

1. Deploy phiên bản ổn định vào development.
2. Xác minh health endpoint và ghi lại deployment ID.
3. Tạo revision thử nghiệm có ValidateService hook trả lỗi có chủ đích.
4. Chạy pipeline tới development.
5. Xác minh CodeDeploy đánh dấu deployment thất bại.
6. Xác minh automatic rollback tạo deployment mới từ revision thành công trước.
7. Kiểm tra ALB target health, application version và request success.
8. Lặp lại bằng CloudWatch alarm test trong staging.
9. Xác minh pipeline stage status và rollback history.

Dùng alarm test riêng và ngưỡng dễ kích hoạt trong staging. Không chỉnh alarm production chỉ để tạo tình huống thử nghiệm.

## 31. Kiểm thử CodePipeline stage rollback

Stage rollback cần có execution thành công trước trong cùng pipeline structure version.

Quy trình:

1. Tạo pipeline V2 và cấu hình stage OnFailure Result ROLLBACK.
2. Chạy pipeline thành công ít nhất một lần để stage có known-good execution.
3. Tạo một build/revision test khiến smoke-test action trong deploy stage thất bại.
4. Chạy pipeline.
5. Xác minh stage fail và rollback được khởi chạy.
6. Kiểm tra stage quay lại artifact/revision của execution thành công gần nhất.
7. Kiểm tra execution history cho rollback execution mới.
8. Xác minh ứng dụng vẫn ở phiên bản ổn định.

Nếu pipeline vừa thay đổi cấu trúc, execution cũ có thể không đủ điều kiện làm rollback target. Hãy tạo một execution thành công với cấu trúc hiện tại trước khi kiểm thử.

## 32. Kiểm thử manual approval và promotion gate

Tạo một release test và xác minh:

- Pipeline dừng ở Approval stage.
- Người không có quyền approval không thể approve.
- Người có quyền có thể xem commit, test result và artifact digest.
- Reject khiến pipeline dừng trước production.
- Approve cho phép production stage bắt đầu.
- Production action dùng đúng cross-account role.
- Artifact digest production giống staging.

Không đặt approval credential hoặc external link có token trong CustomData. Approval message chỉ nên chứa metadata và liên kết tới hệ thống release review có access control.

## 33. Failure scenarios và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| Source action không chạy | Connection chưa AVAILABLE hoặc thiếu quyền repo | Kiểm tra connection status, repository access và branch |
| CodeBuild không lấy được source | Pipeline/CodeBuild role thiếu artifact permission | Kiểm tra CodeBuild service role và artifact input |
| AssumeRole AccessDenied | Trust policy sai principal hoặc thiếu sts:AssumeRole | Kiểm tra ARN của pipeline service role và policy |
| S3 AccessDenied | Bucket policy hoặc role policy không cho phép | Kiểm tra object ARN, bucket ARN và principal |
| KMS AccessDenied | Key policy hoặc identity policy thiếu decrypt | Kiểm tra key ARN, Region và role |
| CodeDeploy action không tìm thấy group | Application/group name hoặc account/Region sai | Xác minh resource trong account đích |
| EC2 không tải revision | Instance profile thiếu S3/KMS hoặc network path | Kiểm tra agent log, instance profile, S3/KMS endpoint |
| Deployment thất bại ở hook | Script lỗi, thiếu dependency hoặc quyền OS | Kiểm tra lifecycle event log |
| Alarm không được đánh giá | Alarm name/Region sai hoặc CodeDeploy role thiếu quyền | Kiểm tra AlarmConfiguration và service role |
| Rollback không xảy ra | Chưa bật event, không có known-good revision | Kiểm tra AutoRollbackConfiguration và lịch sử deployment |
| Pipeline stage không rollback | Pipeline không phải V2 hoặc đang PARALLEL | Kiểm tra pipelineType và executionMode |
| Stage rollback không có target | Chưa có successful execution cùng structure version | Chạy thành công pipeline với cấu trúc hiện tại |
| Ứng dụng cũ vẫn lỗi sau rollback | Database/schema hoặc side effect không tương thích | Kiểm tra migration và backward compatibility |
| Staging pass nhưng production fail | Configuration, quota, network hoặc dependency khác nhau | So sánh environment configuration và IAM/network |

## 34. Troubleshooting theo thứ tự

Khi một cross-account deployment thất bại, đi theo thứ tự:

1. **Pipeline execution:** xác định stage/action fail, execution ID và error code.
2. **Account/Region:** xác minh action đang chạy ở đúng account và Region.
3. **AssumeRole:** kiểm tra principal thực tế và trust relationship.
4. **Artifact:** kiểm tra S3 bucket, object key, version và artifact checksum.
5. **KMS:** kiểm tra key ARN, key policy, identity policy và Region.
6. **CodeDeploy:** kiểm tra application, deployment group, deployment ID và lifecycle event.
7. **EC2 agent:** kiểm tra agent status, instance profile, network và deployment logs.
8. **Application:** kiểm tra systemd, health endpoint, ALB target health và dependency.
9. **Rollback:** xác minh CodeDeploy hoặc CodePipeline rollback event và revision được khôi phục.

Không sửa policy bằng cách cấp AdministratorAccess cho tất cả role. Thêm quyền theo API, resource ARN và principal thực tế. Ghi lại policy change và chạy lại negative test để xác minh quyền không bị mở rộng quá mức.

## 35. Bảo mật và kiểm soát thay đổi

Các nguyên tắc bảo mật:

- Production account chỉ nhận deploy từ pipeline role được phê duyệt.
- Trust policy chỉ tin cậy CodePipeline service role cụ thể.
- Pipeline action role chỉ có quyền trên CodeDeploy application/deployment group cần thiết.
- EC2 instance profile chỉ đọc artifact, log và secret cần thiết.
- S3 artifact bucket không public và yêu cầu TLS.
- KMS key được quản trị riêng; deploy role không có quyền quản trị key.
- GitHub repository yêu cầu branch protection và review.
- Buildspec được lưu trong repository đã review, không cho action override tùy tiện.
- Secret dùng Secrets Manager/Parameter Store, không dùng plaintext environment variable.
- CloudTrail và CodeDeploy events được lưu để audit.
- Production deployment có approval và release window nếu workload yêu cầu.

Nếu pipeline có quyền deploy production, quyền sửa pipeline và quyền thay đổi buildspec cũng là quyền có thể tác động production. Bảo vệ pipeline definition bằng review, IaC và hạn chế quyền update pipeline.

## 36. Quản lý chi phí và artifact retention

Chi phí dự án có thể đến từ CodeBuild minutes, CodePipeline actions, S3 artifact storage, KMS requests, EC2/ALB, CloudWatch logs/alarms và CodeDeploy target infrastructure.

Biện pháp:

- Dùng build cache cho dependency để giảm build time.
- Chọn CodeBuild compute phù hợp workload.
- Dùng EC2 Auto Scaling group có capacity tối thiểu phù hợp môi trường.
- Tắt hoặc scale down dev/staging khi không sử dụng nếu kiến trúc cho phép.
- Đặt retention cho CloudWatch Logs.
- Dùng S3 lifecycle cho artifact cũ nhưng giữ đủ thời gian rollback/audit.
- Theo dõi build duration và failed build để tránh chi phí retry liên tục.
- Dùng cost allocation tags cho project, environment và owner.

Không xóa artifact của phiên bản đang được xem là last-known-good. Retention phải dài hơn cửa sổ rollback và đáp ứng yêu cầu audit của tổ chức.

## 37. Lab triển khai capstone

Thực hiện trong AWS test accounts được phê duyệt. Bắt đầu với tooling và development; chỉ thêm production account sau khi cross-account permission và rollback đã được kiểm chứng.

### Bước 1: Chuẩn bị account

- Xác định tooling, dev, staging và prod account ID.
- Chọn một Region chung.
- Tạo VPC, ALB và EC2 Auto Scaling group trong mỗi environment account.
- Cài CodeDeploy agent trên EC2.
- Tạo CodeDeploy service role và instance profile.
- Ghi lại ARN của các role.

### Bước 2: Tạo artifact infrastructure trong tooling

- Tạo S3 artifact bucket.
- Bật Block Public Access và versioning.
- Tạo customer-managed KMS key.
- Cấu hình CodePipeline service role.
- Cấp S3/KMS access cho pipeline service role.
- Chuẩn bị bucket policy và key policy cho target roles.

### Bước 3: Thiết lập cross-account roles

Trong mỗi environment account:

- Tạo CodePipelineDeployRole.
- Trust chính xác CodePipelineServiceRole trong tooling.
- Cấp quyền CodeDeploy tối thiểu.
- Cấp S3 GetObject và KMS Decrypt cho artifact.
- Cấp S3/KMS read cho CodeDeployInstanceRole.
- Kiểm tra AssumeRole và artifact access.

### Bước 4: Tạo CodeDeploy resources

- Tạo CodeDeploy application orders-api.
- Tạo deployment group theo môi trường.
- Gắn Auto Scaling group.
- Chọn deployment configuration.
- Tạo CloudWatch alarms.
- Bật automatic rollback cho deployment failure và alarm.

### Bước 5: Tạo source và build

- Tạo CodeConnections GitHub connection.
- Tạo CodeBuild project và service role.
- Đưa buildspec, appspec và lifecycle scripts vào repository.
- Chạy build/test trực tiếp trước khi kết nối pipeline.
- Xác minh BuildArtifact chứa đúng file và checksum.

### Bước 6: Tạo CodePipeline V2

- Thêm Source action.
- Thêm CodeBuild action.
- Thêm DeployDev action với dev role ARN.
- Thêm smoke test trong deploy stage.
- Thêm DeployStaging action với staging role ARN.
- Thêm integration test và acceptance gate.
- Thêm Manual approval.
- Thêm DeployProduction action với production role ARN.
- Cấu hình OnFailure Result ROLLBACK cho các deploy stage cần rollback.

### Bước 7: Kiểm thử release thành công

- Merge một commit nhỏ vào main.
- Theo dõi source, build, deploy dev và staging.
- Approve production.
- Xác minh ứng dụng trả đúng version.
- So sánh SHA-256 artifact giữa các môi trường.
- Lưu execution ID và deployment ID.

### Bước 8: Kiểm thử rollback

- Trong dev, tạo revision có health check fail.
- Xác minh CodeDeploy automatic rollback.
- Trong staging, tạo smoke test fail sau deploy.
- Xác minh CodePipeline stage rollback.
- Ghi nhận thời gian rollback và trạng thái ứng dụng.
- Khôi phục test alarm và revision ổn định.

### Bước 9: Dọn dẹp

- Xóa pipeline và build project nếu lab không còn dùng.
- Xóa CodeDeploy deployment group/application theo thứ tự dependency.
- Xóa EC2/ALB/Auto Scaling group và VPC test nếu không còn cần.
- Giữ lại report và log theo retention đã chọn.
- Không xóa KMS key hoặc artifact cần cho audit trước khi xác nhận chính sách lưu trữ.

## 38. Runbook vận hành release và rollback

### Trước release

1. Xác minh main đã được review và merge.
2. Kiểm tra test report và security scan.
3. Ghi artifact digest và commit SHA.
4. Xác nhận CloudWatch alarms đang ở trạng thái OK.
5. Xác nhận có last-known-good revision.
6. Kiểm tra database migration có backward compatible.
7. Xác nhận người trực và release approver sẵn sàng.

### Khi deploy

1. Theo dõi CodePipeline stage/action.
2. Theo dõi CodeDeploy lifecycle events.
3. Theo dõi CloudWatch alarm và target health.
4. Không thay đổi deployment group trong lúc release nếu chưa có kế hoạch.
5. Nếu alarm kích hoạt, để CodeDeploy thực hiện automatic rollback và xác minh kết quả.
6. Nếu smoke test fail, xác minh CodePipeline stage rollback.
7. Nếu rollback không thành công, dừng promotion và gọi incident owner.

### Sau release

1. Xác minh application version, deployment ID và artifact digest.
2. Theo dõi 5xx, latency, healthy hosts và business KPI.
3. Kiểm tra queue/backlog hoặc async jobs nếu ứng dụng có.
4. Cập nhật release record.
5. Đóng change sau khi hết observation window.

## 39. Checklist nghiệm thu production

### Pipeline

- [ ] Source connection dùng GitHub App/CodeConnections.
- [ ] Branch protection và code review được bật.
- [ ] Pipeline dùng CodePipeline V2.
- [ ] Execution mode không phải PARALLEL nếu cần stage rollback.
- [ ] Build/test gate chạy trước deploy.
- [ ] Artifact được tạo một lần và promotion qua các account.
- [ ] Production có manual approval.

### Cross-account security

- [ ] Tooling service role chỉ assume đúng deploy roles.
- [ ] Trust policy target chỉ tin cậy pipeline service role.
- [ ] Deploy role có quyền CodeDeploy và artifact tối thiểu.
- [ ] Artifact bucket policy chỉ cho principal cần thiết.
- [ ] KMS key policy và IAM policy cho phép đúng role.
- [ ] EC2 instance profile đọc được artifact và decrypt key.
- [ ] CodeDeploy service role tách khỏi action role.
- [ ] Không dùng static AWS credentials.

### Deployment and rollback

- [ ] CodeDeploy agent hoạt động trên EC2.
- [ ] AppSpec và lifecycle scripts đã được kiểm thử.
- [ ] Deployment group gắn đúng Auto Scaling group.
- [ ] CloudWatch alarms có baseline và threshold.
- [ ] CodeDeploy auto rollback bật cho failure và alarm.
- [ ] CodePipeline stage rollback được cấu hình.
- [ ] Có successful execution làm rollback target.
- [ ] Rollback test đã chạy ở dev/staging.
- [ ] Database migration tương thích với phiên bản trước.
- [ ] Artifact retention đáp ứng cửa sổ rollback.

### Operations

- [ ] Có dashboard và alert cho pipeline/deployment/application.
- [ ] Có owner và runbook cho release failure.
- [ ] Có release record với commit, artifact digest và deployment ID.
- [ ] Có log retention và audit trail.
- [ ] Có budget alert và cleanup cho non-production.

## 40. Bài tập tự kiểm tra

### Câu 1

Vì sao nên đặt CodePipeline trong tooling account?

**Đáp án:** Để tập trung quyền điều phối release, quản lý artifact và audit; các account môi trường chỉ cấp quyền deploy cần thiết.

### Câu 2

Cross-account deploy action dùng cơ chế nào để truy cập account đích?

**Đáp án:** CodePipeline assume IAM role ở account đích bằng STS; action khai báo role ARN tương ứng.

### Câu 3

Trust policy và permission policy khác nhau thế nào?

**Đáp án:** Trust policy xác định principal được assume role; permission policy xác định hành động role được phép thực hiện sau khi assume.

### Câu 4

Vì sao CodePipeline cross-account cần customer-managed KMS key?

**Đáp án:** Để cho phép role ở account khác giải mã artifact qua key policy và IAM policy; AWS managed key mặc định không đáp ứng cross-account key sharing theo hướng dẫn này.

### Câu 5

Tại sao EC2 instance profile cũng cần S3/KMS access?

**Đáp án:** CodeDeploy agent trên instance cần tải artifact từ S3 và giải mã nếu object được mã hóa bằng KMS.

### Câu 6

Artifact cross-account nên được lưu ở đâu?

**Đáp án:** Trong artifact store của pipeline account; các action ở account đích đọc artifact từ đó.

### Câu 7

Có thể chuyển artifact trực tiếp từ dev account sang staging account trong cùng pipeline không?

**Đáp án:** Không theo giới hạn cross-account artifact của CodePipeline; artifact nên được tạo trong pipeline account hoặc bởi action trước đó trong cùng account của action tiêu thụ.

### Câu 8

CodeBuild thực hiện nhiệm vụ gì trong capstone?

**Đáp án:** Chạy test, build package, tạo deployment bundle, checksum và output artifact cho các deploy stage.

### Câu 9

Vì sao không rebuild ứng dụng riêng cho production?

**Đáp án:** Vì binary production có thể khác binary đã được test ở staging; promotion cùng artifact giữ tính nhất quán.

### Câu 10

CodeDeploy automatic rollback được kích hoạt bởi những điều kiện nào?

**Đáp án:** Deployment failure hoặc CloudWatch alarm được cấu hình cho deployment group chuyển sang ALARM.

### Câu 11

CodeDeploy rollback hoạt động theo cách nào?

**Đáp án:** Nó tạo một deployment mới để triển khai lại revision thành công gần nhất; deployment ID mới được cấp.

### Câu 12

CodePipeline V2 stage rollback khác CodeDeploy rollback thế nào?

**Đáp án:** CodeDeploy rollback khôi phục application revision trong deployment group; CodePipeline rollback khôi phục stage về execution thành công gần nhất.

### Câu 13

Tại sao stage rollback cần successful execution trước?

**Đáp án:** Vì pipeline cần một execution thành công trong cùng pipeline structure version làm rollback target.

### Câu 14

Pipeline PARALLEL mode có hỗ trợ stage rollback không?

**Đáp án:** Không. Dùng SUPERSEDED hoặc QUEUED nếu cần rollback.

### Câu 15

Vì sao nên đặt deploy và smoke test trong cùng stage?

**Đáp án:** Để smoke-test failure làm deploy stage thất bại và kích hoạt stage rollback trên chính stage đã triển khai.

### Câu 16

CloudWatch alarm nên theo dõi những tín hiệu nào?

**Đáp án:** Application 5xx/error rate, latency, healthy host/instance count và business metric liên quan SLO.

### Câu 17

Nếu deployment lần đầu thất bại thì CodeDeploy có revision cũ để rollback không?

**Đáp án:** Không nếu chưa có deployment thành công trước đó; cần bootstrap một known-good revision.

### Câu 18

CodeDeploy rollback có tự hoàn tác database migration không?

**Đáp án:** Không. Database migration cần backward compatibility, backup và recovery plan riêng.

### Câu 19

Vì sao không nên cấp AdministratorAccess cho cross-account deploy role?

**Đáp án:** Vì pipeline chỉ cần một tập API và resource cụ thể; quyền quá rộng làm tăng blast radius nếu pipeline hoặc source bị xâm phạm.

### Câu 20

Những bằng chứng nào cần lưu sau mỗi release?

**Đáp án:** Commit SHA, build ID, artifact checksum, pipeline execution ID, deployment ID, approval identity, alarm state và test report.

## 41. Tài liệu tham khảo chính thức

- [Create a pipeline in CodePipeline that uses resources from another AWS account](https://docs.aws.amazon.com/codepipeline/latest/userguide/pipelines-create-cross-account.html)
- [Configure a stage for automatic rollback](https://docs.aws.amazon.com/codepipeline/latest/userguide/stage-rollback-auto.html)
- [Configure conditions for a stage](https://docs.aws.amazon.com/codepipeline/latest/userguide/stage-conditions.html)
- [Set or change the pipeline execution mode](https://docs.aws.amazon.com/codepipeline/latest/userguide/execution-modes.html)
- [How pipeline executions work](https://docs.aws.amazon.com/codepipeline/latest/userguide/concepts-how-it-works.html)
- [GitHub connections for CodePipeline](https://docs.aws.amazon.com/codepipeline/latest/userguide/connections-github.html)
- [CodeBuild build and test action reference](https://docs.aws.amazon.com/codepipeline/latest/userguide/action-reference-CodeBuild.html)
- [CodeDeploy deployment groups and advanced options](https://docs.aws.amazon.com/codedeploy/latest/userguide/deployment-groups-configure-advanced-options.html)
- [Monitoring deployments with CloudWatch alarms in CodeDeploy](https://docs.aws.amazon.com/codedeploy/latest/userguide/monitoring-create-alarms.html)
- [Redeploy and roll back a deployment with CodeDeploy](https://docs.aws.amazon.com/codedeploy/latest/userguide/deployments-rollback-and-redeploy.html)
- [Deployments on an EC2/On-Premises compute platform](https://docs.aws.amazon.com/codedeploy/latest/userguide/deployment-steps.html)
- [Application Specification files for CodeDeploy](https://docs.aws.amazon.com/codedeploy/latest/userguide/application-specification-files.html)
- [AWS Prescriptive Guidance: CI/CD best practices](https://docs.aws.amazon.com/prescriptive-guidance/latest/strategy-cicd-litmus/cicd-best-practices.html)
- [AWS CodePipeline security](https://docs.aws.amazon.com/codepipeline/latest/userguide/security.html)
- [AWS KMS key policies](https://docs.aws.amazon.com/kms/latest/developerguide/key-policies.html)
- [Using IAM roles to delegate permissions across AWS accounts](https://docs.aws.amazon.com/IAM/latest/UserGuide/tutorial_cross-account-with-roles.html)

Các tên action, quota, Region availability và behavior có thể thay đổi theo dịch vụ. Trước khi triển khai, kiểm tra tài liệu hiện hành, service authorization reference và quota của từng account. Hãy thử nghiệm deployment failure, alarm rollback và stage rollback trong account test trước khi bật tự động hóa ở production.

