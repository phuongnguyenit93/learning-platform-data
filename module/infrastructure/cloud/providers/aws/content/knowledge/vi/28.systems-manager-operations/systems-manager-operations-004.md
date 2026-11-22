# State Manager và duy trì cấu hình mong muốn

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích vai trò của AWS Systems Manager State Manager trong quản lý cấu hình và giảm configuration drift.
- Mô tả association và mối liên hệ giữa SSM document, target, parameter, schedule và IAM role.
- Chọn Command, Policy hoặc Automation document cho từng tình huống.
- Đăng ký EC2 và máy chủ hybrid thành managed nodes để State Manager có thể điều phối.
- Chọn target bằng tag, Resource Groups, node ID hoặc toàn bộ managed nodes trong tài khoản và Region.
- Thiết kế lịch chạy, schedule offset, concurrency và error threshold phù hợp với quy mô fleet.
- Dùng Systems Manager Compliance, execution history và Amazon S3 output để theo dõi kết quả.
- Phân tách quyền của SSM Agent, association dispatch role và Automation assume role.
- Kết hợp State Manager với Quick Setup, AWS Organizations, CloudWatch, CloudTrail và các dịch vụ vận hành khác.

## 1. Bài toán: giữ cho hệ thống ở trạng thái đã định nghĩa

Một đội vận hành có thể tạo hàng trăm EC2 instances cho nhiều ứng dụng. Mỗi máy cần cài CloudWatch Agent, bật một số dịch vụ hệ điều hành, dùng cấu hình bảo mật chuẩn và cập nhật SSM Agent. Nếu nhân viên phải đăng nhập từng máy để kiểm tra, cấu hình sẽ dần khác nhau giữa các máy. Một thay đổi thủ công có thể bị quên, một máy mới có thể thiếu package hoặc một dịch vụ quan trọng có thể bị dừng.

Đó là configuration drift: trạng thái thực tế của tài nguyên lệch khỏi trạng thái mà tổ chức mong muốn.

AWS Systems Manager State Manager giúp tự động áp dụng cấu hình đã định nghĩa lên các managed nodes và một số AWS resources thông qua association. Association liên kết SSM document với target, tham số và lịch chạy. Khi association chạy, State Manager thực thi document trên các target hoặc gọi Systems Manager Automation để thay đổi tài nguyên AWS.

Ví dụ, một association có thể đảm bảo mọi máy chủ Linux mang tag **Environment=Production** đều cài CloudWatch Agent và dịch vụ agent đang hoạt động. Nếu package chưa có, document cài đặt nó. Nếu dịch vụ bị dừng, document có thể khởi động lại. Lần chạy tiếp theo tiếp tục kiểm tra và đưa máy về trạng thái đã định nghĩa.

Trong hệ sinh thái AWS, State Manager kết hợp với:

- **SSM Agent** để nhận và thực thi lệnh trên EC2 và máy chủ hybrid.
- **IAM** để giới hạn quyền quản lý node, dispatch association và chạy Automation.
- **Amazon EC2, VPC và VPC endpoints** để kết nối node với Systems Manager.
- **AWS Resource Groups và tags** để chọn đúng nhóm tài nguyên.
- **Systems Manager Automation** để thay đổi các AWS resources bằng API.
- **Amazon S3 và CloudWatch** để lưu output và quan sát hoạt động.
- **AWS Organizations và Quick Setup** để triển khai cấu hình nhất quán trên nhiều tài khoản và Region.

State Manager phù hợp với việc duy trì cấu hình theo chu kỳ và xử lý drift. Với tác vụ bảo trì cần một cửa sổ thực thi có thời lượng, cutoff và lịch bảo trì rõ ràng, hãy cân nhắc Maintenance Windows.

## 2. Desired state và cơ chế hội tụ

Desired state là trạng thái cuối cùng mà hệ thống cần đạt được. Ví dụ:

- CloudWatch Agent phải được cài trên máy chủ.
- Dịch vụ **amazon-cloudwatch-agent** phải được bật và đang chạy.
- SSM Agent phải được cập nhật theo lịch.
- Một file cấu hình phải có nội dung và quyền truy cập đã quy định.
- Security group phải có tập ingress/egress rule đã phê duyệt.
- Một nhóm EC2 instances phải được dừng ngoài giờ làm việc.

State Manager không cần theo dõi từng thay đổi theo thời gian thực để thực hiện mục tiêu này. Association áp dụng document khi được tạo, theo lịch và trong một số sự kiện như association được cập nhật, document được cập nhật, người vận hành yêu cầu chạy thủ công hoặc node quay lại hoạt động sau khi bỏ lỡ lịch.

Vì vậy, một association thường tạo ra vòng lặp hội tụ:

1. Đọc trạng thái hiện tại.
2. So sánh với điều kiện mong muốn.
3. Thực hiện thay đổi còn thiếu.
4. Xác minh trạng thái sau thay đổi.
5. Trả kết quả thành công hoặc thất bại.
6. Lặp lại ở lần chạy tiếp theo.

~~~mermaid
flowchart TD
    A["Desired configuration"] --> B["State Manager association"]
    B --> C["Select targets and schedule"]
    C --> D["Run SSM document"]
    D --> E["Inspect current state"]
    E --> F{"Matches desired state?"}
    F -->|Yes| G["Report success / compliant"]
    F -->|No| H["Apply configuration"]
    H --> I["Verify result"]
    I --> J{"Verification passed?"}
    J -->|Yes| G
    J -->|No| K["Report failure and retain details"]
    G --> L["Wait for next run or trigger"]
    K --> L
    L --> B
~~~

Để vòng lặp này an toàn, document nên có tính idempotent: chạy nhiều lần với cùng đầu vào vẫn đưa tài nguyên về cùng trạng thái mà không tạo thêm thay đổi không cần thiết. Ví dụ, lệnh **systemctl enable --now** có thể bật và khởi động service nếu cần. Một script chỉ thêm dòng cấu hình vào file ở mọi lần chạy có thể tạo dữ liệu trùng lặp và không phải là idempotent.

Association thành công cũng cần có ý nghĩa rõ ràng. Nếu script chỉ chạy xong mà không kiểm tra trạng thái cuối, Systems Manager có thể báo Success dù mục tiêu cấu hình chưa đạt. Hãy để document trả mã lỗi khi không thể xác minh desired state.

## 3. State Manager và association

State Manager là capability của AWS Systems Manager. Thành phần trung tâm là **association**.

Association là một cấu hình liên kết:

| Thành phần | Vai trò |
|---|---|
| SSM document | Định nghĩa các bước cần thực hiện |
| Targets | Chọn managed nodes hoặc AWS resources cần áp dụng |
| Parameters | Truyền giá trị đầu vào cho document |
| Schedule | Xác định khi nào association chạy |
| Document version | Chọn phiên bản nội dung được thực thi |
| Association dispatch role | Cho phép State Manager gửi lệnh hoặc khởi chạy Automation |
| AutomationAssumeRole | Cho runbook quyền gọi các AWS APIs cần thiết |
| Compliance severity | Gán mức độ nghiêm trọng cho kết quả compliance |
| Rate controls | Giới hạn số target chạy đồng thời và số lỗi được phép |

Khi tạo association, State Manager cấp một Association ID. Association có thể được tạo bằng Systems Manager console, AWS CLI, AWS Tools for PowerShell hoặc API.

Mặc định, association chạy ngay sau khi được tạo rồi tiếp tục theo lịch đã chọn. Nếu không muốn chạy ngay, có thể cấu hình chỉ áp dụng tại cron interval tiếp theo trong những trường hợp được hỗ trợ.

Một managed node có thể nhận nhiều associations, nhưng cần quản lý số lượng và phạm vi để tránh chạy quá nhiều cấu hình chồng chéo.

## 4. Chọn SSM document phù hợp

SSM document mô tả công việc mà Systems Manager thực hiện. AWS cung cấp nhiều document dựng sẵn; tổ chức cũng có thể tạo document riêng.

Các nhóm thường dùng với State Manager:

| Loại document | Mục đích | Ví dụ |
|---|---|---|
| Command | Chạy lệnh hoặc script trên managed node | **AWS-RunShellScript**, **AWS-RunPowerShellScript** |
| Policy | Áp dụng policy hoặc baseline trên managed node | Document dùng cho cấu hình theo policy |
| Automation | Thực hiện chuỗi bước gọi AWS APIs hoặc thao tác tài nguyên | **AWS-RestartEC2Instance**, runbook tùy chỉnh |

### 4.1 Command document

Command document phù hợp với cấu hình bên trong hệ điều hành:

- Cài hoặc cập nhật package.
- Bật và khởi động service.
- Tạo thư mục hoặc file cấu hình.
- Cập nhật nội dung file.
- Kiểm tra tiến trình và cổng mạng.
- Chạy script kiểm tra cấu hình định kỳ.

Command document được gửi đến managed node và thực thi qua SSM Agent. Vì vậy, node phải được Systems Manager quản lý và có thể liên lạc với dịch vụ.

### 4.2 Policy document

Policy document được dùng cho những trường hợp cần áp dụng policy trên managed nodes. Khi chọn document, hãy kiểm tra document type và hành vi của nó trong tài liệu AWS. Không phải mọi SSM document đều phù hợp để làm association.

### 4.3 Automation runbook

Automation runbook phù hợp khi desired state liên quan đến AWS APIs hoặc tài nguyên không phải là một tiến trình bên trong hệ điều hành.

Ví dụ:

- Đảm bảo EC2 instance có cấu hình IAM hoặc trạng thái mong muốn.
- Chuẩn hóa ingress/egress rules của security group.
- Tạo hoặc xóa EBS snapshots.
- Tạo hoặc xóa DynamoDB backups.
- Cập nhật cấu hình S3 bucket.
- Khởi động, dừng hoặc restart EC2 và một số AWS resources khác.

Với association chạy Automation, cần cấu hình **AutomationAssumeRole** trong runbook parameters. State Manager dùng role này để gọi AWS services mà runbook yêu cầu. Cấu hình rate control giúp triển khai Automation trên một fleet.

### 4.4 Chọn document theo vị trí của cấu hình

| Câu hỏi | Lựa chọn phù hợp |
|---|---|
| Cần cài package hoặc sửa file trong Linux/Windows? | Command document |
| Cần áp dụng policy có sẵn cho managed nodes? | Policy document |
| Cần gọi EC2, S3, EBS, DynamoDB hoặc dịch vụ AWS bằng API? | Automation runbook |
| Cần kiểm tra trạng thái định kỳ và tự sửa nếu lệch? | Association với document idempotent |
| Cần chạy tác vụ một lần theo một lịch bảo trì có cutoff? | Cân nhắc Automation hoặc Maintenance Windows tùy yêu cầu |

## 5. Điều kiện để node trở thành managed node

State Manager chỉ có thể áp dụng association lên node đã được Systems Manager quản lý.

Với EC2 instance, các điều kiện cơ bản gồm:

1. SSM Agent đã được cài đặt và đang chạy trên hệ điều hành được hỗ trợ.
2. Instance có IAM instance profile hoặc được quản lý bằng Default Host Management Configuration.
3. Role cung cấp quyền cần thiết để SSM Agent đăng ký và giao tiếp với Systems Manager.
4. Instance truy cập được các Systems Manager endpoints qua Internet/NAT hoặc VPC interface endpoints phù hợp.
5. Node xuất hiện trong đúng AWS account và Region đang thao tác.

Một policy thường dùng cho instance profile là **AmazonSSMManagedInstanceCore** hoặc policy tương đương theo hướng dẫn hiện hành của AWS. Không gắn quyền quản trị rộng cho instance chỉ để làm cho node xuất hiện trong Systems Manager.

### 5.1 EC2 instance

Luồng kết nối:

1. EC2 instance khởi động SSM Agent.
2. Agent lấy credentials từ instance profile hoặc cơ chế host management đã cấu hình.
3. Agent kết nối đến Systems Manager endpoints.
4. Systems Manager đăng ký node và hiển thị trạng thái managed node.
5. State Manager có thể target node bằng ID hoặc tag.

Nếu instance không có outbound Internet, có thể tạo VPC interface endpoints cho các dịch vụ Systems Manager cần thiết. Tùy Region và cấu hình, hãy kiểm tra endpoint **ssm**, **ssmmessages** và **ec2messages** cùng DNS, security group và route.

### 5.2 Máy chủ hybrid và multicloud

State Manager cũng có thể quản lý máy chủ ngoài AWS như máy chủ on-premises hoặc máy ảo ở môi trường cloud khác.

Quy trình tổng quát:

1. Tạo hybrid activation trong Systems Manager.
2. Khai báo giới hạn số node và thời hạn activation.
3. Dùng activation code và activation ID để đăng ký máy chủ.
4. Cài và khởi động SSM Agent.
5. Agent nhận credentials được cấp qua quá trình đăng ký.
6. Xác nhận node xuất hiện dưới dạng managed node.
7. Gán tag để phân nhóm và tạo association.

Với máy chủ không phải EC2, cần IAM service role phù hợp cho hybrid environment và bảo vệ credentials trên hệ điều hành. Không dùng lại activation credentials tùy tiện cho nhiều máy hoặc lưu chúng trong script có thể bị đọc.

### 5.3 Kiểm tra managed node

Có thể xem danh sách node bằng CLI:

~~~bash
aws ssm describe-instance-information \
  --region ap-southeast-1
~~~

Kiểm tra một node cụ thể bằng cách lọc **InstanceInformationList** theo InstanceId. Nếu node không xuất hiện, hãy kiểm tra SSM Agent, IAM permissions, kết nối endpoint, hệ điều hành được hỗ trợ và Region. Trạng thái Online cho biết agent đang giao tiếp với Systems Manager; trạng thái Offline cần được điều tra trước khi tạo association.

## 6. Chọn target cho association

Target xác định tài nguyên nhận cấu hình. State Manager hỗ trợ các cách chọn phổ biến:

| Target | Khi nên dùng |
|---|---|
| Instance ID / managed node ID | Kiểm thử hoặc quản lý một số node cụ thể |
| Tags | Nhóm node theo môi trường, vai trò hoặc ứng dụng |
| AWS Resource Groups | Chọn tập tài nguyên theo query hoặc CloudFormation stack |
| All managed nodes | Áp dụng baseline trên toàn bộ node trong tài khoản và Region hiện tại |

Ví dụ tag:

- **Environment=Production**
- **OperatingSystem=Linux**
- **Application=Checkout**
- **PatchGroup=ProdLinux**

Một association cài CloudWatch Agent có thể target **Environment=Production** và **OperatingSystem=Linux**. Việc dùng tag giúp tài nguyên mới được đưa vào nhóm quản lý khi được gắn tag tương ứng.

### 6.1 Target bằng tag

Khi association dùng Command hoặc Policy document, node mới được tạo và gắn tag khớp có thể tự động nhận association, chạy lần đầu rồi tiếp tục theo lịch. Khi tag bị gỡ, node không còn thuộc target đó.

Đây là cách được khuyến nghị cho associations quản lý managed nodes theo fleet.

Có giới hạn về số tag keys: console hỗ trợ tối đa một tag key cho Automation association và năm tag keys cho Command association; AWS CLI hỗ trợ tối đa năm tag keys. Các tag keys được khai báo phải tồn tại trên node. Nếu cần điều kiện phức tạp hơn, hãy dùng AWS Resource Groups.

### 6.2 Target bằng Resource Groups

Resource Group có thể tập hợp tài nguyên theo tag hoặc CloudFormation stack. Association có thể target các node mà query của group trả về.

Các giới hạn cần lưu ý:

- Một association chỉ target tối đa một Resource Group.
- Không hỗ trợ nhóm lồng nhau hoặc nhiều groups trong cùng association.
- Với tag-based group, số tag keys và values có giới hạn theo tài liệu AWS.
- Khi xóa Resource Group, các node trong group không còn nhận association đó; nên xóa association đang target group theo quy trình.

Quyền tạo association target Resource Group có thể tương đương quyền root-level control trên các EC2 instances trong group vì document có thể thực thi lệnh hệ điều hành. Chỉ cấp quyền này cho quản trị viên đáng tin cậy.

### 6.3 Target tất cả managed nodes

Target **InstanceIds=*** áp dụng association cho tất cả managed nodes trong tài khoản và Region hiện tại. Node mới có thể được áp dụng association khi được đăng ký.

Đây là phạm vi rộng. Trước khi sử dụng, hãy kiểm tra document, quyền, concurrency và khả năng tương thích của hệ điều hành trên toàn bộ fleet.

### 6.4 Target của Automation runbook

Automation association có cơ chế target riêng. Bạn có thể target bằng tag, Resource Groups hoặc parameter values. Với parameter values, Systems Manager tạo child automation cho từng giá trị; số lượng parameter values được target tối đa là 50.

Khi muốn Automation association tự cập nhật theo node mới, cần đáp ứng điều kiện được AWS hỗ trợ. Hiện tại, chức năng tự cập nhật target nodes cho Automation runbook được hỗ trợ trong một số association tạo bởi Quick Setup và khi runbook khai báo resource type phù hợp như **AWS::EC2::Instance** hoặc **AWS::SSM::ManagedInstance**. Không nên giả định mọi Automation association tạo bằng CLI đều tự động nhận node mới như Command/Policy association.

## 7. Lịch chạy: cron, rate và offset

Association có thể chạy ngay sau khi tạo, theo lịch hoặc theo lệnh chạy thủ công. Lịch được khai báo bằng cron hoặc rate expression.

| Loại lịch | Ví dụ | Ý nghĩa |
|---|---|---|
| Rate | **rate(30 minutes)** | Chạy mỗi 30 phút |
| Rate | **rate(1 day)** | Chạy mỗi ngày |
| Cron | **cron(0 2 ? * SUN *)** | Chủ nhật lúc 02:00 UTC |
| Cron | **cron(30 23 ? * TUE#3 *)** | Thứ Ba lần thứ ba trong tháng, lúc 23:30 UTC |

### 7.1 Giới hạn schedule

Với State Manager associations:

- Khoảng chạy tối thiểu là 30 phút.
- Rate expression phải từ 30 phút trở lên và nhỏ hơn 31 ngày.
- Cron expression không hỗ trợ chỉ định tháng như maintenance windows.
- Cron schedule dùng UTC.
- Các expression phải tuân thủ định dạng mà Systems Manager hỗ trợ.

Ví dụ **rate(15 minutes)** không hợp lệ cho State Manager association. Nếu cần tác vụ nhanh hơn, hãy chọn cơ chế phù hợp khác thay vì rút ngắn lịch association dưới giới hạn.

### 7.2 Schedule offset

Schedule offset cho phép trì hoãn association một số ngày sau ngày cron đã định. Ví dụ, association có thể chạy ba ngày sau thứ Năm thứ hai trong tháng.

Offset có giá trị từ 1 đến 6 ngày. Để dùng offset, cần chọn **Apply association only at the next specified Cron interval** trong console hoặc đặt **ApplyOnlyAtCronInterval=true** qua API/CLI. Khi tùy chọn này được bật, association không chạy ngay lúc tạo mà chờ đến cron interval tiếp theo. Offset không áp dụng cho rate expression.

### 7.3 Chọn rate hay cron

Dùng rate khi cấu hình cần được áp dụng đều đặn, chẳng hạn kiểm tra service mỗi ngày hoặc cập nhật SSM Agent mỗi tuần. Dùng cron khi cần gắn với thời điểm cụ thể, chẳng hạn trước giờ làm việc hoặc một ngày trong tuần.

Với Automation associations, AWS khuyến nghị rate expression trong nhiều trường hợp vì Systems Manager có thể thử lại Automation sau khi bị throttling do chạm giới hạn concurrent automations.

## 8. Association chạy khi nào?

Mặc định, State Manager chạy association ngay sau khi tạo rồi tiếp tục theo schedule. Ngoài lịch định kỳ, association còn có thể được áp dụng khi:

- Người dùng sửa association và lưu thay đổi.
- Document được cập nhật theo version mà association đang tham chiếu.
- Người vận hành chọn Apply association now hoặc gọi API tương ứng.
- Managed node xuất hiện lần đầu, quay lại sau khi bỏ lỡ lịch hoặc trở lại sau thời gian dài offline.
- Target thay đổi và đáp ứng điều kiện cập nhật association.

Khi association bị giới hạn bởi concurrency và một node không chạy trong interval hiện tại, State Manager có thể thử lại ở interval kế tiếp. Lịch sử những interval bị bỏ qua có thể xem trong Execution History.

Nếu association được tạo cho một tài nguyên mới nhưng không muốn chạy ngay khi target thay đổi, có thể dùng **Apply association only at the next specified Cron interval** ở những trường hợp được hỗ trợ. Cách này hữu ích để tránh một Automation tốn phí chạy mỗi khi fleet tăng node.

## 9. Tạo association bằng AWS CLI

Ví dụ sau tạo association cài CloudWatch Agent trên các Linux production nodes. Tài khoản và Region minh họa là **ap-southeast-1**.

~~~bash
aws ssm create-association \
  --association-name install-cloudwatch-agent-production \
  --name AWS-ConfigureAWSPackage \
  --document-version '$DEFAULT' \
  --targets Key=tag:Environment,Values=Production \
  --parameters '{"action":["Install"],"name":["AmazonCloudWatchAgent"]}' \
  --schedule-expression 'rate(1 day)' \
  --compliance-severity HIGH \
  --association-dispatch-assume-role arn:aws:iam::123456789012:role/StateManagerAssociationDispatchRole \
  --max-concurrency '10%' \
  --max-errors '1' \
  --region ap-southeast-1
~~~

Thay account ID và role ARN bằng giá trị thực. Association dispatch role cần trust Systems Manager và quyền gửi lệnh phù hợp. EC2 instances cũng phải có quyền cho SSM Agent hoạt động và quyền cần thiết để tải package.

Các tham số quan trọng:

- **--name:** SSM document được dùng.
- **--document-version:** version của document; **$DEFAULT** dùng default version.
- **--targets:** nhóm managed nodes nhận association.
- **--parameters:** tham số truyền vào document.
- **--schedule-expression:** lịch chạy.
- **--compliance-severity:** mức độ nghiêm trọng khi báo compliance.
- **--association-dispatch-assume-role:** role State Manager assume khi dispatch.
- **--max-concurrency:** số node tối đa chạy đồng thời.
- **--max-errors:** số lỗi tối đa trước khi dừng dispatch đến target tiếp theo.

Lệnh tạo association sẽ kích hoạt lần chạy đầu theo hành vi mặc định. Hãy triển khai thử trên một nhóm nhỏ trước khi mở rộng.

## 10. Tạo custom Command document để giữ service ở trạng thái chạy

AWS managed documents phù hợp với nhiều tác vụ thông dụng. Khi cần logic riêng, bạn có thể tạo custom Command document.

Ví dụ sau chỉ dành cho Linux dùng systemd. Document kiểm tra CloudWatch Agent service có tồn tại hay không, bật service và khởi động nó. Nếu service chưa được cài, document trả lỗi để association thể hiện trạng thái thất bại thay vì báo thành công giả.

~~~yaml
schemaVersion: '2.2'
description: Ensure Amazon CloudWatch Agent service is enabled and running
mainSteps:
  - action: aws:runShellScript
    name: ensureCloudWatchAgent
    inputs:
      runCommand:
        - |
          set -eu
          if ! systemctl list-unit-files --type=service | grep -q '^amazon-cloudwatch-agent.service'; then
            echo "CloudWatch Agent service is not installed" >&2
            exit 1
          fi
          systemctl enable --now amazon-cloudwatch-agent
          systemctl is-active --quiet amazon-cloudwatch-agent
~~~

Tạo document:

~~~bash
aws ssm create-document \
  --name EnsureCloudWatchAgentRunning \
  --document-type Command \
  --document-format YAML \
  --content file://ensure-cloudwatch-agent-running.yaml \
  --region ap-southeast-1
~~~

Tạo association để áp dụng cho nhóm Linux production:

~~~bash
aws ssm create-association \
  --association-name ensure-cloudwatch-agent-running \
  --name EnsureCloudWatchAgentRunning \
  --targets Key=tag:Environment,Values=Production \
  --schedule-expression 'rate(30 minutes)' \
  --compliance-severity HIGH \
  --association-dispatch-assume-role arn:aws:iam::123456789012:role/StateManagerAssociationDispatchRole \
  --max-concurrency '10%' \
  --max-errors '1' \
  --region ap-southeast-1
~~~

Document trên chỉ kiểm tra và duy trì trạng thái service. Việc cài package được thực hiện ở bước riêng bằng AWS-ConfigureAWSPackage hoặc quy trình image/bootstrap. Tách cài đặt và duy trì service giúp lỗi package dễ điều tra hơn.

Nếu dùng document trên Windows, cần tạo document riêng bằng **aws:runPowerShellScript** và kiểm tra Windows Service tương ứng. Không chạy lệnh systemd trên Windows nodes.

## 11. Dùng Automation association để quản lý AWS resources

State Manager cũng có thể chạy Automation runbook theo lịch để duy trì trạng thái của AWS resources.

Ví dụ: đội phát triển muốn dừng EC2 instances có tag **Environment=Development** vào cuối ngày Chủ nhật để giảm thời gian chạy. Có thể dùng một runbook nội bộ đã được review, chẳng hạn **Company-StopTaggedDevelopmentInstances**.

Ví dụ CLI minh họa:

~~~bash
aws ssm create-association \
  --association-name stop-development-instances \
  --name Company-StopTaggedDevelopmentInstances \
  --targets Key=tag:Environment,Values=Development \
  --parameters AutomationAssumeRole=arn:aws:iam::123456789012:role/StateManagerAutomationExecutionRole \
  --automation-target-parameter-name InstanceId \
  --schedule-expression 'cron(0 20 ? * SUN *)' \
  --association-dispatch-assume-role arn:aws:iam::123456789012:role/StateManagerAssociationDispatchRole \
  --region ap-southeast-1
~~~

Ở đây có hai role riêng:

- **StateManagerAssociationDispatchRole** cho phép State Manager dispatch association và khởi chạy Automation.
- **StateManagerAutomationExecutionRole** là role mà runbook assume để gọi EC2 APIs.

Trước khi sử dụng, hãy kiểm tra document có parameter **InstanceId**, **AutomationAssumeRole** và hành vi dừng instance phù hợp. Ví dụ này dùng tag làm target nên cần đảm bảo tag không vô tình bao gồm máy chủ production.

Một số runbook có thể thực hiện thay đổi rộng như sửa security group hoặc xóa snapshot. Hãy đọc từng step và quyền IAM trước khi triển khai, đồng thời bắt đầu bằng manual test hoặc nhóm target nhỏ.

## 12. Rate controls: giới hạn concurrency và error threshold

Khi association áp dụng cho nhiều node, không nên để toàn bộ fleet chạy đồng thời nếu document có thể tiêu thụ CPU, network hoặc gây restart dịch vụ.

State Manager cung cấp hai rate controls:

| Thuộc tính | Ý nghĩa |
|---|---|
| Max concurrency | Số lượng hoặc tỷ lệ target được phép chạy đồng thời |
| Max errors | Số lỗi hoặc tỷ lệ lỗi cho phép trước khi ngừng dispatch đến các target tiếp theo |

Concurrency có thể khai báo bằng số tuyệt đối hoặc phần trăm target set. Ví dụ **10** nghĩa là tối đa 10 node; **10%** nghĩa là tối đa 10% target set.

Nếu association dùng targets mà không khai báo concurrency, State Manager áp dụng mặc định tối đa 50 node đồng thời. Nếu không khai báo error threshold, mặc định là ngưỡng 100% lỗi.

### 12.1 Cách hoạt động của error threshold

Nếu đặt max errors là **3**, State Manager dừng gửi association đến các target tiếp theo khi lỗi thứ tư xuất hiện. Những target đã chạy vẫn được phép hoàn tất và cũng có thể phát sinh lỗi.

Nếu đặt max errors là **10%** trên 50 targets, hệ thống dừng dispatch sau khi lỗi thứ sáu xuất hiện. Để giảm khả năng số lỗi vượt ngưỡng do nhiều target chạy song song, có thể đặt concurrency bằng 1 trong giai đoạn rollout đầu.

### 12.2 Ví dụ rollout an toàn

Giả sử có 500 production nodes và muốn cài agent:

- Giai đoạn thử nghiệm: 5 targets, concurrency 1, max errors 1.
- Giai đoạn canary: 5% fleet, concurrency 5%, max errors 1.
- Giai đoạn mở rộng: 10% hoặc 20% fleet tùy thời gian và mức độ ảnh hưởng.
- Giai đoạn ổn định: chọn concurrency theo capacity của hệ thống và cửa sổ vận hành.

Nếu association cập nhật trong lúc node đang chạy, các execution đã bắt đầu được phép hoàn tất; các execution chưa bắt đầu có thể bị dừng. Sau khi cập nhật, association có thể chạy lại trên toàn bộ targets theo concurrency mới.

Rate controls giới hạn phạm vi tác động, nhưng không thay thế rollback. Với thay đổi có rủi ro, cần có phương án phục hồi và giám sát trong thời gian rollout.

## 13. IAM và phân tách vai trò

State Manager liên quan đến nhiều lớp IAM. Nếu gộp tất cả vào một role quản trị rộng, sẽ khó kiểm soát ai có thể gửi lệnh, ai có thể thay đổi node và runbook được phép gọi API nào.

### 13.1 Instance profile hoặc hybrid service role

SSM Agent cần credentials để giao tiếp với Systems Manager. Với EC2, credentials thường đến từ instance profile hoặc Default Host Management Configuration. Với máy chủ hybrid, credentials đến từ IAM service role được thiết lập trong quá trình activation.

Role này cần các quyền quản lý node như policy **AmazonSSMManagedInstanceCore** hoặc quyền tương đương theo cấu hình thực tế.

### 13.2 Association dispatch assume role

State Manager assume role này để dispatch configuration đến managed nodes hoặc gọi Automation. Trust policy cho phép **ssm.amazonaws.com** assume role.

Trust policy mẫu:

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

Quyền permission cần phù hợp với loại association:

- Command/Policy association cần quyền **ssm:SendCommand** và các quyền liên quan.
- Automation association cần quyền **ssm:StartAutomationExecution** và các quyền dispatch liên quan.

AWS đang chuyển dần khỏi việc dựa vào service-linked role mặc định cho State Manager associations. Nên cấu hình custom association dispatch role để kiểm soát quyền rõ ràng. Có thể dùng condition key **ssm:AssociationDispatchAssumeRole** trong IAM policy để yêu cầu principal chỉ được tạo/cập nhật association khi chỉ định role này.

### 13.3 AutomationAssumeRole

AutomationAssumeRole là role mà Automation runbook assume để gọi các AWS APIs trong các bước. Role này cần trust relationship cho Systems Manager Automation và quyền đúng với hành động của runbook.

Ví dụ runbook dừng EC2 cần quyền **ec2:StopInstances** trên tập instance phù hợp. Runbook sửa security group cần quyền đọc và cập nhật các ingress/egress rules liên quan. Tránh dùng AdministratorAccess.

### 13.4 Principal tạo association

Người hoặc pipeline tạo association cần quyền tạo, cập nhật, xem và xóa association theo phạm vi được phép. Đồng thời cần **iam:PassRole** để truyền association dispatch role và Automation role khi phù hợp.

Hãy giới hạn quyền principal theo:

- SSM documents được phép sử dụng.
- Tập target tags hoặc Resource Groups.
- Association dispatch role được phép truyền.
- Automation runbooks được phép chạy.
- AWS resources mà Automation execution role có thể thay đổi.

### 13.5 Bảo vệ quyền điều khiển node

Người có quyền tạo association target Resource Group của EC2 instances có thể thực thi lệnh với quyền rất cao trên các node trong group. Đây là quyền điều khiển hệ điều hành ở quy mô fleet.

Không cấp **ssm:CreateAssociation** hoặc **ssm:UpdateAssociation** một cách rộng rãi cho developer nếu họ không được phép thực thi lệnh trên toàn bộ target. Tách quyền tạo document, phê duyệt document, tạo association và vận hành association.

## 14. Compliance và severity

Systems Manager Compliance tổng hợp trạng thái của State Manager associations và Patch Manager. Với association, trạng thái compliance có thể là:

- **Compliant:** association đạt trạng thái thành công theo kết quả được báo cáo.
- **Non-compliant:** association thất bại hoặc trạng thái cấu hình không đạt yêu cầu.

Khi tạo association, có thể gán severity:

| Severity | Cách dùng gợi ý |
|---|---|
| CRITICAL | Cấu hình bảo mật hoặc tính sẵn sàng có ảnh hưởng nghiêm trọng |
| HIGH | Baseline quan trọng của production |
| MEDIUM | Cấu hình vận hành cần theo dõi |
| LOW | Tác vụ bảo trì ít rủi ro |
| UNSPECIFIED | Chưa phân loại mức độ |

Severity giúp nhóm vận hành ưu tiên xử lý finding. Nó không tự thay đổi hành vi của document và cũng không tự sửa tài nguyên.

Một điểm dễ nhầm: trường **ExecutionTime** trong compliance report của State Manager biểu thị thời điểm Systems Manager ghi nhận/tổng hợp compliance, không nhất thiết là thời điểm association thực sự chạy trên node. Để biết execution time và target nào chạy, hãy dùng association execution history và execution target details.

Có thể xem tổng hợp compliance bằng CLI:

~~~bash
aws ssm list-compliance-summaries \
  --region ap-southeast-1
~~~

Xem summary theo từng resource:

~~~bash
aws ssm list-resource-compliance-summaries \
  --region ap-southeast-1
~~~

Nếu document chỉ thực thi lệnh mà không xác minh desired state, compliance có thể không phản ánh đúng yêu cầu nghiệp vụ. Hãy thiết kế document để trả lỗi khi điều kiện không đạt.

## 15. Theo dõi execution history và output

Association status tổng hợp không đủ để chẩn đoán lỗi. Khi một association thất bại, hãy xem lịch sử execution và target-level details.

Các thao tác thường dùng:

~~~bash
aws ssm describe-association \
  --association-id 11111111-2222-3333-4444-555555555555 \
  --region ap-southeast-1
~~~

Xem các lần thực thi:

~~~bash
aws ssm describe-association-executions \
  --association-id 11111111-2222-3333-4444-555555555555 \
  --region ap-southeast-1
~~~

Xem target details của một execution:

~~~bash
aws ssm describe-association-execution-targets \
  --association-id 11111111-2222-3333-4444-555555555555 \
  --execution-id 99999999-8888-7777-6666-555555555555 \
  --region ap-southeast-1
~~~

Thay các ID minh họa bằng Association ID và Execution ID thực tế.

### 15.1 Output trên node và Amazon S3

Với Command associations, có thể cấu hình output để lưu kết quả vào Amazon S3. Quyền ghi S3 đến từ instance profile của EC2 instance hoặc IAM service role của hybrid node, không phải principal tạo association.

Nếu bucket nằm ở tài khoản khác, cần bucket policy và quyền cross-account phù hợp. Hãy giới hạn bucket prefix theo ứng dụng, môi trường và association ID.

### 15.2 CloudWatch và CloudTrail

CloudWatch có thể dùng để giám sát log của ứng dụng hoặc agent được association quản lý. Nếu document ghi log ra file, cần cấu hình CloudWatch Agent hoặc cơ chế thu thập log tương ứng.

Lưu ý: các API operations do SSM document khởi chạy trong lúc association chạy không được ghi như CloudTrail API events theo mô tả của AWS. Hãy lưu association execution history, SSM Automation execution details, output trên S3 và log của ứng dụng để có bằng chứng vận hành đầy đủ.

## 16. Cập nhật association và quản lý version

Association có thể được cập nhật khi cần thay đổi:

- Document version.
- Document parameters.
- Target nodes.
- Schedule expression.
- Compliance severity.
- Output location.
- Concurrency và error threshold.
- Association dispatch role.

Khi association được sửa và lưu, State Manager có thể chạy lại ngay. Vì vậy, cập nhật document hoặc parameter trong production cần được xem như một thay đổi có tác động thật.

### 16.1 Chọn document version

Có ba cách tham chiếu thường gặp:

- **$DEFAULT:** dùng version đang được đánh dấu default.
- **$LATEST:** dùng version mới nhất.
- Số version cụ thể: pin association vào một version đã kiểm thử.

Pin version giúp triển khai có thể dự đoán và tránh thay đổi bất ngờ khi document được cập nhật. Khi muốn rollout version mới, hãy thử nghiệm và chủ động cập nhật association.

Nếu association tham chiếu **$DEFAULT** và default version thay đổi, hoặc tham chiếu **$LATEST** và document được cập nhật, State Manager có thể thực thi lại association.

Có giới hạn với document được share từ tài khoản khác: State Manager luôn chạy default version của document được share, kể cả khi console hiển thị một version mới đã được xử lý. Nếu cần dùng document share cross-account, hãy đặt document version là **default** và quản lý version tại tài khoản sở hữu document.

### 16.2 Cập nhật document

Một thay đổi document có thể được áp dụng lên hàng trăm node khi association chạy lại. Quy trình an toàn:

1. Tạo version mới của document.
2. Kiểm tra trong một node lab.
3. Tạo association thử nghiệm trên nhóm canary.
4. Xem output và compliance.
5. Mở rộng target hoặc cập nhật association production.
6. Theo dõi error threshold và execution history.
7. Giữ version trước để rollback khi cần.

### 16.3 Xóa association

Xóa association khiến association ngừng chạy trên các target. Việc xóa association không tự động gỡ package, dừng service hoặc hoàn nguyên thay đổi đã áp dụng trước đó.

Nếu muốn đưa node về trạng thái cũ, cần có document rollback hoặc quy trình uninstall/reconfigure riêng. Hãy lưu danh sách association ID và document version trước khi xóa.

## 17. State Manager, Maintenance Windows, Patch Manager và Automation

Các capability trong Systems Manager có thể giải quyết những bài toán gần nhau nhưng mục tiêu khác nhau.

| Capability | Mục tiêu chính | Ví dụ |
|---|---|---|
| State Manager | Duy trì cấu hình mong muốn theo lịch và target | Đảm bảo agent được cài và service luôn chạy |
| Maintenance Windows | Tổ chức tác vụ bảo trì trong cửa sổ có thời lượng/cutoff | Restart server trong maintenance window |
| Patch Manager | Quản lý scan, install và compliance của bản vá | Cài security updates theo patch baseline |
| Automation | Điều phối nhiều bước gọi AWS APIs và thao tác tài nguyên | Snapshot, restart, sửa security group |
| Run Command | Gửi lệnh một lần đến managed nodes | Chạy script điều tra hoặc khắc phục tức thời |

State Manager có thể chạy Patch Manager hoặc Automation thông qua association, nhưng không thay thế các capability chuyên biệt đó. Hãy chọn công cụ theo mục tiêu và vòng đời công việc.

## 18. Quick Setup và quản lý nhiều tài khoản

Quick Setup đơn giản hóa việc triển khai các cấu hình vận hành phổ biến của Systems Manager. Nó có thể tạo các State Manager associations, IAM roles và các tài nguyên hỗ trợ cần thiết.

Quick Setup có thể áp dụng cho một tài khoản hoặc nhiều tài khoản/Region thông qua AWS Organizations. Dashboard hiển thị deployment status và association status.

Ví dụ cấu hình Quick Setup có thể:

- Cấu hình host management cho EC2.
- Bật inventory collection.
- Thiết lập periodic patch scans.
- Cập nhật SSM Agent theo lịch.
- Cấu hình các best practices cho fleet.

Quick Setup cũng định kỳ kiểm tra configuration drift đối với những lựa chọn mà nó quản lý và cố gắng khắc phục. Khi một cấu hình được tạo bằng Quick Setup, hãy xem associations và roles mà Quick Setup đã triển khai trước khi tạo association trùng lặp.

Khi triển khai trên nhiều tài khoản:

1. Chọn management account hoặc delegated administrator theo mô hình quản trị.
2. Xác định OU/account và Region đích.
3. Kiểm tra quyền tích hợp AWS Organizations.
4. Triển khai Quick Setup configuration.
5. Theo dõi stack/deployment status và association status.
6. Điều tra các tài khoản không có managed nodes hoặc chưa hoàn tất prerequisite.
7. Kiểm tra service quotas và Region availability.

Quick Setup có thể có các configuration types khác nhau theo Region. Hãy xem danh sách Region hỗ trợ hiện hành trước khi thiết kế rollout cho tổ chức.

## 19. Hybrid và multicloud operations

State Manager giúp đội vận hành áp dụng cùng một baseline cho EC2 instances và máy chủ hybrid đã đăng ký Systems Manager.

Ví dụ, doanh nghiệp có:

- EC2 Linux trong AWS.
- EC2 Windows trong AWS.
- Máy chủ vật lý trong datacenter.
- Máy ảo ở một cloud provider khác.

Có thể gắn tag thống nhất như **Environment**, **OperatingSystem** và **Application** để tạo các association tương ứng.

Cần phân biệt target theo hệ điều hành. Một document dùng systemd chỉ phù hợp Linux có systemd. Một document dùng PowerShell chỉ phù hợp Windows Server. Không nên gắn một document vào mọi managed nodes nếu document không tương thích với tất cả hệ điều hành.

Đối với máy chủ hybrid, cần theo dõi activation expiration, IAM service role, SSM Agent version, kết nối mạng và việc đăng ký lại node. Nếu node offline, association không thể hoàn tất trên node đó cho đến khi agent kết nối lại.

## 20. Chi phí và giới hạn vận hành

Khi thiết kế State Manager ở quy mô lớn, hãy theo dõi:

- Số lượng associations trên mỗi managed node.
- Số lượng targets của mỗi association.
- Tần suất schedule và thời gian chạy của document.
- Số lượng concurrent Automation executions.
- Chi phí Automation, S3 output, CloudWatch Logs và các dịch vụ được gọi.
- Thời gian node offline và số lần execution bị bỏ lỡ.
- Số lần document cập nhật khiến association chạy lại.

Một số giới hạn cần lưu ý theo tài liệu AWS hiện hành:

| Hạng mục | Giới hạn hoặc hành vi |
|---|---|
| Associations trên mỗi managed node | Tối đa 20 |
| State Manager schedule interval | Tối thiểu 30 phút |
| Automation associations | Tính vào giới hạn concurrent Automation trong tài khoản |
| Concurrent Automation executions | Quota tài khoản thường là 100; kiểm tra Service Quotas thực tế |
| Parameter values khi target Automation | Tối đa 50 giá trị |
| Target set lớn hơn 1.000 nodes | Status aggregation có thể bị throttle theo giờ |
| Resource Groups trong một association | Tối đa một group |

Khi có hơn 1.000 nodes, số liệu trạng thái tổng hợp có thể cập nhật theo cơ chế hourly throttling, nên dashboard có thể không phản ánh ngay mọi thay đổi target. Dùng execution history và target-level details khi cần điều tra chính xác.

State Manager không nên được cấu hình với lịch quá dày nếu document tốn nhiều thời gian hoặc làm thay đổi trạng thái hệ thống. Một association có thể chạy lại do document update hoặc association update, vì vậy cần tính cả các lần chạy ngoài lịch.

## 21. Kiến trúc ví dụ: baseline cho fleet production

Giả sử tổ chức vận hành 300 EC2 Linux instances và 50 Windows instances. Mục tiêu là:

- Mọi node đều được quản lý bởi Systems Manager.
- CloudWatch Agent được cài đặt.
- Dịch vụ agent hoạt động.
- SSM Agent được cập nhật định kỳ.
- Association failures được báo cáo theo severity.
- Thay đổi cấu hình được rollout theo nhóm nhỏ.

Thiết kế:

1. EC2 instances dùng instance profile hoặc Default Host Management Configuration.
2. SSM Agent đăng ký node và kết nối đến Systems Manager endpoints.
3. Tags phân nhóm **Environment**, **OperatingSystem** và **Application**.
4. Association Linux và Windows sử dụng document riêng.
5. Rate controls giới hạn concurrency để tránh ảnh hưởng toàn fleet.
6. Compliance severity được gán theo mức độ quan trọng của baseline.
7. Output và execution history được giữ theo chính sách vận hành.
8. Quick Setup có thể triển khai các cấu hình nền tảng ở cấp organization.

~~~mermaid
flowchart TD
    A["AWS Organizations / Accounts"] --> B["Quick Setup and IAM roles"]
    B --> C["EC2 and hybrid managed nodes"]
    C --> D["SSM Agent connectivity"]
    D --> E["State Manager associations"]
    E --> F["Linux document"]
    E --> G["Windows document"]
    E --> H["Automation runbooks"]
    F --> I["Desired OS configuration"]
    G --> I
    H --> J["AWS resource configuration"]
    I --> K["Compliance and execution history"]
    J --> K
    K --> L["S3 output / CloudWatch / Operations"]
~~~

Không nên dùng một association chung cho cả Linux và Windows nếu các bước thực thi khác nhau. Tách association giúp kiểm soát scope, document version, lịch và lỗi theo nền tảng.

## 22. Lab: cài và duy trì CloudWatch Agent bằng State Manager

Lab dùng một nhóm EC2 Linux thử nghiệm trong Region **ap-southeast-1**. Không dùng fleet production.

### Bước 1: chuẩn bị managed node

- Tạo EC2 Linux test instance.
- Cài SSM Agent và xác nhận agent đang chạy.
- Gắn instance profile có quyền Systems Manager cần thiết.
- Đảm bảo instance truy cập Systems Manager endpoints.
- Xác nhận node xuất hiện trong Fleet Manager hoặc Managed nodes.

### Bước 2: gắn tag

Gắn tag:

~~~text
Environment=StateManagerLab
OperatingSystem=Linux
Application=Observability
~~~

Tag giúp association chỉ target nhóm máy thử nghiệm.

### Bước 3: kiểm tra package document

Xác nhận document **AWS-ConfigureAWSPackage** có sẵn trong Region và tham số cần dùng. Document này cho phép cài đặt package được Distributor hỗ trợ.

### Bước 4: tạo association

Chạy CLI:

~~~bash
aws ssm create-association \
  --association-name install-cloudwatch-agent-lab \
  --name AWS-ConfigureAWSPackage \
  --document-version '$DEFAULT' \
  --targets Key=tag:Environment,Values=StateManagerLab \
  --parameters '{"action":["Install"],"name":["AmazonCloudWatchAgent"]}' \
  --schedule-expression 'rate(1 day)' \
  --compliance-severity MEDIUM \
  --association-dispatch-assume-role arn:aws:iam::123456789012:role/StateManagerAssociationDispatchRole \
  --max-concurrency '1' \
  --max-errors '1' \
  --region ap-southeast-1
~~~

Thay account ID và role ARN bằng giá trị của lab. Nếu role dispatch chưa được tạo, hãy tạo trust policy cho Systems Manager và permission phù hợp trước.

### Bước 5: kiểm tra association

Lấy danh sách associations:

~~~bash
aws ssm list-associations \
  --association-filter-list key=AssociationName,value=install-cloudwatch-agent-lab \
  --region ap-southeast-1
~~~

Lưu Association ID trả về. Dùng **describe-association** và **describe-association-executions** để xem status và lịch sử.

### Bước 6: xác minh trên node

Kết nối vào EC2 test instance và kiểm tra package cùng service:

~~~bash
sudo systemctl is-enabled amazon-cloudwatch-agent
sudo systemctl is-active amazon-cloudwatch-agent
~~~

Nếu package đã cài nhưng service chưa được cấu hình, hãy tạo association riêng bằng custom document để duy trì service. Không coi việc package tồn tại là bằng chứng agent đang gửi telemetry.

### Bước 7: kiểm tra compliance

Mở Systems Manager Compliance và tìm association vừa tạo. Xem trạng thái và severity. Nếu association thất bại, mở execution history, chọn target và đọc output chi tiết.

### Bước 8: thử configuration drift

Dừng CloudWatch Agent trên máy test:

~~~bash
sudo systemctl stop amazon-cloudwatch-agent
~~~

Chạy association thủ công hoặc đợi lịch nếu đã có document duy trì service. Xác minh service trở lại trạng thái active. Với association chỉ cài package, việc dừng service không nhất thiết làm association báo lỗi; cần document kiểm tra service nếu desired state bao gồm trạng thái đang chạy.

### Bước 9: cleanup

- Xóa association của lab.
- Nếu không cần nữa, gỡ package hoặc giữ lại theo yêu cầu thử nghiệm.
- Xóa tag lab và EC2 instance khi hoàn tất.
- Xóa IAM role lab nếu không còn association nào sử dụng.

Xóa association không tự động gỡ package đã cài trên node.

## 23. Troubleshooting thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Node không xuất hiện trong Systems Manager | SSM Agent chưa cài/chạy hoặc OS không hỗ trợ | Kiểm tra agent và hệ điều hành |
| Node Offline | Instance profile, service role hoặc endpoint connectivity sai | Kiểm tra IAM, DNS, route và VPC endpoints |
| Association không tìm thấy target | Tag key/value sai hoặc target không thuộc Region/account | Kiểm tra tag và phạm vi |
| Association Pending lâu | Node offline hoặc agent không nhận lệnh | Kiểm tra managed node status và SSM Agent logs |
| Association Failed | Document trả mã lỗi hoặc thiếu permission | Xem execution history và output |
| Package không cài được | Package name/version hoặc Distributor access sai | Kiểm tra document parameters và package |
| Linux service không hoạt động | Package thiếu hoặc service name sai | Kiểm tra unit file và log hệ điều hành |
| Association chạy lặp ngoài dự kiến | Update association/document hoặc target changes kích hoạt execution | Xem lịch sử update và schedule |
| Node mới không nhận Automation association | Điều kiện target update của Automation chưa đáp ứng | Kiểm tra Quick Setup, resource type, parameters và targets |
| Association không chạy đúng version | Document version tham chiếu $DEFAULT, $LATEST hoặc shared document | Kiểm tra document version và tài khoản sở hữu |
| S3 output không xuất hiện | Instance profile/hybrid role thiếu quyền S3 | Kiểm tra role của node và bucket policy |
| Compliance timestamp không khớp execution | Timestamp là thời điểm compliance được capture | Dùng association execution history |
| Automation bị throttled | Vượt giới hạn concurrent Automation | Dùng rate schedule, giảm concurrency và kiểm tra quota |
| Fleet có nhiều node không thành công | Max concurrency/error threshold quá cao hoặc document không tương thích | Rollout theo canary, hạ concurrency và tách OS |
| Resource Group target trả InvalidTarget | Group vượt giới hạn tag hoặc query không hợp lệ | Kiểm tra cấu hình Resource Group |

### Quy trình điều tra lỗi

1. Xác định Association ID và target node/resource.
2. Kiểm tra association status và lần execution gần nhất.
3. Xem document name, version và parameters.
4. Xác minh node có Online trong đúng Region.
5. Kiểm tra association dispatch role và AutomationAssumeRole nếu dùng runbook.
6. Mở execution target details để xác định step thất bại.
7. Đọc SSM Agent logs hoặc SSM Automation step output.
8. Kiểm tra target tags và document có tương thích với hệ điều hành không.
9. Chạy lại trên một node test sau khi sửa lỗi.
10. Chỉ mở rộng rollout khi association trả kết quả ổn định.

## 24. Các lỗi thiết kế cần tránh

- **Document không idempotent:** mỗi lần chạy lại tạo thêm cấu hình trùng lặp hoặc phá trạng thái hiện tại.
- **Target quá rộng:** một association mới có thể thực thi trên cả production fleet.
- **Không dùng tag chuẩn:** nhóm node khó được quản lý nhất quán khi scale.
- **Không pin document version:** document thay đổi có thể kích hoạt lại association ngoài kế hoạch.
- **Dùng quyền AdministratorAccess:** tăng blast radius khi document bị lỗi hoặc bị sửa.
- **Gộp dispatch role và Automation role:** khó phân biệt quyền gửi lệnh và quyền sửa AWS resources.
- **Không cấu hình rate controls:** nhiều node cùng restart hoặc thay đổi đồng thời.
- **Không xác minh trạng thái cuối:** association có thể báo Success nhưng desired state chưa đạt.
- **Nhầm compliance timestamp với execution time:** dẫn đến kết luận sai khi điều tra.
- **Giả định Automation association tự nhận node mới:** cần đáp ứng điều kiện target update mà AWS hỗ trợ.
- **Không lưu output:** khó xác định node nào lỗi và lỗi ở bước nào.
- **Không có rollback:** association tiếp tục áp dụng cấu hình sai qua nhiều lần chạy.
- **Dùng association thay cho mọi tác vụ:** một số tác vụ bảo trì có thời lượng và cutoff phù hợp với Maintenance Windows hơn.
- **Bỏ qua giới hạn lịch:** association không chạy dưới 30 phút và cron có giới hạn riêng.

## 25. Best practices

### Desired state

- Mô tả desired state bằng điều kiện có thể kiểm chứng.
- Viết document idempotent và có bước verify.
- Tách cấu hình cài package khỏi cấu hình duy trì service khi cần.
- Dùng document riêng cho từng hệ điều hành hoặc nhóm tương thích.
- Lưu custom documents trong version control và review thay đổi.

### Targets và rollout

- Dùng tags nhất quán để phân nhóm theo môi trường và ứng dụng.
- Bắt đầu với node lab rồi canary.
- Giới hạn concurrency và error threshold.
- Kiểm tra target expansion trước khi tạo association.
- Tránh quyền tạo association target Resource Group cho người không có quyền quản trị fleet.

### IAM và bảo mật

- Dùng instance profile hoặc Default Host Management Configuration với quyền tối thiểu.
- Dùng custom association dispatch role.
- Dùng AutomationAssumeRole riêng cho runbook.
- Giới hạn iam:PassRole theo role và dịch vụ tin cậy.
- Hạn chế ai được tạo, sửa hoặc xóa associations.
- Không đặt secret trực tiếp trong document parameters hoặc command output.
- Bảo vệ S3 output bucket bằng encryption, bucket policy và lifecycle.

### Vận hành

- Gán compliance severity theo mức độ ảnh hưởng.
- Theo dõi association execution history và target details.
- Gửi log đến nơi tập trung và lưu output cần thiết.
- Theo dõi offline nodes và failed associations.
- Quản lý document version và lịch rollout.
- Dùng Quick Setup khi cần triển khai baseline cho nhiều tài khoản/Region.
- Kiểm tra quotas và chi phí trước khi mở rộng fleet.

## 26. Bài tập tự luyện

1. State Manager association gồm những thành phần nào?
2. Vì sao cần idempotent document khi muốn duy trì desired state?
3. Khi nào nên dùng Command document và khi nào nên dùng Automation runbook?
4. Một EC2 instance không xuất hiện trong Managed nodes. Bạn kiểm tra những điều kiện nào?
5. Khi nào nên target bằng tag thay vì liệt kê instance IDs?
6. Nếu một association target Environment=Production, node mới được gắn tag đó có thể nhận association không?
7. Tại sao Automation associations có điều kiện riêng về việc tự cập nhật target nodes?
8. rate(15 minutes) có hợp lệ với State Manager không? Vì sao?
9. Schedule offset dùng trong tình huống nào?
10. Khi nào association chạy ngay ngoài lịch?
11. Max concurrency 10% có ý nghĩa gì với 200 targets?
12. Nếu max errors là 2, khi nào State Manager dừng dispatch đến target tiếp theo?
13. Vì sao cần phân tách association dispatch role và AutomationAssumeRole?
14. Ai cấp quyền ghi S3 output cho association: principal tạo association hay instance profile của node?
15. Compliance ExecutionTime có luôn là thời điểm association thực thi không?
16. Làm sao xem node nào thất bại trong một association execution?
17. Khi nào nên dùng Maintenance Windows thay cho State Manager?
18. Tại sao document version $LATEST có thể tạo ra lần chạy ngoài lịch?
19. Một association đã cài package thành công nhưng service bị dừng. Cần bổ sung điều kiện nào?
20. Xóa association có tự động gỡ package hoặc hoàn nguyên cấu hình không?

### Gợi ý đáp án

1. Document, targets, parameters, schedule, document version, IAM roles, compliance severity và rate controls.
2. Để chạy lặp lại không tạo thay đổi trùng lặp và luôn hội tụ về cùng trạng thái.
3. Command cho thao tác bên trong OS; Automation cho AWS APIs và resource-level workflows.
4. SSM Agent, trạng thái agent, IAM instance profile hoặc host management, endpoint connectivity, OS support và Region.
5. Khi muốn quản lý fleet có thể thay đổi theo tag và tự đưa node mới vào nhóm.
6. Có với Command/Policy association theo cơ chế target update; Automation có điều kiện hỗ trợ riêng.
7. Automation runbook cần khai báo target parameter/resource type và association phải đáp ứng điều kiện mà AWS hỗ trợ.
8. Không. State Manager association yêu cầu interval tối thiểu 30 phút.
9. Khi muốn chạy vài ngày sau một cron date, ví dụ sau lịch patch Tuesday.
10. Khi tạo association, update association/document, manual start hoặc target node quay lại hoạt động trong các trường hợp được hỗ trợ.
11. Tối đa khoảng 20 target chạy đồng thời.
12. Khi lỗi thứ ba xuất hiện.
13. Dispatch role cho phép State Manager gửi lệnh/khởi chạy Automation; AutomationAssumeRole cấp quyền cho các API trong runbook.
14. Instance profile của EC2 hoặc IAM service role của hybrid node.
15. Không. Đó là thời điểm compliance được capture; xem execution history để biết thời gian chạy thực tế.
16. Dùng DescribeAssociationExecutionTargets với Association ID và Execution ID.
17. Khi cần lịch bảo trì có duration, cutoff và task orchestration trong một maintenance window.
18. Cập nhật document có thể kích hoạt association chạy lại.
19. Thêm bước kiểm tra và duy trì service running, không chỉ cài package.
20. Không. Association dừng chạy nhưng thay đổi đã áp dụng vẫn tồn tại cho đến khi có quy trình rollback/uninstall.

## 27. Câu hỏi phỏng vấn

### State Manager giải quyết vấn đề gì?

State Manager tự động áp dụng cấu hình mong muốn lên managed nodes hoặc AWS resources theo association. Nó giúp giảm configuration drift và chuẩn hóa vận hành trên fleet.

### Association là gì?

Association là liên kết giữa SSM document, targets, parameters và schedule. Nó mô tả cấu hình cần áp dụng và cách State Manager phân phối cấu hình đó.

### State Manager có phải công cụ theo dõi cấu hình real-time không?

Không. State Manager áp dụng cấu hình khi association chạy: ngay sau khi tạo theo mặc định, theo lịch và trong một số sự kiện cập nhật/target. Khoảng thời gian giữa các lần chạy tạo ra độ trễ phát hiện drift.

### Vì sao document nên idempotent?

Vì association chạy nhiều lần. Document idempotent bảo đảm trạng thái cuối ổn định và tránh tạo thay đổi lặp lại không cần thiết.

### Phân biệt Command association và Automation association?

Command association chạy lệnh trên managed node qua SSM Agent. Automation association gọi runbook để thực hiện workflow trên AWS resources hoặc các bước điều phối khác.

### State Manager target bằng tag có lợi ích gì?

Tag cho phép áp dụng association cho nhóm node có cùng vai trò hoặc môi trường. Khi node mới có tag phù hợp, Command/Policy association có thể tự động áp dụng cho node đó.

### Khi nào nên dùng Resource Groups?

Khi target cần dựa trên query hoặc CloudFormation stack và cần tập hợp nhiều node theo tiêu chí quản trị. Cần kiểm tra giới hạn Resource Group và bảo vệ quyền tạo association.

### Tại sao cần rate controls?

Để tránh thực thi đồng thời trên quá nhiều node, giảm ảnh hưởng đến workload và dừng rollout khi tỷ lệ lỗi vượt ngưỡng.

### Association compliance có thay thế execution history không?

Không. Compliance cho trạng thái tổng hợp và severity. Execution history cho thời điểm chạy, target và chi tiết lỗi.

### Quick Setup liên quan gì đến State Manager?

Quick Setup có thể tạo các State Manager associations và tài nguyên hỗ trợ để triển khai cấu hình vận hành trên một hoặc nhiều tài khoản/Region.

### Tại sao cần hai role khi Automation association chạy?

Association dispatch role cho phép State Manager dispatch hoặc khởi chạy Automation. AutomationAssumeRole cấp quyền cho runbook gọi các AWS APIs trong từng bước.

### State Manager có thay thế Maintenance Windows không?

Không. State Manager duy trì cấu hình theo schedule và target. Maintenance Windows tổ chức tác vụ bảo trì trong cửa sổ có thời lượng và cutoff.

## 28. Checklist trước khi đưa vào production

### Managed nodes

- [ ] SSM Agent được cài và chạy trên OS được hỗ trợ.
- [ ] EC2 có instance profile hoặc Default Host Management Configuration.
- [ ] Hybrid nodes có activation và service role hợp lệ.
- [ ] Node kết nối được Systems Manager endpoints.
- [ ] Node xuất hiện Online trong đúng account và Region.
- [ ] Tags được chuẩn hóa theo môi trường và ứng dụng.

### Association và document

- [ ] Desired state có điều kiện kiểm chứng.
- [ ] Document đã được review và thử nghiệm.
- [ ] Document idempotent và trả lỗi khi verify thất bại.
- [ ] Document tương thích với OS và target resource type.
- [ ] Document version được pin hoặc có quy trình cập nhật.
- [ ] Target scope được kiểm tra trước khi rollout.
- [ ] Schedule tuân thủ giới hạn tối thiểu và UTC.
- [ ] Có phương án không chạy ngay khi tạo nếu cần.

### IAM và rollout

- [ ] Association dispatch role có trust relationship phù hợp.
- [ ] AutomationAssumeRole chỉ có quyền cần thiết.
- [ ] Principal tạo association có quyền và PassRole giới hạn.
- [ ] Concurrency và error threshold được thiết lập.
- [ ] Canary đã thành công trước khi rollout rộng.
- [ ] Change Calendar hoặc CloudWatch alarm được dùng nếu phù hợp.

### Monitoring và recovery

- [ ] Compliance severity được gán.
- [ ] Association history và target details có thể truy cập.
- [ ] Output S3 có bucket policy và encryption phù hợp.
- [ ] Có log hệ điều hành hoặc CloudWatch Agent khi cần.
- [ ] Có quy trình rollback/uninstall.
- [ ] Có cảnh báo cho failed associations và offline nodes.
- [ ] Có quy trình xử lý drift và exception.

## 29. Tài liệu tham khảo chính thức

- [AWS Systems Manager State Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-state.html)
- [Understanding how State Manager works](https://docs.aws.amazon.com/systems-manager/latest/userguide/state-manager-about.html)
- [Creating associations](https://docs.aws.amazon.com/systems-manager/latest/userguide/state-manager-associations-creating.html)
- [Understanding targets and rate controls in State Manager associations](https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-state-manager-targets-and-rate-controls.html)
- [Cron and rate expressions for Systems Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/reference-cron-and-rate-expressions.html)
- [Scheduling automations with State Manager associations](https://docs.aws.amazon.com/systems-manager/latest/userguide/scheduling-automations-state-manager-associations.html)
- [About State Manager association compliance](https://docs.aws.amazon.com/systems-manager/latest/userguide/compliance-about.html)
- [Viewing association histories](https://docs.aws.amazon.com/systems-manager/latest/userguide/state-manager-associations-history.html)
- [Editing and creating a new version of an association](https://docs.aws.amazon.com/systems-manager/latest/userguide/state-manager-associations-edit.html)
- [Setting up managed nodes for AWS Systems Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-setting-up-nodes.html)
- [Troubleshooting managed node availability](https://docs.aws.amazon.com/systems-manager/latest/userguide/fleet-manager-troubleshooting-managed-nodes.html)
- [SSM Agent technical details](https://docs.aws.amazon.com/systems-manager/latest/userguide/ssm-agent-technical-details.html)
- [AWS Systems Manager Quick Setup](https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-quick-setup.html)
- [Supported Quick Setup configuration types](https://docs.aws.amazon.com/systems-manager/latest/userguide/quick-setup-config-types.html)
- [AWS Systems Manager service quotas](https://docs.aws.amazon.com/general/latest/gr/ssm.html)


