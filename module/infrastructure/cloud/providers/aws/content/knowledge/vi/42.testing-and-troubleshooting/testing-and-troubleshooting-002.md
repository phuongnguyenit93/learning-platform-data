# Tài khoản sandbox, dữ liệu thử và cô lập môi trường

Trong AWS, một sandbox là môi trường có phạm vi truy cập, dữ liệu, chi phí và vòng đời được kiểm soát để nhóm phát triển có thể thử nghiệm mà không ảnh hưởng workload khác. Sandbox không phải một dịch vụ AWS độc lập. Nó thường được xây dựng bằng AWS account riêng, AWS Organizations, IAM Identity Center, Service Control Policies (SCP), VPC riêng, dữ liệu thử đã chuẩn bị và quy trình tự động tạo/xóa tài nguyên.

Một AWS account là ranh giới quan trọng để cô lập tài nguyên, quyền truy cập, chi phí và nhiều service quota. Vì vậy, môi trường production nên được tách khỏi development, test và sandbox bằng account riêng khi yêu cầu bảo mật hoặc mức độ ảnh hưởng đủ lớn. AWS Control Tower và Account Factory giúp chuẩn hóa việc tạo account; AWS Organizations quản lý Organizational Unit (OU) và guardrail; IAM Identity Center cấp quyền tạm thời; AWS Budgets và IaC giúp theo dõi chi phí, tái tạo và dọn dẹp môi trường.

Bài học này trình bày cách thiết kế sandbox trong hệ sinh thái AWS, cách chọn account boundary và network boundary, cách tạo dữ liệu thử an toàn, cách kiểm soát truy cập và chi phí, cũng như cách kết thúc một môi trường tạm mà không để lại tài nguyên mồ côi.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích mục đích của sandbox và phân biệt sandbox với dev, test, staging và production.
- Giải thích vì sao AWS account là ranh giới cô lập quan trọng.
- Thiết kế cấu trúc AWS Organizations gồm OU và workload accounts.
- Sử dụng AWS Control Tower Account Factory để cấp phát account theo baseline.
- Phân quyền cho developer bằng IAM Identity Center và permission set.
- Giải thích vai trò, giới hạn và cách thử nghiệm SCP.
- Cô lập VPC, subnet, route, security group, endpoint và kết nối liên account.
- Chọn dữ liệu synthetic, masked hoặc anonymized cho test.
- Sử dụng AWS Glue DataBrew hoặc AWS DMS khi cần xử lý dữ liệu nhạy cảm.
- Hiểu rủi ro khi clone hoặc restore dữ liệu production vào môi trường thử.
- Tách secrets, KMS keys, database và bucket theo môi trường.
- Chuẩn hóa môi trường bằng CloudFormation, CDK hoặc Terraform.
- Đặt budget, cảnh báo, tag và giới hạn quota cho sandbox.
- Tạo quy trình tự động hết hạn và cleanup tài nguyên.
- Xây dựng checklist kiểm tra trước, trong và sau một đợt thử nghiệm.

## 2. Sandbox là gì và dùng khi nào?

Sandbox là môi trường thử nghiệm có quyền và tài nguyên được giới hạn. Người dùng có thể tạo, thay đổi và xóa tài nguyên để học tập, phát triển prototype, kiểm tra service integration hoặc thử nghiệm một thay đổi hạ tầng.

Các tình huống thường gặp:
- Học một dịch vụ AWS mới như Lambda, DynamoDB, S3 hoặc EventBridge.
- Thử một kiến trúc proof of concept (PoC).
- Kiểm tra IAM policy, SCP hoặc cấu hình network.
- Chạy integration test giữa nhiều service.
- Kiểm tra migration, schema change hoặc data pipeline.
- Thử phiên bản ứng dụng mới trước khi đưa vào staging.
- Đào tạo kỹ sư mới mà không cấp quyền vào production.

Sandbox cần có giới hạn rõ ràng:
- Ai được tạo và xóa tài nguyên?
- Được phép dùng Region và service nào?
- Dữ liệu nào được phép đưa vào?
- Mức chi phí tối đa dự kiến là bao nhiêu?
- Môi trường tồn tại trong bao lâu?
- Ai chịu trách nhiệm dọn dẹp?
- Tài nguyên nào được giữ lại sau khi thử nghiệm?

Một account sandbox vẫn có thể phát sinh chi phí thật. EC2, NAT Gateway, RDS, EBS, snapshots, public IPv4, data transfer và nhiều dịch vụ khác có thể tiếp tục tính phí khi người dùng quên dừng hoặc xóa tài nguyên.

## 3. Phân biệt các môi trường

| Môi trường | Mục đích | Dữ liệu | Quyền truy cập | Vòng đời |
|---|---|---|---|---|
| Local | Unit test, kiểm tra logic không cần cloud thật | Fixture nhỏ, synthetic | Developer trên máy | Theo phiên làm việc |
| Sandbox | Học tập, PoC, thử service hoặc kiến trúc | Synthetic hoặc dữ liệu đã xử lý | Quyền thử nghiệm có giới hạn | Tạm thời, có TTL |
| Development | Phát triển tính năng và tích hợp liên tục | Synthetic, fixture hoặc masked | Developer và pipeline | Duy trì theo sprint |
| Test/QA | Kiểm thử chức năng, regression và integration | Bộ test được quản lý | QA và CI/CD | Theo release |
| Staging | Xác minh gần production, rehearsal release | Dữ liệu synthetic/masked có tính đại diện | Nhóm release và vận hành | Theo release hoặc lâu dài |
| Production | Phục vụ người dùng thật | Dữ liệu thật theo chính sách | Quyền hạn chế, có phê duyệt | Liên tục |

Không phải tổ chức nào cũng cần một account cho từng môi trường. Tuy nhiên, account-level separation được khuyến nghị mạnh khi workload có dữ liệu nhạy cảm, yêu cầu tuân thủ, quyền vận hành khác nhau hoặc blast radius lớn.

Một nhóm nhỏ có thể dùng một non-production account cho dev/test với VPC và role tách biệt. Khi số nhóm, dữ liệu hoặc mức độ rủi ro tăng, hãy tách thành account riêng cho từng workload hoặc từng môi trường. Production và staging nên có account riêng với control khác nhau.

## 4. Vì sao nên cô lập bằng AWS account?

AWS account là container tài nguyên và ranh giới cô lập cho quyền truy cập, billing và nhiều service quota. Tách account giúp:

- Giảm blast radius khi developer tạo nhầm hoặc xóa nhầm tài nguyên.
- Tách chi phí theo project hoặc workload.
- Giới hạn quyền và policy theo từng môi trường.
- Quản lý service quota và API request rate độc lập ở nhiều dịch vụ.
- Dễ áp dụng guardrail khác nhau cho sandbox, non-production và production.
- Giảm nguy cơ test job hoặc script tác động đến production.
- Dễ đóng một sandbox account đã hết hạn.

Ví dụ, một lệnh xóa database chạy nhầm trong sandbox account không trực tiếp xóa database ở production account nếu không có quyền cross-account phù hợp.

Tuy nhiên, account boundary không tự động ngăn mọi truy cập liên account. Nếu có IAM role trust, resource policy, KMS key policy, VPC peering, Transit Gateway, shared resource hoặc credential dùng chung, hai account vẫn có thể tương tác. Vì vậy, mọi kết nối xuyên account phải được thiết kế và cấp quyền rõ ràng.

### 4.1 Khi nào một account là chưa đủ?

Nên tách thêm account khi:
- Nhóm phát triển có quyền AdministratorAccess rộng.
- Dữ liệu thử có độ nhạy khác dữ liệu staging.
- Một thử nghiệm có khả năng tạo tải hoặc chi phí lớn.
- Cần kiểm tra guardrail, account vending hoặc landing zone.
- Có yêu cầu compliance hoặc audit tách biệt.
- Một workload cần quyền truy cập dịch vụ khác với workload còn lại.
- Cần tránh một team chiếm hết quota của team khác.

Không nên tạo account mới chỉ để đổi tên một môi trường nếu không có lợi ích quản trị rõ ràng. Account quá nhiều mà thiếu tự động hóa sẽ tăng công việc vận hành, logging, identity, billing và baseline.

## 5. Thiết kế AWS Organizations và OU

AWS Organizations quản lý tập trung nhiều AWS account trong một organization. OU nhóm các account có yêu cầu governance tương tự. SCP gắn vào root, OU hoặc account để giới hạn quyền tối đa mà principal trong member account có thể sử dụng.

Một cấu trúc tham khảo:

~~~text
AWS Organization
|
+-- Root
    |
    +-- Security OU
    |   +-- Log Archive account
    |   +-- Audit / Security account
    |
    +-- Infrastructure OU
    |   +-- Network account
    |   +-- Shared Services account
    |
    +-- Sandbox OU
    |   +-- Sandbox-Training account
    |   +-- Sandbox-Team-A account
    |
    +-- NonProduction OU
    |   +-- Development account
    |   +-- Test account
    |   +-- Staging account
    |
    +-- Production OU
        +-- Workload-Production account
~~~

Ý nghĩa:
- **Management account:** quản lý organization và billing; cần giới hạn người có quyền truy cập.
- **Log Archive account:** lưu log tập trung theo kiến trúc tổ chức.
- **Audit/Security account:** dành cho hoạt động kiểm tra và bảo mật.
- **Infrastructure OU:** chứa network, shared services hoặc nền tảng dùng chung.
- **Sandbox OU:** chứa account thử nghiệm với quota, budget và guardrail riêng.
- **NonProduction OU:** chứa môi trường dev/test/staging.
- **Production OU:** chứa workload phục vụ người dùng thật với policy chặt hơn.

Không nhất thiết phải có đúng tên OU như ví dụ. Thiết kế OU theo nhóm workload và control cần áp dụng, không theo sơ đồ phòng ban.

### 5.1 Guardrail khác nhau theo OU

Ví dụ:
- Sandbox OU cho phép tạo nhiều loại tài nguyên thử nghiệm nhưng hạn chế Region, service nhạy cảm và quyền thay đổi audit control.
- NonProduction OU cho phép deploy tự động qua CI/CD và truy cập test data.
- Production OU yêu cầu change approval, deployment role riêng và quyền vận hành hạn chế.
- Security OU có quyền quan sát và audit tập trung.

AWS Control Tower cung cấp landing zone và controls để quản trị multi-account environment. Account Factory hỗ trợ cấp phát account mới theo cấu hình đã đăng ký. Account Factory Customization hoặc Account Factory for Terraform (AFT) có thể giúp tự động hóa baseline và cấu hình tùy chỉnh theo nhu cầu.

## 6. Cấp phát sandbox account bằng AWS Control Tower

Account Factory là cách chuẩn để tạo hoặc cập nhật member account trong AWS Control Tower landing zone. Người vận hành chọn OU, email account và cấu hình truy cập. Tổ chức có thể tự động hóa account provisioning bằng API, Lambda hoặc AFT.

Quy trình cấp phát gợi ý:

1. Người dùng gửi yêu cầu sandbox với project, owner, mục đích và thời hạn.
2. Hệ thống kiểm tra người yêu cầu có quyền tạo sandbox.
3. Chọn OU Sandbox và baseline phù hợp.
4. Cấp phát account qua Account Factory.
5. Gán user/group trong IAM Identity Center.
6. Áp dụng SCP, logging, Config và security baseline.
7. Tạo budget, tag chuẩn và thông tin hết hạn.
8. Triển khai VPC, role và template cần thiết.
9. Gửi account access cho owner.
10. Ghi nhận account ID, owner, expiry date và cost center.

Một account sandbox nên có thông tin quản lý:
- Account alias hoặc display name.
- Account ID.
- Project/experiment ID.
- Owner/team.
- Request ticket hoặc lý do tạo.
- Ngày tạo và ngày hết hạn.
- Budget và người nhận cảnh báo.
- OU và baseline.
- Region được phép.
- Dữ liệu được phép sử dụng.
- Quy trình gia hạn hoặc đóng account.

Không tạo account bằng cách chia sẻ root credentials. Root account email, MFA và recovery process phải được quản lý tập trung.

## 7. Quản lý quyền với IAM Identity Center

AWS IAM Identity Center cho phép cấp quyền vào nhiều AWS account thông qua user/group và permission set. Đây là cách phù hợp để developer truy cập sandbox mà không cần tạo IAM user dài hạn trong từng account.

Một mô hình đơn giản:

| Nhóm | Sandbox | Development/Test | Production |
|---|---|---|---|
| Developer | Power user có giới hạn | Deploy/dev role | Read-only hoặc không truy cập |
| QA | Quyền test service | Test role | Read-only khi cần |
| Platform | Admin theo nhiệm vụ | Admin/deploy | Platform operations role |
| Security | Audit/read-only và security tools | Audit | Security audit |
| CI/CD | Deploy role scoped | Deploy role | Production deploy role có approval |

Permission set có thể dựa trên managed policy hoặc custom policy. Không nên mặc định gán AdministratorAccess cho mọi developer. Hãy cấp đúng service, resource và action cần thiết; tách quyền deploy khỏi quyền quản trị organization.

Nguyên tắc:
- Dùng federation và temporary credentials.
- Bật MFA.
- Không chia sẻ access key giữa các thành viên.
- Không nhúng credential vào source code hoặc AMI/container image.
- Dùng role riêng cho CI/CD.
- Đặt session duration phù hợp.
- Thu hồi assignment khi thành viên rời team hoặc sandbox hết hạn.
- Dùng CloudTrail để audit API activity.

Root user chỉ dùng cho các tác vụ yêu cầu root. Bảo vệ root bằng MFA và không tạo access key cho root.

## 8. SCP: guardrail cho sandbox account

SCP là policy của AWS Organizations dùng để xác định quyền tối đa mà principal trong member account có thể sử dụng. SCP không cấp quyền. Một API call chỉ thành công khi IAM/resource policy cho phép và không bị SCP áp dụng từ chối.

Ví dụ SCP cho Sandbox OU nhằm bảo vệ organization membership và audit controls:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PreventLeavingOrganization",
      "Effect": "Deny",
      "Action": [
        "organizations:LeaveOrganization",
        "account:CloseAccount"
      ],
      "Resource": "*"
    },
    {
      "Sid": "ProtectAuditConfiguration",
      "Effect": "Deny",
      "Action": [
        "cloudtrail:StopLogging",
        "cloudtrail:DeleteTrail",
        "config:StopConfigurationRecorder",
        "config:DeleteConfigurationRecorder"
      ],
      "Resource": "*"
    }
  ]
}
~~~

Đây là ví dụ guardrail để đọc và thử nghiệm trong account/OU riêng. Trước khi triển khai trên diện rộng, hãy kiểm tra service integration, CloudTrail organization trail, AWS Config recorder và các automation cần thiết.

Các giới hạn quan trọng:
- SCP không cấp quyền IAM.
- SCP không áp dụng cho management account.
- SCP không giới hạn quyền được gắn trực tiếp vào service-linked role.
- SCP có thể tác động cả root user trong member account.
- Deny từ bất kỳ cấp root/OU/account nào trên đường dẫn đều có hiệu lực.
- Một SCP quá rộng có thể chặn pipeline, logging hoặc quy trình cleanup.

Nên thử SCP trong một policy staging account/OU trước. Kiểm tra cả tác vụ tạo, cập nhật, xóa, logging, backup và hỗ trợ vận hành.

### 8.1 Ví dụ policy giới hạn Region

Một sandbox có thể chỉ được tạo tài nguyên trong các Region được tổ chức cho phép. Khi viết SCP dùng điều kiện `aws:RequestedRegion`, cần lưu ý một số global service và API không gắn với Region theo cách giống resource regional. Hãy dùng danh sách service exception dựa trên kiến trúc thực tế, thử nghiệm trong account riêng và kiểm tra các dịch vụ nền tảng trước khi áp dụng.

Không sao chép một deny-all-except-region policy vào root organization mà chưa đánh giá tác động đến IAM, billing, support, CloudFront, Route 53, IAM Identity Center và các global endpoint.

## 9. Cô lập network giữa các môi trường

Tách account là lớp cô lập quan trọng; network isolation là lớp bổ sung. Một VPC riêng cho mỗi workload/account giúp kiểm soát route, security group, subnet và kết nối.

Một thiết kế sandbox tham khảo:
- VPC CIDR riêng, không overlap với các VPC khác.
- Public subnet chỉ dành cho thành phần cần public access như NAT Gateway hoặc load balancer.
- Private subnet cho application và database.
- Security group chỉ mở port từ nguồn cần thiết.
- VPC endpoint cho S3, DynamoDB và các service hỗ trợ để giảm traffic ra Internet.
- Egress qua NAT hoặc proxy có kiểm soát.
- Không mặc định peering sandbox với production.
- Dùng Transit Gateway hoặc shared network account khi có nhu cầu kết nối được phê duyệt.

Ví dụ luồng:

~~~text
Sandbox Account
  |
  +-- Sandbox VPC
       |
       +-- Public subnet
       |     +-- NAT Gateway (nếu cần)
       |
       +-- Private app subnet
       |     +-- EC2 / ECS / Lambda ENI (nếu Lambda gắn VPC)
       |
       +-- Private data subnet
       |     +-- RDS / ElastiCache
       |
       +-- VPC endpoints
             +-- S3
             +-- DynamoDB
             +-- Systems Manager
~~~

Không dùng cùng CIDR cho mọi sandbox nếu có khả năng kết nối VPC-to-VPC sau này. CIDR overlap sẽ gây khó khăn khi dùng peering, Transit Gateway hoặc VPN.

### 9.1 Kiểm soát kết nối xuyên account

Nếu sandbox cần đọc artifact hoặc dataset ở account khác:
- Tạo role cross-account có trust policy chỉ định principal được phép assume.
- Dùng resource policy trên S3/KMS để giới hạn bucket, prefix và key.
- Chỉ mở network route khi thực sự cần.
- Dùng endpoint policy để giới hạn service access nếu phù hợp.
- Ghi audit và định kỳ rà soát trust relationship.
- Không cấp quyền truy cập production database chỉ để thuận tiện cho test.

### 9.2 Security group và network ACL

Security group là stateful và thường được dùng để giới hạn traffic ở cấp network interface. Network ACL là stateless và áp dụng ở subnet. Hãy ưu tiên security group với rule nhỏ và dễ hiểu; dùng NACL cho yêu cầu kiểm soát subnet bổ sung.

Tránh rule kiểu 0.0.0.0/0 trên SSH/RDP hoặc database port. Nếu cần truy cập quản trị, ưu tiên AWS Systems Manager Session Manager thay vì mở cổng quản trị Internet.

## 10. Cô lập dữ liệu và tài nguyên lưu trữ

Dữ liệu thử nghiệm cần tách khỏi dữ liệu production ở nhiều lớp:
- Account và bucket/database riêng.
- KMS key riêng hoặc key policy riêng theo môi trường.
- IAM role và resource policy riêng.
- Secret và connection string riêng.
- Backup/snapshot có owner và retention rõ ràng.
- Không dùng chung production database endpoint.
- Không tự động replicate dữ liệu nhạy cảm sang sandbox.
- Không để developer sandbox đọc bucket production bằng wildcard policy.

Ví dụ quy ước bucket:
- company-dev-app-data
- company-test-app-data
- company-staging-app-data
- company-prod-app-data

Tên bucket chỉ là quy ước. Bảo mật thực sự dựa vào account, IAM, bucket policy, KMS key policy, encryption và network controls.

### 10.1 Phân tách KMS key

Có thể dùng customer managed key riêng cho từng môi trường:
- Dev key chỉ cho dev roles.
- Test key chỉ cho test pipeline.
- Staging key chỉ cho staging workload.
- Production key chỉ cho production workload và security-approved roles.

Không dùng cùng một key policy quá rộng cho tất cả môi trường. Khi chia sẻ dữ liệu liên account, cần cả quyền IAM và key policy phù hợp; chỉ cấp quyền S3 không có nghĩa principal có thể giải mã object dùng KMS key.

## 11. Chọn dữ liệu thử: synthetic, masked hay anonymized?

Dữ liệu thử có thể chia thành ba loại:

| Loại | Mô tả | Ưu điểm | Rủi ro/giới hạn |
|---|---|---|---|
| Synthetic | Tạo mới bằng generator hoặc fixture, không lấy trực tiếp từ người dùng thật | Kiểm soát được, dễ tái tạo, ít rủi ro PII | Cần tạo phân phối và quan hệ dữ liệu đủ thực tế |
| Masked | Thay một phần hoặc toàn bộ giá trị nhạy cảm bằng giá trị khác | Giữ được một số cấu trúc và kiểu dữ liệu | Có thể còn khả năng nhận diện nếu mask chưa đủ |
| Anonymized | Xử lý để cá nhân không còn có thể được nhận diện hợp lý | Phù hợp phân tích/test khi thực hiện đúng | Khó đảo ngược; cần đánh giá re-identification risk |

Ưu tiên synthetic data cho sandbox. Nếu cần dữ liệu production-like, hãy đánh giá khả năng dùng masked/anonymized dataset trước khi dữ liệu rời production account.

Không xem việc đổi tên cột, bỏ tên người hoặc thay email bằng một chuỗi ngẫu nhiên đơn giản là anonymization hoàn chỉnh. Dữ liệu có thể vẫn nhận diện được qua địa chỉ, timestamp, mã định danh liên kết, hành vi hoặc kết hợp nhiều trường.

### 11.1 Synthetic data

Synthetic data được tạo từ schema, quy tắc nghiệp vụ và phân phối thống kê. Một dataset tốt nên giữ:
- Kiểu dữ liệu và constraint.
- Primary/foreign key relationship.
- Cardinality và phân phối giá trị.
- Tần suất null và missing field.
- Dữ liệu biên: min/max, chuỗi rỗng, ký tự Unicode.
- Trường hợp lỗi: duplicate, invalid state, expired record.
- Quan hệ thời gian giữa event.
- Các tình huống hiếm nhưng quan trọng.

Ví dụ dataset thương mại điện tử:
- Customers: customer_id, region, customer_tier.
- Orders: order_id, customer_id, created_at, status.
- OrderItems: order_id, product_id, quantity, unit_price.
- Payments: payment_id, order_id, payment_status.
- Shipments: shipment_id, order_id, delivery_status.

Generator cần tạo foreign key hợp lệ. Nếu tạo order trỏ đến customer không tồn tại, test sẽ thất bại vì dữ liệu sai thay vì vì lỗi ứng dụng.

### 11.2 Dữ liệu masked

Masking thay giá trị nhạy cảm bằng dữ liệu giả hoặc biến đổi. Một số phương pháp:
- Substitution: thay bằng giá trị hợp lệ khác.
- Shuffling: hoán đổi giá trị trong cùng cột.
- Randomization: tạo giá trị ngẫu nhiên.
- Hashing: tạo giá trị băm.
- Tokenization: thay bằng token và giữ mapping ở nơi được kiểm soát.
- Nulling: xóa giá trị.
- Partial masking: che một phần như số điện thoại hoặc email.

Chọn phương pháp dựa trên test requirement. Nếu cần join giữa nhiều bảng theo customer ID, hash/token phải nhất quán giữa các bảng. Nếu mỗi bảng randomize độc lập, referential integrity sẽ bị phá vỡ.

### 11.3 Anonymization và kiểm tra re-identification

Anonymization cần xem xét tổ hợp các trường, không chỉ một cột. Ví dụ ngày sinh, mã bưu chính và giới tính có thể kết hợp để nhận diện một người trong tập dữ liệu nhỏ.

Quy trình nên gồm:
1. Phân loại dữ liệu và trường nhạy cảm.
2. Xác định mục đích test và mức độ chi tiết tối thiểu cần giữ.
3. Mask hoặc tổng hợp các trường.
4. Kiểm tra các khóa liên kết và quasi-identifiers.
5. Đánh giá khả năng tái nhận diện.
6. Ghi lại phương pháp và phiên bản dataset.
7. Chỉ chuyển dataset đã được phê duyệt sang sandbox.

## 12. AWS Glue DataBrew và AWS DMS cho dữ liệu thử

### 12.1 AWS Glue DataBrew

AWS Glue DataBrew hỗ trợ profile dữ liệu và các transform để phát hiện/xử lý PII. Các kỹ thuật masking có thể gồm substitution, shuffling, deterministic/probabilistic encryption, nulling, masking và hashing.

DataBrew phù hợp khi cần chuẩn bị dataset phân tích hoặc dataset test từ file/table. Cần xác minh loại nguồn, destination, transform và khả năng xử lý schema trước khi xây dựng pipeline.

### 12.2 AWS Database Migration Service (DMS)

AWS DMS hỗ trợ transformation rule để mask một số trường khi tải dữ liệu sang target. Tài liệu DMS hiện hành mô tả các hành động data masking gồm:
- Digits Mask.
- Digits Randomize.
- Hashing Mask.

Các rule này có phạm vi và giới hạn cụ thể; chúng không phải một công cụ anonymization tổng quát cho mọi loại dữ liệu. Data masking được giới thiệu từ AWS DMS replication engine 3.5.4. Hãy kiểm tra phiên bản replication engine, loại source/target và column rule trước khi dựa vào DMS để chuẩn bị test data.

### 12.3 Không dùng masking như một lời đảm bảo tuân thủ

Việc sử dụng DataBrew hoặc DMS không tự động chứng minh dữ liệu đã anonymized. Tổ chức vẫn phải xác định trường nào cần bảo vệ, kiểm tra output và đánh giá nguy cơ tái nhận diện. Nếu dữ liệu vẫn có thể liên kết với cá nhân, môi trường sandbox có thể vẫn phải tuân theo yêu cầu bảo vệ dữ liệu tương tự nguồn.

## 13. Clone database production có an toàn không?

Amazon Aurora hỗ trợ clone cluster bằng copy-on-write. Clone ban đầu chia sẻ data pages với source và chỉ cấp thêm storage khi source hoặc clone thay đổi dữ liệu. Điều này giúp tạo môi trường thử nhanh và tiết kiệm hơn so với restore snapshot đầy đủ trong nhiều trường hợp.

Tuy nhiên, clone Aurora không phải masking. Clone ban đầu chứa dữ liệu từ source. Nếu source có PII, payment data hoặc secret, clone cũng có dữ liệu đó cho đến khi được xử lý.

Quy trình an toàn hơn:
1. Tạo clone trong account/environment được phê duyệt.
2. Hạn chế quyền truy cập ngay từ lúc tạo.
3. Chạy masking/anonymization script đã kiểm thử.
4. Xác minh dữ liệu nhạy cảm đã được xử lý.
5. Thay credential và secret bằng bản non-production.
6. Kiểm tra network access và logging.
7. Chỉ sau đó mới mở quyền cho tester/developer.

Nếu cần dữ liệu chỉ để kiểm thử schema hoặc query, hãy ưu tiên synthetic data. Nếu cần tính thực tế của production distribution, clone rồi mask chỉ nên thực hiện khi có phê duyệt dữ liệu và kiểm soát truy cập tương ứng.

## 14. Quản lý secrets và cấu hình theo môi trường

Mỗi môi trường cần có secrets riêng:
- Database username/password.
- API keys.
- OAuth client secret.
- Third-party credentials.
- Signing key.
- Encryption key.
- Webhook secret.

Dùng AWS Secrets Manager hoặc Systems Manager Parameter Store để lưu cấu hình phù hợp. Mỗi account/environment nên có secret path và quyền truy cập riêng.

Ví dụ quy ước:
- /app/dev/database/credentials
- /app/test/database/credentials
- /app/staging/database/credentials
- /app/prod/database/credentials

Không copy secret production sang sandbox. Không đặt secret trong:
- Git repository.
- Docker image.
- CloudFormation parameter dạng plaintext.
- User data hoặc log.
- File cấu hình được commit.
- CI/CD output.

Dùng IAM role và workload identity để lấy secret runtime. Giới hạn secretsmanager:GetSecretValue theo secret ARN và KMS key tương ứng. Bật rotation khi service và quy trình ứng dụng hỗ trợ.

## 15. Chuẩn hóa môi trường bằng Infrastructure as Code

Sandbox nên được tạo từ template để có thể tái tạo và xóa có kiểm soát. Các công cụ thường dùng:
- AWS CloudFormation.
- AWS Cloud Development Kit (CDK).
- Terraform.
- AWS SAM cho serverless application.
- AWS Copilot hoặc các công cụ deployment phù hợp workload.

Một template tốt cần tham số hóa:
- Environment name.
- Project ID.
- VPC CIDR.
- Instance size.
- Database class.
- Data retention.
- KMS key.
- Owner và expiry date.
- Allowed Region.
- Feature flag.

Không nên tạo môi trường bằng thao tác console rời rạc mà không ghi lại cấu hình. Nếu không có IaC, việc tái tạo lỗi hoặc xóa sạch môi trường rất khó kiểm soát.

Ví dụ CloudFormation template rút gọn:

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: Temporary sandbox resource example

Parameters:
  ProjectName:
    Type: String
    Default: device-lab
  Environment:
    Type: String
    Default: sandbox
  Owner:
    Type: String
  ExpiresAt:
    Type: String
    Description: ISO date, for example 2026-12-01
  BucketName:
    Type: String
    Description: Globally unique bucket name

Resources:
  TestBucket:
    Type: AWS::S3::Bucket
    Properties:
      BucketName: !Ref BucketName
      Tags:
        - Key: Project
          Value: !Ref ProjectName
        - Key: Environment
          Value: !Ref Environment
        - Key: Owner
          Value: !Ref Owner
        - Key: ExpiresAt
          Value: !Ref ExpiresAt

Outputs:
  BucketName:
    Value: !Ref TestBucket
~~~

Ví dụ chỉ tạo một bucket để minh họa parameter và tag. Trong production template cần xử lý naming, encryption, public access block, versioning, lifecycle và bucket policy.

### 15.1 Drift và tính nhất quán

Nếu người dùng sửa tài nguyên trực tiếp trong console, môi trường có thể khác template. Hãy:
- Dùng pipeline deploy từ source control.
- Hạn chế quyền sửa trực tiếp tài nguyên quan trọng.
- Kiểm tra CloudFormation drift hoặc Terraform plan.
- Review change set trước khi áp dụng.
- Version hóa template và test fixture.
- Ghi lại khác biệt được phê duyệt.

## 16. Kiểm thử gì ở sandbox và môi trường nào?

Không phải mọi loại test đều cần sandbox account. Chọn môi trường dựa trên phạm vi và rủi ro.

| Loại test | Môi trường phù hợp | Lưu ý |
|---|---|---|
| Unit test | Local/CI | Mock external service khi phù hợp |
| API contract test | Local/CI hoặc dev | Kiểm tra schema và backward compatibility |
| Integration test | Dev/test account | Dùng resource thật có phạm vi hẹp |
| IAM/SCP test | Dedicated sandbox/policy staging account | Tránh thử policy mới trên production OU |
| Data pipeline test | Data sandbox account | Chỉ dùng synthetic hoặc masked data |
| Migration rehearsal | Staging/test account | Snapshot, rollback và validation |
| Performance/load test | Staging có cấu hình đại diện | Không tạo tải production khi chưa được phép |
| Security test | Dedicated security test account | Có scope và authorization rõ ràng |
| Chaos/fault injection | Test/staging cô lập | Đặt stop condition và theo dõi blast radius |
| Release rehearsal | Staging | Cấu hình gần production nhất có thể |

Một sandbox nhỏ có thể xác minh chức năng nhưng không đại diện hiệu năng production. Nếu cần load test, hãy tạo staging đủ gần production về instance, network, database, dữ liệu và autoscaling; thống nhất giới hạn tải, thời gian chạy và chi phí trước khi thực hiện.

## 17. Budget và giới hạn chi phí

AWS Budgets theo dõi cost/usage và gửi thông báo khi actual hoặc forecast vượt ngưỡng. Có thể tạo budget theo account, service, Region hoặc project dimension phù hợp.

Ví dụ mức cảnh báo cho sandbox:
- 50% budget: thông báo owner.
- 80% budget: thông báo owner và platform team.
- 100% budget: review resource và dừng thử nghiệm nếu cần.
- Forecast vượt ngưỡng: kiểm tra sớm trước khi tiếp tục.

AWS Budgets hỗ trợ budget actions. Tùy cấu hình, action có thể áp dụng IAM policy hoặc SCP, hoặc target một số EC2/RDS resource trong account; action có thể tự động chạy hoặc chờ phê duyệt.

Budget không phải hard spending cap. AWS Budgets cập nhật dữ liệu billing tối đa vài lần mỗi ngày; cập nhật thường cách nhau khoảng 8–12 giờ và cảnh báo có thể đến sau khi tài nguyên đã phát sinh thêm chi phí. Vì vậy, kết hợp budget với:
- SCP/permission guardrail.
- Giới hạn instance type và Region.
- Quota và service access.
- Scheduled stop cho tài nguyên phù hợp.
- Cleanup tự động.
- Dashboard và cost anomaly alert.

### 17.1 Service Quotas

Nhiều service quota được quản lý theo account và Region. Tách workload sang account riêng có thể giúp tránh một workload chiếm quota của workload khác. Tuy nhiên, không phải mọi quota đều giống nhau hoặc hoàn toàn độc lập; hãy kiểm tra Service Quotas của từng service và Region.

Trong sandbox:
- Không request tăng quota lớn nếu chưa có owner.
- Đặt giới hạn instance type, số instance và database class.
- Theo dõi VPC, ENI, Elastic IP, NAT Gateway và load balancer.
- Kiểm tra quota trước test quy mô lớn.
- Xóa resource khi kết thúc để giải phóng quota.

## 18. Tagging và nhận diện tài nguyên tạm

Dùng tag nhất quán để biết ai tạo tài nguyên, thuộc môi trường nào và khi nào hết hạn.

Tag gợi ý:

| Tag | Ví dụ | Mục đích |
|---|---|---|
| Project | iot-shadow-lab | Nhóm theo project |
| Environment | sandbox | Nhận diện môi trường |
| Owner | team-platform | Người/team chịu trách nhiệm |
| CostCenter | CC-042 | Phân bổ chi phí |
| ExpiresAt | 2026-12-01 | Hạn sử dụng |
| DataClass | synthetic | Phân loại dữ liệu |
| ManagedBy | cloudformation | Xác định công cụ quản lý |

AWS Organizations Tag Policies giúp chuẩn hóa key/case/value trên các resource type được hỗ trợ. Nhưng tag policy không phát hiện mọi resource chưa được gắn tag; resource không có tag không tự động xuất hiện như một tài nguyên noncompliant trong một số báo cáo tag policy. Hãy kết hợp IaC validation, AWS Config, Resource Explorer hoặc Resource Groups Tagging API để tìm tài nguyên thiếu tag.

Không dùng tag như ranh giới bảo mật duy nhất. Tag hữu ích cho cost allocation, automation và ABAC, nhưng cần IAM policy, resource policy và account boundary để bảo vệ tài nguyên.

## 19. Tự động hóa vòng đời sandbox

Một sandbox nên có thời hạn và quy trình gia hạn rõ ràng.

Vòng đời tham khảo:

~~~text
Request
   |
   v
Approve owner / budget / data class
   |
   v
Provision account and baseline
   |
   v
Deploy IaC stack and test data
   |
   v
Run experiment / test
   |
   v
Review result and request extension?
   |                    |
   | No                 | Yes
   v                    v
Cleanup resources     Extend expiry
   |
   v
Verify no orphan resources
   |
   v
Archive evidence and close sandbox
~~~

Có thể triển khai bằng:
- Account Factory để tạo account.
- Service Catalog hoặc pipeline để cấp phát template.
- EventBridge Scheduler hoặc EventBridge rule để kích hoạt workflow theo lịch.
- Lambda hoặc Step Functions để kiểm tra ExpiresAt và owner.
- CloudFormation/Terraform để xóa stack.
- AWS Budgets để cảnh báo.
- AWS Config/Resource Explorer để rà soát tài nguyên còn sót.

Automation cần có safety check. Không xóa chỉ vì một tag hết hạn nếu tài nguyên đang được bảo vệ, có legal hold hoặc được đánh dấu retain. Nên yêu cầu owner xác nhận trước cleanup đối với resource có dữ liệu quan trọng.

### 19.1 Cleanup CloudFormation stack

CloudFormation có thể xóa các resource thuộc stack khi xóa stack. Tuy nhiên:
- Resource có DeletionPolicy: Retain có thể được giữ lại.
- S3 bucket thường phải được làm rỗng trước khi xóa.
- Resource ngoài stack hoặc resource được retain có thể trở thành orphan.
- Xóa stack không thể dừng sau khi operation đã bắt đầu.
- Cần kiểm tra DELETE_COMPLETE và danh sách resource sau cleanup.

Ví dụ resource dữ liệu cần giữ lại:

~~~yaml
Resources:
  TestArchiveBucket:
    Type: AWS::S3::Bucket
    DeletionPolicy: Retain
    UpdateReplacePolicy: Retain
    Properties:
      VersioningConfiguration:
        Status: Enabled
~~~

Ví dụ này cố ý giữ bucket và dữ liệu khi stack bị xóa. Nếu sandbox cần cleanup hoàn toàn, không áp dụng Retain tùy tiện. Hãy phân loại resource ephemeral và persistent trước khi tạo template.

### 19.2 Danh sách tài nguyên cần kiểm tra sau cleanup

- EC2 instance và Auto Scaling group.
- EBS volume và snapshot.
- Elastic IP và NAT Gateway.
- Load balancer và target group.
- RDS/Aurora instance, cluster và snapshot.
- S3 bucket, object và multipart upload.
- CloudWatch log group và log stream.
- ECR image và repository.
- Lambda function, event source mapping và layer.
- VPC endpoint, security group và ENI.
- Secrets Manager secret và Parameter Store parameter.
- KMS key và scheduled deletion.
- Route 53 record, hosted zone và certificate.
- CloudFormation stack, nested stack và StackSet instance.

Một số tài nguyên cần xóa theo thứ tự phụ thuộc. Nếu cleanup thất bại, đọc event/error của service, xử lý dependency rồi retry. Không force delete một cách máy móc vì có thể giữ lại tài nguyên hoặc dữ liệu không được kiểm soát.

## 20. Logging, audit và security monitoring

Một sandbox vẫn cần audit để điều tra hành động và chi phí.

Các dịch vụ có thể dùng:
- **AWS CloudTrail:** ghi nhận API activity và principal thực hiện.
- **AWS Config:** ghi nhận cấu hình resource và đánh giá rule.
- **Amazon GuardDuty:** phát hiện hành vi đáng ngờ.
- **AWS Security Hub:** tổng hợp security findings.
- **CloudWatch Logs/Metrics:** quan sát ứng dụng và service.
- **Amazon S3 log archive:** lưu log tập trung theo retention.

Không tắt logging để giảm chi phí sandbox nếu tổ chức yêu cầu audit. Nếu sandbox được phép tắt một số integration, phải dùng baseline rõ ràng và phê duyệt trước.

Cần phân biệt log test với log audit. Log ứng dụng có thể chứa token, email, payload hoặc PII; hãy kiểm soát log level, redaction và retention.

## 21. Kiến trúc tham khảo: sandbox account cho ứng dụng AWS

Một nhóm phát triển ứng dụng IoT cần thử Lambda, API Gateway, DynamoDB và S3. Kiến trúc gợi ý:

~~~text
AWS Organization
|
+-- Security OU
|   +-- Log Archive
|   +-- Audit
|
+-- Sandbox OU
    +-- Sandbox-IoT account
         |
         +-- IAM Identity Center assignment
         |     +-- DeveloperSandbox permission set
         |
         +-- SCP guardrails
         |     +-- Protect audit configuration
         |     +-- Restrict selected Regions
         |
         +-- Sandbox VPC
         |     +-- Private subnets
         |     +-- VPC endpoints
         |
         +-- Application stack
         |     +-- API Gateway
         |     +-- Lambda
         |     +-- DynamoDB
         |     +-- S3 test bucket
         |
         +-- Test data
         |     +-- Synthetic dataset
         |     +-- Versioned fixtures
         |
         +-- Cost and lifecycle
               +-- AWS Budget
               +-- Owner / ExpiresAt tags
               +-- Cleanup workflow
~~~

Luồng làm việc:
1. Developer yêu cầu account và khai báo mục tiêu thử.
2. Platform team cấp account vào Sandbox OU.
3. IAM Identity Center cấp permission set.
4. Baseline tạo logging, network và guardrail.
5. CI/CD deploy stack từ template.
6. Pipeline nạp synthetic test data.
7. Developer chạy integration test.
8. Dashboard theo dõi cost và error.
9. Hết hạn, workflow cleanup stack và xác minh tài nguyên.
10. Kết quả test và evidence được lưu theo retention.

## 22. Quy trình kiểm thử an toàn từ đầu đến cuối

### Trước khi thử

1. Xác định mục tiêu, phạm vi và loại test.
2. Chọn account/OU phù hợp.
3. Xác nhận owner và budget.
4. Xác nhận Region/service được phép.
5. Kiểm tra dữ liệu synthetic hoặc masked.
6. Kiểm tra quyền IAM và SCP.
7. Xác nhận VPC, route và security group.
8. Xác nhận secret và KMS key non-production.
9. Deploy bằng IaC.
10. Ghi lại trạng thái baseline.

### Trong khi thử

1. Theo dõi cost, quota và service health.
2. Ghi lại version template, image và dataset.
3. Không đưa production credential vào sandbox.
4. Không mở kết nối production ngoài scope đã duyệt.
5. Theo dõi CloudTrail và CloudWatch logs.
6. Dừng thử nghiệm nếu vượt stop condition hoặc phát hiện dữ liệu nhạy cảm.
7. Ghi nhận lỗi và bước tái hiện.

### Sau khi thử

1. Lưu kết quả và evidence cần thiết.
2. Xóa tài nguyên ephemeral.
3. Kiểm tra retained resources và orphan.
4. Kiểm tra S3 object, snapshot, log group và EIP.
5. Xác nhận secret và credential tạm đã bị thu hồi.
6. Xác nhận budget/cost không tiếp tục tăng bất thường.
7. Gia hạn hoặc đóng sandbox account.
8. Cập nhật template nếu có bài học mới.

## 23. Sự cố thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Developer không vào được account | Chưa gán group/permission set hoặc provisioning chưa xong | Kiểm tra IAM Identity Center assignment và account provisioning status |
| Tạo resource bị AccessDenied | IAM policy hoặc SCP không cho phép | Xác định policy layer gây deny, dùng CloudTrail và policy simulator phù hợp |
| Service không dùng được ở Region | SCP Region guardrail hoặc service chưa hỗ trợ | Kiểm tra requested Region và exception cần thiết |
| Sandbox truy cập được production bucket | Resource policy/trust policy quá rộng | Thu hẹp principal, bucket prefix, KMS key và cross-account role |
| Test data có PII | Dataset chưa được mask hoặc profile chưa đủ | Dừng chia sẻ, cô lập dataset, xử lý lại và kiểm tra output |
| Database clone chứa dữ liệu thật | Clone không tự mask dữ liệu | Hạn chế truy cập, chạy masking/anonymization trước khi mở quyền |
| Budget alert đến muộn | Billing data refresh có độ trễ | Dùng quota, SCP, schedule stop và cleanup làm guardrail bổ sung |
| Chi phí tăng sau khi xóa stack | Resource được retain hoặc không thuộc stack | Kiểm tra stack resources, orphan resource và billing dimensions |
| Stack deletion thất bại | Bucket còn object hoặc resource dependency | Đọc stack events, xử lý dependency và retry |
| Resource không có tag | Console/manual create hoặc service không hỗ trợ tag lúc tạo | Dùng IaC validation, Config/Resource Explorer và remediation |
| Quota bị cạn | Sandbox dùng chung account với workload khác | Tách account hoặc quản lý quota theo project/Region |
| Test load không giống production | Instance/data/network nhỏ hơn hoặc khác cấu hình | Dùng staging có cấu hình đại diện và dữ liệu synthetic đủ thực tế |

Khi điều tra, xác định account, Region, principal, resource ARN và request ID trước. Không giải quyết AccessDenied bằng cách cấp AdministratorAccess rộng mà chưa tìm nguyên nhân.

## 24. Checklist thiết kế sandbox production-ready

- [ ] Đã xác định mục tiêu và owner của sandbox.
- [ ] Sandbox nằm trong AWS Organizations và OU phù hợp.
- [ ] Production được tách account theo yêu cầu cô lập.
- [ ] Account được cấp phát bằng quy trình chuẩn hoặc Account Factory.
- [ ] Có baseline logging, Config và security controls.
- [ ] Developer truy cập qua IAM Identity Center.
- [ ] Có MFA và temporary credentials.
- [ ] Không chia sẻ root credentials hoặc access key.
- [ ] SCP đã được thử trong account/OU staging.
- [ ] Hiểu SCP không cấp quyền và không áp dụng cho management account/service-linked roles.
- [ ] VPC CIDR không overlap với network cần kết nối.
- [ ] Không có route mặc định từ sandbox sang production.
- [ ] Security group chỉ mở traffic cần thiết.
- [ ] Secrets, database và KMS key tách theo môi trường.
- [ ] Dataset synthetic được ưu tiên.
- [ ] Dữ liệu production-like đã được mask/anonymize và kiểm tra.
- [ ] Không coi Aurora clone là dữ liệu đã được mask.
- [ ] Có schema và version cho test fixtures.
- [ ] Template IaC có thể tái tạo môi trường.
- [ ] Có drift detection hoặc review thay đổi.
- [ ] Có budget alert và owner nhận thông báo.
- [ ] Có guardrail bổ sung vì budget không phải hard cap.
- [ ] Resource có tag Project, Environment, Owner và ExpiresAt.
- [ ] Có quy trình cleanup và kiểm tra orphan resources.
- [ ] Có retention cho log, snapshot và test data.
- [ ] Có audit trail cho account access và API activity.
- [ ] Có runbook khi sandbox hết hạn hoặc phát hiện dữ liệu nhạy cảm.

## 25. Bài tập thực hành

### Bài 1: Chọn ranh giới môi trường

Một công ty có một ứng dụng production và ba team phát triển độc lập. Mỗi team cần quyền tạo Lambda, RDS và VPC để thử nghiệm.

Yêu cầu: đề xuất account/OU structure.

Đáp án gợi ý: production workload ở Production OU/account riêng; mỗi team có sandbox account riêng hoặc account sandbox được cô lập theo workload và quyền; dùng IAM Identity Center để gán quyền; áp dụng SCP và budget theo OU/account.

### Bài 2: Đánh giá SCP

Developer có IAM policy cho phép tạo EC2 nhưng lệnh CreateInstances bị AccessDenied. SCP ở Sandbox OU có explicit Deny cho EC2.

Yêu cầu: giải thích kết quả.

Đáp án: SCP giới hạn quyền tối đa. IAM Allow không vượt qua explicit Deny trong SCP. Cần xem CloudTrail và policy áp dụng; không cấp thêm IAM Allow để cố vượt SCP.

### Bài 3: Phát hiện lộ dữ liệu

Một developer restore production database snapshot vào sandbox để kiểm tra query.

Yêu cầu: nêu các bước trước khi mở quyền cho team.

Đáp án: cô lập database, kiểm tra data classification, chạy masking/anonymization, xác minh PII, thay credentials, kiểm tra KMS/network/policy và phê duyệt dataset trước khi cấp quyền.

### Bài 4: Chọn dữ liệu test

Một test chỉ cần xác minh order workflow và quan hệ giữa customer, order, payment.

Yêu cầu: chọn loại dữ liệu và điều kiện cần giữ.

Đáp án: synthetic data là lựa chọn đầu tiên; giữ foreign key, trạng thái order/payment, phân phối giá trị và các edge case cần test.

### Bài 5: Masking quan hệ

Customer ID xuất hiện trong Customers, Orders và Payments. Nếu randomize độc lập từng bảng, kết quả có thể ra sao?

Đáp án: foreign key không còn khớp. Dùng mapping/tokenization hoặc deterministic transformation nhất quán cho cùng một ID ở mọi bảng.

### Bài 6: Budget vượt ngưỡng

AWS Budgets cảnh báo sandbox đã đạt 100% budget nhưng EC2 vẫn chạy.

Yêu cầu: giải thích vì sao và đề xuất biện pháp.

Đáp án: budget alert có độ trễ và không tự động là hard cap. Dùng budget actions có phê duyệt phù hợp, SCP/IAM guardrail, scheduled stop và cleanup workflow.

### Bài 7: Cleanup thất bại

CloudFormation stack ở DELETE_FAILED vì S3 bucket còn object.

Yêu cầu: xử lý thế nào?

Đáp án: kiểm tra stack event, xác định object cần giữ/xóa, làm rỗng bucket theo retention policy rồi retry. Nếu dùng Retain, phải ghi nhận resource được giữ và có owner tiếp quản.

### Bài 8: Tag policy

Resource mới không có tag Owner nhưng báo cáo tag policy không liệt kê nó là noncompliant.

Yêu cầu: giải thích và cách phát hiện.

Đáp án: tag policy không đánh giá resource hoàn toàn không có tag trong một số báo cáo. Dùng IaC validation, AWS Config hoặc Resource Explorer query `tag:none` để tìm resource thiếu tag.

### Bài 9: Aurora clone

Một Aurora clone được tạo để test schema. Nhóm cho rằng clone đã tách khỏi production nên có thể cho developer truy cập trực tiếp.

Đáp án: clone có volume độc lập nhưng dữ liệu ban đầu vẫn là dữ liệu nguồn theo cơ chế copy-on-write. Phải mask/anonymize và thay secrets trước khi mở quyền.

### Bài 10: Chọn môi trường load test

Nhóm muốn thử tải bằng sandbox instance nhỏ hơn production 10 lần.

Đáp án: sandbox có thể kiểm tra logic tải ở mức giới hạn nhưng không đủ đại diện cho production performance. Dùng staging có cấu hình và dữ liệu gần production, giới hạn tải và có phê duyệt.

## 26. Câu hỏi tự kiểm tra

1. Sandbox là gì và dùng trong trường hợp nào?
2. AWS account cung cấp những ranh giới cô lập nào?
3. Vì sao production nên tách khỏi dev/test?
4. OU dùng để làm gì trong AWS Organizations?
5. AWS Control Tower Account Factory giúp ích gì?
6. IAM Identity Center khác IAM user dài hạn ở điểm nào?
7. SCP có cấp quyền cho principal không?
8. SCP có áp dụng cho management account không?
9. Vì sao SCP cần được thử trước khi gắn vào OU lớn?
10. Account boundary có tự động ngăn cross-account access không?
11. VPC isolation bổ sung lớp bảo vệ nào?
12. Vì sao CIDR overlap gây khó khăn?
13. Synthetic data khác masked data như thế nào?
14. Vì sao đổi tên cột không đủ để anonymize?
15. AWS Glue DataBrew có thể hỗ trợ xử lý PII ra sao?
16. AWS DMS data masking hỗ trợ những kiểu transformation nào?
17. Vì sao Aurora clone không đồng nghĩa với masked dataset?
18. Vì sao mỗi môi trường cần secrets và KMS policy riêng?
19. IaC giúp sandbox có vòng đời như thế nào?
20. AWS Budgets có phải hard spending cap không?
21. Vì sao cần kết hợp budget với SCP/quota/cleanup?
22. Tag policy có phát hiện mọi resource không có tag không?
23. Những tài nguyên nào thường bị bỏ sót khi cleanup?
24. Vì sao staging phù hợp hơn sandbox nhỏ cho load test?
25. Cần lưu evidence nào sau một đợt test?

Gợi ý trả lời:

1. Môi trường thử nghiệm có phạm vi quyền, dữ liệu, chi phí và thời hạn.
2. Tài nguyên, quyền truy cập, billing và nhiều service quota.
3. Giảm blast radius và ngăn thao tác test tác động workload thật.
4. Nhóm account theo policy và control chung.
5. Chuẩn hóa và tự động hóa việc tạo/cập nhật account trong landing zone.
6. Identity Center dùng federation và temporary role credentials.
7. Không; SCP chỉ giới hạn quyền tối đa.
8. Không; SCP không giới hạn management account.
9. Deny có thể chặn pipeline, logging hoặc vận hành.
10. Không; cross-account trust và resource policy vẫn có thể cho phép.
11. Route, subnet, security group, egress và endpoint.
12. Route giữa các VPC sẽ mơ hồ hoặc không thể định tuyến đúng.
13. Synthetic được tạo mới; masked biến đổi dữ liệu có nguồn gốc.
14. Các trường khác có thể kết hợp để tái nhận diện.
15. Profile và áp dụng transform để redaction/masking PII.
16. Digits mask, digits randomize và hashing mask.
17. Clone ban đầu vẫn chứa data pages của source.
18. Tránh credential/key dùng chung và giới hạn quyền theo environment.
19. Tạo lại nhất quán, review drift và xóa theo stack.
20. Không; cảnh báo có độ trễ và không tự chặn mọi resource.
21. Để giảm rủi ro chi phí trước khi billing alert cập nhật.
22. Không; resource không có tag có thể không được đánh giá trong báo cáo.
23. EBS/snapshot, EIP, NAT, log group, bucket, secret, KMS key và resource ngoài stack.
24. Vì cấu hình có thể đại diện hơn cho production.
25. Test scope, dataset version, IaC version, log, kết quả, chi phí và cleanup evidence.

## 27. Tài liệu tham khảo chính thức

- [AWS multi-account strategy for an AWS Control Tower landing zone](https://docs.aws.amazon.com/controltower/latest/userguide/aws-multi-account-landing-zone.html)
- [AWS Well-Architected: Separate workloads using accounts](https://docs.aws.amazon.com/wellarchitected/latest/framework/sec_securely_operate_multi_accounts.html)
- [AWS Organizations best practices](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_best-practices.html)
- [Provision accounts with AWS Control Tower](https://docs.aws.amazon.com/controltower/latest/userguide/methods-of-provisioning.html)
- [AWS Organizations Service Control Policies](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_scps.html)
- [IAM Identity Center account access](https://docs.aws.amazon.com/singlesignon/latest/userguide/manage-your-accounts.html)
- [AWS Well-Architected: Experimental and temporary environments](https://docs.aws.amazon.com/wellarchitected/latest/framework/fnd01-bp04.html)
- [AWS Glue DataBrew: Identifying and handling PII](https://docs.aws.amazon.com/databrew/latest/dg/personal-information-protection.html)
- [AWS DMS: Data masking](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_Tasks.CustomizingTasks.TableMapping.SelectionTransformation.Masking.html)
- [Amazon Aurora cloning](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.Managing.Clone.html)
- [AWS Budgets: Managing costs](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html)
- [AWS Budgets: Configuring budget actions](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-controls.html)
- [AWS Organizations tag policies](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_tag-policies.html)
- [CloudFormation: Delete a stack](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/cfn-console-delete-stack.html)
- [CloudFormation: Managing stacks](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacks.html)
- [AWS Prescriptive Guidance: Automate deletion of CloudFormation stacks](https://docs.aws.amazon.com/prescriptive-guidance/latest/patterns/automate-deletion-cloudformation-stacks-associated-resources.html)

Các khả năng Account Factory, Control Tower controls, SCP, quota, masking và service integration có thể thay đổi theo Region, landing zone version và service version. Trước khi áp dụng cho tổ chức, hãy thử trên account/OU riêng, kiểm tra quyền và tác động của policy, xác minh dataset đầu ra, rồi mới mở rộng sang các workload khác.
