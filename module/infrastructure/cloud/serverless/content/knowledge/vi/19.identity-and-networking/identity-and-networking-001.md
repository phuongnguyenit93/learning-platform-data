# Thiết kế quyền tối thiểu cho từng function

Trong một hệ thống serverless, mỗi function thường chỉ thực hiện một phần nhỏ của quy trình: nhận HTTP request, xử lý message, ghi dữ liệu, gửi notification hoặc điều phối một bước workflow. Nếu mọi function dùng chung một execution role có quyền đọc mọi bucket, ghi mọi bảng và gọi mọi dịch vụ, một lỗi trong một function có thể mở rộng thành sự cố bảo mật của cả hệ thống.

**Quyền tối thiểu (least privilege)** là cấp cho mỗi workload identity đúng những hành động cần thiết trên đúng tài nguyên, trong đúng phạm vi và khoảng thời gian cần thiết. Để áp dụng nguyên tắc này, cần phân biệt danh tính của người gọi, danh tính runtime của function, quyền invoke function và quyền function truy cập dịch vụ phía sau. Mạng riêng, firewall và endpoint policy bổ sung lớp bảo vệ, nhưng không thay thế kiểm soát danh tính và quyền.

Bài học này tập trung thiết kế quyền cho từng Java function trong hệ thống serverless, với ví dụ AWS Lambda/IAM và Google Cloud service account. Bạn sẽ học cách phân tách execution role, giới hạn resource ARN, cấu hình quyền cho trigger, gọi dịch vụ bằng credential tạm thời, kiểm soát mạng và kiểm thử cả đường truy cập được phép lẫn bị từ chối.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt end-user identity, caller identity, function execution identity và resource identity.
- Giải thích vì sao mỗi function hoặc workload nên có workload identity riêng.
- Thiết kế AWS Lambda execution role với trust policy và permission policy tối thiểu.
- Phân biệt identity-based policy, resource-based policy và quyền của event source mapping.
- Giới hạn action, resource, condition và quyền KMS theo đúng nhu cầu.
- Cấu hình service account riêng cho Cloud Run và phân biệt quyền invoke với quyền runtime.
- Dùng AWS SDK for Java 2.x hoặc Google Application Default Credentials mà không lưu access key trong code.
- Kết hợp IAM với VPC, security group, private endpoint và ingress controls.
- Tách quyền runtime khỏi quyền deploy, audit quyền và kiểm thử negative cases.

## 1. Bốn loại danh tính cần phân biệt

Một request serverless có thể liên quan đến nhiều principal. Nếu không xác định đúng principal ở từng bước, đội phát triển dễ cấp quyền sai chỗ.

| Danh tính | Đại diện cho ai hoặc điều gì? | Ví dụ |
|---|---|---|
| End-user identity | Người dùng cuối đang thao tác | User đăng nhập bằng Cognito hoặc Identity Platform |
| Caller identity | Principal gọi endpoint hoặc invoke function | API Gateway, EventBridge, IAM role của service khác |
| Workload/runtime identity | Function hoặc container dùng khi gọi dịch vụ khác | Lambda execution role, Cloud Run service account |
| Resource policy/target | Tài nguyên nhận request và policy xác định principal nào được phép | S3 bucket policy, Lambda resource policy, Cloud Run IAM policy |

Một luồng request có thể như sau:

~~~mermaid
flowchart TD
    U["End user / upstream service"] --> A["API Gateway / Event trigger"]
    A -->|"Invoke permission"| F["Java Lambda function"]
    F -->|"Assume execution role"| R["Function runtime identity"]
    R --> D["Database / Queue / Object storage / Secret"]
    F --> Z["Application authorization"]
    U -. "JWT claims / principal context" .-> Z
~~~

- Người dùng được xác thực ở API Gateway hoặc lớp xác thực ứng dụng.
- API Gateway hoặc event service cần quyền gọi function theo cơ chế tích hợp.
- Function chạy với runtime identity riêng để truy cập database, queue, secret hoặc storage.
- Code nghiệp vụ vẫn phải kiểm tra người dùng có quyền thao tác trên order, tenant hoặc resource cụ thể hay không.

**Execution role không phải danh tính của người dùng cuối.** Nếu Lambda có quyền đọc mọi đơn hàng, điều đó không có nghĩa user gửi request được phép đọc mọi đơn hàng. Phân quyền nghiệp vụ phải kiểm tra subject, tenant, ownership và policy từ ngữ cảnh đã xác thực.

## 2. Vì sao mỗi function nên có identity riêng?

Giả sử hệ thống đặt hàng có các function:

- `order-api`: nhận request và tạo đơn.
- `inventory-reserver`: giữ hàng trong kho.
- `payment-processor`: gọi cổng thanh toán.
- `invoice-writer`: tạo hóa đơn trong object storage.
- `notification-sender`: gửi email hoặc notification.

Nếu cả năm function dùng chung một role có quyền đọc/ghi database, S3, SQS, Secrets Manager và gọi mọi Lambda, mỗi function có thể làm nhiều hơn trách nhiệm của nó.

Thiết kế tách quyền:

| Function | Tài nguyên cần truy cập | Quyền cần thiết điển hình |
|---|---|---|
| order-api | Orders table, order-created queue | Đọc/ghi thao tác cần thiết trên orders; gửi message vào queue |
| inventory-reserver | Inventory table, reservation queue | Conditional update inventory; đọc message nguồn |
| payment-processor | Payment secret, payment provider | Đọc đúng secret; gọi outbound API |
| invoice-writer | Invoice bucket | Ghi object trong prefix invoices |
| notification-sender | Notification queue/provider secret | Đọc message; gửi notification |

Lợi ích:

1. **Giới hạn blast radius:** nếu một function bị khai thác, attacker chỉ có quyền của role đó.
2. **Dễ audit:** CloudTrail hoặc audit log cho biết workload identity nào đã thực hiện action.
3. **Dễ phát hiện quyền thừa:** một function không cần S3 thì không có quyền S3.
4. **Triển khai độc lập:** có thể thay đổi quyền cho một function mà không làm tăng quyền của function khác.
5. **Tách trách nhiệm:** nhóm sở hữu từng function có thể xác định rõ resource contract.

Tách role theo function hoặc theo workload boundary có rủi ro và vòng đời giống nhau. Không cần tạo role mới cho mọi helper nhỏ nếu chúng thực sự cùng trust boundary và cùng tập quyền; nhưng các function xử lý dữ liệu nhạy cảm hoặc side effect quan trọng nên có identity riêng.

## 3. Trust policy và permission policy của AWS Lambda

AWS Lambda sử dụng IAM execution role. Có hai phần chính:

- **Trust policy:** xác định principal nào được phép assume role.
- **Permission policy:** xác định code chạy với role được làm những action nào trên resource nào.

Trust policy cơ bản cho Lambda:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

Trust policy này cho phép Lambda service assume role. Nó không cho code đọc S3, DynamoDB hay secret. Những quyền đó nằm trong permission policy gắn với role.

Với workload cần ràng buộc chặt hơn, có thể thêm điều kiện nguồn vào trust policy để giới hạn function/account được phép sử dụng role. Ví dụ minh họa:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Service": "lambda.amazonaws.com" },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "aws:SourceAccount": "123456789012"
        },
        "ArnLike": {
          "aws:SourceArn": "arn:aws:lambda:ap-southeast-1:123456789012:function:order-api"
        }
      }
    }
  ]
}
~~~

Điều kiện phải khớp ARN/account thực tế và cách Lambda assume role trong môi trường triển khai. Khi function được đổi tên hoặc chuyển account/region, cần cập nhật trust policy cùng deployment.

Ví dụ permission policy cho function xử lý đơn hàng:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "WriteOrderRecords",
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem"
      ],
      "Resource": "arn:aws:dynamodb:ap-southeast-1:123456789012:table/Orders"
    },
    {
      "Sid": "PublishOrderCreated",
      "Effect": "Allow",
      "Action": "sqs:SendMessage",
      "Resource": "arn:aws:sqs:ap-southeast-1:123456789012:order-created"
    },
    {
      "Sid": "WriteFunctionLogs",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:ap-southeast-1:123456789012:log-group:/aws/lambda/order-api:*"
    }
  ]
}
~~~

Policy chỉ là ví dụ. Nếu function cần tạo log group lần đầu, có thể cần quyền `logs:CreateLogGroup` trên phạm vi phù hợp; một cách khác là tạo log group qua infrastructure deployment. Hãy xác định chính xác API mà code và runtime cần, sau đó cấp quyền theo resource-level support của từng action.

Không gắn `AdministratorAccess` hoặc `PowerUserAccess` vào execution role để xử lý lỗi AccessDenied. Hãy xác định action và resource bị từ chối rồi bổ sung đúng quyền.

### Tách quyền logging khỏi quyền nghiệp vụ

Logging là một phần của vận hành, nhưng không nên dùng nó làm lý do cấp quyền rộng. Có thể tạo log group trước bằng IaC và cấp role chỉ quyền ghi log stream/event trong log group của function. Nếu dùng CloudWatch Logs subscription hoặc destination, quyền quản trị subscription thường thuộc deployment role.

## 4. Giới hạn action và resource

Một IAM statement nên giới hạn tối thiểu ba yếu tố:

1. **Action:** function được phép làm gì?
2. **Resource:** function được phép làm trên tài nguyên nào?
3. **Condition:** trong hoàn cảnh nào action được phép?

Ví dụ không nên:

~~~json
{
  "Effect": "Allow",
  "Action": "*",
  "Resource": "*"
}
~~~

Nếu function chỉ đọc một secret, policy có thể giới hạn:

~~~json
{
  "Effect": "Allow",
  "Action": "secretsmanager:GetSecretValue",
  "Resource": "arn:aws:secretsmanager:ap-southeast-1:123456789012:secret:prod/payments/provider-*"
}
~~~

Nếu function chỉ ghi file hóa đơn trong một prefix S3:

~~~json
{
  "Effect": "Allow",
  "Action": "s3:PutObject",
  "Resource": "arn:aws:s3:::company-invoices/prod/*"
}
~~~

Nếu cần đọc metadata bucket, action như `s3:ListBucket` áp dụng trên bucket ARN, trong khi `s3:GetObject` áp dụng trên object ARN. Không gộp hai loại resource ARN rồi cho rằng policy sẽ hoạt động như nhau.

Một số action không hỗ trợ resource-level permission hoặc cần `Resource: "*"`. Khi đó, tách action đó thành statement riêng, dùng condition keys nếu dịch vụ hỗ trợ và ghi rõ lý do. Không mở rộng toàn bộ policy chỉ vì một action yêu cầu wildcard.

### Condition keys

Condition có thể giới hạn quyền theo:

- Source ARN hoặc source account đối với service principal gọi Lambda.
- VPC endpoint mà request đi qua, nếu dịch vụ và action hỗ trợ.
- Encryption context hoặc KMS key context.
- Principal tag, resource tag hoặc organization ID khi phù hợp.
- TLS hoặc các điều kiện bảo mật mà service hỗ trợ.

Condition phải dựa trên key thực sự được dịch vụ hỗ trợ cho action đó. Một condition viết sai có thể khiến quyền không hoạt động hoặc tạo cảm giác bảo vệ giả. Kiểm thử cả request hợp lệ và request phải bị từ chối.

## 5. Quyền invoke function khác quyền function truy cập tài nguyên

Một trong những lỗi IAM phổ biến nhất là nhầm quyền gọi Lambda với execution role.

### Caller gọi Lambda trực tiếp

Nếu một IAM role của service A gọi Lambda B bằng SDK, role của A cần `lambda:InvokeFunction` trên function/alias ARN cụ thể:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "lambda:InvokeFunction",
      "Resource": "arn:aws:lambda:ap-southeast-1:123456789012:function:inventory-reserver:prod"
    }
  ]
}
~~~

Function B vẫn dùng execution role riêng để đọc inventory table hoặc ghi reservation queue. Quyền invoke không tự cấp quyền cho caller đọc dữ liệu mà function truy cập.

### AWS service gọi Lambda

Với các dịch vụ push invocation như S3, SNS hoặc EventBridge, Lambda resource-based policy thường cho phép service principal gọi function. Ví dụ EventBridge rule:

~~~bash
aws lambda add-permission \
  --function-name order-event-handler \
  --statement-id allow-orders-rule \
  --action lambda:InvokeFunction \
  --principal events.amazonaws.com \
  --source-arn arn:aws:events:ap-southeast-1:123456789012:rule/orders-created
~~~

Với tích hợp production, giới hạn source ARN và source account khi phù hợp. Nếu trigger gọi alias, cấp permission ở đúng qualifier và cấu hình target trỏ cùng alias.

Với S3 notification, source ARN thường là bucket ARN và có thể thêm source account. Hãy bảo đảm bucket và Lambda ở region tương thích theo yêu cầu của tích hợp. Không cấp quyền cho toàn bộ principal của một service mà không ràng buộc nguồn nếu dịch vụ hỗ trợ điều kiện nguồn.

### SQS và stream event source mapping

SQS là mô hình poll-based event source mapping. Lambda service poll queue bằng quyền của execution role được cấu hình cho function. Role thường cần các action như:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:GetQueueAttributes",
        "sqs:ChangeMessageVisibility"
      ],
      "Resource": "arn:aws:sqs:ap-southeast-1:123456789012:orders-queue"
    }
  ]
}
~~~

Nếu queue mã hóa bằng customer-managed KMS key, cần kiểm tra thêm quyền KMS và key policy. Với queue cross-account, có thể cần queue resource policy cho phép principal phù hợp.

DynamoDB Streams hoặc Kinesis cũng cần quyền đọc stream/shard phù hợp trên execution role, ví dụ `dynamodb:DescribeStream`, `dynamodb:GetRecords`, `dynamodb:GetShardIterator`, `dynamodb:ListStreams` hoặc các action tương ứng của Kinesis theo mapping. Một số action liệt kê có thể yêu cầu resource wildcard vì không hỗ trợ resource-level scope; tách chúng thành statement riêng. Không cấp quyền ghi toàn bộ table nếu function chỉ consume stream.

### Ma trận phân biệt

| Tích hợp | Quyền invoke/poll ở đâu? | Runtime role còn cần gì? |
|---|---|---|
| API Gateway → Lambda | Lambda resource policy cho API Gateway service principal hoặc cơ chế invoke đã cấu hình | Quyền đọc/ghi dữ liệu mà code thực hiện |
| EventBridge → Lambda | Lambda resource policy cho rule/source ARN | Quyền truy cập resource nghiệp vụ |
| S3 notification → Lambda | Lambda resource policy cho bucket/source account | `s3:GetObject` chỉ khi code thực sự đọc object |
| SQS event source mapping | Execution role cho phép poll/delete message | Quyền database, secret, output queue theo logic |
| DynamoDB/Kinesis stream mapping | Execution role có quyền đọc stream | Quyền ghi/đọc tài nguyên khác theo logic |
| Service A gọi Lambda B bằng SDK | Identity policy của A có `lambda:InvokeFunction` | Execution role của B có quyền xử lý công việc |

Đừng cấp `s3:GetObject` cho Lambda chỉ vì S3 là nguồn event nếu function chỉ đọc metadata trong event. Chỉ cấp quyền đọc object khi code thực sự gọi S3 API.

## 6. Quyền KMS và secret theo từng function

Khi function đọc secret, role cần quyền đọc đúng secret. Nếu secret được mã hóa bằng customer-managed KMS key, role có thể cần `kms:Decrypt` và key policy phải cho phép principal sử dụng key.

Ví dụ hai statement tách riêng:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadPaymentSecret",
      "Effect": "Allow",
      "Action": "secretsmanager:GetSecretValue",
      "Resource": "arn:aws:secretsmanager:ap-southeast-1:123456789012:secret:prod/payments/provider-*"
    },
    {
      "Sid": "DecryptPaymentSecret",
      "Effect": "Allow",
      "Action": "kms:Decrypt",
      "Resource": "arn:aws:kms:ap-southeast-1:123456789012:key/11111111-2222-3333-4444-555555555555"
    }
  ]
}
~~~

KMS key policy và IAM policy cùng tham gia quyết định quyền theo cách cấu hình key. Không cấp `kms:*` trên mọi key. Nếu key policy hỗ trợ điều kiện encryption context phù hợp, có thể giới hạn thêm theo secret hoặc service context.

Function chỉ gửi email không cần quyền đọc database password. Function chỉ xử lý inventory không cần payment API key. Tách secret theo domain và quyền theo function giúp giảm khả năng một credential bị lộ kéo theo toàn bộ hệ thống.

## 7. Java: dùng credential provider mặc định

Java code không nên chứa access key hoặc secret access key. AWS SDK for Java 2.x có thể dùng default credentials provider chain để lấy credential tạm thời từ môi trường runtime, bao gồm execution role credentials do Lambda cung cấp.

Ví dụ:

~~~java
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;

public final class InventoryRepository {
    private final DynamoDbClient dynamoDb;

    public InventoryRepository() {
        this.dynamoDb = DynamoDbClient.builder()
                .credentialsProvider(DefaultCredentialsProvider.create())
                .build();
    }

    // Repository methods use the client to access the permitted table.
}
~~~

Trong Lambda, execution role cung cấp credential tạm thời và SDK tự refresh theo cơ chế provider. Client SDK nên được tái sử dụng trong cùng execution environment nếu thread-safe; không tạo client mới ở mỗi request. Không log credential, session token hoặc toàn bộ environment variables.

Với Google Cloud, Java client libraries thường dùng **Application Default Credentials (ADC)**. Khi chạy Cloud Run, gắn user-managed service account làm runtime identity; client library lấy credential ngắn hạn từ metadata server. Không tạo và mount service account key JSON nếu môi trường có thể dùng attached service account.

## 8. Google Cloud: service account riêng cho từng Cloud Run service

Cloud Run service có hai danh tính quan trọng:

- **Caller identity:** principal cần quyền invoke service đích, thường là `roles/run.invoker`.
- **Runtime service account:** danh tính mà container dùng khi gọi Google Cloud APIs.

Ví dụ kiến trúc:

| Service | Runtime service account | Quyền được cấp |
|---|---|---|
| orders-api | `orders-api-runtime@` | Ghi orders, publish đúng topic |
| inventory-worker | `inventory-runtime@` | Đọc subscription, cập nhật inventory |
| invoice-worker | `invoice-runtime@` | Ghi object vào invoice bucket |
| payment-worker | `payment-runtime@` | Đọc đúng secret và gọi payment provider |

Gắn service account vào service trong lúc deploy. Ví dụ:

~~~bash
gcloud run deploy orders-api \
  --image REGION-docker.pkg.dev/PROJECT_ID/apps/orders-api:v1 \
  --region REGION \
  --service-account orders-api-runtime@PROJECT_ID.iam.gserviceaccount.com \
  --no-allow-unauthenticated
~~~

Cấp quyền cho caller invoke service:

~~~bash
gcloud run services add-iam-policy-binding orders-api \
  --region REGION \
  --member serviceAccount:frontend-runtime@PROJECT_ID.iam.gserviceaccount.com \
  --role roles/run.invoker
~~~

Quyền `roles/run.invoker` cho phép principal gọi Cloud Run service; nó không cấp quyền cho container đọc Secret Manager hoặc ghi bucket. Những quyền đó phải được gắn vào runtime service account riêng.

Không dùng default compute service account cho mọi service nếu nó có quyền rộng. Tạo user-managed service account theo workload, cấp role ở resource scope nhỏ nhất có thể và không tạo key tĩnh nếu attached identity đáp ứng được nhu cầu.

## 9. Quyền cho service-to-service và cross-account

Khi function A gọi function B, cần xác định cả hai phía:

- A có quyền invoke B.
- B có thể xác minh caller hoặc nhận request đã được xác thực theo integration.
- B dùng runtime identity của chính B để truy cập dữ liệu.
- Nếu hai account/project khác nhau, cả hai phía cần policy tương ứng.

Với AWS cross-account Lambda invocation, caller role ở account A cần identity policy cho phép `lambda:InvokeFunction` trên function B; resource-based policy của function B ở account B phải cho phép principal/account A. Nếu dùng alias, cấp permission trên đúng alias ARN.

Với Google Cloud service-to-service, service caller cần quyền invoke trên Cloud Run service đích và gửi ID token có audience phù hợp. Runtime service account của service gọi không tự động trở thành danh tính của người dùng cuối.

Không truyền access key của service A vào event payload để service B dùng lại. Dùng workload identity và credential tạm thời của nền tảng, hoặc token trao đổi theo cơ chế được hỗ trợ.

## 10. Kết hợp IAM với network controls

IAM xác định principal được phép thực hiện action. Network controls xác định request có thể đi qua đường mạng nào và kết nối đến endpoint nào. Hai lớp bổ sung cho nhau.

Ví dụ, Lambda có thể chỉ có quyền đọc một secret theo IAM nhưng vẫn cần đường mạng phù hợp nếu function đặt trong VPC và truy cập Secrets Manager qua private endpoint. Ngược lại, một function nằm trong private subnet không tự động có quyền đọc secret chỉ vì nó ở trong mạng nội bộ.

### AWS Lambda trong VPC

Khi Lambda cần truy cập resource trong private subnet:

- Chọn subnet và security group phù hợp.
- Giới hạn outbound rule của security group gắn với Lambda; ở phía database, chỉ cho phép inbound từ security group của Lambda trên port cần thiết.
- Dùng VPC endpoint cho dịch vụ AWS được hỗ trợ khi muốn truy cập qua private network.
- Với endpoint policy, giới hạn principal/action/resource nếu dịch vụ hỗ trợ.
- Kiểm tra route table, DNS, NACL và security group khi request timeout.
- Nếu function cần truy cập internet công khai từ private subnet, thiết kế NAT egress phù hợp; VPC attachment tự nó không tạo đường internet outbound.
- Không đưa function vào VPC nếu không cần truy cập tài nguyên private; cấu hình VPC có thể thêm độ phức tạp và ảnh hưởng cold start/networking.

Security group kiểm soát luồng mạng, không thay thế IAM. Nếu function có outbound đến internet, vẫn phải bảo vệ endpoint bằng TLS, xác thực và quyền ở tầng ứng dụng.

### Google Cloud Run

Cloud Run có thể cấu hình ingress để giới hạn nguồn request, dùng IAM Invoker cho service-to-service và cấu hình Direct VPC egress hoặc Serverless VPC Access khi cần truy cập mạng private.

- Ingress kiểm soát request có thể vào service từ đâu.
- IAM Invoker xác định principal nào được gọi service.
- Runtime service account quyết định quyền truy cập Google Cloud APIs.
- VPC/firewall controls quyết định đường kết nối đến private resources.

Không xem ingress internal là thay thế authorization trong ứng dụng nếu service còn có nhiều caller hoặc cần phân quyền theo user/tenant.

### Bảng chọn lớp kiểm soát

| Mối đe dọa hoặc yêu cầu | Lớp kiểm soát |
|---|---|
| Caller không được phép invoke function | IAM identity policy/resource policy |
| Function đọc nhầm bảng hoặc secret | Execution role/service account và resource scope |
| User đọc dữ liệu tenant khác | Authorization trong Java service và query scope |
| Request đi từ mạng không mong muốn | Ingress, VPC, firewall, endpoint policy |
| Credential bị lộ trong source | Secret manager, workload identity, short-lived credentials |
| Một function bị xâm nhập | Identity riêng, quyền tối thiểu, giới hạn egress và audit |

## 11. Tách quyền deploy và quyền runtime

Quyền triển khai thường rộng hơn quyền chạy ứng dụng. Pipeline có thể cần tạo function, cập nhật image, publish version, gắn role, cập nhật alias và cấu hình trigger. Runtime function chỉ cần đọc/ghi tài nguyên nghiệp vụ trong lúc xử lý.

Tách ít nhất hai principal:

- **Deployment identity:** được phép tạo/cập nhật function và cấu hình hạ tầng. Với AWS, cần giới hạn `iam:PassRole` vào các execution role đã phê duyệt.
- **Runtime identity:** được gắn vào function và chỉ có quyền cần thiết khi thực thi.

Không gắn quyền `iam:PassRole`, `iam:CreatePolicy`, `lambda:UpdateFunctionCode` hoặc `iam:AttachRolePolicy` vào execution role của function. Nếu code runtime có thể sửa role của chính nó hoặc cập nhật function, lỗi ứng dụng có thể trở thành chiếm quyền hạ tầng.

Với Google Cloud, service account dùng để deploy cũng khác runtime service account. Người triển khai cần quyền gắn service account theo chính sách tổ chức; container chỉ nhận quyền của runtime identity đã gắn.

## 12. Quy trình thiết kế quyền tối thiểu

Một quy trình có thể áp dụng cho từng function:

1. **Viết trách nhiệm:** function nhận loại trigger nào và thực hiện nghiệp vụ gì?
2. **Liệt kê API call:** xác định AWS/GCP API mà code, SDK, extension hoặc event source mapping thực sự gọi.
3. **Xác định principal:** caller, runtime identity, service principal và resource policy liên quan.
4. **Liệt kê resource:** bảng, bucket, queue, secret, key hoặc function đích; ghi ARN/name cụ thể.
5. **Tạo policy nhỏ:** chỉ action cần thiết trên resource cụ thể; dùng condition khi phù hợp.
6. **Cấu hình network:** subnet, security group, ingress và endpoint chỉ cho đường cần thiết.
7. **Kiểm thử positive và negative:** thao tác hợp lệ thành công; thao tác ngoài phạm vi bị AccessDenied.
8. **Quan sát production:** theo dõi AccessDenied, API usage, audit log và resource access.
9. **Rà soát định kỳ:** bỏ action/resource không còn dùng, kiểm tra role drift và secret access.
10. **Ghi lại owner:** mỗi role/service account có workload owner và quy trình thay đổi rõ ràng.

### Ví dụ ma trận quyền

| Function | Trigger | Runtime resources | Quyền không nên có |
|---|---|---|---|
| order-api | API Gateway | Orders table, order queue | Payment secret, invoice bucket |
| inventory-worker | SQS | Inventory table | Orders API invoke, payment key |
| payment-worker | SQS | Payment secret, payment provider | Inventory table, invoice bucket |
| invoice-worker | EventBridge/SQS | Invoice bucket, invoice metadata table | Payment secret, user directory |
| notification-worker | SQS | Notification secret/provider | Database admin, function deployment |

Ma trận này là điểm khởi đầu để tạo policy. Sau đó kiểm tra từng SDK operation, event source mapping, KMS key và resource policy thực tế.

## 13. Kiểm thử và audit quyền

Một policy chỉ chạy qua deploy thành công không có nghĩa là đúng. Cần kiểm tra cả hành vi được phép và bị từ chối.

### Positive tests

- Function order-api ghi được vào Orders table.
- Function order-api publish được message vào đúng queue.
- Payment worker đọc được đúng payment secret.
- Invoice worker ghi được object trong prefix được cấp.
- Caller hợp lệ invoke được function alias hoặc Cloud Run service.

### Negative tests

- Order API không đọc được payment secret.
- Payment worker không ghi được invoice bucket.
- Invoice worker không đọc được Orders table nếu không cần.
- Caller không được phép không invoke được production function.
- Principal khác không gọi được Cloud Run service nội bộ.
- Function không truy cập được resource ở environment khác.

IAM Policy Simulator có thể hỗ trợ đánh giá một số identity policy, nhưng không thay thế integration test với resource policy, trust policy, KMS key policy, service integration và điều kiện runtime thực tế. Hãy test trong account/project không chứa dữ liệu production.

### Audit và phát hiện quyền thừa

- Dùng AWS CloudTrail để xem API call của role và resource; bật data events cho loại tài nguyên cần theo dõi nếu phù hợp.
- Dùng IAM Access Analyzer để phát hiện resource policy chia sẻ ra ngoài hoặc quyền truy cập không mong muốn.
- Dùng Google Cloud Audit Logs để kiểm tra principal truy cập resource và thay đổi IAM policy.
- Theo dõi AccessDenied và lỗi permission theo function/revision.
- Rà soát role/service account không còn gắn với workload.
- Loại bỏ policy statement không còn được sử dụng sau khi xác minh qua thời gian quan sát đủ dài.

Không xóa quyền chỉ vì không thấy invocation trong một khoảng ngắn. Có thể function chỉ chạy theo lịch hoặc xử lý event hiếm. Kết hợp owner, lịch chạy, trigger và audit history trước khi thu hồi.

## 14. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Mọi function dùng chung admin role | Blast radius lớn | Tách workload identity và policy |
| Nhầm invoke permission với execution role | Caller hoặc function bị thiếu quyền ở sai lớp | Vẽ luồng principal cho từng bước |
| Dùng `Resource: "*"` cho mọi action | Function có quyền trên tài nguyên không liên quan | Thu hẹp ARN; tách action cần wildcard |
| Chỉ dựa vào private subnet | Service nội bộ vẫn có thể bị gọi sai hoặc có quyền dữ liệu quá rộng | Kết hợp IAM, app authorization và network controls |
| Đưa access key vào environment variable | Credential dài hạn có thể bị lộ | Dùng workload identity và credential tạm thời |
| Cấp quyền KMS trên mọi key | Một function có thể giải mã secret ngoài phạm vi | Giới hạn key ARN và key policy |
| Cho runtime role quyền deploy | Lỗi code có thể sửa hạ tầng hoặc role | Tách deployment identity |
| Không test negative cases | Không phát hiện quyền thừa | Thử thao tác ngoài phạm vi và xác nhận bị từ chối |
| Tin claims do client tự gửi | Có thể vượt quyền tenant/user | Dùng authorizer context và kiểm tra ownership phía server |

## 15. Checklist quyền tối thiểu cho Java serverless

- [ ] Mỗi function nhạy cảm có workload identity riêng.
- [ ] Caller identity, end-user identity và runtime identity được phân biệt.
- [ ] Trust policy chỉ cho đúng runtime/service assume role.
- [ ] Permission policy chỉ có action cần thiết.
- [ ] Resource ARN giới hạn đến đúng table, bucket prefix, queue, secret hoặc function.
- [ ] Action không hỗ trợ resource scope được tách riêng và có lý do.
- [ ] Lambda resource policy giới hạn service principal bằng source ARN/account khi phù hợp.
- [ ] SQS/stream event source mapping có quyền poll/read đúng nguồn.
- [ ] KMS permission và key policy chỉ cho phép key cần thiết.
- [ ] Java SDK dùng default credential provider/ADC, không chứa key tĩnh.
- [ ] Cloud Run service dùng user-managed runtime service account theo workload.
- [ ] Caller có quyền invoke riêng; runtime service account có quyền truy cập tài nguyên riêng.
- [ ] Cross-account invocation được cấp phép ở cả caller và resource khi cần.
- [ ] Network ingress, egress, VPC và endpoint policy được cấu hình theo luồng thực tế.
- [ ] Deployment identity tách khỏi runtime identity; `iam:PassRole` được giới hạn.
- [ ] Có positive test và negative test cho từng function.
- [ ] Audit log và cảnh báo AccessDenied được theo dõi.
- [ ] Policy được rà soát khi trigger, resource hoặc trách nhiệm function thay đổi.

## Tự kiểm tra

1. End-user identity, caller identity và function execution identity khác nhau như thế nào?
2. Vì sao hai function xử lý payment và notification không nên dùng chung một role có quyền đọc mọi secret?
3. Trust policy và permission policy của Lambda giải quyết hai câu hỏi nào?
4. Khi API Gateway gọi Lambda, vì sao cần phân biệt quyền invoke với quyền Lambda đọc database?
5. Với SQS event source mapping, execution role cần những quyền nào để poll queue?
6. Khi function chỉ nhận S3 event metadata mà không đọc object, có cần cấp `s3:GetObject` không?
7. Vì sao cross-account Lambda invocation cần policy ở phía caller và resource?
8. Network private có thay thế IAM và authorization theo tenant không?
9. Vì sao deployment role cần tách khỏi runtime execution role?
10. Negative test giúp phát hiện loại lỗi quyền nào mà positive test không thể phát hiện?

Thiết kế quyền tối thiểu bắt đầu từ trách nhiệm của từng function và luồng principal thực tế. Mỗi workload dùng identity riêng, chỉ được phép gọi action cần thiết trên resource cụ thể; trigger, runtime và người dùng cuối được kiểm soát ở đúng ranh giới. Khi kết hợp IAM, resource policy, network controls, credential tạm thời, audit và negative testing, một function bị lỗi sẽ khó lan sang dữ liệu và dịch vụ ngoài phạm vi của nó.

