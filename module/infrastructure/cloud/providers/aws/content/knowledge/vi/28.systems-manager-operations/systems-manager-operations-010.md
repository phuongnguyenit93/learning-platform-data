# AWS Health, thông báo vận hành và quản lý sự cố

## Mục tiêu học tập

Sau bài học, người học có thể:

- Phân biệt AWS Health, AWS Health Dashboard, AWS Support Center, Amazon EventBridge, AWS User Notifications và AWS Systems Manager OpsCenter.
- Phân biệt public service events với account-specific events; đọc category, scope, status và actionability của AWS Health event.
- Theo dõi tình trạng AWS services, resource events, planned lifecycle changes và thông báo bảo mật trên một hay nhiều AWS accounts.
- Tạo EventBridge rules để lọc AWS Health events theo service, event category, Region, actionability và persona.
- Thiết kế notification routes qua AWS User Notifications, Amazon SNS, SQS, Lambda, Amazon Q Developer chat integrations hoặc hệ thống ITSM/on-call.
- Xử lý at-least-once delivery, duplicate events, backup Regions, event pagination và khác biệt giữa event Region với affected Region.
- Bật organizational view trong AWS Organizations và phân quyền delegated administrator.
- Hiểu điều kiện truy cập AWS Health API, cách dùng endpoint active/passive và cách lấy dữ liệu event có pagination.
- Tạo và quản lý OpsItems trong Systems Manager OpsCenter; liên kết resource, operational data, deduplication và runbooks.
- Tự động hóa phản ứng với scheduled changes bằng Systems Manager Automation, có IAM role và guardrails phù hợp.
- Xây dựng quy trình incident response gồm detection, triage, declaration, communication, mitigation, recovery và post-incident review.
- Hiểu thay đổi vòng đời AWS Systems Manager Incident Manager và chọn giải pháp phù hợp cho khách hàng mới hoặc khách hàng hiện hữu.

**Bối cảnh module:** Bài thuộc chương **Vận hành với Systems Manager** trong CLOUD_PROVIDERS_AWS. Hệ sinh thái AWS gồm Region/AZ, IAM, VPC, compute, storage, database, integration và serverless. Một planned maintenance, sự cố dịch vụ AWS, lỗi resource hoặc thông báo bảo mật có thể tác động tới nhiều thành phần. AWS Health cung cấp tín hiệu; notification pipeline đưa tín hiệu tới đúng người; Systems Manager và quy trình incident response giúp theo dõi và xử lý công việc vận hành.

> **Phạm vi và mốc dịch vụ:** Nội dung phản ánh tài liệu AWS hiện hành tại tháng 11/2026. AWS Health email được chuyển sang AWS User Notifications từ ngày 15/12/2025. AWS Systems Manager Incident Manager ngừng nhận khách hàng mới từ ngày 07/11/2025; tài khoản đã bật dịch vụ trước thời điểm đó vẫn có thể tiếp tục sử dụng. Hãy kiểm tra support plan, Region, service availability và pricing của account trước khi triển khai.

## 1. Bài toán: AWS gửi thông báo nhưng ai sẽ hành động?

Một workload chạy trên EC2, RDS, Lambda và SQS. AWS thông báo một EC2 instance sắp retirement; đồng thời RDS có planned maintenance và một AWS Region đang có operational issue. Nếu chỉ đọc email rời rạc, đội vận hành có thể bỏ lỡ thời hạn, không biết resource nào bị ảnh hưởng hoặc không phân biệt sự cố AWS với lỗi ứng dụng.

Một quy trình vận hành tốt phải trả lời:

- Sự kiện thuộc AWS service, resource cụ thể hay account?
- Event ảnh hưởng Region nào, account nào và resource nào?
- Đây là issue đang diễn ra, thông báo tài khoản, investigation hay scheduled change?
- Sự kiện có cần hành động không? Hạn xử lý là khi nào?
- Ai chịu trách nhiệm: operations, security hay billing?
- Notification đã tới đúng người và có xác nhận chưa?
- Có thể tự động hóa hành động an toàn nào?
- Nếu tự động hóa thất bại, ai tiếp nhận và khôi phục?

~~~mermaid
flowchart TD
    Health[AWS Health event] --> Filter[EventBridge / User Notifications]
    Filter --> Route[Route by service, category, persona]
    Route --> Notify[Email / Chat / Push / ITSM]
    Route --> Ops[Systems Manager OpsCenter]
    Route --> Auto[SSM Automation]
    Notify --> Team[On-call / Service owner]
    Ops --> Triage[Triage and assign]
    Auto --> Verify[Verify automated action]
    Team --> Incident[Incident response]
    Triage --> Incident
    Verify --> Incident
    Incident --> Recover[Mitigate / Recover]
    Recover --> Review[Post-incident review]
~~~

AWS Health cung cấp thông tin về sự kiện ảnh hưởng AWS services/resources. Nó không tự thay thế quy trình phân công, paging, incident command, communications hoặc post-incident review của tổ chức.

## 2. Phân biệt các thành phần trong AWS

| Thành phần | Vai trò chính | Câu hỏi trả lời |
| --- | --- | --- |
| AWS Health | Nguồn thông tin về sự kiện ảnh hưởng AWS services/accounts/resources | AWS đang thông báo điều gì? |
| AWS Health Dashboard | Giao diện xem service health và account-specific events | Account/resource nào bị ảnh hưởng? |
| AWS Support Center | Quản lý support cases và trao đổi với AWS Support | Cần AWS Support hỗ trợ việc gì? |
| Amazon EventBridge | Lọc, định tuyến và kích hoạt hành động từ Health events | Khi event xuất hiện, hệ thống nào cần chạy? |
| AWS User Notifications | Cấu hình và nhận notifications qua console, email, chat, mobile | Ai cần nhận thông báo qua kênh nào? |
| Systems Manager OpsCenter | Theo dõi OpsItems và vấn đề vận hành | Công việc vận hành nào cần được xử lý? |
| Systems Manager Automation | Chạy runbook để thực hiện tác vụ vận hành | Có thể tự động hóa bước nào? |
| Incident management platform | Paging, incident commander, escalation, timeline và communications | Ai điều phối incident tới khi phục hồi? |

CloudWatch alarms thường phát hiện triệu chứng trong workload, ví dụ CPU cao, 5xx tăng hoặc queue age vượt ngưỡng. AWS Health thông báo sự kiện ở phía AWS hoặc resource lifecycle. Hai nguồn cần được tương quan để xác định ảnh hưởng thực tế.

## 3. AWS Health Dashboard: Service health và Account health

AWS Health Dashboard trong AWS Management Console cung cấp thông tin về sự kiện có thể ảnh hưởng tới AWS services và resources.

Hai góc nhìn cần phân biệt:

- **Service health / public events:** thông tin công khai về tình trạng dịch vụ AWS theo Region, không gắn với một resource cụ thể trong account của bạn.
- **Account health / account-specific events:** thông báo liên quan account hoặc resource của bạn, ví dụ EC2 instance retirement, planned maintenance, resource degradation hoặc required action.

Một public event ở Region có thể ảnh hưởng nhiều khách hàng. Account-specific event cho biết workload/resource cụ thể của account có thể cần xử lý.

AWS Health Dashboard là điểm bắt đầu để con người kiểm tra event details và affected resources. Với tích hợp tự động, dùng EventBridge hoặc AWS Health API khi account đủ điều kiện.

## 4. Event category, scope và lifecycle

AWS Health Event có các category thường gặp:

| Category | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| issue | Sự cố đang ảnh hưởng service/account/resource | Operational issue, connectivity issue |
| accountNotification | Thông báo cần account chú ý | Thay đổi hoặc yêu cầu liên quan account |
| scheduledChange | Thay đổi đã lên lịch | Instance retirement, maintenance, service lifecycle |
| investigation | AWS đang điều tra một vấn đề có thể ảnh hưởng | Investigation update |

Event scope cho biết phạm vi:

- `PUBLIC`: public service event;
- `ACCOUNT_SPECIFIC`: event liên quan account/resource.

Event status thường gặp:

- `upcoming`: sự kiện dự kiến trong tương lai;
- `open`: sự kiện đang mở hoặc chưa được đóng;
- `closed`: sự kiện đã đóng.

Đối với scheduled changes, thời gian bắt đầu có thể nằm trong tương lai. Đừng diễn giải `open` thành “sự cố đang gây outage ngay lúc này”; phải đọc category, event description, startTime và affected entities.

AWS Health event có thể được cập nhật nhiều lần. `latestDescription` là nội dung mô tả mới nhất; với public events, trường này không phải toàn bộ lịch sử trao đổi. Nếu cần lịch sử chi tiết, truy vấn AWS Health Dashboard/API.

## 5. Actionability và personas: định tuyến theo ý nghĩa

Một số AWS Health events có metadata để hỗ trợ định tuyến tự động.

`actionability` có thể là:

| Giá trị | Ý nghĩa | Cách xử lý gợi ý |
| --- | --- | --- |
| `ACTION_REQUIRED` | Cần hành động | Tạo ticket/OpsItem, thông báo owner, theo dõi deadline |
| `ACTION_MAY_BE_REQUIRED` | Có thể cần hành động | Triage, kiểm tra resource và runbook |
| `INFORMATIONAL` | Thông tin tham khảo | Ghi nhận hoặc gửi digest |

`personas` có thể chỉ ra nhóm stakeholder:

- `OPERATIONAL`: operations;
- `SECURITY`: security;
- `BILLING`: billing/finance.

Không phải mọi event đều có đầy đủ actionability/personas. Event pattern nên có nhánh fallback cho events thiếu metadata, thay vì silently drop chúng.

Có thể kết hợp event category, service, event type code, scope, actionability và persona để định tuyến. Ví dụ scheduled EC2 lifecycle event có `ACTION_REQUIRED` nên tới platform operations; AWS Health abuse/security event nên tới security response.

## 6. Đọc AWS Health Event schema

Khi event được phát lên EventBridge, envelope có các trường quan trọng:

| Field | Ý nghĩa |
| --- | --- |
| `version` | EventBridge event version |
| `id` | ID của EventBridge message |
| `detail-type` | Thường là `AWS Health Event` hoặc `AWS Health Abuse Event` |
| `source` | `aws.health` |
| `account` | Account nhận event |
| `region` | Region mà EventBridge notification được gửi tới |
| `time` | Thời điểm notification được gửi |
| `resources` | Resource IDs được liệt kê ở envelope nếu có |
| `detail` | Nội dung AWS Health event |

Trong `detail`:

| Field | Ý nghĩa |
| --- | --- |
| `eventArn` | ARN định danh Health event |
| `service` | AWS service bị ảnh hưởng |
| `eventTypeCode` | Mã loại event |
| `eventTypeCategory` | issue/accountNotification/investigation/scheduledChange |
| `eventScopeCode` | PUBLIC hoặc ACCOUNT_SPECIFIC |
| `communicationId` | ID của communication/page |
| `startTime`, `endTime` | Thời gian event bắt đầu/kết thúc nếu có |
| `lastUpdatedTime` | Lần cập nhật gần nhất |
| `statusCode` | upcoming/open/closed |
| `eventRegion` | Region thực sự bị ảnh hưởng |
| `eventDescription` | Ngôn ngữ và latestDescription |
| `affectedEntities` | Resource/entity IDs và trạng thái |
| `affectedAccount` | Account thực sự bị ảnh hưởng |
| `actionability` | Mức cần hành động nếu được cung cấp |
| `personas` | Nhóm stakeholder nếu được cung cấp |
| `page`, `totalPages` | Pagination cho danh sách resources/entities |

### Hai cặp field dễ nhầm

**`region` và `detail.eventRegion`:** `region` là Region nơi notification được gửi tới EventBridge; `eventRegion` là Region bị ảnh hưởng. Không dùng `region` để kết luận resource nằm ở Region nào.

**`account` và `detail.affectedAccount`:** trong organizational view, `account` có thể là management/delegated administrator account nhận feed, còn `affectedAccount` là account member thực sự bị ảnh hưởng. Luôn dùng đúng field cho routing và audit.

Với planned lifecycle events, affected entity status có thể là `PENDING`, `IMPAIRED`, `UNIMPAIRED`, `RESOLVED` hoặc `UNKNOWN`. AWS lưu ý cập nhật resource status được thực hiện bất đồng bộ; trong trường hợp hiếm có thể trễ tới 72 giờ.

## 7. EventBridge: kiến trúc notification và automation

Amazon EventBridge nhận AWS Health events và so khớp event pattern của rules. Khi event khớp, EventBridge gọi một hoặc nhiều targets.

~~~mermaid
flowchart LR
    Health[AWS Health] --> EB[EventBridge default bus]
    EB --> Rule1[Issue rule]
    EB --> Rule2[Scheduled change rule]
    EB --> Rule3[Security / billing rule]
    Rule1 --> SNS[Amazon SNS]
    Rule1 --> SQS[Amazon SQS]
    Rule2 --> Ops[Systems Manager OpsCenter]
    Rule2 --> Auto[SSM Automation]
    Rule3 --> Sec[Security / ITSM]
    SNS --> Email[Email / Chat]
    SQS --> Worker[Lambda / integration worker]
~~~

Targets có thể gồm SNS, SQS, Lambda, Step Functions, Systems Manager Automation và các dịch vụ tích hợp khác. Với chat notifications, có thể dùng Amazon Q Developer in chat applications theo cấu hình hỗ trợ hoặc tích hợp ITSM/partner.

Nên tách rules theo mục đích:
- Incident rules: `issue` events của services quan trọng;
- Change rules: `scheduledChange` hoặc `accountNotification` có `ACTION_REQUIRED`;
- Security rules: `AWS Health Abuse Event` hoặc persona `SECURITY`;
- Billing rules: persona `BILLING`;
- Informational rules: digest hoặc lưu trữ.

Không gửi mọi event tới một kênh paging có mức ưu tiên cao. Phân loại và routing giảm alert fatigue.

## 8. Tạo EventBridge event pattern cho operational issues

Ví dụ chỉ nhận issue events của EC2:

~~~json
{
  "source": ["aws.health"],
  "detail-type": ["AWS Health Event"],
  "detail": {
    "eventTypeCategory": ["issue"],
    "service": ["EC2"]
  }
}
~~~

Ví dụ nhận các event yêu cầu hành động liên quan scheduled changes/account notifications:

~~~json
{
  "source": ["aws.health"],
  "detail-type": ["AWS Health Event"],
  "detail": {
    "eventTypeCategory": [
      "accountNotification",
      "scheduledChange"
    ],
    "actionability": ["ACTION_REQUIRED"]
  }
}
~~~

Ví dụ nhận security persona:

~~~json
{
  "source": ["aws.health"],
  "detail-type": ["AWS Health Event"],
  "detail": {
    "personas": ["SECURITY"]
  }
}
~~~

Nếu muốn nhận cả public và account-specific events, dùng chính xác `source: ["aws.health"]`. Wildcard `aws.health*` không khớp theo cách mong muốn trong event pattern này.

EventBridge pattern là bộ lọc, không phải policy phân quyền. Quyền target, event bus, IAM role và resource policies vẫn cần được cấu hình riêng.

## 9. Tạo EventBridge rule bằng AWS CLI

Lưu event pattern vào file `health-issue-pattern.json`, sau đó tạo rule trong Region cần giám sát:

~~~bash
aws events put-rule \
  --name Health-EC2-Issues \
  --event-pattern file://health-issue-pattern.json \
  --state ENABLED \
  --description "Route EC2 AWS Health issue events"
~~~

Gắn SNS topic làm target:

~~~bash
aws events put-targets \
  --rule Health-EC2-Issues \
  --targets "Id"="NotifyOperations","Arn"="arn:aws:sns:ap-southeast-1:111122223333:operations-health"
~~~

EventBridge cần quyền publish tới SNS topic. Có thể cấp bằng SNS topic policy cho principal/service phù hợp và giới hạn `aws:SourceArn` theo rule ARN, cùng `aws:SourceAccount` khi phù hợp. Nếu target là Lambda, SQS hoặc Systems Manager Automation, cấu hình resource policy/role tương ứng.

Kiểm tra rule:

~~~bash
aws events describe-rule \
  --name Health-EC2-Issues

aws events list-targets-by-rule \
  --rule Health-EC2-Issues
~~~

EventBridge rule chỉ bắt đầu nhận event sau khi được bật và có đúng Region coverage. Khi tạo rule mới, public Health events có thể mất tới một giờ mới bắt đầu được gửi.

## 10. Region coverage và backup Region

AWS Health EventBridge integration có cách phân phối theo Region. Tổ chức cần chọn chiến lược phù hợp.

### Rule theo từng Region

Tạo rule ở từng Region mà workload cần theo dõi. Cách này rõ ràng về Region coverage và phù hợp khi cần lọc events theo Region.

### Backup Region

Trong AWS standard partition:
- US West (Oregon) là backup Region cho các Regions khác;
- US East (N. Virginia) là backup Region cho US West (Oregon).

Khi cấu hình high availability, tạo rule ở Region chính và backup Region. AWS có thể gửi cùng Health event tới cả hai nơi; consumer phải deduplicate bằng `eventArn` và `communicationId`.

Nếu không muốn nhận bản backup, lọc `detail.backupEvent` ở rule backup theo đúng kiểu dữ liệu trong payload. AWS Health event examples biểu diễn giá trị này dưới dạng chuỗi; event pattern tương ứng có dạng:

~~~json
{
  "detail": {
    "backupEvent": ["false"]
  }
}
~~~

Đừng bật backup mà không xử lý duplicate notifications.

### Simplified integration

Nếu chỉ cần account-specific events từ nhiều Regions trong standard partition và chấp nhận không có HA backup setup, có thể dùng simplified integration với rule trung tâm ở US West (Oregon). Cách này không nhận public events như AWS Health Dashboard và được khuyến nghị cho action-required account-specific events.

### Global events

Một số event không gắn với Region, ví dụ IAM global events. Để nhận global events, cần rule tại US East (N. Virginia).

Không áp dụng cùng một giả định Region cho mọi AWS partition. Kiểm tra partition và tài liệu AWS cho coverage thực tế.

## 11. Event delivery, duplicate và pagination

AWS Health gửi events tới EventBridge theo cơ chế durable delivery và cố gắng giao thành công ít nhất một lần. Vì vậy consumer phải chấp nhận duplicate.

Các nguyên nhân duplicate thường gặp:
- EventBridge retry;
- Rule ở primary và backup Regions;
- Một Health event có nhiều communications/updates;
- Một event có nhiều pages affected resources.

### Deduplication

Dùng combination của:
- `detail.affectedAccount`;
- `detail.eventArn`;
- `detail.communicationId`.

Nếu cần xử lý pages, giữ thêm `detail.page`. Không chỉ dùng EventBridge `id` vì backup copies có thể có EventBridge message IDs khác nhau cho cùng một Health event.

Lưu dedup keys trong DynamoDB/DB hoặc idempotency store với TTL phù hợp. Khi event status chuyển open → closed, cần xử lý update như một state transition, không coi đó là duplicate cần bỏ qua.

### Pagination

Nếu danh sách `resources` hoặc `affectedEntities` vượt giới hạn 256 KB của EventBridge, AWS Health chia event thành nhiều messages. Các page giữ cùng `eventArn` và `communicationId`; `page`/`totalPages` cho biết page hiện tại và tổng số page.

Consumer cần:
1. Lưu từng page;
2. Kiểm tra đã nhận đủ `totalPages`;
3. Reconstruct danh sách affected resources/entities;
4. Chỉ tạo một human notification hoặc OpsItem theo policy.

Với email/chat notification đơn giản, có thể lọc `page = 1` để tránh gửi nhiều tin nhắn cho cùng event; không làm vậy ở consumer cần xử lý đầy đủ affected resources.

## 12. AWS User Notifications: hai kiểu notification

AWS User Notifications cung cấp hai nhóm cần phân biệt.

### AWS managed notifications

AWS managed notifications do AWS Health phát ra. Người dùng có thể chọn categories, contacts và channels để nhận thông báo về events ảnh hưởng account/services. Các kênh hiện có thể bao gồm:
- Email;
- Chat;
- Push notification tới AWS Console Mobile Application;
- Console Notification Center.

Từ ngày 15/12/2025, AWS Health email delivery đã chuyển sang AWS managed notifications trong User Notifications. Email mới gửi từ `health@aws.com`; định dạng khác email plain-text cũ. Nếu tổ chức dùng email rules để lọc theo sender hoặc parse nội dung, phải cập nhật workflow.

AWS managed notifications có thể tổng hợp events ảnh hưởng nhiều accounts trong cùng AWS Organization thành notification chung khi đã cấu hình trusted access phù hợp.

**Public service events không có trong AWS managed notifications.** Để nhận public events, dùng EventBridge rule hoặc user-configured notification.

### User-configured notifications (UCNs)

UCN do khách hàng tạo dựa trên notification configurations. Có thể nhận notifications về CloudWatch alarms, Support cases và nhiều AWS service events qua:
- Console Notification Center;
- Email;
- Amazon Q Developer chat notifications;
- AWS Console Mobile App push;
- User Notifications API.

Để nhận UCN, cần chọn ít nhất một notification hub rồi tạo notification configuration. Notification hubs/configurations là cơ chế riêng của UCN, không phải điều kiện chung cho AWS managed notifications.

## 13. Chọn giữa AWS managed notifications, UCN và EventBridge

| Nhu cầu | Cơ chế nên xem xét |
| --- | --- |
| Muốn email/console notifications cho AWS Health categories | AWS managed notifications |
| Muốn nhận public service health events | EventBridge hoặc UCN |
| Muốn lọc notification theo custom event pattern và chọn channels | UCN |
| Muốn gọi Lambda/Step Functions/SSM Automation hoặc gửi SQS | EventBridge |
| Muốn kiểm soát dedup, enrichment, retries và ITSM payload | EventBridge + processing target |
| Muốn đọc đầy đủ affected entities/current status | AWS Health Dashboard, EventBridge hoặc AWS Health API |
| Muốn gom events toàn Organization | AWS Health organizational view, EventBridge organization feed hoặc managed notification aggregation |

AWS managed notifications giúp người nhận biết sự kiện; EventBridge phù hợp hơn khi cần logic tự động hóa, payload enrichment, deduplication và routing theo service/team.

Không giả định email notification chứa mọi affected resource IDs hoặc toàn bộ event history. Khi cần chi tiết, mở Health Dashboard/API hoặc lưu event payload từ EventBridge.

## 14. Notification routing theo team và mức độ ưu tiên

Một routing matrix có thể được thiết kế như sau:

| Điều kiện | Nhóm nhận | Kênh | Hành động |
| --- | --- | --- | --- |
| issue + critical service | On-call SRE | Pager/Chat + incident platform | Triage ngay |
| scheduledChange + ACTION_REQUIRED | Resource owner | Ticket + email | Lập kế hoạch trước deadline |
| personas có SECURITY | Security operations | Security queue + pager theo severity | Đánh giá exposure |
| personas có BILLING | FinOps/Billing | Email/Finance ticket | Kiểm tra account/billing |
| accountNotification | Account/platform owner | Ticket/digest | Xác minh hành động |
| INFORMATIONAL | Operations digest | Chat/email summary | Theo dõi |

Severity nội bộ không nên suy ra chỉ từ eventTypeCategory. Một scheduled change có thể gây rủi ro cao nếu resource critical; một issue công khai có thể chưa ảnh hưởng workload của tổ chức.

Enrichment nên bổ sung:
- Account name/environment;
- Application/service owner;
- Tags/cost center;
- Affected Region/AZ/resource;
- Runbook link;
- Maintenance deadline;
- Dashboard/alarms;
- Escalation policy.

## 15. AWS Organizations: organizational view

Với nhiều AWS accounts, xem từng Health Dashboard riêng lẻ sẽ khó theo dõi. AWS Health organizational view cho phép management account hoặc delegated administrator nhận một feed tổng hợp Health events từ các accounts trong AWS Organization.

~~~mermaid
flowchart TD
    Org[AWS Organizations] --> A1[Workload account A]
    Org --> A2[Workload account B]
    Org --> A3[Workload account C]
    A1 --> Feed[Health organizational view]
    A2 --> Feed
    A3 --> Feed
    Feed --> Admin[Management / delegated admin]
    Admin --> Rule[EventBridge rule]
    Rule --> Central[Central operations workflow]
~~~

Khi bật organizational view:
- Management account hoặc delegated administrator có thể xem event tập trung;
- EventBridge rule ở management/delegated admin account nhận organizational events;
- Event có thể chứa `account` là account nhận feed và `affectedAccount` là member account thực sự bị ảnh hưởng;
- EventBridge rules tại member accounts không bị tự động vô hiệu hóa;
- Nên có ownership rõ ràng để tránh duplicate workflows giữa centralized và local rules.

AWS cho phép đăng ký tối đa năm member accounts làm delegated administrators cho AWS Health organizational view. Nên delegate cho platform/operations account thay vì dùng management account cho mọi tác vụ vận hành.

Sau khi đăng ký, delegated administrator có thể xem các Health events ảnh hưởng Organization trong 90 ngày gần nhất hoặc từ thời điểm bật organizational view, tùy mốc nào gần hơn.

## 16. Bật delegated administrator và phân quyền

Từ management account, có thể đăng ký delegated administrator bằng AWS Organizations:

~~~bash
aws organizations register-delegated-administrator \
  --account-id 444455556666 \
  --service-principal health.amazonaws.com
~~~

Thay account ID bằng member account được chỉ định. Trước đó, cần bật organizational view/trusted access theo tài liệu AWS Health và Organizations.

Trusted access được bật riêng cho từng service. Trusted access của AWS Health không tự động bật trusted access cho AWS User Notifications; nếu muốn aggregation của managed notifications trong User Notifications, phải cấu hình trust riêng cho service đó.

Giới hạn quyền:
- Chỉ platform/operations delegated account được phép xem organization-wide events;
- Dùng IAM roles và federation cho operators;
- Không cấp quyền sửa Organizations cho người chỉ cần đọc Health events;
- Audit các thao tác register/remove delegated administrator;
- Khi gỡ delegated administrator, xác minh các workflows, EventBridge rules và API consumers trước.

## 17. AWS Health API: truy vấn sự kiện bằng code

AWS Health API là REST API dùng HTTPS và JSON. SDK/CLI hỗ trợ ký request bằng AWS Signature Version 4.

Các operation thường dùng:
- `DescribeEvents`: liệt kê events;
- `DescribeEventDetails`: lấy chi tiết event;
- `DescribeAffectedEntities`: lấy resource/entity bị ảnh hưởng;
- Các operation organizational view: truy vấn events/affected entities trong AWS Organization.

**Điều kiện truy cập:** AWS Health API yêu cầu AWS Business Support+, AWS Enterprise Support hoặc AWS Unified Operations. Ở Regions chưa cung cấp/chưa chuyển sang các support plans này, có thể vẫn dùng Business, Enterprise On-Ramp hoặc Enterprise Support theo transition rules. Account không đủ support plan sẽ nhận `SubscriptionRequiredException`.

AWS Health Dashboard trong console và EventBridge event integration có thể được dùng theo availability của chúng mà không đồng nghĩa mọi account đều có quyền gọi AWS Health API.

### Endpoint active/passive

AWS Health API có kiến trúc multi-Region active/passive:
- Active endpoint mặc định: `health.us-east-1.amazonaws.com`;
- Passive endpoint mặc định: `health.us-east-2.amazonaws.com`;
- Global endpoint: `global.health.amazonaws.com`.

Dùng DNS lookup global endpoint để xác định Region active và ký request theo signing Region tương ứng. Passive endpoint có thể trả data nhưng eventually consistent; dữ liệu mới nhất chỉ có trên active endpoint. Khi active endpoint thay đổi, workflow nên xác định lại endpoint và khởi động lại các truy vấn đang chạy.

Không hardcode active Region vĩnh viễn trong ứng dụng production.

## 18. AWS Health API: IAM và xử lý dữ liệu

Dùng temporary credentials từ IAM role/STS thay vì long-term access keys. Không dùng root access keys cho truy cập thường xuyên.

API response có pagination. Luôn đọc `nextToken` và tiếp tục gọi tới khi hết trang. Với organizational queries, lượng dữ liệu có thể lớn; dùng time filters, event scope, service filters và page size phù hợp.

Mô hình xử lý:
1. Poll/consume events;
2. Persist raw event payload;
3. Normalize event fields;
4. Deduplicate;
5. Enrich bằng account/resource metadata;
6. Route tới OpsCenter/ITSM;
7. Update event status khi có communication mới;
8. Retain event history theo audit policy.

Không ghi toàn bộ raw payload vào ticket/chat nếu chứa resource metadata nhạy cảm. Giữ reference/event ARN và link tới nơi có quyền truy cập.
## 19. Systems Manager OpsCenter: quản lý OpsItems

OpsCenter là công cụ Systems Manager để theo dõi và quản lý các vấn đề vận hành dưới dạng **OpsItems**.

OpsItem thường chứa:
- Title và description;
- Source;
- Priority;
- Status;
- Affected/related resources;
- Operational data;
- Related OpsItems;
- Runbooks có thể chạy;
- Owner/tags và thông tin điều tra.

OpsCenter giúp đội vận hành tập trung các công việc cần xử lý từ nhiều AWS services. Nó không phải hệ thống paging/incident command hoàn chỉnh.

Explorer là dashboard vận hành có thể tổng hợp thông tin về AWS resources và OpsItems. OpsCenter cung cấp Summary, OpsItems list và OpsItem details để theo dõi trạng thái và runbooks.

## 20. Thiết lập OpsCenter và hiểu chi phí

AWS Systems Manager cung cấp Integrated Setup cho OpsCenter và Explorer. Quy trình setup tích hợp này hiện thực hiện trong Systems Manager console, không phải workflow cấu hình programmatic đầy đủ.

Khi bật OpsCenter, các EventBridge rules mặc định có thể tự tạo OpsItems cho các tình huống như:
- Auto Scaling instance launch/termination failure;
- EBS snapshot creation/copy failure;
- EBS volume performance issue;
- EC2 issue/scheduled change;
- RDS issue/scheduled change;
- Systems Manager Maintenance Window execution failure/timeout.

**Chi phí:** OpsItems được tạo bởi default rules có thể phát sinh charges. Sau khi enable, kiểm tra danh sách EventBridge rules, tần suất tạo OpsItems, deduplication và pricing. Tắt những rules không cần thiết; không bật hàng loạt chỉ vì console đề xuất.

Tài liệu setup có các bước:
1. Mở Systems Manager console;
2. Chọn OpsCenter;
3. Chọn Get started;
4. Bật tùy chọn Integrated Setup để cấu hình Explorer và default rules nếu cần;
5. Chọn Enable OpsCenter;
6. Kiểm tra OpsItem rules, operational insights và CloudWatch alarm integration.

## 21. OpsItem lifecycle, priority và deduplication

OpsCenter theo dõi OpsItems từ lúc tạo tới khi resolved. Operator có thể:
- Tạo OpsItem thủ công;
- Cập nhật status/priority/description;
- Thêm related resources;
- Thêm operational data;
- Liên kết OpsItems liên quan;
- Xem runbooks đã chạy và runbooks có thể chạy;
- Xem operational insights và duplicate items.

### Deduplication

OpsCenter dùng logic built-in và configurable deduplication strings. Khi CreateOpsItem được gọi, Systems Manager tạo hash dựa trên deduplication string và resource khởi tạo. Nếu OpsItem trùng đang ở trạng thái Open hoặc In Progress, hệ thống không tạo item mới; nếu item cũ đã Resolved, một OpsItem mới có thể được tạo.

Một deduplication key nên đại diện cùng một loại vấn đề trên cùng resource, ví dụ:
- Source/service;
- Event type;
- Resource ID;
- Environment.

Không dùng event message text thay đổi theo từng update làm dedup key. Không gộp hai vấn đề độc lập chỉ vì chúng cùng service.

## 22. Tạo OpsItem bằng AWS CLI

Ví dụ tạo OpsItem cho EC2 instance cần kiểm tra:

~~~bash
aws ssm create-ops-item \
  --title "EC2 instance retirement - review required" \
  --description "AWS Health reports a scheduled retirement. Review affected instance and execute the approved migration runbook." \
  --source "aws.health" \
  --priority 2 \
  --operational-data file://opsitem-data.json \
  --notifications Arn=arn:aws:sns:ap-southeast-1:111122223333:operations-health \
  --tags Key=Environment,Value=prod Key=Owner,Value=platform
~~~

Ví dụ `opsitem-data.json`:

~~~json
{
  "/aws/dedup": {
    "Value": "{\"dedupString\":\"EC2-retirement-prod-i-0123456789abcdef0\"}",
    "Type": "SearchableString"
  },
  "healthEventArn": {
    "Value": "arn:aws:health:ap-southeast-1::event/EC2/example-event",
    "Type": "SearchableString"
  },
  "changeWindow": {
    "Value": "2026-12-01T02:00:00Z",
    "Type": "SearchableString"
  }
}
~~~

Thay event ARN, resource ID, deadline và account/Region bằng dữ liệu thực từ event. CLI shape cho operational data cần được xác minh theo AWS CLI version đang dùng.

OpsItem có thể được tạo qua EventBridge target/integration hoặc một Lambda consumer có quyền `ssm:CreateOpsItem`. Nếu dùng custom consumer, implement idempotency trước khi gọi CreateOpsItem.

## 23. Từ AWS Health event tới OpsCenter

Một integration có thể dùng EventBridge rule lọc action-required scheduled changes, rồi tạo OpsItem.

~~~mermaid
sequenceDiagram
    participant H as AWS Health
    participant E as EventBridge
    participant L as Lambda / integration
    participant O as OpsCenter
    participant R as Resource owner
    H->>E: scheduledChange / ACTION_REQUIRED
    E->>L: Matching event
    L->>L: Deduplicate and enrich
    L->>O: CreateOpsItem
    O-->>R: Assigned operational work
    R->>O: Update status / add notes
    R->>O: Run approved Automation
    O-->>R: Record outcome and resolve
~~~

Consumer nên:
- Map `affectedAccount` tới account owner;
- Map `eventRegion` tới Region owner;
- Chọn affected entity/resource;
- Đưa `eventArn`, `communicationId`, event type, deadline và latest description vào operational data;
- Tạo dedup key ổn định;
- Gắn runbook và dashboard links;
- Đặt priority theo impact/deadline;
- Không tự đóng OpsItem chỉ vì một event update tới `closed` nếu remediation nội bộ chưa xác minh.

## 24. Systems Manager Automation: runbook vận hành

Systems Manager Automation chạy Automation documents để thực hiện tác vụ trên AWS resources hoặc managed nodes.

Use cases:
- Kiểm tra instance state/configuration;
- Stop/start instance theo scheduled retirement runbook đã được phê duyệt;
- Tạo snapshot trước maintenance;
- Thu thập diagnostics;
- Restart service theo điều kiện;
- Thực hiện remediation cho một số cấu hình chuẩn;
- Chạy pre-check/post-check cho maintenance.

AWS Health scheduled events có thể kích hoạt EventBridge rule rồi gọi Systems Manager Automation document. AWS có ví dụ tự động stop/start EC2 instance khi nhận event retirement.

Không nên tự động restart/terminate resource chỉ vì event có category scheduledChange. Hãy kiểm tra event type code, affected resource, workload criticality, Auto Scaling/ASG membership, backup, application readiness và maintenance policy trước khi hành động.

## 25. Guardrails cho automation

Một runbook production nên có:

- **Preconditions:** resource tồn tại, đúng account/Region, đúng tag và trạng thái cho phép;
- **Allowlist:** chỉ xử lý resource types/event codes được duyệt;
- **Approval:** manual approval cho actions destructive hoặc có downtime;
- **Rate limits:** giới hạn concurrency và số resources mỗi execution;
- **Idempotency:** chạy lại không gây hỏng trạng thái;
- **Timeout/retry:** có giới hạn và backoff;
- **Rollback/recovery:** xác định cách quay lại trạng thái trước;
- **Post-check:** xác minh service health sau automation;
- **Audit:** lưu Automation execution ID, actor, parameters và outputs;
- **Escalation:** nếu precondition fail hoặc automation lỗi thì tạo/giữ OpsItem và báo owner.

IAM role của EventBridge/Automation chỉ được cấp các actions cần thiết. Dùng resource ARN/tag conditions khi service hỗ trợ. `iam:PassRole` phải giới hạn vào Automation role cụ thể và service được phép assume.

## 26. Incident response: từ event tới khôi phục

AWS Health event là một input cho incident response. Tổ chức cần quy trình nội bộ để biến tín hiệu thành hành động.

~~~mermaid
flowchart TD
    Detect[Detect: Health / alarms / customer reports] --> Triage[Triage impact and scope]
    Triage --> Declare{Incident threshold met?}
    Declare -->|No| Work[Track as OpsItem / planned work]
    Declare -->|Yes| Lead[Declare incident / assign commander]
    Lead --> Comms[Notify responders and stakeholders]
    Comms --> Mitigate[Mitigate / failover / rollback]
    Mitigate --> Recover[Restore service]
    Recover --> Validate[Validate SLI / customer impact]
    Validate --> Close[Close incident]
    Close --> PIR[Post-incident review / actions]
    Work --> Close
~~~

Các bước:

1. **Detect:** AWS Health, CloudWatch alarms, Application Signals, logs, traces hoặc customer reports.
2. **Triage:** xác định service, account, Region, resource, blast radius và customer impact.
3. **Declare:** dùng severity/incident criteria nội bộ để quyết định mở incident.
4. **Assign roles:** incident commander, technical lead, communications lead, scribe và service owner.
5. **Communicate:** cập nhật status page/chat/ticket theo cadence.
6. **Mitigate:** giảm impact bằng failover, traffic shift, rollback, capacity change hoặc workaround.
7. **Recover:** khôi phục dependencies và backlog.
8. **Validate:** kiểm tra SLI, business transactions và data integrity.
9. **Close:** xác nhận service ổn định và stakeholder được thông báo.
10. **Review:** post-incident review, root cause/contributing factors và corrective actions.

Không kết thúc incident chỉ vì AWS Health event chuyển `closed`. Phải xác minh workload thực tế đã phục hồi.

## 27. Incident Manager: thay đổi availability cần biết

AWS Systems Manager Incident Manager đã ngừng nhận khách hàng mới kể từ **07/11/2025** và AWS không bổ sung tính năng/capability mới. Khách hàng đã bật Incident Manager trước ngày này có thể tiếp tục sử dụng dịch vụ trong các accounts đã enable.

Điều này ảnh hưởng cách lựa chọn công cụ:
- Với khách hàng mới, không thiết kế kiến trúc dựa trên giả định có thể enable Incident Manager;
- Với khách hàng hiện hữu, có thể tiếp tục dùng nhưng nên đánh giá migration plan;
- AWS khuyến nghị Systems Manager OpsCenter cho việc quản lý operational issues trên AWS infrastructure;
- Với automated paging/incident response capabilities, AWS khuyến nghị xem xét giải pháp từ AWS Partner Network;
- Có thể tích hợp Jira Service Management, ServiceNow, PagerDuty và các nền tảng incident/ITSM phù hợp.

OpsCenter quản lý OpsItems và operational work; nó không tự thay thế mọi chức năng paging, escalation, on-call schedules, incident commander và stakeholder communications của một incident platform.

Nếu đang migrate khỏi Incident Manager:
1. Export incident data để phân tích/lưu trữ;
2. Map response plans/on-call contacts/runbooks sang hệ thống đích;
3. Chuyển EventBridge/SNS integrations;
4. Test paging, escalation và incident lifecycle;
5. Chuyển dữ liệu/tài liệu cần giữ;
6. Sau khi migration hoàn tất, dọn resources Incident Manager còn lại để tránh charges.

## 28. Chọn giải pháp incident management

| Nhu cầu | AWS-native building blocks | Giải pháp bổ sung có thể cần |
| --- | --- | --- |
| Nhận AWS Health events | AWS Health + EventBridge | — |
| Email/chat/push notification | AWS User Notifications, SNS, Amazon Q Developer chat integrations | — |
| Theo dõi operational work | Systems Manager OpsCenter | Jira/ServiceNow nếu workflow doanh nghiệp cần |
| Tự động hóa remediation | Systems Manager Automation | — |
| On-call schedules và paging | EventBridge/SNS integration | PagerDuty hoặc APN partner |
| Incident commander và timeline | Ticket/chat/automation integrations | ServiceNow, Jira Service Management hoặc incident platform |
| Customer communications/status page | Notification integrations | Status-page/communications platform |

Chọn theo yêu cầu về on-call scheduling, escalation policy, acknowledgement, audit, chatops, incident timeline, integrations và compliance. Không chọn chỉ dựa trên việc một công cụ có thể nhận SNS notification.

## 29. Kết hợp AWS Health với CloudWatch alarms và observability

AWS Health cho biết AWS đã công bố event; CloudWatch/observability cho biết workload có biểu hiện bất thường hay không.

Ví dụ:
- AWS Health: RDS planned maintenance;
- CloudWatch: DB connections giảm và API latency tăng;
- Logs: connection reset;
- Traces: span database client timeout;
- OpsCenter: OpsItem liên kết RDS resource;
- Runbook: kiểm tra failover/maintenance state;
- Incident platform: mở incident nếu customer SLI vượt error budget policy.

Nên hiển thị AWS Health event cùng:
- Account/Region/service/resource;
- CloudWatch alarms;
- Service dashboard;
- Application Signals/trace search;
- Deployment/maintenance timeline;
- OpsItem/incident/ticket link;
- Owner và runbook.

Một AWS Health event không nhất thiết đồng nghĩa workload đang down. Cần đối chiếu service health và application telemetry trước khi quyết định severity.

## 30. IAM và security cho Health notification workflows

Tách roles theo trách nhiệm:

| Identity | Quyền |
| --- | --- |
| EventBridge service role | Invoke targets được chỉ định |
| Lambda integration role | Đọc event, enrich, tạo OpsItems hoặc gọi downstream API |
| SSM Automation role | Thực hiện actions trong Automation document |
| Operator role | Xem Health/OpsItems, cập nhật trạng thái, chạy runbooks được phép |
| Organization delegated admin | Xem organizational Health events theo delegated permissions |
| ITSM integration role | Publish/query trong hệ thống tích hợp theo API scope |

Security practices:
- Không cấp AdministratorAccess cho notification Lambda;
- Hạn chế `ssm:CreateOpsItem`, `ssm:UpdateOpsItem`, `ssm:StartAutomationExecution` theo use case;
- Scope `iam:PassRole` vào Automation role cụ thể;
- Dùng resource policies cho SNS/SQS/Lambda targets;
- Dùng Secrets Manager/Parameter Store cho API tokens của ITSM;
- Mã hóa queues/logs và giới hạn retention;
- Không đưa credentials, customer PII hoặc secret values vào event enrichment;
- Audit role assumptions, Automation executions và OpsItem updates bằng CloudTrail;
- Kiểm soát quyền xem event descriptions và affected resource IDs.

Event payload có thể chứa resource identifiers và mô tả operational context. Chỉ gửi tới người/nhóm có quyền cần thiết.

## 31. Cost, quotas và operational hygiene

Chi phí có thể đến từ:
- OpsItems tạo bởi default EventBridge rules;
- EventBridge events/rules/targets theo usage;
- SNS, SQS, Lambda và Step Functions;
- Systems Manager Automation executions;
- Logs, metrics và audit storage;
- Third-party ITSM/on-call integrations.

Kiểm soát:
- Chỉ bật default OpsItem rules cần thiết;
- Dùng deduplication để tránh nhiều OpsItems cho một issue;
- Lọc INFORMATIONAL khỏi paging;
- Gộp notification theo service/event/account;
- Có TTL cho idempotency records;
- Giới hạn retry/DLQ và theo dõi failed invocations;
- Theo dõi Automation execution volume;
- Định kỳ review event patterns và stale rules;
- Kiểm tra pricing và quotas theo Region.

Không tạo một OpsItem cho từng duplicate EventBridge delivery. Không tự động chạy remediation hàng loạt khi chưa kiểm tra blast radius.

## 32. Troubleshooting AWS Health notifications

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Không nhận Health event | Rule sai Region hoặc event pattern không khớp | Kiểm tra source, detail-type, service/category và Region |
| Không thấy public event | Rule vừa tạo, chưa đủ thời gian; thiếu rule ở impacted Region | Chờ thời gian propagation và kiểm tra Region coverage |
| Chỉ thấy một phần account events | Chưa bật organizational view/trusted access | Kiểm tra Organizations, delegated admin và Health org view |
| Event bị gửi hai lần | Primary/backup rules hoặc at-least-once delivery | Deduplicate bằng affectedAccount/eventArn/communicationId |
| Thiếu affected resources | Event nhiều pages hoặc public event không có resource list | Kiểm tra page/totalPages, Dashboard/API |
| Sai Region trong ticket | Dùng envelope region thay eventRegion | Map detail.eventRegion |
| Sai account owner | Dùng account thay affectedAccount trong organizational view | Map detail.affectedAccount |
| Event pattern bỏ sót security event | Chỉ lọc AWS Health Event | Xem AWS Health Abuse Event và security persona |
| AWS managed email không tới | Contacts/categories/channels chưa cấu hình | Kiểm tra User Notifications subscriptions và account contacts |
| Public event không tới managed email | Public events không được gửi qua managed notifications | Dùng EventBridge hoặc UCN |
| Email parsing bị lỗi | AWS Health email migration từ 15/12/2025 | Cập nhật sender health@aws.com và parser format |
| Health API trả SubscriptionRequiredException | Support plan không đủ | Kiểm tra AWS Support plan/Region transition |
| Health API dữ liệu stale | Gọi passive endpoint | Resolve global endpoint và ký request đúng active Region |
| OpsItem bị duplicate | Dedup string/resource không ổn định | Kiểm tra /aws/dedup và EventBridge input transformer |
| Không tạo được OpsItem | Lambda/EventBridge role thiếu permission | Kiểm tra ssm:CreateOpsItem và target role |
| Automation target không chạy | Managed node, trust hoặc PassRole thiếu | Kiểm tra SSM Agent, IAM role, trust và Automation execution |
| EventBridge target lỗi | Resource policy hoặc retry/target configuration sai | Kiểm tra rule metrics, DLQ và target permissions |
| Incident không được paging | Notification tới chat/email nhưng chưa tích hợp on-call platform | Kiểm tra acknowledgement/escalation workflow |

### Quy trình điều tra

~~~text
1. Xác nhận AWS account, Region và event scope.
2. Mở AWS Health Dashboard để xác minh event có tồn tại.
3. Kiểm tra EventBridge rule pattern và Region coverage.
4. Kiểm tra event sample, detail.eventRegion và affectedAccount.
5. Kiểm tra rule metrics, target invocation và DLQ.
6. Kiểm tra duplicate keys, page/totalPages và backupEvent.
7. Kiểm tra SNS/SQS/Lambda resource policy và IAM role.
8. Kiểm tra User Notifications contacts, channels và notification hub nếu là UCN.
9. Nếu dùng AWS Health API, kiểm tra Support plan, endpoint active và SigV4 signing Region.
10. Nếu OpsItem không được tạo, kiểm tra ssm:CreateOpsItem và deduplication.
11. Nếu Automation fail, đọc Automation execution steps và CloudTrail.
12. Cập nhật runbook, rule filters và escalation ownership.
~~~

## 33. Lab: AWS Health → EventBridge → SNS → OpsCenter

### Kịch bản

Một workload production chạy EC2 và RDS ở `ap-southeast-1`. Platform team muốn nhận scheduled changes/issue events, gửi thông báo operations và tạo OpsItem cho các event cần hành động.

### Bước 1 — Xác minh event pattern

Tạo file `health-action-required.json`:

~~~json
{
  "source": ["aws.health"],
  "detail-type": ["AWS Health Event"],
  "detail": {
    "eventTypeCategory": [
      "issue",
      "accountNotification",
      "scheduledChange"
    ],
    "actionability": [
      "ACTION_REQUIRED",
      "ACTION_MAY_BE_REQUIRED"
    ]
  }
}
~~~

Trong production, có thể tách issue rules và scheduled-change rules để routing khác nhau. Kiểm tra sample events bằng EventBridge Test event pattern.

### Bước 2 — Tạo rule

~~~bash
aws events put-rule \
  --name Health-Action-Required \
  --event-pattern file://health-action-required.json \
  --state ENABLED
~~~

Tạo rule ở từng Region cần theo dõi hoặc dùng simplified integration khi phù hợp với account-specific events. Nếu bật backup Region, triển khai deduplication.

### Bước 3 — Thêm SNS target

~~~bash
aws events put-targets \
  --rule Health-Action-Required \
  --targets "Id"="OpsEmail","Arn"="arn:aws:sns:ap-southeast-1:111122223333:operations-health"
~~~

Cấu hình SNS topic policy cho EventBridge và subscribe email/chat integration. Xác nhận subscription và kiểm thử notification delivery.

### Bước 4 — Tạo OpsItem integration

Dùng Lambda hoặc integration target để:
- Deduplicate event;
- Lấy affectedAccount/eventRegion;
- Chọn affected resource;
- Tạo OpsItem nếu actionability phù hợp;
- Gắn event ARN, communication ID, deadline và runbook link;
- Gửi ticket link tới service owner.

### Bước 5 — Kiểm thử bằng sample event

Dùng EventBridge sample event tương thích AWS Health schema. Không chờ một AWS Health production incident thật để test pipeline.

Xác minh:
- Rule match;
- SNS nhận event;
- Notification tới đúng team;
- Consumer tạo một OpsItem;
- Duplicate sample không tạo OpsItem thứ hai;
- closed update được xử lý đúng;
- Failed target được retry/DLQ;
- CloudTrail ghi lại các actions.

### Bước 6 — Chạy runbook trong sandbox

Dùng một Automation document không phá hủy để thu thập trạng thái instance hoặc kiểm tra prerequisites. Chỉ thử stop/start/reboot trên test instance đã được phép. Ghi execution ID và post-check results vào OpsItem.

## 34. Bài tập và câu hỏi tự kiểm tra

### Bài tập 1 — Public event và account-specific event

Một public EC2 operational issue xuất hiện ở `us-east-1`; account cũng có EC2 instance retirement ở `ap-southeast-1`.

**Yêu cầu:** Phân biệt event scope/category, xác định event nào gắn resource cụ thể và chọn notification route khác nhau.

### Bài tập 2 — Region coverage và duplicate

Tổ chức tạo EventBridge rules ở primary Region và Oregon backup Region.

**Yêu cầu:** Giải thích vì sao nhận duplicate, chọn deduplication key và giải thích vai trò backupEvent, eventArn, communicationId, eventRegion.

### Bài tập 3 — Organizational view

Có 40 AWS accounts và platform team muốn nhận một feed tập trung.

**Yêu cầu:** Thiết kế organizational view, management/delegated administrator, trusted access và EventBridge central rule. Giải thích khác biệt giữa account và affectedAccount.

### Bài tập 4 — User Notifications

Team trước đây parse plain-text AWS Health email để mở ticket. Sau 15/12/2025 workflow bị lỗi.

**Yêu cầu:** Mô tả email migration, thay đổi sender/format và đề xuất EventBridge hoặc UCN để tạo workflow ổn định.

### Bài tập 5 — OpsItem deduplication

Một Health event được gửi qua hai Regions và tạo hai OpsItems cho cùng EC2 instance.

**Yêu cầu:** Thiết kế deduplication string, giải thích behavior khi OpsItem cũ Open/In Progress/Resolved và cách lưu event communication history.

### Bài tập 6 — Automation an toàn

AWS Health báo EC2 instance retirement scheduled. Team muốn tự động stop/start instance.

**Yêu cầu:** Xác minh event type code, EBS-backed/instance-store behavior, managed node prerequisites, Automation role, PassRole, preconditions và post-check. Chỉ ra điều kiện cần manual approval.

### Bài tập 7 — Incident Manager availability

Một dự án mới dự định sử dụng Systems Manager Incident Manager; một account cũ đã enable Incident Manager trước 07/11/2025.

**Yêu cầu:** Đưa ra phương án khác nhau cho hai trường hợp, so sánh OpsCenter với on-call/ITSM partner solution và lập migration checklist.

### Bài tập 8 — AWS Health API

Một integration gọi DescribeEvents và nhận SubscriptionRequiredException.

**Yêu cầu:** Kiểm tra Support plan, endpoint active/passive, SigV4 signing Region và pagination.

### Câu hỏi ngắn

1. **AWS Health cung cấp gì?** Thông tin về events ảnh hưởng AWS services, accounts và resources.
2. **Public event khác account-specific event thế nào?** Public phản ánh service health theo Region; account-specific gắn với account/resources.
3. **Các event categories chính là gì?** issue, accountNotification, investigation và scheduledChange.
4. **eventScopeCode có giá trị nào?** PUBLIC hoặc ACCOUNT_SPECIFIC.
5. **actionability có các giá trị nào?** ACTION_REQUIRED, ACTION_MAY_BE_REQUIRED và INFORMATIONAL.
6. **personas hỗ trợ routing nào?** OPERATIONAL, SECURITY và BILLING.
7. **region khác eventRegion thế nào?** Region notification được gửi; eventRegion là Region bị ảnh hưởng.
8. **account khác affectedAccount thế nào?** Account nhận feed; affectedAccount là account bị ảnh hưởng.
9. **EventBridge delivery có exactly-once không?** Không; consumer cần idempotency/deduplication.
10. **Public events có thể mất bao lâu để bắt đầu gửi sau khi tạo rule?** Có thể tới một giờ.
11. **Vì sao có backup Region?** Tăng độ tin cậy khi primary Region gặp sự cố.
12. **Dedup key nên gồm gì?** affectedAccount, eventArn và communicationId; thêm page khi reconstruct pagination.
13. **AWS managed notifications có gửi public events không?** Không.
14. **AWS Health email chuyển sang User Notifications từ ngày nào?** 15/12/2025.
15. **UCN cần gì để hoạt động?** Notification hub và notification configuration.
16. **Organizational view dùng để làm gì?** Tổng hợp Health events trên AWS Organization.
17. **Có thể đăng ký tối đa bao nhiêu Health delegated administrators?** Năm member accounts.
18. **AWS Health API yêu cầu support plan nào?** Business Support+, Enterprise Support hoặc Unified Operations theo availability/transition của Region.
19. **OpsCenter quản lý gì?** OpsItems và operational work.
20. **OpsItem deduplication hoạt động thế nào?** So khớp dedup key/resource; Open/In Progress item trùng sẽ không tạo thêm.
21. **SSM Automation dùng để làm gì?** Chạy runbooks cho tác vụ vận hành.
22. **Incident Manager ngừng nhận khách hàng mới từ ngày nào?** 07/11/2025.
23. **AWS khuyến nghị gì cho operational issues của khách hàng mới?** Systems Manager OpsCenter.
24. **OpsCenter thay thế đầy đủ paging/on-call schedules không?** Không; có thể cần APN incident/on-call solution.
25. **Đóng AWS Health event có nghĩa workload đã phục hồi không?** Không; phải xác minh bằng application telemetry và business checks.

## 35. Checklist trước production

- [ ] Đã xác định Health Dashboard, EventBridge, User Notifications và OpsCenter phục vụ vai trò nào.
- [ ] Public events và account-specific events được phân biệt trong routing.
- [ ] Event categories, scope, status, actionability và personas được xử lý.
- [ ] Mapping region/eventRegion và account/affectedAccount chính xác.
- [ ] EventBridge rules được tạo ở đủ Regions cần theo dõi.
- [ ] Backup Region strategy và backupEvent filter được kiểm tra.
- [ ] Consumer xử lý at-least-once delivery và deduplication.
- [ ] Pagination page/totalPages được xử lý nếu cần affected entities đầy đủ.
- [ ] Event patterns được test bằng sample events.
- [ ] EventBridge targets có IAM/resource policies và DLQ phù hợp.
- [ ] AWS managed notifications contacts/channels được cấu hình.
- [ ] UCN có notification hub và notification configurations cần thiết.
- [ ] Public events được định tuyến qua EventBridge hoặc UCN.
- [ ] Email parser đã thích ứng migration từ 15/12/2025.
- [ ] Organizational view/trusted access/delegated administrator được cấu hình đúng.
- [ ] AWS Health API support plan, active endpoint và SigV4 Region được kiểm tra nếu dùng.
- [ ] OpsCenter default rules, OpsItem volume và pricing đã được review.
- [ ] OpsItem deduplication, ownership, priority và lifecycle được định nghĩa.
- [ ] SSM Automation runbooks có preconditions, allowlist, approvals và post-check.
- [ ] IAM roles least privilege; iam:PassRole được scope chặt.
- [ ] Incident severity, commander, paging, escalation và communication cadence được xác định.
- [ ] Có incident platform/partner solution nếu cần paging và automated response.
- [ ] Incident Manager availability được đánh giá cho account hiện hữu/mới.
- [ ] Có export/migration plan nếu đang dùng Incident Manager.
- [ ] Logs, CloudTrail, Automation execution IDs và ticket links được lưu audit.
- [ ] Notification pipeline có retry, DLQ, dashboards và runbook.
- [ ] Test event được dùng để kiểm tra end-to-end mà không chờ sự cố thật.

## 36. Tổng kết

AWS Health là nguồn tín hiệu về service health, account notifications, operational issues và planned lifecycle events. AWS Health Dashboard giúp con người xem event; EventBridge biến event thành trigger cho notification và automation; AWS User Notifications cung cấp các kênh email/chat/push/console; Systems Manager OpsCenter quản lý OpsItems; Systems Manager Automation chạy runbooks đã được kiểm soát.

Thiết kế đáng tin cậy cần phân biệt public với account-specific events, đọc đúng event scope/category/actionability/persona, xử lý eventRegion/affectedAccount, Region coverage, backup delivery, duplicate messages và pagination. Với AWS Organizations, organizational view và delegated administrator giúp tập trung event mà vẫn giữ ranh giới trách nhiệm. AWS Health API chỉ dùng được khi account có Support plan phù hợp và phải theo dõi active/passive endpoint.

Incident response là quy trình của tổ chức: detect, triage, declare, assign, communicate, mitigate, recover, validate và review. OpsCenter hỗ trợ operational work; Automation hỗ trợ remediation; paging/on-call/incident command có thể cần partner platform. Incident Manager đã ngừng nhận khách hàng mới từ 07/11/2025, nên kiến trúc mới cần chọn giải pháp hiện hành phù hợp.

Những điểm cần nhớ:

1. AWS Health event là tín hiệu; không tự kết luận workload đã down hoặc đã phục hồi.
2. EventBridge delivery ít nhất một lần; thiết kế idempotency và deduplication.
3. region khác eventRegion; account khác affectedAccount.
4. AWS managed notifications không gửi public events; dùng EventBridge hoặc UCN cho public events.
5. AWS Health email đã chuyển sang User Notifications từ 15/12/2025.
6. Organizational view và delegated administrator giúp quản lý multi-account Health events.
7. OpsCenter quản lý OpsItems; Automation chạy runbooks với IAM guardrails.
8. Incident Manager không nhận khách hàng mới từ 07/11/2025; OpsCenter và APN incident solutions là các hướng thay thế được AWS nêu.
9. Mọi incident phải kết thúc bằng xác minh workload và post-incident learning, không chỉ dựa vào trạng thái AWS Health.

### Tài liệu chính thức

- [AWS Health User Guide](https://docs.aws.amazon.com/health/latest/ug/what-is-aws-health.html)
- [AWS Health Dashboard](https://docs.aws.amazon.com/health/latest/ug/getting-started-health-dashboard.html)
- [Monitoring events in AWS Health with EventBridge](https://docs.aws.amazon.com/health/latest/ug/cloudwatch-events-health.html)
- [Configuring EventBridge rules for AWS Health](https://docs.aws.amazon.com/health/latest/ug/creating-event-bridge-events-rule-for-aws-health.html)
- [AWS Health EventBridge schema](https://docs.aws.amazon.com/health/latest/ug/aws-health-events-eventbridge-schema.html)
- [AWS Health Region coverage and backup Regions](https://docs.aws.amazon.com/health/latest/ug/choosing-a-region.html)
- [AWS Health organizational view](https://docs.aws.amazon.com/health/latest/ug/aggregating-health-events.html)
- [Delegated administrator for AWS Health](https://docs.aws.amazon.com/health/latest/ug/delegated-administrator-organizational-view.html)
- [AWS Health API access and endpoints](https://docs.aws.amazon.com/health/latest/ug/health-api.html)
- [AWS managed notifications in User Notifications](https://docs.aws.amazon.com/health/latest/ug/manage-user-notifications.html)
- [User-configured notifications](https://docs.aws.amazon.com/notifications/latest/userguide/uc-notifications.html)
- [Systems Manager OpsCenter setup](https://docs.aws.amazon.com/systems-manager/latest/userguide/OpsCenter-setup.html)
- [Manage OpsItems](https://docs.aws.amazon.com/systems-manager/latest/userguide/OpsCenter-working-with-OpsItems.html)
- [OpsItem deduplication](https://docs.aws.amazon.com/systems-manager/latest/userguide/OpsCenter-working-deduplication.html)
- [Automating EC2 operations from AWS Health events](https://docs.aws.amazon.com/health/latest/ug/automating-instance-actions.html)
- [Incident Manager availability change](https://docs.aws.amazon.com/incident-manager/latest/userguide/incident-manager-availability-change.html)
- [Incident Manager migration guides](https://docs.aws.amazon.com/incident-manager/latest/userguide/migration-guides.html)

**Lưu ý vận hành:** AWS Health event schemas, notification channels, Support plans, delegated administrator setup, Systems Manager pricing và partner integrations có thể thay đổi. Trước production, xác minh service availability trong account/Region, kiểm thử EventBridge event patterns bằng sample events, kiểm tra IAM/DLQ/deduplication và chạy thử runbook trong sandbox.
