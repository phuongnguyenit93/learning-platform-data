# CloudTrail Event history, trail và loại sự kiện

Khi cần trả lời câu hỏi “Ai đã thay đổi Security Group?”, “Role nào tạo một IAM access key?”, “Ứng dụng nào đọc object trong S3?” hoặc “Yêu cầu nào bị VPC endpoint policy từ chối?”, đội vận hành cần một nguồn audit có thể truy ngược danh tính, hành động, thời điểm và ngữ cảnh. AWS CloudTrail ghi nhận hoạt động API và một số hoạt động đăng nhập/sự kiện dịch vụ trong tài khoản AWS, giúp điều tra sự cố, kiểm soát thay đổi và đáp ứng yêu cầu kiểm toán.

CloudTrail có ba khái niệm thường bị nhầm lẫn:

- **Event history** là giao diện tra cứu các management events trong 90 ngày gần nhất theo từng Region, có sẵn cho tài khoản AWS.
- **Trail** là cấu hình ghi nhận liên tục và phân phối các event đã chọn tới S3, có thể gửi thêm tới CloudWatch Logs và tích hợp EventBridge để cảnh báo/phản ứng.
- **Event types** mô tả loại hoạt động được ghi nhận: management, data, network activity và Insights events. Không phải loại nào cũng được bật mặc định.

Bài thuộc chương **Kiểm toán và tuân thủ**, mô-đun **CLOUD_PROVIDERS_AWS**. Nội dung kết nối IAM, Region, VPC, S3, Lambda, database và các dịch vụ AWS với mục tiêu có audit evidence, giám sát hoạt động, điều tra thay đổi và kiểm soát rủi ro.

> **Nguyên tắc:** Event history hữu ích để điều tra nhanh sự kiện gần đây. Một trail được cấu hình đúng mới tạo bản ghi dài hạn và tập trung. Muốn theo dõi hành động trên dữ liệu, phải chọn đúng data events; bật management events không đồng nghĩa đã ghi mọi thao tác đọc/ghi object hoặc invoke function.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích CloudTrail ghi nhận loại hoạt động nào và vì sao cần audit trail.
2. Phân biệt Event history, trail và CloudTrail Lake event data store.
3. Hiểu phạm vi 90 ngày, Region và giới hạn tìm kiếm của Event history.
4. Phân biệt management events, data events, network activity events và Insights events.
5. Phân loại read events và write events.
6. Đọc các trường quan trọng trong CloudTrail JSON event record.
7. Tìm sự kiện bằng Console và AWS CLI `lookup-events`.
8. Tạo trail single-Region hoặc multi-Region và bật logging.
9. Thiết kế organization trail cho AWS Organizations.
10. Hiểu basic event selectors và advanced event selectors.
11. Chọn data events theo bucket, object prefix, Lambda function hoặc resource type.
12. Ghi network activity events qua VPC endpoints và Insights events khi cần.
13. Cấu hình S3 log delivery, CloudWatch Logs, EventBridge và log file integrity validation.
14. Quản lý retention, encryption, access control và chi phí CloudTrail.
15. Xây dựng quy trình điều tra, cảnh báo và kiểm tra audit coverage.

## 2. CloudTrail hoạt động như thế nào?

CloudTrail ghi nhận request/operation trong AWS account. Event record thường cho biết identity nào thực hiện hành động, service nhận request, API action, thời điểm, Region, source IP, user agent, resource và kết quả. Sự kiện có thể đến từ AWS Management Console, AWS CLI, SDK/API hoặc một số hoạt động do AWS service thực hiện.

~~~mermaid
flowchart TD
    ACTOR["User / IAM role / AWS service"] --> API["AWS Console / CLI / SDK / API"]
    API --> SERVICE["AWS service processes request"]
    SERVICE --> EVENT["CloudTrail event record"]
    EVENT --> HISTORY["Event history<br/>90-day management events"]
    EVENT --> TRAIL["Trail selectors"]
    TRAIL --> S3["Amazon S3 log archive"]
    TRAIL --> CW["CloudWatch Logs"]
    TRAIL --> EB["EventBridge integration"]
    S3 --> ATHENA["Amazon Athena / SIEM"]
    CW --> ALARM["Metric filters / alarms"]
    EB --> AUTO["Alert / automation"]
~~~

Một số lưu ý:

- Event history có sẵn cho mỗi account và ghi management events theo Region.
- Trail quyết định những event nào được phân phối liên tục và nơi nhận log.
- Event selectors lọc event types, resource types, resource ARNs hoặc API names theo khả năng của selector.
- CloudTrail không phải packet capture và không ghi toàn bộ payload ứng dụng. Nó ghi event metadata/API context theo định dạng mà dịch vụ hỗ trợ.
- CloudTrail log files không phải một stack trace được sắp xếp theo thứ tự gọi API; không giả định thứ tự record trong file là thứ tự nghiệp vụ tuyệt đối.
- Delivery không phải real-time. Log thường được phân phối trung bình khoảng vài phút sau API call, nhưng không có bảo đảm event sẽ xuất hiện trong thời gian cố định.

### 2.1. Event history, trail và CloudTrail Lake

| Thành phần | Dùng để làm gì? | Lưu trữ/truy vấn |
|---|---|---|
| Event history | Tra cứu nhanh management events gần đây | 90 ngày, theo account và Region; Console/LookupEvents |
| Trail | Ghi event liên tục theo selectors | Log files tại S3; có thể gửi CloudWatch Logs |
| CloudTrail Lake event data store | Ingest và query event ở quy mô/độ linh hoạt cao hơn | Event data store, truy vấn SQL trong CloudTrail Lake |

CloudTrail Lake không phải tên khác của trail. Event data store có cấu hình ingestion, selectors, retention và chi phí riêng; dữ liệu Lake không được phân phối như log files vào S3 theo cơ chế trail. **Lưu ý trạng thái dịch vụ tại thời điểm 20/11/2026:** AWS CloudTrail Lake đã đóng đăng ký cho khách hàng mới từ ngày 31/05/2026. Khách hàng hiện hữu có thể tiếp tục sử dụng; AWS khuyến nghị xem xét Amazon CloudWatch cho các khả năng tương tự. Vì vậy, CloudTrail Lake trong bài này là khái niệm/option dành cho tài khoản đã có quyền sử dụng trước thời điểm đóng đăng ký. Với triển khai mới, ưu tiên trail + S3 archive và CloudWatch/Athena theo nhu cầu.

### 2.2. Vì sao cần trail nếu đã có Event history?

Event history chỉ giữ 90 ngày và không cung cấp data events, network activity events hoặc organization-wide aggregation. Trail tạo bản ghi dài hạn trong S3, có thể tích hợp với hệ thống phân tích/giám sát và kiểm soát event selectors. Nếu yêu cầu audit retention 1 năm, 3 năm hoặc lâu hơn, hãy thiết kế S3 retention/lifecycle và kiểm soát xóa; không dựa vào Event history.

## 3. Event history: tra cứu management events trong 90 ngày

Event history là nơi bắt đầu khi điều tra một hoạt động gần đây. CloudTrail tự động cung cấp Event history cho AWS account; không cần tạo trail trước để xem các management events đã ghi nhận trong Region đó. Việc xem Event history không bị tính phí CloudTrail.

### 3.1. Phạm vi và giới hạn

| Thuộc tính | Event history |
|---|---|
| Thời gian | 90 ngày gần nhất |
| Event type | Management events |
| Phạm vi account | Một AWS account |
| Phạm vi Region | Một Region tại một thời điểm |
| Bộ lọc | Một attribute filter và time range |
| Data events | Không hiển thị |
| Network activity events | Không hiển thị |
| Insights events | Không hiển thị |
| Organization aggregation | Không có |
| Tải xuống | Console hỗ trợ CSV/JSON; tối đa 200.000 events mỗi file |

Event history không thể được cấu hình để giữ 1 năm và không thể mở rộng bằng cách chỉnh trail. Trail/event data store là nơi cần tạo để lưu và truy vấn event dài hạn.

### 3.2. Tìm kiếm trên Console

Trong CloudTrail Console:

1. Chọn Region nơi hành động xảy ra.
2. Mở **Event history**.
3. Chọn attribute filter như Event name, Event source, Username, Resource name hoặc Resource type.
4. Nhập giá trị chính xác và đặt time range.
5. Mở event để xem event record JSON, identity, request parameters, response và resources.
6. Tải xuống CSV/JSON nếu cần lưu bằng chứng hoặc tiếp tục phân tích.

Mặc định, Event history áp dụng bộ lọc `Read only = false`, tức chỉ hiển thị write events. Xóa filter này khi điều tra cả read events.

Ví dụ, muốn tìm lần gọi `CreateAccessKey`, chọn Event name và nhập đúng API name. Muốn tìm login events, tìm `ConsoleLogin`. Muốn xem thay đổi trong IAM, lọc Event source là `iam.amazonaws.com`.

### 3.3. Tìm bằng AWS CLI

`lookup-events` truy vấn Event history. Lệnh dưới đây tìm các lần gọi `ConsoleLogin` tại Region chỉ định:

~~~bash
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=ConsoleLogin \
  --region ap-southeast-1 \
  --max-results 50
~~~

Tìm các event từ IAM service:

~~~bash
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventSource,AttributeValue=iam.amazonaws.com \
  --region ap-southeast-1 \
  --max-results 50
~~~

Tìm trong khoảng thời gian cụ thể:

~~~bash
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=CreateAccessKey \
  --start-time 2026-11-19T00:00:00Z \
  --end-time 2026-11-20T23:59:59Z \
  --region ap-southeast-1
~~~

`LookupEvents` chỉ nhận một lookup attribute trong mỗi request; có thể dùng time range bổ sung. Nếu cần kết hợp nhiều điều kiện, nhiều account/Region hoặc query phức tạp, hãy dùng trail logs với Athena hoặc CloudTrail Lake.

### 3.4. Ví dụ điều tra nhanh

Giả sử một Security Group có rule SSH mới. Quy trình tìm kiếm ban đầu:

1. Lấy Security Group ID và Region từ cảnh báo.
2. Trong Event history, lọc Event source `ec2.amazonaws.com`.
3. Giới hạn time range theo thời điểm phát hiện.
4. Tìm event names liên quan như `AuthorizeSecurityGroupIngress`, `ModifySecurityGroupRules` hoặc API tương ứng với thao tác.
5. Đọc `userIdentity`, `sourceIPAddress`, `userAgent`, `requestParameters`, `eventTime` và `responseElements`.
6. Correlate với change ticket, deployment pipeline và CloudTrail trail archive nếu cần điều tra dài hơn.

Event history giúp tìm nhanh; nếu event cũ hơn 90 ngày hoặc cần data events thì phải truy vấn nguồn lưu trữ khác.

## 4. Bốn loại CloudTrail events

CloudTrail phân loại event thành bốn nhóm. Trails và event data stores mặc định ghi management events; data events, network activity events và Insights events cần được cấu hình rõ ràng.

| Loại event | Phạm vi | Ví dụ | Mặc định |
|---|---|---|---|
| Management | Control plane/resource configuration | `CreateVpc`, `PutBucketPolicy`, `AttachRolePolicy` | Có |
| Data | Data plane/resource operations | S3 `GetObject`, Lambda `Invoke`, DynamoDB data API | Không |
| Network activity | API request đi qua VPC endpoint, đặc biệt endpoint policy denial | `VpceAccessDenied` | Không |
| Insights | Bất thường về API call rate hoặc API error rate | Tăng đột biến `RunInstances` hoặc lỗi API | Không |

### 4.1. Management events — control plane

Management events ghi lại hoạt động quản lý resource/account, ví dụ:

- Tạo, sửa hoặc xóa VPC, subnet, route table, security group.
- Tạo IAM user/role, attach policy, đổi trust policy.
- Tạo S3 bucket, sửa bucket policy, cấu hình encryption/versioning.
- Tạo hoặc cập nhật CloudTrail trail.
- Cấu hình database, load balancer, EKS cluster và các resource khác.
- Một số sự kiện không phải API call như `ConsoleLogin`.

Management events có thể được phân loại:

- **Read events:** thao tác đọc metadata/configuration, ví dụ `DescribeInstances`, `GetRole`, `ListBuckets`.
- **Write events:** thao tác thay đổi state, ví dụ `RunInstances`, `CreateRole`, `DeleteBucket`, `PutBucketPolicy`.

Có thể chọn All, Read-only hoặc Write-only. Read events thường có volume lớn; write events thường quan trọng để phát hiện thay đổi hạ tầng. Trong audit security, không nên chỉ thu write events nếu cần biết ai đã đọc configuration nhạy cảm hoặc liệt kê tài nguyên.

### 4.2. Data events — data plane

Data events ghi hoạt động trên hoặc trong resource. Chúng thường có volume lớn hơn management events và có thể phát sinh phí bổ sung. Ví dụ:

- S3 object-level: `GetObject`, `PutObject`, `DeleteObject`.
- Lambda: `Invoke`.
- DynamoDB: data-plane operations như `GetItem`, `PutItem`, `Query` (tùy resource/event support).
- SNS: `Publish`, `PublishBatch` trên topic.
- Nhiều resource types khác được hỗ trợ bằng advanced event selectors.

Event history không hiển thị data events. Muốn biết ai đọc một object S3, cần bật data events cho bucket/prefix phù hợp trong trail hoặc event data store. Chỉ bật management events là chưa đủ.

### 4.3. Network activity events — hoạt động qua VPC endpoint

Network activity events giúp VPC endpoint owner ghi nhận AWS API calls đi qua endpoint từ private VPC tới AWS service. Chúng đặc biệt hữu ích khi điều tra endpoint policy đã từ chối request.

Ví dụ event có:

- `eventCategory: NetworkActivity`
- `eventType: AwsVpceEvent`
- `vpcEndpointId`
- `vpcEndpointAccountId`
- `errorCode: VpceAccessDenied` khi request bị endpoint policy từ chối.

Không phải mọi network packet hoặc mọi kết nối VPC đều được CloudTrail ghi. Network activity events là các event API cụ thể được hỗ trợ qua VPC endpoint và phải cấu hình event source bằng advanced event selectors. Danh sách service hỗ trợ có thể thay đổi theo thời gian.

### 4.4. Insights events — phát hiện bất thường

CloudTrail Insights phân tích baseline hoạt động API và phát hiện thay đổi đáng kể về:

- **API call rate:** số lần gọi API tăng/giảm bất thường; loại này phân tích write API calls.
- **API error rate:** tỷ lệ API trả lỗi bất thường; có thể phân tích read và write API calls.

Insights tạo event đánh dấu khoảng thời gian bất thường và thông tin để điều tra. Đây không phải cảnh báo mọi API error và không thay thế CloudWatch alarms hoặc security monitoring. Cần bật Insights rõ ràng và có thể phát sinh phí riêng. Lần đầu bật, có thể mất thời gian để CloudTrail xây dựng baseline và phát hiện anomaly.

## 5. Đọc CloudTrail event record

CloudTrail event record là JSON object. Log file được phân phối thường có cấu trúc JSON với mảng `Records` chứa một hoặc nhiều event. Event history cũng cho phép mở raw event để xem các trường tương tự.

### 5.1. Các trường quan trọng

| Field | Ý nghĩa | Câu hỏi hỗ trợ điều tra |
|---|---|---|
| `eventTime` | Thời điểm event theo UTC | Hành động xảy ra lúc nào? |
| `eventSource` | Service nhận request, ví dụ `ec2.amazonaws.com` | API gọi tới service nào? |
| `eventName` | API action hoặc tên event, ví dụ `RunInstances` | Đã thực hiện hành động gì? |
| `awsRegion` | Region xử lý request | Hành động xảy ra ở đâu? |
| `userIdentity` | Identity thực hiện request | Ai hoặc role nào thực hiện? |
| `sourceIPAddress` | IP nguồn của request | Request đến từ đâu? |
| `userAgent` | Công cụ/client tạo request | Console, CLI, SDK hay service nào? |
| `requestParameters` | Tham số request nếu có | Resource/config nào được yêu cầu? |
| `responseElements` | Phần response được ghi nhận nếu có | API trả về kết quả gì? |
| `errorCode` / `errorMessage` | Lỗi nếu request thất bại | Vì sao request bị từ chối? |
| `resources` | Resource liên quan nếu được cung cấp | Resource ARN/ID nào liên quan? |
| `readOnly` | Request được phân loại read hay write | Đây có phải thao tác thay đổi? |
| `eventCategory` | Management, Data hoặc NetworkActivity | Event thuộc loại nào? |
| `eventID` | ID duy nhất của event record | Dùng correlate record cụ thể |
| `recipientAccountId` | Account nhận event | Event được ghi cho account nào? |

Các trường optional có thể không xuất hiện trong mọi event. `requestParameters` hoặc `responseElements` có thể null, bị ẩn hoặc không chứa mọi thông tin nghiệp vụ. Không xem CloudTrail như bản sao đầy đủ của request/response payload.

### 5.2. Ví dụ event record rút gọn

~~~json
{
  "eventVersion": "1.09",
  "userIdentity": {
    "type": "AssumedRole",
    "principalId": "EXAMPLE:deployment-job",
    "arn": "arn:aws:sts::123456789012:assumed-role/DeploymentRole/deployment-job",
    "accountId": "123456789012"
  },
  "eventTime": "2026-11-20T03:12:45Z",
  "eventSource": "ec2.amazonaws.com",
  "eventName": "AuthorizeSecurityGroupIngress",
  "awsRegion": "ap-southeast-1",
  "sourceIPAddress": "198.51.100.25",
  "userAgent": "aws-cli/2.x",
  "requestParameters": {
    "groupId": "sg-0123456789abcdef0",
    "ipPermissions": "..."
  },
  "responseElements": null,
  "requestID": "example-request-id",
  "eventID": "example-event-id",
  "readOnly": false,
  "eventType": "AwsApiCall",
  "managementEvent": true,
  "recipientAccountId": "123456789012",
  "eventCategory": "Management"
}
~~~

Ví dụ trên đã rút gọn và thay ID bằng giá trị minh họa. Trong event thực, `userIdentity` có thể là IAMUser, AssumedRole, FederatedUser, AWSService, Root hoặc loại identity khác.

### 5.3. Đọc userIdentity

`userIdentity` là phần quan trọng nhất khi truy vết actor. Các trường con thường gặp:

- `type`: loại identity.
- `arn`: ARN của principal hoặc role session.
- `principalId`: định danh principal.
- `accountId`: account sở hữu identity.
- `accessKeyId`: access key ID được dùng nếu có; không phải secret access key.
- `sessionContext`: thông tin session, role, MFA và issuer.
- `invokedBy`: service đã gọi API thay mặt principal trong một số trường hợp.
- `sourceIdentity`: nếu được cấu hình, giá trị này nằm trong `requestParameters` của STS AssumeRole calls và trong `userIdentity.sessionContext` của các service API calls tiếp theo.

Nếu `type` là `AssumedRole`, ARN thường chứa tên role và session name. Session name giúp correlate với CI job, automation hoặc ticket. Nếu `type` là `AWSService`, hành động có thể do AWS service thực hiện theo service-linked role hoặc service principal; cần xem context trước khi quy trách nhiệm cho một người.

### 5.4. Correlate event

Để điều tra một thay đổi, kết hợp nhiều trường:

1. `eventTime` và `awsRegion` xác định timeline/phạm vi.
2. `eventName` và `eventSource` xác định API.
3. `userIdentity.arn` và `principalId` xác định actor/role session.
4. `sourceIPAddress` và `userAgent` cung cấp nguồn và client.
5. `requestParameters` xác định resource/property bị tác động.
6. `errorCode` và `responseElements` giúp phân biệt thành công/thất bại.
7. `eventID` dùng định danh event; `sharedEventID` có thể liên kết bản ghi cùng một hành động được gửi tới nhiều account.

Event logs có thể đến trễ và không đảm bảo thứ tự tuyệt đối. Khi cần timeline, sort theo `eventTime` và đối chiếu request ID, service logs, deployment logs và application telemetry.

## 6. Tạo trail cho một AWS account

Trail là cấu hình CloudTrail liên tục ghi các event được chọn và phân phối log files tới S3. Trail có thể là single-Region hoặc multi-Region. Với audit baseline, multi-Region trail thường phù hợp hơn vì giúp thu thập hoạt động trên tất cả enabled Regions.

### 6.1. Chuẩn bị S3 bucket

Tạo một S3 bucket chuyên lưu CloudTrail logs. Bucket cần:

- Block Public Access bật.
- Bucket policy cho phép CloudTrail service principal ghi đúng prefix.
- `aws:SourceArn` condition giới hạn đúng trail ARN để giảm confused-deputy risk.
- Encryption at rest (SSE-S3 hoặc SSE-KMS theo yêu cầu).
- Access chỉ cho security/audit roles và log processing roles.
- Lifecycle/retention phù hợp với policy.
- Bảo vệ chống xóa/sửa theo mức độ assurance cần thiết.

CloudTrail không yêu cầu bucket phải nằm cùng Region với trail. Bucket cũng không được cấu hình Requester Pays để nhận log delivery.

### 6.2. Tạo multi-Region trail bằng AWS CLI

Giả sử bucket `company-cloudtrail-archive` đã tồn tại và bucket policy đã cho phép trail ghi log:

~~~bash
aws cloudtrail create-trail \
  --name organization-audit-baseline \
  --s3-bucket-name company-cloudtrail-archive \
  --is-multi-region-trail \
  --include-global-service-events \
  --enable-log-file-validation \
  --region ap-southeast-1
~~~

Lệnh `create-trail` tạo cấu hình trail. Sau đó cần bắt đầu logging:

~~~bash
aws cloudtrail start-logging \
  --name organization-audit-baseline \
  --region ap-southeast-1
~~~

Kiểm tra trạng thái:

~~~bash
aws cloudtrail get-trail-status \
  --name organization-audit-baseline \
  --region ap-southeast-1
~~~

Kiểm tra cấu hình:

~~~bash
aws cloudtrail get-trail \
  --name organization-audit-baseline \
  --region ap-southeast-1

aws cloudtrail get-event-selectors \
  --trail-name organization-audit-baseline \
  --region ap-southeast-1
~~~

Các lệnh trên là thao tác cấu hình AWS và chỉ nên chạy với quyền được phê duyệt trong account mục tiêu. Nếu trail đã tồn tại, kiểm tra cấu hình hiện tại trước khi update.

### 6.3. Single-Region và multi-Region trail

| Thuộc tính | Single-Region | Multi-Region |
|---|---|---|
| Coverage | Một Region được chọn | Tất cả enabled Regions trong account |
| Cấu hình | Quản lý trong Region đó | Một home Region, trail copy hoạt động ở enabled Regions |
| Sự kiện global service | Theo cấu hình trail | Có thể ghi global service events |
| Rủi ro | Bỏ sót Region khác nếu workload mở rộng | Cần kiểm tra opt-in Regions và coverage |
| Use case | Lab, yêu cầu phạm vi hẹp | Audit baseline production |

Console tạo trail mới theo mặc định là multi-Region. Dùng CLI có thể tạo single-Region hoặc multi-Region bằng tham số tương ứng. Khi account bật opt-in Region mới, kiểm tra trail coverage và thời gian cần để cấu hình/event delivery hội tụ.

### 6.4. Kiểm tra log delivery

`get-trail-status` có các field hữu ích:

- `IsLogging`: trail có đang ghi hay không.
- `LatestDeliveryTime`: thời điểm phân phối log gần nhất.
- `LatestDeliveryError`: lỗi khi gửi tới S3.
- `LatestCloudWatchLogsDeliveryError`: lỗi gửi tới CloudWatch Logs.
- `LatestDigestDeliveryTime`: thời điểm phân phối digest file gần nhất.
- `StartLoggingTime` và `StopLoggingTime`: thời điểm bắt đầu/dừng logging.

Không chỉ nhìn `IsLogging=true`. Một trail có thể đang logging nhưng delivery tới S3/CloudWatch Logs gặp lỗi. Theo dõi cả delivery status và alert.

## 7. Organization trail cho AWS Organizations

Trong môi trường nhiều accounts, tạo một trail riêng ở từng account làm tăng công việc quản trị và có thể tạo khoảng trống khi account mới được thêm. **Organization trail** cho phép ghi hoạt động của management account và member accounts trong một AWS Organization vào cùng destination.

### 7.1. Ai có thể tạo organization trail?

- AWS Organizations management account có thể tạo organization trail.
- Management account có thể chỉ định CloudTrail delegated administrator để quản lý trails/event data stores.
- Member accounts nhìn thấy organization trail nhưng không thể tự sửa/xóa trail đó.
- Organization trail do delegated administrator tạo vẫn thuộc ownership của management account.
- S3 bucket policy phải cho phép CloudTrail ghi log cho organization path/account IDs.

### 7.2. Kiến trúc tập trung

~~~mermaid
flowchart TD
    ORG["AWS Organizations"]
    ORG --> MGMT["Management account"]
    ORG --> DEV["Dev account"]
    ORG --> STG["Staging account"]
    ORG --> PROD["Production account"]
    MGMT --> TRAIL["Organization multi-Region trail"]
    DEV --> TRAIL
    STG --> TRAIL
    PROD --> TRAIL
    TRAIL --> S3["Central audit S3 bucket<br/>Security / Log Archive account"]
    S3 --> SIEM["Athena / SIEM / audit tooling"]
~~~

Một thiết kế phổ biến đặt bucket ở Security/Log Archive account, còn trail được quản lý từ management account hoặc delegated administrator. Cần thiết lập bucket policy, KMS key policy và access role phù hợp cho cross-account delivery/read.

### 7.3. Kiểm soát account lifecycle

Khi account mới gia nhập organization, xác minh organization trail đã được áp dụng và logs được ghi. Khi account rời organization, log files đã được phân phối trước đó vẫn còn trong S3 destination theo retention policy. Quản lý quyền truy cập archive ở central account độc lập với quyền quản trị của member accounts.

Nếu home Region của organization multi-Region trail là opt-in Region, member accounts phải enable Region đó để gửi hoạt động vào organization trail. Chọn home Region và Region enablement theo chính sách organization; không giả định mọi member account đều tự động bật mọi opt-in Region.

## 8. Event selectors: chọn sự kiện nào được ghi

Event selectors quyết định event nào CloudTrail xử lý cho một trail. Thiết kế selector là bước quan trọng để cân bằng audit coverage, chi phí và volume log.

### 8.1. Management events: All, Read và Write

Với management events, có thể ghi:

- `All`: cả read và write events.
- `ReadOnly`: chỉ read events.
- `WriteOnly`: chỉ write events.

Trail mới mặc định ghi tất cả management events (read và write). Nếu thay đổi selector, cần hiểu rõ phạm vi trước khi áp dụng. Ví dụ, chỉ ghi write events có thể bỏ qua việc một principal đã gọi `GetRole`, `ListAccessKeys` hoặc `DescribeSecurityGroups`.

### 8.2. Basic event selectors

Basic selectors hỗ trợ management events và data events cho một số resource types phổ biến như:

- `AWS::S3::Object`
- `AWS::Lambda::Function`
- `AWS::DynamoDB::Table`

Ví dụ file `basic-selectors.json` ghi tất cả management events và data events trên một S3 bucket:

~~~json
[
  {
    "ReadWriteType": "All",
    "IncludeManagementEvents": true,
    "DataResources": [
      {
        "Type": "AWS::S3::Object",
        "Values": [
          "arn:aws:s3:::company-audit-data/"
        ]
      }
    ]
  }
]
~~~

Áp dụng selector:

~~~bash
aws cloudtrail put-event-selectors \
  --trail-name organization-audit-baseline \
  --event-selectors file://basic-selectors.json \
  --region ap-southeast-1
~~~

Với S3 object data events, resource value có thể giới hạn bucket hoặc prefix. Ví dụ `arn:aws:s3:::company-audit-data/finance/` để theo dõi object trong prefix `finance/`. Chọn đúng ARN pattern và kiểm tra event test sau khi cập nhật.

### 8.3. Advanced event selectors

Advanced selectors hỗ trợ lọc chi tiết hơn và có thể cấu hình data events cho nhiều resource types, network activity events và management events. Với CloudTrail Lake event data store, data events cũng cần advanced event selectors. Các field thường dùng gồm:

- `eventCategory`
- `resources.type`
- `resources.ARN`
- `eventName`
- `eventSource`
- `readOnly`
- `userIdentity.arn` (tùy event type/loại selector hỗ trợ)

Ví dụ chỉ ghi S3 object write events trong prefix tài chính:

~~~json
[
  {
    "Name": "S3 finance object writes",
    "FieldSelectors": [
      {
        "Field": "eventCategory",
        "Equals": ["Data"]
      },
      {
        "Field": "resources.type",
        "Equals": ["AWS::S3::Object"]
      },
      {
        "Field": "resources.ARN",
        "StartsWith": [
          "arn:aws:s3:::company-audit-data/finance/"
        ]
      },
      {
        "Field": "readOnly",
        "Equals": ["false"]
      }
    ]
  }
]
~~~

Áp dụng advanced selector:

~~~bash
aws cloudtrail put-event-selectors \
  --trail-name organization-audit-baseline \
  --advanced-event-selectors file://advanced-selectors.json \
  --region ap-southeast-1
~~~

CloudTrail cho phép dùng basic selectors hoặc advanced selectors cho một trail tại một thời điểm. Khi chuyển sang advanced selectors, các basic selectors hiện có sẽ bị thay thế; phải tái tạo đầy đủ các selection cần thiết trong cấu hình mới. Không gửi đồng thời cả hai loại selectors trong cùng một request.

### 8.4. Lọc theo API name và resource scope

Advanced selectors giúp giới hạn event theo API name, ví dụ chỉ ghi `GetObject`, `PutObject` hoặc `DeleteObject`, hoặc theo prefix/ARN. Tuy nhiên, đừng chọn quá hẹp nếu yêu cầu điều tra cần cả hoạt động đọc và ghi.

Một số pattern:

| Yêu cầu audit | Selector gợi ý |
|---|---|
| Ai đọc/ghi object trong bucket nhạy cảm? | Data events, `AWS::S3::Object`, bucket/prefix ARN |
| Ai invoke Lambda xử lý dữ liệu? | Data events, `AWS::Lambda::Function`, function ARN |
| Ai truy vấn/ghi DynamoDB? | Data events, `AWS::DynamoDB::Table`, table ARN |
| Chỉ audit thao tác xóa object | Data events + `eventName = DeleteObject` |
| Audit API bị VPC endpoint policy từ chối | NetworkActivity + eventSource + `errorCode = VpceAccessDenied` |

### 8.5. Network activity event selector

Ví dụ ghi các network activity events bị VPC endpoint policy từ chối đối với AWS KMS:

~~~json
[
  {
    "Name": "KMS VPC endpoint denials",
    "FieldSelectors": [
      {
        "Field": "eventCategory",
        "Equals": ["NetworkActivity"]
      },
      {
        "Field": "eventSource",
        "Equals": ["kms.amazonaws.com"]
      },
      {
        "Field": "errorCode",
        "Equals": ["VpceAccessDenied"]
      }
    ]
  }
]
~~~

Network activity events chỉ áp dụng cho các service/event sources CloudTrail hỗ trợ và phải được bật rõ. `errorCode` hiện dùng cho loại event này có thể giới hạn theo tài liệu AWS; ví dụ `VpceAccessDenied` là mã thường gặp khi endpoint policy từ chối request.

### 8.6. Bật CloudTrail Insights

Ví dụ bật API call rate Insights trên trail:

~~~bash
aws cloudtrail put-insight-selectors \
  --trail-name organization-audit-baseline \
  --insight-selectors '[{"InsightType":"ApiCallRateInsight"}]' \
  --region ap-southeast-1
~~~

Có thể chọn `ApiErrorRateInsight` hoặc cả hai loại nếu phù hợp. Điều kiện đầu vào phụ thuộc loại Insights: API call rate cần write events; API error rate cần read hoặc write events. Insights có phí riêng và chỉ phát sinh event khi CloudTrail phát hiện hoạt động lệch đáng kể so với baseline.

### 8.7. Kiểm tra selectors sau khi thay đổi

~~~bash
aws cloudtrail get-event-selectors \
  --trail-name organization-audit-baseline \
  --region ap-southeast-1

aws cloudtrail get-insight-selectors \
  --trail-name organization-audit-baseline \
  --region ap-southeast-1
~~~

Sau khi đổi selectors, tạo một hoạt động thử có chủ đích trên sandbox và kiểm tra event có xuất hiện trong đúng destination. Không suy ra coverage chỉ từ việc lệnh `put-event-selectors` trả thành công.

## 9. Log delivery, destination và retention

Trail phân phối log files tới S3. Có thể tích hợp thêm CloudWatch Logs để tìm kiếm/alert, SNS để nhận thông báo delivery và các công cụ phân tích như Athena/SIEM.

### 9.1. S3 log object path

CloudTrail lưu log files dưới dạng gzip JSON trong bucket. Đường dẫn tiêu chuẩn cho account trail thường có dạng:

~~~text
s3://company-cloudtrail-archive/AWSLogs/123456789012/CloudTrail/ap-southeast-1/2026/11/20/
~~~

Với organization trail, đường dẫn chứa organization ID và account ID trong cấu trúc path. Event categories khác có thể dùng prefix riêng như `CloudTrail-Insight` hoặc `CloudTrail-NetworkActivity`.

Một object log có thể chứa event xảy ra trước thời điểm object được phân phối. Không dùng timestamp trong object key thay cho `eventTime` để dựng timeline chính xác.

### 9.2. Delivery timing và retry

CloudTrail thường phân phối log files trung bình khoảng 5 phút sau API call, nhưng thời gian này không được bảo đảm. Một số trường hợp có thể chậm hơn. Thiết kế alert cần tính đến delivery delay và tránh giả định log xuất hiện tức thời.

Nếu trail bị cấu hình sai, ví dụ S3 bucket policy không cho phép ghi hoặc destination không truy cập được, CloudTrail có thể tiếp tục thử phân phối lại trong tối đa 30 ngày; các lần thử phân phối này có thể phát sinh chi phí. Kiểm tra `get-trail-status`, sửa destination policy và theo dõi delivery error.

### 9.3. Gửi log tới CloudWatch Logs

CloudWatch Logs hữu ích khi cần metric filters, alarms, Logs Insights và cảnh báo nhanh. Cấu hình trail với log group ARN và IAM role cho CloudTrail ghi log. Role cần permissions phù hợp để tạo log stream và put log events.

Có thể dùng CloudWatch Logs metric filter để đếm các event nhạy cảm như:

- IAM policy thay đổi.
- Root account activity.
- Console login failure.
- CloudTrail trail bị stop/update/delete.
- Security Group ingress mở rộng.
- KMS key bị disable hoặc scheduled deletion.

Metric filter cần parse JSON event structure và kiểm tra field path chính xác. Với audit điều tra, S3 archive vẫn quan trọng để lưu log dài hạn và phân tích độc lập.

### 9.4. EventBridge và phản ứng theo sự kiện

CloudTrail tích hợp EventBridge để đưa các AWS API events vào event bus, nơi có thể dùng rules để route tới SNS, SQS, Lambda hoặc automation. EventBridge phù hợp cho phản ứng vận hành như cảnh báo khi `StopLogging`, `DeleteTrail`, `PutBucketPolicy` hoặc thay đổi IAM nhạy cảm.

EventBridge rule là đường xử lý event-driven; nó không thay thế S3 archive/retention của trail. Với các event cần lưu bằng chứng dài hạn, duy trì trail selectors và destination riêng.

### 9.5. Retention và lifecycle

Chọn retention theo yêu cầu pháp lý, compliance, điều tra và chi phí:

- Giữ dữ liệu nóng trong S3 Standard hoặc lớp phù hợp cho truy vấn thường xuyên.
- Chuyển log cũ sang lớp lưu trữ rẻ hơn bằng S3 Lifecycle khi thời gian truy cập có thể dài.
- Xác định retention period và legal hold theo policy của tổ chức.
- Kiểm soát ai được đọc, sửa bucket policy, thay lifecycle hoặc xóa object.
- Dùng versioning/Object Lock nếu yêu cầu chống xóa/sửa cần mức bảo vệ mạnh hơn.
- Kiểm tra cả log files và digest files trong lifecycle rules.

Không chọn retention chỉ theo giá storage. Audit evidence có thể cần được giữ lâu hơn thời gian nhân viên hoặc workload đã tạo ra event.

## 10. Bảo vệ CloudTrail log và xác minh tính toàn vẹn

CloudTrail logs là audit evidence. Nếu principal có thể xóa, sửa hoặc ngăn log delivery, tổ chức có thể mất khả năng điều tra. Cần bảo vệ cả S3 destination, KMS key, trail configuration, digest files và quyền quản trị.

### 10.1. Bucket policy cho account trail

Ví dụ bucket policy tối thiểu cho một account trail. Thay bucket, account ID, Region và trail name bằng giá trị thật:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AWSCloudTrailAclCheck",
      "Effect": "Allow",
      "Principal": {
        "Service": "cloudtrail.amazonaws.com"
      },
      "Action": "s3:GetBucketAcl",
      "Resource": "arn:aws:s3:::company-cloudtrail-archive",
      "Condition": {
        "StringEquals": {
          "aws:SourceArn": "arn:aws:cloudtrail:ap-southeast-1:123456789012:trail/organization-audit-baseline"
        }
      }
    },
    {
      "Sid": "AWSCloudTrailWrite",
      "Effect": "Allow",
      "Principal": {
        "Service": "cloudtrail.amazonaws.com"
      },
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::company-cloudtrail-archive/AWSLogs/123456789012/*",
      "Condition": {
        "StringEquals": {
          "s3:x-amz-acl": "bucket-owner-full-control",
          "aws:SourceArn": "arn:aws:cloudtrail:ap-southeast-1:123456789012:trail/organization-audit-baseline"
        }
      }
    }
  ]
}
~~~

Đây là ví dụ cho account trail. Với organization trail, bucket policy cần cho phép path chứa organization ID và account IDs theo cấu trúc AWS yêu cầu. Nên dùng policy do CloudTrail Console/AWS documentation sinh cho đúng loại trail rồi review trước khi áp dụng.

### 10.2. Encryption và quyền truy cập

- Bật S3 Block Public Access ở bucket/account.
- Dùng SSE-S3 hoặc SSE-KMS theo encryption standard. Với SSE-KMS, key policy phải cho phép CloudTrail encrypt và audit roles decrypt.
- Giới hạn quyền `s3:GetObject`, `s3:ListBucket`, `s3:PutBucketPolicy`, `s3:PutLifecycleConfiguration` và `s3:DeleteObject`.
- Tách role ghi log, role đọc log, role quản trị trail và role quản trị KMS key.
- Ghi nhận thay đổi bucket policy, lifecycle, KMS key policy, trail selectors và logging status bằng chính CloudTrail/Config.
- Dùng SCP hoặc controls phù hợp để ngăn member account tắt/đổi audit logging nếu tổ chức yêu cầu central governance.

Không cấp quyền sửa/xóa log archive cho workload deployment roles. Role có quyền quản lý bucket hoặc KMS key có thể ảnh hưởng trực tiếp tới audit evidence.

### 10.3. Log file integrity validation

Khi bật log file integrity validation, CloudTrail tạo hash cho log files và digest files theo chu kỳ. Digest file được ký số và tham chiếu tới log files trong khoảng thời gian trước đó; có thể dùng AWS CLI để kiểm tra file đã bị sửa, xóa hoặc giữ nguyên sau khi CloudTrail phân phối.

Bật validation khi tạo hoặc update trail:

~~~bash
aws cloudtrail update-trail \
  --name organization-audit-baseline \
  --enable-log-file-validation \
  --region ap-southeast-1
~~~

Kiểm tra cấu hình:

~~~bash
aws cloudtrail get-trail \
  --name organization-audit-baseline \
  --region ap-southeast-1
~~~

Field `LogFileValidationEnabled` phải là `true`. CloudTrail bắt đầu phân phối digest files sau khi bật. Việc bật validation chỉ tạo digest/signature; để xác minh log, cần chạy quy trình validation bằng AWS CLI hoặc công cụ phù hợp.

### 10.4. Validation chứng minh điều gì?

Integrity validation giúp phát hiện thay đổi đối với log files/digest files sau khi được CloudTrail phân phối, dựa trên chuỗi digest đã ký. Nó **không**:

- Ngăn principal có quyền xóa object khỏi bucket.
- Bảo đảm mọi API call của mọi service đều được ghi.
- Thay thế encryption, access control, versioning hoặc Object Lock.
- Chứng minh trail selectors đã bao phủ đúng event types.
- Thay thế kiểm tra log delivery và alert khi trail bị stop.

Kết hợp digest validation với bucket versioning/Object Lock, restrictive bucket policy, KMS key protection, CloudTrail monitoring và retention controls.

## 11. Kết hợp CloudTrail với công cụ audit và monitoring

CloudTrail cung cấp event record; các dịch vụ khác giúp lưu trữ, tìm kiếm, đối chiếu compliance và phản ứng.

| Công cụ | Vai trò | Ví dụ sử dụng |
|---|---|---|
| Amazon S3 | Archive log dài hạn | Retention, lifecycle, Object Lock |
| CloudWatch Logs | Search và alert | Metric filters, Logs Insights, alarms |
| EventBridge | Route event theo pattern | Alert khi `StopLogging` hoặc IAM policy changes |
| Amazon Athena | SQL query trên S3 log files | Tìm role đã gọi `DeleteBucket` trong một khoảng thời gian |
| CloudTrail Lake | SQL query trên event data store | Correlate nhiều event categories/accounts/Regions |
| AWS Config | Configuration history/compliance | Xem resource config trước/sau một event |
| Security Hub / SIEM | Correlate findings và audit signals | Kết hợp CloudTrail với security findings |

### 11.1. CloudTrail + EventBridge

EventBridge rules có thể match CloudTrail events theo `source`, `detail-type`, `eventSource`, `eventName`, `userIdentity` hoặc `requestParameters` (tùy event pattern). Trail phải đang logging loại management/data/network events tương ứng để CloudTrail phát các event phù hợp tới EventBridge. Ví dụ, phát hiện trail bị dừng:

~~~json
{
  "source": ["aws.cloudtrail"],
  "detail-type": ["AWS API Call via CloudTrail"],
  "detail": {
    "eventSource": ["cloudtrail.amazonaws.com"],
    "eventName": ["StopLogging"]
  }
}
~~~

Rule có thể route tới SNS, SQS, Lambda hoặc incident workflow. Để EventBridge nhận đúng loại event, trail phải đang logging management/data events tương ứng; network activity events cũng cần selector phù hợp. Với read-only management events, cấu hình rule state theo yêu cầu của EventBridge để rule match loại event đó.

EventBridge rule là đường xử lý event-driven; nó không thay thế S3 archive/retention của trail. Với các event cần lưu bằng chứng dài hạn, duy trì trail selectors và destination riêng.

### 11.2. CloudTrail + CloudWatch Logs

Dùng CloudWatch Logs khi cần alert gần thời gian thực dựa trên log delivery. Một metric filter có thể đếm event như `ConsoleLogin` failure hoặc `StopLogging`. Chọn filter pattern dựa trên JSON record thật, thử với event mẫu rồi mới tạo alarm.

Không dùng CloudWatch Logs retention làm archive duy nhất nếu policy yêu cầu lưu lâu dài và độc lập. S3 trail archive giúp tách retention và quyền quản trị khỏi log analysis workflow.

### 11.3. CloudTrail + Athena

Khi trail log nằm trong S3, có thể dùng Glue/Athena để phân tích theo account, Region, actor, event name và thời gian. Ví dụ câu hỏi:

- Role nào thực hiện `PutBucketPolicy` trong tuần qua?
- Có `ConsoleLogin` từ IP không quen thuộc không?
- Ai gọi `CreateAccessKey` hoặc `UpdateAssumeRolePolicy`?
- Những object prefix nào bị `DeleteObject` trong thời gian incident?
- Trail có bị dừng hoặc selector thay đổi trong kỳ audit không?

Tạo table theo cấu trúc CloudTrail log path và schema tương ứng. Partition theo account/Region/date để giảm dữ liệu scan và chi phí query.

### 11.4. CloudTrail Lake — lưu ý dành cho khách hàng hiện hữu

CloudTrail Lake event data store cung cấp SQL query trên event được ingest, lọc nhiều attributes, accounts/Regions và kết hợp các nguồn hỗ trợ. Tuy nhiên, AWS đã đóng CloudTrail Lake cho khách hàng mới từ ngày 31/05/2026. Khách hàng đã đăng ký trước ngày này có thể tiếp tục dùng event data stores hiện có; AWS chỉ cam kết critical bug fixes và security updates, đồng thời khuyến nghị migration sang Amazon CloudWatch.

Với organization event data store hiện hữu, AWS tiếp tục hỗ trợ hoạt động và mở rộng cho member accounts/Regions mới. Với account-level event data store, dữ liệu cho account hiện hữu tiếp tục được hỗ trợ, nhưng ingestion không mở rộng sang member accounts mới gia nhập organization. Kiểm tra loại event data store trước khi thêm account.

Với tài khoản mới, dùng trail để lưu CloudTrail logs vào S3, sau đó phân tích bằng Athena hoặc gửi event tới CloudWatch Logs để tìm kiếm/cảnh báo. Không lập kế hoạch triển khai mới dựa trên giả định có thể tạo CloudTrail Lake event data store.

Không nhầm Event history search với Lake query: Event history có một attribute filter và một Region/account; CloudTrail Lake (đối với khách hàng hiện hữu) cung cấp SQL query linh hoạt hơn nhưng ingestion/retention có chi phí.

## 12. Chi phí và tối ưu audit coverage

CloudTrail có các thành phần tính phí khác nhau. Event history viewing miễn phí; management events có một bản sao miễn phí theo cơ chế định giá CloudTrail; các bản sao bổ sung, data events, network activity events và Insights có thể phát sinh phí. CloudTrail Lake ingestion/storage/query áp dụng cho khách hàng hiện hữu. Giá cụ thể thay đổi theo Region và pricing option, nên kiểm tra AWS CloudTrail Pricing trước khi triển khai.

### 12.1. Những nguồn chi phí

- Data events có thể rất nhiều, nhất là S3 object reads/writes hoặc Lambda invocations.
- Network activity events được tính phí khi bật.
- Insights events có phí riêng; bật Insights cho cả trail và Lake có thể phát sinh phí ở cả hai nơi.
- S3 storage, request, replication, lifecycle retrieval và KMS request có thể tính phí.
- CloudWatch Logs ingestion/storage và metric filters có chi phí.
- Với khách hàng CloudTrail Lake hiện hữu, ingestion, retention và query phụ thuộc pricing option.
- Athena tính phí theo dữ liệu scan.

### 12.2. Tối ưu selectors mà không mất audit evidence

1. Phân loại resource theo độ nhạy cảm và yêu cầu compliance.
2. Bật data events cho bucket/prefix, Lambda function, table hoặc resource cần điều tra.
3. Dùng advanced selectors để giới hạn API name hoặc ARN prefix khi yêu cầu audit cho phép.
4. Không loại bỏ read events nếu cần điều tra data access hoặc reconnaissance.
5. Ghi nhận quyết định selector, owner, risk acceptance và thời điểm review.
6. Kiểm thử selector bằng event thực tế trên sandbox.
7. Theo dõi event volume và cost anomaly sau khi triển khai.

Không tối ưu bằng cách tắt management events toàn bộ, bỏ log delivery validation hoặc không ghi data events trên dữ liệu nhạy cảm mà không có đánh giá rủi ro. Coverage là yêu cầu kiểm soát; chi phí phải được tối ưu trong phạm vi coverage đã duyệt.

## 13. Runbook điều tra CloudTrail event

Ví dụ: Security team nhận cảnh báo một IAM role đã thay đổi bucket policy trên production S3 bucket.

### 13.1. Xác định phạm vi

1. Xác định account ID, Region, bucket ARN và thời điểm cảnh báo.
2. Xác định trail/event history coverage có bao gồm event type cần điều tra không.
3. Nếu event trong 90 ngày, bắt đầu từ Event history hoặc `lookup-events`.
4. Nếu event cũ hơn 90 ngày, tìm S3 archive/Athena hoặc CloudTrail Lake.
5. Nếu cần biết object-level access, xác minh data events đã được bật cho bucket/prefix.

### 13.2. Tìm event

~~~bash
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=PutBucketPolicy \
  --region ap-southeast-1 \
  --max-results 50
~~~

Mở event record và kiểm tra `userIdentity`, `eventTime`, `sourceIPAddress`, `userAgent`, `requestParameters`, `responseElements` và `errorCode`.

### 13.3. Correlate actor và change

- Nếu actor là assumed role, truy ngược role session name về pipeline/job/automation.
- Nếu actor là IAM user, xác minh owner, MFA context và access key lifecycle.
- Nếu actor là AWS service, kiểm tra service-linked role, service principal và workflow liên quan.
- So sánh bucket policy trước/sau bằng AWS Config hoặc configuration snapshot.
- Kiểm tra CloudTrail event cho `AssumeRole`, `UpdateAssumeRolePolicy`, `AttachRolePolicy` hoặc thay đổi credential gần thời điểm đó.
- Đối chiếu ticket/PR/deployment record để phân biệt thay đổi được duyệt và ngoài quy trình.

### 13.4. Contain và preserve evidence

Nếu thay đổi không được phép:

1. Theo incident response procedure, hạn chế quyền hoặc khôi phục bucket policy an toàn.
2. Bảo toàn CloudTrail event, S3 log files, digest files và CloudWatch logs liên quan.
3. Kiểm tra object-level data events nếu cần xác định ai đọc/xóa object.
4. Xác minh trail vẫn logging và S3 delivery không lỗi.
5. Ghi lại timeline, actor, resource, request ID, event ID, impact và remediation.
6. Re-run checks và xác nhận security posture đã phục hồi.

Không chỉnh sửa hoặc xóa log evidence để “dọn dẹp” sau incident. Giới hạn quyền truy cập bản sao bằng chứng và giữ theo retention/incident policy.

## 14. Bài thực hành trên AWS sandbox

### 14.1. Lab A — Tìm management event trong Event history

1. Dùng sandbox account và Region đã chọn.
2. Tạo một resource test, ví dụ S3 bucket hoặc Security Group.
3. Mở Event history và lọc theo Event source/Event name.
4. Tìm event tạo resource và ghi lại `eventTime`, `userIdentity`, `eventName`, `awsRegion`.
5. Chạy `aws cloudtrail lookup-events` với cùng điều kiện.
6. So sánh kết quả Console và CLI.
7. Thử bật Read only filter để thấy sự khác biệt giữa read/write events.

### 14.2. Lab B — Tạo multi-Region trail

1. Tạo S3 bucket archive riêng và áp dụng bucket policy cho CloudTrail.
2. Tạo multi-Region trail, bật global service events và log file validation.
3. Chạy `start-logging`.
4. Kiểm tra `get-trail`, `get-trail-status` và `get-event-selectors`.
5. Tạo một management event trong sandbox.
6. Xác minh log file được phân phối vào S3 theo account/Region/date path.
7. Bật CloudWatch Logs integration nếu lab yêu cầu và kiểm tra log group nhận event.

### 14.3. Lab C — Ghi S3 data events theo prefix

1. Tạo bucket sandbox có hai prefix `public-test/` và `sensitive-test/`.
2. Tạo advanced selector chỉ ghi `GetObject`/`PutObject` trên `sensitive-test/`.
3. Tải object lên cả hai prefix và đọc lại object.
4. Kiểm tra trail S3 log hoặc EventBridge event.
5. Xác nhận hoạt động trong prefix được chọn xuất hiện, còn prefix ngoài selector không được ghi theo selector đó.
6. Tính toán event volume và giải thích vì sao không nên bật mọi bucket/object nếu không cần.

### 14.4. Lab D — Network activity và VPC endpoint policy

1. Dùng sandbox VPC có interface/gateway endpoint phù hợp với service được CloudTrail network activity hỗ trợ.
2. Cấu hình endpoint policy thử nghiệm để từ chối một API request cụ thể.
3. Thêm advanced selector với `eventCategory = NetworkActivity`, `eventSource` tương ứng và `errorCode = VpceAccessDenied`.
4. Gọi API qua VPC endpoint.
5. Kiểm tra event có `eventType = AwsVpceEvent`, `vpcEndpointId` và error code tương ứng.
6. Sửa endpoint policy và xác minh request thành công.

Chỉ thử policy deny trong sandbox; không thay đổi endpoint policy production để làm lab.

### 14.5. Lab E — Điều tra Insights event

1. Chọn sandbox account có đủ baseline management event activity.
2. Bật API call rate hoặc API error rate Insights trên trail.
3. Chạy một workload test tạo mức API activity có kiểm soát.
4. Chờ CloudTrail xây dựng baseline và phát hiện anomaly nếu có.
5. Xem Insights event, baseline/insight average và supporting events.
6. Giải thích vì sao không nên xem Insights là real-time alarm hoặc kỳ vọng event xuất hiện ngay.

### 14.6. Lab F — Kiểm tra log file integrity

1. Tạo trail có log file validation enabled.
2. Chờ digest files được phân phối.
3. Dùng AWS CLI validate logs theo trail và time range của lab.
4. Đọc kết quả validation và ghi lại các file được xác minh.
5. Không sửa/xóa log hoặc digest trong bucket; chỉ thử trên bản sao test nếu muốn minh họa tampering detection.

## 15. Checklist review CloudTrail trước khi đưa vào production

### Coverage

- [ ] Event history đã được hiểu đúng là 90 ngày management events theo Region?
- [ ] Trail có multi-Region coverage cho các enabled Regions cần audit?
- [ ] Organization trail có bao phủ management/member accounts?
- [ ] Management events ghi read/write theo yêu cầu kiểm soát?
- [ ] Data events được bật cho resource/prefix nhạy cảm?
- [ ] Network activity events được bật cho VPC endpoint/service cần audit?
- [ ] Insights được bật nếu có use case và budget?
- [ ] Advanced/basic selectors đã được review để tránh vô tình ghi thiếu?

### Destination và delivery

- [ ] S3 bucket chuyên dụng, Block Public Access và bucket policy đúng?
- [ ] Bucket policy có `aws:SourceArn` giới hạn trail?
- [ ] S3/KMS encryption và key policy đã kiểm tra?
- [ ] `IsLogging` đang true và delivery errors được giám sát?
- [ ] CloudWatch Logs integration/role policy hoạt động nếu được dùng?
- [ ] EventBridge rules match đúng event type và event detail?
- [ ] Retention/lifecycle phù hợp với legal/compliance requirements?

### Integrity và access control

- [ ] Log file validation enabled?
- [ ] Digest files được lưu và không bị lifecycle xóa sớm?
- [ ] Quyền đọc/xóa/sửa archive được tách theo role?
- [ ] Có versioning/Object Lock nếu yêu cầu chống xóa/sửa?
- [ ] KMS key administration tách khỏi workload deployment role?
- [ ] Thay đổi trail, selectors, bucket policy và KMS key policy được audit?

### Operations và cost

- [ ] Có alert khi `StopLogging`, `DeleteTrail`, delivery failure hoặc selector change?
- [ ] Có quy trình xác minh trail coverage sau khi thêm account/Region/resource?
- [ ] Data/network/Insights events đã được tính cost và volume?
- [ ] Có Athena/Lake/SIEM query để hỗ trợ điều tra?
- [ ] Runbook nêu rõ cách tìm event, preserve evidence và correlate identity?
- [ ] Có owner và lịch review audit coverage?




## 16. Câu hỏi tự đánh giá

1. CloudTrail ghi nhận hoạt động gì trong AWS account?
2. Event history khác trail như thế nào?
3. Event history lưu những event type nào và trong bao lâu?
4. Vì sao Event history không đủ cho audit retention dài hạn?
5. Event history có thể query nhiều Region/account cùng lúc không?
6. Trail dùng để làm gì và log files được phân phối tới đâu?
7. CloudTrail Lake event data store khác trail ra sao?
8. Bốn loại CloudTrail events là gì?
9. Management events thuộc control plane hay data plane?
10. Read events và write events khác nhau thế nào?
11. Vì sao `GetObject` là data event nhưng `PutBucketPolicy` là management event?
12. Vì sao data events không xuất hiện trong Event history?
13. Network activity events ghi nhận loại hoạt động nào?
14. `VpceAccessDenied` biểu thị điều gì?
15. Insights API call rate và API error rate khác nhau thế nào?
16. `userIdentity` giúp trả lời câu hỏi điều tra nào?
17. `eventSource`, `eventName`, `awsRegion` và `eventTime` có ý nghĩa gì?
18. Vì sao không nên coi `requestParameters` là payload đầy đủ của ứng dụng?
19. Vì sao CloudTrail log file không phải stack trace được sắp thứ tự?
20. Khi nào nên chọn multi-Region trail?
21. Organization trail khác account trail thế nào?
22. Ai có thể tạo organization trail?
23. Basic event selectors hỗ trợ những data resource types phổ biến nào?
24. Advanced event selectors có lợi ích gì?
25. Vì sao không thể đồng thời áp dụng basic và advanced selectors cho một trail?
26. Vì sao cần kiểm tra selectors sau khi update?
27. S3 bucket policy cho CloudTrail cần những quyền chính nào?
28. `aws:SourceArn` giúp bảo vệ điều gì?
29. Log file integrity validation tạo digest file để làm gì?
30. Integrity validation có ngăn xóa log không?
31. Vì sao EventBridge không thay thế S3 trail archive?
32. Những loại event nào có thể phát sinh phí bổ sung?
33. Làm sao tối ưu data events mà vẫn giữ audit coverage?
34. Khi điều tra một thay đổi IAM, cần correlate những trường nào?

### Định hướng đáp án

- **Event history:** 90 ngày management events, theo account/Region, miễn phí để xem, chỉ một attribute filter và time range.
- **Trail:** ghi liên tục event đã chọn và phân phối log files tới S3; có thể gửi CloudWatch Logs và tích hợp EventBridge.
- **Event types:** Management là control plane; Data là resource/data plane; Network activity là API qua VPC endpoint; Insights phát hiện API rate/error anomaly.
- **Selectors:** Management events có All/Read/Write; data/network events phải được chọn rõ, advanced selectors cho filtering chi tiết.
- **Audit record:** `userIdentity`, `eventTime`, `eventSource`, `eventName`, `awsRegion`, `requestParameters`, `errorCode`, `resources`, `eventID`.
- **Integrity:** digest/signature giúp phát hiện thay đổi sau delivery; cần kết hợp S3 access control, retention, encryption và protection chống xóa.
- **Operations:** kiểm tra logging/delivery status, selectors, Region/account coverage, EventBridge alerts và chi phí.

## 17. Tài liệu AWS chính thức

1. [Working with CloudTrail Event history](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/view-cloudtrail-events.html) — Phạm vi 90 ngày, filter, limitations và tra cứu Event history.
2. [Understanding CloudTrail events](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-events.html) — Event categories, management/data/network/Insights events và record format.
3. [CloudTrail record contents](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-event-reference-record-contents.html) — Các field trong JSON event record.
4. [How CloudTrail works](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/how-cloudtrail-works.html) — Tổng quan Event history, trails, Lake và Insights.
5. [Creating a trail for your AWS account](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-create-and-update-a-trail.html) — Tạo trail, multi-Region và log delivery.
6. [Creating a trail for an organization](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/creating-trail-organization.html) — Organization trail và AWS Organizations.
7. [Organization delegated administrator](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-delegated-administrator.html) — Delegated administration cho trails và event data stores.
8. [Logging management events](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/logging-management-events-with-cloudtrail.html) — Control plane, read/write và management event selectors.
9. [Logging data events](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/logging-data-events-with-cloudtrail.html) — Data event resource types và selectors.
10. [Logging network activity events](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/logging-network-events-with-cloudtrail.html) — VPC endpoint activity và advanced selectors.
11. [Working with CloudTrail Insights](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/logging-insights-events-with-cloudtrail.html) — API call rate/error rate anomalies.
12. [PutEventSelectors API](https://docs.aws.amazon.com/awscloudtrail/latest/APIReference/API_PutEventSelectors.html) — Basic/advanced event selector API.
13. [Getting and viewing CloudTrail log files](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/get-and-view-cloudtrail-log-files.html) — S3 path, delivery và log file organization.
14. [Amazon S3 bucket policy for CloudTrail](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/create-s3-bucket-policy-for-cloudtrail.html) — S3 delivery permissions và aws:SourceArn.
15. [Enabling log file integrity validation](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-log-file-validation-enabling.html) — Bật digest/log validation.
16. [Validating CloudTrail log file integrity](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-log-file-validation-intro.html) — Digest files và validation concepts.
17. [Sending CloudTrail events to CloudWatch Logs](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/send-cloudtrail-events-to-cloudwatch-logs.html) — CloudWatch Logs integration.
18. [AWS service events delivered via CloudTrail to EventBridge](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-service-event-cloudtrail.html) — EventBridge rules cho CloudTrail events.
19. [AWS CloudTrail pricing](https://aws.amazon.com/cloudtrail/pricing/) — Pricing cho event types, trails và CloudTrail Lake.
20. [CloudTrail Lake availability change](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-lake-service-availability-change.html) — Đóng đăng ký cho khách hàng mới từ 31/05/2026 và phương án migration sang CloudWatch.

> **Ghi nhớ cuối bài:** Event history giúp tra cứu nhanh management events trong 90 ngày. Trail tạo bản ghi dài hạn ở S3 và có thể bao phủ nhiều Region/accounts. Management, data, network activity và Insights events có phạm vi khác nhau; data/network/Insights cần bật có chủ đích. Muốn audit đáng tin cậy, phải kết hợp selectors đúng, log delivery liên tục, identity correlation, integrity validation, retention và quyền truy cập archive được bảo vệ.





