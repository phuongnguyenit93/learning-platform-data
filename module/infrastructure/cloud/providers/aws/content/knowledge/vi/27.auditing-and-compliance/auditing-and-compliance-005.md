# Config rule, conformance pack và tự động khắc phục

## Mục tiêu học tập

Sau bài học, bạn có thể giải thích cách AWS Config ghi nhận và đánh giá cấu hình tài nguyên; phân biệt managed/custom rule và detective/proactive evaluation; thiết kế conformance pack cho một tài khoản, Region hoặc AWS Organization; cấu hình Systems Manager Automation để khắc phục tài nguyên NON_COMPLIANT; và vận hành remediation với IAM tối thiểu, retry, giới hạn concurrency cùng cơ chế theo dõi.

## 1. Bài toán và vai trò của từng thành phần

Một tổ chức có thể yêu cầu S3 bucket chặn truy cập công khai, EBS volume phải mã hóa, security group không mở SSH cho toàn Internet và IAM password policy phải đạt độ dài tối thiểu. Nếu chỉ kiểm tra thủ công theo quý, cấu hình sai có thể tồn tại nhiều tuần trước khi được phát hiện.

AWS Config ghi nhận trạng thái cấu hình của tài nguyên AWS và đánh giá trạng thái đó theo các quy tắc. Khi rule phát hiện vi phạm, đội vận hành có thể điều tra, tạo ticket, khắc phục thủ công hoặc gọi quy trình tự động bằng Systems Manager Automation.

Trong hệ sinh thái AWS, Config kết hợp với IAM để giới hạn quyền, S3 để lưu lịch sử, Lambda cho custom evaluation, Systems Manager để remediation và Organizations để áp dụng baseline nhiều tài khoản. CloudTrail bổ sung dấu vết API, còn CloudWatch hỗ trợ quan sát workflow. Các thành phần này giúp đội nền tảng triển khai kiểm soát an toàn, theo dõi trạng thái và giảm thời gian khắc phục.

| Thành phần | Vai trò |
|---|---|
| AWS Config rule | Mô tả điều kiện để tài nguyên được xem là tuân thủ |
| Conformance pack | Đóng gói nhiều rule và remediation thành một đơn vị triển khai |
| Remediation action | Thực thi các bước sửa cấu hình cho tài nguyên không tuân thủ |
| Systems Manager Automation | Chạy runbook để thực hiện hành động khắc phục |

Ví dụ, rule **s3-bucket-public-read-prohibited** phát hiện bucket cho phép public read. Một conformance pack có thể gom rule này với các rule về mã hóa, versioning và logging. Remediation action có thể gọi SSM Automation runbook để bật S3 Block Public Access sau khi tổ chức xác nhận hành động phù hợp với bucket.

AWS Config là lớp đánh giá trạng thái. Systems Manager Automation là lớp thực thi thay đổi. Việc tách hai trách nhiệm giúp tổ chức thay đổi cách xử lý mà vẫn giữ nguyên logic phát hiện.

## 2. Luồng hoạt động tổng thể

1. Configuration recorder ghi nhận cấu hình của các loại tài nguyên được chọn trong một Region.
2. AWS Config tạo configuration item khi tài nguyên được tạo, thay đổi hoặc xóa.
3. AWS Config rule được kích hoạt theo trigger đã cấu hình và đánh giá configuration item.
4. Rule trả về COMPLIANT, NON_COMPLIANT, ERROR hoặc NOT_APPLICABLE.
5. Nếu có remediation, AWS Config chuyển tham số cho Systems Manager Automation.
6. Automation assume IAM role được chỉ định và chạy các bước trong SSM document.
7. AWS Config ghi nhận cấu hình mới và đánh giá lại tài nguyên.
8. Đội vận hành theo dõi lịch sử, lỗi, ngoại lệ và xu hướng tuân thủ.

~~~mermaid
flowchart TD
    A["AWS resources"] --> B["AWS Config recorder"]
    B --> C["Configuration items"]
    C --> D["AWS Config rules"]
    D --> E{"Evaluation result"}
    E -->|COMPLIANT| F["Keep monitoring"]
    E -->|NON_COMPLIANT| G["Compliance finding"]
    G --> H{"Remediation mode"}
    H -->|Manual| I["Operator starts runbook"]
    H -->|Automatic| J["AWS Config starts Automation"]
    I --> K["SSM Automation document"]
    J --> K
    K --> L["Automation assume role"]
    L --> M["Change AWS resource"]
    M --> N["New configuration item"]
    N --> D
~~~

Một rule chỉ phát hiện và báo trạng thái. Remediation mới là phần thực hiện thay đổi. Kết quả NON_COMPLIANT không có nghĩa tài nguyên đã được sửa.

## 3. Configuration recorder và phạm vi ghi nhận

AWS Config chỉ đánh giá được cấu hình mà dịch vụ có thể quan sát và ghi nhận. Configuration recorder xác định loại tài nguyên được ghi nhận trong một tài khoản và Region. Configuration item lưu trạng thái cấu hình của một tài nguyên tại một thời điểm, gồm thuộc tính, metadata và quan hệ liên quan.

Nếu recorder không ghi loại tài nguyên **AWS::EC2::Volume**, rule kiểm tra EBS encryption không có đủ dữ liệu để đánh giá volume trong Region đó. Tạo rule thành công không chứng minh recorder đã được thiết lập đúng.

Trước khi triển khai rule hoặc pack, hãy xác minh:

- AWS Config đã được bật trong từng Region cần quản lý.
- Recorder đang chạy và bao gồm loại tài nguyên mà rule cần kiểm tra.
- IAM role của AWS Config có quyền đọc cấu hình cần thiết.
- Delivery channel và S3 bucket lưu lịch sử/snapshot được cấu hình.
- Tổ chức hiểu chi phí ghi nhận và đánh giá tài nguyên.

Có thể ghi nhận tất cả loại tài nguyên được hỗ trợ hoặc chỉ một tập loại tài nguyên. Ghi nhận toàn bộ giúp giảm nguy cơ bỏ sót rule nhưng có thể tăng chi phí. Ghi nhận có chọn lọc giúp kiểm soát chi phí nhưng cần quản lý ma trận giữa rule và resource type.

Để báo cáo trạng thái compliance chính xác, cần ghi nhận resource type **AWS::Config::ResourceCompliance**. Nếu muốn lưu lịch sử thay đổi trạng thái của conformance pack theo timeline, có thể ghi nhận thêm **AWS::Config::ConformancePackCompliance**; AWS Config cung cấp việc ghi nhận resource type này mà không tính thêm phí.

AWS Config hoạt động theo Region. Recorder tại **ap-southeast-1** không tự động ghi nhận tài nguyên trong **ap-southeast-2**. Với môi trường nhiều Region, cần bật recorder và triển khai rule hoặc pack tại từng Region cần kiểm soát.

## 4. AWS Config rule

Một rule thường gồm source, scope, trigger, input parameters và evaluation mode. Một số rule còn được liên kết với remediation action.

| Thành phần | Ý nghĩa | Câu hỏi thiết kế |
|---|---|---|
| Source | Managed rule hoặc custom logic | Dùng rule có sẵn hay tự định nghĩa? |
| Scope | Loại tài nguyên, ID hoặc tag được đánh giá | Tài nguyên nào thuộc phạm vi? |
| Trigger | Sự kiện làm rule chạy | Chạy khi thay đổi hay theo chu kỳ? |
| Input parameters | Ngưỡng hoặc giá trị kỳ vọng | Giá trị nào là chuẩn của tổ chức? |
| Evaluation mode | Detective hoặc proactive | Đánh giá tài nguyên đã tồn tại hay cấu hình dự kiến? |
| Remediation | SSM Automation document được liên kết | Có hành động sửa thủ công hoặc tự động không? |

Ví dụ, rule kiểm tra EBS encryption có thể áp dụng cho mọi EBS volume được ghi nhận trong Region. Rule kiểm tra tag có thể giới hạn scope vào tài nguyên có tag **Environment=Production**. Giới hạn scope giúp giảm đánh giá không cần thiết và tránh áp dụng chính sách ngoài phạm vi.

### 4.1 Managed rules

Managed rules là rule định nghĩa sẵn do AWS cung cấp. Bạn chọn rule, cấu hình tham số và phạm vi phù hợp.

| Rule | Mục đích |
|---|---|
| **s3-bucket-public-read-prohibited** | Phát hiện S3 bucket cho phép public read |
| **s3-bucket-public-write-prohibited** | Phát hiện S3 bucket cho phép public write |
| **s3-bucket-server-side-encryption-enabled** | Kiểm tra default encryption của S3 bucket |
| **encrypted-volumes** | Kiểm tra EBS volume có được mã hóa |
| **restricted-ssh** | Phát hiện security group cho phép SSH từ phạm vi không mong muốn |
| **iam-password-policy** | Kiểm tra thuộc tính IAM password policy |
| **access-keys-rotated** | Kiểm tra tuổi IAM access key theo ngưỡng |

Managed rule phù hợp khi điều kiện kiểm tra gần với yêu cầu của tổ chức. Ví dụ, **access-keys-rotated** nhận tham số tuổi tối đa. Nếu tổ chức yêu cầu access key không quá 60 ngày, bạn đặt tham số tương ứng thay vì viết lại logic đánh giá.

Hãy đọc tài liệu của rule trước khi triển khai: resource type, tham số bắt buộc, trigger, Region availability và giới hạn.

### 4.2 Custom rules

Khi managed rule không mô tả đủ chính sách, có thể tạo custom rule theo hai hướng:

- **Custom Policy rule với CloudFormation Guard:** biểu diễn điều kiện dưới dạng policy-as-code, phù hợp với kiểm tra thuộc tính cấu hình theo cấu trúc.
- **Custom Lambda rule:** dùng Lambda cho logic cần xử lý phức tạp hoặc tích hợp dữ liệu khác. Lambda trả kết quả đánh giá về AWS Config bằng API tương ứng.

Ví dụ Guard rule kiểm tra Point-in-Time Recovery của DynamoDB table:

~~~guard
let status = ['ACTIVE']

rule table_is_active when
    resourceType == "AWS::DynamoDB::Table" {
    configuration.tableStatus == %status
}

rule check_pitr when
    resourceType == "AWS::DynamoDB::Table"
    table_is_active {
    let pitr = supplementaryConfiguration.ContinuousBackupsDescription.pointInTimeRecoveryDescription.pointInTimeRecoveryStatus
    %pitr == "ENABLED" <<DynamoDB tables must have Point-in-Time Recovery enabled>>
}
~~~

Guard rule cần dùng đúng cấu trúc configuration và supplementaryConfiguration mà AWS Config cung cấp cho resource type. Hãy kiểm tra schema và ví dụ của loại tài nguyên trước khi triển khai policy.

Với custom Lambda rule, Lambda cần xử lý sự kiện đánh giá, xác định resource cần kiểm tra, trả evaluation result hợp lệ và sử dụng result token do AWS Config cung cấp. Lambda execution role cần quyền tối thiểu. Nếu rule gọi dịch vụ khác, hãy xem xét timeout, retry, concurrency và lỗi phụ thuộc.

Ưu tiên managed rule khi điều kiện đã có sẵn và có thể cấu hình bằng tham số. Chọn Guard khi policy đơn giản, cần review trong mã nguồn. Chọn Lambda khi cần logic tùy biến hoặc tích hợp dữ liệu ngoài. Custom rule làm tăng trách nhiệm bảo trì mã, runtime, IAM, logging và kiểm thử.

## 5. Trigger và evaluation mode

### Trigger

AWS Config hỗ trợ các kiểu trigger chính:

| Trigger | Cách hoạt động | Khi nên dùng |
|---|---|---|
| Configuration changes | Đánh giá khi tài nguyên phù hợp scope thay đổi | Phát hiện cấu hình sai sau khi tạo hoặc cập nhật |
| Periodic | Đánh giá theo chu kỳ được cấu hình | Kiểm tra lại điều kiện theo lịch |
| Hybrid | Kết hợp configuration changes và periodic | Cần phản ứng nhanh và kiểm tra định kỳ bổ sung |

Configuration change trigger có thể giới hạn theo resource type, resource ID, tag key/value hoặc mọi tài nguyên được ghi nhận. Periodic trigger hữu ích khi logic cần chạy lại dù không có configuration item mới. Chu kỳ càng ngắn thì số lần đánh giá có thể càng cao; cần cân bằng độ trễ phát hiện và chi phí.

Không nên mặc định mọi rule đều cần periodic. Một rule kiểm tra cấu hình bucket có thể chạy theo configuration change. Chỉ dùng periodic khi trigger đó được hỗ trợ và có nhu cầu kiểm tra theo lịch.

### Detective evaluation

Detective evaluation kiểm tra tài nguyên đã được triển khai. AWS Config đọc configuration item đã ghi nhận rồi so sánh với rule.

Ví dụ: security group đã tồn tại và mở TCP/22 cho **0.0.0.0/0**; AWS Config ghi nhận thay đổi; rule **restricted-ssh** đánh giá security group và trả NON_COMPLIANT nếu cấu hình vi phạm.

Đây là chế độ chính để theo dõi cấu hình đang tồn tại trong tài khoản.

### Proactive evaluation

Proactive evaluation kiểm tra thuộc tính dự kiến trước khi tài nguyên được triển khai. Ứng dụng hoặc pipeline gửi cấu hình dự kiến để AWS Config đánh giá xem cấu hình đó có đáp ứng proactive rules được bật trong tài khoản và Region hay không.

Proactive evaluation phù hợp với Infrastructure as Code. Ví dụ, pipeline kiểm tra cấu hình subnet trước khi triển khai để biết cấu hình đó có thể bị đánh giá NON_COMPLIANT hay không.

Có hai giới hạn cần nhớ:

1. Chỉ rule và resource type hỗ trợ proactive evaluation mới tham gia được.
2. Proactive evaluation không tự chặn triển khai và không tự khắc phục tài nguyên bị đánh giá NON_COMPLIANT.

Muốn dùng proactive evaluation như deployment gate, pipeline phải đọc kết quả và chủ động dừng bước triển khai khi kết quả không đạt yêu cầu. Không nên giả định bật proactive evaluation sẽ tự động chặn CloudFormation hoặc Terraform.

## 6. Đọc kết quả đánh giá

Một AWS Config rule có thể trả về các trạng thái sau:

| Trạng thái | Ý nghĩa | Hành động tiếp theo |
|---|---|---|
| COMPLIANT | Tài nguyên đáp ứng điều kiện của rule | Tiếp tục theo dõi |
| NON_COMPLIANT | Tài nguyên không đáp ứng điều kiện | Điều tra và khắc phục |
| ERROR | Tham số không hợp lệ, sai kiểu hoặc sai định dạng | Sửa cấu hình rule hoặc logic |
| NOT_APPLICABLE | Logic rule không áp dụng cho tài nguyên đó | Kiểm tra scope và loại tài nguyên |

ERROR thường cho biết rule không thể đánh giá đúng vì tham số hoặc cấu hình; không nên coi đây là một vi phạm bảo mật. NOT_APPLICABLE cũng không có nghĩa tài nguyên đã vượt qua kiểm tra, mà là logic rule không áp dụng cho tài nguyên đó.

Hãy xem kết quả của từng resource và chi tiết evaluation, không chỉ xem số lượng compliant/noncompliant tổng hợp. Nếu loại tài nguyên không được recorder ghi nhận, rule không có dữ liệu cần thiết.

## 7. Conformance pack

Conformance pack là tập hợp AWS Config rules và remediation actions được mô tả trong YAML template. Pack có thể được triển khai như một đơn vị trong một tài khoản và Region, hoặc dùng custom/organization conformance pack trên nhiều tài khoản trong AWS Organizations.

Một pack có thể chứa managed rules, custom policy rules, custom Lambda rules, remediation actions dựa trên Systems Manager Automation và input parameters để chuẩn hóa giá trị theo môi trường.

Ví dụ, **baseline-security** có thể gồm rule về public S3, encryption, SSH, CloudTrail và IAM. Pack khác có thể tập trung vào logging, backup và tag. Tách pack theo mục tiêu giúp quản lý ownership, triển khai và ngoại lệ rõ ràng hơn.

Với template AWS Config, các resource type chính được hỗ trợ là:

- **AWS::Config::ConfigRule**
- **AWS::Config::RemediationConfiguration**

### 7.1 Managed conformance pack

Managed conformance pack do AWS định nghĩa và duy trì. Bạn chọn pack trong catalog, cấu hình các tham số được hỗ trợ rồi triển khai.

- Nội dung rule do AWS duy trì.
- Có thể thay đổi tham số được hỗ trợ.
- Không thể tự thêm hoặc xóa rule trong managed pack.
- Rule được triển khai có thể khác nhau giữa các Region do mức độ hỗ trợ rule khác nhau.
- AWS có thể thêm, cập nhật hoặc loại bỏ rule khi yêu cầu, dịch vụ hoặc best practice thay đổi.
- Managed conformance pack được triển khai cho từng tài khoản và Region; không triển khai bằng Organization Conformance Pack.

Khi AWS cập nhật managed pack, tham số bạn đã tùy chỉnh được giữ nguyên. Tham số không tùy chỉnh sử dụng default hiện tại. Rule mới có thể được đưa vào deployment hiện có với giá trị mặc định. Hãy theo dõi thay đổi nội dung pack và đánh giá tác động.

### 7.2 Custom conformance pack

Custom conformance pack do tổ chức tự tạo. Bạn kiểm soát rule, tham số, tên, remediation và nhịp cập nhật.

Custom pack phù hợp khi tổ chức có baseline riêng, cần ghép rule từ nhiều dịch vụ, thêm Guard/Lambda rule, đóng gói remediation hoặc triển khai cùng một bộ kiểm soát cho nhiều tài khoản bằng organization conformance pack.

Có thể bắt đầu từ sample template của AWS rồi điều chỉnh theo tài nguyên, Region và quy trình nội bộ. Sample template chỉ là điểm khởi đầu; AWS nêu rõ các mẫu không bảo đảm tổ chức tuân thủ một luật hoặc tiêu chuẩn cụ thể.

| Tiêu chí | Managed pack | Custom pack |
|---|---|---|
| Chủ sở hữu nội dung | AWS | Tổ chức |
| Thêm/xóa rule | Không | Có |
| Cấu hình tham số | Theo tham số được hỗ trợ | Theo template |
| Tùy chỉnh remediation | Theo thiết kế của pack | Tổ chức thiết kế |
| Cập nhật nội dung | AWS có thể cập nhật | Tổ chức phát hành |
| Triển khai theo tổ chức | Không hỗ trợ qua Organization Conformance Pack | Có |
| Phù hợp | Bắt đầu nhanh theo best practice | Baseline riêng và quản trị tập trung |

## 8. Xây dựng custom conformance pack template

Một template có thể có phần Parameters và Resources. Parameters khai báo giá trị dùng để cấu hình rule. Resources khai báo các rule và remediation.

Ví dụ dưới đây gom hai managed rules vào một pack:

~~~yaml
Parameters:
  IamPasswordPolicyMinimumLength:
    Default: '14'
    Type: String
  AccessKeysMaximumAge:
    Default: '90'
    Type: String

Resources:
  IamPasswordPolicy:
    Type: AWS::Config::ConfigRule
    Properties:
      ConfigRuleName: iam-password-policy
      InputParameters:
        MinimumPasswordLength: !Ref IamPasswordPolicyMinimumLength
      Source:
        Owner: AWS
        SourceIdentifier: IAM_PASSWORD_POLICY

  AccessKeysRotated:
    Type: AWS::Config::ConfigRule
    Properties:
      ConfigRuleName: access-keys-rotated
      InputParameters:
        maxAccessKeyAge: !Ref AccessKeysMaximumAge
      Source:
        Owner: AWS
        SourceIdentifier: ACCESS_KEYS_ROTATED
~~~

Điểm cần kiểm tra:

- **Owner: AWS** dùng cho managed rule.
- **Owner: CUSTOM_POLICY** dùng cho custom policy rule.
- **Owner: CUSTOM_LAMBDA** dùng cho custom Lambda rule.
- SourceIdentifier của managed rule phải khớp identifier trong tài liệu AWS.
- Tên parameter trong InputParameters phải khớp tham số của rule.
- Kiểu parameter phải đúng định nghĩa của rule.
- Resource type mà rule đánh giá phải được recorder ghi nhận.
- Tên rule phải ổn định vì remediation tham chiếu đến tên đó.

Không nên sao chép template compliance từ Internet rồi triển khai ngay. Hãy kiểm tra rule có mặt trong Region, tham số có phù hợp và tài nguyên nào sẽ được đánh giá.

## 9. Gắn remediation vào conformance pack

Custom conformance pack có thể chứa cả Config rule và RemediationConfiguration. Ví dụ sau dùng rule kiểm tra public read trên S3 bucket và SSM Automation runbook **AWS-DisableS3BucketPublicReadWrite**.

Template đặt chế độ manual trước để đội vận hành quan sát finding và kiểm tra tác động. Sau khi thử nghiệm và phê duyệt, có thể đổi Automatic thành true để bật auto remediation.

~~~yaml
Resources:
  S3BucketPublicReadProhibited:
    Type: AWS::Config::ConfigRule
    Properties:
      ConfigRuleName: s3-bucket-public-read-prohibited
      Source:
        Owner: AWS
        SourceIdentifier: S3_BUCKET_PUBLIC_READ_PROHIBITED

  S3BucketPublicReadProhibitedRemediation:
    Type: AWS::Config::RemediationConfiguration
    DependsOn: S3BucketPublicReadProhibited
    Properties:
      ConfigRuleName: s3-bucket-public-read-prohibited
      ResourceType: AWS::S3::Bucket
      TargetType: SSM_DOCUMENT
      TargetId: AWS-DisableS3BucketPublicReadWrite
      TargetVersion: "1"
      Automatic: false
      MaximumAutomaticAttempts: 5
      RetryAttemptSeconds: 300
      ExecutionControls:
        SsmControls:
          ConcurrentExecutionRatePercentage: 10
          ErrorPercentage: 50
      Parameters:
        AutomationAssumeRole:
          StaticValue:
            Values:
              - arn:aws:iam::111122223333:role/ConfigRemediationAutomationRole
        S3BucketName:
          ResourceValue:
            Value: RESOURCE_ID
~~~

Thay **111122223333** bằng AWS account ID phù hợp và tạo role đúng tên trước khi triển khai. Tên rule trong RemediationConfiguration phải khớp chính xác với ConfigRuleName của rule.

### Static và dynamic parameters

RemediationConfiguration có thể truyền hai loại giá trị:

- **StaticValue:** giá trị cố định, chẳng hạn ARN của Automation assume role.
- **ResourceValue:** giá trị được AWS Config thay thế khi chạy remediation.

Trong ví dụ, **AutomationAssumeRole** là ARN cố định của role mà Automation sẽ assume. **S3BucketName** nhận giá trị **RESOURCE_ID**. Với S3 bucket, resource ID chính là bucket name.

Dynamic parameter giúp cùng một remediation configuration xử lý nhiều tài nguyên. Không truyền một resource ID cố định nếu runbook cần xử lý từng bucket vi phạm.

### DependsOn và intrinsic functions

RemediationConfiguration tham chiếu đến Config rule. DependsOn yêu cầu CloudFormation tạo rule trước khi tạo remediation.

Đối với conformance pack remediation, AWS Config yêu cầu ARN của Automation execution role và ConfigRuleName được khai báo bằng giá trị đầy đủ. Không dùng CloudFormation intrinsic functions cho hai giá trị này trong phần remediation configuration. Hãy thay ARN mẫu bằng ARN thực tế trước khi triển khai.

## 10. Triển khai conformance pack

Trước khi triển khai:

1. Bật AWS Config recording trong Region.
2. Kiểm tra recorder có bao gồm resource type mà pack cần đánh giá.
3. Xác nhận các rule có sẵn trong Region.
4. Tạo Automation assume role nếu pack có remediation.
5. Tạo Lambda function và execution role nếu pack có custom Lambda rule.
6. Cấu hình S3 delivery bucket và bucket policy khi cần lưu template/artifact.
7. Kiểm tra quyền của principal triển khai pack.

### Triển khai từ console

Trong AWS Config console, mở Conformance packs, chọn Deploy conformance pack, chọn managed hoặc custom pack, cấu hình tham số/template, xem lại và triển khai. Với template lớn hơn 50 KB, tải template lên S3 và chọn S3 URI. Sau triển khai, theo dõi deployment status.

Tên conformance pack phải duy nhất trong phạm vi tài khoản và Region, tối đa 256 ký tự chữ/số, có thể chứa dấu gạch nối và không chứa khoảng trắng.

### Triển khai custom pack bằng AWS CLI

Ví dụ triển khai template từ file cục bộ vào Region Singapore:

~~~bash
aws configservice put-conformance-pack \
  --conformance-pack-name s3-public-access-baseline \
  --template-body file://s3-public-access-baseline.yaml \
  --delivery-s3-bucket config-artifacts-111122223333 \
  --region ap-southeast-1
~~~

Nếu template nằm trong S3, dùng **--template-s3-uri** thay cho **--template-body**.

Theo dõi trạng thái triển khai:

~~~bash
aws configservice describe-conformance-pack-status \
  --conformance-pack-name s3-public-access-baseline \
  --region ap-southeast-1
~~~

Xem trạng thái compliance:

~~~bash
aws configservice describe-conformance-pack-compliance \
  --conformance-pack-name s3-public-access-baseline \
  --region ap-southeast-1
~~~

Triển khai thành công chưa có nghĩa mọi rule đã đánh giá xong. Hãy đợi rule hoàn tất evaluation và kiểm tra chi tiết từng rule/resource.

### Cập nhật và xóa pack

Khi cập nhật custom pack, hãy phát hành lại template có thay đổi. Review kỹ việc thêm/xóa rule, thay tham số hoặc thay remediation vì các thay đổi này có thể tạo nhiều finding hoặc thay đổi tài nguyên thật.

Khi xóa pack, các rule và remediation thuộc pack sẽ bị xóa theo. Kiểm tra dashboard, quy trình downstream và yêu cầu lưu bằng chứng trước khi xóa. Xóa remediation action không đồng nghĩa xóa Config rule; hai thao tác có vòng đời riêng.

## 11. Triển khai ở quy mô AWS Organizations

Organization conformance pack cho phép quản trị tập trung từ organization management account hoặc delegated administrator phù hợp. Tổ chức có thể triển khai, cập nhật và xóa pack trên member accounts, đồng thời loại trừ một số tài khoản khỏi deployment.

Luồng tổng quát:

1. Bật AWS Config recording trong các tài khoản và Region đích.
2. Thiết lập AWS Organizations và quyền tích hợp dịch vụ.
3. Tạo hoặc xác nhận service-linked role cần thiết.
4. Chuẩn bị template và S3 delivery bucket có bucket policy phù hợp.
5. Nếu có remediation, tạo Automation execution role với cùng tên trong tất cả tài khoản cần triển khai.
6. Gọi PutOrganizationConformancePack trong từng Region cần quản lý.
7. Theo dõi deployment status và detailed status theo từng member account.
8. Xử lý tài khoản mới, tài khoản chưa có recorder và lỗi quyền.

Các điểm cần nhớ:

- API triển khai organization pack có phạm vi Region. Muốn triển khai sang Region khác phải gọi API với Region đó.
- Khi tài khoản mới gia nhập Organization, organization pack được triển khai cho tài khoản đó.
- Khi tài khoản rời Organization, organization pack tương ứng bị gỡ khỏi tài khoản.
- AWS Config chỉ retry deployment cho tài khoản mới trong 7 giờ sau khi tài khoản gia nhập Organization nếu chưa có recorder; cần tạo recorder trong khoảng thời gian này.
- Nếu dùng delegated administrator, cần chú ý service-linked role trong management account.
- Role dùng để chạy remediation phải tồn tại trong mọi tài khoản liên quan trước khi gọi PutOrganizationConformancePack.

Managed conformance pack không hỗ trợ triển khai bằng Organization Conformance Pack. Nếu cần triển khai tập trung qua Organizations, hãy dùng custom conformance pack.

API thường dùng:

- **PutOrganizationConformancePack:** tạo hoặc cập nhật pack cho tổ chức.
- **DescribeOrganizationConformancePacks:** liệt kê organization packs.
- **DescribeOrganizationConformancePackStatuses:** xem trạng thái deployment.
- **GetOrganizationConformancePackDetailedStatus:** xem trạng thái theo member account.
- **DeleteOrganizationConformancePack:** xóa pack trên các member account.

Một yêu cầu triển khai ở cấp tổ chức có thể thành công ở một số tài khoản nhưng thất bại ở tài khoản khác. Hãy đưa account ID, Region, trạng thái và thông báo lỗi vào báo cáo vận hành.

## 12. Process checks

Không phải yêu cầu tuân thủ nào cũng có thể suy ra từ cấu hình AWS. Một số kiểm soát yêu cầu xác nhận từ con người hoặc hệ thống ngoài AWS.

Process checks cho phép đưa các nhiệm vụ đó vào conformance pack. Ví dụ:

- Xác nhận bản sao lưu ngoại tuyến được lưu ở địa điểm độc lập.
- Xác nhận quy trình phê duyệt quyền truy cập đã được thực hiện.
- Xác nhận biên bản kiểm thử khôi phục được review.
- Xác nhận nhân sự hoàn thành đào tạo bảo mật định kỳ.

Process check giúp tập hợp kết quả kiểm soát cấu hình và kiểm soát quy trình trong cùng một pack. Trạng thái cần được cập nhật theo bằng chứng và quy trình của tổ chức. Đây không phải cơ chế tự phát hiện cấu hình tài nguyên.

## 13. Remediation với Systems Manager Automation

AWS Config áp dụng remediation bằng AWS Systems Manager Automation documents. Một Automation document, thường gọi là runbook, mô tả các bước cần chạy và tham số đầu vào. AWS cung cấp managed Automation documents và cho phép tạo custom document.

| Runbook | Mục đích |
|---|---|
| **AWS-DisableS3BucketPublicReadWrite** | Dùng S3 Block Public Access để vô hiệu hóa public read/write |
| **AWS-EnableS3BucketEncryption** | Cấu hình default encryption cho S3 bucket |
| **AWS-ConfigureS3BucketVersioning** | Cấu hình S3 bucket versioning |
| **AWSConfigRemediation-ConfigureS3BucketPublicAccessBlock** | Cấu hình S3 Block Public Access theo remediation workflow |

Tên runbook không đủ để chứng minh hành động phù hợp. Hãy đọc mô tả, parameters, steps, IAM permissions và tác động lên tài nguyên trước khi gắn vào rule.

### Manual remediation

Manual remediation gắn runbook với rule nhưng yêu cầu người vận hành chủ động bắt đầu. Cách này phù hợp khi hành động có thể gây gián đoạn, cần phê duyệt, cần kiểm tra ngoại lệ hoặc đội vận hành muốn chạy thử từng tài nguyên.

API StartRemediationExecution bắt đầu remediation cho resource keys đã chọn dựa trên cấu hình hiện có. Người vận hành cần kiểm tra kết quả thực thi và đánh giá lại tài nguyên.

### Automatic remediation

Automatic remediation cho phép AWS Config tự bắt đầu Automation khi phát hiện tài nguyên NON_COMPLIANT theo rule được cấu hình.

1. Rule đánh giá tài nguyên và trả NON_COMPLIANT.
2. AWS Config tìm remediation configuration tương ứng.
3. AWS Config truyền static/dynamic parameters cho SSM document.
4. Systems Manager bắt đầu Automation.
5. Automation assume role và thực thi các bước.
6. AWS Config ghi nhận và đánh giá cấu hình sau thay đổi.

Automatic remediation phù hợp với hành động có phạm vi rõ, có thể lặp lại an toàn và ít khả năng phá vỡ workload. Không nên bật auto cho mọi rule chỉ vì đã có runbook.

| Tiêu chí | Manual | Automatic |
|---|---|---|
| Người khởi chạy | Operator hoặc quy trình được phê duyệt | AWS Config |
| Thời điểm thực thi | Sau khi review | Sau khi rule phát hiện vi phạm |
| Tốc độ xử lý | Phụ thuộc người vận hành | Có thể nhanh và nhất quán |
| Kiểm soát tác động | Dễ kiểm tra từng tài nguyên | Cần giới hạn concurrency và scope |
| Phù hợp | Hành động rủi ro hoặc cần phê duyệt | Hành động lặp lại, có thể kiểm soát |

Một thiết kế thực tế thường bắt đầu bằng manual remediation, đo tỷ lệ thành công và tác động, sau đó chuyển sang automatic cho nhóm tài nguyên đã được kiểm chứng.

## 14. IAM cho remediation

Remediation có nhiều lớp quyền. Không nên dùng một role AdministratorAccess cho toàn bộ quy trình.

### Service-linked role của AWS Config

Khi triển khai conformance pack, AWS Config sử dụng service-linked role tương ứng, thường có tên **AWSServiceRoleForConfigConforms**, để tạo Config rules và remediation configurations trong tài khoản.

### Automation assume role

SSM Automation có thể chạy trong context của người khởi chạy hoặc một IAM service role. AWS khuyến nghị dùng service role/assume role để kiểm soát quyền mà runbook được phép thực thi.

Trust policy tối giản minh họa:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ssm.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

Role cần có permission mà từng bước của runbook yêu cầu. Ví dụ runbook sửa S3 bucket có thể cần quyền đọc trạng thái Block Public Access và cập nhật cấu hình tương ứng. Hãy đọc các bước trong runbook để xác định quyền cụ thể, giới hạn resource ARN và tránh quyền wildcard khi có thể.

### Principal triển khai và iam:PassRole

Principal triển khai pack cần quyền tạo/cập nhật conformance pack, đọc template từ S3 hoặc SSM document và cho phép AWS Config tạo service-linked role khi cần. Tài liệu API nêu các lỗi thường gặp như thiếu IAM GetRole, CreateServiceLinkedRole, quyền đọc S3 hoặc SSM:GetDocument.

Khi một principal gọi Automation với service role, cần kiểm tra quyền iam:PassRole đối với role được truyền. Hãy giới hạn PassRole vào đúng role và đúng dịch vụ tin cậy.

Một thiết kế thường có ba nhóm:

- **Config deployment role:** triển khai rule, pack và cập nhật cấu hình.
- **Automation execution role:** được SSM assume để sửa tài nguyên.
- **Operator role:** xem compliance, điều tra finding, chạy manual remediation và xử lý ngoại lệ.

Tách quyền giúp audit xác định ai thay đổi baseline, dịch vụ nào thực thi hành động và người vận hành nào phê duyệt thao tác thủ công.

## 15. Retry, concurrency và lỗi

Remediation có thể thất bại do thiếu quyền, tài nguyên đã thay đổi, runbook nhận sai tham số, dịch vụ đích throttling hoặc trạng thái tài nguyên không còn như lúc đánh giá.

| Thuộc tính | Ý nghĩa |
|---|---|
| MaximumAutomaticAttempts | Số lần thất bại tối đa trước khi tạo remediation exception |
| RetryAttemptSeconds | Cửa sổ thời gian dùng để tính số lần retry |
| ConcurrentExecutionRatePercentage | Tỷ lệ remediation được phép chạy đồng thời cho rule |
| ErrorPercentage | Tỷ lệ lỗi cho phép trước khi Systems Manager dừng các automation đang chạy theo rule |

Theo API reference, nếu không chỉ định, MaximumAutomaticAttempts mặc định là 5 và RetryAttemptSeconds mặc định là 60 giây. MaximumAutomaticAttempts có giới hạn tối đa 25. RetryAttemptSeconds và các giá trị concurrency/error có giới hạn theo schema API; hãy kiểm tra API reference khi cấu hình.

Trong ví dụ template, **ConcurrentExecutionRatePercentage: 10** giới hạn tỷ lệ hành động chạy song song ở mức thấp để bắt đầu. **ErrorPercentage: 50** cho phép một tỷ lệ lỗi nhất định trước khi SSM dừng thực thi. Hãy chọn giá trị theo số lượng tài nguyên, mức độ rủi ro và khả năng phục hồi của workload.

Khi nhiều lần tự động khắc phục thất bại trong cửa sổ retry, AWS Config có thể tạo remediation exception cho resource. Exception ngăn việc lặp vô hạn một hành động đang thất bại. Đội vận hành cần xem exception, xử lý nguyên nhân và quản lý vòng đời theo quy trình.

Retry không thay thế việc sửa nguyên nhân gốc. Tăng retry trong khi role thiếu quyền hoặc tham số sai chỉ làm tăng số lần thất bại và chi phí Automation.

## 16. Rủi ro auto remediation và giới hạn blast radius

Tự động sửa cấu hình có thể ảnh hưởng đến ứng dụng đang chạy. Ví dụ, bucket có thể được public có chủ đích để phân phối website tĩnh. Bật Block Public Access ngay lập tức có thể làm website ngừng truy cập.

Một rủi ro kỹ thuật khác là AWS Config dùng compliance data snapshot được tạo theo chu kỳ để khởi tạo auto remediation. Nếu tài nguyên đã được sửa sau snapshot nhưng snapshot chưa cập nhật, quá trình remediation có thể vẫn bắt đầu theo trạng thái NON_COMPLIANT cũ. Vì vậy, hành động đôi khi có thể được khởi chạy cho tài nguyên hiện đã compliant.

Các biện pháp kiểm soát:

1. Bắt đầu bằng manual remediation cho hành động có tác động lớn.
2. Giới hạn scope theo resource type, tag hoặc account.
3. Quản lý ngoại lệ hợp lệ bằng quy trình có thời hạn và chủ sở hữu.
4. Dùng runbook có thể chạy lặp lại an toàn (idempotent) nếu có thể.
5. Kiểm tra trạng thái hiện tại ngay trước khi thay đổi.
6. Giới hạn concurrency và ngưỡng lỗi.
7. Triển khai thử ở development, sau đó staging, rồi mới production.
8. Ghi log đầu vào, tài nguyên mục tiêu, kết quả từng bước và lỗi.
9. Có cách rollback hoặc phục hồi cấu hình nếu hành động ảnh hưởng workload.
10. Theo dõi remediation exception và không để exception tồn tại vô thời hạn.

Đối với thay đổi có thể làm mất dữ liệu, xóa tài nguyên, khóa quyền truy cập hoặc gián đoạn production, hãy dùng bước phê duyệt riêng thay vì bật auto remediation ngay.

## 17. Giới hạn API và mô hình triển khai

Không phải mọi rule đều có thể gắn remediation theo cùng một cách.

- AWS Config console chỉ cho phép quản lý remediation trực tiếp đối với các rule không phải service-linked rule.
- API PutRemediationConfigurations không hỗ trợ thêm remediation configuration cho service-linked rules như organization Config rules, rule được triển khai bởi conformance pack hoặc rule được triển khai bởi AWS Security Hub.
- Nếu cần đóng gói rule và remediation trong custom conformance pack, khai báo cả AWS::Config::ConfigRule và AWS::Config::RemediationConfiguration trong cùng template.
- Nếu thay đổi SSM document theo cách không tương thích ngược, cần cập nhật lại remediation configuration để AWS Config dùng cấu hình mục tiêu phù hợp.
- Một số rule chỉ có trong một số Region. Kiểm tra Region availability trước khi triển khai pack.
- Tài nguyên phải được recorder ghi nhận thì rule mới có dữ liệu đánh giá.

Hãy phân biệt remediation configuration gắn trực tiếp với rule thông thường và remediation được định nghĩa bên trong custom conformance pack.

## 18. Theo dõi compliance và remediation

Theo dõi ba lớp:

### Rule compliance

Xem rule nào COMPLIANT/NON_COMPLIANT/ERROR/NOT_APPLICABLE, tài nguyên nào bị đánh dấu, tham số/scope của rule và thời điểm evaluation.

Có thể yêu cầu đánh giá lại rule bằng CLI:

~~~bash
aws configservice start-config-rules-evaluation \
  --config-rule-names s3-bucket-public-read-prohibited \
  --region ap-southeast-1
~~~

### Conformance pack status

Dashboard conformance pack hiển thị deployment status, compliance score và các rule trong pack. Compliance score là tỷ lệ các cặp rule-resource compliant trên tổng số cặp có thể có. Trong khi pack đang triển khai, score có thể chưa đầy đủ.

Trạng thái tổng hợp của pack có quy tắc riêng: pack là NON_COMPLIANT nếu có bất kỳ rule nào NON_COMPLIANT; pack là INSUFFICIENT_DATA chỉ khi tất cả rule đều thiếu dữ liệu đánh giá. Nếu một số rule COMPLIANT và các rule còn lại INSUFFICIENT_DATA, pack vẫn hiển thị COMPLIANT. Compliance được đánh giá theo từng nhóm rule, không nhất thiết tất cả rule hoàn tất cùng lúc. Vì vậy, hãy mở từng rule và resource để kiểm tra kết quả chi tiết.

Để báo cáo compliance chính xác, recorder phải ghi nhận **AWS::Config::ResourceCompliance**. Để xem lịch sử thay đổi compliance của pack theo timeline, có thể ghi nhận **AWS::Config::ConformancePackCompliance**.

### Remediation execution

Với remediation thất bại, dùng DescribeRemediationExecutionStatus để xem trạng thái, timestamp của các bước và thông báo lỗi. Sau đó kiểm tra SSM Automation execution history để tìm step thất bại.

Ví dụ bắt đầu manual remediation cho một S3 bucket thử nghiệm:

~~~bash
aws configservice start-remediation-execution \
  --config-rule-name s3-bucket-public-read-prohibited \
  --resource-keys resourceType=AWS::S3::Bucket,resourceId=my-test-bucket \
  --region ap-southeast-1
~~~

Thay resource ID bằng bucket đã được xác nhận phù hợp và kiểm tra trước khi thực thi.

## 19. Ví dụ kiến trúc: baseline bảo mật cho nhiều tài khoản

Giả sử công ty có ba nhóm tài khoản: Shared services chứa công cụ CI/CD, logging và network; Development phục vụ môi trường phát triển; Production chạy ứng dụng thật.

Đội cloud platform duy trì custom conformance pack **company-security-baseline** gồm S3 public access, S3 default encryption, EBS volume encryption, security group SSH exposure, CloudTrail enabled và IAM password policy.

Quy trình vận hành:

1. Platform team cập nhật template trong repository.
2. Pull request được review bởi security và cloud operations.
3. Pipeline kiểm tra YAML, tên rule, resource type và Region availability.
4. Pipeline triển khai pack vào tài khoản thử nghiệm.
5. Đội vận hành xem finding và xác minh false positive.
6. Remediation được chạy manual cho tài nguyên cần xử lý.
7. Sau khi runbook được kiểm chứng, một số rule có thể chuyển sang automatic.
8. Pack được triển khai theo Organizations đến tài khoản/OU phù hợp.
9. Dashboard tổng hợp trạng thái, remediation failures và exception.
10. Mỗi lần thay đổi baseline được lưu trong version control và có lịch sử phê duyệt.

~~~mermaid
flowchart TD
    A["Security baseline repository"] --> B["Review and CI validation"]
    B --> C["Test account and Region"]
    C --> D["AWS Config conformance pack"]
    D --> E["Organization deployment"]
    E --> F["Development accounts"]
    E --> G["Production accounts"]
    F --> H["Compliance findings"]
    G --> H
    H --> I["Manual or automatic SSM remediation"]
    I --> J["Re-evaluation and audit evidence"]
    J --> K["Central operations dashboard"]
~~~

Không nên triển khai một baseline với cùng mức tự động hóa cho mọi tài khoản. Development có thể cho phép remediation tự động rộng hơn. Production có thể yêu cầu phê duyệt cho thay đổi có khả năng ảnh hưởng dịch vụ.

## 20. Lab: tạo rule, conformance pack và kiểm tra remediation

Lab dùng một bucket thử nghiệm và Region **ap-southeast-1**. Không sử dụng bucket production hoặc bucket đang phục vụ website.

### Bước 1: chuẩn bị AWS Config

- Mở AWS Config trong Region thử nghiệm.
- Bật configuration recorder.
- Đảm bảo recorder ghi nhận S3 bucket.
- Xác nhận delivery channel và IAM role hoạt động.

### Bước 2: chuẩn bị Automation role

- Tạo IAM role cho Systems Manager Automation.
- Trust policy cho phép **ssm.amazonaws.com** assume role.
- Gắn quyền tối thiểu theo các bước của runbook **AWS-DisableS3BucketPublicReadWrite**.
- Ghi lại ARN của role.
- Xác nhận principal triển khai có quyền cần thiết để truyền role cho Automation.

### Bước 3: tạo bucket thử nghiệm

Tạo bucket chỉ dùng trong lab. Nếu cần tạo trạng thái NON_COMPLIANT, cấu hình public read trên bucket thử nghiệm theo cách được AWS cho phép trong tài khoản lab. Không áp dụng bước này trên dữ liệu thật.

### Bước 4: tạo conformance pack

- Lưu template ở mục 9 thành **s3-public-access-baseline.yaml**.
- Thay account ID trong Automation role ARN.
- Bảo đảm rule name trong remediation khớp ConfigRuleName của rule.
- Giữ **Automatic: false** trong lần chạy đầu.
- Triển khai pack bằng AWS CLI hoặc console.

### Bước 5: xem kết quả rule

Đợi AWS Config đánh giá bucket. Mở Conformance packs, chọn pack, xem rule và tài nguyên NON_COMPLIANT. Kiểm tra đúng bucket thử nghiệm và xác minh nguyên nhân vi phạm.

### Bước 6: chạy manual remediation

Chạy StartRemediationExecution cho bucket thử nghiệm hoặc khởi chạy remediation từ console. Theo dõi Automation execution trong Systems Manager. Kiểm tra từng step, đầu vào và output.

### Bước 7: xác minh lại

- Kiểm tra S3 Block Public Access của bucket.
- Yêu cầu AWS Config đánh giá lại rule.
- Xác nhận trạng thái chuyển sang COMPLIANT.
- Ghi lại thời gian phát hiện, thời gian remediation và kết quả.

### Bước 8: thử nghiệm automatic remediation

Sau khi manual remediation thành công, cập nhật template để đặt **Automatic: true**, triển khai cập nhật pack vào môi trường lab và thử trên một bucket thử nghiệm khác. Quan sát retry, concurrency, lỗi và trạng thái compliance.

## 21. Troubleshooting thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Rule không có kết quả | Resource type chưa được recorder ghi nhận | Kiểm tra recorder và Region |
| Rule luôn INSUFFICIENT_DATA | Không có tài nguyên phù hợp hoặc chưa có dữ liệu | Kiểm tra resource type, scope và lần ghi nhận đầu |
| Rule trả ERROR | Input parameter sai kiểu hoặc sai định dạng | Đối chiếu parameter với tài liệu rule |
| Rule đánh giá sai tài nguyên | Scope hoặc tag filter không đúng | Kiểm tra scope và tag thực tế |
| Custom Lambda rule không chạy | Lambda ARN, permission hoặc execution role sai | Kiểm tra invoke permission, CloudWatch Logs và timeout |
| Guard rule báo kết quả không như mong đợi | Sai đường dẫn configuration hoặc schema | Kiểm tra payload và Guard policy |
| Pack deployment thất bại | Thiếu quyền, S3 bucket policy hoặc recorder chưa bật | Kiểm tra prerequisite, IAM và S3 access |
| Pack chỉ triển khai một phần | Một số tài khoản chưa có recorder hoặc role | Xem detailed status theo account |
| SSM Automation không bắt đầu | Thiếu quyền StartAutomationExecution, PassRole hoặc trust relationship | Kiểm tra IAM caller và Automation role |
| Runbook không tìm thấy tài nguyên | Dynamic parameter hoặc resource type sai | Kiểm tra RESOURCE_ID và tham số document |
| Runbook chạy nhưng không sửa được | Role thiếu quyền trên tài nguyên | Đọc lỗi step và bổ sung quyền tối thiểu |
| Remediation thất bại liên tục | Tham số sai, lỗi dịch vụ hoặc trạng thái thay đổi | Dừng retry, điều tra nguyên nhân, kiểm tra exception |
| Tài nguyên đã compliant nhưng vẫn bị remediation | Compliance snapshot chưa cập nhật | Kiểm tra trạng thái hiện tại và lịch sử execution |
| Pack compliance score thấp | Nhiều resource/rule không compliant | Xem chi tiết rule-resource và ưu tiên theo rủi ro |
| Rule không có remediation option | Rule là service-linked hoặc cách triển khai không hỗ trợ | Đưa remediation vào custom conformance pack template nếu phù hợp |

### Quy trình điều tra lỗi remediation

1. Xác định account, Region, Config rule và resource ID.
2. Xem compliance result và thời điểm evaluation.
3. Xem remediation configuration: TargetId, TargetVersion, Automatic và Parameters.
4. Mở SSM Automation execution để tìm step thất bại.
5. Kiểm tra IAM role trust relationship và quyền của từng API.
6. Kiểm tra resource có còn tồn tại và còn ở trạng thái cần sửa không.
7. Xác minh runbook nhận đúng dynamic resource ID.
8. Sửa cấu hình rồi chạy lại manual trên một tài nguyên.
9. Khi kết quả ổn định, mới bật lại auto remediation.
10. Theo dõi remediation exception để bảo đảm không còn lỗi bị che giấu.

## 22. Chi phí và quota

Chi phí cần xem xét gồm AWS Config recording và evaluation, số lượng resource type/tài nguyên được ghi nhận, tần suất periodic evaluation, Systems Manager Automation executions, Amazon S3 lưu template/history/snapshot, Lambda và CloudWatch Logs nếu custom rule sử dụng Lambda.

Một rule periodic chạy thường xuyên trên phạm vi rộng có thể tạo nhiều evaluation. Remediation thất bại và retry nhiều lần có thể tạo thêm Automation executions. Để tối ưu chi phí:

- Chỉ ghi nhận loại tài nguyên có nhu cầu kiểm soát rõ ràng, hoặc dùng all supported resource types khi lợi ích bao phủ cao hơn chi phí.
- Tránh periodic trigger quá dày nếu configuration change trigger đã đáp ứng yêu cầu.
- Dùng scope theo resource type/tag khi chính sách không cần áp dụng toàn bộ tài nguyên.
- Loại bỏ rule trùng lặp hoặc không còn được sử dụng.
- Giám sát số lần evaluation và remediation execution.
- Thiết kế runbook dừng sớm khi resource đã đạt trạng thái mong muốn.

Các quota AWS Config có thể thay đổi theo thời gian. Tại thời điểm biên soạn, tài liệu AWS công bố các giới hạn chính sau:

| Hạng mục | Quota mặc định |
|---|---:|
| AWS Config rules trên mỗi tài khoản, mỗi Region | 1.000 |
| Conformance packs trên mỗi tài khoản | 50 |
| Config rules trong một conformance pack | 130 |
| Organization conformance packs trên mỗi Organization | 50 |
| Config rules trong một organization conformance pack | 130 |
| Configuration aggregators | 50 |
| Số tài khoản trong một aggregator | 10.000 |

Rule nằm trong conformance pack vẫn được tính vào quota AWS Config rules của tài khoản/Region. Organization-level pack cũng được tính vào quota của child accounts. Template truyền trực tiếp trong API có giới hạn kích thước; template lớn cần được lưu trong S3. Hãy kiểm tra service quotas và API reference trước rollout lớn.

## 23. Best practices

### Thiết kế rule

- Viết mô tả rule theo ngôn ngữ nghiệp vụ.
- Đặt scope có chủ đích để tránh đánh giá tài nguyên ngoài phạm vi.
- Chọn trigger theo độ trễ phát hiện mong muốn.
- Kiểm tra resource type có được recorder ghi nhận.
- Dùng managed rule nếu logic đã có sẵn.
- Giữ custom Guard/Lambda rule trong version control và review như mã nguồn.

### Thiết kế conformance pack

- Chia pack theo mục tiêu bảo mật, vận hành hoặc cost governance.
- Dùng parameter để chuẩn hóa ngưỡng theo môi trường.
- Kiểm tra rule availability ở từng Region.
- Quản lý template theo version và có quy trình review.
- Dùng custom pack khi cần triển khai qua AWS Organizations.
- Theo dõi thay đổi nội dung managed pack do AWS duy trì.
- Không xem sample pack là chứng nhận tuân thủ.

### Thiết kế remediation

- Bắt đầu với manual remediation cho hành động có tác động lớn.
- Đọc toàn bộ runbook trước khi gắn vào rule.
- Dùng Automation assume role riêng và quyền tối thiểu.
- Truyền resource ID động thay vì hard-code resource ID.
- Ưu tiên hành động idempotent.
- Giới hạn concurrency và error percentage.
- Đặt retry hợp lý; không dùng retry để che giấu lỗi cấu hình.
- Theo dõi stale compliance snapshot và remediation exceptions.
- Có rollback hoặc quy trình phục hồi cho thay đổi rủi ro.

### Vận hành nhiều tài khoản

- Bật recorder trước khi triển khai organization pack.
- Triển khai theo Region và theo OU/account scope.
- Tạo Automation role trong mọi tài khoản cần remediation.
- Dùng delegated administrator khi mô hình vận hành yêu cầu.
- Theo dõi detailed deployment status theo từng tài khoản.
- Gắn owner và thời hạn cho mọi ngoại lệ.
- Lưu lịch sử thay đổi template và phê duyệt.

## 24. Bài tập tự luyện

1. Một rule kiểm tra EBS encryption không trả kết quả cho volume mới tạo. Bạn kiểm tra thành phần nào trước tiên?
2. Khi nào nên dùng configuration change trigger thay cho periodic trigger?
3. Nêu điểm khác nhau giữa detective và proactive evaluation.
4. Proactive evaluation có tự động chặn CloudFormation triển khai tài nguyên NON_COMPLIANT không? Giải thích.
5. Một rule managed có tham số maxAccessKeyAge. Tổ chức yêu cầu tối đa 60 ngày. Bạn cấu hình ở đâu?
6. Khi nào nên chọn custom Guard rule thay cho custom Lambda rule?
7. Một conformance pack có 12 rule. Lợi ích của việc triển khai bằng một YAML template là gì?
8. Có thể tự thêm rule vào managed conformance pack không?
9. Tại sao managed conformance pack có thể chứa số rule khác nhau giữa hai Region?
10. Một tổ chức muốn triển khai baseline qua AWS Organizations. Nên dùng managed hay custom conformance pack?
11. Vì sao Automation assume role cần quyền hẹp hơn AdministratorAccess?
12. Trong RemediationConfiguration, RESOURCE_ID giúp ích gì?
13. Tại sao nên bắt đầu bằng manual remediation với hành động bật Block Public Access trên bucket production?
14. Điều gì có thể xảy ra khi AWS Config dùng compliance snapshot cũ để khởi tạo auto remediation?
15. Khi nào retry nhiều lần làm tăng chi phí mà không giải quyết được vấn đề?
16. Một organization conformance pack triển khai thất bại ở hai tài khoản. Bạn cần xem dữ liệu nào?
17. Vì sao một template có remediation cần role Automation tồn tại trong các tài khoản đích?
18. Một SSM document thay đổi theo cách không tương thích ngược. Cần cập nhật thành phần nào?
19. Tại sao không nên chỉ dựa vào compliance score tổng hợp của pack?
20. Process check phù hợp với loại yêu cầu tuân thủ nào?

### Gợi ý đáp án

1. Kiểm tra recorder có ghi nhận **AWS::EC2::Volume** trong đúng Region không.
2. Dùng configuration change khi cần đánh giá sau mỗi thay đổi; periodic khi cần kiểm tra lại theo lịch dù không có configuration change.
3. Detective đánh giá tài nguyên đã triển khai; proactive đánh giá cấu hình dự kiến trước triển khai.
4. Không. Pipeline hoặc hệ thống triển khai phải đọc kết quả và tự quyết định dừng.
5. Trong input parameter của rule hoặc parameter tương ứng trong conformance pack template.
6. Khi policy có thể biểu diễn rõ bằng Guard và không cần logic/tích hợp phức tạp.
7. Dễ version, review, triển khai lặp lại và theo dõi baseline như một đơn vị.
8. Không. Nội dung rule của managed pack do AWS quản lý.
9. Rule availability có thể khác nhau theo Region.
10. Custom conformance pack vì managed pack không hỗ trợ Organization Conformance Pack.
11. Để giới hạn tác động nếu runbook lỗi hoặc bị gọi ngoài dự kiến.
12. AWS Config thay RESOURCE_ID bằng ID của tài nguyên vi phạm tại thời điểm chạy.
13. Vì bucket có thể phục vụ website hoặc ứng dụng cần public access; hành động có thể gây gián đoạn.
14. Remediation có thể vẫn được khởi chạy theo trạng thái NON_COMPLIANT cũ dù tài nguyên đã được sửa.
15. Khi nguyên nhân là thiếu quyền, sai parameter hoặc lỗi logic; retry chỉ lặp lại lỗi.
16. Account ID, Region, deployment status, detailed status, recorder và IAM role.
17. SSM Automation cần assume role để thực hiện các API thay đổi tài nguyên.
18. Cập nhật remediation configuration/pack để dùng phiên bản document và tham số tương thích.
19. Vì score tổng hợp có thể che giấu rule/resource thiếu dữ liệu hoặc vi phạm cụ thể.
20. Yêu cầu cần người hoặc hệ thống ngoài AWS xác minh, như kiểm tra hồ sơ, phê duyệt hoặc diễn tập khôi phục.

## 25. Câu hỏi phỏng vấn

### AWS Config rule khác CloudTrail event như thế nào?

CloudTrail ghi hoạt động API và ai thực hiện hành động. AWS Config ghi nhận trạng thái cấu hình tài nguyên theo thời gian và đánh giá trạng thái đó theo rule. CloudTrail giúp điều tra ai thay đổi; Config giúp xác định cấu hình sau thay đổi có tuân thủ hay không.

### Khi nào chọn managed rule?

Khi AWS đã cung cấp logic phù hợp và yêu cầu có thể biểu diễn bằng input parameters. Managed rule giảm lượng mã tùy chỉnh phải bảo trì.

### Custom Guard rule khác custom Lambda rule thế nào?

Guard biểu diễn policy-as-code để kiểm tra thuộc tính cấu hình. Lambda phù hợp với logic phức tạp hơn, cần xử lý tùy biến hoặc gọi hệ thống khác. Lambda làm tăng trách nhiệm quản lý runtime, IAM, logging và retry.

### Vì sao proactive evaluation không phải deployment gate?

AWS Config trả kết quả đánh giá nhưng không tự chặn deployment. Pipeline phải gọi API đánh giá, đọc kết quả và áp dụng chính sách dừng/cho phép.

### Vì sao managed conformance pack không triển khai bằng Organization Conformance Pack?

Đây là giới hạn được AWS công bố cho managed pack. Khi cần triển khai ở cấp tổ chức, hãy dùng custom conformance pack và quản lý template của tổ chức.

### Một conformance pack có bảo đảm đạt chứng nhận ISO 27001 hoặc PCI DSS không?

Không. Pack là framework kiểm tra cấu hình AWS và có thể hỗ trợ thu thập bằng chứng. Việc đạt chuẩn còn phụ thuộc quy trình, con người, phạm vi, bằng chứng và đánh giá của tổ chức/chuyên gia độc lập.

### Vì sao remediation có thể chạy trên tài nguyên đã compliant?

AWS Config dùng compliance data snapshot theo chu kỳ để khởi tạo một số auto-remediation. Snapshot có thể cũ hơn trạng thái hiện tại. Do đó cần kiểm tra trạng thái trong runbook và quản lý scope, đặc biệt khi bật auto cho tài nguyên hiện hữu.

### Khi nào nên bật automatic remediation?

Khi hành động đã được thử nghiệm, có thể chạy lặp lại an toàn, quyền đã giới hạn, có giới hạn concurrency/error và đã đánh giá tác động đến workload. Hành động rủi ro cao nên yêu cầu phê duyệt.

### Làm sao hạn chế tác động khi remediation chạy trên nhiều tài nguyên?

Giới hạn scope, dùng manual mode ở giai đoạn đầu, đặt concurrency/error threshold, triển khai theo nhóm nhỏ, dùng runbook idempotent và theo dõi kết quả theo resource.

## 26. Checklist trước khi đưa vào production

### AWS Config

- [ ] Recorder đã bật trong từng Region cần quản lý.
- [ ] Recorder bao gồm resource type cần đánh giá.
- [ ] Delivery channel và lưu trữ lịch sử được cấu hình.
- [ ] IAM role của Config có quyền tối thiểu.
- [ ] Rule scope và trigger được review.
- [ ] Managed/custom rule được kiểm tra theo tài liệu và Region availability.
- [ ] Proactive evaluation được tích hợp vào pipeline nếu cần deployment gate.

### Conformance pack

- [ ] Template được lưu trong version control.
- [ ] Tên rule và parameter nhất quán.
- [ ] Template không vượt giới hạn kích thước khi truyền trực tiếp.
- [ ] Các rule có trong Region triển khai.
- [ ] S3 bucket policy cho delivery artifact đã được kiểm tra.
- [ ] Pack đã được triển khai thử trong tài khoản kiểm thử.
- [ ] Organization pack có detailed status theo tài khoản.
- [ ] Quota rule/pack được kiểm tra trước rollout.

### Remediation

- [ ] Runbook đã được đọc và thử nghiệm.
- [ ] Automation assume role có trust relationship phù hợp.
- [ ] IAM permission giới hạn theo hành động và tài nguyên.
- [ ] Dynamic parameters ánh xạ đúng resource ID.
- [ ] ConfigRuleName và Automation role ARN là giá trị đầy đủ theo yêu cầu của template.
- [ ] Manual remediation đã thành công trước khi bật auto cho hành động rủi ro.
- [ ] Retry, concurrency và error percentage phù hợp.
- [ ] Có xử lý exception và quy trình rollback.
- [ ] Có giám sát SSM Automation execution và lỗi.

### Governance

- [ ] Có owner cho từng pack và từng ngoại lệ.
- [ ] Có quy trình phê duyệt thay đổi baseline.
- [ ] Có thời hạn cho ngoại lệ.
- [ ] Có báo cáo compliance theo tài khoản/Region.
- [ ] Bằng chứng audit được lưu theo chính sách.
- [ ] Đội vận hành hiểu rõ pack không thay thế đánh giá tuân thủ pháp lý.

## 27. Tài liệu tham khảo chính thức

- [AWS Config terminology and concepts](https://docs.aws.amazon.com/config/latest/developerguide/config-concepts.html)
- [Components of an AWS Config Rule](https://docs.aws.amazon.com/config/latest/developerguide/evaluate-config_components.html)
- [AWS Config Managed Rules](https://docs.aws.amazon.com/config/latest/developerguide/evaluate-config_use-managed-rules.html)
- [Creating AWS Config Custom Policy Rules](https://docs.aws.amazon.com/config/latest/developerguide/evaluate-config_develop-rules_cfn-guard.html)
- [Evaluating resources with AWS Config Rules](https://docs.aws.amazon.com/config/latest/developerguide/evaluating-your-resources.html)
- [Conformance Packs for AWS Config](https://docs.aws.amazon.com/config/latest/developerguide/conformance-packs.html)
- [Creating templates for Custom Conformance Packs](https://docs.aws.amazon.com/config/latest/developerguide/custom-conformance-pack.html)
- [Prerequisites for Conformance Packs](https://docs.aws.amazon.com/config/latest/developerguide/cpack-prerequisites.html)
- [Deploying Conformance Packs](https://docs.aws.amazon.com/config/latest/developerguide/conformance-pack-deploy.html)
- [Managing Organization Conformance Packs](https://docs.aws.amazon.com/config/latest/developerguide/conformance-pack-organization-apis.html)
- [Remediating Noncompliant Resources with AWS Config](https://docs.aws.amazon.com/config/latest/developerguide/remediation.html)
- [Setting Up Auto Remediation](https://docs.aws.amazon.com/config/latest/developerguide/setup-autoremediation.html)
- [PutRemediationConfigurations API](https://docs.aws.amazon.com/config/latest/APIReference/API_PutRemediationConfigurations.html)
- [AWS-DisableS3BucketPublicReadWrite runbook](https://docs.aws.amazon.com/systems-manager-automation-runbooks/latest/userguide/automation-aws-disables3bucketpublicreadwrite.html)
- [Systems Manager Automation IAM roles](https://docs.aws.amazon.com/systems-manager/latest/userguide/automation-setup-iam.html)
- [AWS Config service limits](https://docs.aws.amazon.com/config/latest/developerguide/configlimits.html)
- [Viewing Compliance Data in the Conformance Packs Dashboard](https://docs.aws.amazon.com/config/latest/developerguide/conformance-pack-dashboard.html)
- [Compliance History Timeline for Conformance Packs](https://docs.aws.amazon.com/config/latest/developerguide/compliance-history-conformance-pack.html)


