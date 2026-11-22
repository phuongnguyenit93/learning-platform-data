# Archive, replay và phát sự kiện liên tài khoản

> **Chương:** Sự kiện và điều phối  
> **Module:** CLOUD_PROVIDERS_AWS — khám phá AWS qua hạ tầng Region/Availability Zone (AZ), IAM, VPC, điện toán, lưu trữ, cơ sở dữ liệu, tích hợp và serverless. Bài học hướng đến lựa chọn dịch vụ, triển khai ứng dụng an toàn, có giám sát, phục hồi và kiểm soát chi phí.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **EventBridge default/Custom Event Bus – Classic** với **Custom Event Bus** mới, đặc biệt cách lưu và phát lại sự kiện.
2. Giải thích **archive**, event pattern, retention, encryption và cơ chế ngăn archive lưu lại replayed events trên Classic.
3. Thiết kế **replay** chọn đúng time window, đúng rules và có biện pháp kiểm soát side effects/idempotency.
4. Triển khai tư duy **cross-account event delivery** qua IAM delivery role và resource-based policy hoặc **AWS RAM** theo loại bus.
5. Hiểu các giới hạn của bus-to-bus routing, quy tắc nhận sự kiện từ account khác, khả năng gửi trực tiếp tới cross-account targets.
6. Theo dõi **CloudWatch metrics, DLQ, retries, IAM/KMS, CloudTrail** và chi phí ingest, lưu trữ, replay.
7. Dùng AWS CLI **chỉ đọc** để kiểm tra cấu hình và tìm nguyên nhân sự cố.
8. Áp dụng cho mô hình Orders → Billing → Analytics, rebuild projection và replay không trùng giao dịch.

## 1. Khi nào cần archive, replay và liên kết tài khoản?

Giả sử ứng dụng Java Spring Boot quản lý đơn hàng chạy trong **Account A**. Khi user đặt hàng, ứng dụng phát sự kiện **OrderCreated**. Hệ thống **Billing ở Account B** tạo hóa đơn; nhóm **Analytics ở Account C** cập nhật báo cáo.

Có thể xảy ra:

- Billing consumer lỗi do một phiên bản Lambda mới.
- Cấu hình IAM bị thay đổi, một số events không đến target.
- Analytics cần bổ sung trường dữ liệu và **tính lại projection từ lịch sử**.
- Hệ thống cần cô lập account để áp IAM least privilege, data ownership và billing boundaries.
- Một lỗi runtime làm consumer xử lý một sự kiện hai lần.

**EventBridge archive/replay** cho phép lưu và tái phát lịch sử trong một mô hình event bus cụ thể; **cross-account delivery** tách nhà phát sự kiện khỏi người dùng sự kiện. Nhưng không tính năng nào tự bảo đảm consumer chỉ xử lý một giao dịch đúng một lần.

~~~mermaid
flowchart LR
  O["Orders service - Account A"] --> BUS["EventBridge bus"]
  BUS --> B["Billing - Account B"]
  BUS --> A["Analytics - Account C"]
  BUS -.-> H["Archive / Retention"]
  H -.->|"Replay"| BUS
  B --> DB[("Invoice database")]
  A --> PROJ[("Analytics projection")]
~~~

Lưu ý: sơ đồ mô tả quan hệ logic. **Cách triển khai bus/rules/subscribers** phụ thuộc loại EventBridge bus, không chỉ tên dịch vụ.

## 2. Hai loại EventBridge bus: đừng trộn lẫn API

AWS hiện có hai mô hình quan trọng:

| Tiêu chí | **Default / Custom Event Bus – Classic** | **Custom Event Bus mới** |
| --- | --- | --- |
| Định tuyến | **Rule** + một hoặc nhiều target. | **Subscriber** + filter + một target. |
| Lưu lịch sử | Thêm **Archive** riêng; Classic bus không tự giữ lịch sử phục vụ replay. | **Retention tích hợp trên bus**, mặc định **1 ngày**, có thể cấu hình **1–365 ngày**. |
| Replay | Tạo **Replay** từ archive về chính source bus; chọn rules hoặc all rules. | Subscriber đọc từ **starting position** nằm trong retention; không có StartReplay kiểu Classic. |
| Cross-account | Resource policy trên receiver bus, IAM role khi forwarding; direct PutEvents nếu được cho phép. | **AWS RAM share** bus để account khác tạo subscriber/publish theo managed permission. |
| Ordering | Không bảo đảm thứ tự replay tuyệt đối. | Có **FIFO theo event group, trên từng subscriber** khi được cấu hình. |
| Deduplication | Consumer tự thiết kế idempotency. | Có cơ chế publish deduplication trong cửa sổ theo tài liệu; vẫn cần consumer idempotent. |
| Format | JSON events qua PutEvents theo cơ chế Classic. | PutEvents hoặc PutRawEvents với khả năng định dạng bổ sung theo dịch vụ. |
| CLI | **aws events**. | **aws eventsv2**. |
| Metrics | **AWS/Events**. | **AWS/EventsV2**. |

**Quy tắc học:** nếu tài liệu/lab của bạn dùng **aws events create-archive**, **aws events start-replay**, **list-rules** và **put-targets**, đó là **Classic**. Nếu dùng **aws eventsv2 create-subscriber**, **RetentionPeriodInDays** trên bus và **AWS RAM share**, đó là **Custom Event Bus mới**.

Hai mô hình cùng tồn tại, nhưng logic và giới hạn khác nhau. AWS hiện khuyến nghị xem xét Custom Event Bus mới cho ứng dụng greenfield; các hệ thống Classic vẫn có thể tiếp tục vận hành/migrate dần.

### 2.1. So sánh với SQS, SNS và Step Functions

- **EventBridge:** lọc và route events từ producers đến consumers; không lưu trạng thái workflow nghiệp vụ.
- **SQS:** durable queue với visibility timeout, polling, consumer retries, DLQ và backlog metrics.
- **SNS:** push pub/sub notifications và fan-out.
- **Kinesis:** stream với retention/shards và semantics đọc theo shard.
- **Step Functions:** orchestration có trạng thái, retries/catches, workflow execution history.

Nếu một đơn hàng cần chuỗi **reserve inventory → charge → ship** với compensation, **Step Functions** phù hợp orchestration hơn việc chỉ phát ba events. Nếu mục tiêu là phát **OrderPaid** cho nhiều account độc lập, EventBridge phù hợp event routing.

## 3. Cấu trúc sự kiện và event contract

Một event Classic minh họa:

~~~json
{
  "version": "0",
  "id": "eventbridge-generated-id-example",
  "detail-type": "OrderCreated",
  "source": "shop.orders",
  "account": "111122223333",
  "time": "2026-11-20T03:00:00Z",
  "region": "ap-southeast-1",
  "resources": [],
  "detail": {
    "schemaVersion": 2,
    "eventId": "evt-order-10023-v3",
    "orderId": "ORDER-10023",
    "orderVersion": 3,
    "tenantId": "TENANT-42",
    "occurredAt": "2026-11-20T02:59:58Z",
    "currency": "VND",
    "amount": 125000
  }
}
~~~

| Trường | Ý nghĩa | Lưu ý khi replay và cross-account |
| --- | --- | --- |
| **id** | EventBridge event ID. | Không thay cho idempotency key nghiệp vụ trong mọi cách tái publish. |
| **source** | Nguồn sự kiện logic. | Đặt namespace nhất quán, ví dụ shop.orders. |
| **detail-type** | Loại sự kiện. | Chọn tên ổn định, versioning khi schema thay đổi. |
| **account** | AWS account nguồn theo envelope. | Dùng để lọc cross-account, không thay authorization của IAM. |
| **time** | Timestamp event. | Không phải lúc consumer đã xử lý hoặc lúc replay. |
| **detail** | Nội dung nghiệp vụ do producer cung cấp. | Không mặc định mọi field đã được xác minh. |
| **resources** | ARNs liên quan, có thể rỗng. | Không phải tất cả AWS service events đều chứa resources. |

**Thiết kế contract tốt:** có **eventId bất biến**, **schemaVersion**, aggregate ID, **orderVersion/sequence**, occurredAt và dữ liệu tối thiểu. Replay một sự kiện schema v1 sau sáu tháng yêu cầu consumer mới **đọc được định dạng cũ** hoặc upcast có kiểm soát.

**Không gửi** mật khẩu, access tokens, secret, thông tin thanh toán thô hoặc PII không cần thiết trong EventBridge detail: dữ liệu có thể được archive, forward nhiều account, log và replay.

## 4. Classic Archive: lưu sự kiện từ một source bus

Với **default event bus** và **Custom Event Bus – Classic**, archive là một tài nguyên riêng nhận events từ **một source event bus**.

~~~mermaid
flowchart TB
    P["Producer"] --> BUS["Classic EventBridge bus"]
    BUS --> RULE1["Rule: billing-events"]
    BUS --> RULE2["Rule: analytics-events"]
    BUS --> ARC["Archive: orders-history"]
    RULE1 --> SQS["SQS billing"]
    RULE2 --> LAMBDA["Lambda analytics"]
    ARC -.->|"Replay về cùng bus"| BUS
~~~

Các thuộc tính chính:

- **ArchiveName**: tên archive.
- **EventSourceArn**: ARN source event bus; **không đổi được** sau khi tạo.
- **EventPattern**: lọc những events đưa vào archive.
- **RetentionDays**: giữ event bao nhiêu ngày; nếu không cấu hình, Classic archive có thể **giữ vô thời hạn** theo mặc định.
- **KmsKeyIdentifier**: mã hóa bằng AWS owned key hoặc customer managed key theo tính năng hỗ trợ.
- **EventCount/SizeBytes**: số lượng và kích thước thống kê được dịch vụ reconciliation.

Một bus có thể tạo **nhiều archives** với filters/retention khác nhau. Một archive nên được sở hữu bởi nhóm vận hành và có tags, retention review, logging/audit và ngân sách rõ ràng.

### 4.1. Chọn event pattern để lưu có mục đích

Ví dụ archive chỉ giữ sự kiện đơn hàng được phát từ Account A:

~~~json
{
  "account": ["111122223333"],
  "source": ["shop.orders"],
  "detail-type": ["OrderCreated", "OrderPaid", "OrderCancelled"]
}
~~~

Đây là **JSON event pattern**, không phải toàn bộ CreateArchive payload. Chọn filter quá hẹp có thể làm không còn dữ liệu cần khôi phục; quá rộng có thể lưu dữ liệu nhạy cảm hoặc tốn phí lớn.

### 4.2. Retention và quyền xóa dữ liệu

| Mục tiêu | Retention ví dụ | Điểm cần chú ý |
| --- | --- | --- |
| Khôi phục lỗi consumer ngắn hạn | 7–14 ngày. | Đủ thời gian phát hiện và sửa lỗi. |
| Rebuild reporting | 30–90 ngày. | Hỗ trợ tái dựng projection từ history. |
| Phục vụ kiểm toán | Theo yêu cầu nội bộ/pháp lý. | Archive không tự thành immutable audit ledger. |
| Lưu lâu dài | Đánh giá storage/retention chuyên dụng. | Kiểm soát phí, GDPR/PII và vòng đời key. |

Các mốc ở bảng là **đề xuất minh họa**, không phải mặc định AWS hoặc tư vấn pháp lý.

### 4.3. Archive ingestion delay và reconciliation

Theo AWS:

- Event có thể đến archive chậm hơn lúc bus nhận; **nên đợi khoảng 10 phút** trước khi replay những events vừa nhận để không vô tình thiếu.
- **EventCount/SizeBytes** của DescribeArchive có thể có **24 giờ reconciliation period**.
- Archive vừa tạo có thể mất thời gian mới bắt đầu nhận sự kiện.
- Không kết luận “archive rỗng” chỉ vì EventCount chưa cập nhật tức thì.

### 4.4. Mã hóa và KMS

Archive mặc định được mã hóa với **AWS owned key**. Khi dùng **customer managed KMS key**:

- IAM/key policy phải cho phép EventBridge mã hóa/giải mã theo hướng dẫn.
- Key disabled/deleted có thể khiến không truy cập được archive.
- Cần quản trị key rotation, encryption context và chi phí KMS.
- Mã hóa at rest **không thay** kiểm soát nội dung event, quyền đọc/log/forward.

## 5. Classic Replay: điều kiện và hành vi

Một Classic Replay **đọc events từ archive** trong khoảng time window và **gửi lại vào chính event bus nguồn**.

Tham số quan trọng:

1. **ReplayName:** tên duy nhất cho chiến dịch replay.
2. **EventSourceArn:** ARN archive.
3. **EventStartTime / EventEndTime:** giới hạn các events theo thời gian sự kiện.
4. **Destination.Arn:** phải là **source bus của archive**, không phải bus bất kỳ.
5. **Destination.FilterArns:** tùy chọn rule ARNs sẽ nhận replay; nếu không chọn lọc, replay có thể đi qua **tất cả rules** trên bus.

**Không có tùy chọn “Replay trực tiếp sang một account khác” trong Classic StartReplay.** Khi cần downstream account, replay về source bus rồi dùng forwarding rules/targets được phép, hoặc một quy trình xuất/nhập khác được kiểm soát.

### 5.1. Replay metadata và managed rule

EventBridge thêm metadata field **replay-name** vào events khi phát lại:

~~~json
{
  "replay-name": "orders-rebuild-2026-11-20"
}
~~~

Archive dùng AWS-managed rule để **không archive lại replayed events**, với logic filter tương đương:

~~~json
{
  "replay-name": [
    {"exists": false}
  ]
}
~~~

Consumer có thể dùng **replay-name** để nhận biết backfill và chuyển sang code path an toàn, hoặc rule chỉ dành cho replay. **Không xóa managed rule của archive** để sửa lỗi routing.

### 5.2. Replay không bảo đảm thứ tự tuyệt đối

- Events được xử lý dựa trên **event time**, theo các **khoảng một phút**.
- Events trong một khoảng **không nhất thiết được phát lại đúng thứ tự gốc**.
- Replay có thể xen với live traffic mới.
- Replay có thể tốn thời gian theo khối lượng và quota, không phải phát 100.000 events ngay tức thì.
- **DescribeReplay.EventLastReplayedTime** giúp theo dõi tiến độ xử lý theo time range.

Nếu consumer nhận OrderCancelled v7 rồi nhận replay OrderCreated v3, nó không được khôi phục trạng thái đơn về Created. Cần **aggregate version, conditional writes** hoặc một quy trình rebuild riêng.

### 5.3. Vòng đời và giới hạn

- Tài liệu AWS nêu tối đa **10 active replays/account/Region**.
- Có thể cancel khi Replay ở STARTING hoặc RUNNING.
- Replay **không xóa** events khỏi archive, có thể chạy nhiều lượt.
- EventBridge **xóa replay resource records sau 90 ngày**; đó không phải archive retention.
- Với events vừa phát, cần cân nhắc **archive lag khoảng 10 phút**.

## 6. Replay an toàn: checklist production

Replay là một hành động có **side effects và có thể phát sinh phí**, không phải chỉ đọc. Trước khi chạy:

1. **Mục tiêu:** rebuild report, phục hồi consumer hay kiểm tra code mới?
2. **Phạm vi:** event types, account, tenants, start/end UTC nào?
3. **Nguồn:** archive đã lưu những events đó chưa, retention còn không?
4. **Rules:** gửi về **một rule cụ thể** hay mọi rules?
5. **Side effects:** có gửi email, charge payment, webhooks hoặc ghi dữ liệu sai lệch không?
6. **Idempotency:** consumer có eventId, aggregate version, conditional writes?
7. **Schema:** code hiện tại parse được event lịch sử v1/v2 không?
8. **Capacity:** Lambda/SQS/RDS/HTTP APIs có chịu được replay + live traffic?
9. **Giám sát:** CloudWatch, DLQ, progress, business outcomes có được theo dõi?
10. **Rollback:** có phương án stop/cancel, disable consumer phụ, khôi phục projection?
11. **Phê duyệt:** owner/incident ticket/change window và IAM least privilege?

### 6.1. Replay thử theo khoảng nhỏ

Ví dụ target **rebuild-analytics** đã idempotent, archive lưu events từ 10:00–11:00 UTC ngày sự cố:

- Chạy thử khoảng **10:00–10:05** với đúng rule rebuild.
- So sánh số order records và số projected rows.
- Kiểm tra DLQ, stale versions, exception logs.
- Kiểm tra tải database.
- Sau khi xác minh, mở rộng các time ranges còn lại.

Nếu rule production **charge-credit-card** cũng đang match OrderPaid, **không** replay tới mọi rules khi chưa chứng minh thanh toán không bị charge lần nữa.

### 6.2. Replay không tự khôi phục dữ liệu gốc

Sự kiện lịch sử có thể chứa tham chiếu S3 object đã bị xóa hoặc schema đã thay đổi. Archive không phục hồi các object/database state đó. Với data loss lớn, có thể cần **backup/restore** và reconciliation, không chỉ replay.

Replay cũng không thay Step Functions execution history; không tự phục hồi workflow đã lỗi khi business state đã thay đổi.

## 7. Idempotency, schema evolution và ordering

### 7.1. Vì sao eventId nghiệp vụ quan trọng?

Một business event có thể:

- Bị producer publish lại vì không thấy ACK.
- Đến hai lần do target retries.
- Được replay từ archive nhiều lần.
- Chuyển account qua một bus khác.
- Được backfill bằng một producer riêng với transport event ID mới.

Do đó cần một **detail.eventId** hoặc **operationId** ổn định, không chỉ reliance vào EventBridge envelope **id**.

~~~json
{
  "detail": {
    "schemaVersion": 2,
    "eventId": "order-10023-paid-v4",
    "orderId": "ORDER-10023",
    "orderVersion": 4,
    "paymentTransactionId": "PAYMENT-TXN-EXAMPLE"
  }
}
~~~

### 7.2. Conditional writes và transactional inbox

Với DynamoDB, có thể dùng **ConditionExpression attribute_not_exists(eventId)** để tránh chèn lại marker. Nhưng nếu ghi marker rồi side effect thất bại, retry có thể thấy marker và **bỏ qua công việc chưa hoàn tất**.

Một phương án vững hơn:

- Dùng **TransactWriteItems** để ghi dedup marker và business state trong cùng transaction khi dữ liệu cùng DynamoDB.
- Với database SQL, dùng transaction chứa **processed_event** unique key và update bản ghi.
- Với external payment provider, dùng **idempotency key** hỗ trợ bởi provider, không dựa vào transaction DB nội bộ duy nhất.
- Với nhiều hệ thống khác nhau, dùng **transactional outbox/inbox + reconciliation** theo architecture.

### 7.3. Guard theo aggregate version

Một consumer duy trì **lastAppliedVersion** theo orderId:

~~~text
Nếu incomingVersion <= lastAppliedVersion:
  Đây là event trùng/cũ; không overwrite state.
Nếu incomingVersion == lastAppliedVersion + 1:
  Có thể áp update tương ứng.
Nếu incomingVersion > lastAppliedVersion + 1:
  Có gap; buffer/retry hoặc truy vấn source of truth.
~~~

Logic chính xác phụ thuộc nghiệp vụ; những events không nhất thiết phát theo phiên bản tăng một đơn vị vẫn cần mô hình ordering khác.

**Ví dụ:** Không để replay OrderCreated v3 sau live OrderShipped v8 khiến hệ thống báo “đơn vừa được tạo”. Đó là lý do replay và event ordering phải được thiết kế cùng nhau.

### 7.4. Side effects không thể tùy tiện chạy lại

- Gửi email: có **notification dispatch key**.
- Charge credit card: dùng **payment idempotency key và ledger**.
- Gọi webhook: xác minh đối tác có dedup hay không.
- Analytics projection: upsert có event version/checkpoint.
- Cập nhật inventory: dùng atomic conditional update, không trừ kho hai lần.

**Replay không đồng nghĩa exactly-once business processing.**

## 8. Classic: phát sự kiện sang tài khoản AWS khác

**Thiết kế kinh điển:** Account A phát OrderCreated trên bus nguồn; rule có target là **bus của Account B**; Account B dùng rule riêng để gửi sự kiện tới SQS/Lambda consumer.

~~~mermaid
flowchart LR
    subgraph A["Account A — Orders"]
        PUB["Orders Spring Boot / outbox publisher"] --> BA["Classic bus orders-events"]
        BA --> RA["Rule forward-to-billing"]
        RA --> ROLE["IAM delivery role"]
    end
    subgraph B["Account B — Billing"]
        POLICY["Bus resource-based policy"] --> BB["Classic bus billing-events"]
        BB --> RB["Rule accept-order-created"]
        RB --> SQS["Billing SQS + DLQ"]
        SQS --> JAVA["Java consumer"]
        JAVA --> DB[("Billing RDS")]
    end
    ROLE -->|"events:PutEvents"| BB
~~~

**Hai đầu phải cấp quyền và cấu hình đồng thời:**

1. Account B tạo destination bus và **resource-based policy** cho phép Account A/role được publish.
2. Account A tạo rule matching OrderCreated, target là destination bus ARN.
3. Account A dùng IAM **delivery role** cho EventBridge, role có **events:PutEvents** trên destination bus ARN.
4. Account B tạo rule matching **account/source/detail-type** và gắn target.
5. Với SQS/Lambda target, resource policy/execution permissions phải được cấp theo loại target.
6. Giám sát cả hai buses, rule target delivery, queue backlog và consumer.

### 8.1. Ví dụ IAM role của forwarding rule

Trust policy cho EventBridge assume role:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "events.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

Identity policy gắn delivery role của Account A:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PutOnlyToBillingEvents",
      "Effect": "Allow",
      "Action": "events:PutEvents",
      "Resource": "arn:aws:events:ap-southeast-1:444455556666:event-bus/billing-events"
    }
  ]
}
~~~

Đây là những policy fragments minh họa; production cần cân nhắc trust policy **aws:SourceArn/aws:SourceAccount** theo cách AWS hỗ trợ để hạn chế confused deputy, kết hợp IAM permissions boundaries/SCP nếu có.

AWS yêu cầu các **cross-account event bus targets mới** gắn IAM role; trường hợp mục tiêu cũ từ trước thay đổi năm 2023 có thể khác. Không chỉ dựa vào một ví dụ CLI cũ rồi bỏ role trong kiến trúc mới.

### 8.2. Resource policy ở destination bus Account B

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowOrdersAccount",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::111122223333:root"
      },
      "Action": "events:PutEvents",
      "Resource": "arn:aws:events:ap-southeast-1:444455556666:event-bus/billing-events"
    }
  ]
}
~~~

Ở đây Account A root ARN là **cách biểu diễn principal account** trong policy; không có nghĩa phải dùng root access keys để publish. Với security chặt hơn, restrict principal xuống delivery role cụ thể hoặc sử dụng conditions được AWS hỗ trợ.

**Không đặt Principal = wildcard trên production bus** trừ khi có policy/conditions đủ bảo vệ và business justification đã được review.

### 8.3. Dùng AWS Organizations

Có thể cho một AWS Organization được phép publish bằng **aws:PrincipalOrgID**, ví dụ fragment:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": "*",
      "Action": "events:PutEvents",
      "Resource": "arn:aws:events:ap-southeast-1:444455556666:event-bus/billing-events",
      "Condition": {
        "StringEquals": {
          "aws:PrincipalOrgID": "o-exampleorg"
        }
      }
    }
  ]
}
~~~

Giá trị organization ID là placeholder. Nếu cả Organization có hàng trăm accounts, quyền này có thể rộng hơn bạn nghĩ; cân nhắc cụ thể **account/role/source** và SCP boundaries. **Organization membership không loại bỏ yêu cầu IAM delivery role của bên gửi.**

### 8.4. Receiver rule lọc đúng account

~~~json
{
  "account": ["111122223333"],
  "source": ["shop.orders"],
  "detail-type": ["OrderCreated"]
}
~~~

Không viết **account: ["*"]** rồi nghĩ EventBridge sẽ hiểu là mọi account; ký tự đó không xuất hiện như account ID thật. Nếu muốn match tất cả incoming accounts được bus policy cho phép, bạn bỏ field account, nhưng đó là lựa chọn cần cân nhắc rủi ro.

Một event đã đến bus không mặc nhiên hợp lệ về mặt nghiệp vụ: producer có thể phát payload sai hoặc account được quyền publish có thể bị xâm phạm. Consumer vẫn phải validate schema, nguồn tin cậy, aggregate ID và quyền dữ liệu.

## 9. Classic: hạn chế chuyển tiếp nhiều chặng và cross-Region

### 9.1. Không xây chain A → B → C bằng rule forwarding liên tiếp

AWS nêu rõ:

- Nếu **Account A** forward tới bus **Account B**, rule ở B **không tự forward tiếp event nhận được từ A** đến bus **Account C** qua cùng cơ chế liên bus Classic.
- Cơ chế hạn chế cũng áp dụng cho một số chuỗi bus-to-bus trong cùng account.

**Hệ quả:** Không thiết kế pipeline **Orders A → Billing B → Analytics C** dựa trên việc mỗi bus cứ chuyển tiếp vô hạn theo rule. Thay vào đó:

- **Account A** có thể route riêng tới B và C nếu được phép.
- Dùng một **central event bus** có các rules/targets phù hợp.
- Với kiến trúc mới, cân nhắc **shared Custom Event Bus + subscriber do mỗi consumer sở hữu**.
- Nếu cần tái phát một event **mới về mặt nghiệp vụ**, consumer có thể phát **sự kiện mới** với event type/operation rõ ràng thay vì tìm cách chuyển tiếp nguyên event xuyên nhiều buses.

### 9.2. Cross-Region không có nghĩa tất cả Region đều cho phép

Classic bus-to-bus cross-account:

- Trong **cùng Region** có thể sử dụng ở Region hỗ trợ.
- Cross-Region cần destination Region nằm trong **tập Region được AWS hỗ trợ cho cross-Region event delivery**.
- Cần IAM role/resources ở đúng Region, endpoint ARN chính xác, quota và network/data residency review.
- Cross-Region delivery có tác động tới **độ trễ, phí và quyền lưu trữ dữ liệu**.

Không viết code hard-code region ap-southeast-1 rồi chỉ sửa account ID khi destination bus thực tế nằm tại ap-northeast-1. Phải kiểm tra ARN/Region phù hợp và hạn mức tính năng.

### 9.3. Cẩn thận vòng lặp

Một rule có thể gửi event tới bus khác và event quay lại qua logic ứng dụng. Dù dịch vụ có các cơ chế chống loop theo sản phẩm/phiên bản, **không thiết kế ứng dụng dựa trên giả định AWS luôn chặn được mọi vòng lặp**.

Biện pháp:

- Cụ thể hóa **source/detail-type** và account event patterns.
- Không để output của consumer match ngược trigger đầu vào khi không có chủ đích.
- Có business operation ID/idempotency.
- Theo dõi **PutEvents rate**, target invocations, DLQ và cost anomaly.
- Với S3/SQS/Lambda handlers, tránh self-trigger vô hạn.

## 10. Classic: direct cross-account service targets

AWS còn hỗ trợ **EventBridge Classic rule trực tiếp gửi event tới một số AWS service targets ở account khác**, thay vì lúc nào cũng phải forward qua một destination bus.

Theo tài liệu hiện hành, cross-account direct targets **trong cùng Region** gồm những dịch vụ được hỗ trợ như:

- **Amazon SQS queue**.
- **AWS Lambda function**.
- **Amazon SNS topic**.
- **Amazon Kinesis Data Streams**.
- **Amazon API Gateway API**.

Đây là mô hình **target service khác account**, không phải “bus-to-bus” như phần 8.

~~~mermaid
flowchart LR
    subgraph A["Account A"]
      BUS["Classic EventBridge bus"] --> RULE["Rule: order-created"]
      RULE --> ROLE["EventBridge delivery role"]
    end
    subgraph B["Account B"]
      RESOURCE_POLICY["Target resource policy"] --> Q["SQS billing queue"]
    end
    ROLE -->|"sqs:SendMessage (IAM)"| Q
~~~

### 10.1. Hai lớp quyền khi gửi trực tiếp

1. **Execution role** của rule ở **cùng account với source bus**; role có quyền hành động đối với target, ví dụ **sqs:SendMessage**.
2. **Resource policy** của destination target cho phép invocation từ principal/role theo tài liệu của dịch vụ đó.
3. Kiểm tra target service/Region có trong danh sách hỗ trợ direct cross-account delivery.
4. Với customer managed KMS key, cấu hình KMS policies đủ dùng.
5. Có DLQ hoặc on-failure path để lưu failures.

**Không nhầm** role có quyền events:PutEvents khi target là **event bus** với role cần **sqs:SendMessage/lambda:InvokeFunction** khi target là service trực tiếp.

### 10.2. Khi nào chọn bus-to-bus hay direct service target?

| Nhu cầu | **Bus-to-bus Classic** | **Direct service target** |
| --- | --- | --- |
| Account B tự định nghĩa nhiều rules/consumers. | Tốt: event tới bus B, B quản lý routing. | Ít linh hoạt hơn, target do nguồn định nghĩa. |
| Chỉ một SQS queue account B cần event. | Có thể dư một bus/rule. | Hợp lý nếu cùng Region và service hỗ trợ. |
| Muốn tách producer khỏi target implementation. | Tách tốt. | Sender biết loại ARN target. |
| Cần cross-Region. | Xem destination Region hỗ trợ. | Direct cross-account service targets theo tài liệu chỉ **cùng Region**. |
| Muốn consumer account sở hữu subscription trên một bus chung. | Classic không phải mô hình phù hợp nhất. | Cân nhắc Custom Event Bus mới + AWS RAM. |

## 11. Custom Event Bus mới: retention và subscriber-owned routing

**Custom Event Bus** mới là mô hình khác với Classic: bus tiếp nhận và **giữ events**; consumers tạo **subscribers** để nhận event theo filter.

~~~mermaid
flowchart TB
    subgraph OWNER["Account A — Bus owner"]
      PUB["Orders producer"] --> BUS["Custom Event Bus: orders"]
      BUS -.-> RET["Integrated retention 1–365 ngày"]
    end
    subgraph BILL["Account B — Billing"]
      SB["Subscriber billing"] --> SQS["SQS billing"]
    end
    subgraph ANA["Account C — Analytics"]
      SA["Subscriber analytics"] --> L["Lambda analytics"]
    end
    BUS -->|"AWS RAM share + subscriber"| SB
    BUS -->|"AWS RAM share + subscriber"| SA
    RET -.->|"Historical starting position"| SB
    RET -.->|"Historical starting position"| SA
~~~

**Khác biệt lớn về ownership:**

- Account A sở hữu **bus** và có thể chia sẻ bus cho accounts khác.
- Account B tạo và sở hữu **subscriber của B** trên shared bus.
- Account C tạo và sở hữu **subscriber của C**.
- Bus owner nhìn được các subscribers trên bus; một consumer account thường chỉ quản lý subscribers do mình tạo.
- Account B không được update/delete bus hoặc subscribers thuộc account khác.
- Khi cần ngừng hẳn một subscriber đã được tạo trước đó, bus owner có cơ chế **RevokeResource** theo tài liệu.

### 11.1. Retention của Custom Event Bus

Custom bus giữ events theo **StorageConfiguration.RetentionPeriodInDays**, từ **1 đến 365 ngày**, mặc định **1 ngày** nếu không chỉ định. Đây là retention của bus, không cần tạo Classic Archive.

**DescribeEventBus.RetentionWindowStartTime** cho biết thời điểm sớm nhất có thể bắt đầu đọc retained events. Không dùng quy tắc “Classic archive default giữ vô hạn” cho Custom Event Bus mới.

Longer retention tăng khả năng replay nhưng cũng tăng **phí lưu trữ** và trách nhiệm kiểm soát PII/data retention.

### 11.2. Subscriber bắt đầu từ quá khứ

Subscriber có hai hướng starting position chính:

- **LATEST:** chỉ nhận events mới kể từ khi subscriber bắt đầu.
- **POINT_IN_TIME:** nhận retained events từ một điểm đã chọn trong retention window.

Với POINT_IN_TIME:

- **PointType = HORIZON:** sớm nhất trong retention window.
- **PointType = TIMESTAMP:** StartingPoint là timestamp được chọn.
- Có thể đặt **EndPoint** để replay đến một thời điểm dừng; nếu không, subscriber sẽ **bắt kịp live traffic và tiếp tục nhận events mới**.
- StartingPoint phải nằm trong retention window và không ở tương lai.
- Với lựa chọn open-ended, tài liệu đặt điều kiện **StartingPoint ít nhất 5 phút trong quá khứ**; nếu có EndPoint thì có ngoại lệ theo mô hình.

**Đây là replay bằng subscriber starting position**, không phải gọi Classic StartReplay. Có thời gian khởi động replay; không kết luận thất bại khi chưa bắt đầu ngay.

### 11.3. Phân biệt live và replay trên Custom bus mới

Events được subscriber nhận có **SystemMetadata.aws:DeliveryType**:

~~~json
{
  "SystemMetadata": {
    "aws:DeliveryType": "REPLAY"
  }
}
~~~

Giá trị **LIVE** cho event mới và **REPLAY** cho retained event được đọc lại. Ví dụ chỉ trích một phần metadata, không phải nguyên payload.

**Không lẫn** field **Classic replay-name** với **Custom bus aws:DeliveryType**. Nếu consumer muốn idempotency xuyên cả hai, cần một business eventId/aggregate version độc lập cơ chế transport.

### 11.4. FIFO và deduplication không đồng nghĩa exactly once

Custom bus hỗ trợ:

- FIFO theo **event group** trên từng subscriber trong cấu hình tương ứng.
- Deduplication lúc publish theo content hoặc key trong **cửa sổ 5 phút** được công bố.
- Retention và subscriber pause/resume.

Tuy nhiên:

- Duplicate có thể xảy ra ngoài cửa sổ dedup hoặc ở downstream retries.
- Một event có side effect phải có business idempotency.
- FIFO trong event group **không phải thứ tự toàn cục** giữa mọi account/tenant.
- Target retries, transformations và consumer bugs vẫn cần được xử lý.

### 11.5. Schema và payload format

Custom Event Bus có **PutRawEvents** để hỗ trợ nội dung như JSON, Avro, Protobuf/raw bytes theo tính năng/schema registry. Không tự gửi binary bytes bằng Classic PutEvents rồi kỳ vọng subscriber hiểu như raw events.

Khi một consumer cần lọc theo fields, dữ liệu đã được deserialized theo cấu hình hỗ trợ hay chưa là điều phải kiểm tra; event filter không tự hiểu schema của mọi binary payload.

## 12. Cross-account trên Custom Event Bus mới: AWS RAM

Với Custom Event Bus mới, AWS hướng dẫn **share bus bằng AWS Resource Access Manager** thay vì mô hình Classic bắt buộc forward qua một receiving bus khác.

### 12.1. Các kiểu quyền RAM phổ biến

| AWS RAM permission | Consumer account có thể làm gì? |
| --- | --- |
| **AWSRAMEventBridgeEventBusV2PublishOnly** | Publish events và describe bus. |
| **AWSRAMEventBridgeEventBusV2SubscribeOnly** | Tạo/quản lý subscriber của chính mình và describe bus. |
| **AWSRAMEventBridgeEventBusV2EventSourceAccess** | Gắn và quản lý event sources của mình theo quyền. |
| **AWSRAMEventBridgeEventBusV2FullAccess** | Tổng hợp publish, subscriber và event source actions do managed permission cho phép. |

Chọn **least privilege**: Billing chỉ tiêu thụ Orders events thì thông thường cấp **SubscribeOnly**, không phải FullAccess.

Khi share bus:

1. Bus owner chọn ARN Custom Event Bus mới, accounts/OUs và RAM permission.
2. Nếu chia sẻ ngoài AWS Organizations, consumer có thể cần **accept invitation**.
3. Consumer cần **IAM identity policy** tương ứng ngoài quyền từ RAM; cả hai phía đều phải allow.
4. Consumer tạo subscriber trên shared bus cùng Region.
5. Bus owner giám sát delivery/egress theo subscriber account và có quyền revoke khi cần.

### 12.2. Giới hạn Region

Custom Event Bus được share cho consumer account trong **cùng Region và partition** của bus. Đây không phải giao thức tự share subscriber xuyên Region.

Đừng sao chép quy tắc **Classic bus-to-bus cross-Region** sang RAM subscriber model.

### 12.3. Gỡ RAM share chưa luôn dừng subscriber có sẵn

Một lưu ý bảo mật quan trọng:

- Gỡ resource share/permission có thể ngăn account khác **tạo subscriber mới/publish mới**.
- Nhưng subscriber đã được tạo khi share còn hiệu lực **có thể tiếp tục delivery** theo cơ chế authorization của Custom bus.
- Nếu cần chấm dứt hẳn consumer đã tồn tại, bus owner phải **RevokeResource** hoặc xử lý subscriber lifecycle theo hướng dẫn AWS.

Do đó offboarding partner/account cần checklist đầy đủ: **unshare → revoke resource(s) → kiểm tra stopped delivery → review access logs/CloudTrail**.

### 12.4. Resource policy và điều kiện

Custom bus có thể dùng custom resource policy khi RAM managed permission không đủ biểu đạt **explicit Deny**, conditions hoặc phạm vi đặc biệt.

Một Custom bus có thể có policy do owner tự quản và policy **AWS_RAM** do RAM viết. **Explicit Deny** từ một policy được đánh giá có thể thắng Allow từ policy khác. Không chỉ xem một policy rồi suy quyền access đã thành công.

**Không** copy JSON resource policy của Classic EventBridge bus target sang **event-busv2 ARN** mà không kiểm tra allowed IAM actions/ARN formats của Custom bus.

## 13. Khi nào chọn Classic hay Custom Event Bus mới?

| Bối cảnh | Chọn lựa ban đầu |
| --- | --- |
| Đang dùng AWS service events trên default bus, rules/targets và archive. | **Classic** và quy trình archive/replay hiện hữu. |
| Nhiều account mới, mỗi nhóm muốn tự sở hữu subscriber trên bus chung. | **Custom Event Bus mới + RAM**. |
| Cần replay độc lập cho từng consumer, retention tích hợp. | **Custom Event Bus mới**. |
| Có hệ thống phụ thuộc deeply vào Classic rule InputTransformer và routing semantics. | Giữ Classic hoặc migrate có kế hoạch; tính năng tương đương trên Custom bus cần cấu hình phù hợp. |
| Muốn route một rule tới Lambda/SQS của account khác cùng Region mà không có bus đích. | **Classic direct cross-account service target** nếu được hỗ trợ. |
| Cần API JSON PutEvents truyền thống trên default bus. | **Default / Classic**. |
| Muốn FIFO theo entity group và publish-time deduplication theo feature mới. | **Custom Event Bus**, vẫn thực hiện consumer idempotency. |

### 13.1. Không migrate bằng cách đổi tên ARN

AWS cho phép Classic và Custom bus chạy song song theo tài liệu, nhưng **resource models khác**:

- Classic **rule + target** chuyển thành một hoặc nhiều **subscribers**.
- Classic **archive + replay** chuyển sang **retention + starting position**.
- Classic event pattern có thể được chuyển thành subscriber filter phù hợp.
- Classic input transformer và target configuration phải migrate sang mô hình transformer/invoke configuration mới.

Một migration an toàn cần contract tests, shadow consumption hoặc dual-read có kiểm soát, business deduplication và chi phí thử nghiệm. Không tự chuyển lịch sử mọi event chỉ bằng một thao tác đổi tên bus.

## 14. IAM, Organizations, KMS và ranh giới trách nhiệm

### 14.1. Phân biệt các principal

| Principal | Quyền cần | Không được nhầm với |
| --- | --- | --- |
| **Producer app IAM role** | Publish vào bus được phép: events:PutEvents hoặc PutRawEvents theo bus. | Consumer role. |
| **Classic rule delivery role** | EventBridge assume role để gửi tới bus/target. | User app có quyền thay bus policy. |
| **Destination Classic bus policy** | Cho phép Accounts/roles publish. | Rule filter hoặc backend authorization. |
| **Custom RAM share** | Cho account khác quyền publish/subscribe theo permission. | IAM identity policy của chính account đó. |
| **Custom subscriber delivery role** | EventBridge gửi event đến target và failure destination. | Bus owner admin role. |
| **Consumer runtime role** | Đọc SQS, ghi DB/S3 theo đúng nghiệp vụ. | Quyền rộng tạo/delete archives. |
| **Operator role** | Describe/read metrics và có thể start replay theo quy trình. | Quyền deploy mọi services. |

Không dùng IAM wildcard events:* trên mọi account để tiện debug. Chia roles theo **publisher, subscriber, operator, security auditor**.

### 14.2. Biện pháp least privilege

- Giới hạn destination ARN, accounts, Region.
- Dùng **aws:PrincipalOrgID**, **events:source** và conditions phù hợp khi dịch vụ hỗ trợ.
- Cấp quyền **events:StartReplay** riêng cho operator thay vì mọi application role.
- Với KMS CMK, có key policy cho đúng service principal và encryption context.
- Audit CreateArchive, DeleteArchive, StartReplay, PutPermission, PutRule, PutTargets, RAM share/subscriber changes.
- Không cho operator replay historical PII sang consumer ngoài phạm vi xử lý đã phê duyệt.
- Test **explicit Deny/SCP** và account ownership, không chỉ policy Allow.

### 14.3. Bảo mật payload

Trước khi gửi event liên account:

1. Minimize payload: tham chiếu orderId thay vì toàn bộ địa chỉ/thẻ thanh toán nếu không cần.
2. Classify dữ liệu: PII, thông tin nhạy cảm và retention period.
3. Encrypt at rest/in transit theo dịch vụ; dùng CMK khi chính sách yêu cầu.
4. Kiểm soát consumer accounts và roles theo organization policy.
5. Thiết lập schema compatibility và validation.
6. Chặn accidental republishing vào account bên ngoài.
7. Theo dõi contract/data deletion khi replay lịch sử.

**Tách tài khoản AWS không tự loại bỏ nghĩa vụ bảo vệ dữ liệu**; cross-account delivery là một sự chia sẻ dữ liệu thực sự và phải được kiểm soát.

## 15. Giám sát archive, replay và cross-account delivery

Không thể xử lý sự cố chỉ bằng việc biết producer đã gọi PutEvents. Cần quan sát **producer → source bus → filter/rule → target/receiver bus → consumer → business state**.

### 15.1. CloudWatch metrics của Classic bus

Classic EventBridge sử dụng namespace **AWS/Events**, với các metrics quan trọng:

| Metric | Diễn giải | Cần kiểm tra khi |
| --- | --- | --- |
| **PutEventsEntries** | Số entries được gửi tới event bus qua API. | Lượng producer events tăng/giảm bất thường. |
| **PutEventsFailedEntries** | Events không được chấp nhận thành công qua PutEvents. | Lỗi publish, quota, schema/payload. |
| **MatchedEvents** | Số events khớp rules theo dimension. | Có event nhưng rule không kích hoạt. |
| **TriggeredRules** | Rules được trigger/matched. | Event pattern/account sai. |
| **Invocations** | Target invocations từ rules. | Match có nhưng target không được gọi. |
| **InvocationAttempts** | Những lần EventBridge cố invoke target. | Delivery chậm hoặc retry nhiều. |
| **RetryInvocationAttempts** | Số target retries. | Downstream throttled/unavailable. |
| **FailedInvocations** | Invocations thất bại vĩnh viễn. | Cần xử lý target, policy, quota. |
| **InvocationsSentToDlq** | Failure records đã vào DLQ. | Cần triage và redrive. |
| **InvocationsFailedToBeSentToDlq** | Không ghi được failed delivery vào DLQ. | Rủi ro mất đường phục hồi. |
| **IngestionToInvocationSuccessLatency** | Thời gian từ ingest đến target success. | Retry hoặc backend gây chậm. |

**Chú ý:** Một số metrics chỉ phát khi có lỗi/lần gọi. “Không có datapoint” không chắc bằng “0 lỗi” nếu time range, Region, dimensions hoặc hệ thống không phát dữ liệu.

### 15.2. Quan sát archive/replay

- **DescribeArchive.State**, EventSourceArn, EventPattern, RetentionDays và KmsKeyIdentifier.
- **EventCount/SizeBytes**, nhớ reconciliation có thể tới **24 giờ**.
- **DescribeReplay.State**, EventStartTime, EventEndTime, EventLastReplayedTime và StateReason.
- **Consumer logs** gắn business eventId, aggregateVersion, replay-name, processing result.
- **DLQ/target health** và số row thực tế đã được rebuild.

Replay state **COMPLETED** chỉ xác nhận replay operation theo EventBridge, **không chứng minh** hệ thống Billing đã ghi invoice chính xác.

### 15.3. Theo dõi ở consumer

| Consumer | Metrics |
| --- | --- |
| SQS worker | ApproximateNumberOfMessagesVisible, ApproximateAgeOfOldestMessage, DLQ depth. |
| Lambda | Invocations, Errors, Duration, Throttles, ConcurrentExecutions. |
| Step Functions | ExecutionsFailed/TimedOut, business execution status. |
| Database | Connections, write errors, latency, conditional check failures, row counts. |
| Business | OrdersCreated, InvoicesIssued, DuplicateOperationsSkipped, RebuildCheckpoint. |

Một rule forward sang SQS thành công nhưng worker không poll queue có thể khiến backlog tăng mà **FailedInvocations của EventBridge vẫn bằng 0**.

## 16. Observability cho Custom Event Bus mới

Custom Event Bus có metrics namespace **AWS/EventsV2**, khác Classic.

| Metric | Giải thích |
| --- | --- |
| **FilterEvaluated** | Events được đánh giá theo subscriber filters. |
| **FilterMatched** | Events khớp tất cả filters. |
| **EventDeliveryAttempts** | Attempts giao sự kiện, gồm trường hợp thử lại. |
| **TargetInvocations** | Target API calls, một call có thể gửi batch. |
| **EventsDelivered** | Số events target chấp nhận. |
| **RetryInvocationAttempts** | Số lần thử lại delivery. |
| **EventTransformationFailures** | Transform/filter-related expression failures. |
| **EgressBytes** | Lượng bytes delivery. |
| **IngestionToInvocationStartTime** | Trễ từ ingest tới bắt đầu target invoke. |
| **OnFailureDestinationDelivered** | Failure records gửi được tới nơi nhận lỗi. |
| **OnFailureDestinationFailed** | Không gửi được failure records. |
| **EventsDropped** | Events hết retries và không có nơi giữ lỗi. |
| **ApproximateBacklogAge** | Tuổi event cũ nhất subscriber chưa giao được. |

Các dimensions như **EventBus/Subscriber** và **SubscriberAccount** cho phép theo dõi consumption theo account. Với subscriber logs, cấu hình log level và payload retention cẩn thận: logging mọi dữ liệu khách hàng có thể làm tăng phí và rủi ro PII.

Không cộng **TargetInvocations** như số business events: target call có thể chứa batch. Không xem **EventsDelivered** như số giao dịch business đã commit: target nhận thông điệp và code xử lý là hai giai đoạn khác.

## 17. Retry, DLQ và archive: ba vai trò khác nhau

### 17.1. Classic target retry

EventBridge Classic có **RetryPolicy** cho target delivery. Theo default phổ biến, EventBridge có thể retry trong **tối đa 24 giờ hoặc 185 attempts**, với backoff/jitter. Các giá trị thực tế còn phụ thuộc cấu hình policy và loại target.

- **Retry**: xử lý lỗi tạm thời khi target bị throttle hoặc không có sẵn.
- **DLQ**: giữ failed delivery information khi retries exhausted và cấu hình có sẵn.
- **Archive**: giữ lịch sử event từ bus để replay trong future.

Một DLQ chứa failed delivery **không phải bản sao đầy đủ của mọi event**. Một archive có event **không thay thế việc redrive failures** theo runbook.

### 17.2. Custom subscriber retry

Custom Event Bus mới có **RetryPolicy** và **OnFailureConfiguration** của subscriber; defaults/giới hạn khác Classic, cần xem **DescribeSubscriber**. Tài liệu hiện hành nêu các defaults dạng **5 attempts và 300 giây** cho subscriber tương ứng.

Nếu delivery thất bại nhiều lần:

1. Sửa IAM/KMS/target lỗi.
2. Kiểm tra on-failure destination có ghi được không.
3. Khi event còn retention, cân nhắc tạo subscriber replay ở đúng time/IDs.
4. Không tự động replay toàn bus khi chỉ vài messages hỏng.

### 17.3. Mẫu DLQ runbook

1. Alarm nhận **InvocationsSentToDlq/OnFailureDestinationDelivered**.
2. Operator đọc failure metadata, xác định errorCode, target ARN và source event.
3. Tách lỗi **permanent** (schema invalid/permission denied) khỏi **transient** (throttle/timeout).
4. Fix cấu hình/code, kiểm thử một event.
5. Redrive/replay theo subset và checkpoint.
6. Kiểm tra business outcomes, xóa/đánh dấu messages đã xử lý trong DLQ.
7. Ghi incident summary và bổ sung metrics/alerts.

**Không nên để DLQ không có người nhận cảnh báo**, vì nó chỉ trì hoãn việc xử lý mất dữ liệu.

### 17.4. Nhiều tầng retry gây nhân bản

Một event route tới Lambda có thể được:

- EventBridge retry target delivery.
- Lambda async invocation retry.
- SDK HTTP retry.
- Consumer tự retry DB/3rd-party API.

Phải tính tổng số attempts và side effects. Với payment, dùng idempotency key và transaction ledger; đừng tin “chỉ có một eventId” đủ bảo đảm không charge lặp.

## 18. Kiểm soát chi phí và capacity

### 18.1. Cost drivers

| Hạng mục | Cần tính |
| --- | --- |
| **Classic PutEvents** | Custom event ingest và kích thước metering. |
| **Classic cross-account bus-to-bus** | Theo pricing Classic, bên gửi chịu phí tương ứng **custom event**, bên nhận không bị phí chính sự kiện cross-account đó. |
| **Classic Archive** | Archival processing và storage theo dữ liệu/retention. |
| **Classic Replay** | Replay traffic và downstream deliveries theo bảng giá. |
| **Custom Event Bus mới** | Publish, delivery tới subscribers và integrated retention. |
| **SQS/Lambda/Step Functions** | Request, compute, queue requests, executions và retries. |
| **CloudWatch/KMS** | Logs, metrics, alarms, key requests, data visibility. |
| **Cross-Region transfer** | Nếu kiến trúc/capabilities có cross-Region, đo phí và độ trễ riêng. |

Bảng trên mô tả **cấu phần**, không tự khẳng định đơn giá hiện hành. Xem AWS EventBridge Pricing cho Region, loại event, kích thước và bus model đang dùng.

### 18.2. Ước tính dung lượng

Giả sử Orders tạo **500.000 events/ngày**, mỗi event trung bình **2 KiB**, giữ **30 ngày**.

\[
500{,}000\times2\ \text{KiB}\times30
=30{,}000{,}000\ \text{KiB}
\approx28.6\ \text{GiB}
\]

Đây chỉ là dữ liệu thô trước overhead/metering; không phải số GB AWS sẽ tính phí một cách chính xác.

Nếu replay toàn bộ 30 ngày, có **15 triệu events đầu vào** cho các consumers. Với ba targets, deliveries/retries và phí downstream có thể cao hơn nhiều. Cần load-test DB, queue và quota trước khi phát lại lượng lớn.

### 18.3. Tối ưu chi phí đúng hướng

- Chọn event pattern/filters chỉ nhận những events thực sự cần.
- Retention theo nghiệp vụ, không để Classic archive vô hạn mà không review.
- Chọn **FilterArns** khi Classic replay thay vì All rules nếu chỉ rebuild một consumer.
- Tránh replay những workflows có side effects ngoài ý muốn.
- Monitor **Cost per successful business outcome** thay vì chỉ phí mỗi event.
- Dùng AWS Budgets/Cost Anomaly Detection, nhớ budget alert không phải hard cap.
- Giới hạn concurrency/retry và đặt alarm khi event volume tăng bất thường.
- Quản trị IAM/KMS để archive/retention không bị xóa hoặc mở quyền tùy tiện.

## 19. AWS CLI chỉ đọc: Classic event bus, archive, replay

Các lệnh dưới đây **không sửa tài nguyên**, không start replay, không phát event thật. Thay account/ARN/Region minh họa bằng tài nguyên được phép truy cập.

### 19.1. Xác định account và buses

~~~bash
aws sts get-caller-identity

aws events list-event-buses \
  --region ap-southeast-1

aws events describe-event-bus \
  --name orders-events \
  --region ap-southeast-1
~~~

Đọc **Name, Arn, Policy, KmsKeyIdentifier**, chắc chắn account/Region đúng. Một người dùng có thể truy cập nhiều AWS accounts; không suy từ tên bus duy nhất.

### 19.2. Xem rules và targets

~~~bash
aws events list-rules \
  --event-bus-name orders-events \
  --region ap-southeast-1

aws events describe-rule \
  --name forward-to-billing \
  --event-bus-name orders-events \
  --region ap-southeast-1

aws events list-targets-by-rule \
  --rule forward-to-billing \
  --event-bus-name orders-events \
  --region ap-southeast-1
~~~

Kiểm tra **EventPattern, Rule State, Targets[].Arn, Targets[].RoleArn, RetryPolicy và DeadLetterConfig**. RoleArn của bus target cần đủ permissions ở tài khoản gửi; receiving bus cần resource policy.

### 19.3. Xem archive

~~~bash
aws events list-archives \
  --region ap-southeast-1

aws events describe-archive \
  --archive-name orders-history \
  --region ap-southeast-1
~~~

Những trường có giá trị: **EventSourceArn, EventPattern, RetentionDays, State, EventCount, SizeBytes, KmsKeyIdentifier**. Số lượng/kích thước có thể cập nhật chậm; không dùng như metric realtime.

### 19.4. Xem replay progress

~~~bash
aws events list-replays \
  --region ap-southeast-1

aws events describe-replay \
  --replay-name orders-rebuild-2026-11-20 \
  --region ap-southeast-1
~~~

Đọc **EventLastReplayedTime, EventStartTime, EventEndTime, Destination.FilterArns, StateReason**. State COMPLETED chưa chứng minh consumer đã xử lý toàn bộ business records.

### 19.5. Test pattern an toàn

**aws events test-event-pattern** kiểm tra JSON pattern với một sample event mà không publish event thật. Dùng để phát hiện sai **account/source/detail-type**, nhưng vẫn cần kiểm tra IAM và target delivery ở bước vận hành riêng.

## 20. AWS CLI chỉ đọc: Custom Event Bus mới

Yêu cầu AWS CLI có namespace **eventsv2**. Nếu CLI cũ chưa biết các lệnh này, cần cập nhật version theo quy trình tổ chức, không đổi sang aws events và dùng API khác loại.

### 20.1. Danh sách buses sở hữu/được share

~~~bash
aws eventsv2 list-event-buses \
  --region ap-southeast-1

aws eventsv2 list-event-buses \
  --event-bus-account-id 111122223333 \
  --region ap-southeast-1
~~~

Đọc **EventBusArn, EventBusAccountId và State**; bus được RAM share có thể xuất hiện như tài nguyên của owner account khác.

### 20.2. Bus retention và retention window

~~~bash
aws eventsv2 describe-event-bus \
  --event-bus-arn arn:aws:events:ap-southeast-1:111122223333:event-busv2/orders/EXAMPLE1234567890abcdef1234567 \
  --region ap-southeast-1
~~~

ARN chỉ là **placeholder**. Dùng ARN thật từ list-event-buses. Xem **StorageConfiguration.RetentionPeriodInDays, RetentionWindowStartTime, State**.

### 20.3. Subscribers và trạng thái replay

~~~bash
aws eventsv2 list-subscribers \
  --event-bus-arn arn:aws:events:ap-southeast-1:111122223333:event-busv2/orders/EXAMPLE1234567890abcdef1234567 \
  --region ap-southeast-1

aws eventsv2 describe-subscriber \
  --subscriber-arn arn:aws:events:ap-southeast-1:444455556666:subscriber/billing/EXAMPLE1234567890abcdef1234567 \
  --region ap-southeast-1
~~~

Kiểm tra **StartingPosition, PointInTimeConfiguration, FilterConfiguration, InvokeConfiguration, RetryPolicy, OnFailureConfiguration và State**. Consumer account có thể chỉ thấy subscribers do chính account ấy sở hữu; owner bus thấy phạm vi rộng hơn theo tài liệu.

### 20.4. Các thao tác thay đổi được loại khỏi lab

Không chạy các lệnh sau trong bài chỉ đọc vì chúng có thể làm thay đổi lịch sử, routing, IAM hoặc chi phí:

~~~text
aws events start-replay
aws events cancel-replay
aws events create-archive
aws events delete-archive
aws events put-rule
aws events put-targets
aws eventsv2 create-event-bus
aws eventsv2 create-subscriber
aws eventsv2 revoke-resource
aws ram create-resource-share
~~~

Tạo/đổi tài nguyên thật phải có account lab, IAM approval, IaC review, monitoring và rollback.

## 21. Runbook điều tra sự kiện không tới consumer

~~~mermaid
flowchart TD
    S["Sự kiện không đến Billing"] --> A{"Producer PutEvents thành công?"}
    A -->|"Không"| A1["Kiểm tra IAM, payload, FailedEntryCount, quota"]
    A -->|"Có"| B{"Source rule / subscriber filter có match?"}
    B -->|"Không"| B1["Test event pattern, source, detail-type, account"]
    B -->|"Có"| C{"Target delivery có thành công?"}
    C -->|"Không"| C1["Kiểm tra IAM role, bus policy, target KMS, DLQ"]
    C -->|"Có"| D{"Consumer thực sự xử lý được?"}
    D -->|"Không"| D1["Xem SQS queue age, Lambda errors, DB transactions"]
    D -->|"Có"| E["Đối chiếu business eventId, orderVersion và projection"]
~~~

### 21.1. Tình huống A — Producer trả lỗi

- Đọc **FailedEntryCount/Entries[].ErrorCode** từ PutEvents response trong ứng dụng/log an toàn.
- Kiểm tra app IAM role có events:PutEvents trên bus ARN.
- Kiểm tra EventBusName/Region và event payload JSON có hợp lệ.
- Kiểm tra Service Quotas và throttles.
- Dùng retry có idempotency, không publish lại vô hạn.

### 21.2. Tình huống B — Cross-account target AccessDenied

- Account A: rule target ARN, delivery role trust và events:PutEvents permission.
- Account B: bus resource policy/organization conditions.
- Nếu role có IAM Allow nhưng SCP explicit Deny, request vẫn bị từ chối.
- Nếu destination dùng customer managed KMS key, kiểm tra KMS requirements.
- Đọc CloudWatch FailedInvocations, retries và DLQ, đừng chỉ kiểm tra rule State=ENABLED.

### 21.3. Tình huống C — Replay không có business records

- Kiểm tra đúng archive/source bus và retention.
- Có chờ archive ingestion lag khoảng 10 phút chưa?
- Time range UTC có đúng event time?
- Replay có chọn đúng **FilterArns** hay rule không match replayed event?
- Consumer có chủ động bỏ qua replay-name events hoặc dùng stale-version guard?
- Có ghi thành công target delivery nhưng transaction DB thất bại?

### 21.4. Tình huống D — Custom subscriber không replay được từ 45 ngày trước

- Bus retention có đủ lớn và **RetentionWindowStartTime** bao phủ thời điểm đó không?
- Subscriber dùng **POINT_IN_TIME** thay vì LATEST chưa?
- PointType TIMESTAMP/HORIZON và StartingPoint có đúng?
- Với open-ended replay, có đáp ứng điều kiện về thời điểm cách hiện tại tối thiểu không?
- Shared bus và subscriber có ở **cùng Region/partition**?
- Target permissions, on-failure destination và subscriber state có hợp lệ?

**Không thể replay một event nằm ngoài retention window** chỉ bằng việc đặt timestamp cũ hơn. Cần backup/historical source khác nếu dữ liệu không còn.

## 22. Tình huống thực tế

### Case A — Billing deploy lỗi 40 phút

**Bối cảnh:** Orders vẫn phát OrderCreated, Billing consumer chạy code lỗi từ 09:00 đến 09:40, có Classic archive.

**Giải pháp:**

1. Xác định events có trong archive và nằm trong retention.
2. Sửa Billing consumer, bật idempotency theo **eventId/orderId**.
3. Tạo/kiểm tra rule chỉ phục vụ Billing rebuild, không kích hoạt payment charge lại.
4. Chọn replay 09:00–09:40 UTC, dùng FilterArns đúng rule.
5. Kiểm soát SQS backlog và DB concurrency.
6. Đối chiếu số orders/invoices, eventId dedup count và DLQ.
7. Ghi hậu kiểm, bổ sung alarm và test replay.

**Sai lầm:** replay All rules để vô tình gửi email xác nhận đơn lần thứ hai hoặc charge thẻ thêm.

### Case B — Analytics xây projection mới

**Bối cảnh:** Analytics muốn tính lifetime customer value từ OrderPaid lịch sử.

**Giải pháp:** Nếu Classic archive đã giữ đủ data, thêm một rule target phục vụ projection mới và replay **chỉ tới rule ấy**. Nếu Custom Event Bus mới có retention, tạo **subscriber starting position POINT_IN_TIME**, kiểm tra replay/live transitions.

**Sai lầm:** coi event history là database state hoàn chỉnh, không xét OrderRefunded/OrderCancelled hoặc schemaVersion cũ.

### Case C — Nhiều tài khoản AWS Organization

**Bối cảnh:** Có account Orders, Inventory, Billing, Support; mỗi nhóm muốn tự quản lý subscriber.

**Lựa chọn:** **Custom Event Bus mới + AWS RAM SubscribeOnly**, chọn retention, KMS, owner audit. Nếu hệ thống đã có Classic buses/rules, cân nhắc migration dần thay vì chuyển tất cả ngay.

**Sai lầm:** dùng một IAM role events:* và chia sẻ toàn organization không có ranh giới publisher/consumer.

### Case D — A → B → C không chạy

**Bối cảnh:** Một Classic rule forward A sang B, rule B lại target bus C nhưng C không nhận.

**Nguyên nhân:** Classic bus-to-bus **không hỗ trợ tự chain forwarded events như mong muốn**. Chuyển thành A → B và A → C riêng, hoặc dùng bus trung tâm/subscribers trong Custom bus mới.

### Case E — Offboard một consumer account

**Bối cảnh:** Account Analytics không còn cần access tới Custom Event Bus được share qua RAM.

**Quy trình:** Xóa/quản lý share permissions, xác định các subscribers đã tạo, dùng **RevokeResource** khi cần dừng delivery hẳn; sau đó xác minh EventDeliveryAttempts/EventsDelivered không còn và audit permission removal.

**Sai lầm:** chỉ xóa RAM share rồi tin rằng mọi subscriber cũ lập tức dừng.

## 23. Sai lầm thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Mọi EventBridge bus đều có retention mặc định.” | Classic cần Archive; Custom bus mới có retention tích hợp. |
| “Archive Classic cho replay sang bất kỳ bus nào.” | Classic replay về **chính source bus**. |
| “StartReplay hoạt động với Custom bus mới.” | Custom bus replay qua **subscriber starting position**. |
| “Classic Replay giữ thứ tự của tất cả events.” | Không đảm bảo; xử lý theo time window từng phút và có thể out of order. |
| “Replay chỉ gọi một consumer.” | Nếu không chọn FilterArns, có thể đánh vào tất cả matching rules. |
| “Replay xóa events khỏi archive.” | Không; archive retention vẫn áp dụng. |
| “Replay resource xóa sau 90 ngày nghĩa archive chỉ giữ 90 ngày.” | Lifecycle replay record khác archive retention. |
| “EventCount = 0 ngay sau tạo Archive chắc là không nhận.” | DescribeArchive counters có thể cần reconciliation tới 24 giờ. |
| “Cùng eventId transport luôn đủ chống trùng.” | Business eventId và transaction-safe idempotency mới bảo vệ side effects. |
| “Có DLQ thì không cần archive.” | DLQ giữ failed deliveries; archive lưu lịch sử event theo phạm vi. |
| “Cho events:PutEvents ở source role là đủ cho cross-account Classic.” | Receiver bus policy cũng phải cho phép; target role và downstream policy phải đúng. |
| “Cứ chuyển A sang B rồi B chuyển tiếp sang C.” | Classic không hỗ trợ chaining forwarded bus events như vậy. |
| “WAF hay MFA cần thiết để event bus cross-account hoạt động.” | Đây là IAM/event policies; WAF/MFA thuộc lớp khác khi architecture dùng. |
| “Custom bus RAM share xóa là mọi subscriber ngừng tức thì.” | Có thể cần revoke subscribers đã tồn tại. |
| “Custom Event Bus có FIFO global tuyệt đối.” | FIFO theo event group/subscriber khi được hỗ trợ, không phải thứ tự toàn hệ thống. |
| “EventsDelivered = invoices committed.” | Delivery tới target khác giao dịch nghiệp vụ. |
| “Tăng retries là luôn tốt.” | Có thể tăng duplicates, chi phí và gây quá tải downstream. |
| “Lưu Archive vô hạn không tăng phí.” | Storage retention có cost và rủi ro dữ liệu. |
| “Cross-account đồng nghĩa cross-Region luôn được.” | Phụ thuộc model, Region support và ARN/quotas. |

## 24. Bài tập thực hành có lời giải

### Bài tập 1 — Chọn cơ chế lưu lịch sử

**Đề:** Một công ty đang sử dụng default EventBridge bus và muốn lưu OrderCreated trong 30 ngày để tái dựng báo cáo.

**Lời giải:** Đây là **Classic default bus**. Tạo **Archive** gắn với source bus, event pattern giới hạn source/detail-type/account, RetentionDays theo yêu cầu, IAM/KMS và quan sát EventCount/SizeBytes. Không thiết lập StorageConfiguration.RetentionPeriodInDays như Custom Event Bus mới.

### Bài tập 2 — Chọn replay an toàn

**Đề:** Một archive có OrderPaid events và trên bus có ba rules: charge-credit-card, send-email, analytics-update. Chỉ cần tính lại analytics.

**Lời giải:** Khi dùng **Classic Replay**, giới hạn **Destination.FilterArns** vào rule phục vụ analytics, không replay tất cả. Trước đó xác nhận analytics consumer idempotent, event versions hợp lệ, replay time window và business checkpoints.

### Bài tập 3 — Events trong archive chưa xuất hiện

**Đề:** Producer vừa phát 500 events, DescribeArchive.EventCount vẫn bằng 0 sau 30 giây.

**Lời giải:** Không kết luận archive hỏng. AWS có archive ingestion delay và **EventCount/SizeBytes reconciliation period tới 24 giờ**. Kiểm tra event patterns, source bus, archive State và chờ khoảng thời gian thích hợp trước khi replay.

### Bài tập 4 — Event ordering

**Đề:** Trong Classic Replay, consumer nhận OrderCancelled v7 trước OrderPaid v5.

**Lời giải:** Không dựa vào delivery order. Dùng **aggregate version**, conditional writes, logic stale-event skipping hoặc rebuild theo sequence có kiểm soát. Nếu cần thứ tự per-entity trong kiến trúc mới, xem **Custom Event Bus event groups/FIFO** theo tính năng, nhưng vẫn cần idempotency.

### Bài tập 5 — Tính nhanh dung lượng

**Đề:** 200.000 events/ngày, trung bình 4 KiB/event, retention 15 ngày. Ước tính dữ liệu thô.

**Lời giải:**

\[
200{,}000 \times 4\,\text{KiB}\times15
=12{,}000{,}000\,\text{KiB}
\approx11.44\,\text{GiB}
\]

Không phải bill AWS thực tế vì còn overhead, metering, pricing tiers, Region và usage khác.

### Bài tập 6 — Classic cross-account IAM

**Đề:** Account A có rule forward tới event bus B. CloudWatch báo FailedInvocations, Account A role có events:PutEvents nhưng Account B chưa cấp quyền.

**Lời giải:** Cần **destination bus resource policy** ở B cho source role/account, cùng IAM role/target/Region chính xác. Nếu sử dụng Organization permissions, kiểm tra SCP và condition keys. Không sửa bằng cách cấp AdministratorAccess cho service.

### Bài tập 7 — Cross-account chain

**Đề:** Rule A → B thành công, rule B → C lại không gửi event đó đi.

**Lời giải:** Classic bus-to-bus không hỗ trợ chain forwarded events như vậy. Cấu hình A → B và A → C độc lập hoặc dùng shared Custom Event Bus mới để B/C tự subscribe.

### Bài tập 8 — Shared bus với ba consumer

**Đề:** Orders account sở hữu bus, Billing và Analytics muốn tự viết filters/targets mà không cần Orders deploy rules cho họ.

**Lời giải:** Đánh giá **Custom Event Bus mới + AWS RAM SubscribeOnly**, mỗi consumer tạo subscriber thuộc account mình trong cùng Region/partition. Bus owner theo dõi EventsDelivered/EgressBytes theo SubscriberAccount.

### Bài tập 9 — Consumer cần dữ liệu 60 ngày trước

**Đề:** Custom bus giữ 30 ngày. Analytics tạo subscriber POINT_IN_TIME về 60 ngày trước.

**Lời giải:** Không thể đọc event ngoài retention window. Cần retained source, backup, archive Classic/nguồn lịch sử khác nếu đã được lưu hoặc điều chỉnh retention trước các lần phát sự kiện tương lai. Tăng retention hiện tại không làm tự xuất hiện data đã hết hạn.

### Bài tập 10 — Replay để sửa lỗi billing

**Đề:** Billing consumer nhận một OrderPaid event hai lần sau replay. Invoice bị tạo hai lần.

**Lời giải:** Thiết kế **transactional inbox/unique business eventId**, hoặc giao dịch idempotency và API idempotency key. Nếu consumer là payment charge, dùng provider idempotency key và ledger. Không chỉ dựa vào transport event ID.

### Bài tập 11 — Gỡ quyền subscriber

**Đề:** Consumer Account C không còn được phép đọc shared Custom bus. Team xóa AWS RAM share.

**Lời giải:** Kiểm tra subscribers đã tồn tại; gỡ share không tự đảm bảo chấm dứt delivery cho subscribers đã được tạo. Bus owner cần áp **RevokeResource** theo quy trình và xác minh metrics/logs ngừng gửi.

### Bài tập 12 — Phân biệt DLQ và archive

**Đề:** SQS DLQ chỉ giữ 23 events lỗi, nhưng muốn rebuild toàn bộ 50.000 events của ngày đó.

**Lời giải:** DLQ không phải toàn bộ lịch sử; dùng **Classic archive** hoặc **Custom bus retention** nếu có dữ liệu phù hợp. Phải xác định source of truth và time range, sau đó replay idempotent theo consumer.

## 25. Câu hỏi tự kiểm tra

**Câu 1.** Classic EventBridge lưu sự kiện dài hạn ngay trên bus mặc định không?  
**Đáp án:** Không theo mô hình archive/replay; cần tạo **Archive** riêng.

**Câu 2.** Custom Event Bus mới có retention mặc định bao nhiêu ngày?  
**Đáp án:** **1 ngày** nếu không cấu hình; có thể chọn 1–365 ngày theo tài liệu hiện hành.

**Câu 3.** Classic Replay gửi events sang bus bất kỳ được không?  
**Đáp án:** Không; destination phải là **source bus của archive**.

**Câu 4.** Classic Replay dùng tham số nào giới hạn các rules?  
**Đáp án:** **Destination.FilterArns**.

**Câu 5.** EventBridge đánh dấu Classic replayed events bằng trường nào?  
**Đáp án:** **replay-name**.

**Câu 6.** Vì sao replayed events không bị ghi vào cùng archive liên tục?  
**Đáp án:** AWS-managed archive rule lọc events chứa replay-name.

**Câu 7.** Classic Replay bảo đảm thứ tự nguyên bản không?  
**Đáp án:** Không; replay theo event time từng khoảng một phút, không bảo đảm thứ tự mọi events.

**Câu 8.** Vì sao cần chờ khoảng 10 phút khi replay events vừa tới?  
**Đáp án:** Classic archive có ingestion lag; chờ giúp giảm nguy cơ event chưa vào archive.

**Câu 9.** Classic archive EventCount có cập nhật tức thì không?  
**Đáp án:** Không; reconciliation có thể tới **24 giờ**.

**Câu 10.** Replay xóa events khỏi archive không?  
**Đáp án:** Không. Events hết hạn theo retention hoặc khi archive bị xóa.

**Câu 11.** Có thể chạy bao nhiêu Classic replays active đồng thời theo giới hạn AWS nêu?  
**Đáp án:** **10/account/Region**.

**Câu 12.** IAM role ở Account A có đủ cho bus-to-bus cross-account không?  
**Đáp án:** Chưa đủ; destination bus của B cũng cần resource policy cho phép.

**Câu 13.** Classic receiving rule nên có field nào để tránh nhận nhầm account?  
**Đáp án:** **account** cùng source/detail-type theo trust model.

**Câu 14.** Có nên đặt account: ["*"] để match tất cả accounts không?  
**Đáp án:** Không; phải có account ID cụ thể hoặc bỏ field theo policy có chủ đích.

**Câu 15.** Classic A → B → C bằng forwarding rules liên tiếp có được hỗ trợ như mặc định không?  
**Đáp án:** Không; AWS giới hạn forwarding events đã được forward giữa buses.

**Câu 16.** Direct cross-account service targets Classic có yêu cầu cùng Region không?  
**Đáp án:** Có đối với mô hình được công bố; phải kiểm tra danh sách supported targets và Region.

**Câu 17.** Custom Event Bus mới share cho consumer bằng gì?  
**Đáp án:** **AWS RAM** hoặc resource policy phù hợp, thường cấp managed permission SubscribeOnly cho consumer.

**Câu 18.** Gỡ AWS RAM share có luôn hủy subscribers đã tạo không?  
**Đáp án:** Không. Cần xem **RevokeResource/subscriber lifecycle** để dừng hoàn toàn.

**Câu 19.** Custom bus replay cần gọi aws events start-replay không?  
**Đáp án:** Không. Subscriber dùng **POINT_IN_TIME** và starting point trong retention.

**Câu 20.** Custom bus đánh dấu replayed delivery ở đâu?  
**Đáp án:** **SystemMetadata.aws:DeliveryType = REPLAY**.

**Câu 21.** Custom FIFO có bảo đảm exactly-once business side effects không?  
**Đáp án:** Không; vẫn cần idempotency và transaction guards.

**Câu 22.** Sự khác nhau giữa AWS/Events và AWS/EventsV2?  
**Đáp án:** Hai namespace metrics cho **Classic** và **Custom Event Bus mới**.

**Câu 23.** EventsDelivered của Custom subscriber có nghĩa invoice đã commit thành công không?  
**Đáp án:** Không; target accepted delivery khác transaction nghiệp vụ.

**Câu 24.** Vì sao DLQ không thay archive?  
**Đáp án:** DLQ giữ những failed deliveries được cấu hình, còn archive/retention giữ lịch sử rộng hơn để replay.

**Câu 25.** Khi replay events thanh toán cần kiểm tra điều gì trước tiên?  
**Đáp án:** Idempotency key/ledger, target rule selection và risk lặp charge.

**Câu 26.** CLI nào dùng cho Custom Event Bus mới?  
**Đáp án:** **aws eventsv2** với AWS CLI phiên bản hỗ trợ.

## 26. Tổng kết và checklist triển khai

**Hai đường thiết kế cần nhớ:**

- **Classic default/Custom Event Bus – Classic:** route bằng **rules/targets**, cần **Archive** nếu muốn lưu lịch sử; **Replay** phát về cùng source bus và có thể giới hạn rules bằng FilterArns. Định tuyến cross-account qua destination bus policy + sender delivery role, hoặc direct cross-account service targets trong phạm vi được hỗ trợ.
- **Custom Event Bus mới:** **retention tích hợp 1–365 ngày**, consumers tạo **subscribers** và đọc lịch sử bằng **POINT_IN_TIME starting position**; share cross-account qua **AWS RAM** và phân quyền riêng theo owner/consumer.

Checklist trước production:

1. Chọn rõ **bus model**, API/CLI và loại workflow.
2. Thiết kế **event contract**, schemaVersion, eventId nghiệp vụ, aggregate version.
3. Đặt **retention** đúng nhu cầu và bảo vệ dữ liệu nhạy cảm.
4. Phân quyền **publisher, forwarding role, bus policy/RAM share, subscriber delivery role, target**.
5. Kiểm tra **Region/partition** và cross-account support.
6. Có **DLQ/on-failure path, retries có giới hạn, alerts và runbook**.
7. Consumer sử dụng **idempotency, transactional writes và stale-event guard**.
8. Với replay, chọn **time window nhỏ, target rules/subscribers cụ thể**, tránh side effects.
9. Theo dõi đúng **AWS/Events** hoặc **AWS/EventsV2** và business outcomes.
10. Kiểm soát archive/retention, replay traffic, Lambda/SQS/DB và chi phí toàn pipeline.
11. Có cơ chế revoke/offboard cross-account và audit CloudTrail.
12. Diễn tập mất consumer, IAM AccessDenied, expired history, duplicate và rollback.

Amazon EventBridge giúp ứng dụng AWS **phát sự kiện linh hoạt giữa các dịch vụ và tài khoản**, nhưng khả năng phục hồi không đến từ việc lưu lịch sử đơn thuần. Chính **event contract rõ ràng, phân quyền đúng, quan sát đầy đủ, kiểm soát side effects và consumer idempotent** mới biến archive/replay thành một phương án khôi phục đáng tin cậy.

### Tài liệu AWS chính thức

- [EventBridge default và Custom Event Bus – Classic](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-event-bus.html) — rules/targets và mô hình cũ.
- [Archiving and replaying events](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-archive.html) — retention, replay-name, ingestion lag và giới hạn.
- [Creating archives](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-archive-event.html) — archive pattern và retention.
- [Creating replays](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-replay-archived-event.html) — time window và rule selection.
- [Cross-account Classic event buses](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-cross-account.html) — IAM, resource policies, forwarding limitations.
- [Event bus permissions](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-event-bus-perms.html) — quyền publish/rule/target.
- [Cross-account service targets](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-service-cross-account.html) — target service khác account.
- [Custom Event Bus mới](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-custom-bus-what-is.html) — retention, subscriber, ordering và dedup.
- [Custom Event Bus retention](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-custom-bus-create.html) — StorageConfiguration 1–365 ngày.
- [Replaying retained events to subscribers](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-custom-bus-replay.html) — POINT_IN_TIME, HORIZON, REPLAY metadata.
- [Sharing Custom Event Bus](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-custom-bus-sharing.html) — AWS RAM và revoke.
- [Custom Event Bus observability](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-custom-bus-observability.html) — metrics AWS/EventsV2.
- [Monitoring Classic EventBridge](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-monitoring.html) — AWS/Events metrics.
- [Amazon EventBridge pricing](https://aws.amazon.com/eventbridge/pricing/) — chi phí ingest, delivery, archive/replay và retention.







