# Change set, cập nhật stack và rollback

Một thay đổi CloudFormation có thể chỉ chỉnh số lượng EC2 instances, nhưng cũng có thể thay thế database, xóa security group hoặc tạo lại load balancer. Khi stack đã phục vụ production, một lần cập nhật template không còn là thao tác sửa file đơn giản: nó là một **deployment thay đổi hạ tầng đang chạy**.

CloudFormation **change set** cho phép xem trước các thay đổi mà một lần update dự kiến thực hiện. Người vận hành có thể đọc danh sách resource được thêm, sửa, xóa hoặc thay thế, xem property-level differences, rồi mới quyết định execute. Nếu update thất bại, CloudFormation có thể rollback về cấu hình trước đó; khi rollback cũng thất bại, stack chuyển sang trạng thái cần xử lý như UPDATE_ROLLBACK_FAILED.

Bài học thuộc chương **Hạ tầng dưới dạng mã** của mô-đun **CLOUD_PROVIDERS_AWS**. Nội dung đặt change set, stack update và rollback trong quy trình vận hành AWS an toàn, có giám sát, phục hồi và kiểm soát chi phí. Các ví dụ sử dụng AWS CloudFormation và AWS CLI; tên stack, account, Region và tài nguyên đều là dữ liệu minh họa.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích vai trò của CloudFormation stack, template, parameters, resources, outputs và change set.
2. Tạo change set cho một stack đang tồn tại và review trước khi execute.
3. Đọc các action Add, Modify, Remove, Import và Replacement để đánh giá blast radius.
4. Phân biệt update không gián đoạn, update có interruption và replacement.
5. Cập nhật stack bằng console hoặc AWS CLI theo quy trình có thể kiểm toán.
6. Theo dõi stack status, events, resource status reason và xử lý update failure.
7. Thiết lập rollback triggers bằng CloudWatch alarms và monitoring period.
8. Phân biệt UPDATE_ROLLBACK_COMPLETE với UPDATE_ROLLBACK_FAILED và biết cách phục hồi.
9. Sử dụng stack policies, termination protection, DeletionPolicy và UpdateReplacePolicy đúng mục đích.
10. Phát hiện drift, quản lý nested stacks, CloudFormation service role và least privilege.
11. Lập kế hoạch kiểm thử, cutover, rollback và hậu kiểm sau deployment.

## 2. Các khái niệm nền tảng

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Template** | Mô tả hạ tầng mong muốn bằng YAML/JSON | VPC, subnet, EC2, RDS, S3 |
| **Stack** | Một lần triển khai template cùng parameters/tags/role | orders-prod-network |
| **Resource logical ID** | Tên resource trong template, CloudFormation dùng để theo dõi | AppDatabase |
| **Physical ID** | ID thực tế của tài nguyên AWS | DB instance identifier, bucket name |
| **Parameter** | Input được truyền vào khi tạo/cập nhật stack | InstanceType, Environment |
| **Output** | Giá trị stack công bố cho người dùng hoặc stack khác | VPC ID, endpoint |
| **Change set** | Bản xem trước thay đổi dự kiến của một stack operation | Replace database, add subnet |
| **Stack event** | Sự kiện mô tả tiến trình resource/stack | UPDATE_IN_PROGRESS, UPDATE_FAILED |
| **Drift** | Cấu hình thực tế khác với template và parameter values | SG rule bị sửa ngoài CloudFormation |

CloudFormation lưu quan hệ giữa logical ID trong template và physical resources. Khi template thay đổi, CloudFormation so sánh cấu hình mới với cấu hình stack đã triển khai để xác định cần tạo, sửa, giữ, thay thế hoặc xóa tài nguyên.

### 2.1. Update stack khác với sửa template

Sửa file YAML trong Git chỉ thay đổi **desired state trong repository**. Tài nguyên AWS chỉ thay đổi khi một stack operation được thực thi. Change set giúp xem trước phần khác biệt giữa desired state mới và stack hiện tại.

~~~mermaid
flowchart TD
    GIT["Template mới trong Git"] --> INPUT["Parameters / capabilities / role"]
    INPUT --> CS["Create change set"]
    CS --> REVIEW["Review resource actions<br/>Replacement / property diff"]
    REVIEW --> DECISION{"Có chấp nhận thay đổi?"}
    DECISION -->|"Không"| DELETE["Delete change set"]
    DECISION -->|"Có"| EXEC["Execute change set"]
    EXEC --> EVENTS["Theo dõi stack events"]
    EVENTS --> RESULT{"Kết quả"}
    RESULT -->|"UPDATE_COMPLETE"| VERIFY["Smoke test và hậu kiểm"]
    RESULT -->|"Rollback hoàn tất"| INVESTIGATE["Điều tra nguyên nhân"]
    RESULT -->|"UPDATE_ROLLBACK_FAILED"| RECOVER["Khôi phục rollback"]
~~~

## 3. Change set là gì và giới hạn của nó

Change set là bản mô tả những thay đổi CloudFormation **dự kiến** thực hiện khi stack operation chạy. Khi tạo change set, CloudFormation phân tích template/parameter changes và trả về danh sách resource actions. Tạo change set không tự áp dụng các thay đổi lên stack.

Change set giúp:

- Nhận biết resource nào sẽ được **Add, Modify, Remove, Import**.
- Xem resource có bị **Replacement** hay không.
- Xem property-level changes và giá trị trước/sau khi hỗ trợ.
- So sánh các phương án thay đổi bằng nhiều change sets.
- Phát hiện một số lỗi validation, naming conflicts, quota và cấu hình trước khi execute.
- Tạo bằng Console, AWS CLI hoặc CloudFormation API.

**Change set không bảo đảm update sẽ thành công.** Một số lỗi chỉ xuất hiện lúc CloudFormation gọi service API hoặc resource đi vào trạng thái ổn định, ví dụ custom resource logic, service quota phát sinh, thiếu quyền ở resource policy, điều kiện network, hoặc tài nguyên phụ thuộc chưa sẵn sàng.

### 3.1. Vòng đời change set

| Trạng thái | Ý nghĩa |
|---|---|
| CREATE_PENDING / CREATE_IN_PROGRESS | CloudFormation đang tạo change set |
| CREATE_COMPLETE | Change set đã tạo và có thể xem xét |
| FAILED / CREATE_FAILED | Không tạo được change set; xem StatusReason |
| AVAILABLE | Execution status cho biết change set có thể execute |
| EXECUTE_IN_PROGRESS | Change set đang được thực thi |
| EXECUTE_COMPLETE | Execution hoàn tất |
| OBSOLETE | Change set không còn áp dụng cho stack hiện tại |

Tên trạng thái cụ thể phụ thuộc trường ChangeSetStatus và ExecutionStatus. Một change set có ChangeSetStatus CREATE_COMPLETE chưa chắc có thể execute nếu ExecutionStatus không AVAILABLE.

### 3.2. Change set không phải backup

Change set không lưu bản sao dữ liệu database, không tạo AMI, không snapshot EBS và không bảo đảm có thể khôi phục dữ liệu sau khi resource bị thay thế/xóa. Với stateful resources, cần thiết kế **backup, snapshot, replication và restore test** độc lập.

## 4. Đọc các loại thay đổi trước khi execute

Change set thường hiển thị action và mức độ replacement. Review phải hiểu cả hai trường; một Modify có thể dẫn tới replacement.

| Action | Ý nghĩa | Câu hỏi khi review |
|---|---|---|
| **Add** | Tạo resource mới | Có quota, subnet, policy, naming và chi phí chưa? |
| **Modify** | Cập nhật resource hiện có | Thuộc tính có interruption hoặc replacement không? |
| **Remove** | Xóa resource khỏi stack | Dữ liệu có bị mất? Có retain policy không? |
| **Import** | Đưa resource có sẵn vào quản lý stack | Resource properties có khớp template và import requirements không? |

Replacement có thể được biểu diễn là:

- **True:** CloudFormation sẽ thay thế physical resource.
- **False:** không cần thay thế physical resource.
- **Conditional:** có thể thay thế tùy giá trị/property hoặc điều kiện runtime.

Lưu ý: **Conditional không phải Resource Action**. Đây là giá trị có thể xuất hiện ở trường Replacement. Action vẫn là Add, Modify, Remove hoặc Import; việc replacement có xảy ra hay không được mô tả riêng.

### 4.1. Replacement là điểm cần review kỹ nhất

Ví dụ sửa tên DB instance identifier hoặc một thuộc tính không thể cập nhật tại chỗ có thể làm CloudFormation tạo database mới rồi xóa database cũ theo resource update semantics. Điều này có thể gây:

- Downtime hoặc chuyển endpoint.
- Tạo lại physical ID.
- Tăng chi phí vì hai resource cùng tồn tại trong giai đoạn chuyển đổi.
- Mất dữ liệu nếu resource cũ bị xóa và không có snapshot/retain policy phù hợp.
- Ảnh hưởng các stack/app đang tham chiếu endpoint cũ.

Không coi replacement là một dòng diff nhỏ. Với database, volume, bucket, key hoặc network resource quan trọng, cần migration/cutover plan và phương án khôi phục dữ liệu.

### 4.2. Property-level changes

Khi có property-level change details, review:

1. Property nào bị đổi, bị thêm hoặc bị xóa?
2. Giá trị hiện tại và giá trị dự kiến có đúng môi trường không?
3. Update requires: no interruption, some interruption hay replacement theo tài liệu resource type?
4. Có thay đổi security exposure, encryption, retention, deletion behavior hoặc public access không?
5. Tài nguyên phụ thuộc có bị cập nhật dây chuyền không?

Không phải mọi resource/property đều có property-level diff đầy đủ. Đối chiếu CloudFormation resource reference và service documentation khi change set không hiển thị chi tiết.

## 5. Quy trình chuẩn trước khi cập nhật stack

Trước khi tạo change set, cần biết stack hiện đang ở trạng thái nào, được quản lý trong account/Region nào và template hiện tại có drift không.

### 5.1. Preflight checklist

- Xác minh AWS account, Region và caller identity.
- Xác minh stack name/stack ID, stack status và CloudFormation service role.
- Kiểm tra template/version/commit đang được deploy.
- Kiểm tra parameters, dynamic references, mappings, conditions và capabilities.
- Xem stack events gần nhất và resource status reasons.
- Kiểm tra drift của resources quan trọng.
- Kiểm tra backups/snapshots và RPO/RTO nếu có stateful resources.
- Xác minh IAM permissions, service quotas, VPC/network dependencies và maintenance window.
- Xác định rollback triggers/CloudWatch alarms và monitoring period.
- Chuẩn bị smoke tests, dashboard, on-call owner và rollback decision criteria.

### 5.2. Chỉ update stack ở trạng thái phù hợp

Thông thường, stack cần ở trạng thái ổn định như CREATE_COMPLETE hoặc UPDATE_COMPLETE trước một update bình thường. Nếu stack đang UPDATE_IN_PROGRESS, DELETE_IN_PROGRESS hoặc UPDATE_ROLLBACK_FAILED, không bắt đầu update mới. Kiểm tra trạng thái và xử lý operation hiện tại trước.

### 5.3. Xác nhận đúng stack

Stack name có thể giống nhau giữa các Regions hoặc accounts. Dùng **stack ID/ARN** trong automation production khi có thể; xác nhận account, Region, environment tags và service role trước khi tạo change set.

~~~bash
aws sts get-caller-identity

aws cloudformation describe-stacks \
  --stack-name orders-prod \
  --region ap-southeast-1 \
  --query 'Stacks[0].{StackId:StackId,Status:StackStatus,Reason:StackStatusReason,RoleARN:RoleARN,Drift:DriftInformation.StackDriftStatus}' \
  --output json
~~~

Đây là lệnh đọc metadata. Nếu stack không có drift information hoặc chưa từng detect drift, trường drift có thể không phản ánh trạng thái hiện tại; cần chủ động chạy drift detection khi cần.

## 6. Tạo change set bằng AWS CLI

Ví dụ dưới đây tạo một change set cho stack hiện tại. Template mới nằm trong file local và parameters được truyền rõ ràng.

### 6.1. Template minh họa

~~~yaml
AWSTemplateFormatVersion: "2010-09-09"
Description: Orders API compute settings

Parameters:
  Environment:
    Type: String
    AllowedValues:
      - dev
      - staging
      - prod
  InstanceType:
    Type: String
    Default: t3.small

Resources:
  AppSecurityGroup:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupDescription: Allow HTTPS from approved ingress
      VpcId: vpc-0123456789abcdef0
      SecurityGroupIngress:
        - IpProtocol: tcp
          FromPort: 443
          ToPort: 443
          CidrIp: 10.20.0.0/16

  AppLaunchTemplate:
    Type: AWS::EC2::LaunchTemplate
    Properties:
      LaunchTemplateData:
        InstanceType: !Ref InstanceType
        SecurityGroupIds:
          - !Ref AppSecurityGroup

Outputs:
  LaunchTemplateId:
    Value: !Ref AppLaunchTemplate
~~~

Template này minh họa cấu trúc và chỉ nên dùng trong lab sau khi thay VPC ID bằng VPC phù hợp. Với production, VPC, subnet, AMI, IAM instance profile, ingress source và launch template version phải được quản lý có chủ đích. Không dùng CIDR mở rộng hoặc resource IDs hard-code sai account/Region.

### 6.2. Tạo change set

Ví dụ sử dụng parameter overrides:

~~~bash
aws cloudformation create-change-set \
  --stack-name orders-prod \
  --change-set-name update-instance-type-2026-11-20 \
  --change-set-type UPDATE \
  --template-body file://template.yaml \
  --parameters \
    ParameterKey=Environment,ParameterValue=prod \
    ParameterKey=InstanceType,ParameterValue=t3.medium \
  --description "Increase app instance size after capacity review" \
  --region ap-southeast-1
~~~

Các điểm cần lưu ý:

- Dùng UPDATE cho stack đã tồn tại. Tạo change set cho stack mới là luồng CREATE và có stack state khác.
- Nếu không truyền parameter mới, cần xác định có dùng giá trị hiện tại hay default; không để vô tình reset parameter quan trọng.
- Với template chứa IAM resources, truyền capability phù hợp như CAPABILITY_IAM hoặc CAPABILITY_NAMED_IAM.
- Với macro/transform có khả năng mở rộng template, có thể cần CAPABILITY_AUTO_EXPAND theo loại template và workflow.
- Với nested stacks, quyết định có tạo change sets cho nested stacks hay không; review cả root và child stacks.
- Có thể chỉ định CloudFormation service role bằng --role-arn khi cần; role này được liên kết với stack cho các operation tương lai.

### 6.3. Chờ change set tạo xong

~~~bash
aws cloudformation describe-change-set \
  --stack-name orders-prod \
  --change-set-name update-instance-type-2026-11-20 \
  --region ap-southeast-1 \
  --output json
~~~

Kiểm tra:

- Status và StatusReason.
- ExecutionStatus có AVAILABLE hay không.
- Changes: LogicalResourceId, ResourceType, Action, Replacement.
- Details: Target.Attribute, Target.Name, Evaluation và ChangeSource nếu được cung cấp.
- Parameters, capabilities, role ARN, rollback configuration và nested change sets.

Nếu change set FAILED, đọc StatusReason, sửa nguyên nhân rồi tạo **change set mới**. Không execute change set lỗi hoặc giả định một change set đã tạo từ template cũ vẫn áp dụng được sau khi stack thay đổi.

### 6.4. Xem danh sách thay đổi gọn

~~~bash
aws cloudformation describe-change-set \
  --stack-name orders-prod \
  --change-set-name update-instance-type-2026-11-20 \
  --region ap-southeast-1 \
  --query 'Changes[].ResourceChange.{LogicalId:LogicalResourceId,Type:ResourceType,Action:Action,Replacement:Replacement,Scope:Scope}' \
  --output table
~~~

Output giúp review nhanh, nhưng trước production phải xem đầy đủ details/property changes, template, parameter values và resource reference. Bảng rút gọn không thể thay cho review kiến trúc.

## 7. Checklist review change set

Review change set theo từng lớp:

### 7.1. Resource actions

- [ ] Không có resource Remove ngoài dự kiến.
- [ ] Mọi Add có owner, quota, dependencies, naming và cost estimate.
- [ ] Mọi Modify được phân loại theo interruption/replacement.
- [ ] Mọi Replacement có kế hoạch dữ liệu, endpoint, DNS, cutover và cleanup.
- [ ] Import chỉ dùng cho resource đã tồn tại và đáp ứng điều kiện import.
- [ ] Không có thay đổi ngoài scope của ticket/commit.

### 7.2. Security changes

- [ ] IAM policy không mở rộng quyền ngoài yêu cầu.
- [ ] Security group ingress/egress không mở CIDR hoặc port quá rộng.
- [ ] S3 bucket public access, encryption, versioning và lifecycle vẫn đúng.
- [ ] KMS key, key policy, aliases và grants được review.
- [ ] Secrets Manager/SSM dynamic references trỏ tới đúng secret/path.
- [ ] VPC endpoint policies, route tables và network ACLs không làm lộ service.
- [ ] Logging/audit/CloudTrail settings vẫn được bật theo yêu cầu.

### 7.3. Availability, data và cost

- [ ] RDS/Aurora/EBS/ElastiCache stateful resources có backup/snapshot phù hợp.
- [ ] Multi-AZ/replicas/autoscaling settings không bị vô tình giảm.
- [ ] Replacement không gây downtime vượt SLO.
- [ ] Capacity/quota/limits đủ cho resource mới.
- [ ] Chi phí tạm thời khi resource cũ và mới cùng tồn tại đã được tính.
- [ ] CloudWatch alarms và rollback monitoring period có ý nghĩa.
- [ ] Rollback có thể phục hồi cấu hình nhưng dữ liệu cần restore riêng đã có kế hoạch.

### 7.4. Change set nào cần từ chối?

Không execute khi:

- Database hoặc storage resource bị replacement ngoài kế hoạch.
- Có resource Remove không rõ owner hoặc không có backup/retain decision.
- IAM policy đột ngột chuyển sang wildcard hoặc resource rộng.
- Stack/Region/account không đúng.
- Change set được tạo từ commit/template/parameters khác với release đang review.
- Change set đã obsolete hoặc execution status không AVAILABLE.
- Nested stack changes chưa được review.
- Có drift chưa được hiểu, khiến update có thể ghi đè thay đổi ngoài template.

## 8. Execute change set và giám sát stack update

Chỉ sau khi review và approval theo quy trình deployment mới execute:

~~~bash
aws cloudformation execute-change-set \
  --stack-name orders-prod \
  --change-set-name update-instance-type-2026-11-20 \
  --region ap-southeast-1
~~~

Sau execute:

- Stack chuyển sang UPDATE_IN_PROGRESS.
- CloudFormation áp dụng resource operations theo dependency graph.
- Events xuất hiện cho từng resource và stack.
- Nếu thành công, stack đạt UPDATE_COMPLETE.
- Nếu update thất bại và rollback thành công, stack thường đạt UPDATE_ROLLBACK_COMPLETE.
- Nếu rollback không thể hoàn tất, stack đạt UPDATE_ROLLBACK_FAILED.

Sau khi execute một change set, các change sets khác gắn với stack bị xóa/không còn hợp lệ vì stack state đã thay đổi. Nếu update thất bại và muốn thử lại, tạo change set mới từ state hiện tại.

### 8.1. Theo dõi stack events

~~~bash
aws cloudformation describe-stack-events \
  --stack-name orders-prod \
  --region ap-southeast-1 \
  --max-items 50 \
  --output table
~~~

Stack events thường được trả về theo thứ tự thời gian đảo ngược, sự kiện mới nhất xuất hiện trước. Tập trung vào:

- Timestamp.
- LogicalResourceId và PhysicalResourceId.
- ResourceType.
- ResourceStatus.
- ResourceStatusReason.
- ClientRequestToken để liên kết operation nếu có.

Khi thấy resource UPDATE_FAILED, đọc reason cụ thể. Event của stack có thể chỉ nói operation failed; resource event thường cho biết lý do như quota, invalid parameter, dependency violation, insufficient permissions hoặc service stabilization timeout.

### 8.2. Theo dõi stack status

~~~bash
aws cloudformation describe-stacks \
  --stack-name orders-prod \
  --region ap-southeast-1 \
  --query 'Stacks[0].{Status:StackStatus,Reason:StackStatusReason,Updated:LastUpdatedTime}' \
  --output json
~~~

Không dựa riêng vào CLI command exit code của execute-change-set để kết luận deployment thành công. Lệnh có thể trả về khi CloudFormation mới bắt đầu operation; cần theo dõi đến trạng thái terminal và chạy application smoke tests.

### 8.3. Theo dõi resource cụ thể

~~~bash
aws cloudformation describe-stack-resources \
  --stack-name orders-prod \
  --region ap-southeast-1 \
  --output table
~~~

Dùng resource list để đối chiếu logical ID, physical ID và resource status. Với replacement, kiểm tra physical ID cũ/mới và các consumers tham chiếu endpoint hoặc ARN.

### 8.4. Không chỉnh sửa resource ngoài CloudFormation giữa lúc update

Khi stack đang update/rollback, tránh thao tác tay lên resource mà CloudFormation đang quản lý trừ khi runbook yêu cầu khắc phục cụ thể. Sửa ngoài band có thể làm CloudFormation mất trạng thái mong đợi, khiến rollback hoặc update kế tiếp thất bại.

## 9. Rollback tự động khi stack update thất bại

Trong update bình thường, nếu CloudFormation không thể hoàn thành resource operation, stack có thể tự rollback các thay đổi đã áp dụng về trạng thái trước operation. Trạng thái cuối thường là **UPDATE_ROLLBACK_COMPLETE** nếu rollback thành công.

Rollback có thể:

- Khôi phục resource property về giá trị trước đó.
- Xóa resource mới được tạo trong operation nếu policy/operation settings cho phép.
- Khôi phục resource đã bị thay đổi theo update behavior của resource type.
- Giữ resource cũ nếu replacement đã tạo resource mới và rollback cần quay lại physical resource trước đó.

**Rollback không phải transaction dữ liệu phân tán.** Nó không đảo ngược side effects do application/custom resource đã thực hiện, không tự khôi phục dữ liệu đã bị ghi/xóa bên trong database và không hoàn tác mọi thay đổi ngoài CloudFormation.

### 9.1. Trạng thái update và rollback

| Stack status | Ý nghĩa | Hành động |
|---|---|---|
| UPDATE_IN_PROGRESS | Đang áp dụng thay đổi | Theo dõi events/alarms, không chạy update khác |
| UPDATE_COMPLETE | Update thành công | Chạy smoke tests và hậu kiểm |
| UPDATE_FAILED | Update thất bại; tùy failure behavior/configuration | Đọc events và xác định stack có thể tiếp tục operation nào |
| UPDATE_ROLLBACK_IN_PROGRESS | Đang hoàn tác update | Theo dõi resource rollback events |
| UPDATE_ROLLBACK_COMPLETE | Rollback hoàn tất; stack có thể tiếp tục được update | Điều tra nguyên nhân, tạo change set mới sau khi sửa |
| UPDATE_ROLLBACK_FAILED | Rollback không hoàn tất | Khắc phục blocker rồi Continue update rollback |

Một stack có UPDATE_ROLLBACK_COMPLETE không có nghĩa deployment mới đã thành công; nó có nghĩa stack đã quay lại trạng thái trước lần update thất bại. Ứng dụng có thể vẫn gặp lỗi tồn tại từ trước hoặc dữ liệu có thể đã bị side effects.

### 9.2. Cancel update

CloudFormation hỗ trợ cancel một số stack update khi đang UPDATE_IN_PROGRESS. Hành động này yêu cầu CloudFormation dừng update và thực hiện rollback theo operation semantics; nó không phải nút undo tức thời. Một số resource operation không thể dừng ngay và CloudFormation vẫn cần thời gian để ổn định/rollback.

Không cancel chỉ vì event không xuất hiện trong vài giây. Kiểm tra resource operation, service events và timeout trước khi quyết định.

## 10. Rollback triggers bằng CloudWatch alarms

Có thể yêu cầu CloudFormation giám sát một hoặc nhiều **CloudWatch alarms** trong lúc create/update và trong monitoring period sau khi các resource đã được triển khai. Nếu alarm chuyển sang ALARM, CloudFormation rollback toàn bộ stack operation.

### 10.1. Chọn alarm có ý nghĩa

Ví dụ:

- Application 5xx error rate vượt ngưỡng.
- ALB target response time/p99 vượt SLO.
- ECS service không duy trì desired healthy tasks.
- CPU/memory utilization vượt ngưỡng ảnh hưởng khả năng phục vụ.
- Custom business metric báo checkout failure tăng mạnh.

Alarm phải đo đúng ứng dụng/stack đang update. Một alarm luôn ở INSUFFICIENT_DATA hoặc không có datapoints có thể khiến rollback signal không phản ánh health thật; alarm ARN không tồn tại có thể làm stack operation thất bại.

### 10.2. Monitoring period

Rollback configuration có trường **MonitoringTimeInMinutes**, giá trị từ 0 đến 180 phút, mặc định 0. Nếu đặt thời gian, CloudFormation tiếp tục monitor triggers sau khi resource provisioning hoàn tất. Thời gian này cũng có thể dùng để giữ các resource cũ trong khoảng manual validation trước cleanup, theo semantics của operation.

Chọn period đủ để application khởi động, warm up, nhận traffic mẫu và thể hiện lỗi. Period quá ngắn có thể bỏ sót lỗi muộn; quá dài có thể kéo dài deployment và thời gian giữ resource cũ, ảnh hưởng chi phí.

### 10.3. Ví dụ rollback configuration

Có thể truyền rollback configuration khi tạo change set:

~~~bash
aws cloudformation create-change-set \
  --stack-name orders-prod \
  --change-set-name release-2026-11-20 \
  --change-set-type UPDATE \
  --template-body file://template.yaml \
  --rollback-configuration '{
    "RollbackTriggers": [
      {
        "Arn": "arn:aws:cloudwatch:ap-southeast-1:444455556666:alarm:orders-api-5xx-high",
        "Type": "AWS::CloudWatch::Alarm"
      }
    ],
    "MonitoringTimeInMinutes": 15
  }' \
  --region ap-southeast-1
~~~

ARN alarm và account là ví dụ. CloudFormation cần credentials/quyền để theo dõi alarm và các resource liên quan. Khi cập nhật rollback triggers cho stack, danh sách mới có thể **thay thế** danh sách trigger đã lưu; nếu muốn giữ các trigger cũ, phải gửi lại toàn bộ danh sách mong muốn. Nếu không truyền rollback triggers, CloudFormation giữ cấu hình hiện có theo API behavior.

### 10.4. Trigger không thay thế post-deployment tests

CloudWatch alarm chỉ kiểm tra các metrics/conditions đã cấu hình. Vẫn cần:

- Smoke tests cho critical APIs.
- Kiểm tra database migration/schema compatibility.
- Kiểm tra queue consumers và event processing.
- Kiểm tra IAM authorization và network path.
- Kiểm tra business correctness bằng test transaction.

Nếu alarm báo lỗi, CloudFormation rollback hạ tầng; application data hoặc external side effects cần runbook riêng.

## 11. Khi rollback thất bại: UPDATE_ROLLBACK_FAILED

Stack vào **UPDATE_ROLLBACK_FAILED** khi CloudFormation không thể khôi phục một hoặc nhiều resources về trạng thái trước update. Trong trạng thái này, stack không thể nhận update bình thường. Phải khôi phục rollback về **UPDATE_ROLLBACK_COMPLETE** trước rồi mới tạo change set mới.

Ví dụ nguyên nhân:

- Resource cũ đã bị xóa ngoài CloudFormation nên không thể restore.
- Quota không đủ để khôi phục resource.
- Một resource phụ thuộc không đạt trạng thái ổn định.
- Security/network/permission change làm CloudFormation không thể thao tác resource.
- Custom resource rollback handler bị lỗi hoặc không idempotent.
- Nested stack rollback thất bại.
- Resource replacement/physical ID bị can thiệp thủ công trong lúc operation.

### 11.1. Quy trình điều tra

1. Dùng describe-stacks lấy StackStatusReason.
2. Dùng describe-stack-events để tìm resource UPDATE_FAILED trong giai đoạn UpdateRollback.
3. Dùng describe-stack-resources để xác định logical ID và physical ID.
4. Kiểm tra resource thực tế trong service tương ứng: còn tồn tại không, có drift không, dependencies/quota/permissions ra sao.
5. Khắc phục blocker bên ngoài theo runbook, ví dụ khôi phục resource bị xóa hoặc sửa quota/network/policy.
6. Chỉ khi nguyên nhân được xử lý, tiếp tục rollback.

~~~bash
aws cloudformation describe-stacks \
  --stack-name orders-prod \
  --region ap-southeast-1 \
  --query 'Stacks[0].{Status:StackStatus,Reason:StackStatusReason}' \
  --output json

aws cloudformation describe-stack-events \
  --stack-name orders-prod \
  --region ap-southeast-1 \
  --max-items 100 \
  --output table
~~~

### 11.2. Continue update rollback

Khi đã xử lý nguyên nhân, tiếp tục rollback:

~~~bash
aws cloudformation continue-update-rollback \
  --stack-name orders-prod \
  --region ap-southeast-1
~~~

CloudFormation tiếp tục khôi phục stack từ UPDATE_ROLLBACK_FAILED. Theo dõi events đến khi stack đạt UPDATE_ROLLBACK_COMPLETE. Nếu operation vẫn thất bại, đọc reason mới và tiếp tục xử lý nguyên nhân cụ thể.

### 11.3. Chỉ skip resource khi thực sự cần

Nếu không thể sửa blocker, API hỗ trợ **ResourcesToSkip** để bỏ qua một số resources khiến rollback không thể hoàn tất:

~~~bash
aws cloudformation continue-update-rollback \
  --stack-name orders-prod \
  --resources-to-skip AppDatabase \
  --region ap-southeast-1
~~~

Logical ID AppDatabase chỉ là ví dụ. Chỉ chỉ định resources đã vào **UPDATE_FAILED trong giai đoạn UpdateRollback**, không phải resource thất bại trong forward update. Với nested stack, dùng định dạng NestedStackLogicalName.ResourceLogicalID.

Khi resource bị skip, CloudFormation đánh dấu nó UPDATE_COMPLETE để tiếp tục rollback. **Trạng thái thực tế của resource có thể không còn khớp template/stack metadata.** Trước lần update kế tiếp phải đồng bộ lại resource và template bằng một kế hoạch rõ ràng; nếu không, operation sau có thể thất bại hoặc stack khó phục hồi.

### 11.4. Force rollback

CLI hỗ trợ force rollback để CloudFormation skip các resources rollback thất bại:

~~~bash
aws cloudformation continue-update-rollback \
  --stack-name orders-prod \
  --force-rollback \
  --region ap-southeast-1
~~~

Không dùng đồng thời --force-rollback và --resources-to-skip trong cùng request. Force rollback có thể bỏ qua nhiều resource hơn phạm vi tối thiểu cần thiết, kể cả nested resources. Chỉ dùng khi đã đánh giá hậu quả và có kế hoạch reconcile sau đó.

### 11.5. Reconcile sau khi skip resource

Sau khi stack trở lại UPDATE_ROLLBACK_COMPLETE:

1. Chạy drift detection trên stack và resource bị skip.
2. Đối chiếu actual physical resource properties với template.
3. Quyết định giữ resource thực tế, sửa resource theo template hoặc cập nhật template để phản ánh desired state.
4. Backup dữ liệu trước mọi thay đổi destructive.
5. Tạo change set mới, review kỹ replacement/deletion và reconcile từng bước.
6. Chỉ đóng incident sau khi stack state, template và application behavior nhất quán.

## 12. Stack policy: bảo vệ resource quan trọng khỏi update ngoài ý muốn

**Stack policy** là một JSON document xác định CloudFormation được phép thực hiện update actions trên resources nào của stack. Mục đích là bảo vệ các tài nguyên có rủi ro cao như database hoặc storage volume khỏi bị update/replacement ngoài dự kiến.

Stack policy:

- Là lớp bảo vệ bổ sung trong quá trình stack update.
- Áp dụng cho các người dùng thực hiện update stack, không phân biệt người dùng theo policy riêng.
- Không thay IAM policy và không cấp quyền truy cập service APIs.
- Không ngăn người có quyền phù hợp sửa resource trực tiếp ngoài CloudFormation.
- Không tự bảo vệ dữ liệu khỏi mọi thao tác delete ngoài stack update.

### 12.1. Ví dụ bảo vệ database

~~~json
{
  "Statement": [
    {
      "Effect": "Deny",
      "Action": "Update:*",
      "Principal": "*",
      "Resource": "LogicalResourceId/ProductionDatabase"
    },
    {
      "Effect": "Allow",
      "Action": "Update:*",
      "Principal": "*",
      "Resource": "*"
    }
  ]
}
~~~

Logical ID ProductionDatabase là ví dụ. Policy này từ chối update database và cho phép update các resources còn lại. Cần review thứ tự/evaluation và resource matching theo tài liệu stack policy; không copy một policy mẫu vào production mà chưa kiểm tra logical IDs thực tế.

### 12.2. Mở quyền tạm thời cho một update

Nếu change set cần cập nhật resource đang được bảo vệ, stack policy hiện tại vẫn được áp dụng khi execute change set. **Không thể gửi temporary stack policy override cùng ExecuteChangeSet**. Phải cập nhật stack policy phù hợp trước hoặc chọn direct update workflow hỗ trợ temporary policy override theo API.

Sau update, đặt lại stack policy để tiếp tục bảo vệ resource. Việc nới policy cần approval và audit riêng.

### 12.3. Stack policy không thay IAM least privilege

IAM kiểm soát ai có thể gọi CloudFormation APIs và service APIs; stack policy kiểm soát resource update actions trong stack update. Một principal có quyền xóa database trực tiếp qua RDS API có thể không bị stack policy ngăn. Dùng IAM/SCP/resource policies để kiểm soát quyền truy cập thật.

## 13. Termination protection, DeletionPolicy và UpdateReplacePolicy

Ba cơ chế này giải quyết các tình huống khác nhau và không thay thế lẫn nhau.

| Cơ chế | Bảo vệ điều gì? | Khi nào áp dụng? |
|---|---|---|
| **Termination protection** | Ngăn xóa cả stack | Khi ai đó gọi DeleteStack |
| **DeletionPolicy** | Quy định xử lý resource khi resource bị xóa khỏi stack hoặc stack bị xóa | Resource removal/stack deletion |
| **UpdateReplacePolicy** | Quy định xử lý physical resource cũ sau khi CloudFormation thay thế resource khi update | Resource replacement |

### 13.1. Termination protection

Stack mới mặc định không bật termination protection. Khi bật, thao tác DeleteStack trực tiếp bị từ chối và stack giữ nguyên trạng thái. Với nested stacks, termination protection được điều khiển từ root stack.

~~~bash
aws cloudformation update-termination-protection \
  --stack-name orders-prod \
  --enable-termination-protection \
  --region ap-southeast-1
~~~

Termination protection **không ngăn stack update xóa hoặc thay thế resource** nếu template update yêu cầu. Nó chỉ bảo vệ thao tác xóa stack; không phải cơ chế chống mọi resource deletion.

### 13.2. DeletionPolicy

Ví dụ giữ database khi stack bị xóa:

~~~yaml
Resources:
  ProductionDatabase:
    Type: AWS::RDS::DBInstance
    DeletionPolicy: Retain
    Properties:
      DBInstanceClass: db.t3.medium
      Engine: postgres
      AllocatedStorage: 100
~~~

DeletionPolicy thường có các lựa chọn như Delete, Retain và Snapshot đối với các resource types hỗ trợ. Với RDS, Snapshot có thể giữ snapshot trước khi resource bị xóa; behavior và hỗ trợ tùy resource type. **Retain** giữ physical resource lại nhưng CloudFormation không còn quản lý nó như một resource trong stack sau khi xóa khỏi stack.

### 13.3. UpdateReplacePolicy

Khi update buộc phải replacement, UpdateReplacePolicy quyết định cách xử lý physical resource cũ sau khi resource mới được tạo:

~~~yaml
Resources:
  ProductionDatabase:
    Type: AWS::RDS::DBInstance
    DeletionPolicy: Snapshot
    UpdateReplacePolicy: Snapshot
    Properties:
      DBInstanceClass: db.t3.medium
      Engine: postgres
      AllocatedStorage: 100
~~~

Ví dụ đặt Snapshot cho RDS resource; cần xác minh resource type hỗ trợ và snapshot constraints. UpdateReplacePolicy khác DeletionPolicy: một policy áp dụng khi resource bị remove/stack deletion, policy còn lại áp dụng khi update thay physical resource.

### 13.4. Không nhầm Retain với backup

Retain giữ resource lại nhưng không chứng minh dữ liệu có thể restore, không tạo backup mới và không kiểm tra RPO/RTO. Snapshot cũng cần kiểm tra trạng thái, encryption key, retention, cross-account/Region copy và restore tests.

## 14. Drift detection trước và sau update

**Drift** xuất hiện khi actual resource configuration khác với template/parameter values CloudFormation quản lý. Ví dụ một kỹ sư thêm ingress rule trực tiếp trong EC2 Security Group console nhưng không sửa template.

Drift có thể khiến:

- Change set không phản ánh đầy đủ khác biệt mà operator mong đợi.
- Update sau đó ghi đè thay đổi ngoài template.
- Rollback không khôi phục được cấu hình ngoài band.
- Stack deletion/update gặp dependency hoặc state mismatch.

### 14.1. Detect drift

~~~bash
aws cloudformation detect-stack-drift \
  --stack-name orders-prod \
  --region ap-southeast-1
~~~

Lệnh trả về StackDriftDetectionId. Theo dõi tiến trình:

~~~bash
aws cloudformation describe-stack-drift-detection-status \
  --stack-drift-detection-id DETECTION_ID \
  --region ap-southeast-1
~~~

Khi detection hoàn tất, xem drifted resources:

~~~bash
aws cloudformation describe-stack-resource-drifts \
  --stack-name orders-prod \
  --stack-resource-drift-status-filters MODIFIED DELETED \
  --region ap-southeast-1 \
  --output table
~~~

### 14.2. Giới hạn drift detection

CloudFormation chỉ so sánh các resource properties được hỗ trợ và các giá trị được set rõ trong template/parameters. Default values không được khai báo tường minh có thể không được drift-check. Drift detection trên root stack không tự detect drift của nested stacks; cần chạy riêng cho child stacks.

Trạng thái IN_SYNC có nghĩa các properties được hỗ trợ và đã kiểm tra khớp expected configuration; không chứng minh mọi behavior/application data đều đúng.

### 14.3. Cách xử lý drift

1. Xác định ai thay đổi, khi nào và lý do.
2. Đánh giá thay đổi ngoài band có cần giữ không.
3. Nếu thay đổi hợp lệ, cập nhật template/parameters để desired state phản ánh cấu hình mới.
4. Nếu thay đổi không hợp lệ, dùng CloudFormation update hoặc service APIs có kiểm soát để đưa resource về trạng thái mong muốn.
5. Detect drift lại và review change set trước lần update kế tiếp.

Không tự động “fix all drift” khi chưa biết ý nghĩa vận hành. Một thay đổi manual có thể là mitigation đang bảo vệ production; cần hiểu trước khi hoàn tác.

## 15. Nested stacks và change sets

Nested stack cho phép chia template lớn thành các template con có trách nhiệm riêng, ví dụ network, database, compute và monitoring. Root stack tham chiếu child template bằng resource type AWS::CloudFormation::Stack.

### 15.1. Change sets cho nested stacks

Khi tạo change set, CloudFormation có thể tạo change sets cho nested stacks. Nested change sets thường được bật mặc định; có thể chọn Disabled nếu chỉ muốn change set của stack hiện tại. Khi review production, nên xem root và child change sets vì thay đổi nhỏ ở parent có thể lan tới nhiều child resources.

### 15.2. Execute root change set

Đối với nested stack changes, execute root change set. CloudFormation sẽ thực thi các nested change sets liên quan nếu đã bật nested change sets khi tạo. Theo dõi events ở root và child stacks.

### 15.3. Rollback nested stacks

Khi rollback parent stack, CloudFormation cũng cố rollback child stacks. Nếu rollback thất bại ở nested resource, phải xác định child stack name và logical ID. Khi skip resource nested, format là:

~~~text
NestedStackName.ResourceLogicalID
~~~

Ví dụ:

~~~bash
aws cloudformation continue-update-rollback \
  --stack-name WebInfra \
  --resources-to-skip WebInfra-Storage.Database \
  --region ap-southeast-1
~~~

Tên child stack là ví dụ; phải lấy đúng nested stack physical name và logical ID từ stack resources/events. Không đoán tên child stack theo logical ID.

## 16. CloudFormation service role và deployment identity

CloudFormation có thể assume **service role** để gọi các AWS service APIs thay mặt người thực hiện stack operation. Role này khác với IAM identity của developer/CI đang gọi CloudFormation API.

| Identity | Vai trò |
|---|---|
| Developer/CI deploy role | Tạo change set, review/execute theo quyền được cấp |
| CloudFormation service role | CloudFormation assume để tạo/sửa/xóa EC2, RDS, IAM, S3, v.v. |
| Application runtime role | Code trong ECS/EKS/Lambda/EC2 dùng khi chạy nghiệp vụ |

### 16.1. Vì sao service role quan trọng?

Khi gắn service role vào stack, CloudFormation dùng role đó cho các operation tiếp theo. Người có quyền thao tác stack có thể khiến CloudFormation dùng role đã gắn, ngay cả khi principal không có quyền pass role đó trong mỗi operation. Vì vậy service role có thể trở thành **quyền gián tiếp** của những người được phép update stack.

### 16.2. Least privilege cho CloudFormation service role

- Chỉ cấp actions cần để quản lý resource types trong stack.
- Scope resource ARNs và conditions khi service hỗ trợ.
- Giới hạn iam:PassRole vào các runtime roles cụ thể.
- Không dùng AdministratorAccess làm service role mặc định.
- Review trust policy cho cloudformation.amazonaws.com.
- Audit role ARN trên stack và thay đổi permissions.
- Tách service roles cho stack/app có phạm vi quyền khác nhau khi phù hợp.

### 16.3. Gắn role khi tạo change set

Ví dụ:

~~~bash
aws cloudformation create-change-set \
  --stack-name orders-prod \
  --change-set-name release-2026-11-20 \
  --change-set-type UPDATE \
  --template-body file://template.yaml \
  --role-arn arn:aws:iam::444455556666:role/orders-cloudformation-service-role \
  --region ap-southeast-1
~~~

Chỉ định role ARN phải phù hợp với trust policy và permissions. Nếu stack đã gắn service role, operation có thể tiếp tục dùng role hiện tại khi không chỉ định role mới. Việc thay service role cần review vì ảnh hưởng tất cả future stack operations.

## 17. Parameters, capabilities và dynamic references

Change set chỉ có ý nghĩa khi input giống release dự định. Template đúng nhưng parameter sai có thể cập nhật nhầm account/resource, thay instance class ngoài kế hoạch hoặc trỏ application sang sai endpoint.

### 17.1. Giữ nguyên parameter hiện tại khi phù hợp

Khi cập nhật stack, có thể giữ giá trị parameter cũ bằng UsePreviousValue:

~~~bash
aws cloudformation create-change-set \
  --stack-name orders-prod \
  --change-set-name update-app-capacity \
  --change-set-type UPDATE \
  --template-body file://template.yaml \
  --parameters \
    ParameterKey=Environment,UsePreviousValue=true \
    ParameterKey=InstanceType,ParameterValue=t3.medium \
  --region ap-southeast-1
~~~

Không giả định mọi parameter đều nên giữ nguyên. Review các parameter có default mới, AllowedValues, NoEcho, dynamic references và conditions. Ghi nhận parameter values đã được phê duyệt trong deployment record.

### 17.2. Capabilities cho IAM resources và macros

Nếu template tạo/cập nhật IAM resources:

- **CAPABILITY_IAM:** acknowledge template có IAM resources không dùng custom names theo cách yêu cầu capability khác.
- **CAPABILITY_NAMED_IAM:** acknowledge template có IAM resources với custom names.
- **CAPABILITY_AUTO_EXPAND:** liên quan macros/transform khi workflow yêu cầu acknowledge auto expansion.

Ví dụ:

~~~bash
aws cloudformation create-change-set \
  --stack-name orders-prod \
  --change-set-name update-iam-role \
  --change-set-type UPDATE \
  --template-body file://template.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-southeast-1
~~~

Capabilities chỉ là acknowledgement để CloudFormation tiếp tục; nó **không thay review IAM policies**. Review trust policy, actions, resources, conditions, permissions boundaries và iam:PassRole.

### 17.3. Không truyền secret plaintext qua parameters

Không đặt database password/API token trực tiếp trong command line hoặc parameter overrides; chúng có thể xuất hiện trong shell history, CI logs hoặc deployment records. Dùng dynamic references tới Secrets Manager/SSM SecureString khi resource property hỗ trợ, hoặc để ứng dụng lấy secret runtime bằng IAM role.

Ví dụ dynamic reference:

~~~yaml
Resources:
  AppDatabase:
    Type: AWS::RDS::DBInstance
    Properties:
      MasterUsername: orders_admin
      MasterUserPassword: '{{resolve:secretsmanager:orders/prod/database:SecretString:password}}'
      Engine: postgres
      DBInstanceClass: db.t3.medium
      AllocatedStorage: 100
~~~

Dynamic reference có thể không hiển thị secret value trong change set; điều đó không có nghĩa giá trị secret đã được validate. Cần kiểm tra secret tồn tại, version/rotation behavior, KMS permissions và resource property constraints.

### 17.4. Xử lý change set không có thay đổi

Nếu template và parameters mới không tạo ra resource changes, CloudFormation có thể trả change set FAILED với reason cho biết không có updates. Đây thường là no-op, không phải lỗi hạ tầng cần rollback. Xác minh:

- Đúng stack/Region/account chưa?
- Template artifact có đúng commit mới không?
- Parameters có bị giữ nguyên hoặc ghi đè ngoài ý muốn không?
- Conditions/mappings có khiến thay đổi không áp dụng không?
- Resource đã có desired value chưa?

Không cố execute change set no-op. Nếu thay đổi mong muốn không xuất hiện, sửa template/inputs và tạo change set mới.

## 18. Quản lý change set không còn dùng

Một stack có thể có nhiều change sets để so sánh phương án. Khi đã quyết định không triển khai một phương án, xóa change set để tránh operator khác execute nhầm.

~~~bash
aws cloudformation list-change-sets \
  --stack-name orders-prod \
  --region ap-southeast-1 \
  --output table

aws cloudformation delete-change-set \
  --stack-name orders-prod \
  --change-set-name update-instance-type-2026-11-20 \
  --region ap-southeast-1
~~~

Sau khi execute một change set, các change sets khác của stack không còn phù hợp với stack state mới và bị CloudFormation xóa/đánh dấu obsolete. Nếu update thất bại, tạo change set mới sau khi stack trở lại trạng thái cho phép update.

## 19. Update failure behavior và tài nguyên tạo dở

Trong một số workflow, CloudFormation cho phép chọn behavior khi provisioning thất bại, bao gồm rollback hoặc giữ lại các resources đã provision thành công để phục vụ điều tra. Tùy chọn này ảnh hưởng resource states và cleanup ở operation tiếp theo.

### 19.1. Rollback khi update thất bại

Đây là lựa chọn phổ biến cho production: tài nguyên thất bại được đưa về last known stable state nếu rollback thành công. Theo dõi events để biết resource nào đã update, resource nào rollback và resource nào gặp lỗi.

### 19.2. Preserve successfully provisioned resources

Giữ lại resources đã provision thành công có thể hữu ích khi:

- Đang triển khai một stack mới hoặc một nhóm resources độc lập.
- Cần kiểm tra resource được tạo trước khi operation thất bại.
- Có runbook rõ ràng để tiếp tục/cleanup phần còn lại.

Nhưng resource giữ lại có thể chưa được stack quản lý theo trạng thái cuối mà team kỳ vọng, có thể phát sinh chi phí và phải được reconcile trước operation tiếp theo. Không chọn chế độ giữ resource chỉ để né rollback trong production.

### 19.3. Resource không có last known stable state

Một resource mới tạo nhưng operation chưa đạt stable state có thể bị xóa ở stack operation kế tiếp. Đọc status reason và failure options của CloudFormation đúng phiên bản; không giả định resource đang nhìn thấy trong console sẽ luôn tồn tại sau operation tiếp theo.

## 20. Quy trình rollback và phục hồi theo từng cấp độ

Rollback nên được phân loại trước khi chạy lệnh:

| Cấp độ | Tình trạng | Hành động |
|---|---|---|
| **A — Update fail, rollback tự động hoàn tất** | UPDATE_ROLLBACK_COMPLETE | Giữ stack, điều tra root cause, tạo change set mới sau khi sửa |
| **B — Rollback đang chạy** | UPDATE_ROLLBACK_IN_PROGRESS | Theo dõi events, chờ resource operation hoàn tất |
| **C — Rollback thất bại** | UPDATE_ROLLBACK_FAILED | Khắc phục blocker rồi ContinueUpdateRollback |
| **D — Resource không thể rollback** | Một vài resources rollback failed | Xem xét ResourcesToSkip tối thiểu hoặc force rollback có phê duyệt |
| **E — Data/application side effects** | Stack rollback nhưng dữ liệu hoặc external systems đã đổi | Chạy application/data recovery runbook riêng |

### 20.1. Không xóa stack để chữa UPDATE_ROLLBACK_FAILED

Xóa stack có thể làm mất resource và dữ liệu còn lại, đồng thời không giải quyết nguyên nhân rollback thất bại. Trước hết phải hiểu resource nào bị lỗi, data retention policies và physical IDs. Dùng ContinueUpdateRollback để đưa stack về trạng thái operable khi có thể.

### 20.2. Rollback application và rollback infrastructure

CloudFormation rollback template/resources không tự động rollback:

- Database schema migrations do application thực hiện.
- Message đã gửi tới SQS/SNS/EventBridge.
- Data writes đã commit vào RDS/DynamoDB.
- External API side effects.
- DNS caches/client connection state.

Thiết kế deployment backward-compatible: expand/contract DB migrations, versioned event schemas, idempotency và feature flags. Khi hạ tầng quay lại phiên bản cũ, application/data layer vẫn phải hoạt động an toàn.

### 20.3. Rollback không xóa mọi resource được Retain

DeletionPolicy/UpdateReplacePolicy và operation settings ảnh hưởng việc resource cũ/mới tồn tại sau rollback. Kiểm tra physical resources, snapshots và costs sau rollback; không suy luận chỉ từ stack status.

## 21. Chi phí và tác động vận hành khi cập nhật

Change set tự nó không triển khai resource, nhưng execution có thể tạo resource mới trước khi xóa resource cũ. Trong thời gian replacement hoặc blue/green cutover, chi phí có thể tăng tạm thời.

| Tác động | Ví dụ | Cách kiểm soát |
|---|---|---|
| **Temporary double capacity** | RDS replacement hoặc ASG rolling update | Ước lượng chi phí hai resource cùng tồn tại |
| **Snapshots/backups** | Snapshot trước khi xóa RDS/EBS | Đặt retention, encryption và cleanup owner |
| **Data transfer** | Replicate/copy data cross-AZ/Region | Tính phí transfer và thời gian sync |
| **Long monitoring window** | Rollback trigger monitoring giữ resources cũ | Chọn period phù hợp, theo dõi cleanup |
| **Failed resources** | Preserve successful resources hoặc rollback chưa xong | Có cleanup plan và owner |
| **Retries/operations** | Nhiều lần tạo change set/update | Giảm deploy churn, sửa root cause |

Không chọn replacement chỉ vì template diff gọn. Cần cân nhắc downtime, cost, data safety và khả năng quay lại.

## 22. Runbook triển khai một stack update

Runbook mẫu cho một lần update production:

### Giai đoạn A — Chuẩn bị

1. Xác nhận release commit, template artifact và checksum/version.
2. Xác minh account, Region, stack ID, stack status và CloudFormation service role.
3. Kiểm tra stack drift và các resources quan trọng.
4. Xác nhận backup/snapshot, maintenance window, quota và dependencies.
5. Xác minh CloudWatch alarms, rollback triggers và dashboard.
6. Chạy unit/template validation và các kiểm tra policy trước deployment.

### Giai đoạn B — Tạo và review change set

1. Tạo change set từ template/parameters đã version.
2. Chờ CREATE_COMPLETE và ExecutionStatus AVAILABLE.
3. Đọc mọi resource actions, replacement flags và property-level diffs.
4. Review IAM/security/network/database changes.
5. Review nested stack changes và rollback configuration.
6. Lưu change set ARN/ID, commit, parameters đã redaction và approval record.
7. Nếu không được duyệt, delete change set.

### Giai đoạn C — Execute và monitor

1. Execute đúng change set ID đã review.
2. Theo dõi stack status và stack events.
3. Nếu UPDATE_FAILED, đọc resource reason và để rollback hoàn tất theo policy.
4. Nếu rollback triggers chuyển ALARM, xác minh application metrics và rollback events.
5. Không tạo operation mới khi stack đang update/rollback.

### Giai đoạn D — Verify hoặc recover

1. Khi UPDATE_COMPLETE, chạy smoke tests và xác minh application health.
2. Kiểm tra physical IDs, outputs, DNS/endpoints, IAM permissions và CloudWatch alarms.
3. Detect drift khi cần; kiểm tra resource replacements/retained resources.
4. Nếu UPDATE_ROLLBACK_COMPLETE, giữ stack và tạo change set mới sau khi sửa root cause.
5. Nếu UPDATE_ROLLBACK_FAILED, chạy rollback recovery runbook; skip resource chỉ khi có kế hoạch reconcile.
6. Ghi nhận kết quả, chi phí phát sinh, action items và release status.

~~~mermaid
flowchart TD
    PRE["Preflight: account, Region, stack, drift, backups"] --> CREATE["Create change set"]
    CREATE --> REVIEW["Review actions, replacements,<br/>security, nested stacks"]
    REVIEW --> APPROVE{"Approval"}
    APPROVE -->|"Reject"| DISCARD["Delete change set"]
    APPROVE -->|"Approve"| EXEC["Execute change set"]
    EXEC --> MON["Monitor stack events + alarms"]
    MON --> STATUS{"Terminal stack status"}
    STATUS -->|"UPDATE_COMPLETE"| TEST["Smoke tests / outputs / drift"]
    STATUS -->|"UPDATE_ROLLBACK_COMPLETE"| RCA["Root cause + new change set"]
    STATUS -->|"UPDATE_ROLLBACK_FAILED"| REC["Fix blocker + continue rollback"]
    REC --> STATUS
~~~

## 23. Bài tập tình huống

### Tình huống A — Đổi DB instance class nhưng change set báo replacement

Team muốn tăng DB instance class. Change set hiển thị AppDatabase Modify với Replacement: True.

**Câu hỏi:** có nên execute ngay vì chỉ đổi cấu hình compute?

**Gợi ý:** không. Kiểm tra resource property update behavior và engine/instance compatibility. Nếu replacement thật, cần snapshot/restore, replication/cutover, endpoint migration, downtime window, backup và cost plan. Có thể chọn phương án modify in-place nếu resource type hỗ trợ.

### Tình huống B — Change set có resource Remove không nằm trong ticket

Một template update thêm một SQS queue nhưng change set còn Remove một IAM role cũ mà team không nhắc tới.

**Câu hỏi:** làm gì trước khi execute?

**Gợi ý:** xác định resource owner/dependencies, xem conditions/logical ID/template diff, IAM role có đang được workload khác assume không. Từ chối change set cho tới khi removal được giải thích và approval riêng.

### Tình huống C — Change set không tạo được

CREATE_FAILED với StatusReason cho biết template chứa IAM resource nhưng chưa acknowledge capability.

**Câu hỏi:** thêm CAPABILITY_NAMED_IAM rồi execute luôn?

**Gợi ý:** capability chỉ acknowledge CloudFormation được phép xử lý IAM resources. Review trust/permissions policy và resource scope trước, sau đó tạo change set mới với capability đúng; không coi capability là security approval.

### Tình huống D — Update thất bại và rollback thành công

Một security group update gây service health check fail. CloudFormation đưa stack về UPDATE_ROLLBACK_COMPLETE.

**Câu hỏi:** stack có thể nhận update mới ngay không?

**Gợi ý:** thường stack đã trở lại trạng thái operable, nhưng phải đọc events, xác nhận actual resource config, tìm nguyên nhân health check và tạo change set mới. Không execute lại change set cũ.

### Tình huống E — UPDATE_ROLLBACK_FAILED vì database cũ đã bị xóa thủ công

Template update thay RDS database. Forward update thất bại; rollback cố quay lại physical database cũ nhưng DB đã bị xóa ngoài CloudFormation.

**Câu hỏi:** vì sao rollback không hoàn tất?

**Gợi ý:** CloudFormation không thể restore physical resource đã bị xóa. Kiểm tra snapshots/restore path và resource dependencies; phục hồi blocker nếu có thể, sau đó ContinueUpdateRollback. Chỉ skip database khi đã hiểu hậu quả và có plan reconcile.

### Tình huống F — Skip resource để stack hoạt động lại

Team dùng ResourcesToSkip để đưa stack về UPDATE_ROLLBACK_COMPLETE, nhưng template vẫn mô tả database properties khác với actual DB.

**Câu hỏi:** bước tiếp theo?

**Gợi ý:** không deploy tiếp. Detect drift trên database, so sánh physical state và template, xác nhận backup/data integrity rồi reconcile. CloudFormation có thể đánh dấu skipped resource UPDATE_COMPLETE nhưng điều đó không chứng minh resource khớp template.

### Tình huống G — Rollback trigger báo ALARM sau deploy

Stack update hoàn tất resource provisioning nhưng alarm 5xx chuyển ALARM trong monitoring period 15 phút.

**Câu hỏi:** CloudFormation làm gì và team cần làm gì?

**Gợi ý:** rollback trigger có thể khiến CloudFormation rollback toàn bộ stack operation. Theo dõi events và alarm, kiểm tra deployment/application logs, data side effects và external systems. Sau rollback, verify app behavior và tạo change set mới sau khi fix.

### Tình huống H — Change set preview sạch nhưng runtime update fail

Change set không có replacement, nhưng khi execute resource tạo mới bị service quota exceeded.

**Câu hỏi:** change set có lỗi không?

**Gợi ý:** change set chỉ preview và prevalidate một số failure causes; không bảo đảm resource operation sẽ thành công. Kiểm tra quota, request increase nếu cần, rollback state và thử lại bằng change set mới.

### Tình huống I — Drift do emergency manual change

Trong incident, kỹ sư thêm ingress rule trực tiếp trên security group. Ngày hôm sau CloudFormation update template và rule bị loại bỏ.

**Câu hỏi:** cách vận hành đúng?

**Gợi ý:** sau emergency change, ghi nhận và cập nhật template/parameter desired state hoặc hoàn tác manual change có kiểm soát. Detect drift trước update, không để template cũ vô tình ghi đè mitigation.

### Tình huống J — Stack policy chặn database update

Change set hợp lệ nhưng execute thất bại vì stack policy Deny Update:* cho ProductionDatabase.

**Câu hỏi:** thêm IAM AdministratorAccess có giải quyết không?

**Gợi ý:** không. Stack policy là guardrail update của CloudFormation, khác IAM. Review change, cập nhật stack policy qua quy trình được phê duyệt hoặc dùng direct update workflow với temporary policy override nếu phù hợp; sau đó khôi phục policy bảo vệ.

### Tình huống K — Stack có termination protection nhưng update vẫn xóa resource

Team tin bật termination protection sẽ ngăn mọi resource deletion. Một change set vẫn đề xuất Remove S3 bucket khỏi stack.

**Câu hỏi:** tại sao?

**Gợi ý:** termination protection ngăn DeleteStack, không ngăn update xóa/thay thế resource. Cần DeletionPolicy, stack policy, IAM/resource policies và review change set.

### Tình huống L — Parent stack update nhưng nested child stack lỗi

Root stack change set có update network và database child stacks. Child database stack rollback fail.

**Câu hỏi:** xác định resource skip nested thế nào?

**Gợi ý:** xem root/child stack events và stack resource physical IDs. Với ResourcesToSkip, dùng nested stack physical name cộng logical resource ID; rollback parent sẽ điều phối child stacks. Reconcile cả hierarchy trước update tiếp theo.

### Tình huống M — CloudFormation service role quá rộng

CI deploy role chỉ có quyền ExecuteChangeSet nhưng stack gắn service role có AdministratorAccess. Một pipeline change set có thể tạo IAM policy mới.

**Câu hỏi:** vì sao đây vẫn là rủi ro?

**Gợi ý:** CloudFormation dùng service role đã gắn cho các operations; quyền thao tác stack có thể gián tiếp sử dụng role đó. Thu hẹp service role, review iam:PassRole, stack resource policies và pipeline approval.

### Tình huống N — Alarm không tồn tại

Change set khai báo rollback trigger ARN nhưng alarm đã bị xóa hoặc nằm ở Region khác.

**Câu hỏi:** operation có thể diễn ra thế nào?

**Gợi ý:** nếu trigger không tồn tại/không truy cập được, stack operation có thể fail và rollback. Xác minh alarm ARN, Region, account, permissions và alarm state trước deployment.

### Tình huống O — Rollback stack thành công nhưng order đã gửi hai lần

Custom resource hoặc application hook gửi event tới SQS trước khi một resource khác fail. CloudFormation rollback stack nhưng message đã được consumer xử lý.

**Câu hỏi:** rollback có thu hồi message không?

**Gợi ý:** không. Side effects ngoài CloudFormation cần idempotency, deduplication, outbox/workflow compensation và application recovery. Thiết kế custom resources với create/update/delete handlers idempotent.

## 24. Checklist production

- [ ] Đã xác minh đúng account, Region, stack ID, status và CloudFormation service role.
- [ ] Template/parameters có version/commit và được review.
- [ ] Stack không ở trạng thái operation đang chạy hoặc UPDATE_ROLLBACK_FAILED.
- [ ] Drift đã được kiểm tra trên resources quan trọng.
- [ ] Backup/snapshot/restore plan có cho stateful resources.
- [ ] Change set được tạo và có CREATE_COMPLETE/AVAILABLE.
- [ ] Mọi Add/Modify/Remove/Import đã được review.
- [ ] Replacement True/Conditional được đánh giá downtime, data migration, endpoint cutover và chi phí.
- [ ] IAM capabilities và IAM policy changes được review.
- [ ] Security groups, KMS, bucket policies, endpoint policies và encryption được review.
- [ ] Nested stack change sets đã được xem xét.
- [ ] Parameters, dynamic references, capabilities và role ARN khớp release.
- [ ] Rollback triggers trỏ tới alarms tồn tại, đúng account/Region và có metrics.
- [ ] Monitoring period đủ cho app warm-up và smoke tests.
- [ ] Stack policy bảo vệ resources critical và có quy trình override.
- [ ] Termination protection bật cho stack cần bảo vệ khỏi DeleteStack.
- [ ] DeletionPolicy/UpdateReplacePolicy phù hợp với data retention requirements.
- [ ] CloudFormation service role least privilege; iam:PassRole giới hạn.
- [ ] CI deploy identity tách khỏi CloudFormation service role và application runtime role.
- [ ] Execute đúng change set đã duyệt; change sets cũ được dọn.
- [ ] Stack events và resource status reasons được theo dõi đến trạng thái terminal.
- [ ] UPDATE_COMPLETE được xác nhận bằng smoke tests và application metrics.
- [ ] UPDATE_ROLLBACK_COMPLETE được điều tra trước khi thử update tiếp.
- [ ] UPDATE_ROLLBACK_FAILED được phục hồi theo runbook; skip resources là phương án cuối.
- [ ] Sau skip resource, detect drift và reconcile template/physical state trước update kế tiếp.
- [ ] Side effects của application/data migrations có compensation/idempotency plan.
- [ ] Retained/replaced resources và snapshots có owner/cleanup plan.
- [ ] Kết quả deployment, stack events, change set ARN, approval và rollback decision được lưu audit.

## 25. Ghi nhớ

**Change set là bước review trước khi cập nhật CloudFormation stack.** Tạo change set không thay đổi tài nguyên; execute mới bắt đầu update. Hãy đọc action Add/Modify/Remove/Import, replacement flags, property-level differences, IAM/security changes, parameters và nested stack changes. Change set giúp thấy trước tác động nhưng không bảo đảm update sẽ thành công.

Khi update thất bại, CloudFormation thường tự rollback. **UPDATE_ROLLBACK_COMPLETE** cho biết rollback đã hoàn tất và stack có thể được xử lý tiếp sau khi điều tra. **UPDATE_ROLLBACK_FAILED** nghĩa là rollback chưa hoàn tất; cần sửa blocker rồi ContinueUpdateRollback. ResourcesToSkip/force rollback chỉ nên dùng khi thật sự cần, vì skipped resources có thể không khớp template và phải reconcile trước update kế tiếp.

Để giảm rủi ro, dùng rollback triggers/CloudWatch alarms, stack policies, termination protection, DeletionPolicy/UpdateReplacePolicy, CloudFormation service role least privilege và drift detection. Cuối cùng, nhớ rằng CloudFormation rollback không đảo ngược database writes, messages hoặc external side effects; cần backup/restore, idempotency, smoke tests và runbook application riêng.

### Tài liệu AWS chính thức để đối chiếu

- [Update CloudFormation stacks using change sets](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-updating-stacks-changesets.html) — quy trình tạo, xem và execute change sets.
- [Create a change set](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-updating-stacks-changesets-create.html) — parameters, capabilities và nested stacks.
- [Execute a change set](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-updating-stacks-changesets-execute.html) — execution behavior và stack policies.
- [Update stacks directly](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-updating-stacks-direct.html) — update flow và rollback.
- [CloudFormation best practices](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/best-practices.html) — change sets, drift và rollback triggers.
- [Continue rolling back an update](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-updating-stacks-continueupdaterollback.html) — UPDATE_ROLLBACK_FAILED, ResourcesToSkip và force rollback.
- [Troubleshooting CloudFormation](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/troubleshooting.html) — các nguyên nhân rollback failure.
- [Rollback triggers](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-rollback-triggers.html) — CloudWatch alarms và monitoring period.
- [RollbackConfiguration API](https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_RollbackConfiguration.html) — triggers và MonitoringTimeInMinutes.
- [Stack policies](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/protect-stack-resources.html) — bảo vệ resource khỏi update ngoài ý muốn.
- [Termination protection](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-protect-stacks.html) — ngăn xóa stack.
- [Drift detection](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-stack-drift.html) — phát hiện thay đổi ngoài template.
- [Detect drift on a stack](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/detect-drift-stack.html) — thao tác drift detection.
- [CloudFormation UpdateStack API](https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_UpdateStack.html) — RoleARN, rollback configuration và stack policy.





