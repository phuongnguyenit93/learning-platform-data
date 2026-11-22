# Drift detection, import resource và quản lý thay đổi ngoài mã

Infrastructure as Code (IaC) mô tả hạ tầng mong muốn trong các tệp có thể review, version control và triển khai lặp lại. Nhưng hạ tầng AWS vẫn có thể bị thay đổi ngoài workflow IaC: một kỹ sư chỉnh Security Group trên Console để xử lý sự cố, một automation cập nhật cấu hình, một service tự thay đổi thuộc tính được quản lý, hoặc một team tạo resource mới trực tiếp bằng CLI. Khi cấu hình thực tế không còn khớp với mã, hệ thống xuất hiện **configuration drift**.

Drift detection giúp phát hiện khác biệt giữa cấu hình được IaC quản lý và trạng thái thật. Resource import đưa resource đã tồn tại vào phạm vi quản lý IaC. Quản lý thay đổi ngoài mã thiết lập quy trình để ghi nhận, đánh giá, chấp thuận, khôi phục hoặc đưa thay đổi có chủ đích trở lại source of truth.

Bài thuộc chương **Hạ tầng dưới dạng mã**, mô-đun **CLOUD_PROVIDERS_AWS**. Nội dung kết nối Region/AZ, IAM, VPC, compute, storage, database, messaging và serverless với mục tiêu xây dựng hạ tầng an toàn, có khả năng quan sát, phục hồi và kiểm soát chi phí. Ví dụ sử dụng AWS CloudFormation và Terraform để minh họa các khái niệm chung; các giới hạn import/drift phụ thuộc resource type, provider version và công cụ.

> **Nguyên tắc vận hành:** Trước khi sửa drift, phải xác định resource owner, source of truth, tác động và lý do thay đổi. Chỉ một hệ thống IaC nên chịu trách nhiệm lifecycle cho một resource tại một thời điểm. Một lệnh apply có thể thay đổi hoặc xóa resource đang chạy thật; luôn đọc plan/change set trước khi thực thi.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích configuration drift và phân biệt drift với unmanaged resource.
2. Phân biệt desired configuration, actual configuration, IaC state và resource ownership.
3. Mô tả cách CloudFormation drift detection so sánh template với AWS resource.
4. Hiểu trạng thái `IN_SYNC`, `DRIFTED`, `NOT_CHECKED` và trạng thái detection operation.
5. Nhận biết giới hạn coverage: resource type, property, default value, nested stack và attachment relationships.
6. Phát hiện drift trong Terraform bằng `plan`, `plan -refresh-only` và HCP Terraform health assessments.
7. Phân biệt refresh state với sửa hạ tầng thật.
8. Import resource hiện có vào CloudFormation stack hoặc Terraform state/configuration.
9. Lập inventory và xác định resource identifier, dependency, ownership trước khi import.
10. Tránh quản lý cùng một resource bằng nhiều stack/workspace.
11. Chọn remediation: codify thay đổi, revert về desired state, import hoặc tách ownership.
12. Quản lý thay đổi khẩn cấp qua break-glass, audit trail, approval và reconciliation.
13. Bảo vệ Terraform state, state locking, backup và CloudFormation change sets.
14. Xây dựng CI/CD drift checks, AWS Config/CloudTrail signals và cảnh báo vận hành.
15. Thực hành phát hiện, import và xử lý drift trên sandbox an toàn.

## 2. Configuration drift là gì?

**Configuration drift** xảy ra khi thuộc tính thực tế của một resource khác với cấu hình mà IaC mong muốn hoặc đang ghi nhận. Ví dụ:

- Template định nghĩa Security Group chỉ mở TCP 443, nhưng một kỹ sư thêm rule TCP 22 từ Internet.
- Terraform khai báo RDS instance có deletion protection, nhưng Console tắt thuộc tính này.
- CloudFormation template định nghĩa S3 bucket versioning enabled, nhưng cấu hình thực tế bị thay đổi.
- Một automation thay đổi desired capacity của Auto Scaling Group ngoài workflow IaC.
- Một resource đã được tạo bằng Console, chưa nằm trong state/template nào: đây là **unmanaged resource**, chưa nhất thiết là drift của một stack/workspace cụ thể.

### 2.1. Ba trạng thái cần phân biệt

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Desired configuration | Cấu hình mà mã IaC yêu cầu | `min_size = 2` |
| Recorded state | Thông tin IaC lưu về resource đã quản lý | Terraform state ghi instance ID và thuộc tính đã refresh gần nhất |
| Actual configuration | Cấu hình đang tồn tại trên AWS | ASG đang có `min_size = 4` |

Drift có thể tồn tại giữa desired và actual, hoặc giữa recorded state và actual. Cách công cụ phát hiện khác nhau: CloudFormation so sánh actual với các property được quản lý trong template; Terraform refresh provider state rồi so với configuration để lập plan.

### 2.2. Ví dụ Security Group drift

~~~mermaid
flowchart LR
    CODE["IaC desired state<br/>TCP 443 from approved CIDR"] --> EXPECTED["Expected configuration"]
    CONSOLE["Console / CLI / automation<br/>adds TCP 22 from 0.0.0.0/0"] --> ACTUAL["Actual Security Group"]
    EXPECTED --> COMPARE["Drift detection / plan"]
    ACTUAL --> COMPARE
    COMPARE --> RESULT["Drift found"]
    RESULT --> DECIDE{"Review intent and impact"}
    DECIDE -->|"Approved change"| UPDATE["Update IaC code"]
    DECIDE -->|"Unauthorized / temporary"| REVERT["Restore approved configuration"]
~~~

### 2.3. Vì sao drift nguy hiểm?

- **Security:** rule mở rộng, encryption tắt, public access bật hoặc IAM permission bị nới.
- **Availability:** subnet route, load balancer listener, scaling hoặc database parameter bị thay đổi.
- **Data protection:** retention, backup, deletion protection, versioning hoặc KMS key policy bị chỉnh.
- **Cost:** instance size, NAT Gateway, logging, storage class hoặc provisioned capacity tăng ngoài dự kiến.
- **Deployment failure:** lần apply tiếp theo có thể overwrite thay đổi vận hành, thay resource hoặc gây replacement.
- **Audit/compliance:** mã trong Git không phản ánh cấu hình thực tế đang chạy.

Drift detection không tự sửa resource. Nó cung cấp bằng chứng để người vận hành quyết định remediation.

## 3. Drift, import và unmanaged resource khác nhau thế nào?

| Tình huống | Resource có trong IaC state/stack? | Actual khác desired? | Hành động chính |
|---|---:|---:|---|
| Drifted managed resource | Có | Có | Detect, review và reconcile |
| In-sync managed resource | Có | Không (trong phạm vi công cụ kiểm tra) | Tiếp tục quản lý bình thường |
| Unmanaged resource | Không | Không có desired state tương ứng | Inventory, import hoặc giao owner khác |
| Orphan resource | Không còn owner hợp lệ | Không xác định | Truy vết owner, dependencies, retention trước khi xử lý |
| Intentional out-of-band change | Có thể có | Có thể có | Approve, codify hoặc rollback |
| Unsupported property/resource | Có | Không thể kết luận | Bổ sung kiểm tra khác, không hiểu `NOT_CHECKED` là in-sync |

**Import không phải remediation chung cho mọi drift.** Import dùng khi resource đã tồn tại nhưng chưa được một stack/state quản lý. Nếu resource đã nằm trong CloudFormation stack hoặc Terraform state, thường cần sửa template/configuration hoặc actual resource để hai phía hội tụ.

### 3.1. Một resource chỉ nên có một IaC owner

Một EC2 instance hoặc Security Group không nên đồng thời được quản lý lifecycle bởi:

- CloudFormation stack A,
- Terraform workspace B,
- một CDK stack,
- và một pipeline script tự gọi AWS API.

Các công cụ có thể đọc hoặc tham chiếu cùng resource, nhưng chỉ một owner nên chịu trách nhiệm create/update/delete. Nếu hai hệ thống cùng quản lý, một pipeline có thể undo thay đổi của pipeline kia hoặc xóa resource mà hệ thống còn lại vẫn nghĩ đang tồn tại.

### 3.2. Phân biệt shared dependency và shared ownership

Có thể để một network stack sở hữu VPC/subnets, còn application stack tham chiếu subnet IDs qua exports/outputs/data sources. Application stack sử dụng VPC không có nghĩa nó sở hữu lifecycle của VPC. Thiết kế ranh giới ownership rõ từ đầu sẽ giảm drift và tránh import chồng lấn.

## 4. Quy trình quản lý drift tổng quát

~~~mermaid
flowchart TD
    A["Schedule / alert / incident"] --> B["Discover affected resource"]
    B --> C["Identify IaC owner and last change"]
    C --> D["Detect and collect expected vs actual"]
    D --> E{"Resource supported and result reliable?"}
    E -->|"No"| F["Use AWS Config / API / audit checks"]
    E -->|"Yes"| G["Assess security, availability, data and cost impact"]
    F --> G
    G --> H{"Why did it change?"}
    H -->|"Approved permanent change"| I["Update IaC code"]
    H -->|"Emergency / temporary"| J["Record exception and expiry"]
    H -->|"Unauthorized / accidental"| K["Restore desired state"]
    H -->|"Unmanaged resource"| L["Inventory and import decision"]
    I --> M["Plan / change set review"]
    J --> M
    K --> M
    L --> M
    M --> N["Apply through approved workflow"]
    N --> O["Re-detect / verify / close audit"]
~~~

Các bước bắt buộc:

1. **Discover:** tìm resource, account, Region, stack/workspace và business owner.
2. **Identify source of truth:** xác nhận repository, module, state backend và resource address/logical ID.
3. **Detect:** chạy drift detection hoặc refresh-only plan, ghi lại timestamp.
4. **Investigate:** đối chiếu CloudTrail, AWS Config, incident ticket, change request và người thực hiện.
5. **Classify:** thay đổi có chủ đích, khẩn cấp, vô tình, do service tự quản lý hay resource chưa được quản lý.
6. **Choose remediation:** codify, revert, import, tách ownership hoặc tạo exception có thời hạn.
7. **Review:** kiểm tra plan/change set và tác động replacement/deletion.
8. **Apply:** thực hiện qua workflow có approval, state lock và audit.
9. **Verify:** chạy detection lại, kiểm tra health/metrics và đóng incident/change record.


## 5. AWS CloudFormation drift detection

CloudFormation có thể detect drift trên toàn stack hoặc từng resource. Công cụ so sánh **actual property values** với giá trị mong đợi trong template và stack parameters. Nếu một resource có property khác, resource được đánh dấu `MODIFIED`; nếu resource bị xóa ngoài CloudFormation, trạng thái có thể là `DELETED`.

### 5.1. Drift status

| Phạm vi | Status | Ý nghĩa |
|---|---|---|
| Stack | `IN_SYNC` | Các resource được hỗ trợ và đã kiểm tra khớp expected properties |
| Stack | `DRIFTED` | Có ít nhất một resource bị drift |
| Stack | `NOT_CHECKED` | Chưa có kết quả drift check |
| Resource | `IN_SYNC` | Các properties được hỗ trợ và đã kiểm tra khớp expected values |
| Resource | `MODIFIED` | Một hoặc nhiều properties của resource khác expected |
| Resource | `DELETED` | Resource đã bị xóa ngoài stack |
| Resource | `NOT_CHECKED` | Resource chưa được kiểm tra hoặc không có coverage phù hợp |
| Detection operation | `DETECTION_IN_PROGRESS` | Detection operation đang chạy |
| Detection operation | `DETECTION_COMPLETE` | Detection hoàn tất cho resource được hỗ trợ |
| Detection operation | `DETECTION_FAILED` | Detection thất bại cho ít nhất một resource |

`IN_SYNC` chỉ có nghĩa là các thuộc tính được CloudFormation hỗ trợ và đã kiểm tra đang khớp. Nó **không chứng minh mọi thuộc tính của mọi resource trong stack đều giống nhau**; stack không có resource nào hỗ trợ drift detection cũng có thể mang trạng thái này.

### 5.2. Những gì CloudFormation có thể và không thể phát hiện

CloudFormation drift detection có giới hạn quan trọng:

- Chỉ kiểm tra resource types có hỗ trợ drift detection.
- Chỉ kiểm tra các resource properties được khai báo tường minh trong template hoặc qua stack parameters. Default value mà template bỏ trống không được theo dõi.
- Một số properties không thể so sánh chính xác vì API service không trả được giá trị tương ứng; ví dụ một số nội dung code hoặc cấu hình được biểu diễn gián tiếp.
- Một số attachment relationships giữa resource types có thể làm kết quả khó diễn giải, nhất là khi attachment nằm ở stack khác.
- Drift detection trên parent stack không tự chạy cho nested stacks; cần chạy trực tiếp trên nested stack.
- Có trường hợp service trả giá trị default hoặc normalize property khiến kết quả cần review.

Trước khi dùng detection làm control bắt buộc, tra danh sách resource type/property support của AWS cho Region và resource đang dùng. Nếu kết quả là `NOT_CHECKED`, bổ sung AWS Config rules, service API checks hoặc policy-as-code.

### 5.3. Chạy drift detection qua AWS CLI

~~~bash
# Khởi chạy drift detection cho toàn stack.
aws cloudformation detect-stack-drift \
  --stack-name production-network

# Lệnh trên trả về StackDriftDetectionId.
# Dùng ID đó để theo dõi operation.
aws cloudformation describe-stack-drift-detection-status \
  --stack-drift-detection-id d1b2c3d4-0000-1111-2222-example

# Liệt kê drift details của resources trong stack.
aws cloudformation describe-stack-resource-drifts \
  --stack-name production-network
~~~

Đây là thao tác đọc cấu hình/khởi chạy detection, không tự thay đổi resource. Chạy detection có thể mất vài phút tùy số lượng resource. Không khởi chạy nhiều operation chồng nhau trên cùng stack; xem timestamp `Last drift check` để tránh dựa vào kết quả cũ.

### 5.4. Detect một resource cụ thể

~~~bash
aws cloudformation detect-stack-resource-drift \
  --stack-name production-network \
  --logical-resource-id PublicWebSecurityGroup
~~~

Phù hợp khi vừa xử lý incident hoặc muốn xác minh một resource sau remediation. Kết quả có expected/current property values và difference types nếu service/resource hỗ trợ.

### 5.5. Quyền IAM cần thiết

Principal chạy drift detection cần CloudFormation permissions phù hợp, ví dụ `cloudformation:DetectStackDrift`, `cloudformation:DetectStackResourceDrift`, cùng quyền read/describe resource types cần kiểm tra (ví dụ EC2 Describe APIs). Một số resource types còn yêu cầu CloudFormation registry/type configuration read permissions. Nếu thiếu permission, detection có thể fail hoặc resource không được kiểm tra.

### 5.6. Ví dụ đọc kết quả

Giả sử template khai báo:

~~~yaml
Resources:
  WebSecurityGroup:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupDescription: HTTPS ingress only
      VpcId: vpc-0123456789abcdef0
      SecurityGroupIngress:
        - IpProtocol: tcp
          FromPort: 443
          ToPort: 443
          CidrIp: 203.0.113.0/24
~~~

Nếu Console thêm rule SSH TCP 22 từ `0.0.0.0/0`, drift detail có thể hiển thị property list khác biệt. Trước khi revert, kiểm tra incident/change record: có thể kỹ sư đã thêm rule để xử lý sự cố và quên rollback. Nếu rule không được phê duyệt, cập nhật template/stack về cấu hình an toàn đã được duyệt và kiểm tra rule thực tế đã biến mất sau update.

## 6. Import resource hiện có vào CloudFormation

Resource import dùng khi một AWS resource đã tồn tại nhưng chưa được quản lý bởi CloudFormation stack đích. Import giúp stack tiếp nhận ownership của resource mà không cần xóa rồi tạo lại. Không phải mọi resource type đều hỗ trợ import; phải kiểm tra resource identifier và support matrix trước khi lập change set.

### 6.1. Chuẩn bị trước khi import

1. Inventory resource: account, Region, ARN/physical ID, tags, dependencies và business owner.
2. Xác nhận resource chưa thuộc một CloudFormation stack khác trong cùng Region.
3. Kiểm tra resource type có hỗ trợ import và xác định identifier property.
4. Thu thập actual configuration từ AWS API/Console/Config.
5. Viết template có resource logical ID mới hoặc đúng logical ID cần quản lý; properties phải phản ánh actual configuration.
6. Đặt `DeletionPolicy` cho resource được import. `Retain` thường là lựa chọn thận trọng khi tiếp nhận resource có dữ liệu; lựa chọn policy cuối cùng phải phù hợp lifecycle.
7. Tạo change set loại `IMPORT`, review kỹ rồi mới execute.
8. Sau khi import thành công, chạy drift detection và điều chỉnh template để khớp actual.

**Import operation không phải stack update thông thường.** Trong cùng một import operation, CloudFormation không cho tạo resource mới, xóa resource khác hoặc thay đổi cấu hình properties của resource. Hãy import trước; sau đó tạo một change set update riêng cho các thay đổi mong muốn.

### 6.2. Ví dụ import một S3 bucket

Giả sử stack `audit-storage` đã tồn tại, còn bucket `company-audit-logs-prod` được tạo thủ công, hiện có dữ liệu và chưa thuộc stack nào. Template tối thiểu cần khai báo resource và policy phù hợp:

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: Adopt an existing audit bucket into CloudFormation

Resources:
  AuditLogsBucket:
    Type: AWS::S3::Bucket
    DeletionPolicy: Retain
    Properties:
      BucketName: company-audit-logs-prod
      VersioningConfiguration:
        Status: Enabled
~~~

Ví dụ trên chỉ minh họa cấu trúc. Trước khi import, template phải khớp với các properties thực tế mà CloudFormation sẽ quản lý; không giả định bucket đã bật versioning nếu chưa xác minh.

Tạo file `resources-to-import.json`:

~~~json
[
  {
    "ResourceType": "AWS::S3::Bucket",
    "LogicalResourceId": "AuditLogsBucket",
    "ResourceIdentifier": {
      "BucketName": "company-audit-logs-prod"
    }
  }
]
~~~

Tạo import change set:

~~~bash
aws cloudformation create-change-set \
  --stack-name audit-storage \
  --change-set-name adopt-audit-bucket \
  --change-set-type IMPORT \
  --template-body file://template.yaml \
  --resources-to-import file://resources-to-import.json
~~~

Xem change set trước khi execute:

~~~bash
aws cloudformation describe-change-set \
  --stack-name audit-storage \
  --change-set-name adopt-audit-bucket

aws cloudformation execute-change-set \
  --stack-name audit-storage \
  --change-set-name adopt-audit-bucket
~~~

Nếu template có IAM resources cần capability, thêm capability tương ứng sau khi review quyền tạo/cập nhật IAM. Theo dõi stack events đến khi import operation hoàn tất (`IMPORT_COMPLETE`) hoặc rollback/failure.

### 6.3. Kiểm tra sau import

~~~bash
aws cloudformation detect-stack-drift \
  --stack-name audit-storage

aws cloudformation describe-stack-resource-drifts \
  --stack-name audit-storage
~~~

Nếu resource vừa import hiển thị `MODIFIED`, template chưa mô tả đúng actual configuration trong các properties được kiểm tra. Sửa template để phản ánh actual state trước, hoặc lập kế hoạch update resource thực tế sau import. Không thực hiện một update mù quáng có thể làm mất dữ liệu hoặc thay đổi security posture.

### 6.4. Import nhiều resource và auto-import

CloudFormation có thể import nhiều resource trong một operation nếu tất cả resource types/identifiers đáp ứng yêu cầu. Một số named resources còn hỗ trợ auto-import khi tạo hoặc update stack. Auto-import không loại bỏ việc review: cần kiểm tra identifier uniqueness, template, stack ownership và drift sau import.

### 6.5. Các giới hạn cần nhớ

- Resource type phải hỗ trợ import tại Region hiện tại.
- Mỗi resource được import cần `DeletionPolicy`.
- Không import cùng một resource vào nhiều stack trong cùng Region.
- Import không tự khám phá và viết đầy đủ template cho mọi thuộc tính; có thể dùng IaC generator làm điểm khởi đầu nếu resource type được hỗ trợ, nhưng phải review.
- Stack quotas và resource identifier format vẫn áp dụng.
- Import không chuyển ownership của resource liên quan một cách tự động; dependencies/attachments cần được đánh giá riêng.


## 7. Terraform drift detection và refresh-only mode

Terraform có một cơ chế khác CloudFormation. Trong normal `terraform plan`, Terraform refresh các resource đang được quản lý bằng cách gọi provider đọc actual state, cập nhật state **trong bộ nhớ**, rồi so sánh với configuration để lập execution plan. Nếu resource bị thay đổi ngoài Terraform, plan có thể hiển thị thông báo như `Objects have changed outside of Terraform` và đề xuất hành động cần thiết để đưa actual infrastructure về configuration.

### 7.1. Normal plan phát hiện drift

~~~bash
terraform init
terraform plan
~~~

Ví dụ: Terraform state trước đó ghi Security Group có ingress TCP 443. Kỹ sư thêm ingress TCP 22 trên Console. Normal plan refresh trạng thái hiện tại và so với HCL; nếu cấu hình HCL vẫn chỉ cho 443, plan có thể đề xuất xóa rule TCP 22.

Plan chỉ trình bày thay đổi dự kiến; **`terraform plan` không thực thi thay đổi lên AWS**. Không bỏ qua phần `Plan:` hoặc resource actions khi review.

### 7.2. Refresh-only plan

~~~bash
terraform plan -refresh-only
~~~

Refresh-only mode tạo plan có mục tiêu cập nhật Terraform state và root module outputs theo thay đổi thực tế bên ngoài Terraform. Nó cho phép review những thay đổi state trước khi ghi chúng.

Nếu quyết định chấp nhận actual configuration hiện tại vào state:

~~~bash
terraform apply -refresh-only
~~~

Lệnh trên cập nhật state/output; nó **không chỉnh sửa resource trên AWS**. Tuy nhiên, HCL vẫn giữ cấu hình mong muốn cũ. Vì vậy normal plan tiếp theo có thể đề xuất thay đổi actual infrastructure để khớp HCL. Nếu thay đổi ngoài mã là vĩnh viễn và được duyệt, hãy cập nhật HCL trước/sau refresh theo quy trình review để source of truth phản ánh quyết định.

### 7.3. Không nhầm refresh-only với remediation

| Lệnh/chế độ | State | Actual infrastructure | Mục đích |
|---|---|---|---|
| `terraform plan` | Refresh trong memory | Không đổi | Phát hiện drift và preview reconcile |
| `terraform plan -refresh-only` | Tính toán state update, chưa lưu | Không đổi | Review thay đổi state |
| `terraform apply -refresh-only` | Ghi state theo actual | Không đổi | Chấp nhận actual vào state |
| `terraform apply` normal mode | Ghi state sau apply | Có thể thay đổi | Đưa resource về HCL |
| `terraform plan -refresh=false` | Bỏ qua refresh | Không đổi | Chế độ đặc biệt; có thể bỏ sót drift |

Không dùng `-refresh=false` như cách “làm plan sạch”. Nó có thể khiến Terraform bỏ qua thay đổi ngoài mã và tạo execution plan không đầy đủ. `terraform refresh` là lệnh cũ đã deprecated; ưu tiên refresh-only mode để review trước khi ghi state.

### 7.4. Đọc drift trong plan

Giả sử plan có dạng rút gọn:

~~~text
Note: Objects have changed outside of Terraform

  # aws_security_group.web has changed
  ~ resource "aws_security_group" "web" {
        id = "sg-0123456789abcdef0"
      ~ ingress = [
          + {
              from_port   = 22
              to_port     = 22
              protocol    = "tcp"
              cidr_blocks = ["0.0.0.0/0"]
            },
        ]
    }

Plan: 0 to add, 1 to change, 0 to destroy.
~~~

Dấu `+` ở phần drift minh họa property xuất hiện trên actual resource. Cần xem toàn bộ plan: nếu Terraform đề xuất xóa rule, xác nhận đó là hành động mong muốn và không phá vỡ incident mitigation hoặc service dependency.

### 7.5. Drift trong HCP Terraform

HCP Terraform có health assessments cho workspace (phụ thuộc edition/tính năng). Drift detection có thể chạy refresh-only plans không hành động để so sánh resource actual với state. Assessment cho biết drift; nó không tự cập nhật state hoặc infrastructure. Có thể dùng scheduled assessments, workspace notifications và policy checks để đưa drift vào quy trình vận hành.

## 8. Import resource hiện có vào Terraform

Terraform import đưa một remote object vào Terraform state tại một resource address. Để quản lý lifecycle về sau, cần có resource configuration tương ứng. Import không tự biến mọi cấu hình thực tế thành HCL hoàn chỉnh; sau import, phải review `terraform plan` để xác nhận không có thay đổi ngoài ý muốn.

### 8.1. Chuẩn bị

1. Xác định provider/account/Region và resource identifier theo tài liệu provider.
2. Kiểm tra resource có hỗ trợ import; không phải mọi resource types đều importable.
3. Xác nhận object chưa được quản lý trong state khác hoặc Terraform address khác.
4. Viết resource block mô tả resource và dependencies.
5. Chuẩn bị remote backend/state lock; backup state theo quy trình bảo mật.
6. Import vào một address duy nhất.
7. Chạy `terraform state show` và `terraform plan`.
8. Chỉnh HCL để khớp actual, hoặc review plan để chủ động reconcile actual về desired.

### 8.2. Declarative import block (Terraform 1.5+)

Ví dụ bucket S3 đã tồn tại:

~~~hcl
import {
  to = aws_s3_bucket.audit_logs
  id = "company-audit-logs-prod"
}

resource "aws_s3_bucket" "audit_logs" {
  bucket = "company-audit-logs-prod"
}
~~~

Chạy:

~~~bash
terraform init
terraform plan
terraform apply
terraform state show aws_s3_bucket.audit_logs
terraform plan
~~~

Import block khai báo resource address đích và ID của object. `terraform plan` hiển thị import action để review; `terraform apply` thực hiện import vào state. Sau khi import, giữ import block như lịch sử declarative adoption hoặc xóa theo repository convention sau khi import đã được xác nhận và state đã lưu ổn định.

### 8.3. CLI import một resource

Có thể dùng lệnh truyền thống:

~~~hcl
resource "aws_s3_bucket" "audit_logs" {
  bucket = "company-audit-logs-prod"
}
~~~

~~~bash
terraform import \
  aws_s3_bucket.audit_logs \
  company-audit-logs-prod
~~~

CLI import ghi binding vào state cho resource address. Nó **không tự viết resource block**; phải chuẩn bị HCL trước. Với cách CLI, lệnh import gọi provider và cập nhật state trực tiếp, nên phải kiểm tra workspace/backend/Region trước khi chạy.

### 8.4. Sau import: state show và plan

~~~bash
terraform state show aws_s3_bucket.audit_logs
terraform plan
~~~

Nếu plan đề xuất thay đổi versioning, encryption, policy, lifecycle hoặc bucket settings, dừng lại để review. Có thể:

- Cập nhật HCL để phản ánh actual configuration đã được duyệt.
- Giữ HCL như desired state và áp dụng thay đổi có kiểm soát để reconcile resource.
- Tách các settings thành resource blocks độc lập theo AWS provider schema (ví dụ bucket versioning, encryption, ownership controls), import từng remote object/address nếu provider model yêu cầu.

Một resource provider abstraction có thể quản lý một phần thuộc tính hoặc một remote object khác nhau; đọc docs của đúng provider version để tránh hai resource blocks cùng quản lý một thuộc tính.

### 8.5. Import nhiều resource

Import blocks hỗ trợ `for_each` để khai báo batch imports khi có map/set identifiers. Với inventory lớn, có thể dùng Terraform query/bulk import features nếu provider và workflow hỗ trợ. Không import hàng trăm resources trước khi thử một resource đại diện và xác minh provider IDs, generated configuration, dependencies và plan behavior.

### 8.6. One-to-one mapping và lỗi phổ biến

Terraform kỳ vọng một remote object được bind với **một resource address duy nhất** trong state. Import cùng object vào hai address hoặc hai workspace tạo ownership conflict; một pipeline có thể thay đổi/xóa resource mà workspace còn lại vẫn quản lý.

Các lỗi thường gặp:

- Dùng sai ID format; mỗi provider resource có import ID riêng.
- Resource block không khai báo required arguments.
- Provider alias/account/Region sai.
- Resource đã có trong state hoặc bị workspace khác quản lý.
- Provider version khác làm schema/attributes thay đổi.
- Plan sau import đề xuất replacement vì immutable argument không khớp.
- Import resource cha nhưng bỏ sót dependencies hoặc attachment resources.

## 9. Bảo vệ state và ownership khi import/reconcile

Terraform state là mapping giữa resource address và remote object identity. Nó cũng chứa attributes và metadata provider; một số state values có thể chứa secrets. State là dữ liệu vận hành nhạy cảm, không phải file cache có thể xóa hoặc sửa tùy ý.

### 9.1. Remote state, locking và backup

- Dùng remote backend hoặc HCP Terraform để team cùng dùng một state nhất quán.
- Chọn backend hỗ trợ state locking; Terraform tự lock các operation có thể ghi state nếu backend hỗ trợ.
- Không dùng `-lock=false` trong workflow team chỉ để vượt qua lock contention.
- Backup state trước các thao tác migration/import/state surgery; lưu backup ở nơi có encryption và access control.
- Không commit `terraform.tfstate`, state backup hoặc plan file có thể chứa sensitive values vào Git.
- Không chỉnh JSON state trực tiếp. Dùng `terraform state` commands được hỗ trợ.
- Chỉ dùng `terraform force-unlock` khi xác minh lock thuộc operation của mình đã thất bại và lock ID khớp; force unlock khi người khác đang apply có thể làm hỏng state.

### 9.2. Đọc và lưu state có kiểm soát

~~~bash
# Hiển thị resources trong state.
terraform state list

# Đọc attributes của một resource.
terraform state show aws_s3_bucket.audit_logs

# Pull state ra stdout để backup trong quy trình được bảo vệ.
terraform state pull
~~~

State pull có thể in dữ liệu nhạy cảm. Nếu lưu ra file, dùng thư mục hạn chế quyền truy cập, encryption và retention policy; không gửi file qua chat hoặc commit vào repository.

### 9.3. Phân biệt state rm, state mv và import

| Lệnh | Tác dụng với state | Tác dụng trực tiếp lên AWS |
|---|---|---|
| `terraform state rm ADDRESS` | Bỏ binding resource khỏi state | Không xóa remote object |
| `terraform state mv SOURCE DEST` | Chuyển binding sang address mới | Không tạo/xóa remote object |
| `terraform import ADDRESS ID` | Tạo binding cho object hiện có | Không tạo resource mới |
| `terraform apply` normal | Cập nhật state theo apply | Có thể create/update/delete resource |

`terraform state rm` không phải lệnh xóa resource; sau khi bỏ binding, resource trở thành unmanaged đối với workspace đó. Nếu sau này vẫn cần quản lý, phải import vào đúng address khác hoặc khôi phục binding. Dùng `state mv` khi refactor/rename address trong cùng state để tránh Terraform hiểu resource cũ bị xóa và resource mới cần tạo.

### 9.4. Không để hai workspace cùng sở hữu resource

Trước khi chuyển ownership giữa workspaces:

1. Freeze pipeline apply ở cả hai workspace.
2. Backup cả hai state và xác minh resource address/physical ID.
3. Xác nhận target workspace đã có HCL/provider/dependencies đúng.
4. Thực hiện state move/import theo quy trình migration đã review.
5. Kiểm tra `terraform plan` ở cả hai workspace; workspace nguồn không được đề xuất destroy resource đã bàn giao.
6. Ghi nhận owner mới và mở lại pipeline.

Không chạy import trước khi xác nhận binding cũ đã được xử lý. Việc import cùng remote object vào hai state không tự tạo coordination giữa chúng.

## 10. Quản lý thay đổi ngoài mã trong production

Không phải mọi out-of-band change đều sai. Khi production incident xảy ra, kỹ sư có thể cần thay đổi nhanh một Security Group, scale capacity hoặc điều chỉnh route để khôi phục dịch vụ. Rủi ro xuất hiện khi thay đổi không được ghi nhận, không có thời hạn và không được đưa về IaC source of truth.

### 10.1. Phân loại thay đổi

| Loại thay đổi | Ví dụ | Hành động |
|---|---|---|
| Emergency break-glass | Mở rule tạm để khôi phục kết nối | Ghi incident, actor, phạm vi và expiry; review sau incident |
| Approved permanent change | Tăng DB storage vì growth | Sửa IaC qua PR và deploy có review |
| Accidental change | Tắt encryption hoặc xóa route nhầm | Khôi phục desired state, đánh giá impact |
| Service-managed change | ECS task/ASG instance thay đổi theo controller | Đánh giá đúng abstraction; không cố pin ephemeral state |
| Unmanaged creation | Tạo S3 bucket/queue qua Console | Xác định owner; import hoặc chuyển sang data/reference model |
| Third-party automation | Security tool tự gắn policy/tag | Phân định field ownership và integration contract |

### 10.2. Break-glass workflow

Một workflow khẩn cấp nên có:

1. Role break-glass riêng, MFA/short-lived session và quyền giới hạn theo incident.
2. Ticket/incident ID, người thực hiện, resource ARN, Region/account và lý do.
3. Ghi nhận before/after configuration hoặc CloudTrail event.
4. Xác định thời hạn của thay đổi tạm thời (TTL) và người chịu trách nhiệm rollback.
5. Thông báo cho IaC owner để không có pipeline apply đồng thời.
6. Sau khi ổn định, quyết định revert hoặc codify thay đổi đã được duyệt.
7. Chạy drift detection/plan và đóng incident khi actual, code và state đã hội tụ.

Không coi “đã xử lý xong incident” là hoàn tất change management. Nếu thay đổi tạm thời không thể rollback ngay, tạo exception có expiry, compensating control và owner rõ ràng.

### 10.3. Chỉ một đường triển khai thường lệ

Production changes nên đi qua pipeline IaC với PR, code review, policy checks, plan/change set và approval. Console/CLI access vẫn có thể cần cho read-only troubleshooting và break-glass; quyền ghi trực tiếp nên được giới hạn, giám sát và audit theo risk.

## 11. AWS Config và CloudTrail bổ sung cho drift detection

Drift detection của CloudFormation/Terraform tập trung vào resources mà stack/state quản lý. Nó không phải inventory toàn account và không phát hiện mọi resource được tạo thủ công. Hai dịch vụ AWS giúp mở rộng góc nhìn:

### 11.1. AWS Config

AWS Config ghi nhận resource configuration history và có thể đánh giá resource theo AWS Config Rules/conformance packs.

Dùng AWS Config để:

- Khám phá resource trong account/Region, kể cả unmanaged resources.
- Xem timeline/configuration changes và so sánh configuration items.
- Đánh giá compliance như S3 public access, encrypted volumes, restricted SSH hoặc required tags.
- Tổng hợp compliance/configuration nhiều account bằng aggregator.
- Phát hiện resource mới hoặc configuration không tuân thủ policy.

AWS Config rule đánh giá **compliance với rule**; nó không nhất thiết biết HCL/CloudFormation template mong muốn là gì. Vì vậy Config bổ sung cho IaC drift detection, không thay thế IaC plan/diff.

### 11.2. AWS CloudTrail

CloudTrail ghi lại API activity để hỗ trợ trả lời:

- Ai đã gọi API?
- Thời điểm nào?
- API action/resource nào bị thay đổi?
- Từ role/session, source IP hoặc user agent nào?
- Có liên quan tới incident, deployment hay automation nào?

Management events ghi nhận control-plane operations. Nếu cần audit object-level S3 access hoặc các data-plane operations khác, cấu hình data events phù hợp; không giả định mọi data event đều được ghi mặc định. Event history, trail và Lake có phạm vi/retention/cost khác nhau.

### 11.3. Kết hợp tín hiệu

~~~mermaid
flowchart TD
    CFN["CloudFormation drift detection"] --> CORRELATE["Correlate by ARN / account / Region / time"]
    TF["Terraform plan -refresh-only"] --> CORRELATE
    CONFIG["AWS Config history / rules"] --> CORRELATE
    TRAIL["CloudTrail API events"] --> CORRELATE
    CORRELATE --> CASE["Incident / change record"]
    CASE --> OWNER["IaC owner investigates"]
    OWNER --> FIX["Codify / revert / import / exception"]
    FIX --> VERIFY["Re-run drift and compliance checks"]
~~~

Ví dụ: AWS Config báo Security Group không compliant với rule restricted SSH; CloudTrail cho biết một assumed role đã gọi `AuthorizeSecurityGroupIngress`; Terraform refresh-only plan hiển thị rule mới. Ba tín hiệu giúp xác định resource, thời điểm và owner để xử lý đúng.

## 12. Chọn cách remediation phù hợp

Khi drift được xác nhận, không có một lệnh “fix drift” đúng cho mọi tình huống. Quyết định dựa trên intent, security impact, owner, resource lifecycle và desired state.

### 12.1. Revert actual về IaC desired state

Dùng khi thay đổi ngoài mã không được phê duyệt hoặc chỉ là workaround đã hết hạn.

- Xác nhận rule/property hiện tại không còn cần cho incident hoặc service.
- Review Terraform plan hoặc CloudFormation change set.
- Kiểm tra resource có bị replacement, interruption, deletion hoặc data loss không.
- Apply qua pipeline có approval.
- Re-run drift detection và xác minh service health.

Ví dụ: Terraform HCL vẫn chỉ cho phép HTTPS. Sau khi xác nhận SSH rule không còn cần, normal plan sẽ đề xuất xóa rule ngoài mã. Review plan rồi apply theo change window.

### 12.2. Codify actual thành desired state

Dùng khi thay đổi ngoài mã là chủ đích, được phê duyệt và sẽ tồn tại lâu dài.

1. Thu thập actual configuration và lý do thay đổi.
2. Sửa template/HCL để mô tả trạng thái đã duyệt.
3. Mở PR kèm risk assessment và rollback plan.
4. Chạy plan/change set để đảm bảo không có thay đổi ngoài ý muốn.
5. Merge/deploy qua pipeline.
6. Re-run drift check để xác nhận source of truth đã khớp.

Nếu đã sửa actual trên Console trước khi cập nhật code, pipeline kế tiếp không nên bất ngờ rollback thay đổi đó. Hãy cập nhật code và review plan trước khi apply.

### 12.3. Import unmanaged resource

Dùng khi resource đã tồn tại, có owner rõ ràng và quyết định đưa vào IaC lifecycle. Trước khi import, xác minh resource type hỗ trợ, identifier, dependencies, state/stack hiện tại và one-to-one ownership. Nếu resource chỉ cần được tham chiếu, dùng data source/CloudFormation parameter hoặc output thay vì import ownership.

### 12.4. Chuyển ownership hoặc tách resource

Nếu resource hiện đang nằm trong stack/workspace sai, lập kế hoạch handover. Dừng concurrent applies, backup state, remove binding/ownership có kiểm soát và import vào owner đích. Đảm bảo owner cũ không còn đề xuất destroy resource.

### 12.5. Temporary exception có expiry

Có lúc chưa thể codify hoặc revert ngay. Khi đó exception phải có:

- Resource ARN, account/Region và properties đang khác.
- Business/incident reason và risk acceptance.
- Compensating control (ví dụ giới hạn source CIDR, monitoring bổ sung).
- Owner và người phê duyệt.
- Expiry/rollback date.
- Drift check frequency và cách đóng exception.

Không dùng Terraform `lifecycle.ignore_changes` hoặc bỏ property khỏi template chỉ để che drift. Chỉ dùng ignore/ownership delegation khi một controller khác thực sự được giao quản lý field đó; ghi rõ field, owner, lý do và test để tránh che mất thay đổi bảo mật.

### 12.6. Khi resource đã bị xóa ngoài mã

Nếu CloudFormation báo `DELETED` hoặc Terraform refresh cho thấy object không còn:

- Kiểm tra CloudTrail, AWS Config history và dependency graph để xác định ai/xóa khi nào.
- Xác minh resource có được cố ý decommission hay bị xóa nhầm.
- Nếu phải khôi phục, review plan/change set tạo lại resource; một số resource replacement sẽ sinh physical ID mới và cần cập nhật references/data restore.
- Nếu resource đã được retire, cập nhật IaC và downstream references theo change request; không giữ resource block chỉ để “xanh” detection.
- Không tạo lại database/storage resource mà chưa xác định backup, retention và data recovery requirements.

## 13. Phòng ngừa drift trong CI/CD và vận hành

Drift control hiệu quả cần kết hợp preventive controls và detective controls.

### 13.1. Preventive controls

- Dùng pipeline role chuyên dụng cho deploy IaC; giới hạn quyền ghi trực tiếp trên production Console/CLI.
- Dùng break-glass role riêng với MFA, session ngắn, alert và review sau incident.
- Yêu cầu PR review, plan/change set artifact và approval trước production apply.
- Dùng policy-as-code để chặn public storage, unrestricted SSH/RDP, unencrypted resources hoặc thiếu tags.
- Áp dụng AWS Organizations SCP/permission boundaries phù hợp; tránh deny quá rộng làm chặn cả IaC service role và incident response.
- Gắn owner, environment, cost-center, repository/workspace và support contact tags theo policy.
- Tách shared network/security/platform ownership khỏi application stack.
- Không cho script vận hành tự thay đổi property do IaC quản lý nếu không có contract/field ownership rõ.

### 13.2. Detective controls

- Lập lịch CloudFormation drift detection cho stacks quan trọng.
- Lập lịch Terraform refresh-only plans/health assessments cho workspaces quan trọng.
- Dùng AWS Config rules/conformance packs để kiểm tra compliance trên toàn account.
- Dùng CloudTrail/EventBridge để cảnh báo API write calls ngoài deployment roles.
- Theo dõi unmanaged resources, orphan resources và tag/owner coverage.
- Gửi kết quả về dashboard/ticket có account, Region, resource ARN, owner và timestamp.
- Đặt SLA xử lý theo severity: security drift nghiêm trọng cần xử lý nhanh hơn tag/cost metadata drift.

### 13.3. Terraform plan trong pipeline

Một bước kiểm tra có thể chạy:

~~~bash
terraform init -input=false
terraform validate
terraform plan -input=false -detailed-exitcode
~~~

`-detailed-exitcode` thường trả:

| Exit code | Ý nghĩa |
|---:|---|
| 0 | Plan không có thay đổi |
| 1 | Lỗi |
| 2 | Plan có thay đổi |

Exit code 2 không tự chứng minh drift: thay đổi có thể đến từ PR HCL. Pipeline phải phân biệt source change với scheduled drift assessment; dùng refresh-only plan hoặc HCP Terraform health assessment cho drift-focused checks.

Nếu lưu plan file để review/apply, bảo vệ file vì nó có thể chứa sensitive values và resource details. Không publish raw plan/state vào artifact công khai.

### 13.4. CloudFormation drift schedule

Có thể dùng EventBridge Scheduler hoặc pipeline định kỳ để gọi `detect-stack-drift`, theo dõi detection ID và lấy resource drift details. Tạo alert khi stack có `DRIFTED` hoặc detection fail. Đặt concurrency/rate limits, xử lý nested stacks riêng và chỉ chạy trên stack statuses được CloudFormation hỗ trợ.

### 13.5. Drift policy theo mức độ quan trọng

| Tier | Ví dụ | Kiểm tra gợi ý |
|---|---|---|
| Critical | IAM, KMS, public access, network perimeter, production data | Detection thường xuyên + Config/CloudTrail alerts |
| High | RDS, EKS, load balancer, production compute | Scheduled plan/drift assessment và PR approval |
| Standard | Non-production application resources | Scheduled assessment theo release/cadence |
| Low | Disposable sandbox resources | Cleanup/TTL và periodic inventory |

Cadence phải dựa trên blast radius, compliance và chi phí API calls. Drift detection không thay monitoring real-time hoặc security incident detection.

## 14. So sánh CloudFormation và Terraform

Hai công cụ có cùng mục tiêu quản lý desired state nhưng cách lưu ownership và phát hiện drift khác nhau.

| Nội dung | AWS CloudFormation | Terraform |
|---|---|---|
| Desired configuration | Stack template + parameters | HCL configuration |
| Recorded ownership | Stack resources/logical IDs | Resource addresses trong state |
| Drift detection | Detect stack/resource drift | Refresh provider state rồi tạo plan |
| Chỉ rõ drift | Drift status + expected/current properties | Plan output/refresh-only plan |
| Chấp nhận actual vào recorded state | Import/adopt resource hoặc cập nhật stack/template theo workflow | `apply -refresh-only` cập nhật state |
| Import unmanaged resource | Import change set, resource identifier, `DeletionPolicy` | Import block hoặc CLI `terraform import` |
| Xem thay đổi trước khi thực thi | Change set | Execution plan |
| Ownership uniqueness | Một resource không thể import vào nhiều stack trong cùng Region | Một remote object nên bind với một resource address |
| Coverage | Chỉ resource/property hỗ trợ drift detection | Phụ thuộc provider read/schema và resource implementation |
| State security | AWS quản lý stack metadata | Team/backend phải bảo vệ Terraform state |

### 14.1. Chọn tool theo workflow

- Dùng CloudFormation drift detection khi resource đã nằm trong CloudFormation stack và cần so sánh template với actual properties.
- Dùng Terraform plan/refresh-only khi resource được quản lý bởi Terraform state.
- Dùng AWS Config khi cần inventory/compliance trên nhiều resource, kể cả resource không nằm trong IaC.
- Dùng CloudTrail khi cần điều tra ai/role nào đã gọi API làm thay đổi resource.
- Dùng import khi resource chưa có IaC owner và tổ chức quyết định nhận ownership.

Không chạy import Terraform cho resource đang thuộc CloudFormation stack chỉ để “đưa vào Terraform”. Trước hết phải có kế hoạch handover ownership giữa hai hệ thống, bao gồm state/stack removal và rollback.

## 15. Runbook xử lý một drift incident

Ví dụ: production Security Group bất ngờ có SSH ingress từ Internet.

### 15.1. Contain và thu thập bằng chứng

1. Xác định account, Region, Security Group ID, VPC và workload liên quan.
2. Kiểm tra mức độ phơi nhiễm, source CIDR, port, thời điểm và traffic.
3. Lấy CloudTrail event, AWS Config timeline và incident context.
4. Xác định IaC owner (CloudFormation stack hoặc Terraform workspace) và trạng thái pipeline đang chạy.
5. Nếu nguy cơ cao, dùng incident procedure để hạn chế exposure; ghi nhận trước/sau khi sửa và thông báo IaC owner.

### 15.2. Review drift

Nếu CloudFormation sở hữu resource:

~~~bash
aws cloudformation detect-stack-resource-drift \
  --stack-name production-network \
  --logical-resource-id WebSecurityGroup

aws cloudformation describe-stack-resource-drifts \
  --stack-name production-network
~~~

Nếu Terraform sở hữu resource:

~~~bash
terraform plan -refresh-only
terraform plan
~~~

Lưu drift result/plan trong nơi được kiểm soát và gắn incident ID. Không chia sẻ plan/state có secrets qua kênh công khai.

### 15.3. Quyết định remediation

- Nếu rule SSH không được phê duyệt: restore approved configuration sau khi xác nhận không ảnh hưởng recovery.
- Nếu rule là workaround cần thiết: tạo exception có TTL/compensating control, rồi codify hoặc rollback trong change window.
- Nếu resource chưa có owner: inventory, xác định dependencies và import sau khi được chấp thuận.
- Nếu rule được security automation quản lý: làm rõ field ownership và tránh để hai controller tranh nhau ghi cùng property.

### 15.4. Verify và đóng incident

- Kiểm tra Security Group thực tế không còn rule ngoài ý muốn.
- Chạy lại drift detection/plan sau remediation.
- Xác nhận service health, application connectivity và security controls.
- Kiểm tra không còn pipeline apply hoặc automation sẽ đưa rule cũ trở lại.
- Ghi root cause, actor, timeline, corrective action, owner và prevention task.
- Đóng exception/ticket khi IaC, state và actual đã hội tụ.

## 16. Bài thực hành trên sandbox

### 16.1. Lab A — CloudFormation drift detection

1. Tạo stack sandbox với Security Group chỉ mở HTTPS từ CIDR test.
2. Dùng Console/CLI thêm một ingress rule tạm ngoài stack.
3. Chạy `detect-stack-drift` và lấy resource drift details.
4. Ghi lại expected/current property values và status.
5. Xóa rule ngoài mã hoặc cập nhật template theo quyết định.
6. Chạy detection lần nữa và xác nhận trạng thái phù hợp.

Không thực hiện thay đổi trên Security Group production hoặc resource đang phục vụ traffic thật.

### 16.2. Lab B — Import S3 bucket vào CloudFormation

1. Tạo bucket sandbox bằng AWS CLI/Console và xác minh cấu hình.
2. Tạo một CloudFormation stack đích đã tồn tại.
3. Viết template mô tả bucket và đặt `DeletionPolicy: Retain`.
4. Tạo resources-to-import file với đúng `ResourceType`, `LogicalResourceId`, `ResourceIdentifier`.
5. Tạo import change set, review rồi execute.
6. Chạy drift detection; điều chỉnh template nếu resource bị `MODIFIED`.
7. Xác minh stack quản lý bucket mà không tạo bucket mới hoặc mất object.

### 16.3. Lab C — Terraform refresh-only

1. Dùng Terraform tạo một Security Group sandbox.
2. Thay đổi một thuộc tính qua AWS Console.
3. Chạy `terraform plan` và đọc phần drift.
4. Chạy `terraform plan -refresh-only`, review state changes.
5. Thử `terraform apply -refresh-only` trong sandbox để thấy state thay đổi nhưng AWS resource giữ nguyên.
6. Chạy normal plan; giải thích vì sao Terraform có thể đề xuất đưa actual về HCL.
7. Reconcile theo một quyết định có chủ đích.

### 16.4. Lab D — Terraform import

1. Tạo một S3 bucket sandbox ngoài Terraform.
2. Viết HCL resource block và import block trỏ tới bucket name.
3. Chạy `terraform plan`, review import action rồi `terraform apply`.
4. Chạy `terraform state show` và `terraform plan`.
5. Điều chỉnh HCL cho khớp actual hoặc review changes để chủ động reconcile.
6. Xác minh bucket chỉ được quản lý bởi một workspace.

### 16.5. Lab E — Điều tra out-of-band change

Mô phỏng một API write call trên resource sandbox. Dùng CloudTrail để xác định principal/action/time, AWS Config để xem configuration timeline, rồi đối chiếu drift result với IaC owner. Viết change record nêu rõ revert hay codify, owner, expiry và cách verify.

## 17. Checklist review trước khi merge hoặc đóng drift ticket

### Ownership và inventory

- [ ] Đã xác định account, Region, resource ARN/physical ID?
- [ ] Đã xác định CloudFormation stack hoặc Terraform workspace owner?
- [ ] Resource có đang bị quản lý bởi IaC system khác không?
- [ ] Đã xác minh resource type/property hỗ trợ drift/import?
- [ ] Đã xác định dependency và blast radius?

### Detection và investigation

- [ ] Drift result/plan có timestamp mới?
- [ ] Đã phân biệt `NOT_CHECKED` với `IN_SYNC`?
- [ ] Đã xem expected/current property values?
- [ ] Đã kiểm tra AWS Config/CloudTrail và incident/change records?
- [ ] Đã xác định actor, intent và business owner?

### Remediation/import

- [ ] Quyết định revert, codify, import, handover hay exception có lý do?
- [ ] Terraform import có resource block, đúng ID và one-to-one binding?
- [ ] CloudFormation import có `DeletionPolicy`, đúng identifier và import change set?
- [ ] Import operation không kèm create/delete/property updates?
- [ ] Plan/change set không có replacement/deletion ngoài ý muốn?
- [ ] Temporary exception có owner, expiry và compensating control?
- [ ] State backup/locking/access control đã sẵn sàng?

### Verification và governance

- [ ] Changes được deploy qua approved workflow?
- [ ] Drift detection/plan đã chạy lại sau remediation?
- [ ] Actual resource, IaC code và state/stack đã hội tụ trong phạm vi kiểm tra?
- [ ] Service health/security posture được xác minh?
- [ ] CI/CD, AWS Config, CloudTrail alert và ownership tags phù hợp?
- [ ] Ticket/incident có root cause, evidence, owner và prevention action?

## 18. Câu hỏi tự đánh giá

1. Configuration drift là gì?
2. Desired configuration, recorded state và actual configuration khác nhau thế nào?
3. Unmanaged resource có phải luôn là drift không?
4. Vì sao một resource chỉ nên có một IaC owner?
5. CloudFormation drift detection so sánh những giá trị nào?
6. `IN_SYNC` có chứng minh mọi property đều được kiểm tra không?
7. `NOT_CHECKED` có nghĩa resource không bị drift không?
8. Vì sao CloudFormation chỉ detect property được khai báo tường minh?
9. Drift detection trên parent stack có tự bao gồm nested stack không?
10. Cần permissions nào để chạy CloudFormation drift detection?
11. Import resource vào CloudFormation cần `DeletionPolicy` không?
12. Import change set có thể đồng thời tạo resource mới hoặc thay đổi properties không?
13. Vì sao phải chạy drift detection sau CloudFormation import?
14. Terraform normal plan refresh state theo cách nào?
15. `terraform plan -refresh-only` khác normal plan ra sao?
16. `terraform apply -refresh-only` có sửa resource trên AWS không?
17. Vì sao normal plan sau refresh-only có thể đề xuất revert actual configuration?
18. Terraform CLI import có tự tạo HCL resource block không?
19. Terraform import block được hỗ trợ từ phiên bản nào?
20. Vì sao một remote object chỉ nên bind với một Terraform resource address?
21. `terraform state rm` có xóa remote resource không?
22. `terraform state mv` hữu ích trong tình huống nào?
23. Vì sao cần remote state và locking trong team?
24. AWS Config khác IaC drift detection ở điểm nào?
25. CloudTrail giúp điều tra out-of-band change như thế nào?
26. Khi nào nên codify actual configuration?
27. Khi nào nên revert actual về desired state?
28. Khi nào nên import resource thay vì dùng data source?
29. Vì sao không nên dùng `lifecycle.ignore_changes` để che drift?
30. Break-glass change cần ghi lại những thông tin nào?
31. Vì sao `-refresh=false` có thể làm plan không đầy đủ?
32. Những guardrails nào giúp giảm thay đổi ngoài mã?
33. Vì sao plan file và Terraform state cần được bảo vệ?
34. Drift detection có thay thế security monitoring real-time không?

### Định hướng đáp án

- **Drift:** Khác biệt giữa desired/recorded state và actual; unmanaged resource chưa có IaC owner.
- **CloudFormation:** So sánh actual với properties hỗ trợ được khai báo tường minh; import qua IMPORT change set, cần `DeletionPolicy`, rồi detect lại.
- **Terraform:** Normal plan refresh trong memory; refresh-only apply ghi state theo actual, không sửa AWS; import cần resource block và one-to-one binding.
- **Ownership:** Một remote object có một IaC owner; data source/reference dùng khi không nhận lifecycle ownership.
- **Governance:** CloudTrail điều tra actor/API, AWS Config cung cấp inventory/history/compliance; break-glass cần ticket, expiry, owner và reconciliation.
- **Remediation:** Revert, codify, import, handover hoặc exception tùy intent và impact; review plan/change set trước apply.

## 19. Tài liệu AWS và HashiCorp chính thức

1. [CloudFormation drift detection overview](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-stack-drift.html) — Drift concepts, status codes, limitations and permissions.
2. [Detect drift on an entire CloudFormation stack](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/detect-drift-stack.html) — Start and inspect stack drift operations.
3. [Detect drift on individual stack resources](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/detect-drift-resource.html) — Resource-level detection.
4. [CloudFormation resource type support](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/resource-import-supported-resources.html) — Import, drift detection and IaC generator support matrix.
5. [Import AWS resources into an existing CloudFormation stack](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/import-resources-manually.html) — Import requirements, DeletionPolicy and operation constraints.
6. [Import existing resources into a stack](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/resource-import-existing-stack.html) — Import workflow and CLI.
7. [Automatically import named resources](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/import-resources-automatically.html) — Auto-import support and requirements.
8. [AWS Config developer guide](https://docs.aws.amazon.com/config/latest/developerguide/WhatIsConfig.html) — Resource inventory, configuration history and rules.
9. [AWS CloudTrail user guide](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-user-guide.html) — API activity and audit trails.
10. [Terraform plan command](https://developer.hashicorp.com/terraform/cli/commands/plan) — Normal and refresh-only planning modes.
11. [Manage resource drift in Terraform](https://developer.hashicorp.com/terraform/tutorials/state/resource-drift) — Detect drift and inspect refresh-only plans.
12. [Terraform import overview](https://developer.hashicorp.com/terraform/language/import) — Import workflows and resource ownership.
13. [Terraform import block reference](https://developer.hashicorp.com/terraform/language/block/import) — Declarative import syntax and arguments.
14. [Import existing resources with Terraform CLI](https://developer.hashicorp.com/terraform/cli/import/usage) — CLI import workflow and one-to-one mapping.
15. [Terraform state](https://developer.hashicorp.com/terraform/language/state) — State purpose, security and object bindings.
16. [Terraform state locking](https://developer.hashicorp.com/terraform/language/state/locking) — Lock behavior and force-unlock cautions.
17. [Terraform state backends](https://developer.hashicorp.com/terraform/language/state/backends) — Remote state storage and locking.
18. [HCP Terraform drift and policy tutorial](https://docs.hashicorp.com/terraform/tutorials/cloud/drift-and-policy) — Health assessments and drift checks.

> **Ghi nhớ cuối bài:** Drift detection cho biết actual resource khác với cấu hình IaC trong phạm vi công cụ có thể kiểm tra. Import đưa resource chưa được quản lý vào một IaC owner. Terraform refresh-only cập nhật state, còn normal apply có thể thay đổi AWS; CloudFormation import cần import change set và `DeletionPolicy`. Mọi out-of-band change cần owner, lý do, audit evidence, expiry nếu tạm thời và bước reconciliation để mã, state và hạ tầng tiếp tục nhất quán.




