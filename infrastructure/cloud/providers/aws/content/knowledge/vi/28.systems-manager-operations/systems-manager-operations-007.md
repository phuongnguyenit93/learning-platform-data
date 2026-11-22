# Automation runbook và xử lý sự cố lặp lại

## Mục tiêu bài học

Trong hệ sinh thái CLOUD_PROVIDERS_AWS, AWS Systems Manager cung cấp các công cụ vận hành để quản lý tài nguyên và managed node trên quy mô lớn. Automation biến một quy trình vận hành thành runbook có thể chạy lặp lại với đầu vào, quyền thực thi, điều kiện, bước phê duyệt, kết quả và lịch sử thực thi rõ ràng. Khi kết hợp với Amazon EventBridge, Amazon CloudWatch và OpsCenter, runbook có thể trở thành một phần của quy trình tiếp nhận và xử lý sự cố.

Sau bài học, người học có thể:

- Phân biệt Automation runbook với Command document, Run Command, State Manager và Maintenance Windows.
- Đọc cấu trúc một Automation document và lựa chọn action phù hợp.
- Thiết kế runbook có tham số, kiểm tra đầu vào, phân nhánh, hậu kiểm và xử lý lỗi.
- Cấu hình IAM assume role theo nguyên tắc quyền tối thiểu và hiểu quyền của người khởi chạy.
- Kết nối runbook với EventBridge, lịch vận hành, CloudWatch alarm và quy trình xử lý OpsItem.
- Kiểm soát việc chạy trên nhiều tài nguyên bằng concurrency, error threshold và phê duyệt.
- Theo dõi execution, điều tra lỗi và cải tiến runbook để xử lý sự cố lặp lại an toàn.

## 1. Automation giải quyết vấn đề vận hành nào?

Trong vận hành hệ thống, nhiều sự cố có cùng một mẫu xử lý: xác định tài nguyên bị ảnh hưởng, thu thập trạng thái, kiểm tra điều kiện, thực hiện hành động khắc phục, xác nhận dịch vụ đã phục hồi và ghi lại kết quả. Nếu mỗi lần đều thao tác thủ công, kết quả dễ khác nhau giữa các kỹ sư, thời gian phản hồi kéo dài và khó chứng minh ai đã làm gì.

AWS Systems Manager Automation chuẩn hóa quy trình đó thành một chuỗi bước có thể thực thi và kiểm tra. Runbook có thể thao tác trên các tài nguyên AWS như EC2, EBS, RDS, S3, CloudFormation và các managed node thông qua Run Command. Một runbook có thể gọi API AWS, chạy script Python hoặc PowerShell, khởi chạy runbook khác, chờ một trạng thái tài nguyên, yêu cầu phê duyệt hoặc thực thi lệnh trên máy chủ.

Ví dụ, khi dịch vụ web trên EC2 liên tục dừng, nhóm vận hành có thể xây dựng quy trình:

1. Nhận diện instance và dịch vụ bị ảnh hưởng.
2. Kiểm tra instance có đang chạy và còn kết nối với Systems Manager hay không.
3. Thu thập trạng thái dịch vụ và log cần thiết.
4. Yêu cầu người có thẩm quyền phê duyệt nếu thao tác có thể gây gián đoạn.
5. Khởi động lại dịch vụ.
6. Kiểm tra dịch vụ đã hoạt động và endpoint ứng dụng trả về kết quả mong đợi.
7. Ghi lại execution ID, kết quả, thời gian và nguyên nhân.

Runbook giúp nhóm thực hiện cùng một quy trình cho mọi lần xảy ra sự cố. Tuy nhiên, tự động hóa chỉ nên thực hiện những hành động đã được hiểu rõ và có điều kiện an toàn. Một cảnh báo chưa đủ thông tin không nên tự động kích hoạt thao tác có thể làm mất dữ liệu hoặc ảnh hưởng diện rộng.

## 2. Phân biệt Automation với các tính năng Systems Manager khác

Systems Manager có nhiều loại document và cơ chế vận hành. Chọn đúng loại giúp runbook dễ bảo trì và tránh nhầm lẫn về cách thực thi.

| Thành phần | Mục đích | Ví dụ |
|---|---|---|
| Automation runbook | Điều phối workflow nhiều bước trên tài nguyên AWS hoặc managed node | Kiểm tra EC2, xin phê duyệt, khởi động lại dịch vụ, xác minh |
| Command document | Định nghĩa các lệnh chạy trên managed node thông qua SSM Agent | AWS-RunShellScript, AWS-RunPowerShellScript |
| Run Command | Gửi một Command document tới một hoặc nhiều managed node | Chạy lệnh kiểm tra dung lượng đĩa trên EC2 |
| State Manager | Duy trì trạng thái cấu hình mong muốn bằng association và lịch thực thi | Đảm bảo agent hoặc cấu hình được cài đặt định kỳ |
| Maintenance Windows | Lập lịch cửa sổ bảo trì cho các tác vụ vận hành | Chạy cập nhật hoặc automation trong khung giờ bảo trì |

Automation runbook là document type Automation, dùng schema version 0.3. Command document dùng schema khác, thường là 1.2, 2.0 hoặc 2.2. Một Automation runbook có thể gọi Command document bằng action aws:runCommand; hai document phục vụ hai tầng khác nhau của workflow.

Hãy dùng Automation khi cần điều phối nhiều bước, điều kiện, quyền thực thi, phê duyệt hoặc thao tác trên nhiều dịch vụ AWS. Nếu chỉ cần chạy một tập lệnh trên một nhóm máy chủ, Run Command có thể đã đủ. Nếu cần liên tục duy trì một cấu hình mong muốn, State Manager phù hợp hơn. Nếu tác vụ phải chạy trong cửa sổ bảo trì đã định trước, Maintenance Windows có thể gọi Automation hoặc Run Command làm task.

## 3. Thành phần của một Automation runbook

Runbook được lưu dưới dạng Systems Manager document. Nội dung có thể viết bằng YAML hoặc JSON. Một runbook thường gồm:

- description: mô tả mục đích.
- schemaVersion: phiên bản schema của document; Automation dùng 0.3.
- assumeRole: IAM role mà Automation assume để thực hiện hành động.
- parameters: đầu vào do người gọi cung cấp, có thể kèm kiểu dữ liệu, mặc định và ràng buộc.
- mainSteps: các bước thực thi theo thứ tự.
- outputs: giá trị kết quả muốn công bố từ những bước có output phù hợp.

Mỗi phần tử trong mainSteps có một tên duy nhất và một action. Action quyết định đầu vào, hành vi và output của bước. Một bước có thể tham chiếu output của bước trước bằng cú pháp {{ stepName.outputName }}. Nhờ đó, runbook có thể lấy ID tài nguyên từ một API call rồi chuyển ID đó cho bước tiếp theo.

Ví dụ cấu trúc tối giản:

~~~yaml
description: Kiem tra trang thai mot EC2 instance
schemaVersion: '0.3'
parameters:
  InstanceId:
    type: String
    description: ID cua EC2 instance can kiem tra
mainSteps:
  - name: describeInstance
    action: aws:executeAwsApi
    inputs:
      Service: ec2
      Api: DescribeInstances
      InstanceIds:
        - '{{ InstanceId }}'
    outputs:
      - Name: InstanceState
        Selector: '$.Reservations[0].Instances[0].State.Name'
        Type: String
~~~

Đây là ví dụ minh họa cấu trúc. Khi triển khai, cần bổ sung ràng buộc đầu vào, IAM permissions, xử lý trường hợp API không trả về instance và bước kiểm tra kết quả. Với action aws:executeAwsApi, Selector dùng JSONPath để trích dữ liệu từ phản hồi API. Với action chờ hoặc xác nhận trạng thái, PropertySelector xác định thuộc tính cần so sánh.

## 4. Các Automation action thường dùng

Automation có nhiều action chuyên biệt. Không cần viết script cho mọi thao tác; ưu tiên action có sẵn vì chúng mô tả rõ mục đích và output.

| Action | Chức năng | Tình huống phù hợp |
|---|---|---|
| aws:executeAwsApi | Gọi API của dịch vụ AWS | Đọc trạng thái EC2, tạo snapshot, cập nhật tag |
| aws:executeScript | Chạy Python hoặc PowerShell trong runbook | Chuẩn hóa dữ liệu, tính toán hoặc xử lý logic không có action riêng |
| aws:runCommand | Gọi Command document trên managed node | Kiểm tra dịch vụ, dung lượng đĩa hoặc chạy lệnh khắc phục |
| aws:branch | Chuyển sang bước khác theo điều kiện | Chọn nhánh Linux/Windows hoặc chỉ khắc phục khi đủ điều kiện |
| aws:approve | Tạm dừng chờ principal phê duyệt hoặc từ chối | Restart dịch vụ quan trọng, thay đổi cấu hình production |
| aws:waitForAwsResourceProperty | Chờ một thuộc tính tài nguyên đạt giá trị mong muốn | Chờ instance, volume hoặc image chuyển trạng thái |
| aws:assertAwsResourceProperty | Kiểm tra thuộc tính có giá trị mong muốn | Dừng workflow nếu điều kiện trước khi thay đổi không đúng |
| aws:executeAutomation | Gọi một Automation runbook khác | Tách workflow lớn thành runbook có thể tái sử dụng |
| aws:invokeLambdaFunction | Gọi hàm Lambda | Tích hợp logic tùy chỉnh đã được đóng gói trong Lambda |
| aws:loop | Lặp qua các bước | Xử lý danh sách phần tử trong workflow |
| aws:sleep | Tạm dừng trong khoảng thời gian xác định | Chờ trước một lần kiểm tra tiếp theo |

Các thuộc tính dùng chung của step còn có:

- maxAttempts: số lần thử lại khi bước thất bại; mặc định là một lần.
- timeoutSeconds: giới hạn thời gian thực thi của bước.
- onFailure: Abort, Continue hoặc chuyển tới một step khác.
- onCancel: xác định bước xử lý khi execution bị hủy, trong giới hạn và các loại action được hỗ trợ.

Không nên đặt retry cao cho mọi lỗi. Lỗi quyền IAM, tham số sai hoặc tài nguyên không tồn tại thường không tự hết khi thử lại. Retry hữu ích hơn với lỗi tạm thời, throttling hoặc dịch vụ đang chuyển trạng thái. Với thao tác có side effect, phải bảo đảm lần thử lại không tạo thêm tài nguyên hoặc lặp một thay đổi ngoài ý muốn.

## 5. Thiết kế tham số và kiểm soát đầu vào

Tham số làm cho một runbook có thể dùng lại cho nhiều tài nguyên. Thay vì viết riêng một document cho từng EC2 instance, người vận hành truyền InstanceId, tên dịch vụ, môi trường hoặc mức độ xử lý khi chạy.

Các kiểu dữ liệu thường dùng gồm String, StringList, Boolean, Integer, MapList và các kiểu khác theo schema của Systems Manager. Có thể xác định default, allowedValues, allowedPattern, minItems, maxItems và mô tả để giới hạn đầu vào.

Ví dụ:

~~~yaml
parameters:
  InstanceId:
    type: String
    description: EC2 instance ID
    allowedPattern: '^i-[0-9a-f]{8,17}$'
  ServiceName:
    type: String
    description: Ten systemd service tren Linux
    allowedPattern: '^[A-Za-z0-9_.@-]{1,64}$'
  Environment:
    type: String
    allowedValues:
      - development
      - staging
      - production
~~~

Ràng buộc tham số giúp phát hiện lỗi sớm và giảm khả năng người vận hành truyền nhầm tài nguyên. Với tham số được chèn vào shell command hoặc script, cần giới hạn ký tự hợp lệ, kiểm tra giá trị ở bước đầu và tránh nối trực tiếp chuỗi tùy ý vào câu lệnh. Không đưa mật khẩu, access key, token hoặc secret vào tham số văn bản thông thường; dùng cơ chế quản lý bí mật phù hợp và phân quyền truy cập riêng.

Một runbook production nên yêu cầu các thông tin đủ để xác định chính xác đối tượng và phạm vi thay đổi. Ví dụ, thay vì chỉ nhận một InstanceId, quy trình có thể kiểm tra tag Environment, Application và Owner trước khi cho phép khắc phục.

## 6. IAM assume role và quyền thực thi

Có hai lớp quyền cần phân biệt:

1. **Quyền của người hoặc hệ thống khởi chạy:** quyết định principal có được gọi ssm:StartAutomationExecution trên document hay không, có được truyền role hay không và có được xem, dừng hoặc gửi tín hiệu cho execution hay không.
2. **Quyền của Automation assume role:** quyết định những API AWS và hành động trên managed node mà workflow được phép thực hiện.

Khi runbook có assumeRole, Systems Manager sử dụng IAM role đó để thực hiện các bước. Trust policy của role phải cho phép dịch vụ Systems Manager assume role. Policy gắn với role cần có quyền tối thiểu cho đúng action và đúng tài nguyên. Ví dụ, runbook gọi EC2 API cần quyền EC2 tương ứng; runbook gọi aws:runCommand cần quyền gửi Command document tới managed node và document liên quan.

Người khởi chạy cần quyền iam:PassRole cho Automation role được truyền vào khi thao tác yêu cầu. Không cấp iam:PassRole trên mọi role trong tài khoản. Hãy giới hạn ARN role được phép truyền và giới hạn document nào principal được quyền thực thi.

Nếu không chỉ định assume role, Automation sử dụng quyền của principal khởi chạy. Cách này có thể phù hợp với tác vụ ngắn, đơn giản, nhưng khó tách quyền người vận hành khỏi quyền thực thi khi runbook cần quyền cao hơn. Với workflow production, nên dùng một Automation service role riêng có trust policy, policy quyền tối thiểu, logging và quy trình rà soát.

Một số trường hợp cần chỉ định service role, chẳng hạn association của State Manager chạy runbook, tác vụ dự kiến kéo dài hơn 12 giờ, hoặc runbook không do AWS sở hữu dùng aws:executeScript để gọi AWS API hay thao tác trên tài nguyên. Khi aws:executeScript gọi API AWS, Automation assume role là bắt buộc. Role đó cũng phải có quyền đối với dịch vụ được gọi.

Đối với managed node, cần bảo đảm SSM Agent hoạt động, instance profile hoặc cơ chế credential tương ứng có quyền Systems Manager, và node có kết nối tới các endpoint cần thiết. Quyền của Automation role không tự thay thế quyền kết nối và đăng ký managed node.

## 7. Kết nối runbook với lịch và sự kiện

Runbook có thể được khởi chạy thủ công từ Systems Manager console hoặc AWS CLI. Với công việc lặp lại, có thể dùng lịch hoặc sự kiện để tránh phụ thuộc vào thao tác của con người.

### 7.1. Amazon EventBridge

EventBridge có thể dùng runbook làm target của rule. Rule có thể chạy theo lịch hoặc khi một sự kiện AWS khớp với event pattern. Ví dụ:

- EC2 chuyển sang trạng thái running và cần thực hiện bước bootstrap.
- Một sự kiện thay đổi trạng thái tài nguyên cần kích hoạt quy trình kiểm tra.
- Một lịch định kỳ cần rà soát tài nguyên, dọn dẹp hoặc kiểm tra trạng thái.
- Một sự kiện từ dịch vụ AWS cần tạo workflow chẩn đoán hoặc remediation.

EventBridge cần role cho phép gọi Systems Manager Automation và truyền các tham số bắt buộc cho runbook. Khi tham số được lấy từ event payload, dùng input transformer để chuyển dữ liệu sự kiện thành cấu trúc đầu vào phù hợp. Nếu rule được tạo nhưng thiếu giá trị cho một tham số bắt buộc, target có thể không chạy được.

Sự kiện có thể được gửi lại khi target lỗi. Vì vậy, runbook nên có tính idempotent và kiểm tra trạng thái hiện tại trước khi thay đổi. Không giả định rằng mỗi sự kiện chỉ được xử lý đúng một lần.

### 7.2. Lịch bảo trì

Với tác vụ có khung giờ cố định, Maintenance Windows có thể lập lịch task chạy Automation. Ví dụ, nhóm nền tảng chạy kiểm tra sau cập nhật vào cuối tuần hoặc thực hiện một quy trình bảo trì định kỳ ngoài giờ cao điểm.

Có thể dùng EventBridge schedule cho lịch chạy runbook đơn giản. Dùng Maintenance Windows khi cần quản lý cửa sổ bảo trì, task, target và giới hạn thực thi theo quy trình vận hành.

### 7.3. CloudWatch alarm và OpsCenter

Có thể gắn CloudWatch alarm vào một Automation execution để theo dõi điều kiện trong khi workflow đang chạy. Nếu alarm chuyển sang ALARM, execution có thể bị hủy và chạy nhánh onCancel đã định nghĩa. Đây là cơ chế bảo vệ khi hệ thống xấu đi trong lúc remediation.

OpsCenter cho phép liên kết OpsItem với Automation runbook để xử lý vấn đề. Người vận hành có thể xem thông tin liên quan như CloudWatch metrics, alarm, CloudTrail logs và AWS Config, sau đó chạy runbook phù hợp để khắc phục. Hãy xác định rõ runbook nào được phép chạy tự động và runbook nào cần người vận hành xác nhận.

## 8. Phê duyệt và kiểm soát thay đổi

Không phải mọi remediation đều nên chạy tự động hoàn toàn. Có thể chia hành động theo mức độ rủi ro:

| Mức độ | Ví dụ | Cách kiểm soát |
|---|---|---|
| Chẩn đoán, không thay đổi | Thu thập trạng thái instance, log hoặc cấu hình | Có thể tự động khi quyền đọc đã được giới hạn |
| Thay đổi ít rủi ro, có thể đảo ngược | Thêm tag chuẩn, chạy lại một agent đã dừng | Kiểm tra điều kiện, giới hạn target và ghi log |
| Có thể gây gián đoạn | Restart dịch vụ, detach volume, thay đổi cấu hình mạng | Yêu cầu phê duyệt hoặc change window |
| Có thể mất dữ liệu hoặc ảnh hưởng diện rộng | Xóa tài nguyên, thay đổi database, thao tác trên fleet lớn | Phê duyệt nhiều cấp, backup, canary, rollback và xác nhận phạm vi |

Action aws:approve tạm dừng Automation cho đến khi các principal được chỉ định chấp thuận hoặc từ chối. Có thể gửi thông báo qua SNS; tên topic SNS dùng cho approval phải bắt đầu bằng Automation. Có thể yêu cầu một hoặc nhiều approval. Mặc định, bước approval chờ tối đa 7 ngày và có thể cấu hình timeout đến 30 ngày. Nếu hết thời gian mà chưa có đủ approval, workflow không tự tiếp tục như thể đã được duyệt.

Một số giới hạn cần lưu ý: aws:approve không hỗ trợ automation đa tài khoản và đa Region. Với quy trình cần approval trên nhiều tài khoản hoặc Region, cần thiết kế cơ chế phê duyệt phù hợp ở tầng điều phối hoặc chia workflow theo phạm vi được hỗ trợ.

Khi có thay đổi quan trọng, lưu lại lý do, ticket, người phê duyệt, thời gian, tài nguyên và document version đã chạy. Approval phải xuất hiện trước bước có side effect; không đặt sau khi thao tác đã hoàn tất.

## 9. Chạy trên nhiều tài nguyên với rate controls

Automation hỗ trợ mapping target bằng ID hoặc tiêu chí như tag. Khi chạy trên fleet, cần kiểm soát số lượng tài nguyên xử lý đồng thời và số lỗi cho phép trước khi dừng gửi execution tới các target tiếp theo.

- **MaxConcurrency:** số lượng hoặc tỷ lệ phần trăm target được xử lý đồng thời. Ví dụ 1 chạy tuần tự; 10% cho phép tối đa 10% target chạy cùng lúc.
- **MaxErrors:** số lượng hoặc tỷ lệ lỗi cho phép trước khi dừng gửi Automation tới các target mới. Nếu đặt 0, hệ thống dừng gửi thêm sau lỗi đầu tiên.

Các execution đã bắt đầu khi error threshold đạt vẫn được phép hoàn tất và cũng có thể thất bại. Nếu cần hạn chế số lỗi vượt ngưỡng, đặt concurrency bằng 1 để xử lý tuần tự. Với thay đổi có tác động lớn, nên bắt đầu từ một canary nhỏ, kiểm tra kết quả rồi mới tăng tỷ lệ.

Ví dụ chiến lược triển khai cho 100 EC2 instance:

| Giai đoạn | Target | Concurrency | Error threshold | Mục tiêu |
|---|---:|---:|---:|---|
| Canary | 1 instance | 1 | 0 | Xác minh lệnh và hậu kiểm |
| Mở rộng nhỏ | 10 instance | 1 hoặc 10% | 1 | Phát hiện vấn đề khi tác động còn nhỏ |
| Mở rộng | Phần còn lại | Theo tỷ lệ đã kiểm chứng | Theo SLO vận hành | Hoàn tất khi metrics ổn định |

Con số trong bảng là ví dụ thiết kế, không phải giá trị mặc định của AWS. Hãy điều chỉnh theo khả năng phục hồi, tải ứng dụng, thời gian bảo trì và giới hạn dịch vụ. Nếu runbook gọi nhiều bước có thể gây gián đoạn, hãy cân nhắc rate control ở cấp execution và điều kiện dừng trong từng bước.

## 10. Ví dụ: runbook khởi động lại dịch vụ Linux có phê duyệt

Giả sử ứng dụng trên EC2 thường gặp tình trạng tiến trình web bị dừng. Nhóm muốn chuẩn hóa việc khởi động lại service, nhưng production phải có người phê duyệt trước khi thay đổi.

Workflow mẫu:

~~~mermaid
flowchart TD
    A[CloudWatch alarm hoặc OpsItem] --> B[Nhận InstanceId và ServiceName]
    B --> C[Kiểm tra tham số và phạm vi]
    C --> D{Có đủ điều kiện?}
    D -- Không --> E[Dừng và ghi lý do]
    D -- Có --> F[Chờ approval]
    F --> G{Được phê duyệt?}
    G -- Không hoặc timeout --> H[Abort và lưu quyết định]
    G -- Có --> I[SSM Run Command: restart service]
    I --> J[Kiểm tra systemctl is-active]
    J --> K{Dịch vụ hoạt động?}
    K -- Có --> L[Ghi kết quả thành công]
    K -- Không --> M[Đánh dấu cần điều tra]
~~~

Ví dụ Automation document dưới đây minh họa các thành phần quan trọng. Hãy thay ARN của role, SNS topic và approver bằng tài nguyên thuộc tài khoản của tổ chức. Runbook chỉ phù hợp với Linux instance có SSM Agent hoạt động và service được quản lý bằng systemd.

~~~yaml
description: Restart a Linux service after approval
schemaVersion: '0.3'
assumeRole: '{{ AutomationAssumeRole }}'

parameters:
  AutomationAssumeRole:
    type: String
    description: IAM role for Systems Manager Automation
  InstanceId:
    type: String
    description: EC2 instance to remediate
    allowedPattern: '^i-[0-9a-f]{8,17}$'
  ServiceName:
    type: String
    description: systemd service name
    allowedPattern: '^[A-Za-z0-9_.@-]{1,64}$'
  ApprovalTopicArn:
    type: String
    description: SNS topic whose name starts with Automation
  ApproverArns:
    type: StringList
    description: IAM users or roles allowed to approve

mainSteps:
  - name: approveRestart
    action: aws:approve
    timeoutSeconds: 3600
    onFailure: Abort
    inputs:
      NotificationArn: '{{ ApprovalTopicArn }}'
      Message: 'Approve restart of {{ ServiceName }} on {{ InstanceId }}.'
      MinRequiredApprovals: 1
      Approvers: '{{ ApproverArns }}'

  - name: restartService
    action: aws:runCommand
    timeoutSeconds: 600
    onFailure: Abort
    inputs:
      DocumentName: AWS-RunShellScript
      InstanceIds:
        - '{{ InstanceId }}'
      Parameters:
        commands:
          - 'set -e'
          - 'systemctl restart {{ ServiceName }}'
          - 'systemctl is-active --quiet {{ ServiceName }}'
          - 'systemctl --no-pager status {{ ServiceName }}'
~~~

Phân tích các điểm quan trọng:

- schemaVersion: '0.3' xác định đây là Automation document.
- assumeRole xác định role dùng để thực thi các bước.
- allowedPattern giới hạn ID instance và ký tự trong tên service. Điều này giảm rủi ro chèn lệnh khi giá trị tham số được thay vào shell command.
- aws:approve tạm dừng workflow và gửi thông báo tới SNS topic. Nếu bị từ chối hoặc hết timeout, bước restart không được chạy.
- aws:runCommand gọi Command document AWS-RunShellScript trên instance được chỉ định.
- systemctl is-active --quiet làm bước hậu kiểm. Nếu service không active, lệnh trả mã lỗi và Automation đánh dấu bước thất bại.

Ví dụ này cố ý chỉ có một action aws:runCommand. Automation hỗ trợ nhiều Run Command action trong một runbook, nhưng output của chỉ một Run Command action được hỗ trợ tại một thời điểm. Nếu cần thu thập diagnostics trước khi restart và hậu kiểm bằng nhiều lần gọi Run Command, hãy thiết kế cách lưu và truy xuất output rõ ràng, chẳng hạn CloudWatch Logs hoặc S3, thay vì giả định mọi action đều có output trực tiếp trong cùng execution.

Trước khi dùng production, cần bổ sung các bước kiểm tra tag môi trường, trạng thái EC2, quyền của managed node, change window, log và rollback phù hợp. Không chạy lệnh restart trên mọi instance cùng lúc chỉ vì một alarm đã phát sinh.

## 11. Khởi chạy và theo dõi execution bằng AWS CLI

Có thể tạo Automation document bằng console, Document Builder hoặc AWS CLI. Với file YAML đã chuẩn bị, ví dụ lệnh tạo document:

~~~bash
aws ssm create-document \
  --name "RestartLinuxServiceWithApproval" \
  --document-type "Automation" \
  --document-format "YAML" \
  --content file://restart-linux-service.yml \
  --region ap-southeast-1
~~~

Khi chạy, truyền tham số theo đúng kiểu của document. Ví dụ file parameters.json:

~~~json
{
  "AutomationAssumeRole": [
    "arn:aws:iam::123456789012:role/SSMAutomationRole"
  ],
  "InstanceId": [
    "i-0123456789abcdef0"
  ],
  "ServiceName": [
    "nginx"
  ],
  "ApprovalTopicArn": [
    "arn:aws:sns:ap-southeast-1:123456789012:Automation-ApprovalRequest"
  ],
  "ApproverArns": [
    "arn:aws:iam::123456789012:role/OperationsApprover"
  ]
}
~~~

Khởi chạy và lưu AutomationExecutionId được trả về:

~~~bash
aws ssm start-automation-execution \
  --document-name "RestartLinuxServiceWithApproval" \
  --parameters file://parameters.json \
  --region ap-southeast-1
~~~

Theo dõi trạng thái và chi tiết từng bước:

~~~bash
aws ssm get-automation-execution \
  --automation-execution-id "EXECUTION_ID" \
  --region ap-southeast-1
~~~

Nếu execution đang chờ approval, người có thẩm quyền có thể gửi tín hiệu chấp thuận hoặc từ chối:

~~~bash
aws ssm send-automation-signal \
  --automation-execution-id "EXECUTION_ID" \
  --signal-type "Approve" \
  --payload "Comment=Approved after checking the maintenance ticket." \
  --region ap-southeast-1
~~~

Thay Approve bằng Deny khi từ chối. Người vận hành cũng có thể dừng execution bằng stop-automation-execution. Cần lưu execution ID trong ticket hoặc OpsItem để liên kết thao tác với sự cố gốc.

Document có version riêng. Mỗi lần cập nhật nội dung sẽ tạo một version mới; có thể chọn version mặc định. Trong môi trường production, hãy kiểm thử version mới, xem lại thay đổi và chỉ chuyển default version sau khi đã xác nhận. Với các workflow yêu cầu khả năng tái lập, chỉ định rõ document version khi khởi chạy thay vì phụ thuộc vào latest có thể thay đổi theo thời gian.

## 12. Logging, giám sát và lưu vết

Một runbook dùng cho xử lý sự cố phải để lại đủ thông tin cho người trực tiếp xử lý và người điều tra sau đó. Nên theo dõi:

- Automation execution ID, document name và version.
- Thời điểm bắt đầu, kết thúc, người hoặc service khởi chạy.
- Parameters đã dùng, tài nguyên mục tiêu và AWS account/Region.
- Tên step, action, trạng thái, thời lượng và lỗi trả về.
- Approval decision, approver, comment và thời điểm.
- Kết quả hậu kiểm, rollback và trạng thái cuối của incident.

Systems Manager console và API GetAutomationExecution cho phép xem trạng thái tổng thể và StepExecutions. Với step lỗi, kiểm tra output của step và FailureMessage để xác định API hoặc action gây lỗi.

Có thể gửi output từ action aws:executeScript tới CloudWatch Logs để debug. Cấu hình logging này áp dụng ở cấp tài khoản; Systems Manager không tự tạo log group hoặc log stream cho document không dùng aws:executeScript. Nếu log group được mã hóa bằng KMS, output gửi tới log group cũng được mã hóa theo cấu hình. Với output của Run Command, cấu hình CloudWatch Output hoặc S3 output riêng theo nhu cầu.

Không ghi secret, token, mật khẩu, dữ liệu cá nhân hoặc nội dung nhạy cảm vào message, script output hay log nếu không cần thiết. Quyền đọc log và execution history cũng cần được giới hạn theo vai trò. Đặt retention policy cho CloudWatch Logs và S3 để cân bằng yêu cầu kiểm toán, khả năng điều tra và chi phí lưu trữ.

## 13. Xử lý lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Không khởi chạy được execution | Thiếu ssm:StartAutomationExecution hoặc không được phép dùng document | Kiểm tra IAM policy của principal và ARN document |
| Lỗi iam:PassRole | Người khởi chạy không được truyền Automation role | Giới hạn và cấp iam:PassRole đúng role ARN |
| Không assume được role | Role không tồn tại, trust policy sai hoặc ARN không hợp lệ | Kiểm tra trust principal ssm.amazonaws.com, ARN và policy |
| AccessDenied trong step | Automation role thiếu quyền API của dịch vụ đích | Đối chiếu action trong runbook với IAM policy |
| aws:runCommand không tới instance | Instance không phải managed node, SSM Agent lỗi hoặc thiếu kết nối endpoint | Kiểm tra Fleet Manager, SSM Agent, instance profile và network |
| Step bị timeout | timeoutSeconds quá ngắn hoặc dịch vụ đích phản hồi chậm | Kiểm tra output step, thời gian thực tế và trạng thái tài nguyên |
| API trả về không có tài nguyên | ID sai, Region sai hoặc tài nguyên đã bị xóa | Kiểm tra account, Region, tham số và quyền đọc |
| Runbook thất bại sau khi retry | Lỗi đầu vào hoặc lỗi quyền không thể khắc phục bằng retry | Phân loại lỗi trước khi tăng maxAttempts |
| Approval ở trạng thái Waiting | Chưa đủ approver chấp thuận hoặc notification không tới người nhận | Kiểm tra SNS topic, approver ARN, timeout và execution ID |
| Một số target thất bại khi chạy fleet | Tag target không khớp, quyền không đồng đều hoặc rate controls dừng gửi thêm | Xem kết quả từng target, target mapping và error threshold |

Quy trình điều tra nên bắt đầu từ step đầu tiên thất bại, không chỉ nhìn trạng thái tổng thể. Xác định action gọi API nào, input thực tế là gì, role nào thực thi, service trả lỗi gì và tài nguyên có đang ở trạng thái mong đợi không. Sau khi sửa nguyên nhân, chạy lại bằng tham số đã được kiểm tra và document version đã xác minh.

Nếu dùng runbook như remediation cho một incident, cần ghi nhận lý do automation không thể tự xử lý và chuyển sang người trực. Không tự động lặp lại một thao tác thay đổi trạng thái khi nguyên nhân gốc chưa rõ.

## 14. Thiết kế runbook có khả năng phục hồi và an toàn

Một runbook tốt không chỉ kết thúc bằng trạng thái Success. Nó cần có điều kiện đầu vào, hành động, hậu điều kiện và cách xử lý khi một bước không đạt kết quả.

**Tính idempotent:** chạy lại cùng một runbook không nên tạo thêm tài nguyên hoặc làm thay đổi trạng thái không cần thiết. Ví dụ, trước khi tạo snapshot mới, kiểm tra snapshot phù hợp đã tồn tại hay chưa. Trước khi restart service, kiểm tra trạng thái service và điều kiện cần thiết.

**Precondition và postcondition:** xác minh tài nguyên đúng phạm vi trước khi thay đổi; sau thao tác, xác minh trạng thái thực tế. API trả về thành công không đồng nghĩa ứng dụng đã phục hồi.

**Timeout và retry:** đặt timeout theo đặc tính của từng API hoặc script. Retry có giới hạn, có khoảng chờ phù hợp và chỉ áp dụng cho lỗi có khả năng tạm thời.

**Rollback hoặc recovery path:** với thay đổi có thể gây gián đoạn, chuẩn bị cách quay lại trạng thái trước đó, chẳng hạn khôi phục cấu hình, dùng AMI hoặc snapshot đã kiểm tra. Không giả định rollback luôn an toàn; nó cũng cần điều kiện và phê duyệt.

**Canary và blast radius:** chạy thử trên một tài nguyên không quan trọng, sau đó một nhóm nhỏ rồi mới mở rộng. Dùng tag có ý nghĩa và kiểm tra lại target trước khi thao tác.

**Document version và thay đổi:** quản lý runbook như mã nguồn. Review thay đổi, lưu version, kiểm thử ở staging, xác định người sở hữu và quy trình phát hành default version.

**Human handoff:** nếu phát hiện dữ liệu bất thường, thiếu thông tin hoặc điều kiện vượt ngưỡng, dừng remediation và chuyển incident cho người có thẩm quyền.

## 15. Chi phí và giới hạn vận hành

Automation có quota về số execution chạy đồng thời. Tài liệu AWS hiện mô tả quota mặc định 100 Automation đồng thời cho mỗi tài khoản; có thể opt-in adaptive concurrency để tự điều chỉnh quota, tối đa 500 execution đồng thời theo cơ chế AWS công bố. Execution cha, execution con và các execution có rate control đều ảnh hưởng đến số lượng đang chạy. Khi xử lý fleet lớn, cần xem quota hiện tại của tài khoản và Region, không chỉ dựa vào số lượng instance.

AWS cũng đã thay đổi free tier của Systems Manager Automation: khách hàng mới từ ngày 14/08/2025 không còn được áp dụng free tier Automation; free tier cho khách hàng hiện hữu kết thúc ngày 31/12/2025. Vì vậy, tại thời điểm bài học này được biên soạn, cần tính chi phí Automation theo bảng giá hiện hành. Các dịch vụ được gọi trong runbook như EC2, Lambda, CloudWatch Logs, SNS, S3 hoặc KMS có thể phát sinh chi phí riêng.

Các biện pháp kiểm soát chi phí:

- Tránh chạy automation quá thường xuyên nếu sự kiện có thể được gom nhóm hoặc khử trùng lặp.
- Giới hạn target và concurrency theo mục tiêu vận hành.
- Dùng timeout và điều kiện kết thúc để tránh execution kéo dài.
- Chỉ ghi log cần thiết và đặt retention phù hợp.
- Theo dõi số lần execution, lỗi và chi phí theo account, Region, document và nhóm tài nguyên.

## 16. Quy trình triển khai từ thử nghiệm đến production

Có thể triển khai runbook theo các giai đoạn sau:

1. **Mô tả sự cố:** ghi lại dấu hiệu, phạm vi ảnh hưởng, nguyên nhân thường gặp và quy trình xử lý hiện tại.
2. **Chuẩn hóa thao tác:** tách phần chẩn đoán, quyết định, thay đổi, hậu kiểm và rollback.
3. **Chọn action:** ưu tiên API action hoặc action có sẵn; chỉ dùng script khi cần logic tùy chỉnh.
4. **Thiết kế tham số và IAM:** giới hạn tài nguyên, validate đầu vào và tách quyền khởi chạy khỏi quyền thực thi.
5. **Viết runbook:** đặt tên step rõ ràng, timeout, retry, onFailure, approval và output.
6. **Kiểm thử staging:** thử tình huống thành công, tham số sai, thiếu quyền, timeout, target không sẵn sàng và approval bị từ chối.
7. **Chạy canary:** giới hạn một hoặc vài tài nguyên, kiểm tra hậu kiểm và tác động thực tế.
8. **Tích hợp:** nối với EventBridge, CloudWatch alarm, Maintenance Windows hoặc OpsCenter sau khi luồng thủ công đã ổn định.
9. **Phát hành:** review, tạo document version, đổi default version theo quy trình change management.
10. **Vận hành:** theo dõi execution, lỗi, thời gian phục hồi và tỷ lệ remediation thành công; cập nhật runbook khi ứng dụng hoặc kiến trúc thay đổi.

Các chỉ số hữu ích gồm thời gian từ alert đến bắt đầu xử lý, thời gian phục hồi dịch vụ, tỷ lệ runbook thành công, tỷ lệ phải chuyển cho người trực, tỷ lệ rollback và số lần remediation lặp lại. Những chỉ số này giúp đánh giá liệu tự động hóa có giảm MTTR và lỗi thao tác hay không.

## 17. Bài tập thực hành

Một ứng dụng nội bộ chạy trên EC2 có service nginx. Trong tháng vừa qua, service bị dừng nhiều lần và nhóm vận hành thường phải đăng nhập từng máy để khởi động lại. Hãy thiết kế một runbook có thể tái sử dụng với các yêu cầu:

- Nhận InstanceId và ServiceName làm tham số.
- Chỉ cho phép service name có ký tự hợp lệ.
- Dùng Automation assume role với quyền tối thiểu.
- Gửi approval tới người trực trước khi restart production.
- Gọi AWS-RunShellScript để restart service.
- Kiểm tra systemctl is-active sau khi restart.
- Lưu execution ID vào ticket và cấu hình log phù hợp.
- Chạy thử trên một instance staging trước khi mở rộng.

Sau đó, thử phân tích các tình huống:

1. Instance không xuất hiện trong Fleet Manager.
2. Người khởi chạy có ssm:StartAutomationExecution nhưng thiếu iam:PassRole.
3. Approval bị từ chối.
4. Service restart thành công nhưng health check của ứng dụng vẫn thất bại.
5. Runbook chạy trên 20 instance và hai instance đầu tiên trả lỗi.
6. EventBridge gửi lại cùng một sự kiện.
7. Một document version mới có lỗi và cần quay lại version trước.

Kết quả mong đợi là một runbook có thể giải thích được từng quyết định, giới hạn tác động và chuyển cho người trực khi điều kiện không an toàn.

## Kết luận

AWS Systems Manager Automation biến quy trình vận hành thành runbook có thể lặp lại, kiểm soát và theo dõi. Runbook kết hợp tham số, action, output, điều kiện, IAM assume role và approval để xử lý công việc trên AWS resources hoặc managed node. EventBridge, lịch bảo trì, CloudWatch alarm và OpsCenter giúp đưa runbook vào luồng vận hành thực tế.

Khi tự động hóa xử lý sự cố, hãy xác minh phạm vi trước khi thay đổi, giới hạn quyền và concurrency, yêu cầu phê duyệt cho hành động gây gián đoạn, kiểm tra kết quả sau thao tác và lưu lại execution history. Runbook chỉ nên tự động xử lý trường hợp đã có điều kiện rõ ràng; trường hợp bất thường cần dừng an toàn và chuyển cho người có trách nhiệm.

## Tài liệu tham khảo

- [AWS Systems Manager Automation](https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-automation.html)
- [Creating your own runbooks](https://docs.aws.amazon.com/systems-manager/latest/userguide/automation-documents.html)
- [Authoring Automation runbooks](https://docs.aws.amazon.com/systems-manager/latest/userguide/automation-authoring-runbooks.html)
- [Systems Manager Automation actions reference](https://docs.aws.amazon.com/systems-manager/latest/userguide/automation-actions.html)
- [Setting up Automation and configuring service roles](https://docs.aws.amazon.com/systems-manager/latest/userguide/automation-setup.html)
- [aws:approve – Pause an automation for manual approval](https://docs.aws.amazon.com/systems-manager/latest/userguide/automation-action-approve.html)
- [aws:runCommand – Run a command on a managed instance](https://docs.aws.amazon.com/systems-manager/latest/userguide/automation-action-runcommand.html)
- [Run automations based on EventBridge events](https://docs.aws.amazon.com/systems-manager/latest/userguide/running-automations-event-bridge.html)
- [Control automations at scale](https://docs.aws.amazon.com/systems-manager/latest/userguide/running-automations-scale-controls.html)
- [Logging Automation action output with CloudWatch Logs](https://docs.aws.amazon.com/systems-manager/latest/userguide/automation-action-logging.html)
- [Troubleshooting Systems Manager Automation](https://docs.aws.amazon.com/systems-manager/latest/userguide/automation-troubleshooting.html)
- [Remediate OpsItem issues](https://docs.aws.amazon.com/systems-manager/latest/userguide/OpsCenter-remediating.html)
- [AWS Systems Manager pricing](https://aws.amazon.com/systems-manager/pricing/)

