# CloudFormation StackSets cho nhiều tài khoản và Region

> **Chương:** Hạ tầng dưới dạng mã  
> **Module:** CLOUD_PROVIDERS_AWS — khám phá hệ sinh thái AWS qua hạ tầng Region/AZ, IAM, VPC, dịch vụ tính toán, lưu trữ, cơ sở dữ liệu, tích hợp và serverless. Người học rèn khả năng chọn dịch vụ, thiết kế và triển khai ứng dụng an toàn, có khả năng giám sát, phục hồi và kiểm soát chi phí.

## Mục tiêu học tập

AWS CloudFormation StackSets mở rộng mô hình Infrastructure as Code (IaC) từ một stack trong một account/Region thành triển khai có điều phối trên nhiều AWS accounts và Regions. Một StackSet giữ template và cấu hình triển khai; mỗi account/Region mục tiêu có một **stack instance** tương ứng.

Bài học xây dựng baseline cho một AWS Organization, triển khai vào nhiều Organizational Units (OU) và Regions, sau đó theo dõi operation, phát hiện drift và xử lý lỗi có kiểm soát. Nội dung tập trung vào hai permission models: service-managed và self-managed.

Sau bài học, bạn có thể:

1. Phân biệt Stack, StackSet, stack instance và StackSet operation.
2. Chọn service-managed hoặc self-managed permissions theo mô hình quản trị.
3. Giải thích AWS Organizations trusted access và delegated administrator.
4. Chọn account/OU targets, account filters và Regions.
5. Thiết kế template có parameters, pseudo parameters và region-specific values.
6. Tạo StackSet và stack instances bằng AWS CLI.
7. Cấu hình Region concurrency, failure tolerance và concurrency mode.
8. Thiết kế auto-deployment khi account gia nhập/rời OU.
9. Phát hiện drift và hiểu giới hạn của drift detection.
10. Triển khai rollout theo waves, xử lý partial failure và kiểm soát rollback.
11. Bảo vệ quyền quản trị, execution roles, SCPs, KMS và audit.
12. Vận hành StackSets với metrics, operation history và runbook.

## 1. StackSets giải quyết bài toán nào?

### 1.1. Từ một stack đến nhiều accounts và Regions

Một CloudFormation stack triển khai resources trong một account và Region cụ thể. Nếu tổ chức có hàng chục accounts, mỗi account chạy ở nhiều Regions, việc copy template và triển khai thủ công tạo ra drift cấu hình, thiếu audit và chi phí vận hành cao.

StackSets cho phép quản trị một template từ một nơi rồi tạo/cập nhật/xóa stacks ở nhiều account/Region theo một operation.

~~~mermaid
flowchart TD
    ADMIN[CloudFormation StackSet]
    ADMIN --> A1[Account A]
    ADMIN --> A2[Account B]
    ADMIN --> A3[Account C]
    A1 --> R11[ap-southeast-1 stack]
    A1 --> R12[ap-southeast-2 stack]
    A2 --> R21[ap-southeast-1 stack]
    A2 --> R22[ap-southeast-2 stack]
    A3 --> R31[ap-southeast-1 stack]
    A3 --> R32[ap-southeast-2 stack]
~~~

Ví dụ, một security baseline cần tạo cùng một CloudWatch log group, AWS Config rule hoặc IAM role ở mọi workload account. StackSets giúp định nghĩa template một lần, sau đó triển khai theo OU và Region.

### 1.2. Bốn khái niệm cần phân biệt

| Khái niệm | Ý nghĩa |
|---|---|
| Stack | Tập hợp resources được CloudFormation quản lý trong một account/Region |
| StackSet | Định nghĩa trung tâm gồm template, parameters, permissions và cấu hình deployment |
| Stack instance | Một stack được StackSet quản lý tại một account/Region cụ thể |
| StackSet operation | Một lần create/update/delete/drift detection/import triển khai lên tập stack instances |

Một StackSet có thể quản lý nhiều stack instances. Stack instance được xác định bởi account và Region; cùng một account có thể có một instance ở Singapore và một instance khác ở Sydney.

### 1.3. Ma trận triển khai

Giả sử tổ chức có 3 accounts và 2 Regions:

| Account | ap-southeast-1 | ap-southeast-2 |
|---|---|---|
| Shared Services | Stack instance | Stack instance |
| Development | Stack instance | Stack instance |
| Production | Stack instance | Stack instance |

Một operation có thể triển khai đến toàn bộ ma trận hoặc một tập con. Cần xác định rõ target set để tránh vô tình áp dụng thay đổi vào production.

### 1.4. Khi nào nên dùng StackSets?

StackSets phù hợp với cấu hình nền tảng cần đồng nhất:

- IAM roles/policies dùng chung;
- AWS Config rules và conformance baseline;
- CloudWatch log groups, alarms hoặc account-level settings;
- GuardDuty/Security Hub/CloudTrail configuration;
- VPC endpoints hoặc network baseline theo account;
- SSM parameters, deployment agents và tagging baseline.

StackSets không thay thế mọi deployment pipeline. Ứng dụng có release cadence riêng, phụ thuộc phức tạp hoặc cần approval theo từng workload có thể phù hợp hơn với pipeline chuyên dụng, trong khi StackSets quản lý account baseline.

## 2. StackSet permissions: service-managed và self-managed

### 2.1. Hai permission models

| Tiêu chí | Service-managed | Self-managed |
|---|---|---|
| Phạm vi target | Accounts thuộc AWS Organizations; có thể target organization/OU | Account IDs được chỉ định |
| Role provisioning | CloudFormation/Organizations quản lý service-linked roles | Tổ chức tự tạo và quản lý IAM roles |
| Organizations | Bắt buộc cho mô hình này | Không bắt buộc |
| Onboarding accounts | Có thể tự động deploy vào accounts mới trong target OU | Phải cập nhật targets/deployment |
| Delegated administrator | Hỗ trợ | Không dùng Organizations delegated admin theo mô hình này |
| Kiểm soát role | Theo service-linked role và Organizations | Trust/policy roles do tổ chức quản lý |
| Phù hợp | Enterprise multi-account governance | Cross-account deployments có role setup riêng hoặc không dùng Organizations |

Không có model nào luôn tốt hơn. Nếu tổ chức đã quản lý accounts qua AWS Organizations, service-managed thường giảm việc tạo và duy trì execution roles. Self-managed phù hợp khi cần target các account cụ thể không thuộc cùng Organization hoặc muốn tự kiểm soát role provisioning.

### 2.2. Service-managed permissions

Service-managed StackSets tích hợp AWS Organizations. Sau khi bật trusted access, CloudFormation có thể tạo và sử dụng service-linked roles cần thiết trong management account/member accounts.

Bạn không phải tự tạo administrator/execution role trong từng target account. CloudFormation điều phối role provisioning theo Organizations và permission model.

Các điều kiện và giới hạn quan trọng:

- Target accounts phải thuộc AWS Organization;
- StackSet có thể target toàn organization hoặc OU cụ thể;
- Không thể target accounts nằm ngoài Organization;
- Service-managed StackSets **không triển khai vào management account**;
- Service-managed StackSets không hỗ trợ nested stacks hoặc templates chứa macros/transforms;
- Quyền triển khai được khởi tạo từ management account hoặc delegated administrator đã đăng ký.

Nếu cần deploy vào management account, hãy đánh giá self-managed permissions và quy trình quản trị riêng cho account đó.

### 2.3. Self-managed permissions

Với self-managed StackSets, tổ chức phải chuẩn bị IAM roles:

1. **Administration role** trong account điều khiển StackSet;
2. **Execution role** trong mỗi target account;
3. Trust policy cho phép administration role assume execution role;
4. Permission policy cho execution role tạo/cập nhật resources mà template yêu cầu.

Mô hình:

~~~mermaid
flowchart LR
    OP[Operator / CI role]
    OP --> ADMIN[Administration role]
    ADMIN -->|AssumeRole| E1[Execution role - Account A]
    ADMIN -->|AssumeRole| E2[Execution role - Account B]
    E1 --> CFN1[CloudFormation resources]
    E2 --> CFN2[CloudFormation resources]
~~~

Tên role có thể tùy chỉnh nhưng phải khớp cấu hình StackSet. Tổ chức chịu trách nhiệm tạo, bảo vệ, rotate/update policies và xử lý trust relationships. Không copy một execution role AdministratorAccess vào tất cả accounts.

### 2.4. Chọn model theo tình huống

- Tất cả workload accounts thuộc một Organization và cần auto-deployment theo OU: ưu tiên đánh giá service-managed.
- Target account nằm ngoài Organization hoặc có yêu cầu cross-account role riêng: đánh giá self-managed.
- Muốn triển khai vào management account: cần kế hoạch riêng; service-managed không target management account.
- Muốn delegated platform team vận hành: service-managed delegated admin có thể phù hợp, nhưng phải đánh giá phạm vi quyền rộng của delegated administrator.

## 3. AWS Organizations trusted access và delegated administrator

### 3.1. Trusted access

Trusted access cho phép CloudFormation StackSets tích hợp với AWS Organizations để triển khai trên các accounts/OU. Đây là nền tảng của service-managed permission model.

Trước khi tạo StackSet service-managed:

- Organization phải được cấu hình trong AWS Organizations;
- Trusted access cho CloudFormation StackSets phải được kích hoạt;
- Operator cần quyền quản lý StackSets và target scope;
- Các target accounts phải ở trạng thái phù hợp để nhận triển khai;
- Các Regions cần dùng phải khả dụng trong target accounts.

Khi tắt trusted access, khả năng vận hành service-managed StackSets sẽ bị ảnh hưởng. Không thay đổi trusted access trong lúc đang có rollout nếu chưa đánh giá tác động.

### 3.2. Management account và delegated administrator

Management account sở hữu StackSet service-managed. Một member account có thể được đăng ký làm **delegated administrator** để vận hành StackSets mà không cần mọi thao tác hằng ngày thực hiện trực tiếp bằng management account.

Khi delegated administrator tạo StackSet, StackSet vẫn được tạo trong management account. Lệnh CLI chạy từ delegated admin cần chỉ rõ `--call-as DELEGATED_ADMIN`.

AWS cho phép tối đa **5 delegated administrator accounts** được đăng ký cho StackSets trong một Organization. Một delegated administrator có phạm vi quyền rộng: có thể triển khai tới bất kỳ account nào trong Organization; management account không thể giới hạn delegated admin chỉ vào một vài OUs hoặc loại StackSet operation bằng cơ chế delegated admin này.

Vì vậy:

- Chỉ đăng ký delegated admin cho account nền tảng được bảo vệ;
- Dùng IAM policies/SCPs và quy trình change approval phù hợp;
- Theo dõi CloudTrail cho thao tác StackSet;
- Không cấp quyền delegated admin cho workload teams nếu họ không cần quyền triển khai toàn Organization.

### 3.3. Deployment targets trong Organization

Service-managed StackSets có thể target:

- Toàn Organization;
- Một hoặc nhiều OUs;
- Các account cụ thể;
- Tập account được chọn bằng account filters kết hợp với OU/account targets.

Khi target parent OU, các child OUs và accounts bên dưới cũng được bao gồm. Hãy hiểu cấu trúc OU trước khi chọn parent OU, vì một target rộng có thể bao gồm nhiều workload hơn dự kiến.

### 3.4. Account filters

Khi kết hợp OU IDs và account IDs, `AccountFilterType` giúp lọc tập account:

| Filter type | Ý nghĩa |
|---|---|
| `NONE` | Không áp dụng account filtering |
| `INTERSECTION` | Chỉ chọn accounts vừa thuộc target OUs vừa có trong danh sách accounts |
| `DIFFERENCE` | Chọn accounts trong target OUs ngoại trừ danh sách accounts |
| `UNION` | Chọn accounts thuộc target OUs hoặc nằm trong danh sách accounts |

Ví dụ: target OU `ou-prod` nhưng loại trừ account đang migration bằng `DIFFERENCE`. Trước khi triển khai, kiểm tra tập account thực tế qua Organizations và StackSet target configuration; đừng suy ra target chỉ từ tên OU.

**Lưu ý với auto-deployment:** StackSets không áp dụng account-level targeting filters cho các account được thêm sau này. Nếu bật auto-deployment, StackSet có thể triển khai vào account mới trong Organization/OU dù cấu hình ban đầu có danh sách account filter. Nếu không muốn điều đó, hãy tắt auto-deployment hoặc tách StackSets/OU theo đúng lifecycle.

### 3.5. Account onboarding và offboarding

Nếu bật auto-deployment, account mới gia nhập target OU có thể tự động nhận stack instances. Khi account rời target OU, StackSet có thể xóa stack instance hoặc giữ stack tùy `RetainStacksOnAccountRemoval`.

Auto-deployment cũng được kích hoạt khi account được chuyển giữa các OUs. Ví dụ account rời OU Development để vào OU Production có thể bị xóa instance thuộc StackSet target Development và được tạo instance của StackSet target Production.

Quyết định retain phải theo ownership:

- Baseline do central platform sở hữu có thể cần được xóa khi account rời scope;
- Resources có dữ liệu/workload ownership có thể cần retain và chuyển giao;
- Xóa stack có thể xóa resources nếu template/resource policies cho phép.

Không chọn retain hoặc delete chỉ để tiện vận hành; cần xác định resource lifecycle và data retention.

## 4. Thiết kế template dùng chung cho nhiều accounts/Regions

### 4.1. Template là source of truth

StackSet dùng CloudFormation template. Template cần:

- Khai báo resources rõ ràng;
- Dùng Parameters cho khác biệt theo environment;
- Dùng pseudo parameters như `AWS::AccountId`, `AWS::Region`, `AWS::Partition`;
- Tránh hard-code account IDs và Region trong resource names/policies;
- Có tags, outputs và metadata cần thiết;
- Dùng resource names không xung đột giữa accounts/Regions;
- Tạo ra cùng desired state khi triển khai lặp lại.

### 4.2. Ví dụ template regional baseline

Template sau tạo một SSM Parameter trong từng account/Region được target:

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: Regional baseline marker deployed by CloudFormation StackSets

Parameters:
  EnvironmentType:
    Type: String
    AllowedValues:
      - development
      - staging
      - production

Resources:
  RegionalEnvironmentParameter:
    Type: AWS::SSM::Parameter
    Properties:
      Name: !Sub /organization/${EnvironmentType}/deployment-context
      Type: String
      Value: !Sub 'account=${AWS::AccountId};region=${AWS::Region};partition=${AWS::Partition}'
      Description: Regional deployment context managed by StackSets
      Tags:
        ManagedBy: CloudFormationStackSets
        Environment: !Ref EnvironmentType

Outputs:
  ParameterName:
    Value: !Ref RegionalEnvironmentParameter
~~~

`AWS::AccountId` và `AWS::Region` được resolve tại từng stack instance. Vì SSM Parameter là regional resource, mỗi account/Region có parameter riêng. Đây là ví dụ đào tạo; production cần namespace, encryption và ownership phù hợp.

### 4.3. Parameters dùng chung và parameter overrides

StackSet có thể nhận parameters dùng chung cho các instances. Với một số stack instances, có thể đặt parameter overrides để tùy biến account/Region.

Ví dụ:

- `EnvironmentType=production` cho OU production;
- `LogRetentionDays` khác nhau theo compliance;
- `VpcCidr` riêng cho từng account;
- `KmsKeyArn` theo Region.

Không nhúng secrets trực tiếp vào template hoặc parameter values có thể bị lộ qua CloudFormation APIs/events. Dùng dynamic references tới Secrets Manager/SSM SecureString khi phù hợp và cấp quyền đọc secret cho execution context.

Parameter override giúp cấu hình khác nhau nhưng làm tăng độ phức tạp; quản lý chúng bằng source control/manifest, không chỉnh tay không có audit.

Với auto-deployment, parameter overrides chỉ áp dụng cho accounts hiện đang ở target OUs và child OUs. Accounts được thêm vào sau này dùng giá trị mặc định của StackSet; đừng dựa vào override hiện tại để cấu hình account onboarding.

### 4.4. Region và Partition pseudo parameters

Template có thể dùng:

- `AWS::Region`: Region của stack instance;
- `AWS::AccountId`: account đang triển khai;
- `AWS::Partition`: partition như `aws`, `aws-cn`, `aws-us-gov`.

Không giả định mọi service/resource type có ở mọi Region hoặc partition. Commercial, China và GovCloud có endpoint, account boundary và service availability riêng. StackSets không phải cơ chế triển khai xuyên partition tùy ý.

### 4.5. IAM capabilities

Nếu template tạo IAM resources, `create-stack-set` có thể cần `CAPABILITY_IAM` hoặc `CAPABILITY_NAMED_IAM` tùy resource naming. Chỉ xác nhận capability sau khi review quyền IAM mà template sẽ tạo.

StackSets nhân bản quyền sang nhiều accounts. Một policy quá rộng trong template có thể mở rộng blast radius toàn Organization; review IAM resources như code production.

## 5. Tạo StackSet với service-managed permissions

### 5.1. Quy trình tổng quát

1. Chuẩn bị AWS Organization, OUs và trusted access;
2. Chọn management account hoặc delegated administrator;
3. Review template, parameters, IAM capabilities và target scope;
4. Tạo StackSet với `SERVICE_MANAGED`;
5. Tạo stack instances cho OU/account và Regions;
6. Theo dõi operation cho đến terminal status;
7. Xác minh stack instances và resources tại target accounts.

Tạo StackSet chỉ tạo định nghĩa quản lý; để triển khai vào các OUs/Regions đã chọn, cần tạo stack instances hoặc bật auto-deployment cho accounts phù hợp.

### 5.2. Tạo StackSet

Ví dụ AWS CLI từ management account:

~~~bash
aws cloudformation create-stack-set \
  --stack-set-name organization-regional-baseline \
  --template-body file://regional-baseline.yaml \
  --permission-model SERVICE_MANAGED \
  --auto-deployment Enabled=true,RetainStacksOnAccountRemoval=false \
  --parameters ParameterKey=EnvironmentType,ParameterValue=production \
  --region ap-southeast-1
~~~

Nếu gọi từ delegated administrator, thêm `--call-as DELEGATED_ADMIN`. Nếu gọi từ management account, dùng mặc định `SELF`.

`--region ap-southeast-1` ở lệnh này là Region nơi quản lý StackSet API/StackSet definition; nó không có nghĩa chỉ triển khai stack instance tại Singapore. Danh sách Regions mục tiêu được chỉ định ở bước create/update stack instances.

`RetainStacksOnAccountRemoval=false` là lựa chọn minh họa. Đánh giá resource deletion behavior trước khi dùng trong production.

### 5.3. Tạo stack instances theo OU và Regions

Tạo file `operation-preferences.json`:

~~~json
{
  "RegionConcurrencyType": "SEQUENTIAL",
  "RegionOrder": [
    "ap-southeast-1",
    "ap-southeast-2"
  ],
  "FailureTolerancePercentage": 5,
  "MaxConcurrentPercentage": 10,
  "ConcurrencyMode": "STRICT_FAILURE_TOLERANCE"
}
~~~

Sau đó tạo instances:

~~~bash
aws cloudformation create-stack-instances \
  --stack-set-name organization-regional-baseline \
  --deployment-targets OrganizationalUnitIds=ou-abcd-12345678 \
  --regions ap-southeast-1 ap-southeast-2 \
  --operation-preferences file://operation-preferences.json \
  --region ap-southeast-1
~~~

`ou-abcd-12345678` là placeholder. Xác minh OU ID và account membership trước khi chạy. Với delegated administrator, thêm `--call-as DELEGATED_ADMIN`.

### 5.4. Triển khai một số accounts trong OU

Nếu muốn chỉ chọn một số account thuộc OU, có thể dùng account filters. Ví dụ khái niệm:

~~~bash
aws cloudformation create-stack-instances \
  --stack-set-name organization-regional-baseline \
  --deployment-targets OrganizationalUnitIds=ou-abcd-12345678,Accounts=111122223333,444455556666,AccountFilterType=INTERSECTION \
  --regions ap-southeast-1 \
  --region ap-southeast-1
~~~

Ví dụ dùng `INTERSECTION`: chỉ các accounts vừa thuộc OU vừa nằm trong danh sách được triển khai. Kiểm tra AWS CLI version và cú pháp shorthand/JSON tương ứng; với cấu hình phức tạp, dùng file JSON để tránh lỗi parsing.

## 6. Tạo StackSet với self-managed permissions

### 6.1. Chuẩn bị roles

Trước khi gọi CloudFormation:

- Administration role nằm trong account điều khiển;
- Execution role có trong từng target account;
- Administration role được phép assume execution role;
- Execution role trust policy cho phép đúng administration role;
- Execution role chỉ có permissions cần thiết cho resources trong template;
- Tên role thống nhất với StackSet configuration.

Dùng AWS-provided setup template/hướng dẫn hiện hành để tạo trust relationship; không tự suy đoán principal ARN hoặc bỏ qua external governance controls.

### 6.2. Tạo self-managed StackSet

Ví dụ:

~~~bash
aws cloudformation create-stack-set \
  --stack-set-name selected-account-baseline \
  --template-body file://regional-baseline.yaml \
  --permission-model SELF_MANAGED \
  --administration-role-arn arn:aws:iam::111122223333:role/StackSetAdministrationRole \
  --execution-role-name StackSetExecutionRole \
  --parameters ParameterKey=EnvironmentType,ParameterValue=staging \
  --region ap-southeast-1
~~~

Sau đó triển khai vào account IDs:

~~~bash
aws cloudformation create-stack-instances \
  --stack-set-name selected-account-baseline \
  --accounts 444455556666 777788889999 \
  --regions ap-southeast-1 ap-southeast-2 \
  --region ap-southeast-1
~~~

Trong self-managed model, StackSet không tự discover tất cả accounts qua OU. Danh sách account targets và role provisioning là trách nhiệm của tổ chức.

### 6.3. Kiểm tra trust và execution permissions

Lỗi assume role thường do:

- Execution role không tồn tại trong target account;
- Trust policy không cho administration role assume;
- Administration role không có `sts:AssumeRole`;
- Execution role thiếu CloudFormation resource permissions;
- SCP/permission boundary chặn action;
- Role name trong StackSet không khớp.

Không khắc phục bằng cách gắn AdministratorAccess cho mọi execution role. Tạo policy theo resource types/actions mà template thực sự cần.

## 7. Operation preferences: concurrency và failure tolerance

### 7.1. Region concurrency

StackSet có thể chạy theo hai cách:

- `SEQUENTIAL`: hoàn tất Region trước rồi chuyển Region kế tiếp;
- `PARALLEL`: triển khai nhiều Regions đồng thời.

Sequential phù hợp rollout có kiểm soát, ví dụ triển khai Singapore trước, kiểm tra rồi mới tới Sydney. Parallel rút ngắn thời gian nhưng tăng phạm vi thay đổi đồng thời.

Với `SEQUENTIAL`, có thể chỉ định `RegionOrder` để kiểm soát thứ tự. Chọn Region đầu tiên có blast radius phù hợp và khả năng quan sát tốt; nếu muốn canary theo account, hãy target một tập account/OU nhỏ riêng trước.

### 7.2. Failure tolerance

Failure tolerance quy định số lượng hoặc tỷ lệ accounts trong mỗi Region được phép thất bại trước khi CloudFormation dừng triển khai ở Region đó và không tiếp tục các Regions tiếp theo.

Có thể chọn:

- `FailureToleranceCount`;
- `FailureTolerancePercentage`.

Chỉ dùng một trong hai trong cùng cấu hình. Khi dùng percentage, CloudFormation làm tròn xuống số nguyên gần nhất. Với target rất nhỏ, tỷ lệ 5% có thể tương đương 0 accounts được phép thất bại.

### 7.3. Maximum concurrent accounts

`MaxConcurrentCount` hoặc `MaxConcurrentPercentage` xác định mức account concurrency tối đa cho operation. Chỉ dùng một trong hai.

Concurrency thực tế có thể thấp hơn do throttling/service limits. Khi `STRICT_FAILURE_TOLERANCE`, mức concurrency ban đầu bị giới hạn bởi failure tolerance + 1 và giảm khi phát sinh lỗi để giữ failure tolerance. Khi `SOFT_FAILURE_TOLERANCE`, concurrency được tách khỏi failure tolerance và tiếp tục ở mức maximum đã cấu hình dù có lỗi.

### 7.4. Chọn ConcurrencyMode

| Mode | Behavior | Khi nào cân nhắc |
|---|---|---|
| `STRICT_FAILURE_TOLERANCE` | Giảm concurrency khi có failures để giữ failure tolerance | Rollout thận trọng, baseline quan trọng |
| `SOFT_FAILURE_TOLERANCE` | Giữ concurrency ở mức maximum đã đặt dù có failures | Rollout cần throughput và có kiểm soát riêng |

Mặc định là `STRICT_FAILURE_TOLERANCE`. Không chọn soft mode chỉ để tăng tốc nếu chưa có capacity, alarm và quy trình dừng operation.

Với soft mode, khi số failures vượt failure tolerance, operation sẽ dừng sau khi các deployments đã nằm trong concurrency queue hoàn tất. Vì vậy tổng số failed instances cuối cùng có thể lớn hơn failure tolerance đã cấu hình; hãy tính đến điều này khi đặt blast radius.

### 7.5. Operation preferences không phải auto-deployment preferences

`StackSetOperationPreferences` áp dụng cho các operations do người dùng khởi tạo như create/update stack instances. Các preferences này **không áp dụng cho AutoDeployment**. Auto-deployment settings được cấu hình riêng ở StackSet level.

Nếu cần rollout theo wave với canary, không dựa vào auto-deployment để thay thế pipeline có approval. Có thể target OU theo từng đợt hoặc điều khiển account onboarding bằng quy trình Organizations riêng.

### 7.6. Managed execution

StackSet có thể bật `ManagedExecution` để cho phép các operations không xung đột chạy đồng thời và xếp hàng các operations xung đột. Khi StackSet đang có operations chạy hoặc queued, các operation mới có thể được queue theo behavior của managed execution.

Bật managed execution chỉ khi hiểu operation ordering và conflict semantics. Nó không có nghĩa hai update cùng một stack instance sẽ chạy song song.

AWS khuyến nghị cân nhắc bật managed execution khi dùng auto-deployment; cơ chế này cho phép các auto-deployment operations ở nhiều target accounts chạy đồng thời trong một StackSet, tăng tốc onboarding ở Organization lớn.

Nếu StackSet đã có operations đang chạy hoặc đang queued, CloudFormation sẽ queue các operation mới kể cả khi chúng không xung đột. Không thể đổi execution configuration trong lúc StackSet còn operations running/queued.

## 8. Auto-deployment theo AWS Organizations

### 8.1. Account mới vào OU

Khi bật auto-deployment cho service-managed StackSet, accounts mới gia nhập target Organization/OU có thể tự động được triển khai stack instances. Đây là cách áp dụng baseline cho account onboarding.

Ví dụ:

- Account mới được tạo trong OU `Workloads-Production`;
- StackSet target OU này và auto-deployment enabled;
- CloudFormation tạo stack instances tại các Regions được cấu hình cho StackSet;
- Baseline xuất hiện mà không cần operator thêm account thủ công.

### 8.2. Account rời OU

Khi account rời target OU, StackSet xử lý stack instances theo `RetainStacksOnAccountRemoval`:

- `false`: Stack instances bị xóa theo auto-deployment behavior;
- `true`: Stacks được giữ lại trong account sau khi account rời target scope.

Retain stacks có thể để lại resources do central StackSet không còn quản lý theo cùng cách. Cần quy trình ownership handoff, tag và cleanup rõ ràng.

Khi chọn retain, stacks và resources vẫn ở trong target account nhưng stack được gỡ khỏi StackSet; sau đó central StackSet không còn quản lý chúng như stack instances của mình.

### 8.3. Auto-deployment settings là StackSet-level

Auto-deployment settings áp dụng ở cấp StackSet, không thể cấu hình riêng cho từng OU/account/Region trong cùng StackSet. Nếu các OU có lifecycle khác nhau, có thể cần tách StackSets theo policy/ownership.

### 8.4. Dependencies giữa StackSets trong auto-deployment

Với service-managed StackSets, có thể khai báo danh sách StackSet ARNs mà StackSet hiện tại phụ thuộc trong thuộc tính `AutoDeployment.DependsOn`. Khi auto-deployment được kích hoạt, CloudFormation xếp thứ tự để tất cả dependencies hoàn tất thành công trước khi bắt đầu operation của StackSet phụ thuộc.

Giới hạn hiện hành:

- Tối đa 10 dependencies cho mỗi StackSet;
- Tối đa 100 dependencies tính trên mỗi account;
- Dependencies được gỡ khi StackSet bị xóa hoặc Organizations bị deactivate.

Ví dụ cấu hình CLI khi cập nhật auto-deployment:

~~~bash
aws cloudformation update-stack-set \
  --stack-set-name workload-baseline \
  --use-previous-template \
  --auto-deployment Enabled=true,RetainStacksOnAccountRemoval=false,DependsOn=NETWORK_BASELINE_STACKSET_ARN,SECURITY_BASELINE_STACKSET_ARN \
  --region ap-southeast-1
~~~

Các giá trị `NETWORK_BASELINE_STACKSET_ARN` và `SECURITY_BASELINE_STACKSET_ARN` là placeholders; thay bằng StackSet ARNs thực tế trong cùng Organization/permission model phù hợp.

Dependency này dành cho **auto-deployment operations**. Nó không thay thế pipeline/waves cho mọi thao tác update thủ công hoặc release cần approval riêng. Với quy trình rollout có canary và kiểm tra application health giữa các bước, tiếp tục điều phối bằng pipeline/workflow.

## 9. Region strategy và account readiness

### 9.1. Chọn Regions trước khi triển khai

Mỗi stack instance triển khai resources trong một account/Region. Trước khi chọn Regions, xác định:

- Workload cần chạy ở đâu;
- Data residency/compliance;
- Service/resource type có hỗ trợ không;
- Region có được enable trong target accounts không;
- Quotas và resource naming;
- Network/DNS/KMS dependencies;
- Chi phí triển khai và vận hành.

Một Region có thể bị disabled by default trong account. Hãy enable Region cho các target accounts theo quy trình AWS trước khi StackSets deploy vào đó.

### 9.2. Region availability không đồng nhất

Một template hợp lệ tại Singapore có thể thất bại tại Sydney nếu resource type, feature hoặc quota khác nhau. Một số services là global/account-level, số khác là regional. Không giả định mọi resource được tạo một lần sẽ tự xuất hiện toàn cầu.

Dùng conditions/parameters khi có khác biệt thật sự, nhưng tránh tạo một template quá phức tạp cho mọi partition và service combination.

### 9.3. RegionOrder và rollout waves

Ví dụ rollout:

~~~text
Wave 0: sandbox account, ap-southeast-1
Wave 1: development OU, ap-southeast-1
Wave 2: development OU, ap-southeast-2
Wave 3: staging OU, both Regions
Wave 4: production OU, ap-southeast-1
Wave 5: production OU, ap-southeast-2
~~~

Dùng target OUs/account filters để tạo waves; đặt Region concurrency sequential khi cần quan sát từng Region. Ghi rõ success criteria trước khi mở wave tiếp theo.

### 9.4. Cross-account resource references

ARN, KMS key, VPC IDs và resource names có thể khác theo account/Region. Dùng parameters, SSM parameters hoặc outputs/exports theo kiến trúc phù hợp. Không giả định CloudFormation export/import tự động hoạt động xuyên account/Region như trong một stack đơn.

Khi template cần resource từ account khác, xác định rõ cơ chế chia sẻ như RAM, resource policy, role assumption hoặc deployment dependency.

## 10. Theo dõi StackSet operations

### 10.1. Operation là asynchronous

Các lệnh create/update/delete stack instances trả operation ID. Operation có thể mất thời gian vì CloudFormation phải thực hiện stack operations trên nhiều account/Regions.

Không coi việc CLI trả operation ID là deployment thành công. Theo dõi đến terminal status và kiểm tra từng stack instance.

### 10.2. Các lệnh kiểm tra

~~~bash
aws cloudformation describe-stack-set \
  --stack-set-name organization-regional-baseline \
  --region ap-southeast-1

aws cloudformation list-stack-instances \
  --stack-set-name organization-regional-baseline \
  --region ap-southeast-1

aws cloudformation list-stack-set-operations \
  --stack-set-name organization-regional-baseline \
  --region ap-southeast-1
~~~

Để xem một operation cụ thể:

~~~bash
aws cloudformation describe-stack-set-operation \
  --stack-set-name organization-regional-baseline \
  --operation-id OPERATION_ID \
  --region ap-southeast-1
~~~

Thay `OPERATION_ID` bằng ID trả về từ lệnh create/update. Khi dùng delegated administrator, thêm `--call-as DELEGATED_ADMIN` cho các lệnh yêu cầu call-as context.

### 10.3. Status của operation và stack instances

Theo dõi các status như `RUNNING`, `SUCCEEDED`, `FAILED`, `STOPPING`, `STOPPED`, `QUEUED` ở cấp operation và các trạng thái stack instance như `CURRENT`, `OUTDATED`, `INOPERABLE` hoặc trạng thái lỗi tương ứng.

Đừng chỉ đọc status tổng StackSet. Một operation có thể partial success: nhiều instances đã thành công nhưng một số accounts/Regions thất bại. Kiểm tra status reason và stack events trong account/Region bị lỗi.

### 10.4. Retry operation sau khi sửa lỗi

Khi operation thất bại:

1. Xác định account/Region/stack instance lỗi;
2. Mở stack events và đọc Status reason;
3. Phân loại template error, IAM deny, quota, Region availability hoặc resource conflict;
4. Sửa template/role/target prerequisites;
5. Kiểm tra các instances đã thành công có còn đúng desired state;
6. Khởi tạo operation mới với target/concurrency phù hợp;
7. Xác minh toàn bộ target set.

Không chạy retry hàng loạt liên tục khi chưa biết nguyên nhân. Điều đó tăng throttling và làm khó phân tích event history.

## 11. Drift detection và configuration compliance

### 11.1. Drift là gì?

Drift xảy ra khi actual resource configuration khác với desired configuration trong CloudFormation template và parameters, ví dụ người vận hành sửa Security Group rule trực tiếp trong console.

StackSet drift detection chạy drift detection trên các stacks thuộc stack instances và tổng hợp trạng thái. Có thể dùng để phát hiện cấu hình bị chỉnh sửa ngoài IaC.

### 11.2. Chạy drift detection

Ví dụ:

~~~bash
aws cloudformation detect-stack-set-drift \
  --stack-set-name organization-regional-baseline \
  --region ap-southeast-1
~~~

Lệnh trả về operation ID; theo dõi operation bằng `describe-stack-set-operation`. Drift detection có thể mất thời gian tùy số instances/resources và chỉ chạy một drift detection operation cho một StackSet tại một thời điểm.

### 11.3. Giới hạn drift detection

Drift detection:

- Chỉ đánh giá resource types/properties được CloudFormation hỗ trợ drift detection;
- Cần permissions đọc trạng thái resource;
- Không thay thế AWS Config, Security Hub hoặc continuous compliance monitoring;
- Không phát hiện mọi thay đổi ở mọi service;
- Chỉ so sánh các property được template/parameters khai báo rõ; default properties không được khai báo có thể không được theo dõi;
- Thay đổi một stack instance trực tiếp bằng CloudFormation stack operation, thay vì qua StackSet, không được xem là drift trong StackSet drift detection;
- Có thể có edge cases với relationships/attachments giữa resources hoặc stacks.

Vì vậy, `IN_SYNC` không phải bằng chứng tuyệt đối rằng mọi cấu hình trong account đều compliant. Kết hợp drift detection với AWS Config rules, CloudTrail, security monitoring và policy-as-code.

### 11.4. Xử lý DRIFTED

Khi instance bị drift:

1. Xem resource drift details và expected/current property values;
2. Xác định thay đổi có chủ đích hay ngoài quy trình;
3. Nếu thay đổi hợp lệ, cập nhật template để desired state phản ánh quyết định mới;
4. Nếu thay đổi trái phép, review tác động rồi đưa resource về trạng thái template;
5. Chạy update/drift detection lại;
6. Ghi audit và cập nhật quy trình ngăn tái diễn.

Không update StackSet mù quáng khi chưa hiểu resource drift; CloudFormation có thể ghi đè thay đổi thủ công và gây gián đoạn.

## 12. Update, rollback và quản lý thay đổi

### 12.1. Update template và instances

Khi template thay đổi:

- Review diff và resource replacement risks;
- Kiểm tra parameter changes;
- Xác định target account/Region;
- Chọn operation preferences;
- Triển khai canary/waves;
- Theo dõi từng stack instance;
- Xác minh resource state và application health.

Một StackSet update có thể tác động hàng trăm stacks. Không dùng production-wide update làm lần kiểm thử đầu tiên.

### 12.2. StackSet operation không phải một transaction toàn Organization

Một operation có thể thành công ở một số account/Regions và thất bại ở nơi khác. CloudFormation không đảm bảo rollback nguyên tử toàn bộ matrix về trạng thái trước đó.

Một stack instance có thể rollback resources trong stack theo CloudFormation semantics, nhưng các instances đã thành công ở accounts khác có thể vẫn giữ version mới. Cần quản lý partial rollout và quyết định tiếp tục, sửa rồi retry, hoặc triển khai một update đảo ngược đã review.

### 12.3. Rollback strategy

Trước rollout, chuẩn bị:

- Template version trước đó;
- Parameter values/overrides;
- Target account/Region list;
- Operation ID và status snapshot;
- Change set/diff review ở cấp template nếu quy trình có;
- Rollback/forward-fix criteria;
- Owner và thời gian maintenance.

Rollback có thể là update StackSet về template version cũ, nhưng resource updates không phải lúc nào cũng đảo ngược dữ liệu hoặc external side effects. Database migrations, data deletion và IAM trust changes cần kế hoạch riêng.

### 12.4. RetainStacksOnAccountRemoval không phải deletion protection

`RetainStacksOnAccountRemoval` điều khiển auto-deployment khi account rời target scope. Nó không thay thế CloudFormation stack termination protection hoặc resource-specific deletion policies.

Dùng `DeletionPolicy: Retain` cho resources cần giữ dữ liệu khi stack bị xóa, và review resource lifecycle. Phân biệt rõ retain stack instance với retain resource khi stack deletion xảy ra.

### 12.5. Import và migration

Nếu account đã có resources tạo thủ công hoặc từ stacks riêng lẻ, không giả định StackSet sẽ tự adopt chúng. Cần đánh giá CloudFormation resource import, StackSet import capabilities và resource type support.

Trước khi import, đối chiếu logical IDs, physical IDs, template ownership, stack status và drift. Không tạo một resource mới trùng tên chỉ vì StackSet chưa quản lý resource cũ.

## 13. Security guardrails và governance

### 13.1. Least privilege cho operator

Operator/CI role cần quyền CloudFormation StackSets phù hợp với actions như create/update/delete/list/describe/detect drift, cùng quyền Organizations hoặc role assumptions cần thiết theo permission model.

Giới hạn theo:

- StackSet names/ARNs và allowed Regions;
- Resource types được phép trong templates;
- Target OUs/accounts;
- IAM capabilities;
- Role ARN và execution role name;
- Change approval cho production OU.

### 13.2. Execution permissions

Với self-managed, execution role có thể tạo mọi resources được policy cho phép. Với service-managed, service-linked role và permissions được quản lý qua Organizations integration, nhưng quyền của operator vẫn quyết định ai có thể khởi tạo deployment.

Không nhầm quyền gọi CloudFormation với quyền mà CloudFormation cần để tạo resource. Kiểm tra cả operator policy, execution/service-linked role, resource policy và SCP.

### 13.3. SCP và permission boundaries

SCP có thể chặn resource action dù StackSet template và execution role có Allow. Ví dụ SCP chặn tạo public S3 bucket hoặc tắt CloudTrail. Trước rollout, kiểm tra guardrails của target OU.

Đừng tắt SCP để làm deployment thành công. Sửa template hoặc policy theo security architecture đã được phê duyệt.

### 13.4. Secrets và encryption

- Không hard-code secret values trong template;
- Dùng Secrets Manager/SSM SecureString dynamic references khi phù hợp;
- Kiểm soát KMS key policies theo account/Region;
- Không log parameter values nhạy cảm;
- Mã hóa artifact/template trong S3 nếu có dữ liệu nhạy cảm;
- Giới hạn quyền đọc template artifacts và operation logs.

### 13.5. Audit

CloudTrail ghi nhận các API calls liên quan đến CloudFormation/Organizations. Lưu lại:

- Ai khởi tạo operation;
- StackSet name và operation ID;
- Template version/hash;
- Target OUs/accounts và Regions;
- Parameter overrides;
- Operation preferences;
- Kết quả, failed instances và remediation.

Tích hợp change ticket/release ID vào tags, description hoặc deployment metadata để truy vết thay đổi.

## 14. Troubleshooting

### 14.1. Trusted access hoặc Organizations errors

Kiểm tra trusted access đã bật chưa, operator đang dùng management account hay delegated admin, `--call-as` có đúng không và account target có thuộc Organization không.

Nếu delegated admin chưa đăng ký hoặc dùng sai call-as context, API có thể từ chối. Không dùng `SELF` từ delegated account cho service-managed operation khi API yêu cầu `DELEGATED_ADMIN`.

### 14.2. Account/OU target không đúng

Kiểm tra OU ID, parent/child hierarchy, account membership và `AccountFilterType`. Với account filters, xác minh tập intersection/difference/union trước khi deploy.

Đặc biệt cẩn thận khi target parent OU: child OUs có thể được bao gồm.

### 14.3. Region disabled hoặc resource không hỗ trợ

Nếu Region disabled by default trong target account, enable Region trước. Kiểm tra resource type/service availability, quotas, KMS keys và dependencies tại Region đó.

Một Region có trong `--regions` không đảm bảo mọi resource trong template đều được hỗ trợ ở đó.

### 14.4. AssumeRole/AccessDenied

Với self-managed:

- Administration role ARN có đúng không;
- Execution role có tồn tại trong mọi target account không;
- Trust policy có đúng principal không;
- `sts:AssumeRole` có được phép không;
- Execution role có resource permissions không.

Với service-managed, kiểm tra trusted access/service-linked role và operator permissions. Cả hai models đều có thể bị SCP/permission boundary/resource policy chặn.

### 14.5. Resource creation failed

Mở stack events trong account/Region bị lỗi để tìm resource logical ID và Status reason. Kiểm tra duplicate names, quota, dependency, immutable property replacement, IAM capability và Region-specific limitations.

StackSet operation status thường chỉ cho biết tổng thể; stack events mới cho biết nguyên nhân chi tiết của resource failure.

### 14.6. Operation đang chạy lâu hoặc bị queue

Xem operation history, number of target instances, Region concurrency, max concurrent accounts và service throttling. Managed execution có thể queue conflicting operations. Không gửi thêm nhiều updates cùng lúc với kỳ vọng chúng sẽ chạy nhanh hơn.

### 14.7. Stack instance OUTDATED hoặc INOPERABLE

`OUTDATED` thường cho biết stack instance chưa khớp template/version hiện tại hoặc operation trước đó không hoàn tất. `INOPERABLE` có thể cho biết instance ở trạng thái không thể tiếp tục operation bình thường.

Xem stack events, status reason và stack status. Sửa nguyên nhân rồi chạy update/retry phù hợp; nếu stack cần repair thủ công, ghi rõ thay đổi và chạy drift detection sau đó.

## 15. Case study: triển khai regional baseline cho Organization

### 15.1. Bối cảnh

Một tổ chức có:

- Management account;
- Platform delegated administrator account;
- OUs `Sandbox`, `Development`, `Production`;
- Workload accounts tại Singapore và Sydney;
- Baseline cần một SSM Parameter theo account/Region để ứng dụng đọc deployment context.

Yêu cầu:

1. Account mới vào OU được nhận baseline tự động;
2. Development được rollout trước Production;
3. Singapore triển khai trước Sydney;
4. Không triển khai vào management account;
5. Có thể giữ stacks khi account rời OU theo policy;
6. Theo dõi operation và drift.

### 15.2. Thiết kế

- Dùng service-managed permissions;
- Bật trusted access cho CloudFormation StackSets;
- Đăng ký platform account làm delegated administrator;
- Tạo StackSet trong management account context qua delegated admin;
- Target OU riêng theo từng rollout wave;
- Chọn `SEQUENTIAL` Region concurrency;
- Bắt đầu với `STRICT_FAILURE_TOLERANCE`;
- Bật auto-deployment cho OU có onboarding tự động;
- Chọn `RetainStacksOnAccountRemoval` theo ownership policy;
- Dùng CloudWatch/CloudTrail và runbook để theo dõi.

### 15.3. Rollout plan

~~~text
Preflight:
  - Validate template
  - Confirm trusted access and delegated admin
  - Confirm target OU/account membership
  - Enable required Regions
  - Confirm service quotas and IAM/SCP

Wave 1:
  - Sandbox OU
  - ap-southeast-1
  - Validate SSM parameter and stack events

Wave 2:
  - Development OU
  - ap-southeast-1, then ap-southeast-2
  - Verify drift and application consumption

Wave 3:
  - Production OU
  - Canary accounts first
  - Review operation status and health signals

Steady state:
  - Auto-deploy new accounts
  - Periodic drift detection
  - Review operation history and failed instances
~~~

### 15.4. Tiêu chí thành công

- Tất cả target accounts/Regions có stack instance `CURRENT`;
- Stack operation hoàn tất `SUCCEEDED`;
- SSM parameter values có account/Region chính xác;
- Không có unexpected resource replacement;
- Drift detection không phát hiện drift chưa được xử lý;
- CloudTrail có actor/operation ID để audit;
- Account onboarding nhận baseline theo auto-deployment policy;
- Account offboarding giữ/xóa stacks theo quyết định đã ghi nhận.

## 16. Câu hỏi tự kiểm tra

1. Stack, StackSet và stack instance khác nhau thế nào?
2. Một StackSet có thể triển khai tới bao nhiêu account/Region combinations theo thiết kế?
3. Service-managed permissions dựa vào dịch vụ AWS nào?
4. Self-managed permissions cần những roles nào?
5. Vì sao service-managed StackSets không target management account?
6. Delegated administrator được đăng ký ở đâu và có phạm vi quyền thế nào?
7. `--call-as DELEGATED_ADMIN` dùng trong trường hợp nào?
8. Target parent OU có bao gồm child OUs không?
9. `INTERSECTION`, `DIFFERENCE` và `UNION` khác nhau thế nào?
10. Auto-deployment xử lý account mới vào OU ra sao?
11. `RetainStacksOnAccountRemoval` quyết định điều gì?
12. Vì sao `OperationPreferences` không điều khiển auto-deployment?
13. `SEQUENTIAL` và `PARALLEL` Region concurrency khác nhau thế nào?
14. `STRICT_FAILURE_TOLERANCE` giảm concurrency ra sao?
15. Vì sao failure tolerance percentage có thể làm tròn xuống zero?
16. StackSet create có tự triển khai stack instances không?
17. Vì sao một operation có thể partial success?
18. Drift detection có phát hiện mọi thay đổi ngoài CloudFormation không?
19. Vì sao `AWS::Region` và `AWS::AccountId` hữu ích trong StackSet templates?
20. Vì sao không nên hard-code KMS key ARN hoặc account ID trong template dùng chung?
21. Region disabled by default ảnh hưởng deployment thế nào?
22. StackSets có bảo đảm atomic rollback toàn Organization không?
23. Vì sao service-managed model không hỗ trợ nested stacks/macros/transforms?
24. Khi nào cần self-managed permissions?
25. Những dữ liệu nào cần lưu trong deployment audit?

## 17. Đáp án gợi ý

1. Stack là tập resources; StackSet là định nghĩa quản lý nhiều stacks; stack instance là stack tại một account/Region.
2. Phụ thuộc số target accounts, Regions, service quotas và thiết kế; cần kiểm tra quotas hiện hành.
3. AWS Organizations trusted access.
4. Administration role và execution role ở target accounts.
5. Đây là giới hạn của service-managed permission model; dùng self-managed nếu cần triển khai management account.
6. Đăng ký trong AWS Organizations; delegated admin có quyền triển khai rộng tới các accounts trong Organization.
7. Khi gọi StackSets service-managed từ delegated administrator account.
8. Có; parent OU target bao gồm child OUs/accounts.
9. Intersection là phần giao; Difference loại accounts trong danh sách; Union là hợp.
10. Auto-deployment tạo stack instances khi account gia nhập target scope.
11. Giữ hay xóa stack instances khi account rời target OU/scope.
12. Auto-deployment có settings riêng; StackSetOperationPreferences không áp dụng cho auto-deployment.
13. Sequential lần lượt từng Region; Parallel chạy nhiều Regions đồng thời.
14. Giảm actual concurrency khi failures xảy ra để giữ failure tolerance.
15. CloudFormation làm tròn xuống số nguyên accounts.
16. Không; cần create-stack-instances hoặc auto-deployment.
17. Một số instances có thể thành công trong khi một số account/Region thất bại.
18. Không; chỉ resource types/properties hỗ trợ drift detection.
19. Chúng được resolve riêng cho từng stack instance.
20. Mỗi account/Region có resource/ARN khác nhau; dùng pseudo parameters và parameters.
21. Stack instance deployment có thể thất bại cho đến khi Region được enable.
22. Không; operation có thể partial success và cần remediation/forward-fix.
23. Đây là giới hạn của service-managed StackSets.
24. Khi target accounts ngoài Organization hoặc cần tự quản lý role deployment.
25. Actor, StackSet, template version/hash, targets, Regions, parameters, operation ID, preferences và results.

## 18. Checklist triển khai production

### Governance và permissions

- [ ] Chọn service-managed hay self-managed theo account governance.
- [ ] Trusted access được bật và kiểm tra khi dùng service-managed.
- [ ] Delegated administrator được đăng ký đúng account và bảo vệ.
- [ ] Đã hiểu service-managed StackSets không deploy vào management account.
- [ ] Self-managed administration/execution roles có trust và permissions least privilege.
- [ ] Operator role, SCP và permission boundaries đã được review.
- [ ] Target OU/account IDs đã được xác minh.

### Template và deployment

- [ ] Template được validate, review diff và lưu version control.
- [ ] Parameters/overrides có manifest và audit.
- [ ] Dùng pseudo parameters cho account/Region/partition.
- [ ] Resource types có hỗ trợ tại mọi target Regions.
- [ ] Required Regions đã được enable trong target accounts.
- [ ] `RegionOrder`, concurrency và failure tolerance phù hợp rollout risk.
- [ ] Auto-deployment/retain behavior đã được quyết định.
- [ ] Dependencies giữa StackSets được điều phối bằng waves/pipeline.
- [ ] IAM capabilities và resource replacement risks đã được review.

### Operations và security

- [ ] Theo dõi operation ID đến terminal status.
- [ ] Kiểm tra stack instances và stack events, không chỉ StackSet summary.
- [ ] Có quy trình xử lý partial success/OUTDATED/INOPERABLE.
- [ ] Drift detection kết hợp AWS Config/CloudTrail và compliance monitoring.
- [ ] Secrets không nằm trong plaintext template/parameters/logs.
- [ ] KMS/resource policies được kiểm tra theo account/Region.
- [ ] CloudTrail audit ghi actor, target, template version và operation ID.
- [ ] Có rollback/forward-fix, canary, runbook và owner.
- [ ] Có quy trình redrive/retry operations sau khi sửa nguyên nhân.
- [ ] Không giả định StackSet operation là transaction atomic toàn Organization.

**Kết quả mong đợi:** bạn có thể thiết kế và vận hành CloudFormation StackSets cho nhiều accounts/Regions, lựa chọn đúng permission model, target đúng OUs, điều phối rollout an toàn, theo dõi partial failures và phát hiện drift trong mô hình IaC tập trung.

## Tài liệu AWS chính thức

- [CloudFormation StackSets concepts](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacksets-concepts.html)
- [Prerequisites for using CloudFormation StackSets](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacksets-prereqs.html)
- [Create StackSets with service-managed permissions](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacksets-orgs-associate-stackset-with-org.html)
- [Activate trusted access for StackSets](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacksets-orgs-activate-trusted-access.html)
- [Register a delegated administrator](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacksets-orgs-delegated-admin.html)
- [Create StackSets with self-managed permissions](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacksets-getting-started-create-self-managed.html)
- [Add stacks to StackSets](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stackinstances-create.html)
- [Enable or disable automatic deployments](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacksets-orgs-manage-auto-deployment.html)
- [StackSet AutoDeployment properties and dependencies](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-properties-cloudformation-stackset-autodeployment.html)
- [StackSet operation options](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacksets-operate.html)
- [Choose the concurrency mode](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/concurrency-mode.html)
- [StackSetOperationPreferences API](https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_StackSetOperationPreferences.html)
- [Managed execution for StackSets](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacksets-concepts.html)
- [Performing drift detection on StackSets](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacksets-drift.html)
- [Troubleshooting StackSets](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacksets-troubleshooting.html)
- [AWS::CloudFormation::StackSet resource reference](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-cloudformation-stackset.html)
- [CloudFormation drift detection](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-stack-drift.html)
- [AWS Organizations](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_introduction.html)

> **Lưu ý áp dụng:** OU IDs, account IDs, role ARNs, Regions, resource names và parameters trong bài là ví dụ đào tạo. Trước khi triển khai, xác minh target membership, trusted access, permissions, Region availability, quotas và resource replacement behavior. StackSets có thể thay đổi hàng loạt resources trên nhiều accounts; hãy thử nghiệm trên sandbox, dùng canary/waves và lưu audit đầy đủ.
