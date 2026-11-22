# Log group, log stream, retention và quyền truy cập log

> **Chương:** Quan sát với CloudWatch  
> **Học phần:** `CLOUD_PROVIDERS_AWS` — khám phá hệ sinh thái AWS qua Region/AZ, IAM, VPC, dịch vụ tính toán, lưu trữ, cơ sở dữ liệu, tích hợp và serverless; rèn khả năng chọn dịch vụ, thiết kế và triển khai ứng dụng an toàn, có giám sát, phục hồi và kiểm soát chi phí.

Khi một ứng dụng chạy trên AWS, log là bằng chứng quan trọng để tìm lỗi, hiểu hành vi request, theo dõi hoạt động bảo mật và điều tra sự cố. Amazon CloudWatch Logs cung cấp nơi tập trung log từ Lambda, EC2, ECS, EKS, ứng dụng và nhiều dịch vụ AWS. Để quản lý log hiệu quả, cần hiểu cách tổ chức log group/log stream, thời gian lưu giữ, cơ chế cấp quyền và cách giới hạn quyền đọc log.

Log thường chứa thông tin nhạy cảm như email, token, địa chỉ IP, thông tin đơn hàng hoặc dữ liệu nghiệp vụ. Một cấu hình log thiếu retention có thể làm chi phí lưu trữ tăng không kiểm soát; một IAM policy quá rộng có thể khiến người không cần thiết đọc được dữ liệu; một resource policy sai có thể mở đường cho tài khoản khác gửi log vào hoặc đọc log ngoài phạm vi dự kiến.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích quan hệ giữa log event, log stream và log group trong CloudWatch Logs.
2. Chọn cách tổ chức log group/stream theo ứng dụng, môi trường và nguồn phát log.
3. Cấu hình log group, retention và encryption phù hợp.
4. Phân biệt quyền ghi log của workload với quyền đọc, truy vấn và quản trị log.
5. Viết IAM identity policy theo least privilege cho CloudWatch Logs.
6. Giải thích vai trò của CloudWatch Logs resource policies trong việc nhận log từ dịch vụ/tài khoản khác.
7. Cấp quyền dùng KMS key khi log group được mã hóa bằng customer managed key.
8. Thiết kế cross-account logging, subscription filters và quyền truy cập log tập trung.
9. Giảm rủi ro lộ dữ liệu nhạy cảm và quản lý chi phí lưu trữ.
10. Điều tra lỗi phổ biến liên quan đến log group, log stream, retention và AccessDenied.

## 2. CloudWatch Logs tổ chức dữ liệu như thế nào?

CloudWatch Logs có ba khái niệm cơ bản:

- **Log event:** một bản ghi gồm timestamp và message. Message có thể là một dòng text, JSON hoặc định dạng do ứng dụng phát ra.
- **Log stream:** chuỗi log events từ cùng một nguồn phát log trong một log group, thường gắn với một instance, container, function execution environment hoặc nguồn cụ thể.
- **Log group:** vùng chứa logic cho nhiều log streams có cùng mục đích, cấu hình lưu giữ, quyền và chính sách quản lý.

~~~mermaid
flowchart TD
    APP["Application / AWS service"] --> GROUP["CloudWatch Logs log group"]
    GROUP --> S1["Log stream: instance-A"]
    GROUP --> S2["Log stream: instance-B"]
    GROUP --> S3["Log stream: container-C"]
    S1 --> E1["Timestamp + message"]
    S1 --> E2["Timestamp + message"]
    S2 --> E3["Timestamp + message"]
    S3 --> E4["Timestamp + message"]
~~~

Log group là đơn vị quan trọng để áp dụng retention, encryption, data protection, tags và một số quyền truy cập. Log stream giúp tách luồng ghi theo nguồn phát; người vận hành có thể xem các stream riêng hoặc truy vấn toàn group.

### 2.1. Ví dụ log event

Một ứng dụng có thể ghi log JSON:

~~~json
{
  "timestamp": "2026-11-20T04:30:00Z",
  "level": "ERROR",
  "service": "order-api",
  "requestId": "req-7f91",
  "message": "Payment authorization failed",
  "errorCode": "PAYMENT_PROVIDER_TIMEOUT"
}
~~~

Trong CloudWatch Logs, mỗi event vẫn có timestamp và message; JSON nằm bên trong message. CloudWatch Logs Insights có thể parse trường JSON để truy vấn theo `level`, `service`, `requestId` hoặc `errorCode`.

Không đưa access token, password, secret key, card data hoặc dữ liệu cá nhân không cần thiết vào message. Mask dữ liệu ở application logger trước khi gửi log.

## 3. Thiết kế tên log group và log stream

Tên log group nên phản ánh service, môi trường và mục đích. Một convention dễ đọc:

~~~text
/<platform>/<environment>/<service>/<purpose>

/platform/prod/order-api/application
/platform/prod/order-api/audit
/platform/staging/order-api/application
/platform/prod/payment-worker/application
~~~

Với các AWS services có convention riêng, giữ đúng tên group mặc định nếu dịch vụ yêu cầu hoặc tích hợp tự động phụ thuộc vào tên đó, ví dụ Lambda thường dùng:

`/aws/lambda/<function-name>`

### 3.1. Nguyên tắc đặt tên

- Có environment rõ ràng: `dev`, `staging`, `prod`.
- Có service/team owner để xác định ai chịu trách nhiệm.
- Phân biệt application logs, audit logs và security logs khi retention/access cần khác nhau.
- Không nhúng email, account ID người dùng, session ID hoặc dữ liệu nhạy cảm vào tên group/stream.
- Không tạo log group theo từng request hoặc từng user; số lượng group tăng nhanh và khó quản trị.
- Dùng naming convention nhất quán giữa Region/account.

### 3.2. Log stream naming

Stream có thể được đặt theo nguồn:

~~~text
instance/i-0123456789abcdef0
ecs/order-api/cluster-a/task-7d9c
lambda/order-api/2026/11/20/[$LATEST]abc123
~~~

Đây là ví dụ minh họa; tên thực tế phụ thuộc dịch vụ hoặc agent. Không tự tạo stream cho mỗi event. Một nguồn phát nên tái sử dụng stream theo cách agent/service hỗ trợ và quản lý việc tạo stream phù hợp.

### 3.3. Tách application log và audit log

Application logs phục vụ debug/operations. Audit logs ghi lại hoạt động cần truy vết, ví dụ thay đổi quyền, cập nhật trạng thái đơn hàng hoặc hành động quản trị. Hai loại này thường khác nhau về:

- Quyền đọc: audit có thể giới hạn cho security/compliance roles.
- Retention: audit có thể cần lưu lâu hơn theo chính sách tổ chức.
- Integrity: audit có thể cần lưu bản sao bất biến hoặc chuyển sang hệ thống lưu trữ chuyên dụng.
- Alerting: một số audit events cần cảnh báo ngay khi xuất hiện.

CloudWatch Logs là một phần của audit pipeline, nhưng log application thông thường không tự trở thành hồ sơ audit đáng tin cậy. Phải thiết kế nguồn sự kiện, quyền ghi, bảo vệ, lưu trữ và quy trình điều tra riêng.

## 4. Tạo log group và log stream

Log group có thể được tạo:

- Tự động bởi một AWS service khi workload bắt đầu ghi log, nếu service/configuration hỗ trợ.
- Bằng AWS Console, AWS CLI, SDK hoặc CloudFormation.
- Bằng IaC trước khi workload được triển khai.

Tạo trước log group giúp chủ động cấu hình retention, KMS encryption, tags và access controls. Nếu ứng dụng tự tạo group lúc khởi động, workload cần quyền `logs:CreateLogGroup`; điều này có thể không cần nếu group đã được provision sẵn.

### 4.1. AWS CLI: tạo log group và stream

~~~bash
aws logs create-log-group \
  --log-group-name /platform/prod/order-api/application \
  --region ap-southeast-1

aws logs create-log-stream \
  --log-group-name /platform/prod/order-api/application \
  --log-stream-name order-api-instance-a \
  --region ap-southeast-1
~~~

Nếu group hoặc stream đã tồn tại, lệnh create có thể trả lỗi resource already exists. Trong automation, xử lý trạng thái idempotent: kiểm tra resource trước hoặc bắt đúng lỗi đã tồn tại, không bỏ qua mọi exception.

### 4.2. Gửi log event bằng CLI

~~~bash
aws logs put-log-events \
  --log-group-name /platform/prod/order-api/application \
  --log-stream-name order-api-instance-a \
  --log-events timestamp=1795149000000,message="order-api started" \
  --region ap-southeast-1
~~~

Timestamp của log event dùng Unix epoch milliseconds. Trong ứng dụng, ưu tiên AWS SDK/logging agent hoặc service integration; không gọi CLI cho từng log message.

CloudWatch Logs API có giới hạn về kích thước event, batch, tần suất và thứ tự timestamp. Hãy kiểm tra quota hiện hành theo Region/service và thiết kế batching, retry, buffering đúng cách.

### 4.3. Tạo log group bằng CloudFormation

~~~yaml
Resources:
  OrderApiLogGroup:
    Type: AWS::Logs::LogGroup
    Properties:
      LogGroupName: /platform/prod/order-api/application
      RetentionInDays: 30
      Tags:
        - Key: Service
          Value: order-api
        - Key: Environment
          Value: prod
~~~

Provision log group bằng IaC cho phép review retention và tags trong pull request. Nếu log group được CloudFormation quản lý, không tạo thủ công cùng tên ngoài stack rồi để hai bên tranh ownership.

### 4.4. Tạo log group trước Lambda

Ví dụ Lambda cần dùng log group có retention cố định:

~~~yaml
Resources:
  OrderApiLogGroup:
    Type: AWS::Logs::LogGroup
    Properties:
      LogGroupName: /aws/lambda/order-api
      RetentionInDays: 30

  OrderApiFunction:
    Type: AWS::Lambda::Function
    DependsOn: OrderApiLogGroup
    Properties:
      FunctionName: order-api
      Runtime: java21
      Handler: example.Handler::handleRequest
      Role: !GetAtt OrderApiExecutionRole.Arn
      Code:
        S3Bucket: deployment-artifacts
        S3Key: order-api/function.zip
      Timeout: 20
      MemorySize: 512
~~~

`OrderApiExecutionRole` và artifact bucket/key là các thành phần giả định đã được định nghĩa/cấp quyền trong template triển khai thực tế. Tên log group theo convention Lambda giúp function ghi vào group đó. Nếu dùng log group custom, cấu hình logging destination theo cơ chế Lambda hỗ trợ và kiểm tra quyền tương ứng.

### 4.5. Tạo stream và ghi log không phải cùng một quyền

Một workload có thể cần:

- `logs:CreateLogStream` để tạo stream mới.
- `logs:PutLogEvents` để gửi events.
- `logs:CreateLogGroup` chỉ khi workload được phép tự tạo group.

Nếu group/stream được IaC tạo trước, có thể loại bỏ quyền create tương ứng khỏi runtime role. Điều này giảm quyền của workload khi bị compromise.

## 5. Retention: log được lưu trong bao lâu?

Mỗi log group có retention policy. Nếu không cấu hình retention, CloudWatch Logs giữ events vô thời hạn cho đến khi chúng bị xóa theo thao tác quản trị hoặc group bị xóa. Đây là một nguyên nhân phổ biến khiến chi phí lưu trữ tăng dần theo thời gian.

Retention được đặt ở cấp log group, tính theo ngày. CloudWatch Logs hỗ trợ các khoảng thời gian định sẵn, từ 1 ngày đến nhiều năm; chỉ chọn giá trị hợp lệ mà API/service hỗ trợ.

### 5.1. Chọn retention theo mục đích

| Loại log | Ví dụ retention ban đầu | Lý do |
| --- | ---: | --- |
| Development/debug | 3–14 ngày | Dữ liệu debug thường chỉ cần trong thời gian ngắn |
| Application production | 30–90 ngày | Đủ thời gian điều tra lỗi vận hành thông thường |
| Security/audit | Theo chính sách tổ chức, có thể dài hơn nhiều | Phục vụ điều tra, audit hoặc nghĩa vụ lưu trữ |
| High-volume access logs | 7–30 ngày trong CloudWatch, sau đó archive nếu cần | Kiểm soát chi phí và giữ bản lưu theo nhu cầu |

Các khoảng trên là gợi ý thiết kế, không phải quy định compliance. Thời hạn thực tế phải căn cứ vào yêu cầu pháp lý, hợp đồng, sự kiện cần điều tra và chính sách dữ liệu của tổ chức.

### 5.2. Đặt retention bằng AWS CLI

~~~bash
aws logs put-retention-policy \
  --log-group-name /platform/prod/order-api/application \
  --retention-in-days 30 \
  --region ap-southeast-1
~~~

Xem thông tin log group và retention:

~~~bash
aws logs describe-log-groups \
  --log-group-name-prefix /platform/prod/order-api \
  --region ap-southeast-1
~~~

Trong output, kiểm tra `retentionInDays`. Nếu trường này không xuất hiện, group không có retention policy và events được giữ vô thời hạn.

### 5.3. Đặt retention bằng CloudFormation

~~~yaml
Resources:
  ApplicationLogGroup:
    Type: AWS::Logs::LogGroup
    Properties:
      LogGroupName: /platform/prod/catalog-api/application
      RetentionInDays: 90
~~~

Quản lý retention bằng IaC giúp mọi môi trường có cấu hình được review và version control. Khi thay đổi thời hạn, tạo Change Set và xác nhận policy mới đáp ứng yêu cầu lưu trữ.

### 5.4. Xóa retention policy

~~~bash
aws logs delete-retention-policy \
  --log-group-name /platform/prod/order-api/application \
  --region ap-southeast-1
~~~

Lệnh này **xóa quy tắc hết hạn**, khiến log group trở về trạng thái lưu giữ vô thời hạn. Nó không xóa log events hiện có. Vì vậy, không dùng `delete-retention-policy` như một cách dọn log.

### 5.5. Hết hạn không đồng nghĩa xóa ngay lập tức

Khi event vượt quá retention period, CloudWatch Logs đánh dấu để xóa theo quy trình nền. Việc xóa có thể không xảy ra đúng thời điểm vừa chạm mốc; quá trình xóa thường diễn ra không đồng bộ và có thể mất thêm thời gian.

Không dùng retention expiration làm cơ chế xóa dữ liệu chính xác theo phút hoặc đáp ứng một yêu cầu xóa dữ liệu tức thời. Nếu có yêu cầu xóa theo subject/request, cần thiết kế data lifecycle và storage phù hợp; log không nên chứa dữ liệu cá nhân không cần thiết ngay từ đầu.

### 5.6. Retention của log group không giống lifecycle archive

Retention trong CloudWatch Logs quyết định thời điểm events hết hạn. Nếu cần lưu lâu dài với chi phí khác hoặc phục vụ phân tích tập trung, có thể chuyển log sang S3 hoặc hệ thống lưu trữ khác bằng subscription/delivery pipeline. Khi đó, cần policy lifecycle riêng cho bản archive và phải kiểm tra rằng bản sao không vô tình tồn tại lâu hơn chính sách dữ liệu.

## 6. Encryption và bảo vệ dữ liệu log

CloudWatch Logs mã hóa dữ liệu log lưu trữ bằng encryption mặc định của dịch vụ. Nếu cần kiểm soát key, có thể liên kết log group với AWS KMS customer managed key (CMK) được hỗ trợ.

### 6.1. Khi nào dùng customer managed key?

CMK có thể phù hợp khi:

- Tổ chức cần kiểm soát key policy và vòng đời key.
- Có yêu cầu audit việc sử dụng key.
- Muốn tách quyền quản trị key khỏi quyền quản trị log.
- Có yêu cầu encryption/key ownership theo account hoặc workload.

CMK làm tăng trách nhiệm vận hành: key policy, IAM permissions, rotation, disable/delete protection và chi phí KMS. Nếu key bị disable hoặc policy bị thay đổi sai, quyền truy cập dữ liệu đã mã hóa có thể bị ảnh hưởng.

### 6.2. Gắn KMS key với log group

~~~yaml
Resources:
  ApplicationLogGroup:
    Type: AWS::Logs::LogGroup
    Properties:
      LogGroupName: /platform/prod/payment-api/application
      RetentionInDays: 90
      KmsKeyId: !GetAtt LogsKey.Arn

  LogsKey:
    Type: AWS::KMS::Key
    Properties:
      Description: Key for CloudWatch Logs encryption
      EnableKeyRotation: true
      KeyPolicy:
        Version: "2012-10-17"
        Statement:
          - Sid: EnableAccountAdministration
            Effect: Allow
            Principal:
              AWS: !Sub "arn:${AWS::Partition}:iam::${AWS::AccountId}:root"
            Action: "kms:*"
            Resource: "*"
          - Sid: AllowCloudWatchLogsUse
            Effect: Allow
            Principal:
              Service: !Sub "logs.${AWS::Region}.amazonaws.com"
            Action:
              - kms:Encrypt*
              - kms:Decrypt*
              - kms:ReEncrypt*
              - kms:GenerateDataKey*
              - kms:Describe*
            Resource: "*"
            Condition:
              ArnLike:
                kms:EncryptionContext:aws:logs:arn: !Sub "arn:${AWS::Partition}:logs:${AWS::Region}:${AWS::AccountId}:log-group:/platform/prod/payment-api/*"
~~~

Đây là ví dụ policy minh họa nguyên tắc giới hạn encryption context. Khi triển khai, kiểm tra service principal, key policy và encryption context format đúng theo Region/partition và CloudWatch Logs integration hiện hành. Một số thao tác cần quyền KMS khác nhau; không sao chép policy rộng vào production mà không review.

### 6.3. Quyền KMS và quyền CloudWatch Logs là hai lớp riêng

Một principal đọc log group được mã hóa bằng CMK có thể cần quyền CloudWatch Logs tương ứng và quyền sử dụng KMS key theo cơ chế dịch vụ hỗ trợ. Cấp `logs:FilterLogEvents` không tự động cấp `kms:Decrypt`; ngược lại, có `kms:Decrypt` cũng không tự cấp quyền đọc log group.

Phân tách:

- CloudWatch Logs permissions: thao tác nào được phép trên log group/stream.
- KMS key policy/IAM: principal hoặc service nào được phép dùng key.
- Resource policy: dịch vụ/account khác có được gửi log hoặc gọi hành động được hỗ trợ trên log resource hay không.

### 6.4. Data protection và masking

CloudWatch Logs có khả năng data protection policy để phát hiện và mask một số loại dữ liệu nhạy cảm trong quá trình truy cập log. Đây là lớp bảo vệ bổ sung, không thay thế việc loại bỏ secret/PII ở nguồn.

Nguyên tắc:

- Không log credentials, authorization headers hoặc secret payload.
- Mask PII trước khi ghi.
- Giới hạn người có quyền xem dữ liệu gốc/unmasked nếu tính năng đó được bật.
- Kiểm thử pattern detection bằng dữ liệu giả.
- Xem xét cả bản archive, subscription destination và bản export; masking khi đọc không có nghĩa mọi bản sao đã bị xóa hoặc sửa.
## 7. IAM identity policy: ai được ghi và đọc log?

IAM identity policy gắn với user, group hoặc role và xác định principal được phép gọi CloudWatch Logs API. Cần tách hai nhóm quyền:

- **Writer permissions:** workload/agent tạo stream và gửi log events.
- **Reader/operator permissions:** người hoặc service truy vấn, xem, cấu hình retention, encryption và subscription.

Không cấp một policy quản trị log rộng cho mọi application role. Workload chỉ cần ghi log; developer cần đọc một số group; platform/security team mới cần quản trị hoặc truy vấn trên nhiều group.

### 7.1. Writer policy cho một log group

Ví dụ role của một workload chỉ ghi vào group của order API:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "CreateStreamsForOrderApi",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:ap-southeast-1:111122223333:log-group:/platform/prod/order-api/application:log-stream:*"
    }
  ]
}
~~~

Nếu log group đã được tạo trước, writer không cần quyền `logs:CreateLogGroup`. Nếu workload buộc phải tự tạo group, bổ sung quyền riêng với resource scope phù hợp theo IAM service authorization reference và naming convention; không mặc định thêm `Resource: "*"` cho toàn bộ Logs actions.

Thay account ID, Region và log group name theo môi trường. ARN minh họa không phải ARN dùng chung cho mọi account.

### 7.2. Reader policy chỉ đọc một log group

Một developer chỉ cần xem và truy vấn log của order API có thể được cấp một policy hẹp:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadOrderApiLogs",
      "Effect": "Allow",
      "Action": [
        "logs:DescribeLogStreams",
        "logs:GetLogEvents",
        "logs:FilterLogEvents",
        "logs:StartQuery",
        "logs:StopQuery",
        "logs:GetQueryResults"
      ],
      "Resource": "arn:aws:logs:ap-southeast-1:111122223333:log-group:/platform/prod/order-api/application:*"
    }
  ]
}
~~~

Một số thao tác liệt kê/describe cần `Resource: "*"` theo bảng hỗ trợ resource-level permissions của từng action. Nếu console cần liệt kê group, có thể phải cấp `logs:DescribeLogGroups` ở statement riêng với resource wildcard. Chỉ bổ sung các action thật sự cần và kiểm tra policy bằng IAM Access Analyzer/policy simulator.

### 7.3. Reader policy và Logs Insights

Để chạy Logs Insights query, người dùng thường cần quyền:

- `logs:StartQuery` để bắt đầu query.
- `logs:GetQueryResults` để lấy kết quả.
- `logs:StopQuery` để dừng query.
- `logs:DescribeLogGroups`/`logs:DescribeLogStreams` nếu giao diện cần liệt kê group/stream.

Quyền query có thể làm lộ nhiều dữ liệu hơn việc chỉ xem một stream. Giới hạn log group được phép truy vấn và dùng field-level/data protection controls khi phù hợp.

### 7.4. Quyền quản trị log group

Các thao tác quản trị có thể bao gồm:

| Nhu cầu | IAM actions thường liên quan |
| --- | --- |
| Tạo/xóa group | `logs:CreateLogGroup`, `logs:DeleteLogGroup` |
| Tạo stream | `logs:CreateLogStream`, `logs:DeleteLogStream` |
| Đặt/xóa retention | `logs:PutRetentionPolicy`, `logs:DeleteRetentionPolicy` |
| Gắn/tháo KMS key | `logs:AssociateKmsKey`, `logs:DisassociateKmsKey` |
| Cấu hình subscription | `logs:PutSubscriptionFilter`, `logs:DeleteSubscriptionFilter`, `logs:DescribeSubscriptionFilters` |
| Cấu hình data protection | `logs:PutDataProtectionPolicy`, `logs:DeleteDataProtectionPolicy` |
| Cấu hình resource policy | `logs:PutResourcePolicy`, `logs:DeleteResourcePolicy`, `logs:DescribeResourcePolicies` |

Tên action và resource-level support có thể khác nhau theo thao tác; tham khảo Service Authorization Reference trước khi viết policy. Không gộp mọi quyền này vào execution role của ứng dụng.

### 7.5. Quyền ghi và quyền đọc nên thuộc các role khác nhau

~~~mermaid
flowchart LR
    APP["Application role"] -->|CreateLogStream / PutLogEvents| LOGS["CloudWatch Logs"]
    DEV["Developer read role"] -->|Filter / Get / Query| LOGS
    OPS["Platform admin role"] -->|Retention / KMS / Subscription| LOGS
    SEC["Security audit role"] -->|Read audit groups| LOGS
~~~

Application role không cần đọc lại log sau khi ghi. Developer không cần quyền thay retention. Security audit role không cần quyền deploy hoặc xóa log group. Tách role giúp giới hạn tác động nếu credentials bị lộ.

## 8. Resource policy và quyền gửi log từ dịch vụ khác

CloudWatch Logs có resource-based policies. Resource policy được cấu hình bằng `logs:PutResourcePolicy` và có thể cho phép AWS service principal hoặc principal được chỉ định thực hiện hành động được hỗ trợ trên log resources.

Resource policy thường xuất hiện trong hai tình huống:

1. Một AWS service cần gửi log vào log group của account.
2. Một destination cần cho phép CloudWatch Logs từ account nguồn gửi subscription data đến.

Resource policy và IAM identity policy giải quyết hai phía khác nhau. Identity policy nói principal được phép làm gì; resource policy nói resource chấp nhận principal nào.

### 8.1. Resource policy không thay thế IAM role của reader

Không dùng resource policy nhận log như một cách cấp quyền cho developer đọc log. Để người dùng đọc log, cần IAM identity policy phù hợp trên principal của họ, cộng thêm quyền KMS nếu group dùng CMK.

### 8.2. Ví dụ resource policy cho service principal

Một service AWS có thể cần quyền gửi log vào group theo integration được hỗ trợ. Policy minh họa:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowServiceToWriteLogs",
      "Effect": "Allow",
      "Principal": {
        "Service": "delivery.logs.amazonaws.com"
      },
      "Action": [
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:ap-southeast-1:111122223333:log-group:/platform/prod/network-flow-logs:*"
    }
  ]
}
~~~

Đây là hình thức minh họa, không phải policy copy/paste cho mọi service. Service principal, điều kiện `aws:SourceAccount`/`aws:SourceArn`, resource ARN và action phải theo tài liệu tích hợp cụ thể. Một số dịch vụ dùng service-linked role hoặc cơ chế delivery riêng.

### 8.3. Cấu hình resource policy bằng CLI

~~~bash
aws logs put-resource-policy \
  --policy-name AllowApprovedLogDelivery \
  --policy-document file://logs-resource-policy.json \
  --region ap-southeast-1
~~~

Xem các resource policies:

~~~bash
aws logs describe-resource-policies \
  --region ap-southeast-1
~~~

Resource policies có giới hạn số lượng/kích thước và phạm vi áp dụng. Với policy theo account, cần tránh tạo nhiều policy trùng lặp hoặc cấp quyền cho service principal rộng hơn nhu cầu.

### 8.4. Phân biệt resource policy của CloudWatch Logs và destination policy

Trong subscription flow, log group nguồn có subscription filter trỏ tới destination. Destination ở account nhận có policy cho phép account nguồn tạo subscription/gửi dữ liệu theo cơ chế CloudWatch Logs hỗ trợ. Cần kiểm tra cả hai đầu:

- Source log group: quyền `logs:PutSubscriptionFilter` và cấu hình filter.
- Destination: destination access policy, role/service permissions và target resource policy.
- Target service: Lambda, Kinesis Data Streams, Amazon Data Firehose hoặc destination được hỗ trợ.

Nếu chỉ cấu hình source subscription mà quên destination policy, việc tạo subscription hoặc delivery có thể thất bại.

## 9. Cross-account logging và quyền truy cập tập trung

Ở quy mô nhiều AWS accounts, mỗi workload account có thể ghi log vào log groups riêng; security/operations account cần tập trung quan sát hoặc lưu trữ. Có nhiều mô hình, cần chọn theo mục tiêu:

- **Cross-account observability:** dùng CloudWatch cross-account observability/Observability Access Manager (OAM) để chia sẻ telemetry theo cấu hình link/sink được hỗ trợ.
- **Subscription-based centralization:** dùng subscription filters chuyển log events tới destination tập trung như Kinesis Data Streams, Data Firehose hoặc Lambda.
- **Archive:** chuyển log sang S3 để lưu trữ, lifecycle hoặc phân tích ngoài CloudWatch.

Các mô hình trên có semantics, phí và quyền khác nhau. OAM không đồng nghĩa copy mọi log event sang account trung tâm; subscription pipeline mới là cơ chế chuyển log events theo filter tới destination.

### 9.1. Mô hình subscription

~~~mermaid
flowchart TD
    A["Workload account A"] --> G1["Application log group"]
    B["Workload account B"] --> G2["Application log group"]
    G1 --> F1["Subscription filter"]
    G2 --> F2["Subscription filter"]
    F1 --> D["Central destination"]
    F2 --> D
    D --> S["Security / analytics account"]
    S --> K["Kinesis / Firehose / Lambda"]
    K --> ARCH["S3 archive or analytics"]
~~~

### 9.2. Subscription filter

Subscription filter chọn events theo filter pattern và chuyển các events khớp tới destination. Filter pattern có thể lọc severity hoặc nội dung JSON, ví dụ:

~~~text
{ $.level = "ERROR" }
~~~

Chỉ gửi những events cần downstream xử lý có thể giảm tải và chi phí, nhưng filter quá hẹp có thể bỏ sót bằng chứng quan trọng. Với security/audit streams, review filter pattern kỹ và có kiểm thử bằng sample logs.

### 9.3. Ví dụ subscription filter tới Lambda

~~~yaml
Resources:
  ErrorLogSubscription:
    Type: AWS::Logs::SubscriptionFilter
    Properties:
      LogGroupName: /platform/prod/order-api/application
      FilterPattern: '{ $.level = "ERROR" }'
      DestinationArn: !GetAtt LogForwarderFunction.Arn
~~~

Ví dụ cần Lambda destination policy cho phép CloudWatch Logs service invoke function, thường được khai báo bằng `AWS::Lambda::Permission` với `Principal` phù hợp và `SourceArn` giới hạn log group. Function xử lý payload dạng CloudWatch Logs subscription (base64/gzip envelope); không giả định mỗi invocation chỉ chứa một event.

### 9.4. Subscription destination tới Kinesis/Firehose

Khi dùng Kinesis Data Streams hoặc Data Firehose, cần role mà CloudWatch Logs assume được để ghi vào destination. Role trust policy phải cho phép service principal đúng; permission policy giới hạn vào stream/delivery stream ARN cần thiết. Destination policy và account trust phải khớp mô hình same-account/cross-account.

### 9.5. Một số giới hạn cần nhớ

- Mỗi log group có giới hạn số subscription filters; kiểm tra quota hiện hành.
- Một số AWS service log groups có thể có ràng buộc về subscription filters.
- Filter pattern cần test bằng events thực tế đã mask.
- Delivery có thể retry hoặc bị giới hạn bởi destination; xây dựng DLQ/reprocessing theo khả năng target service.
- Không gửi cùng một log tới nhiều pipeline nếu không có mục đích, vì ingestion/delivery/storage có thể phát sinh chi phí lặp.

## 10. Đọc và truy vấn log

Quyền truy cập log nên được thiết kế theo tác vụ. Xem một stream, lọc events, chạy Logs Insights query, tạo subscription và xóa log group là những thao tác khác nhau.

### 10.1. Xem stream bằng AWS CLI

Liệt kê streams:

~~~bash
aws logs describe-log-streams \
  --log-group-name /platform/prod/order-api/application \
  --order-by LastEventTime \
  --descending \
  --limit 20 \
  --region ap-southeast-1
~~~

Đọc events từ một stream:

~~~bash
aws logs get-log-events \
  --log-group-name /platform/prod/order-api/application \
  --log-stream-name order-api-instance-a \
  --start-from-head \
  --limit 100 \
  --region ap-southeast-1
~~~

`GetLogEvents` có thể trả về token để tiếp tục đọc trang tiếp theo. Client cần xử lý pagination và dừng khi không còn dữ liệu mới; không giả định một response chứa toàn bộ stream.

### 10.2. Lọc events trong một group

~~~bash
aws logs filter-log-events \
  --log-group-name /platform/prod/order-api/application \
  --filter-pattern '"PAYMENT_PROVIDER_TIMEOUT"' \
  --start-time 1795140000000 \
  --region ap-southeast-1
~~~

Filter pattern tìm message phù hợp trong khoảng thời gian. Kết quả có thể được phân trang; quyền `logs:FilterLogEvents` cần giới hạn vào các log groups được phép.

### 10.3. Logs Insights query

Ví dụ đếm lỗi theo service và level:

~~~sql
fields @timestamp, service, level, requestId, message
| filter level = "ERROR"
| stats count(*) as errorCount by service
| sort errorCount desc
~~~

Ví dụ tìm request có lỗi timeout:

~~~sql
fields @timestamp, requestId, errorCode, message
| filter errorCode = "PAYMENT_PROVIDER_TIMEOUT"
| sort @timestamp desc
| limit 50
~~~

Logs Insights có thể tự phát hiện một số trường JSON. Nếu ứng dụng dùng format không chuẩn, cần parse trường bằng query hoặc chuẩn hóa log format ở nguồn.

### 10.4. Query theo thời gian và chi phí

- Chọn time range ngắn nhất đủ để trả lời câu hỏi.
- Chỉ chọn các log groups cần thiết.
- Dùng filter sớm để giảm lượng dữ liệu xử lý.
- Tránh query lặp liên tục trên toàn bộ retention window.
- Cân nhắc field indexes cho workload truy vấn phù hợp và được hỗ trợ.
- Lưu query hữu ích thành query definition để team dùng lại.

Logs Insights tính phí theo dữ liệu được scan; query không giới hạn thời gian có thể tốn kém trên group có lượng log lớn.

## 11. Quyền truy cập theo lớp và phạm vi resource

IAM policy cần khớp action, resource ARN và principal. Chỉ dựa vào tên action là chưa đủ; một số API là list/describe và cần wildcard resource, trong khi API đọc/ghi event có thể giới hạn theo log group hoặc stream ARN.

### 11.1. ARN của log group và stream

Ví dụ ARN log group:

~~~text
arn:aws:logs:ap-southeast-1:111122223333:log-group:/platform/prod/order-api/application
~~~

ARN log stream có thêm phần định danh stream:

~~~text
arn:aws:logs:ap-southeast-1:111122223333:log-group:/platform/prod/order-api/application:log-stream:order-api-instance-a
~~~

Khi policy cần bao phủ mọi stream trong group, có thể dùng wildcard ở phần stream theo cú pháp resource ARN được IAM hỗ trợ. Tránh dùng wildcard account/Region/group nếu chỉ cần một service cụ thể.

### 11.2. Tách statement theo action scope

Ví dụ policy có thể cần statement riêng:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ListLogGroups",
      "Effect": "Allow",
      "Action": [
        "logs:DescribeLogGroups"
      ],
      "Resource": "*"
    },
    {
      "Sid": "ReadOnlyOrderApi",
      "Effect": "Allow",
      "Action": [
        "logs:DescribeLogStreams",
        "logs:FilterLogEvents",
        "logs:GetLogEvents"
      ],
      "Resource": [
        "arn:aws:logs:ap-southeast-1:111122223333:log-group:/platform/prod/order-api/application",
        "arn:aws:logs:ap-southeast-1:111122223333:log-group:/platform/prod/order-api/application:log-stream:*"
      ]
    }
  ]
}
~~~

Đây là policy minh họa về cách tách quyền liệt kê và quyền đọc; resource ARN chính xác phải theo action/resource types trong Service Authorization Reference. Một số action có yêu cầu resource ARN khác hoặc không hỗ trợ resource-level scoping. Dùng IAM policy simulator và thử bằng role thật trong sandbox.

### 11.3. Permission boundary, SCP và explicit deny

Một Allow trong identity policy chưa chắc đủ để gọi API. Quyền hiệu lực còn chịu ảnh hưởng của:

- Permission boundary của role/user.
- Service control policy (SCP) ở AWS Organizations.
- Session policy của assumed role.
- Resource policy và KMS key policy.
- Explicit Deny trong bất kỳ policy áp dụng nào.

Khi nhận `AccessDenied`, kiểm tra principal thực tế bằng STS `GetCallerIdentity`, sau đó xem các policy layers. Không giải quyết bằng cách gắn `AdministratorAccess` nếu chưa xác định thiếu quyền nào.

## 12. Cross-account access: đọc log và gửi log

Cross-account logging có hai hướng khác nhau:

1. Principal ở account khác **đọc** log group hiện có.
2. Service/workload ở account khác **gửi** log events vào destination tập trung.

Hai hướng này có thể cần cơ chế khác nhau. Với reader, thường dùng assume-role vào account sở hữu log group hoặc CloudWatch cross-account observability theo mô hình OAM. Với delivery, dùng subscription destination/resource policy hoặc service integration được hỗ trợ.

### 12.1. Assume role để đọc log

Một security analyst ở account A có thể assume role `CentralLogReadRole` ở account B. Trust policy của role B cho phép principal/role cụ thể ở account A assume role; identity policy gắn role B cấp quyền đọc các log groups cần thiết.

~~~mermaid
sequenceDiagram
    participant Analyst as Analyst role (Account A)
    participant STS
    participant Role as CentralLogReadRole (Account B)
    participant Logs as CloudWatch Logs (Account B)
    Analyst->>STS: AssumeRole
    STS-->>Analyst: Temporary credentials
    Analyst->>Logs: FilterLogEvents / StartQuery
    Logs-->>Analyst: Log events / query results
~~~

Không đặt access key của account B trong account A. Dùng temporary credentials, trust policy giới hạn principal và session duration phù hợp.

### 12.2. CloudWatch cross-account observability

CloudWatch cross-account observability sử dụng Observability Access Manager (OAM) với sink ở monitoring account và link từ source accounts. Tổ chức có thể chia sẻ telemetry như metrics, logs và traces theo loại dữ liệu/nguồn được OAM hỗ trợ.

OAM chia sẻ khả năng quan sát theo cấu hình, không thay thế IAM authorization của người xem và không mặc nhiên sao chép dữ liệu log sang account nhận. Kiểm tra danh sách telemetry types, Region support, account relationships và OAM policies trước khi triển khai.

### 12.3. Centralized subscription destination

Với subscription cross-account, destination account cần tạo destination và access policy cho phép account nguồn sử dụng. Account nguồn cấu hình subscription filter tới destination ARN. Role dùng cho destination phải có trust và permission phù hợp với target service.

Khi điều tra lỗi, xác minh:

- Destination ARN đúng account/Region.
- Destination policy cho phép đúng source account.
- Source role có quyền tạo subscription filter.
- Target stream/Firehose/Lambda có quyền nhận dữ liệu.
- KMS key policy và encryption của destination cho phép delivery.

### 12.4. Không nhầm cross-account observability với log archive

Nếu yêu cầu là bản sao log độc lập để lưu trữ tập trung, hãy thiết kế subscription/export delivery tới S3 hoặc data pipeline phù hợp. Nếu yêu cầu là xem log/metrics/traces tại monitoring account mà không cần copy toàn bộ log, xem xét OAM. Chọn theo retention, access model, audit, latency và cost.

## 13. Lifecycle, deletion và log group class

Log group có lifecycle riêng với workload. Xóa application stack không nên vô tình xóa audit log hoặc log cần giữ lại.

### 13.1. Xóa log group

`DeleteLogGroup` xóa group và các log streams/events thuộc group đó. Đây là thao tác destructive; IAM quyền xóa nên tách khỏi quyền đọc và ghi.

Nếu cần giữ logs sau khi xóa ứng dụng:

- Tách log group khỏi application stack hoặc dùng retention/retention strategy rõ ràng.
- Archive sang S3 theo policy và xác minh bản archive đầy đủ.
- Dùng DeletionPolicy phù hợp nếu group được quản lý bằng CloudFormation và cần giữ lại sau stack deletion.
- Gán owner và quy trình xóa cuối vòng đời cho retained group.

Ví dụ CloudFormation:

~~~yaml
Resources:
  AuditLogGroup:
    Type: AWS::Logs::LogGroup
    DeletionPolicy: Retain
    UpdateReplacePolicy: Retain
    Properties:
      LogGroupName: /platform/prod/order-api/audit
      RetentionInDays: 365
~~~

`Retain` có nghĩa resource được giữ lại khi stack bị xóa hoặc resource bị replacement theo policy tương ứng. Nó không bảo đảm log được giữ vô thời hạn nếu retention vẫn được cấu hình 365 ngày; retention và DeletionPolicy là hai cơ chế độc lập.

### 13.2. Log group class

CloudWatch Logs có các log group classes với feature set và chi phí khác nhau, gồm Standard và Infrequent Access; một số delivery use cases có class riêng theo dịch vụ hỗ trợ. Chọn class theo cách log được truy vấn, filter và chuyển tiếp.

- Standard phù hợp khi cần bộ tính năng CloudWatch Logs đầy đủ, bao gồm các tính năng vận hành phổ biến.
- Infrequent Access phù hợp với log ít truy cập và ưu tiên chi phí; cần kiểm tra feature limitations như subscription/metric filters trước khi chọn.
- Class được chọn khi tạo group và không nên giả định có thể đổi class trực tiếp sau đó. Khi cần đổi, phải có kế hoạch tạo group mới và chuyển nguồn ghi/consumer.

Đừng chọn class chỉ dựa trên giá ingestion. So sánh cả query, filtering, data protection, Live Tail, subscriptions và nhu cầu vận hành.

### 13.3. Di chuyển sang log group mới

1. Tạo group mới với class, KMS key và retention đúng.
2. Cấp quyền writer vào group mới.
3. Cập nhật Lambda/agent/log driver/service destination.
4. Chạy song song hoặc chuyển theo rollout để tránh mất log.
5. Kiểm tra event timestamps, stream creation và query results.
6. Cập nhật reader roles, dashboards, alarms và subscription filters.
7. Giữ group cũ theo retention/archive policy rồi mới xóa khi không còn consumer.

## 14. Chi phí và quản trị log volume

Chi phí CloudWatch Logs có thể đến từ ingestion, storage, Logs Insights queries, data delivery/exports và những tính năng liên quan. Mức giá khác nhau theo Region, class và tính năng; xem bảng giá AWS hiện hành trước khi lập budget.

### 14.1. Những yếu tố làm log tăng nhanh

- Debug logs quá chi tiết ở production.
- Ghi cả request/response body lớn.
- Log cùng một exception nhiều lần ở nhiều layer.
- Retry loop phát sinh hàng nghìn events.
- Tạo log group theo user/request.
- Giữ log vô thời hạn.
- Query toàn bộ log history thường xuyên.
- Gửi cùng events đến nhiều destination mà không có nhu cầu rõ.

### 14.2. Giảm log volume ở nguồn

- Dùng log levels và giảm DEBUG/TRACE ở production.
- Ghi một exception tại layer chịu trách nhiệm xử lý, tránh duplicate stack traces.
- Ghi structured fields thay vì lặp payload lớn.
- Dùng sampling cho high-volume diagnostic events khi nghiệp vụ cho phép.
- Không ghi secret/PII hoặc payload không cần thiết.
- Thêm request/trace IDs để một log event giàu thông tin hơn.

### 14.3. Budget và cost allocation

Gắn tags cho log groups theo `Service`, `Environment`, `Owner`, `CostCenter`. Dùng AWS Budgets/Cost Explorer và CloudWatch usage metrics hoặc billing data để theo dõi xu hướng. Cảnh báo khi ingestion/storage/query tăng bất thường.

Không dựa vào retention đơn lẻ để giải quyết cost spike. Tìm nguồn phát log và giảm volume trước, sau đó điều chỉnh retention/archive/class theo chính sách.

## 15. Troubleshooting lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| **Không thấy log group** | Sai Region/account, group chưa được tạo hoặc tên sai | Kiểm tra caller identity, Region, tên group và service logging configuration |
| **Lambda chạy nhưng không có log** | Execution role thiếu quyền Logs hoặc function chưa ghi stdout/stderr | Kiểm tra role, `CreateLogStream`, `PutLogEvents`, function execution và log group |
| **AccessDenied khi PutLogEvents** | Resource ARN không khớp group/stream hoặc thiếu action | Kiểm tra stream ARN, role thực tế, boundary/SCP và explicit Deny |
| **AccessDenied khi CreateLogGroup** | Runtime role không có quyền tạo group | Provision group bằng IaC hoặc cấp quyền create có scope phù hợp |
| **Không tạo được stream** | Sai group, stream đã tồn tại hoặc thiếu `CreateLogStream` | Kiểm tra group name, stream name và quyền writer |
| **Reader thấy group nhưng không đọc được events** | Thiếu `GetLogEvents`/`FilterLogEvents` hoặc resource scope sai | Kiểm tra action và ARN stream/group theo API đang gọi |
| **Logs Insights không chạy** | Thiếu `StartQuery`/`GetQueryResults`, chọn sai group/time range hoặc query syntax sai | Kiểm tra policy, log fields, time range và query |
| **Log không hết hạn** | Retention chưa được đặt hoặc cấu hình nhầm group | Kiểm tra `retentionInDays` trên đúng group và Region |
| **Log vẫn còn sau retention deadline** | Expiration/deletion xử lý không đồng bộ | Chờ quy trình nền; không coi retention là xóa tức thời |
| **KMS AccessDenied** | Key policy/IAM thiếu quyền hoặc encryption context không khớp | Kiểm tra KMS key state, policy, Region và encryption context |
| **Subscription filter không tạo được** | Thiếu quyền source, destination policy hoặc target permission | Kiểm tra source group, destination access policy, role trust và target service |
| **Subscription có nhưng destination thiếu events** | Filter pattern không khớp, delivery bị throttled hoặc target lỗi | Test pattern, xem delivery errors/metrics và target logs |
| **Cross-account log không truy cập được** | Trust relationship/OAM link/destination policy sai | Kiểm tra account IDs, Region, role trust, sink/link và resource policies |
| **Log group không xóa được** | Thiếu `DeleteLogGroup`, stack ownership hoặc resource protection | Kiểm tra IAM, CloudFormation stack và deletion policy |
| **Chi phí log tăng bất thường** | Log level quá chi tiết, retry storm, retention dài hoặc query scan rộng | Xác định source, giảm volume, review retention/query và subscription |

### 15.1. Quy trình điều tra AccessDenied

1. Xác định API thất bại: `CreateLogGroup`, `CreateLogStream`, `PutLogEvents`, `FilterLogEvents` hay `StartQuery`.
2. Xác định principal thật sự bằng STS `GetCallerIdentity`.
3. Xác nhận Region, account ID, log group name và ARN stream.
4. Kiểm tra identity policy và resource-level scope cho đúng action.
5. Kiểm tra permission boundary, SCP, session policy và explicit Deny.
6. Nếu có CMK, kiểm tra KMS key policy, key state và encryption context.
7. Nếu là service delivery/subscription, kiểm tra service principal, resource/destination policy và target permissions.

Không mở rộng policy thành `logs:*` hoặc `Resource: "*"` chỉ để làm lỗi biến mất. Sửa đúng statement thiếu và xác nhận bằng một request thử trong sandbox.

### 15.2. Không thấy log dù request thành công

Kiểm tra theo thứ tự:

- Ứng dụng có ghi log ở mức level đang bật không?
- Logger có ghi stdout/stderr hoặc file path mà agent đang theo dõi không?
- Agent/log driver có đang chạy và có network path tới CloudWatch Logs endpoint không?
- Workload role có quyền gửi events không?
- Group/stream có đúng Region/account không?
- Event timestamp có nằm ngoài time range đang xem không?
- Subscription filter có đang loại event khỏi destination không?

Log event vẫn có thể tồn tại trong source group nhưng không xuất hiện ở destination nếu filter pattern không khớp.

## 16. Bài tập củng cố

### Bài 1 — Phân biệt group và stream

Một ECS service chạy 12 tasks trong cùng môi trường production. Nên tạo một log group hay 12 log groups?

**Gợi ý:** thường dùng một group theo service/environment và các streams theo task/container theo log driver; tách group khi policy/retention/access khác nhau.

### Bài 2 — Retention mặc định

Một log group không có `RetentionInDays`. Events sẽ được giữ bao lâu?

**Gợi ý:** vô thời hạn cho đến khi có thao tác xóa hoặc group bị xóa.

### Bài 3 — Writer least privilege

Lambda log group được CloudFormation tạo sẵn. Execution role cần quyền nào để tạo stream và gửi log?

**Gợi ý:** `logs:CreateLogStream` và `logs:PutLogEvents` trên group/stream ARN phù hợp; không cần `CreateLogGroup` nếu group đã tồn tại.

### Bài 4 — Reader policy

Developer cần chạy Logs Insights trên group của order API. Những quyền chính nào cần được kiểm tra?

**Gợi ý:** `StartQuery`, `GetQueryResults`, `StopQuery`, quyền liệt kê cần cho console và quyền truy cập group theo scope.

### Bài 5 — KMS

Principal có `logs:FilterLogEvents` nhưng không đọc được group mã hóa bằng CMK. Cần kiểm tra lớp quyền nào nữa?

**Gợi ý:** KMS key policy/IAM, trạng thái key, service integration và encryption context.

### Bài 6 — Resource policy

Một AWS service không thể gửi log vào group. Vì sao thêm IAM policy cho developer không giải quyết được?

**Gợi ý:** cần cấu hình resource policy hoặc service delivery role đúng cho service principal và integration cụ thể.

### Bài 7 — Export log cross-account

Một team muốn tập trung log events từ nhiều accounts vào Kinesis ở security account. Cần thiết kế những thành phần nào?

**Gợi ý:** source subscription filters, destination, destination access policy, role trust/permissions và Kinesis target policy.

### Bài 8 — OAM hay subscription?

Operations team muốn xem telemetry liên account; security team muốn bản sao log độc lập trong S3. Có thể dùng cùng một cơ chế cho cả hai không?

**Gợi ý:** OAM phục vụ cross-account observability; subscription/delivery pipeline phù hợp để chuyển log events sang archive.

### Bài 9 — Hết hạn log

Log group đặt retention 30 ngày nhưng một số events cũ vẫn còn sau mốc. Điều đó có nhất thiết là cấu hình sai không?

**Gợi ý:** không. Expiration/deletion diễn ra không đồng bộ; kiểm tra retention đúng group và cho phép quy trình nền hoàn tất.

### Bài 10 — Cost spike

CloudWatch Logs ingestion tăng gấp năm lần sau khi deploy. Hãy nêu các nguồn có thể gây ra thay đổi.

**Gợi ý:** DEBUG bật ở production, retry storm, exception duplicate, payload quá lớn, log group mới hoặc duplicate subscription.

## 17. Checklist triển khai production

- [ ] Naming convention thể hiện environment, service, purpose và owner.
- [ ] Group boundary phản ánh retention, access, encryption và lifecycle.
- [ ] Streams tách theo nguồn phát; không tạo group/stream theo từng request hoặc user.
- [ ] Log format có timestamp, severity, service, request/trace ID và error code phù hợp.
- [ ] Không ghi credentials, authorization headers, secret hoặc PII không cần thiết.
- [ ] Log groups được provision bằng IaC khi cần retention/encryption/tags ổn định.
- [ ] Runtime writer role chỉ có `CreateLogStream`/`PutLogEvents` cần thiết.
- [ ] Không cấp `CreateLogGroup` nếu group đã được tạo trước và workload không cần tự tạo.
- [ ] Reader roles chỉ đọc các groups phục vụ nhiệm vụ.
- [ ] Query permissions, admin permissions và delete permissions được tách.
- [ ] Resource policies giới hạn service principal/account và source ARN/account khi integration hỗ trợ.
- [ ] KMS CMK có key policy, encryption context, rotation và recovery plan được review.
- [ ] Retention được đặt theo loại log và policy dữ liệu; không để group production lưu vô thời hạn ngoài chủ đích.
- [ ] Retention expiration được hiểu là asynchronous; không dùng thay cho cơ chế xóa tức thời.
- [ ] Audit/security logs có owner, retention, integrity và archive strategy riêng.
- [ ] Subscription destination có source filter, destination policy, role trust và target permissions.
- [ ] Cross-account observability được phân biệt với delivery/copy/archive log events.
- [ ] CloudWatch Logs Insights query giới hạn time range và log groups cần thiết.
- [ ] Log group class được chọn theo feature requirements và cost trước khi tạo.
- [ ] CloudFormation deletion/retention policy không làm mất audit log ngoài ý muốn.
- [ ] Có CloudWatch/Billing usage monitoring và alert cho ingestion/storage/query bất thường.
- [ ] Có runbook xử lý AccessDenied, KMS, missing events, retention và subscription failures.

## 18. Ghi nhớ

1. **Log event** chứa timestamp/message; **log stream** gom events từ một nguồn; **log group** gom streams và là đơn vị cấu hình retention, encryption, tags và nhiều policy.
2. Log group không có retention policy sẽ giữ events vô thời hạn. Đặt retention theo mục đích và nhớ expiration diễn ra không đồng bộ.
3. Workload chỉ cần ghi log nên có quyền writer hẹp; người đọc, người query và người quản trị cần role riêng.
4. IAM identity policy, CloudWatch Logs resource policy và KMS key policy bảo vệ các lớp khác nhau. Một policy không tự thay thế hai policy còn lại.
5. Cross-account observability qua OAM khác với subscription pipeline chuyển log events sang destination.
6. `DeletionPolicy: Retain` giữ log group khi stack deletion nhưng không vô hiệu hóa retention period của group.
7. Chọn log group class dựa trên feature set và chi phí; không giả định class có thể đổi trực tiếp sau khi tạo.
8. Giảm chi phí từ nguồn phát log, retention, query scope và delivery duplication; không chỉ tăng hoặc giảm thời hạn lưu giữ.

Một hệ thống logging tốt giúp team điều tra sự cố nhanh, bảo vệ dữ liệu và kiểm soát chi phí. Hãy thiết kế quyền và retention ngay từ lúc tạo log group, thay vì đợi đến khi log đã tích lũy hoặc sự cố bảo mật xảy ra.

### Tài liệu chính thức

- [Amazon CloudWatch Logs User Guide](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/WhatIsCloudWatchLogs.html) — khái niệm log groups, streams và events.
- [CreateLogGroup API](https://docs.aws.amazon.com/AmazonCloudWatchLogs/latest/APIReference/API_CreateLogGroup.html) — tạo log group.
- [PutRetentionPolicy API](https://docs.aws.amazon.com/AmazonCloudWatchLogs/latest/APIReference/API_PutRetentionPolicy.html) — đặt retention.
- [CloudWatch Logs retention](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/Working-with-log-groups-and-streams.html) — quản lý group, stream và retention.
- [CloudWatch Logs IAM permissions](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/permissions-reference-cwl.html) — quyền IAM cho CloudWatch Logs.
- [CloudWatch Logs resource policies](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/Subscriptions.html) — subscription và resource policy liên quan.
- [Encrypt log data using AWS KMS](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/encrypt-log-data-kms.html) — mã hóa log group bằng KMS.
- [CloudWatch Logs Insights query syntax](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/CWL_QuerySyntax.html) — cú pháp truy vấn.
- [Subscription filters](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/Subscriptions.html) — chuyển log events tới destination.
- [Cross-account observability](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Unified-Cross-Account.html) — chia sẻ telemetry giữa accounts.
- [CloudWatch Logs pricing](https://aws.amazon.com/cloudwatch/pricing/) — giá ingestion, storage và query theo Region.
- [CloudWatch Logs log classes](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/CloudWatch_Logs_Log_Classes.html) — Standard và Infrequent Access.

