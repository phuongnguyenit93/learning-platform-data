# Tự động hóa ứng phó bằng EventBridge và Systems Manager

Khi một sự cố xuất hiện, đội vận hành cần nhận biết tín hiệu, xác định tài nguyên bị ảnh hưởng, chọn hành động phù hợp và lưu lại kết quả. Nếu mỗi bước đều phải chờ người trực mở console, tìm đúng tài nguyên rồi chạy lệnh thủ công, thời gian phản ứng sẽ tăng và thao tác dễ thiếu nhất quán.

Amazon EventBridge nhận sự kiện từ dịch vụ AWS, ứng dụng và đối tác, sau đó lọc sự kiện bằng rule và chuyển tới đích xử lý. AWS Systems Manager cung cấp Automation runbook để điều phối nhiều bước, Run Command để chạy lệnh trên managed node và OpsCenter để ghi nhận, phân loại, theo dõi công việc vận hành. Kết hợp hai dịch vụ giúp xây dựng quy trình phản ứng có thể lặp lại, kiểm soát quyền và kiểm tra được.

Bài học thuộc chương **Giám sát an ninh và ứng phó** của module CLOUD_PROVIDERS_AWS. Module giúp người học lựa chọn và vận hành dịch vụ AWS an toàn, có khả năng giám sát, phục hồi và kiểm soát chi phí.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Mô tả luồng từ sự kiện nguồn qua EventBridge đến hành động trong Systems Manager.
- Viết event pattern để chỉ kích hoạt khi sự kiện thỏa điều kiện cần xử lý.
- Chọn giữa Automation, Run Command và OpsCenter theo mức độ phức tạp của phản ứng.
- Truyền dữ liệu từ event vào tham số runbook bằng Input Transformer.
- Phân biệt IAM role cho EventBridge gọi đích và IAM role cho Automation thao tác tài nguyên.
- Thiết kế phản ứng có kiểm soát tác động, chống chạy lặp và có đường xử lý khi target lỗi.
- Theo dõi trạng thái, điều tra lỗi và kiểm thử quy trình trước khi bật tự động hóa trên production.

## 1. Kiến trúc phản ứng theo sự kiện

Một quy trình cơ bản có bốn phần:

1. **Nguồn phát hiện:** GuardDuty, Security Hub CSPM, AWS Config, CloudWatch Alarm, EC2, dịch vụ AWS khác hoặc ứng dụng nội bộ.
2. **Định tuyến:** EventBridge nhận event trên event bus, so khớp event pattern của rule và chọn target.
3. **Thực thi:** Systems Manager Automation chạy runbook nhiều bước, Run Command chạy tài liệu lệnh trên managed node, hoặc OpsCenter tạo OpsItem để điều tra.
4. **Theo dõi:** EventBridge nhận sự kiện trạng thái từ Systems Manager; CloudWatch metrics, CloudTrail, SNS và OpsCenter hỗ trợ giám sát, thông báo và kiểm toán.

~~~mermaid
flowchart TD
    A["GuardDuty / Security Hub / CloudWatch / AWS service"] --> B["EventBridge event bus"]
    B --> C{"Event pattern khớp?"}
    C -->|Không| D["Không gọi target"]
    C -->|Có| E["EventBridge rule"]
    E --> F["Systems Manager Automation"]
    E --> G["Systems Manager Run Command"]
    E --> H["Systems Manager OpsCenter"]
    F --> I["Runbook: kiểm tra, phê duyệt, khắc phục"]
    G --> J["Command document trên managed node"]
    H --> K["OpsItem: điều tra và giao việc"]
    I --> L["Trạng thái thực thi"]
    J --> L
    L --> M["EventBridge / CloudWatch / CloudTrail / thông báo"]
~~~

EventBridge xử lý việc nhận, lọc và chuyển sự kiện. Nó không tự quyết định hành động khắc phục có an toàn hay không. Logic kiểm tra, điều kiện phê duyệt, quyền thao tác và bước phục hồi cần được thiết kế trong runbook hoặc quy trình vận hành.

Một lần EventBridge giao event thành công cũng không đồng nghĩa runbook đã hoàn tất. Việc giao target thành công chỉ cho biết lời gọi target được chấp nhận; kết quả của từng bước Automation phải được theo dõi riêng.

## 2. Vai trò của EventBridge trong quy trình

### 2.1. Event bus, event và rule

Event bus là nơi nhận event. Các event do dịch vụ AWS phát ra trong tài khoản được gửi tới **default event bus** của tài khoản và Region. Bạn có thể tạo custom event bus để tiếp nhận event ứng dụng hoặc phân tách luồng xử lý. EventBridge cũng hỗ trợ event từ đối tác SaaS.

Một event phổ biến có các trường:

| Trường | Ý nghĩa |
|---|---|
| `version` | Phiên bản cấu trúc event |
| `id` | ID của event |
| `source` | Dịch vụ hoặc ứng dụng phát event, ví dụ `aws.guardduty` |
| `detail-type` | Loại sự kiện, ví dụ `GuardDuty Finding` |
| `account` | Tài khoản AWS phát event |
| `region` | Region liên quan |
| `time` | Thời điểm phát event |
| `resources` | Các ARN tài nguyên liên quan |
| `detail` | Dữ liệu cụ thể của sự kiện |

Rule có event pattern để xác định event nào cần chuyển tiếp. Pattern có cấu trúc tương tự event và có thể lọc theo `source`, `detail-type`, tài khoản, Region hoặc trường trong `detail`.

Ví dụ, một rule có thể chỉ xử lý finding có severity cao, chỉ liên quan EC2 instance và chỉ trong tài khoản production đã chỉ định. Rule càng cụ thể thì càng giảm khả năng gọi nhầm runbook.

### 2.2. Event từ dịch vụ AWS và CloudTrail

Một số dịch vụ phát service event trực tiếp tới EventBridge. GuardDuty phát event loại `GuardDuty Finding`; Systems Manager phát event trạng thái Automation và Run Command; EC2 phát event thay đổi trạng thái instance.

Một số thao tác API không có service event tương ứng. Khi đó, có thể tạo rule dựa trên sự kiện API được ghi qua CloudTrail, thường có `detail-type` là `AWS API Call via CloudTrail`. Cách này cần CloudTrail ghi nhận loại sự kiện liên quan và event pattern phải khớp đúng cấu trúc CloudTrail event.

Không nên mặc định mọi dịch vụ có cùng bảo đảm giao event. AWS công bố mức chuyển giao theo từng loại service event; có loại best-effort và có loại durable. Hãy kiểm tra mức giao event của nguồn quan trọng trước khi xem EventBridge là tín hiệu duy nhất cho một quy trình ứng phó.

Với GuardDuty, finding mới có ID duy nhất được gửi gần thời gian thực. Các lần xuất hiện tiếp theo của cùng finding được tổng hợp thành event cập nhật; mặc định GuardDuty gom trong khoảng sáu giờ và tài khoản quản trị có thể chọn chu kỳ 15 phút, một giờ hoặc sáu giờ. Vì vậy, một finding có thể tạo nhiều event theo thời gian dù ID finding vẫn giữ nguyên. Thiết kế idempotency nên dựa trên finding ID cùng hành động và trạng thái hiện tại của tài nguyên.

Finding được tự động archive bởi GuardDuty suppression rule sẽ không được gửi tới EventBridge. Nếu quy trình ứng phó cần nhận các finding đó, hãy rà soát suppression rule và phạm vi sự kiện bị loại.

### 2.3. Rule theo event và lịch chạy

Rule theo event pattern phù hợp khi cần phản ứng ngay khi có thay đổi hoặc finding mới. EventBridge rule cũng hỗ trợ lịch `rate` và `cron`; với lịch chạy mới, có thể cân nhắc EventBridge Scheduler khi cần lịch một lần, múi giờ hoặc quản lý lịch độc lập.

Không dùng lịch chạy định kỳ để thay thế event-driven response nếu mục tiêu là phản ứng ngay khi một sự cố cụ thể xảy ra.

## 3. Chọn target Systems Manager phù hợp

EventBridge có thể gọi nhiều loại target. Với Systems Manager, ba lựa chọn thường gặp là Automation, Run Command và OpsCenter.

| Target | Dùng khi nào | Kết quả mong đợi |
|---|---|---|
| **Automation** | Cần nhiều bước, điều kiện, kiểm tra trạng thái, phê duyệt, gọi API AWS hoặc phối hợp nhiều runbook | Một Automation execution có trạng thái và lịch sử từng bước |
| **Run Command** | Cần chạy một command document trên một hoặc nhiều EC2/hybrid managed node | Một hoặc nhiều command invocation trên managed node |
| **OpsCenter** | Cần tạo công việc điều tra, ưu tiên, giao người xử lý và liên kết runbook | Một OpsItem có trạng thái, tài nguyên liên quan và lịch sử xử lý |

### 3.1. Systems Manager Automation

Automation chạy một tài liệu loại Automation, thường gọi là *runbook*. Runbook có thể:

- Gọi API AWS bằng `aws:executeAwsApi`.
- Chạy script Python hoặc PowerShell bằng `aws:executeScript`.
- Chạy lệnh trên managed node bằng `aws:runCommand`.
- Rẽ nhánh bằng `aws:branch`.
- Chờ trạng thái tài nguyên bằng `aws:waitForAwsResourceProperty`.
- Tạm dừng chờ người phê duyệt bằng `aws:approve`.
- Gọi runbook khác bằng `aws:executeAutomation`.

Automation phù hợp với phản ứng có nhiều điều kiện, ví dụ kiểm tra finding, xác minh tài nguyên, thu thập bằng chứng, chờ phê duyệt rồi cô lập tài nguyên.

AWS cung cấp runbook dựng sẵn như `AWS-CreateImage`, `AWS-StopEC2Instance` và `AWS-QuarantineEC2Instance`. Hãy đọc nội dung và danh sách quyền của runbook trước khi dùng, vì tên gọi ngắn không thể hiện đầy đủ tác động.

### 3.2. Systems Manager Run Command

Run Command gửi command document tới managed node. EventBridge gọi API `SendCommand` thay mặt bạn. Target cần chỉ định tài nguyên bằng instance ID hoặc tag; cấu hình Run Command của EventBridge hỗ trợ từ một đến năm nhóm target.

Run Command phù hợp với thao tác đơn giản như thu thập trạng thái dịch vụ, kiểm tra dung lượng đĩa hoặc chạy script chuẩn hóa. Nếu cần điều kiện, approval, nhiều bước gọi API hoặc xử lý lỗi theo nhánh, hãy đóng gói logic vào Automation runbook.

Managed node cần được đăng ký với Systems Manager, có SSM Agent đang hoạt động, IAM instance profile hoặc cơ chế xác thực phù hợp và kết nối mạng tới endpoint Systems Manager. Việc tạo EventBridge rule không tự cài agent hoặc đăng ký máy chủ.

### 3.3. Systems Manager OpsCenter

OpsCenter tạo OpsItem để nhóm vận hành điều tra và xử lý. OpsItem có thông tin như tiêu đề, mức ưu tiên, mô tả, nguồn, tài nguyên liên quan và trạng thái.

Có thể dùng EventBridge để tạo OpsItem khi:

- GuardDuty hoặc Security Hub phát finding cần người phân tích.
- Automation execution thất bại.
- Một dịch vụ gặp throttling hoặc tài nguyên chuyển sang trạng thái bất thường.
- Một sự kiện cần lưu thành công việc có người chịu trách nhiệm.

OpsCenter có thể gắn runbook vào OpsItem để người trực mở công việc, xem dữ liệu liên quan rồi chạy Automation. OpsCenter cũng có cơ chế hỗ trợ phát hiện OpsItem trùng; hãy cấu hình deduplication string cho rule khi cùng một sự cố có thể tạo nhiều event. OpsItem phát sinh chi phí theo bảng giá Systems Manager, vì vậy event pattern và deduplication cũng giúp kiểm soát số lượng OpsItem được tạo.

## 4. Thiết kế Automation runbook

Runbook Automation được viết bằng YAML hoặc JSON. Tài liệu có khai báo tham số, role thực thi và danh sách `mainSteps`.

Một runbook thường gồm:

- `schemaVersion`: phiên bản schema của Automation document, thường là `'0.3'`.
- `assumeRole`: IAM role mà Automation sử dụng để gọi dịch vụ AWS.
- `parameters`: đầu vào và ràng buộc giá trị.
- `mainSteps`: các bước thực thi theo thứ tự hoặc nhánh.

Ví dụ khung runbook:

~~~yaml
---
description: "Khung kiểm tra tài nguyên trước khi khắc phục"
schemaVersion: '0.3'
assumeRole: '{{ AutomationAssumeRole }}'
parameters:
  AutomationAssumeRole:
    type: String
    description: "ARN của role dành cho Automation"
  InstanceId:
    type: String
    description: "EC2 instance cần kiểm tra"
    allowedPattern: '^i-[0-9a-f]+$'
mainSteps:
  - name: inspectInstance
    action: aws:executeAwsApi
    onFailure: Abort
    inputs:
      Service: ec2
      Api: DescribeInstances
      InstanceIds:
        - '{{ InstanceId }}'
    outputs:
      - Name: InstanceState
        Selector: '$.Reservations[0].Instances[0].State.Name'
        Type: String
  - name: checkInstanceState
    action: aws:assertAwsResourceProperty
    onFailure: Abort
    inputs:
      Service: ec2
      Api: DescribeInstances
      InstanceIds:
        - '{{ InstanceId }}'
      PropertySelector: '$.Reservations[0].Instances[0].State.Name'
      DesiredValues:
        - running
~~~

Đây là khung minh họa cách khai báo tham số, gọi API và xác minh trạng thái. Khi xây runbook thật, hãy đối chiếu tên API, cấu trúc request/response và selector với tài liệu của action đang dùng; một runbook hợp lệ về YAML vẫn có thể thất bại nếu API input hoặc JSONPath không đúng.

### 4.1. Thiết kế tham số an toàn

Tham số nên mô tả đúng đầu vào cần thiết và giới hạn giá trị có thể nhận:

- Dùng `allowedValues` cho danh sách lựa chọn cố định.
- Dùng `allowedPattern` để kiểm tra định dạng ID hoặc tên.
- Dùng `StringList` khi cần danh sách giá trị.
- Đặt giá trị mặc định an toàn nếu runbook có thể được chạy thủ công.
- Không truyền mật khẩu, token hoặc dữ liệu nhạy cảm trong event payload nếu không cần thiết.
- Không nhận ARN tùy ý từ event rồi dùng trực tiếp làm target của hành động có quyền cao.

Event có thể chứa dữ liệu do dịch vụ hoặc người dùng cung cấp. Hãy xác thực tham số và kiểm tra tài nguyên trước khi dùng giá trị đó để thay đổi hạ tầng.

### 4.2. Kiểm soát lỗi trong từng bước

Các thuộc tính như `onFailure`, `onCancel`, `maxAttempts`, `timeoutSeconds` và `nextStep` giúp xác định cách Automation phản ứng khi một bước lỗi hoặc quá thời gian.

Ví dụ:

- Dùng `Abort` khi bước xác minh quan trọng thất bại; không tiếp tục hành động thay đổi tài nguyên.
- Dùng `maxAttempts` cho thao tác có thể lỗi tạm thời và an toàn khi thử lại.
- Dùng `aws:waitForAwsResourceProperty` để chờ trạng thái thay vì giả định API trả về đồng nghĩa thao tác đã hoàn tất.
- Ghi output cần thiết để người trực biết bước nào đã chạy và tài nguyên nào đã thay đổi.

Không nên tự động thử lại vô hạn một bước có tác động không thể lặp an toàn, ví dụ tạo nhiều snapshot hoặc gửi nhiều lệnh thay đổi cấu hình.

## 5. Kết nối EventBridge với Automation

Khi tạo EventBridge rule, chọn event bus, event pattern, sau đó chọn target là **Systems Manager Automation** và runbook cần chạy. Với runbook có tham số bắt buộc, phải truyền đủ giá trị; nếu thiếu tham số, rule vẫn có thể được tạo nhưng target không chạy được khi event đến.

Có hai cách truyền dữ liệu:

- **Input cố định:** truyền giá trị tĩnh vào tham số runbook. Phù hợp với target chạy trên một tài nguyên hoặc cấu hình cố định.
- **Input Transformer:** trích trường từ event bằng JSONPath rồi tạo JSON đầu vào theo tham số của runbook. Phù hợp với sự kiện thay đổi theo từng tài nguyên.

Ví dụ event EC2 có `detail.instance-id`. Input Transformer có thể trích instance ID và truyền thành tham số `InstanceId` cho runbook. Đừng nhầm Input Transformer với `Input` của Run Command target: Run Command dùng `RunCommandParameters` để xác định máy đích và `Input` để khai báo document cùng parameters.

## 6. Ví dụ ứng phó GuardDuty finding trên EC2

Giả sử GuardDuty phát hiện hành vi đáng ngờ liên quan tới một EC2 instance. Quy trình cần:

1. Chỉ nhận finding có mức độ nghiêm trọng đã chọn.
2. Chỉ xử lý finding có tài nguyên là EC2 instance.
3. Lấy instance ID từ event.
4. Chạy runbook để kiểm tra và cô lập instance.
5. Ghi lại trạng thái và thông báo cho đội an ninh.

GuardDuty gửi event với `source` là `aws.guardduty` và `detail-type` là `GuardDuty Finding`. Phần `detail` chứa một finding, bao gồm severity, ID, loại finding và thông tin tài nguyên.

### 6.1. Event pattern lọc finding

Ví dụ sau chọn finding có severity từ 7 trở lên và tài nguyên là EC2 instance. Severity của GuardDuty nằm trong khoảng 1.0 đến 10.0; hãy chọn ngưỡng dựa trên quy trình phân loại của tổ chức.

~~~json
{
  "source": [
    "aws.guardduty"
  ],
  "detail-type": [
    "GuardDuty Finding"
  ],
  "account": [
    "123456789012"
  ],
  "region": [
    "ap-southeast-1"
  ],
  "detail": {
    "severity": [
      {
        "numeric": [
          ">=",
          7
        ]
      }
    ],
    "resource": {
      "resourceType": [
        "Instance"
      ],
      "instanceDetails": {
        "instanceId": [
          {
            "exists": true
          }
        ]
      }
    }
  }
}
~~~

Thay account và Region bằng phạm vi thực tế. Pattern này chỉ minh họa lọc theo severity và loại tài nguyên; production có thể cần thêm điều kiện theo finding type, tài khoản, tag quản trị hoặc nhóm tài nguyên được phép tự động xử lý.

Dùng EventBridge Sandbox để thử pattern với event mẫu của GuardDuty trước khi tạo rule. Kiểm tra cả event cần khớp và event phải bị loại.

### 6.2. Ánh xạ dữ liệu từ event

GuardDuty đặt instance ID tại `detail.resource.instanceDetails.instanceId`. Với runbook có tham số `InstanceId`, Input Transformer có thể trích trường này. Ví dụ:

**Input paths**

~~~json
{
  "instanceId": "$.detail.resource.instanceDetails.instanceId",
  "findingId": "$.detail.id",
  "findingType": "$.detail.type"
}
~~~

**Input template**

~~~json
{
  "InstanceId": [
    <instanceId>
  ],
  "FindingId": [
    <findingId>
  ],
  "FindingType": [
    <findingType>
  ],
  "AutomationAssumeRole": [
    "arn:aws:iam::123456789012:role/AutomationQuarantineRole"
  ],
  "IsolationSecurityGroup": [
    "Quarantine-EC2"
  ]
}
~~~

`FindingId`, `FindingType`, `AutomationAssumeRole` và `IsolationSecurityGroup` là tham số của runbook tùy chỉnh trong ví dụ này. Nếu target là runbook AWS dựng sẵn, chỉ truyền những tham số mà tài liệu đó thực sự khai báo. Input Transformer thay placeholder bằng dữ liệu JSONPath; không tự thêm trường ngoài schema của runbook.

### 6.3. Chọn runbook cô lập

AWS cung cấp runbook `AWS-QuarantineEC2Instance`. Runbook này:

- Thu thập thông tin instance.
- Kiểm tra instance có thuộc Auto Scaling group hay không.
- Tạo snapshot của root volume và chờ snapshot hoàn tất.
- Gán security group cô lập được chỉ định cho instance.

Security group cô lập được dùng để chặn inbound và outbound traffic. Runbook có bước xác minh instance không thuộc Auto Scaling group. Nếu instance đang do Auto Scaling quản lý, điều kiện của runbook không được đáp ứng; hãy thiết kế quy trình riêng có phê duyệt cho lifecycle của nhóm thay vì giả định runbook sẽ detach instance hoặc điều chỉnh desired capacity.

Runbook trả về ID snapshot root volume và ID/tên security group đã bị thu hồi. Hãy lưu các output này vào OpsItem hoặc hồ sơ incident để đội xử lý có dữ liệu đối chiếu khi khôi phục mạng. Nếu instance có các EBS volume khác cần bảo toàn cho điều tra, hãy lập bước snapshot riêng cho chúng.

Vì vậy, hãy xem cô lập tự động là hành động có tác động lớn. Với môi trường quan trọng, có thể gửi finding tới OpsCenter trước, yêu cầu phê duyệt, hoặc chỉ cho phép tự động cô lập instance có tag/nhóm tài nguyên đã được tổ chức chấp thuận. Hãy kiểm tra quyền, RDP settings và cách khôi phục trước khi áp dụng.

### 6.4. Thêm bước phê duyệt

Nếu cần người trực xác nhận trước khi cô lập, tạo một runbook bao ngoài có bước `aws:approve`, sau đó gọi `AWS-QuarantineEC2Instance` bằng `aws:executeAutomation`.

~~~yaml
---
description: "Phê duyệt trước khi cô lập EC2 có GuardDuty finding"
schemaVersion: '0.3'
assumeRole: '{{ AutomationAssumeRole }}'
parameters:
  AutomationAssumeRole:
    type: String
    description: "Role được Automation sử dụng"
  InstanceId:
    type: String
    allowedPattern: '^i-[0-9a-f]+$'
  FindingId:
    type: String
  FindingType:
    type: String
  IsolationSecurityGroup:
    type: String
  ApprovalTopicArn:
    type: String
mainSteps:
  - name: approveContainment
    action: aws:approve
    timeoutSeconds: 3600
    onFailure: Abort
    inputs:
      NotificationArn: '{{ ApprovalTopicArn }}'
      Message: 'GuardDuty finding {{ FindingId }} ({{ FindingType }}) yêu cầu xem xét cô lập EC2 {{ InstanceId }}.'
      MinRequiredApprovals: 1
      Approvers:
        - arn:aws:iam::123456789012:role/SecurityIncidentApprover
  - name: quarantineInstance
    action: aws:executeAutomation
    timeoutSeconds: 7200
    onFailure: Abort
    inputs:
      DocumentName: AWS-QuarantineEC2Instance
      RuntimeParameters:
        InstanceId:
          - '{{ InstanceId }}'
        IsolationSecurityGroup:
          - '{{ IsolationSecurityGroup }}'
        AutomationAssumeRole:
          - '{{ AutomationAssumeRole }}'
~~~

Đây là khung minh họa, cần thay ARN, tham số và quyền theo tài khoản. SNS topic dùng cho approval phải được cấu hình theo yêu cầu của Automation; tên topic cho approval có tiền tố `Automation`. Người phê duyệt phải có quyền `ssm:SendAutomationSignal` trên execution và quyền cần thiết để xem Automation. Bước `aws:approve` không hỗ trợ Automation chạy đa tài khoản và đa Region.

Runbook con được chạy trong ngữ cảnh của principal đã khởi chạy Automation ban đầu. Nếu runbook con khai báo `AutomationAssumeRole`, principal khởi chạy phải có `iam:PassRole` cho role đó; principal này cũng cần `ssm:StartAutomationExecution` trên document con. Vì vậy, khi EventBridge là bên khởi chạy, invocation role phải được cấp các quyền cần thiết để gọi cả runbook bao ngoài lẫn runbook con. Tham số `AutomationAssumeRole` của runbook con cần được truyền rõ trong `RuntimeParameters`.

## 7. Phân tách IAM role

Một thiết kế dễ kiểm toán thường tách hai vai trò:

1. **EventBridge invocation role:** EventBridge assume role này để gọi target, ví dụ bắt đầu Automation execution. Với Systems Manager Automation target, trust policy cho phép `events.amazonaws.com` và `ssm.amazonaws.com`.
2. **Automation assume role:** Systems Manager assume role này để thao tác EC2, EBS, Auto Scaling hoặc dịch vụ liên quan. Trust policy cho phép `ssm.amazonaws.com`.

Không cấp quyền EC2 thay đổi tài nguyên cho EventBridge invocation role nếu role đó chỉ cần khởi chạy runbook. Quyền sửa tài nguyên nên nằm ở Automation role và được giới hạn theo đúng runbook.

Với target Systems Manager Automation, hướng dẫn AWS yêu cầu EventBridge invocation role cho phép cả `events.amazonaws.com` và `ssm.amazonaws.com` trong trust policy. Role này vẫn chỉ cần quyền gọi Automation và pass Automation role. Automation assume role là vai trò riêng, được Systems Manager assume để thao tác tài nguyên và có trust policy cho `ssm.amazonaws.com`.

### 7.1. Trust policy của EventBridge role

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": [
          "events.amazonaws.com",
          "ssm.amazonaws.com"
        ]
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

Policy quyền của role này cần cho phép `ssm:StartAutomationExecution` trên runbook được chỉ định và `iam:PassRole` cho Automation role. Hạn chế tài nguyên theo ARN của document và role cụ thể.

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "StartApprovedRunbook",
      "Effect": "Allow",
      "Action": "ssm:StartAutomationExecution",
      "Resource": [
        "arn:aws:ssm:ap-southeast-1:123456789012:document/GuardDutyQuarantineWithApproval",
        "arn:aws:ssm:ap-southeast-1::document/AWS-QuarantineEC2Instance",
        "arn:aws:ssm:ap-southeast-1:123456789012:automation-execution/*"
      ]
    },
    {
      "Sid": "PassOnlyAutomationRole",
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": "arn:aws:iam::123456789012:role/AutomationQuarantineRole",
      "Condition": {
        "StringEquals": {
          "iam:PassedToService": "ssm.amazonaws.com"
        }
      }
    }
  ]
}
~~~

Trong policy IAM, ví dụ chính thức của Systems Manager cấp `ssm:StartAutomationExecution` trên resource type `document` và `automation-execution`. Trường `Arn` của EventBridge target dùng dạng ARN `automation-definition`; đây là hai ngữ cảnh ARN khác nhau, vì vậy hãy đối chiếu policy với ví dụ IAM của Systems Manager và cấu hình target với tài liệu EventBridge.

### 7.2. Trust policy của Automation role

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

Với `AWS-QuarantineEC2Instance`, tài liệu runbook liệt kê các quyền liên quan gồm:

- `autoscaling:DescribeAutoScalingInstances`
- `autoscaling:DetachInstances`
- `ec2:CreateSecurityGroup`
- `ec2:CreateSnapshot`
- `ec2:DescribeInstances`
- `ec2:DescribeSecurityGroups`
- `ec2:DescribeSnapshots`
- `ec2:ModifyInstanceAttribute`
- `ec2:RevokeSecurityGroupEgress`
- `ec2:RevokeSecurityGroupIngress`

Đây là danh sách tham khảo cho runbook cụ thể đó, không phải policy mẫu để gắn nguyên trạng cho mọi Automation. Với runbook bao ngoài có approval, Automation role cần `sns:Publish` trên SNS topic phê duyệt. Quyền `ssm:StartAutomationExecution` trên document con và `iam:PassRole` để truyền `AutomationAssumeRole` thuộc về principal khởi chạy Automation ban đầu; trong ví dụ này đó là EventBridge invocation role. Hãy đọc phiên bản runbook đang dùng và kiểm tra resource-level permission, điều kiện IAM, quyền SNS approval và quyền gọi runbook con. Tránh dùng `AdministratorAccess` chỉ để làm cho Automation chạy được.

## 8. Cấu hình EventBridge rule bằng AWS CLI

Các ví dụ sau dùng hai file JSON do người triển khai chuẩn bị:

- `guardduty-ec2-high-pattern.json`: event pattern ở mục 6.1.
- `guardduty-automation-target.json`: target và Input Transformer.

Ví dụ file target:

~~~json
[
  {
    "Id": "guardduty-quarantine",
    "Arn": "arn:aws:ssm:ap-southeast-1:123456789012:automation-definition/GuardDutyQuarantineWithApproval",
    "RoleArn": "arn:aws:iam::123456789012:role/EventBridgeInvokeAutomationRole",
    "InputTransformer": {
      "InputPathsMap": {
        "instanceId": "$.detail.resource.instanceDetails.instanceId",
        "findingId": "$.detail.id",
        "findingType": "$.detail.type"
      },
      "InputTemplate": "{\"InstanceId\":[<instanceId>],\"FindingId\":[<findingId>],\"FindingType\":[<findingType>],\"IsolationSecurityGroup\":[\"Quarantine-EC2\"],\"ApprovalTopicArn\":[\"arn:aws:sns:ap-southeast-1:123456789012:Automation-IR-Approval\"],\"AutomationAssumeRole\":[\"arn:aws:iam::123456789012:role/AutomationQuarantineRole\"]}"
    }
  }
]
~~~

Tạo rule và gắn target:

~~~bash
aws events put-rule \
  --name GuardDutyHighEC2Finding \
  --event-pattern file://guardduty-ec2-high-pattern.json \
  --state ENABLED \
  --description "Route high-severity EC2 GuardDuty findings to Systems Manager Automation"

aws events put-targets \
  --rule GuardDutyHighEC2Finding \
  --targets file://guardduty-automation-target.json
~~~

Kết quả `put-targets` cần có `FailedEntryCount` bằng 0. Nếu có lỗi, đọc `FailedEntries` để biết target nào không được thêm. Kiểm tra lại rule, role ARN, document ARN, Input Transformer và các tham số bắt buộc.

Nếu dùng runbook dựng sẵn trực tiếp, ARN của tài liệu AWS-owned thường có account component là `*`, ví dụ `arn:aws:ssm:ap-southeast-1:*:automation-definition/AWS-QuarantineEC2Instance`. Hãy dùng đúng ARN và parameter schema theo tài liệu runbook trong Region triển khai.

## 9. EventBridge gọi Run Command

Với tác vụ đơn giản, EventBridge có thể gọi Run Command trực tiếp. Target cần có:

- ARN của command document.
- IAM role cho phép `ssm:SendCommand` trên document và các instance được phép.
- `RunCommandParameters` để xác định instance ID hoặc tag.
- `Input` chứa tên document, version nếu cần và map `Parameters`.

Ví dụ cấu trúc target rút gọn:

~~~json
{
  "Id": "check-web-service",
  "Arn": "arn:aws:ssm:ap-southeast-1:123456789012:document/AWS-RunShellScript",
  "RoleArn": "arn:aws:iam::123456789012:role/EventBridgeRunCommandRole",
  "Input": "{\"DocumentName\":\"AWS-RunShellScript\",\"Parameters\":{\"commands\":[\"systemctl is-active nginx\"]}}",
  "RunCommandParameters": {
    "RunCommandTargets": [
      {
        "Key": "tag:Environment",
        "Values": [
          "development"
        ]
      }
    ]
  }
}
~~~

Đây là ví dụ kiểm tra trạng thái dịch vụ trên các Linux managed node có tag `Environment=development`. Trước khi chạy, bảo đảm tag target được quản lý chặt và không thể bị gắn nhầm vào máy production.

EventBridge role cho Run Command cần `ssm:SendCommand` trên command document và instance/managed instance mục tiêu. Khi target theo tag, dùng điều kiện IAM theo resource tag để thu hẹp tập máy. Với tài liệu command có khả năng thay đổi hệ thống, review script và giới hạn tham số giống như review một thay đổi phần mềm.

Trust policy của role target Run Command cần cho phép `events.amazonaws.com` assume role. Với target theo tag, policy phải giới hạn quyền trên cả command document và tập managed node có tag được phép; không dùng quyền `ssm:SendCommand` trên mọi instance nếu quy trình chỉ phục vụ một nhóm máy.

## 10. Tạo OpsItem thay vì tự động sửa ngay

Không phải finding nào cũng có thể được xử lý an toàn bằng một hành động tự động. Nếu nguyên nhân chưa rõ, tài nguyên có thể đang phục vụ hệ thống quan trọng hoặc hành động có thể làm mất dữ liệu, hãy tạo OpsItem để người trực phân tích.

Một quy trình điển hình:

1. EventBridge lọc finding theo severity và loại tài nguyên.
2. Rule gửi event tới OpsCenter để tạo OpsItem.
3. OpsItem ghi lại tài nguyên, finding, mô tả và mức ưu tiên.
4. Người trực xem CloudTrail, CloudWatch, GuardDuty và thông tin tài nguyên.
5. Người xử lý chọn runbook phù hợp và thực thi sau khi xác minh.
6. Sau khi khắc phục, cập nhật trạng thái OpsItem thành Resolved và lưu thông tin nguyên nhân.

OpsCenter có thể tích hợp với EventBridge để tạo OpsItem tự động. Dùng deduplication string khi nhiều event có thể đại diện cho cùng một sự cố, ví dụ cùng một tài nguyên và cùng một finding type trong một khoảng thời gian.

## 11. Độ tin cậy: retry, DLQ và event trùng

### 11.1. Retry khi target lỗi

EventBridge rule target có retry policy. Với rule target cổ điển, mặc định EventBridge thử giao event tối đa 24 giờ và tối đa 185 lần, theo exponential backoff và jitter; giới hạn nào đến trước sẽ kết thúc retry. Có thể cấu hình thời gian giữ event và số lần thử lại theo yêu cầu.

Nếu không cấu hình dead-letter queue (DLQ), event không giao được sau khi hết retry có thể bị loại bỏ. Hãy cấu hình SQS DLQ cho target quan trọng và giám sát số event được gửi vào DLQ.

Không nhầm retry của rule target với cấu hình retry của các loại EventBridge subscriber mới trên custom event bus; từng mô hình có giới hạn mặc định riêng. Luôn kiểm tra loại event bus và cơ chế target đang triển khai.

### 11.2. Thiết kế idempotency

Một event có thể được giao lại hoặc một rule có thể được gọi nhiều lần cho cùng một event. Vì vậy, hành động phản ứng phải an toàn khi lặp.

Các cách thường dùng:

- Dùng `event.id` hoặc GuardDuty `findingId` kết hợp resource ID và action để tạo khóa xử lý.
- Lưu trạng thái đã xử lý bằng DynamoDB conditional write hoặc cơ chế khóa tương đương.
- Trước khi thay đổi tài nguyên, đọc trạng thái hiện tại và chỉ thay đổi khi điều kiện còn đúng.
- Gắn tag/metadata theo incident ID để hỗ trợ đối chiếu.
- Dùng tên tài nguyên, snapshot và ticket có quy ước để phát hiện kết quả đã tồn tại.

Đừng dựa vào giả định một finding chỉ tạo một event hoặc một target chỉ được gọi đúng một lần.

### 11.3. Ngăn vòng lặp vô hạn

Một rule có thể tự kích hoạt lại nếu hành động khắc phục tạo ra event mà chính rule đó đang lắng nghe. Ví dụ, rule phát hiện thay đổi security group rồi chạy runbook sửa security group có thể tiếp tục nhận event do chính runbook tạo ra.

Để tránh vòng lặp:

- Lọc đúng `source`, `detail-type` và trường trạng thái cần xử lý.
- Chỉ match chuyển trạng thái từ điều kiện xấu sang trạng thái cần chú ý.
- Loại trừ thay đổi do automation hoặc gắn tag để nhận diện nguồn thay đổi.
- Không tạo rule quá rộng như match mọi event từ một dịch vụ nếu chỉ cần một event type.
- Theo dõi số lần invocation và chi phí sau khi bật rule.

### 11.4. Xử lý DLQ và replay

DLQ giúp giữ lại record của event không giao được để điều tra. Trước khi redrive hoặc replay, cần xác minh tài nguyên hiện tại và trạng thái incident; phát lại một event cũ có thể chạy lại hành động đã được xử lý.

Nếu SQS DLQ được mã hóa bằng customer managed KMS key, key policy phải cho phép EventBridge dùng key theo hướng dẫn của dịch vụ. Queue policy cũng phải cho phép đúng EventBridge rule gửi message.

## 12. Theo dõi kết quả Automation

EventBridge phát metric cho việc giao target, còn Systems Manager ghi lại tiến trình Automation execution. Hai nhóm tín hiệu này trả lời hai câu hỏi khác nhau:

- **EventBridge:** Event có khớp rule và được giao tới target không?
- **Systems Manager:** Runbook có khởi chạy và hoàn tất các bước khắc phục không?

Các EventBridge metrics nên theo dõi:

| Metric | Ý nghĩa |
|---|---|
| `InvocationAttempts` | Tổng số lần EventBridge thử gọi target, gồm retry |
| `SuccessfulInvocationAttempts` | Số lần gọi target thành công |
| `RetryInvocationAttempts` | Số lần retry khi giao target |
| `FailedInvocations` | Số lần invocation thất bại vĩnh viễn; không gồm invocation đang retry, thành công sau retry hoặc đã được tính ở `DeadLetterInvocations` |
| `DeadLetterInvocations` | Số lần rule không gọi target cho event; có thể bao gồm trường hợp EventBridge chặn vòng lặp vô hạn |
| `InvocationsSentToDlq` | Số event được chuyển tới DLQ |
| `InvocationsFailedToBeSentToDlq` | Số lần EventBridge không thể gửi invocation tới DLQ, thường do lỗi quyền, queue hoặc giới hạn kích thước |
| `IngestionToInvocationSuccessLatency` | Độ trễ từ khi nhận event đến khi gọi target thành công |

Có thể tạo CloudWatch Alarm khi `FailedInvocations` tăng, DLQ có message hoặc độ trễ giao target vượt ngưỡng. Kết hợp `SuccessfulInvocationAttempts` và `InvocationAttempts` để đánh giá tỷ lệ giao thành công.

Metric EventBridge được gửi tới CloudWatch theo cơ chế best-effort; chúng hữu ích để theo dõi xu hướng và phát hiện bất thường, nhưng không phải sổ kiểm toán đầy đủ cho từng event.

Systems Manager phát event khi Automation execution hoặc step thay đổi trạng thái. Có thể tạo rule riêng với:

- `source`: `aws.ssm`
- `detail-type`: `EC2 Automation Execution Status-change Notification` hoặc `EC2 Automation Step Status-change Notification`
- `detail.Status`: `Failed`, `Success`, `TimedOut`, `Canceled` hoặc trạng thái cần theo dõi.

Khi Automation thất bại, gửi thông báo tới SNS, tạo OpsItem hoặc mở quy trình xử lý dự phòng. Hãy giới hạn pattern theo đúng trạng thái và runbook để rule thông báo không phản ứng với mọi Automation trong tài khoản.

Event trạng thái của Systems Manager được phát theo cơ chế best-effort. Hãy dùng Automation execution history và CloudTrail làm nguồn điều tra bổ sung thay vì dựa duy nhất vào event trạng thái để xác nhận kết quả.

### 12.1. Lưu dấu vết và kiểm toán

Dùng nhiều nguồn log theo đúng vai trò:

- **Systems Manager Automation execution history:** trạng thái, step, input, output và lỗi của từng lần chạy.
- **CloudWatch Logs:** lưu output của các bước `aws:executeScript` khi đã cấu hình logging.
- **CloudTrail:** ghi nhận các API như `StartAutomationExecution`, `SendCommand` và thao tác thay đổi tài nguyên.
- **EventBridge metrics và logs đã cấu hình:** theo dõi match, invocation, retry, latency và lỗi target.
- **OpsCenter:** lưu trạng thái điều tra, người xử lý, tài nguyên và runbook liên quan.

Không ghi secret, token hoặc dữ liệu cá nhân vào output của runbook. Hãy áp dụng retention và quyền đọc log phù hợp với mức nhạy cảm của sự cố.

## 13. Kiểm soát blast radius và tốc độ thực thi

Tự động hóa có thể biến một lỗi cấu hình nhỏ thành thay đổi trên nhiều tài nguyên. Trước khi bật, hãy giới hạn phạm vi:

- Chỉ cho phép target trong account, Region và tag được chỉ định.
- Dùng danh sách finding type được phê duyệt thay vì tự động xử lý mọi finding.
- Dùng approval cho hành động có thể làm ngừng dịch vụ hoặc mất kết nối quản trị.
- Thử nghiệm trên development/staging trước.
- Chạy theo từng nhóm nhỏ, đo kết quả rồi mới mở rộng.
- Với Automation chạy trên nhiều target qua `StartAutomationExecution` hoặc bước `aws:executeAutomation`, dùng `MaxConcurrency` và `MaxErrors` để kiểm soát số lượng chạy song song và ngưỡng lỗi. EventBridge target đơn giản không tự đặt các giới hạn này chỉ bằng Input Transformer.
- Chuẩn bị runbook rollback hoặc quy trình khôi phục quyền truy cập.
- Theo dõi quota và khả năng tiếp nhận Automation execution khi có đợt finding lớn.

`MaxErrors` là ngưỡng để ngừng gửi Automation tới các target mới sau số lỗi đã định; những execution đang chạy có thể vẫn hoàn tất hoặc thất bại. Ví dụ, đặt `MaxErrors=3` thì Automation dừng gửi tới target mới khi nhận lỗi thứ tư. Nếu cần giới hạn số execution lỗi vượt ngưỡng, giảm `MaxConcurrency` xuống 1 để xử lý tuần tự hơn.

Không tự động dừng, terminate hoặc cô lập toàn bộ instance chỉ dựa vào một event chưa được xác minh. Hãy kết hợp finding, vai trò tài nguyên, tag, quan hệ Auto Scaling và mức độ quan trọng của workload.

## 14. Chạy Automation đa tài khoản và đa Region

Trong tổ chức lớn, sự kiện có thể phát sinh ở nhiều tài khoản và Region. Có thể dùng EventBridge event bus policy để chuyển event từ tài khoản thành viên tới bus tập trung; sau đó rule ở tài khoản trung tâm phân loại và gọi target phù hợp.

Systems Manager Automation hỗ trợ một số kịch bản thực thi đa tài khoản và đa Region thông qua cơ chế target locations, runbook chia sẻ và IAM role ở tài khoản đích. Khi thiết kế, cần xác định:

- Tài khoản nào phát hiện, tài khoản nào điều phối và tài khoản nào sở hữu tài nguyên.
- Event bus policy cho phép đúng tài khoản/nguồn gửi event.
- Runbook được chia sẻ đúng phạm vi và phiên bản.
- Role ở tài khoản đích chỉ cho phép hành động cần thiết.
- Kết quả của child automation được thu thập và đối chiếu ở tài khoản điều phối.

Với GuardDuty delegated administrator, trường `detail.accountId` xác định tài khoản thành viên phát sinh finding. Trường `account` ở cấp event biểu thị tài khoản phát event; hãy chọn đúng trường khi muốn chỉ xử lý một member account trong môi trường tập trung.

Bước `aws:approve` không hỗ trợ Automation đa tài khoản và đa Region. Nếu cần phê duyệt tập trung cho quy trình nhiều tài khoản, hãy thiết kế bước approval ở lớp điều phối phù hợp thay vì giả định approval step hoạt động trong mọi mô hình.

## 15. Kiểm thử trước khi bật phản ứng tự động

Kiểm thử theo từng lớp giúp tìm lỗi mà không cần tạo sự cố thật.

1. **Kiểm tra event schema:** Lấy sample event của dịch vụ và xác nhận trường cần dùng tồn tại.
2. **Kiểm tra event pattern:** Dùng EventBridge Sandbox hoặc `test-event-pattern` để xác nhận event đúng được match và event ngoài phạm vi bị loại.
3. **Kiểm tra Input Transformer:** Thử với event mẫu và xem JSON đầu ra có đúng kiểu dữ liệu, tên tham số và giá trị bắt buộc.
4. **Kiểm tra runbook độc lập:** Chạy runbook thủ công trên tài nguyên thử nghiệm với tham số kiểm soát.
5. **Kiểm tra IAM:** Xác nhận EventBridge assume được invocation role, được gọi đúng target và pass đúng Automation role.
6. **Kiểm tra approval:** Xác nhận SNS topic nhận được thông báo và đúng principal có thể approve/reject.
7. **Kiểm tra DLQ:** Dùng target thử nghiệm có quyền bị từ chối có kiểm soát để xác nhận lỗi được ghi nhận theo retry policy.
8. **Kiểm tra lặp:** Gửi lại cùng dữ liệu thử nghiệm và xác nhận runbook không tạo tác động trùng.
9. **Kiểm tra rollback:** Thực hiện quy trình phục hồi trong môi trường test.
10. **Bật theo từng nhóm:** Theo dõi metric, execution history và OpsItem trước khi mở rộng.

Có thể dùng AWS CLI để kiểm tra event pattern:

~~~bash
aws events test-event-pattern \
  --event-pattern file://guardduty-ec2-high-pattern.json \
  --event file://sample-guardduty-finding.json
~~~

Lệnh trả về `Result: true` nếu event khớp pattern. Lệnh này chỉ kiểm tra bộ lọc; nó không chạy Automation và không xác minh IAM target.

Kiểm tra trạng thái rule và target:

~~~bash
aws events describe-rule \
  --name GuardDutyHighEC2Finding

aws events list-targets-by-rule \
  --rule GuardDutyHighEC2Finding
~~~

Kiểm tra kết quả Automation khi đã có execution ID:

~~~bash
aws ssm get-automation-execution \
  --automation-execution-id <AUTOMATION_EXECUTION_ID>
~~~

Không dùng finding production hoặc instance đang phục vụ người dùng để thử hành động cô lập. Hãy dùng tài nguyên thử nghiệm có thể khôi phục.

## 16. Xử lý sự cố thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Rule không khớp event | Sai `source`, `detail-type`, tên trường, kiểu số hoặc Region | Xem raw event; dùng EventBridge Sandbox/test-event-pattern |
| Rule khớp nhưng target không chạy | Target chưa gắn, thiếu tham số bắt buộc hoặc target ARN sai | `list-targets-by-rule`, kiểm tra `FailedEntries` và target ARN |
| EventBridge báo AccessDenied | Invocation role thiếu quyền hoặc trust policy không cho `events.amazonaws.com` | Kiểm tra trust relationship, `ssm:StartAutomationExecution` và `iam:PassRole` |
| Automation báo thiếu quyền | Automation role thiếu API permission hoặc policy có explicit Deny | Xem step lỗi, CloudTrail và IAM policy của assume role |
| Automation không assume được role | ARN sai hoặc trust policy không cho `ssm.amazonaws.com` | Kiểm tra role tồn tại, trust relationship và tham số `AutomationAssumeRole` |
| Run Command không có kết quả | Instance chưa là managed node, agent offline hoặc thiếu quyền | Kiểm tra Managed nodes, SSM Agent, instance profile và kết nối endpoint |
| Input Transformer lỗi | JSONPath không tồn tại hoặc template không tạo JSON hợp lệ | Kiểm tra event mẫu, input paths và template trong Sandbox |
| Event vào DLQ | Target throttling, role thiếu quyền, tài nguyên không tồn tại hoặc retry hết hạn | Đọc error code/message của DLQ, metric retry và target logs |
| Một event tạo nhiều execution | Event giao lặp, finding cập nhật hoặc rule bị trùng | Đối chiếu event ID/finding ID; thêm idempotency guard |
| Automation thành công nhưng tài nguyên chưa đổi như mong đợi | Runbook kiểm tra trạng thái rồi kết thúc, target không đúng hoặc bước đổi trạng thái chưa được gọi | Xem step execution, outputs và resource ID |
| Instance mất kết nối quản trị sau quarantine | Security group cô lập chặn cả đường SSM/SSH/RDP | Dùng quy trình break-glass và runbook khôi phục đã được phê duyệt |
| Rule tự kích hoạt liên tục | Hành động khắc phục phát event khớp lại cùng rule | Thu hẹp event pattern, loại trừ thay đổi do automation và kiểm tra số invocation |

Khi chẩn đoán, xác định lỗi xảy ra ở giai đoạn nào: event không tới bus, pattern không khớp, target không được gọi, Automation không khởi chạy, hay một step trong runbook thất bại. Mỗi giai đoạn có log và quyền khác nhau.

## 17. Tình huống thực hành

Một tài khoản AWS có EC2 chạy ứng dụng nội bộ. GuardDuty phát hiện finding có severity cao liên quan đến instance. Nhóm an ninh muốn lưu bằng chứng, thông báo người trực và cô lập máy khi đã xác nhận.

Hãy thiết kế luồng xử lý đáp ứng các yêu cầu:

- Chỉ nhận finding EC2 có severity từ ngưỡng do nhóm an ninh chọn.
- Lấy đúng instance ID và finding ID từ event.
- Tạo OpsItem để nhóm an ninh có thể theo dõi.
- Chờ phê duyệt trước khi chạy runbook cô lập.
- Sau khi Automation kết thúc, gửi thông báo kết quả.
- Không chạy lặp hành động cô lập khi cùng finding được gửi lại.

Một phương án:

1. EventBridge rule lọc GuardDuty finding theo `source`, `detail-type`, `severity`, `resourceType` và account/Region.
2. Rule chuyển event tới OpsCenter để tạo OpsItem và tới Automation wrapper runbook.
3. Input Transformer ánh xạ instance ID, finding ID và finding type thành tham số.
4. Runbook kiểm tra tài nguyên, tag quản trị và trạng thái hiện tại.
5. Runbook dùng `aws:approve` để chờ người trực phê duyệt.
6. Sau khi duyệt, runbook gọi `AWS-QuarantineEC2Instance`.
7. Automation execution status event kích hoạt rule thông báo thành công hoặc thất bại.
8. Runbook hoặc lớp điều phối ghi finding ID và trạng thái xử lý vào nơi lưu idempotency để event trùng không lặp lại thay đổi.
9. Người trực cập nhật OpsItem, lưu lý do và theo dõi quy trình khôi phục.

Khi đánh giá thiết kế, hãy giải thích vì sao OpsCenter vẫn cần thiết dù có Automation, role nào được phép bắt đầu runbook, role nào được phép thay đổi EC2 và cách khôi phục quyền truy cập sau cô lập.

## 18. Những lỗi thiết kế cần tránh

**Match mọi event từ một dịch vụ.** Điều này có thể gọi runbook quá nhiều lần và tạo chi phí ngoài dự kiến. Hãy lọc theo event type và thuộc tính có ý nghĩa.

**Dùng một IAM role có quyền quản trị cho mọi target.** Nếu role bị lộ hoặc rule cấu hình sai, phạm vi tác động sẽ rất lớn. Tách role và thu hẹp quyền theo document, resource và action.

**Cho phép event quyết định trực tiếp tài nguyên cần thay đổi.** Event có thể thiếu trường hoặc chứa giá trị không phù hợp. Xác minh resource ID, account, Region, tag và trạng thái trước khi hành động.

**Coi target invocation thành công là remediation thành công.** EventBridge giao request và Automation hoàn tất là hai trạng thái riêng. Theo dõi cả hai.

**Bỏ qua event trùng.** Một event lặp có thể tạo nhiều snapshot, nhiều OpsItem hoặc nhiều lần thay đổi tài nguyên. Thiết kế idempotency ngay từ đầu.

**Tự động cô lập mọi EC2 có finding.** Một instance có thể thuộc hệ thống quan trọng, Auto Scaling group hoặc đang giữ dữ liệu cần bảo toàn. Phân loại tài nguyên và đặt approval cho hành động có blast radius lớn.

**Không có DLQ hoặc cảnh báo lỗi giao target.** Event bị loại bỏ sau khi hết retry có thể khiến nhóm vận hành không biết quy trình đã bỏ sót sự cố.

**Không chuẩn bị bước khôi phục.** Cô lập, dừng hoặc thay đổi cấu hình có thể làm mất quyền truy cập. Cần có runbook phục hồi và quyền break-glass được kiểm soát.

## 19. Câu hỏi tự kiểm tra

1. EventBridge đảm nhiệm phần nào trong quy trình ứng phó?
2. `source` và `detail-type` khác nhau như thế nào?
3. Vì sao event pattern nên lọc theo tài khoản và Region?
4. Khi nào nên chọn Automation thay vì Run Command?
5. OpsCenter giải quyết vấn đề gì mà Automation execution history không thay thế hoàn toàn?
6. Input Transformer giúp ích gì khi event chứa instance ID thay đổi theo từng lần phát?
7. Vì sao tham số từ event cần được kiểm tra trước khi dùng trong runbook?
8. EventBridge invocation role và Automation assume role có nhiệm vụ khác nhau ra sao?
9. `aws:approve` giúp kiểm soát rủi ro nào?
10. Vì sao EventBridge target invocation thành công chưa chứng minh hành động khắc phục đã hoàn tất?
11. DLQ giúp xử lý tình huống nào?
12. Làm thế nào để tránh một runbook tự tạo event khiến rule chạy lặp?
13. Vì sao cần idempotency khi cùng finding có thể được gửi nhiều lần?
14. Khi nào nên tạo OpsItem thay vì tự động cô lập tài nguyên?
15. Cần kiểm tra gì trước khi áp dụng runbook quarantine cho EC2 production?

## 20. Checklist trước khi vận hành

- [ ] Nguồn event, event type, account và Region đã được xác định.
- [ ] Event pattern đã được thử với event mẫu đúng và sai.
- [ ] Input Transformer ánh xạ đủ tham số, đúng kiểu dữ liệu.
- [ ] Runbook đã được review nội dung, version, action và output.
- [ ] EventBridge role chỉ được gọi đúng target và pass đúng Automation role.
- [ ] Automation role chỉ có quyền cần thiết cho runbook.
- [ ] Managed node đã sẵn sàng nếu quy trình có Run Command.
- [ ] Hành động có tác động lớn có điều kiện phê duyệt hoặc phạm vi cho phép rõ ràng.
- [ ] Đã có idempotency guard và cơ chế tránh vòng lặp.
- [ ] Retry policy và SQS DLQ được cấu hình.
- [ ] Có CloudWatch alarm cho lỗi giao target, retry và DLQ.
- [ ] Có rule theo dõi trạng thái Automation execution.
- [ ] CloudTrail, Automation history và log cần thiết được lưu giữ.
- [ ] Có quy trình rollback, break-glass và người chịu trách nhiệm.
- [ ] Đã thử trên development/staging trước khi bật production.

## Kết luận

EventBridge và Systems Manager tạo thành một nền tảng phản ứng theo sự kiện: EventBridge nhận và lọc tín hiệu, còn Systems Manager thực thi quy trình đã định nghĩa hoặc tạo OpsItem để người vận hành xử lý. Chất lượng của hệ thống phụ thuộc vào event pattern chính xác, runbook có kiểm tra đầu vào, IAM role tối thiểu, cơ chế approval cho hành động rủi ro, xử lý event trùng và quan sát đầy đủ từ lúc nhận event đến khi remediation hoàn tất.

## Tài liệu AWS tham khảo

- [Run automations based on EventBridge events](https://docs.aws.amazon.com/systems-manager/latest/userguide/running-automations-event-bridge.html)
- [Sample scenarios: Systems Manager targets in EventBridge rules](https://docs.aws.amazon.com/systems-manager/latest/userguide/monitoring-systems-manager-targets.html)
- [Event bus targets in Amazon EventBridge](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-targets.html)
- [Processing GuardDuty findings with Amazon EventBridge](https://docs.aws.amazon.com/guardduty/latest/ug/guardduty_findings_eventbridge.html)
- [AWS-QuarantineEC2Instance runbook](https://docs.aws.amazon.com/systems-manager-automation-runbooks/latest/userguide/aws-quarantineec2instance.html)
- [Systems Manager Automation actions reference](https://docs.aws.amazon.com/systems-manager/latest/userguide/automation-actions.html)
- [aws:executeAutomation action](https://docs.aws.amazon.com/systems-manager/latest/userguide/automation-action-executeAutomation.html)
- [aws:approve action](https://docs.aws.amazon.com/systems-manager/latest/userguide/automation-action-approve.html)
- [Setting up Systems Manager Automation](https://docs.aws.amazon.com/systems-manager/latest/userguide/automation-setup.html)
- [Systems Manager Automation identity-based policy examples](https://docs.aws.amazon.com/systems-manager/latest/userguide/automation-setup-identity-based-policies.html)
- [Systems Manager IAM actions, resources, and condition keys](https://docs.aws.amazon.com/service-authorization/latest/reference/list_awssystemsmanager.html)
- [IAM roles for EventBridge targets](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-events-iam-roles.html)
- [Amazon EventBridge input transformation](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-transform-target-input.html)
- [Passing data to Automation using input transformers](https://docs.aws.amazon.com/systems-manager/latest/userguide/automation-tutorial-eventbridge-input-transformers.html)
- [EventBridge retry policies and dead-letter queues](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-rule-retry-policy.html)
- [Monitoring Amazon EventBridge](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-monitoring.html)
- [Systems Manager event examples for EventBridge](https://docs.aws.amazon.com/systems-manager/latest/userguide/monitoring-systems-manager-event-examples.html)
- [Systems Manager OpsCenter](https://docs.aws.amazon.com/systems-manager/latest/userguide/OpsCenter.html)
- [Configure EventBridge rules to create OpsItems](https://docs.aws.amazon.com/systems-manager/latest/userguide/OpsCenter-automatically-create-OpsItems-2.html)
- [Monitoring Systems Manager events with EventBridge](https://docs.aws.amazon.com/systems-manager/latest/userguide/monitoring-eventbridge-events.html)
- [Amazon EventBridge event patterns and types for Systems Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/reference-eventbridge-events.html)
- [Testing event patterns with EventBridge Sandbox](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-event-pattern-sandbox.html)

