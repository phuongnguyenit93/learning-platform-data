# CloudTrail Lake và điều tra hoạt động tài khoản

> **Chương:** Kiểm toán và tuân thủ  
> **Học phần:** `CLOUD_PROVIDERS_AWS` — khám phá hệ sinh thái AWS qua Region/AZ, IAM, VPC, dịch vụ tính toán, lưu trữ, cơ sở dữ liệu, tích hợp và serverless; rèn khả năng chọn dịch vụ, thiết kế và triển khai ứng dụng an toàn, có giám sát, phục hồi và kiểm soát chi phí.

Khi một tài khoản AWS có hàng trăm workload và nhiều người vận hành, câu hỏi quan trọng trong một sự cố thường là: **ai đã gọi API nào, vào thời điểm nào, từ đâu, trên tài nguyên nào và kết quả ra sao?** AWS CloudTrail ghi lại hoạt động API và hoạt động tài khoản. CloudTrail Lake bổ sung Event Data Store (EDS) và khả năng truy vấn SQL để phân tích sự kiện trên nhiều trường, nhiều tài khoản hoặc nhiều Region.

Bài học này hướng dẫn cách đọc cấu trúc CloudTrail event, tổ chức Event Data Store, chọn dữ liệu cần thu thập, truy vấn SQL và điều tra một chuỗi hoạt động đáng ngờ. Nội dung cũng giải thích quyền hạn, retention, chi phí, federation với Athena và quy trình chuyển dữ liệu sang kiến trúc được AWS khuyến nghị hiện nay.

> **Lưu ý về khả năng cung cấp dịch vụ (cập nhật ngày 20-11-2026):** AWS CloudTrail Lake đã ngừng mở cho khách hàng mới từ **31-05-2026**. Khách hàng đã sử dụng trước thời điểm đó tiếp tục dùng các Event Data Store hiện có; AWS cho biết CloudTrail Lake chỉ nhận critical bug fixes và security updates. AWS CloudTrail Trails, Event history, Insights và Aggregated Events vẫn được hỗ trợ. AWS khuyến nghị khách hàng chuyển sang Amazon CloudWatch để có năng lực thu thập, lưu trữ và phân tích tương tự. Vì vậy, phần CloudTrail Lake dưới đây phục vụ việc hiểu và vận hành các hệ thống hiện hữu; người học mới nên xem phần kiến trúc thay thế ở mục 17. [Thông báo khả năng cung cấp CloudTrail Lake](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-lake-service-availability-change.html).

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt CloudTrail Event history, Trail và CloudTrail Lake Event Data Store.
2. Giải thích management events, data events, network activity events và Insights events.
3. Đọc các trường quan trọng trong CloudTrail event để xác định actor, action, target, source và kết quả.
4. Hiểu cách EDS thu thập sự kiện bằng advanced event selectors.
5. Phân biệt account-level EDS và organization EDS trong AWS Organizations.
6. Viết SQL có giới hạn thời gian để tìm hoạt động IAM, đăng nhập, thay đổi tài nguyên và truy cập dữ liệu.
7. Xây dựng timeline và kiểm tra giả thuyết trong một cuộc điều tra.
8. Quản lý retention, ingestion, query cost, quyền truy cập và query results.
9. Hiểu federation sang AWS Glue, Lake Formation và Amazon Athena.
10. Lập kế hoạch bảo toàn bằng chứng và chuyển đổi sang Amazon CloudWatch khi phù hợp.

## 2. CloudTrail ghi lại điều gì?

AWS CloudTrail ghi lại hoạt động được thực hiện bởi user, role, AWS service hoặc workload thông qua AWS APIs và các nguồn sự kiện được hỗ trợ. Một event thường mô tả:

- **Who:** principal hoặc identity đã thực hiện hành động.
- **What:** API/action được gọi.
- **When:** thời điểm event xảy ra.
- **Where:** Region và địa chỉ nguồn.
- **On what:** resource hoặc đối tượng bị tác động.
- **Outcome:** thành công hay thất bại, error code/message nếu có.

Ví dụ, khi một role gọi `iam:CreateAccessKey`, CloudTrail có thể ghi `eventSource`, `eventName`, `userIdentity`, `sourceIPAddress`, `requestParameters`, `responseElements` và `eventTime`. Những trường này cho phép điều tra ai tạo access key, cho IAM user nào và trong phiên đăng nhập nào.

### 2.1. CloudTrail Event history

Event history là giao diện tra cứu management events gần đây trong một account và một Region. Event history:

- Có sẵn mà không cần tạo Trail.
- Hiển thị management events trong 90 ngày gần nhất.
- Tìm kiếm theo một số thuộc tính đơn giản như event name, user name hoặc resource.
- Phù hợp với kiểm tra nhanh một thao tác vừa xảy ra.

Event history không phải kho phân tích dài hạn, không thay thế data event logging và không hỗ trợ truy vấn SQL đa trường trên nhiều account/Region.

### 2.2. CloudTrail Trail

Trail cấu hình việc thu thập và phân phối CloudTrail events tới Amazon S3; có thể tích hợp CloudWatch Logs và các dịch vụ khác. Trail phù hợp để:

- Lưu bản ghi lâu dài trong S3.
- Tập trung log nhiều account bằng organization trail.
- Phân tích bằng Athena, SIEM hoặc pipeline xử lý.
- Thiết lập log file validation và bảo vệ bucket theo yêu cầu.

Trail có thể là single-Region hoặc multi-Region. Với môi trường production, multi-Region trail thường là baseline tốt để tránh bỏ sót hoạt động ở Region khác. Cần xem xét cả opt-in Regions và AWS partitions đang sử dụng.

### 2.3. CloudTrail Lake Event Data Store

CloudTrail Lake là dịch vụ phân tích được xây dựng quanh Event Data Store. EDS thu thập các event categories được chọn, giữ dữ liệu theo retention đã cấu hình và cho phép truy vấn bằng SQL.

Một EDS có thể tập trung sự kiện từ nhiều account/Region (tùy loại EDS và cấu hình), đồng thời hỗ trợ truy vấn nhiều trường và kết hợp các EDS theo khả năng SQL được hỗ trợ. CloudTrail Lake không yêu cầu phải có Trail riêng để ingest sự kiện vào EDS.

### 2.4. So sánh nhanh

| Cơ chế | Mục đích | Phạm vi và truy vấn |
| --- | --- | --- |
| Event history | Tra cứu nhanh hoạt động gần đây | 90 ngày management events, account/Region hiện tại |
| Trail → S3 | Thu thập và lưu trữ audit log lâu dài | Multi-Region/organization; phân tích bằng Athena hoặc công cụ khác |
| CloudTrail Lake EDS | Kho event có SQL query tích hợp | Nhiều loại event, retention và selectors theo EDS |
| CloudWatch architecture | Kiến trúc AWS khuyến nghị thay thế CloudTrail Lake cho khách hàng mới | Tập trung security/operations/compliance telemetry và analytics |

Không nên coi các cơ chế này là loại trừ lẫn nhau. Một tổ chức có thể dùng Trail để lưu bản ghi trong S3, Event history để kiểm tra nhanh và một nền tảng analytics để điều tra dài hạn.

## 3. Các loại CloudTrail events

Chọn đúng event category là bước đầu tiên của một hệ thống audit có ích. Bỏ sót event cần thiết thì không có truy vấn nào khôi phục được hoạt động chưa từng được ghi.

### 3.1. Management events

Management events (control plane events) ghi lại thao tác quản lý tài nguyên AWS, ví dụ:

- `CreateRole`, `AttachRolePolicy`, `PutRolePolicy` trong IAM.
- `RunInstances`, `AuthorizeSecurityGroupIngress`, `CreateVpc` trong EC2/VPC.
- `CreateBucket`, `PutBucketPolicy` trong S3 control plane.
- `CreateFunction`, `UpdateFunctionConfiguration` trong Lambda.
- `CreateTrail`, `StopLogging`, `DeleteEventDataStore` trong CloudTrail.

Management events thường được thu thập mặc định bởi CloudTrail. Chúng có thể là read-only hoặc write management events. Read-only event như `DescribeInstances` giúp hiểu hoạt động truy vấn; write event như `ModifySecurityGroupRules` giúp phát hiện thay đổi cấu hình.

### 3.2. Data events

Data events ghi lại thao tác trên dữ liệu hoặc bên trong resource, ví dụ:

- Đọc/ghi object trong S3: `GetObject`, `PutObject`, `DeleteObject`.
- Invoke Lambda function.
- Đọc/ghi item trong DynamoDB khi cấu hình hỗ trợ.
- Một số hoạt động dữ liệu của các dịch vụ được CloudTrail hỗ trợ.

Data events thường có volume lớn và có thể phát sinh phí. Không nên bật mọi data event trên mọi resource nếu không có use case. Hãy xác định bucket, function, table hoặc resource nhạy cảm cần audit; chọn read/write operations và selector cụ thể.

### 3.3. Network activity events

Network activity events ghi lại một số hoạt động network được CloudTrail hỗ trợ, thường liên quan đến VPC endpoint policy hoặc hoạt động truy cập qua endpoint. Đây không phải bản thay thế VPC Flow Logs. Network activity event có thể giúp điều tra API/network access trong phạm vi dịch vụ hỗ trợ; VPC Flow Logs vẫn cần thiết cho phân tích network flow.

### 3.4. CloudTrail Insights events

CloudTrail Insights phát hiện một số hoạt động API bất thường so với baseline, chẳng hạn thay đổi đột biến về API call rate hoặc error rate. Insights events là tín hiệu để điều tra sâu hơn; chúng không chứng minh một hành động là độc hại.

Khi thấy Insights event:

1. Xác định event type/insight source và khoảng thời gian bất thường.
2. Truy vấn management events liên quan trong cùng khoảng thời gian.
3. So sánh actor, source IP, user agent, Region và resource.
4. Kiểm tra change window, deployment hoặc hoạt động vận hành hợp lệ.
5. Mở rộng sang VPC Flow Logs, GuardDuty, IAM Access Analyzer hoặc workload logs nếu cần.

### 3.5. Event category và event type

`eventCategory` phân biệt các nhóm sự kiện như `Management`, `Data`, `NetworkActivity`, `Insight` hoặc `ConfigurationItem` tùy loại EDS. `eventType` mô tả loại event chi tiết hơn, ví dụ `AwsApiCall` hoặc một loại service event. Không nhầm `eventCategory` với `eventSource`: category mô tả nhóm, còn source cho biết dịch vụ tạo API event.

## 4. Đọc cấu trúc CloudTrail event

Một CloudTrail event là JSON record. Các trường thường dùng khi điều tra:

| Trường | Ý nghĩa | Câu hỏi hỗ trợ |
| --- | --- | --- |
| `eventTime` | Thời điểm sự kiện xảy ra | Sự kiện xảy ra khi nào? |
| `eventSource` | Dịch vụ nhận API request | API thuộc dịch vụ nào? |
| `eventName` | Tên API/action | Người gọi đã làm gì? |
| `awsRegion` | Region xử lý request | Hoạt động diễn ra ở đâu? |
| `userIdentity` | Identity thực hiện request | Ai hoặc role nào thực hiện? |
| `sourceIPAddress` | Địa chỉ nguồn request | Request đến từ đâu? |
| `userAgent` | Client/SDK/console context | Công cụ nào phát request? |
| `requestParameters` | Tham số request | Tài nguyên/giá trị nào được yêu cầu? |
| `responseElements` | Phần response được ghi lại | API trả về kết quả gì? |
| `errorCode`, `errorMessage` | Thông tin lỗi | Request thất bại vì sao? |
| `resources` | Resource liên quan nếu được ghi | Đối tượng nào bị tác động? |
| `eventID` | ID duy nhất của event | Dùng định danh event khi đối chiếu |
| `requestID` | Request ID của dịch vụ | Hỗ trợ đối chiếu với service/support logs |

### 4.1. Ví dụ event đã rút gọn

~~~json
{
  "eventVersion": "1.09",
  "userIdentity": {
    "type": "AssumedRole",
    "principalId": "AROAEXAMPLE:deployment-session",
    "arn": "arn:aws:sts::111122223333:assumed-role/DeploymentRole/deployment-session",
    "accountId": "111122223333",
    "sessionContext": {
      "sessionIssuer": {
        "type": "Role",
        "arn": "arn:aws:iam::111122223333:role/DeploymentRole",
        "userName": "DeploymentRole"
      },
      "attributes": {
        "mfaAuthenticated": "true"
      }
    }
  },
  "eventTime": "2026-11-20T03:15:22Z",
  "eventSource": "iam.amazonaws.com",
  "eventName": "AttachRolePolicy",
  "awsRegion": "ap-southeast-1",
  "sourceIPAddress": "198.51.100.25",
  "userAgent": "aws-cli/2.x",
  "requestParameters": {
    "roleName": "ApplicationRole",
    "policyArn": "arn:aws:iam::aws:policy/AdministratorAccess"
  },
  "responseElements": null,
  "requestID": "example-request-id",
  "eventID": "example-event-id",
  "readOnly": false,
  "eventType": "AwsApiCall",
  "managementEvent": true,
  "recipientAccountId": "111122223333",
  "eventCategory": "Management"
}
~~~

Trong ví dụ này, một assumed role đã gắn AWS managed policy `AdministratorAccess` vào `ApplicationRole`. Đây là thay đổi quyền có mức ảnh hưởng cao. Điều tra viên nên xác định ai assume `DeploymentRole`, phiên đăng nhập có được phê duyệt không, thay đổi có thuộc deployment window không và role nào đã được cấp quyền mới.

### 4.2. Phân biệt actor và role được assume

Khi `userIdentity.type` là `AssumedRole`, ARN thường có dạng:

~~~text
arn:aws:sts::<account-id>:assumed-role/<role-name>/<session-name>
~~~

`userIdentity.arn` xác định assumed-role session. `userIdentity.sessionContext.sessionIssuer.arn` xác định IAM role đã phát hành credentials. Nếu có `sourceIdentity`, `onBehalfOf`, `inScopeOf` hoặc session tags, các trường đó có thể cung cấp thêm ngữ cảnh về người dùng gốc, workload hoặc phiên được ủy quyền.

Không kết luận rằng role name là con người thực hiện hành động. Role có thể được assume bởi người dùng IAM Identity Center, automation, Lambda, EC2, CI/CD hoặc một AWS service.

### 4.3. Những giới hạn khi đọc event

- Không phải mọi API đều trả đầy đủ `requestParameters`/`responseElements`.
- Một số trường có thể bị loại bỏ hoặc ẩn vì lý do bảo mật.
- `sourceIPAddress` có thể là địa chỉ AWS service, proxy, NAT, endpoint hoặc client; không tự động quy về vị trí địa lý của người dùng.
- `userAgent` là một tín hiệu, không phải bằng chứng xác thực tuyệt đối.
- `eventTime` là thời điểm sự kiện; thời điểm log được ingest hoặc phân phối có thể muộn hơn.
- Event schema có thể bổ sung trường mới; parser nên bỏ qua trường chưa biết và kiểm tra major version theo khuyến nghị AWS.

## 5. Event Data Store và advanced event selectors

Event Data Store là kho event được CloudTrail Lake quản lý. Khi tạo EDS, chọn event category, nguồn, phạm vi account/Region, selector và retention. EDS thu thập những sự kiện khớp cấu hình; nó không tự chứa toàn bộ lịch sử đã xảy ra trước thời điểm tạo.

### 5.1. Những loại EDS thường gặp

Tùy nhu cầu, EDS có thể được tạo cho:

- CloudTrail management events.
- CloudTrail data events.
- CloudTrail network activity events.
- CloudTrail Insights events.
- AWS Config configuration items.
- Events ngoài AWS từ ứng dụng hoặc tích hợp đối tác được hỗ trợ.

Mỗi loại EDS có schema và event categories riêng. Không thể giả định một EDS sẽ gom mọi loại dữ liệu không tương thích vào cùng một schema.

### 5.2. Advanced event selectors

Advanced event selectors cho phép lọc theo trường và điều kiện, ví dụ:

- `eventCategory`.
- `eventSource`.
- `eventName`.
- `resources.type`.
- `resources.ARN`.
- `readOnly`.
- `userIdentity.arn`.
- `eventType`.

Ví dụ, một EDS dành cho data events của một S3 bucket có thể chỉ chọn object operations của bucket đó:

~~~json
[
  {
    "Name": "Sensitive bucket object events",
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
          "arn:aws:s3:::company-sensitive-data/"
        ]
      }
    ]
  }
]
~~~

Đây là ví dụ minh họa selector; xác nhận field, operator và resource ARN pattern được hỗ trợ cho event source cụ thể trước khi áp dụng. Nếu cần cả read và write data events, đừng lọc chỉ một chiều bằng `readOnly`.

### 5.3. Chọn dữ liệu theo mục tiêu điều tra

| Mục tiêu | Event types/selectors nên cân nhắc |
| --- | --- |
| Điều tra thay đổi IAM | Management events của `iam.amazonaws.com`, gồm write và các read events cần thiết |
| Điều tra đăng nhập | Sign-in/STS management events và các trường identity/session |
| Điều tra thay đổi network | EC2/VPC management events; bổ sung VPC Flow Logs cho traffic |
| Điều tra đọc/xóa object | S3 data events cho bucket/prefix nhạy cảm |
| Điều tra Lambda invocation | Lambda data events nếu cần audit invocation |
| Điều tra bất thường API | Management events và Insights events khi tính năng phù hợp |

Không chọn selector quá hẹp đến mức bỏ mất chuỗi sự kiện cần điều tra. Ví dụ chỉ thu thập `PutBucketPolicy` có thể bỏ qua `GetBucketPolicy` hoặc các thay đổi IAM trước đó tạo ra quyền truy cập.

### 5.4. EDS không tự hồi tố dữ liệu

EDS bắt đầu ingest từ khi được cấu hình. Nếu cần phân tích lịch sử đã được ghi bởi Trail, khách hàng CloudTrail Lake hiện hữu có thể copy trail events vào EDS theo quy trình AWS hỗ trợ. Việc copy có thể phát sinh phí ingestion, phụ thuộc dữ liệu trong S3, quyền truy cập bucket/KMS và retention của EDS.

## 6. Account-level và organization Event Data Store

Với AWS Organizations, cần xác định EDS thuộc một account hay áp dụng cho toàn organization.

### 6.1. Account-level EDS

Account-level EDS thu thập sự kiện cho account sở hữu EDS theo cấu hình. Nó phù hợp khi:

- Một account độc lập cần kho điều tra riêng.
- Workload/team có ownership và retention riêng.
- Phạm vi dữ liệu không cần hợp nhất toàn organization.

### 6.2. Organization EDS

Organization EDS được tạo bởi management account hoặc delegated administrator được phép. Khi áp dụng cho organization, EDS tự động bao phủ các member accounts theo cấu hình và có thể thu thập nhiều Region.

Member accounts không trực tiếp nhìn thấy, sửa hoặc xóa organization EDS. Quyền truy vấn cần được cấp riêng; mặc định member account không có quyền query EDS của organization.

~~~mermaid
flowchart TD
    ORG["AWS Organizations"]
    ORG --> MGMT["Management account"]
    ORG --> A["Member account A"]
    ORG --> B["Member account B"]
    ORG --> C["Member account C"]
    MGMT --> EDS["Organization Event Data Store"]
    A --> EDS
    B --> EDS
    C --> EDS
    EDS --> QUERY["Central investigation queries"]
~~~

### 6.3. Management account và delegated administrator

Management account giữ ownership của organization EDS. Delegated administrator có thể thực hiện nhiều thao tác quản trị và query theo quyền AWS quy định, nhưng một số thao tác chỉ management account được làm, ví dụ copy trail events vào organization EDS và một số thao tác chuyển đổi loại EDS.

Thiết kế delegated administrator theo least privilege. Không cấp quyền organization-wide chỉ vì một team cần chạy một vài truy vấn.

### 6.4. Lưu ý quan trọng sau ngày 31-05-2026

AWS thông báo rằng khách hàng hiện hữu tiếp tục được hỗ trợ EDS hiện có. Tuy nhiên, nếu organization chỉ có account-level EDS, CloudTrail Lake không ingest cho member accounts mới được thêm sau mốc đóng khách hàng mới. Muốn bao phủ account mới, tổ chức hiện hữu cần có organization EDS hoặc chuyển sang kiến trúc Amazon CloudWatch được AWS khuyến nghị. Đừng giả định account-level EDS tự mở rộng cho mọi account gia nhập organization sau mốc này.

## 7. Tạo và cấu hình Event Data Store

Phần này dành cho account đã có quyền sử dụng CloudTrail Lake. Trước khi tạo EDS, xác định rõ:

- Dữ liệu nào cần điều tra và event category nào cần thu thập.
- Account/Region nào thuộc phạm vi.
- Selector nào giữ đủ evidence nhưng không ingest dữ liệu không cần thiết.
- Retention period và pricing option.
- Ai được tạo, sửa, query và xóa EDS.
- Có cần organization EDS, federation hoặc resource-based access không.

### 7.1. Tạo EDS cho management events bằng AWS CLI

~~~bash
aws cloudtrail create-event-data-store \
  --name security-management-events \
  --advanced-event-selectors '[{"Name":"Management events","FieldSelectors":[{"Field":"eventCategory","Equals":["Management"]}]}]' \
  --multi-region-enabled \
  --retention-period 366 \
  --billing-mode EXTENDABLE_RETENTION_PRICING \
  --termination-protection-enabled \
  --region ap-southeast-1
~~~

Ví dụ này minh họa account-level EDS cho management events trên nhiều Region, với retention mặc định 366 ngày theo pricing option extendable. Hãy kiểm tra các CLI options được hỗ trợ trong account/Region và giá hiện hành trước khi chạy. Không dùng lệnh tạo EDS như hướng dẫn đăng ký dịch vụ cho khách hàng mới sau ngày 31-05-2026.

### 7.2. Tạo EDS cho data events

Một EDS có thể dùng advanced selectors để thu thập data events cho resource cần audit. Ví dụ JSON selector ở mục 5.2 có thể được truyền vào `--advanced-event-selectors`. Khi thiết kế, xác minh:

- Resource ARN và event source chính xác.
- Chọn read, write hay cả hai.
- Selector có loại trừ nhầm hoạt động hợp lệ cần điều tra không.
- Volume dự kiến có phù hợp với ngân sách không.
- Data event coverage của service/Region có đáp ứng yêu cầu không.

### 7.3. Tạo organization EDS

Với tổ chức đã sử dụng CloudTrail Lake, management account hoặc delegated administrator có thể tạo organization EDS bằng `--organization-enabled` theo quyền AWS quy định. Ví dụ khái quát:

~~~bash
aws cloudtrail create-event-data-store \
  --name organization-management-events \
  --organization-enabled \
  --multi-region-enabled \
  --retention-period 366 \
  --billing-mode EXTENDABLE_RETENTION_PRICING \
  --termination-protection-enabled \
  --region ap-southeast-1
~~~

Ví dụ trên minh họa cấu hình management events mặc định. Nếu cần data events, network activity events hoặc Insights, thêm event selectors phù hợp. Organization EDS được sở hữu ở management account kể cả khi delegated administrator khởi tạo.

### 7.4. Kiểm tra EDS đã tạo

~~~bash
aws cloudtrail list-event-data-stores \
  --region ap-southeast-1

aws cloudtrail get-event-data-store \
  --event-data-store <event-data-store-arn-or-id> \
  --region ap-southeast-1
~~~

Kiểm tra status, ARN, organization setting, multi-Region setting, advanced selectors, retention, billing mode, termination protection và ingestion status. Ghi lại EDS ARN/ID trong inventory vận hành.

### 7.5. Ingestion status và termination protection

EDS có thể được cấu hình để bắt đầu hoặc dừng ingest events. Dừng ingestion không xóa dữ liệu đã có; nó ngăn EDS tiếp tục nhận events mới. Termination protection giúp ngăn xóa EDS ngoài ý muốn, đặc biệt với kho audit trung tâm.

Không dừng ingestion trong incident chỉ để giảm chi phí mà chưa đánh giá tác động: việc dừng có thể tạo khoảng trống audit đúng lúc cần bằng chứng. Nếu cần giảm chi phí, review selectors và event volume theo change plan.

## 8. Retention, pricing và kiểm soát chi phí

CloudTrail Lake có chi phí ingestion, retention và query. Chi phí phụ thuộc event volume/type, pricing option, thời gian lưu giữ và lượng dữ liệu query scan. Không có một con số cố định áp dụng cho mọi Region và mọi loại event.

### 8.1. Hai pricing options

CloudTrail Lake có hai lựa chọn retention pricing:

| Pricing option | Đặc điểm | Khi nào cân nhắc |
| --- | --- | --- |
| One-year extendable retention | Bao gồm giai đoạn lưu trữ ban đầu một năm; có thể kéo dài retention tới khoảng 10 năm theo giới hạn dịch vụ | Workload ingest thấp hơn khoảng 25 TB/tháng và cần retention linh hoạt |
| Seven-year retention | Bao gồm retention dài hạn khoảng 7 năm; không mở rộng vượt giới hạn option | Workload ingest lớn hơn khoảng 25 TB/tháng và cần retention dài hạn |

Các ngưỡng/retention trên là hướng dẫn theo pricing model của AWS tại thời điểm biên soạn. Xem trang giá hiện hành trước khi quyết định; retention period tối thiểu của EDS là 7 ngày và giá được tính theo loại dữ liệu/volume.

### 8.2. Những nguồn chi phí

- **Ingestion:** dữ liệu được ingest vào EDS.
- **Retention:** dung lượng dữ liệu được lưu theo pricing option và retention period.
- **Query:** lượng dữ liệu được quét bởi SQL query.
- **Federation:** bản thân bật federation không tính phí CloudTrail Lake; query chạy trên Athena có chi phí Athena.
- **Historical copy:** copy trail events vào EDS tính theo dung lượng uncompressed được ingest.

Không giả định gzip object size trong S3 bằng dung lượng CloudTrail Lake ingestion. Khi copy trail events, dữ liệu được giải nén; AWS đưa ra ước lượng sơ bộ rằng dung lượng uncompressed có thể lớn hơn nhiều so với object đã nén.

### 8.3. Giảm chi phí bằng selector

- Thu thập data events cho bucket/table/function quan trọng.
- Chỉ bật event sources cần cho use case.
- Tránh ingest mọi resource của mọi account nếu không cần.
- Review selectors định kỳ khi workload thay đổi.
- Dùng organization EDS khi cần coverage tập trung và phù hợp quyền/khả năng sẵn có.
- Tách kho điều tra ngắn hạn với kho lưu trữ dài hạn nếu kiến trúc và policy yêu cầu.

### 8.4. Giảm chi phí query

- Luôn lọc `eventTime` theo khoảng thời gian cụ thể.
- Chỉ chọn cột cần thiết thay vì `SELECT *`.
- Thêm điều kiện `eventSource`, `eventName`, `awsRegion`, `userIdentity.arn` để thu hẹp tập kết quả.
- Bắt đầu với time window nhỏ, sau đó mở rộng khi giả thuyết cần thiết.
- Xem `BytesScanned` và runtime trong query metadata.
- Tránh chạy lặp query toàn kho trong dashboard hoặc automation.

Điều kiện `eventTime` giúp giảm scan theo best effort; không bảo đảm mọi query đều chỉ đọc dữ liệu trong time range. Một số query vẫn có thể scan nhiều dữ liệu hơn dự kiến.

### 8.5. Retention và historical copy

Khi copy historical trail events vào EDS, CloudTrail chỉ copy events có `eventTime` nằm trong retention period của EDS. Nếu muốn copy event cũ 45 ngày và tiếp tục giữ thêm 45 ngày sau khi copy, retention phải đủ bao phủ cả tuổi dữ liệu tại thời điểm copy và thời gian muốn giữ tiếp.

Nếu EDS chỉ dùng để phân tích lịch sử, có thể tắt ingest events mới sau khi copy hoàn tất để tránh phát sinh ingestion ngoài mục tiêu. Kiểm tra thời gian copy, trạng thái failed records và tránh copy trùng khoảng thời gian đã được ingest trực tiếp.

## 9. CloudTrail Lake SQL: cấu trúc và quy tắc

CloudTrail Lake query dùng SQL với cú pháp dựa trên Trino. Chỉ các câu lệnh `SELECT` được phép; query không thể thay đổi hoặc xóa dữ liệu trong EDS.

Khung query:

~~~sql
SELECT
    eventTime,
    eventSource,
    eventName,
    userIdentity.arn AS actor
FROM
    event-data-store-id
WHERE
    eventTime >= TIMESTAMP '2026-11-20 00:00:00'
    AND eventTime < TIMESTAMP '2026-11-21 00:00:00'
ORDER BY
    eventTime DESC
LIMIT 100;
~~~

Thay `event-data-store-id` bằng ID (phần cuối ARN) của EDS. CloudTrail console thường tự điền FROM khi bạn chọn EDS trong query editor.

### 9.1. Giới hạn SQL

- Chỉ dùng SELECT statements.
- Dùng cú pháp và hàm được CloudTrail Lake hỗ trợ; không giả định mọi Trino features đều có sẵn.
- `FROM` chỉ định EDS ID; có thể query nhiều EDS bằng các JOIN được hỗ trợ khi cần.
- Dùng `LIMIT` để tránh trả về kết quả quá lớn.
- Dùng `eventTime` để giới hạn thời gian; EDS có retention tối thiểu 7 ngày nên time window hợp lệ cũng cần lưu ý.
- Các trường nested như `userIdentity.arn` có thể được truy cập theo schema event.

### 9.2. Chọn đúng trường thời gian

`eventTime` là thời điểm AWS API event xảy ra. Khi điều tra, hãy dùng nó làm trục thời gian chính. Không nhầm với thời điểm object được giao vào S3, thời điểm ingest vào EDS hoặc thời điểm query chạy.

Các timestamp trong CloudTrail thường được biểu diễn theo UTC. Chuyển sang múi giờ của incident timeline một cách nhất quán và ghi rõ timezone.

### 9.3. Query có thể bị timeout hoặc trả quá nhiều dữ liệu

Query kéo dài hơn giới hạn runtime có thể timeout; một số trường hợp vẫn có partial results. Query trả quá nhiều dòng hoặc aggregation quá lớn có thể gặp lỗi response size/resource exhaustion. Chia time range nhỏ hơn, chọn ít cột hơn và tổng hợp sớm.

## 10. Các truy vấn điều tra thường dùng

Các query sau là mẫu cho EDS đã thu thập đúng event category. Thay EDS ID, account, Region, actor và time window bằng dữ liệu của incident. Tên trường/case và nested field cần khớp schema của EDS.

### 10.1. Liệt kê hoạt động của một principal

~~~sql
SELECT
    eventTime,
    eventSource,
    eventName,
    awsRegion,
    sourceIPAddress,
    userAgent,
    errorCode,
    eventID
FROM
    event-data-store-id
WHERE
    eventTime >= TIMESTAMP '2026-11-20 00:00:00'
    AND eventTime < TIMESTAMP '2026-11-21 00:00:00'
    AND userIdentity.arn =
        'arn:aws:sts::111122223333:assumed-role/DeploymentRole/deployment-session'
ORDER BY
    eventTime DESC
LIMIT 500;
~~~

Dùng query này để dựng danh sách hoạt động của một session. Nếu ARN session thay đổi, tìm thêm theo role issuer ARN hoặc principal ID; không giả định một người dùng luôn dùng cùng session name.

### 10.2. Tìm console login thành công và thất bại

~~~sql
SELECT
    eventTime,
    userIdentity.type,
    userIdentity.arn,
    sourceIPAddress,
    userAgent,
    responseElements,
    errorCode,
    errorMessage
FROM
    event-data-store-id
WHERE
    eventTime >= TIMESTAMP '2026-11-20 00:00:00'
    AND eventTime < TIMESTAMP '2026-11-21 00:00:00'
    AND eventSource = 'signin.amazonaws.com'
    AND eventName = 'ConsoleLogin'
ORDER BY
    eventTime DESC
LIMIT 500;
~~~

`ConsoleLogin` thường có trường trạng thái trong response hoặc error fields tùy kết quả. Kiểm tra cả `responseElements.ConsoleLogin` và `errorMessage` nếu có; không kết luận mọi event không có `errorCode` đều là login thành công nếu schema/context chưa được kiểm tra.

### 10.3. Tìm hoạt động tạo hoặc thay đổi IAM privilege

~~~sql
SELECT
    eventTime,
    userIdentity.arn AS actor,
    eventName,
    requestParameters,
    responseElements,
    sourceIPAddress,
    userAgent,
    errorCode
FROM
    event-data-store-id
WHERE
    eventTime >= TIMESTAMP '2026-11-19 00:00:00'
    AND eventTime < TIMESTAMP '2026-11-21 00:00:00'
    AND eventSource = 'iam.amazonaws.com'
    AND eventName IN (
        'CreateAccessKey',
        'CreateLoginProfile',
        'CreatePolicy',
        'CreatePolicyVersion',
        'AttachRolePolicy',
        'AttachUserPolicy',
        'PutRolePolicy',
        'PutUserPolicy',
        'AddUserToGroup',
        'UpdateAssumeRolePolicy'
    )
ORDER BY
    eventTime DESC
LIMIT 1000;
~~~

Tập trung vào thay đổi quyền có thể mở rộng privilege. Đọc `requestParameters` để xác định policy/role/user; nếu có `policyArn` hoặc policy document, so sánh với baseline được phê duyệt.

### 10.4. Điều tra AssumeRole

~~~sql
SELECT
    eventTime,
    userIdentity.arn AS caller,
    userIdentity.type AS callerType,
    requestParameters.roleArn AS targetRole,
    requestParameters.roleSessionName AS sessionName,
    requestParameters.externalId AS externalId,
    sourceIPAddress,
    userAgent,
    errorCode
FROM
    event-data-store-id
WHERE
    eventTime >= TIMESTAMP '2026-11-20 00:00:00'
    AND eventTime < TIMESTAMP '2026-11-21 00:00:00'
    AND eventSource = 'sts.amazonaws.com'
    AND eventName = 'AssumeRole'
ORDER BY
    eventTime DESC
LIMIT 500;
~~~

Query này tìm các lần assume role. Để theo dõi hành động sau khi assume, query tiếp theo cần tìm các events có assumed-role ARN/principal ID tương ứng trong `userIdentity`.

### 10.5. Tìm thay đổi security group

~~~sql
SELECT
    eventTime,
    userIdentity.arn AS actor,
    eventName,
    requestParameters,
    sourceIPAddress,
    awsRegion,
    errorCode
FROM
    event-data-store-id
WHERE
    eventTime >= TIMESTAMP '2026-11-20 00:00:00'
    AND eventTime < TIMESTAMP '2026-11-21 00:00:00'
    AND eventSource = 'ec2.amazonaws.com'
    AND eventName IN (
        'AuthorizeSecurityGroupIngress',
        'AuthorizeSecurityGroupEgress',
        'RevokeSecurityGroupIngress',
        'RevokeSecurityGroupEgress',
        'ModifySecurityGroupRules'
    )
ORDER BY
    eventTime DESC
LIMIT 500;
~~~

Kiểm tra CIDR, port range, protocol và security group ID trong request parameters. Một rule `0.0.0.0/0` mở cổng quản trị hoặc database cần được xác minh khẩn cấp.

### 10.6. Tìm truy cập S3 object

~~~sql
SELECT
    eventTime,
    userIdentity.arn AS actor,
    eventName,
    requestParameters.bucketName,
    requestParameters.key,
    sourceIPAddress,
    userAgent,
    errorCode
FROM
    event-data-store-id
WHERE
    eventTime >= TIMESTAMP '2026-11-20 00:00:00'
    AND eventTime < TIMESTAMP '2026-11-21 00:00:00'
    AND eventSource = 's3.amazonaws.com'
    AND eventCategory = 'Data'
    AND eventName IN ('GetObject', 'PutObject', 'DeleteObject')
ORDER BY
    eventTime DESC
LIMIT 1000;
~~~

Query này chỉ trả kết quả nếu EDS đã ingest S3 data events tương ứng. Management events của S3 không đủ để chứng minh ai đã đọc object.

### 10.7. Tìm API calls thất bại

~~~sql
SELECT
    eventTime,
    userIdentity.arn AS actor,
    eventSource,
    eventName,
    sourceIPAddress,
    errorCode,
    errorMessage
FROM
    event-data-store-id
WHERE
    eventTime >= TIMESTAMP '2026-11-20 00:00:00'
    AND eventTime < TIMESTAMP '2026-11-21 00:00:00'
    AND errorCode IS NOT NULL
ORDER BY
    eventTime DESC
LIMIT 500;
~~~

Lỗi có thể là hoạt động hợp lệ như policy evaluation deny, resource không tồn tại hoặc quota. Gom nhóm theo actor, source, API và error code trước khi kết luận hành vi tấn công.

## 11. Dựng timeline và tương quan sự kiện

Một event riêng lẻ hiếm khi kể đủ câu chuyện. Điều tra tốt cần kết hợp nhiều events theo actor, session, resource và thời gian.

### 11.1. Bắt đầu từ event đáng ngờ

Khi phát hiện một thay đổi nhạy cảm, ghi lại:

- `eventID`, `requestID` và `eventTime`.
- `eventSource`, `eventName`, `awsRegion`.
- `userIdentity.type`, `userIdentity.arn`, `principalId`.
- `sessionContext.sessionIssuer.arn` nếu có.
- `sourceIPAddress`, `userAgent`.
- `requestParameters`, `responseElements`, `errorCode`.
- Resource ARN/ID bị tác động.

Đây là điểm neo để mở rộng truy vấn. Không dựa vào display name hoặc session name đơn lẻ vì chúng có thể được tái sử dụng.

### 11.2. Lần theo AssumeRole chain

Một cuộc điều tra có thể cần chuỗi:

~~~mermaid
flowchart TD
    LOGIN["ConsoleLogin / Identity Center sign-in"]
    STS["STS AssumeRole"]
    SESSION["Assumed-role session"]
    ACTION["IAM / EC2 / S3 API calls"]
    CHANGE["Sensitive resource change"]
    LOGIN --> STS --> SESSION --> ACTION --> CHANGE
~~~

Trình tự điều tra:

1. Tìm sign-in hoặc federation event liên quan.
2. Tìm `AssumeRole` trong STS và xác định caller, target role, session name, external ID nếu có.
3. Tìm API events có `userIdentity.arn` hoặc principal ID tương ứng với assumed-role session.
4. Kiểm tra `sessionIssuer` để biết IAM role phát hành credentials.
5. So sánh `sourceIPAddress`, `userAgent`, MFA context và thời gian session.
6. Đối chiếu với deployment pipeline, ticket thay đổi hoặc hoạt động automation đã phê duyệt.

Với IAM Identity Center, web identity, service roles hoặc chained role sessions, actor gốc có thể nằm ở trường `onBehalfOf`, `sourceIdentity`, `inScopeOf` hoặc một event STS trước đó. Không phải mọi loại session đều có cùng các trường.

### 11.3. Tìm các hành động xảy ra quanh một event

Sau khi có event time, chạy query với cửa sổ nhỏ trước/sau sự kiện, ví dụ 15 phút. Mở rộng cửa sổ nếu:

- Có nhiều bước provisioning hoặc deployment.
- Một role được assume trước đó khá lâu.
- Event delivery bị trễ.
- Sự kiện liên quan đến nhiều Region hoặc account.

Giữ lại event time UTC, không chỉ thời điểm ingest/query. Sắp xếp timeline theo `eventTime` và lưu cả các event IDs để có thể truy xuất lại.

### 11.4. Tương quan với các nguồn dữ liệu khác

CloudTrail là control-plane audit trail, không phải telemetry đầy đủ của workload. Tùy giả thuyết, đối chiếu với:

| Nguồn | Bằng chứng bổ sung |
| --- | --- |
| AWS Config | Resource configuration hiện tại và lịch sử thay đổi được ghi nhận |
| GuardDuty | Findings về hành vi hoặc threat indicators |
| VPC Flow Logs | Network flows, source/destination IP, port, bytes |
| CloudWatch Logs | Application/system logs và runtime errors |
| IAM Access Analyzer | External access, policy exposure và trust relationships |
| S3 server access logs / S3 data events | Hoạt động truy cập object theo cấu hình |
| CI/CD audit logs | Ai khởi chạy pipeline, commit và deployment nào |

Không kết luận chỉ từ một IP, user agent hoặc event. Kết hợp nhiều nguồn và kiểm tra bối cảnh change management.

## 12. Chạy query và quản lý kết quả

CloudTrail console cung cấp Query Editor, Sample queries và Saved queries. AWS CLI có thể dùng để chạy query trong automation hoặc incident runbook.

### 12.1. Chạy query bằng console

1. Mở CloudTrail console và chọn Lake → Query.
2. Chọn Sample queries hoặc tạo query mới.
3. Chọn EDS cần phân tích.
4. Thêm `eventTime` start/end và filter theo event source/action/actor.
5. Chạy query và theo dõi trạng thái.
6. Xem Query results, số bản ghi và metadata của lần chạy.
7. Lưu query thành saved query nếu cần tái sử dụng.

Sample query là điểm bắt đầu. Hãy chỉnh actor, time range, event source và account theo incident; không chạy nguyên query không giới hạn trên kho lớn.

### 12.2. Chạy query bằng AWS CLI

~~~bash
aws cloudtrail start-query \
  --query-statement "SELECT eventTime, eventSource, eventName, userIdentity.arn FROM event-data-store-id WHERE eventTime >= TIMESTAMP '2026-11-20 00:00:00' AND eventTime < TIMESTAMP '2026-11-21 00:00:00' LIMIT 100" \
  --region ap-southeast-1
~~~

Lệnh trả về `QueryId`. Dùng ID này để theo dõi:

~~~bash
aws cloudtrail describe-query \
  --query-id <query-id> \
  --region ap-southeast-1

aws cloudtrail get-query-results \
  --query-id <query-id> \
  --region ap-southeast-1
~~~

Kiểm tra query status, error message, result count, runtime và `BytesScanned`. Nếu query đang chạy quá lâu, cân nhắc cancel hoặc chia time range.

### 12.3. Hủy query

~~~bash
aws cloudtrail cancel-query \
  --query-id <query-id> \
  --region ap-southeast-1
~~~

Hủy query không xóa dữ liệu trong EDS. Dùng khi truy vấn chạy nhầm phạm vi hoặc phát hiện query scan lớn hơn dự kiến.

### 12.4. Lưu kết quả vào S3

Query results có thể được lưu vào S3 để chia sẻ cho nhóm incident response hoặc lưu cùng hồ sơ điều tra. Khi delivery tới S3:

- Bucket phải ở Region/account được hỗ trợ cho thao tác.
- Bucket policy phải cho phép CloudTrail ghi kết quả.
- Encryption, bucket ownership và lifecycle phải theo chuẩn bảo mật.
- Hạn chế quyền đọc kết quả vì có thể chứa principal ARNs, IPs, resource names và request parameters.
- Ghi lại query statement, EDS ID, time range, query ID và thời điểm export.

Không xem file CSV export là bằng chứng tự xác thực. Dùng cơ chế validation của CloudTrail và quy trình evidence handling của tổ chức.

### 12.5. Saved queries và runbook

Đặt tên query theo câu hỏi điều tra, ví dụ:

~~~text
IR-01-ConsoleLoginFailures
IR-02-IAMPrivilegeChanges
IR-03-AssumeRoleChain
IR-04-PublicSecurityGroupChanges
IR-05-S3SensitiveObjectAccess
~~~

Lưu mô tả về phạm vi event coverage, EDS ID, time range và trường cần thay. Query template không thay thế incident-specific validation.

## 13. Federation sang Athena

CloudTrail Lake có thể federate Event Data Store để truy vấn event data bằng Amazon Athena. Federation đăng ký metadata của EDS trong AWS Glue Data Catalog và sử dụng AWS Lake Formation để quản lý quyền truy cập dữ liệu federated.

~~~mermaid
flowchart LR
    EDS["CloudTrail Lake EDS"]
    GLUE["AWS Glue Data Catalog"]
    LF["AWS Lake Formation"]
    ATHENA["Amazon Athena"]
    EDS --> GLUE
    GLUE --> LF
    LF --> ATHENA
    ATHENA --> RESULTS["Query results in S3"]
~~~

### 13.1. Cách federation hoạt động

- CloudTrail tạo hoặc sử dụng managed database `aws:cloudtrail` trong Glue Data Catalog.
- Một federated table được tạo cho EDS.
- CloudTrail đăng ký federation role và EDS với Lake Formation.
- Athena dùng metadata đó để tìm, đọc và xử lý dữ liệu.

Federation hữu ích khi team đã có Athena workflows, cần join dữ liệu với các bảng khác hoặc muốn dùng công cụ analytics hiện có.

### 13.2. Quyền truy cập

Người query Athena cần:

- Quyền Athena để chạy query và đọc kết quả.
- Quyền Glue Data Catalog phù hợp.
- Quyền Lake Formation trên federated database/table và data access.
- IAM permission `lakeformation:GetDataAccess` theo hướng dẫn AWS.
- Quyền ghi query results vào Athena result bucket.

Role federation cần các quyền tối thiểu để quản lý Glue/Lake Formation resources. Nếu xóa role hoặc revoke quyền Lake Formation/Glue, Athena query có thể không hoạt động.

### 13.3. Chi phí và lifecycle

Bật federation không tính phí CloudTrail Lake; query trong Athena có phí theo lượng dữ liệu Athena scan. Cần tối ưu Athena query và S3 result storage riêng.

Khi federation bật, EDS không thể bị xóa trực tiếp. Trước khi xóa, phải disable federation và tắt termination protection nếu đang bật. Disable federation chỉ tắt tích hợp Glue/Lake Formation/Athena; dữ liệu CloudTrail Lake không bị xóa và vẫn có thể query trong CloudTrail Lake.

### 13.4. Khi nào không cần federation?

Nếu analyst chỉ cần SQL query trong CloudTrail Lake, dùng Query Editor trực tiếp có thể đơn giản hơn. Chỉ bật federation khi có nhu cầu Athena/Lake Formation thực tế; thêm một lớp tích hợp đồng nghĩa thêm role, policy, catalog và chi phí cần quản lý.

## 14. Resource-based policy và cross-account query

Event Data Store hỗ trợ resource-based policy để cho phép principal ở account khác thực hiện một số thao tác trên EDS. Đây là cơ chế phù hợp khi security account sở hữu EDS nhưng analyst hoặc delegated team ở account khác cần query.

### 14.1. Các actions có thể cấp qua EDS resource policy

CloudTrail hỗ trợ một tập actions cụ thể trên EDS, bao gồm:

- `cloudtrail:StartQuery`.
- `cloudtrail:CancelQuery`.
- `cloudtrail:ListQueries`.
- `cloudtrail:DescribeQuery`.
- `cloudtrail:GetQueryResults`.
- `cloudtrail:GenerateQuery`.
- `cloudtrail:GenerateQueryResultsSummary`.
- `cloudtrail:GetEventDataStore`.

Resource policy không cấp mọi quyền quản trị EDS. Quyền tạo, sửa, xóa EDS và quyền IAM của caller vẫn phải được quản lý riêng.

### 14.2. Ví dụ cho phép một account query EDS

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowSecurityAnalystAccountToQuery",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::444455556666:root"
      },
      "Action": [
        "cloudtrail:StartQuery",
        "cloudtrail:CancelQuery",
        "cloudtrail:ListQueries",
        "cloudtrail:DescribeQuery",
        "cloudtrail:GetQueryResults",
        "cloudtrail:GetEventDataStore"
      ],
      "Resource": "arn:aws:cloudtrail:ap-southeast-1:111122223333:eventdatastore/example-eds-id"
    }
  ]
}
~~~

Ví dụ này cho phép principals trong account `444455556666` được cấp identity permissions sử dụng các query actions được liệt kê trên EDS thuộc account `111122223333`. Trong production, có thể chỉ định role ARN cụ thể thay vì account root để thu hẹp trust boundary. Account được chia sẻ vẫn cần identity policy cho phép các actions tương ứng.

### 14.3. Gắn resource policy bằng CLI

~~~bash
aws cloudtrail put-resource-policy \
  --resource-arn arn:aws:cloudtrail:ap-southeast-1:111122223333:eventdatastore/example-eds-id \
  --resource-policy file://eds-resource-policy.json \
  --region ap-southeast-1
~~~

Đảm bảo policy áp dụng đúng EDS ARN, đúng Region và principal được phê duyệt. Sau khi chia sẻ, kiểm tra bằng một role test trong account consumer; xác minh cả identity policy và resource policy.

### 14.4. Resource policy khác organization delegated access

Organization EDS có thể có resource policy mặc định được CloudTrail quản lý để phản ánh delegated administrator permissions trong AWS Organizations. Khi thay đổi delegated administrators hoặc organization configuration, policy này có thể được cập nhật tự động.

Không ghi đè policy do CloudTrail quản lý mà chưa hiểu tác động tới delegated administrators và dashboards.

### 14.5. Nguyên tắc chia sẻ an toàn

- Chỉ chia sẻ query/read actions cần thiết.
- Không cấp quyền xóa hoặc thay đổi ingestion cho analyst chỉ cần điều tra.
- Dùng role cụ thể, session duration ngắn và MFA/Identity Center theo chính sách.
- Theo dõi việc sử dụng query và chi phí scan.
- Giới hạn access vào EDS chứa đúng phạm vi dữ liệu; tách EDS nếu cần ranh giới bảo mật khác nhau.

## 15. Bảo toàn và xác thực query results

Trong incident response, kết quả query thường được đính kèm vào ticket, hồ sơ pháp chứng hoặc báo cáo tuân thủ. Cần bảo vệ cả nội dung kết quả và bằng chứng rằng file không bị thay đổi sau khi CloudTrail tạo.

### 15.1. CloudTrail query results integrity validation

Khi lưu query results vào S3, CloudTrail có thể ghi:

- Một hoặc nhiều file kết quả CSV nén gzip.
- File chữ ký `result_sign.json` chứa hash của từng file kết quả và chữ ký số.

CloudTrail dùng SHA-256 để hash nội dung file và SHA-256 with RSA để ký thông tin hash. Cơ chế này giúp phát hiện file kết quả bị sửa, bị xóa hoặc file chữ ký không hợp lệ sau khi được CloudTrail phân phối.

### 15.2. Xác thực bằng AWS CLI

~~~bash
aws cloudtrail verify-query-results \
  --s3-bucket audit-evidence-bucket \
  --s3-prefix cloudtrail-lake/query/incident-2026-11-20/ \
  --region ap-southeast-1
~~~

Nếu đã tải cả file kết quả và sign file về máy, có thể xác thực local:

~~~bash
aws cloudtrail verify-query-results \
  --local-export-path ./incident-query-results/ \
  --region ap-southeast-1
~~~

Lệnh yêu cầu AWS CLI v2. Khi xác thực local, giữ nguyên tên file gốc và đặt file kết quả cùng sign file trong thư mục được chỉ định. Khi xác thực trong S3, prefix phải chứa các file gốc và sign file; không đổi tên chúng.

### 15.3. Đọc kết quả validation

| Kết quả | Ý nghĩa |
| --- | --- |
| Sign file validated successfully | Chữ ký sign file hợp lệ; có thể kiểm tra hash từng result file |
| Hash mismatch | Nội dung file kết quả không khớp hash trong sign file |
| Invalid signature | Chữ ký sign file không hợp lệ |
| File missing | Một file được sign file tham chiếu không còn tại vị trí mong đợi |

Validation chứng minh tính toàn vẹn của file query results được CloudTrail ký; nó không chứng minh query đã chọn đúng EDS, time range, selectors hoặc giả thuyết điều tra. Lưu kèm query statement, EDS ID, query ID, event time window, operator và lý do truy vấn.

### 15.4. Chain of custody cho evidence

- Lưu bản gốc trong S3 bucket chuyên dụng, bật encryption và hạn chế quyền ghi/xóa.
- Dùng S3 Versioning/Object Lock khi yêu cầu compliance và mô hình lưu trữ phù hợp.
- Giữ `result_sign.json` cùng result files.
- Ghi lại ai thực hiện query, khi nào, EDS nào và query statement nào.
- Ghi nhận mọi thao tác download, copy, chuyển giao hoặc xử lý dữ liệu.
- Xác thực integrity trước khi sử dụng kết quả trong báo cáo pháp chứng.
- Hạn chế chia sẻ raw event payload vì có thể chứa thông tin nhạy cảm.

Query result integrity validation không thay thế log file integrity validation của CloudTrail Trail. Hai cơ chế áp dụng cho hai loại bằng chứng khác nhau: query output và log files được phân phối bởi Trail.

## 16. Quy trình điều tra hoạt động tài khoản

Một incident runbook nên bắt đầu bằng giả thuyết và bằng chứng, không bắt đầu bằng việc chạy một query lớn. Quy trình dưới đây phù hợp với sự kiện nghi ngờ như tạo access key trái phép, gắn policy quản trị, mở security group hoặc đọc dữ liệu nhạy cảm.

### 16.1. Triage và xác định phạm vi

1. Ghi nhận alert/findings, nguồn báo cáo và thời điểm phát hiện.
2. Xác định account, Region, resource, actor hoặc API liên quan.
3. Chọn time window ban đầu trước/sau sự kiện.
4. Kiểm tra EDS có thu thập event category và selectors cần thiết không.
5. Xác định liệu dữ liệu có thể bị trễ ingest hoặc chưa được ingest do selector.

Không kết luận "không có event" là "không có hoạt động" trước khi xác nhận event coverage, Region, account, retention và ingestion status.

### 16.2. Dựng timeline ban đầu

Tìm event chính, sau đó mở rộng:

- 15–30 phút trước sự kiện để tìm sign-in, AssumeRole hoặc thay đổi quyền.
- Khoảng thời gian sự kiện để tìm API calls cùng actor/resource.
- 15–60 phút sau sự kiện để tìm hành động tiếp theo hoặc cleanup.
- Time window dài hơn nếu session được assume trước đó hoặc event delivery chậm.

Lưu query statement và event IDs. Dùng UTC làm chuẩn và ghi chú mọi chuyển đổi múi giờ.

### 16.3. Xác định actor và session

- Kiểm tra `userIdentity.type`, `arn`, `principalId`, `accountId`.
- Nếu là `AssumedRole`, xem `sessionIssuer`, `sourceIdentity`, session name và STS events.
- Kiểm tra `mfaAuthenticated` nếu có.
- Đối chiếu `sourceIPAddress`, `userAgent`, `awsRegion` và session creation time.
- Xác định hoạt động đến từ human, CI/CD, workload hoặc AWS service.

Một `userAgent` lạ hoặc IP mới là tín hiệu cần điều tra, không phải kết luận tự thân. So sánh với baseline và lịch thay đổi.

### 16.4. Xác định tác động

Trả lời:

- API nào được gọi và có thành công không?
- Resource nào bị tạo, sửa, xóa hoặc truy cập?
- Policy/role/permission nào thay đổi?
- Có data events liên quan tới object, table hoặc function không?
- Có network changes hoặc traffic bất thường không?
- Có API calls tiếp theo sử dụng quyền vừa được cấp không?

Đọc `requestParameters` để hiểu ý định và `responseElements` để hiểu kết quả nếu các trường được ghi. Đối chiếu trạng thái resource với AWS Config/current API khi cần.

### 16.5. Kiểm tra giả thuyết và mở rộng

Ví dụ giả thuyết: "Một role bị gắn AdministratorAccess ngoài change window".

1. Tìm event `AttachRolePolicy` hoặc `PutRolePolicy`.
2. Xác định actor/session và target role.
3. Tìm STS AssumeRole event tạo session đó.
4. Tìm hoạt động sign-in hoặc pipeline trigger trước đó.
5. Tìm các API calls sau thay đổi privilege.
6. Kiểm tra tài nguyên được tạo, dữ liệu được đọc hoặc security controls bị tắt.
7. Đối chiếu CloudTrail với GuardDuty, Config, CloudWatch Logs và CI/CD audit logs.
8. Xác minh thay đổi có ticket/approval và owner hợp lệ không.

### 16.6. Containment và evidence

Nếu có dấu hiệu compromise, phối hợp incident commander/security owner để:

- Vô hiệu hóa hoặc rotate credentials theo runbook đã phê duyệt.
- Thu hồi session/role access khi phù hợp.
- Khôi phục policy hoặc network rule về baseline an toàn.
- Bảo toàn EDS, Trail logs, query results, Config history và workload evidence.
- Tránh xóa resource hoặc log trước khi thu thập bằng chứng cần thiết.
- Ghi rõ người thực hiện containment, thời điểm và lý do.

CloudTrail Lake là công cụ điều tra, không phải công cụ containment. Hành động thay đổi IAM/network cần theo quy trình incident response và change control.

### 16.7. Kết thúc incident

Hồ sơ kết thúc nên có:

- Incident timeline với UTC timestamps và event IDs.
- Actor/session chain và account/Region scope.
- Tài nguyên bị ảnh hưởng và hành động đã thực hiện.
- Query statements và query results đã xác thực.
- Evidence từ các nguồn khác và mức độ tin cậy của từng kết luận.
- Root cause, containment/recovery actions và preventive controls.
- Khoảng trống logging/selector được phát hiện và kế hoạch khắc phục.

## 17. Khả năng cung cấp hiện tại và hướng chuyển sang CloudWatch

Từ ngày 31-05-2026, CloudTrail Lake không mở cho khách hàng mới. AWS CloudTrail vẫn được hỗ trợ; Trails, Event history, Insights và Aggregated Events không bị ảnh hưởng. CloudTrail Lake hiện hữu tiếp tục hoạt động, nhưng chỉ nhận critical bug fixes và security updates. AWS khuyến nghị Amazon CloudWatch cho năng lực thu thập, lưu trữ và phân tích tương tự.

### 17.1. Khách hàng mới nên học kiến trúc nào?

Với tổ chức chưa từng sử dụng CloudTrail Lake, nên thiết kế CloudTrail Trails và Amazon CloudWatch architecture theo tài liệu AWS hiện hành. CloudWatch có thể hợp nhất security, operations và compliance telemetry; hỗ trợ OCSF/OTel, pipeline/transformations, OpenSearch-backed analytics, Logs Insights và tích hợp nguồn dữ liệu rộng.

CloudWatch là kiến trúc thay thế được AWS khuyến nghị, nhưng không phải bản sao tính năng hoàn toàn:

| Năng lực | CloudTrail Lake | CloudWatch architecture |
| --- | --- | --- |
| CloudTrail management/data events | Có | Có qua cơ chế ingestion được hỗ trợ |
| Network activity và Insights events | Có trong phạm vi EDS hỗ trợ | Không được liệt kê là coverage tương đương trong so sánh migration hiện tại |
| SQL analytics | SQL trong EDS, hỗ trợ truy vấn lồng phức tạp | Logs QL, SQL và PPL với analytics/OpenSearch |
| Data normalization | Hạn chế hơn | Có OCSF/OTel và transformations được hỗ trợ |
| Third-party sources | Tích hợp theo CloudTrail Lake | CloudWatch pipelines/connectors được AWS công bố |
| Cross-account/Region | Có cơ chế EDS organization | Có centralization; enablement có thể cần cấu hình theo từng Region |

Trước khi thiết kế mới, lập bảng coverage theo event sources thực tế. Nếu use case cần Network Activity hoặc Insights events, duy trì CloudTrail Trails/Insights và chọn thêm nguồn dữ liệu phù hợp; đừng giả định CloudWatch pipeline tự thay thế mọi event category.

CloudWatch pipelines và một số connectors chỉ khả dụng ở các Region được AWS công bố. Kiểm tra Region availability và service quotas tại nơi đặt workload trước khi chốt kiến trúc; Singapore (`ap-southeast-1`) nằm trong danh sách Region hỗ trợ hiện tại của CloudWatch pipelines.

### 17.2. Khách hàng CloudTrail Lake hiện hữu

AWS khuyến nghị migrate log data từ CloudTrail Lake sang Amazon CloudWatch. Một kế hoạch an toàn:

1. Inventory EDS, event categories, selectors, account/Region scope và retention.
2. Liệt kê saved queries, dashboards, federation, cross-account policies và downstream consumers.
3. Chọn một EDS nhỏ hoặc một time window ngắn để pilot migration.
4. Export historical EDS data vào CloudWatch log group theo quy trình AWS hỗ trợ.
5. Xác minh schema/fields, retention, IAM permissions và query results.
6. Đo ingestion volume/cost của sample trước khi migrate toàn bộ.
7. Chuyển dashboard, alert, query runbooks và access roles.
8. Bật live CloudTrail ingestion vào CloudWatch theo kiến trúc được AWS khuyến nghị.
9. Giữ lại EDS/S3 archive theo yêu cầu pháp lý và khoảng thời gian dữ liệu chưa migrate.
10. Chỉ retire integration cũ sau khi consumer, evidence và retention đã được kiểm chứng.

### 17.3. Pilot migration và giới hạn lịch sử

AWS khuyến nghị pilot bằng một tập dữ liệu nhỏ để kiểm tra:

- Log xuất hiện đúng trong CloudWatch log group.
- Schema/field mapping đáp ứng query và dashboard.
- IAM roles và permissions hoạt động.
- Ingestion cost được ước lượng từ sample, ví dụ 24 giờ.
- Logs Insights queries thay thế được các câu hỏi điều tra chính.

Theo hướng dẫn migration hiện tại, dữ liệu trước năm 2023 không được migrate từ CloudTrail Lake sang CloudWatch bằng quy trình import này. Nếu cần truy cập dữ liệu cũ hơn, tiếp tục query trực tiếp trong EDS hiện hữu hoặc chuyển/lưu trữ vào S3 theo kế hoạch riêng.

### 17.4. Import historical EDS data bằng AWS CLI

AWS cung cấp API import từ EDS vào CloudWatch Logs. Ví dụ:

~~~bash
aws logs create-import-task \
  --import-source-arn arn:aws:cloudtrail:ap-southeast-1:111122223333:eventdatastore/example-eds-id \
  --import-role-arn arn:aws:iam::111122223333:role/CloudTrailLakeExportRole \
  --import-filter '{"startEventTime":1795046400000,"endEventTime":1795132800000}' \
  --region ap-southeast-1
~~~

`startEventTime` và `endEventTime` là Unix epoch milliseconds, không phải ISO-8601 strings. Ví dụ trên giới hạn khoảng 19-11-2026 00:00 UTC đến 20-11-2026 00:00 UTC. Import task chạy bất đồng bộ; theo dõi bằng `aws logs describe-import-tasks` với import ID được trả về.

Import role phải trust principal `cloudtrail.amazonaws.com` và có quyền tối thiểu để đọc EDS và tạo log group/stream, ghi resource policy; nếu EDS dùng customer managed KMS key, cần quyền KMS tương ứng. API caller cần quyền truy cập source EDS, quyền `logs:CreateImportTask` và `iam:PassRole`. AWS giới hạn tối đa ba import tasks active trên mỗi account tại một thời điểm; source EDS phải ở trạng thái ACTIVE và time range phải nằm trong retention. Kiểm tra prerequisites, role trust/policy và quota trong [CreateImportTask API](https://docs.aws.amazon.com/AmazonCloudWatchLogs/latest/APIReference/API_CreateImportTask.html) trước khi chạy.

### 17.5. Những việc không nên làm khi migration

- Không xóa EDS cũ ngay sau khi tạo import task.
- Không tắt Trail logging khi chưa xác minh CloudWatch live ingestion đã nhận đủ event coverage.
- Không giả định mọi event category và schema đều map một-một.
- Không bỏ qua dữ liệu trước 2023 nếu có nghĩa vụ điều tra/lưu trữ.
- Không chuyển dashboards/queries trước khi pilot xác nhận field mapping.
- Không retire federation, resource policies hoặc saved queries trước khi có owner thay thế.

### 17.6. Tài liệu migration chính thức

AWS duy trì hướng dẫn về [CloudTrail Lake availability change và migration options](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-lake-service-availability-change.html). Dùng hướng dẫn này làm nguồn chuẩn cho các bước export/import, role permissions, phạm vi dữ liệu và những giới hạn được hỗ trợ hiện tại.

## 18. Troubleshooting khi điều tra

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| **Không tìm thấy event** | Sai EDS/Region, selector không thu thập event, time range sai hoặc event chưa ingest | Xác minh EDS ARN, event coverage, UTC time range và ingestion status |
| **Có management event nhưng thiếu S3 object access** | EDS/Trail chưa bật S3 data events cho bucket/prefix | Kiểm tra advanced event selectors và data event configuration |
| **Query trả 0 rows** | Lọc sai `eventSource`, `eventName`, actor ARN hoặc casing/field path | Chạy query hẹp theo time range, bỏ dần điều kiện và xem sample event |
| **Query scan quá nhiều dữ liệu** | Thiếu `eventTime`, chọn `SELECT *` hoặc time range quá rộng | Giới hạn thời gian, chọn cột cần thiết, thêm filter sớm |
| **Query response quá lớn** | Nhiều rows hoặc aggregation tạo một kết quả rất lớn | Thêm `LIMIT`, chia time range, bỏ `array_agg` dư thừa hoặc tổng hợp gọn |
| **Query exhausted resources** | Join/aggregation/window function xử lý tập dữ liệu quá lớn | Chia time window nhỏ hơn, giảm join và retry theo hướng dẫn AWS |
| **Không query được organization EDS** | Principal member account không có quyền hoặc delegated admin chưa được cấp | Kiểm tra management/delegated administrator, resource policy và identity policy |
| **Cross-account query bị AccessDenied** | EDS resource policy hoặc identity policy thiếu action | Kiểm tra principal, EDS ARN, actions được hỗ trợ và account ID |
| **Athena không thấy EDS table** | Federation chưa bật hoặc Glue/Lake Formation permissions sai | Kiểm tra federation role, Glue database/table và Lake Formation grants |
| **Không xóa được EDS** | Federation hoặc termination protection còn bật | Disable federation trước, tắt termination protection theo quy trình |
| **Không thể thay đổi retention/export** | Export đang được sử dụng hoặc cấu hình bị khóa theo pricing/lifecycle | Kiểm tra importers, EDS settings và pricing option constraints |
| **Historical copy thất bại** | S3 bucket/KMS policy, object storage class hoặc role permissions sai | Kiểm tra `GetObject`, KMS decrypt, S3 bucket policy và object restore |
| **Query results không xác thực được** | File bị đổi tên, thiếu sign file hoặc nội dung đã thay đổi | Dùng file gốc và sign file; kiểm tra S3 prefix, Region và AWS CLI v2 |
| **CloudWatch import task lỗi** | Role thiếu quyền, source ARN sai hoặc import filter không hợp lệ | Kiểm tra role trust/policy, EDS ARN và task status |

### 18.1. Query trả về 0 rows: điều tra theo từng bước

1. Chạy một query chỉ lọc `eventTime` với khoảng thời gian chắc chắn có hoạt động.
2. Chỉ thêm `eventSource`.
3. Thêm `eventName`.
4. Thêm actor ARN sau khi kiểm tra giá trị thực tế trong event.
5. Kiểm tra event category có đúng EDS đang ingest không.
6. Kiểm tra account/Region và event delivery timing.

Không sửa query bằng cách mở time range vô hạn ngay lập tức. Xác định điều kiện nào làm mất kết quả và kiểm tra event sample.

### 18.2. Kiểm tra event coverage trước khi kết luận

Nếu không có S3 `GetObject` event, có thể là:

- Data events chưa được bật cho bucket/prefix.
- Selector chỉ chọn write events.
- EDS mới được tạo sau khi hành động đã xảy ra.
- EDS đang ingest ở Region/account khác.
- Event nằm ngoài retention.

CloudTrail Lake chỉ query được dữ liệu đã được ingest hoặc historical data đã được copy thành công.

### 18.3. Điều tra thiếu dữ liệu khi copy

Khi copy Trail events từ S3 vào EDS:

- CloudTrail đọc gzip-compressed CloudTrail log files trong S3.
- Một số archived storage classes cần restore object trước khi đọc.
- Bucket policy phải cho phép CloudTrail đọc object.
- Nếu S3 dùng SSE-KMS, key policy phải cho phép thao tác decrypt/generate data key cần thiết.
- Chọn time range phù hợp retention của EDS.
- Kiểm tra copy status và retry failures theo hướng dẫn.

## 19. Case study: điều tra một lần mở quyền quản trị ngoài kế hoạch

### 19.1. Bối cảnh

Security team nhận cảnh báo rằng role `ApplicationRole` vừa được gắn policy `AdministratorAccess` vào buổi tối, ngoài deployment window. EDS organization đang thu thập management events trên nhiều account/Region; S3 data events được bật cho bucket dữ liệu nhạy cảm.

### 19.2. Giả thuyết điều tra

- Một actor đã gắn policy quản trị.
- Actor dùng assumed-role session từ một nguồn không quen thuộc.
- Role mới được cấp quyền đã được dùng để thay đổi resource hoặc đọc dữ liệu.

### 19.3. Bước 1 — tìm event thay đổi IAM

Chạy query IAM privilege change ở mục 10.3, giới hạn thời gian từ lúc alert trước đó 1–2 giờ. Xác định:

- Event ID và timestamp.
- Actor ARN và principal ID.
- Target role name.
- Policy ARN/document.
- Source IP, user agent và Region.
- API có thành công hay trả error.

### 19.4. Bước 2 — truy nguồn session

Lấy assumed-role ARN từ event. Tìm `AssumeRole` trong STS để biết:

- Caller identity đã assume `DeploymentRole` hoặc role trung gian.
- Target role ARN và session name.
- External ID/source identity nếu có.
- Source IP và user agent tại thời điểm assume.

Sau đó đối chiếu sign-in/Identity Center events và kiểm tra MFA context. Nếu session được tạo bởi CI/CD, xác định pipeline run, repository, commit và deployment approval.

### 19.5. Bước 3 — tìm hành động sau khi có quyền

Tìm các events sau `AttachRolePolicy` do actor/assumed-role session đó thực hiện:

- IAM: tạo user/access key, thay trust policy hoặc attach thêm policy.
- EC2/VPC: tạo instance, mở security group hoặc thay route.
- S3: `GetObject`, `PutObject`, `DeleteObject` trên bucket nhạy cảm.
- CloudTrail: stop trail, thay selector hoặc thay EDS ingestion settings.

Nếu S3 data events không được thu thập cho bucket liên quan, ghi nhận đây là gap trong coverage; không khẳng định dữ liệu không bị truy cập.

### 19.6. Bước 4 — xác minh và containment

Security team xác nhận session không thuộc pipeline đã phê duyệt, sau đó thực hiện containment theo incident runbook:

1. Thu thập và xác thực query results.
2. Lưu event IDs, role/session ARNs, source IP và resource IDs.
3. Thu hồi quyền/credentials hoặc session theo quy trình được phê duyệt.
4. Khôi phục policy của `ApplicationRole` về baseline.
5. Kiểm tra resource/data changes phát sinh trong session.
6. Bật bổ sung selector cho resource nhạy cảm nếu phát hiện coverage gap.

### 19.7. Kết quả và bài học

Timeline nên thể hiện rõ sign-in → AssumeRole → AttachRolePolicy → API calls sau khi có quyền → containment. Nếu không tìm thấy event nào ở một mắt xích, ghi rõ đó là "không có dữ liệu trong nguồn đã thu thập" thay vì "không xảy ra".

Case study cho thấy CloudTrail Lake hữu ích khi event coverage được thiết kế trước incident. SQL giúp thu hẹp và tương quan dữ liệu; kết luận vẫn cần đối chiếu với các nguồn khác và quy trình xác minh.

## 20. Bài tập củng cố

### Bài 1 — Event history hay CloudTrail Lake?

Một operator cần kiểm tra nhanh ai vừa gọi `StopLogging` trong account hiện tại. Nếu cần điều tra sâu hoạt động của nhiều accounts và nhiều ngày, nên dùng cơ chế nào?

**Gợi ý:** Event history phù hợp với tra cứu nhanh management event gần đây; EDS/Trail analytics phù hợp với SQL và phạm vi dài hạn nếu account đã có CloudTrail Lake. Với khách hàng mới, dùng CloudWatch architecture được AWS khuyến nghị.

### Bài 2 — Management event hay data event?

Bạn cần biết ai đã gọi `GetObject` trên một object trong bucket dữ liệu nhạy cảm. Management events có đủ không?

**Gợi ý:** không. Cần bật S3 data events cho bucket/prefix và operation cần audit.

### Bài 3 — Actor là assumed role

Một event có `userIdentity.type = AssumedRole`. Trường nào giúp xác định role phát hành credentials?

**Gợi ý:** `userIdentity.sessionContext.sessionIssuer.arn`; tiếp tục tìm STS AssumeRole để truy nguồn caller.

### Bài 4 — Chọn selector

Một organization muốn audit mọi thao tác object trong bucket `finance-data`, nhưng không cần data events của các bucket khác. Selector nên giới hạn theo trường nào?

**Gợi ý:** `eventCategory=Data`, `resources.type=AWS::S3::Object` và `resources.ARN` bắt đầu bằng bucket/prefix cần theo dõi.

### Bài 5 — Query tốn kém

Một query dùng `SELECT *` trên EDS nhiều TB mà không có time range. Cách tối ưu đầu tiên?

**Gợi ý:** thêm `eventTime` start/end, chỉ chọn các cột cần thiết và thêm filter theo event source/name/actor.

### Bài 6 — Không có S3 GetObject event

Điều tra viên không tìm thấy `GetObject`. Có thể kết luận không ai đọc object không?

**Gợi ý:** không. Kiểm tra S3 data event selector, bucket/prefix, Region, retention và thời điểm EDS bắt đầu ingest.

### Bài 7 — Cross-account query

Analyst ở account A cần query organization EDS do security account sở hữu. Hai lớp quyền nào cần được xem xét?

**Gợi ý:** resource-based policy trên EDS và identity policy của principal ở account A; ngoài ra cần đúng organization/delegated administrator permissions nếu là organization EDS.

### Bài 8 — Athena federation

Một team đã query EDS bằng Athena. Họ muốn xóa EDS nhưng lệnh delete bị từ chối. Cần kiểm tra gì?

**Gợi ý:** federation phải được disable trước; nếu termination protection bật, phải tắt theo quy trình trước khi xóa.

### Bài 9 — Evidence integrity

Query results đã được export ra S3 và gửi cho incident commander. Làm thế nào xác minh file chưa bị sửa?

**Gợi ý:** giữ sign file `result_sign.json` và dùng `aws cloudtrail verify-query-results` trên S3 prefix hoặc local files.

### Bài 10 — CloudTrail Lake availability

Một tổ chức mới tạo AWS account sau ngày 31-05-2026 và muốn bắt đầu với CloudTrail Lake. Nên làm gì?

**Gợi ý:** CloudTrail Lake không mở cho khách hàng mới; dùng CloudTrail Trails và kiến trúc Amazon CloudWatch được AWS khuyến nghị, đồng thời xác nhận coverage của event categories cần thiết.

## 21. Checklist vận hành và điều tra

- [ ] Xác định Event history, Trail, EDS và CloudWatch architecture đang được sử dụng.
- [ ] Ghi rõ trạng thái CloudTrail Lake availability; chỉ vận hành EDS hiện hữu nếu tổ chức đã là khách hàng trước mốc đóng.
- [ ] Multi-Region Trail hoặc EDS coverage được review cho các Region đang hoạt động.
- [ ] Event categories phù hợp use case: management, data, network activity, Insights hoặc Config.
- [ ] Advanced event selectors không bỏ sót resource/action quan trọng.
- [ ] Data events được bật có chủ đích cho bucket, table, function hoặc resource nhạy cảm.
- [ ] Organization EDS hoặc central architecture có coverage cho account mới theo yêu cầu.
- [ ] Retention và pricing option được phê duyệt; ingestion/query volume được theo dõi.
- [ ] Query template có time range, event source/action filters và giới hạn kết quả.
- [ ] Saved queries được version/review và có owner/runbook.
- [ ] Quyền tạo/sửa/xóa EDS tách khỏi quyền query/read.
- [ ] Cross-account access dùng resource policy/identity policy theo least privilege.
- [ ] Delegated administrator chỉ có quyền cần thiết.
- [ ] Federation role, Glue catalog và Lake Formation grants được quản lý.
- [ ] Query results được lưu trong S3 bucket bảo vệ, có encryption, retention và access logging phù hợp.
- [ ] `result_sign.json` được giữ cùng result files và validation được chạy khi evidence cần bảo toàn.
- [ ] Incident timeline dùng UTC, lưu event IDs và truy nguồn assumed-role sessions.
- [ ] CloudTrail được đối chiếu với Config, GuardDuty, VPC Flow Logs, CloudWatch và CI/CD evidence.
- [ ] Không kết luận thiếu event trước khi kiểm tra selectors, account, Region, retention và ingestion.
- [ ] Có migration plan sang CloudWatch cho tổ chức CloudTrail Lake hiện hữu.
- [ ] Dữ liệu lịch sử chưa migrate có retention/archive path rõ ràng.
- [ ] Runbook containment được thực hiện theo incident/change-control process.

## 22. Ghi nhớ

1. **CloudTrail ghi lại hoạt động tài khoản và API**; Event history giúp tra cứu nhanh, Trail phân phối log tới S3, còn CloudTrail Lake EDS cung cấp SQL analytics cho khách hàng hiện hữu.
2. **Management events và data events khác nhau.** Muốn biết ai đọc object hoặc invoke function, cần cấu hình data events đúng resource.
3. **Event Data Store chỉ chứa dữ liệu đã ingest hoặc được copy.** Không có selector phù hợp thì không thể query lại hoạt động đã bỏ lỡ.
4. **`userIdentity` là chìa khóa truy nguồn actor.** Với assumed role, kết hợp session issuer, STS AssumeRole, source IP, user agent và MFA context.
5. **SQL phải có time bounds.** Dùng `eventTime`, chọn ít cột, thêm filters và xem `BytesScanned` để kiểm soát chi phí.
6. **Organization EDS và cross-account access cần quản trị tập trung.** Resource policy, identity policy và delegated administrator permissions là các lớp quyền riêng.
7. **Query results có thể được xác thực.** Giữ sign file và dùng `verify-query-results` để kiểm tra tính toàn vẹn sau khi CloudTrail giao file.
8. **CloudTrail Lake đã ngừng mở cho khách hàng mới từ 31-05-2026.** AWS khuyến nghị CloudWatch architecture cho triển khai mới và migration của khách hàng hiện hữu; cần kiểm tra event coverage vì không phải mọi tính năng đều tương đương.

Điều tra hiệu quả bắt đầu từ event coverage đúng, xác định actor/session, dựng timeline và kiểm chứng giả thuyết bằng nhiều nguồn. CloudTrail cung cấp audit evidence; kết luận và containment vẫn cần quy trình bảo mật có kiểm soát.

### Tài liệu chính thức

- [CloudTrail Lake availability change](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-lake-service-availability-change.html) — mốc ngừng mở khách hàng mới, support hiện hữu và migration sang CloudWatch.
- [Working with AWS CloudTrail Lake](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-lake.html) — tổng quan Event Data Store, query và federation.
- [CloudTrail concepts](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-concepts.html) — event categories, trails và EDS.
- [CloudTrail event record contents](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-event-reference-record-contents.html) — schema và fields của event.
- [CloudTrail userIdentity element](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-event-reference-user-identity.html) — identity/session fields.
- [Create an event data store for CloudTrail events](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/query-event-data-store-cloudtrail.html) — EDS và advanced event selectors.
- [Organization event data stores](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-lake-organizations.html) — management account, delegated administrator và organization scope.
- [CloudTrail Lake queries](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-lake-queries.html) — SQL query editor và time filters.
- [CloudTrail Lake SQL constraints](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/query-limitations.html) — SELECT syntax và SQL constraints.
- [Optimize CloudTrail Lake queries](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/lake-queries-optimization.html) — tối ưu query và xử lý lỗi.
- [Resource-based policy examples](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/security_iam_resource-based-policy-examples.html) — cross-account EDS access.
- [Federate an event data store](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/query-federation.html) — Glue, Lake Formation và Athena.
- [Copying trail events to CloudTrail Lake](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-copy-trail-to-lake.html) — historical event copy.
- [Validate CloudTrail Lake saved query results](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-query-results-validation.html) — sign file và integrity verification.
- [AWS CloudTrail pricing](https://aws.amazon.com/cloudtrail/pricing/) — ingestion, retention và query charges.
- [CloudTrail organization trails](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/creating-trail-organization.html) — organization trail và multi-Region logging.
- [Amazon CloudWatch pipelines](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/cloudwatch-pipelines.html) — kiến trúc CloudWatch thay thế.
