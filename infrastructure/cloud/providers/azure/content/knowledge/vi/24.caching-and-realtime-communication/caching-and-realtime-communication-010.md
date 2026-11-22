# Thiết kế thông báo trực tiếp kết hợp message và cache

Một ứng dụng bán hàng cần báo ngay khi đơn hàng được thanh toán, một nền tảng học trực tuyến cần cập nhật tiến độ theo thời gian thực, và một hệ thống vận hành cần thông báo sự cố đến đúng nhóm trực ca. Yêu cầu có vẻ đơn giản: “có sự kiện thì gửi thông báo đến trình duyệt”. Nhưng điều gì xảy ra khi người dùng đang offline, một tab mất WebSocket, backend khởi động lại, worker xử lý trùng message hoặc cache bị xóa sạch?

Thiết kế tốt phải tách bốn trách nhiệm:

1. **Message broker** chuyển sự kiện giữa các dịch vụ, hấp thụ tải và hỗ trợ xử lý lại theo cơ chế phù hợp.
2. **Durable notification store** lưu trạng thái thông báo và lịch sử để client có thể truy vấn khi quay lại.
3. **Cache** phục vụ những dữ liệu tạm hoặc được truy cập thường xuyên: unread count, presence, snapshot và rate-limit state.
4. **Realtime gateway** đẩy tín hiệu đến các kết nối đang online qua WebSocket hoặc giao thức ứng dụng hỗ trợ.

Bài học thuộc chương **Cache và giao tiếp thời gian thực** của module **CLOUD_PROVIDERS_AZURE**. Trong lộ trình khám phá Microsoft Azure từ subscription, resource group và Microsoft Entra ID đến mạng, compute, lưu trữ và dữ liệu, đây là tình huống kết hợp kiến trúc ứng dụng: triển khai dịch vụ, bảo vệ danh tính, giám sát, xử lý lỗi và kiểm soát chi phí.

Ví dụ tập trung vào **Azure Service Bus**, **Azure Web PubSub** hoặc **Azure SignalR Service**, **Azure Managed Redis** (và những hệ thống Redis cũ đang được vận hành), **Azure Cosmos DB for NoSQL** hoặc **Azure SQL Database**, cùng ứng dụng **Java**. Các dịch vụ là lựa chọn tham khảo, không phải bắt buộc dùng tất cả trong mọi bài toán.

> **Nguyên tắc cốt lõi:** Đẩy được một frame WebSocket **không chứng minh người dùng đã đọc**, và đưa dữ liệu vào Redis **không mặc nhiên bảo đảm lưu trữ bền vững**. Sự kiện nghiệp vụ, bản ghi thông báo, việc gửi realtime và trạng thái đã đọc là **những trạng thái độc lập**, cần định nghĩa hợp đồng nhất quán.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **event**, **command**, **message**, **notification**, **realtime push**, **ack** và **read receipt**.
2. Giải thích ranh giới trách nhiệm giữa Service Bus, Event Grid, Redis, Web PubSub/SignalR và database.
3. Thiết kế luồng nghiệp vụ **transactional outbox → broker → notification worker → persistent inbox → push**.
4. Phân biệt các mức bảo đảm: accepted by broker, persisted, accepted by realtime service, received by client, displayed và read.
5. Chọn cách lưu notification id, event id, tenant/user id, trạng thái read, timestamp, version và cursor.
6. Dùng **cache-aside**, TTL và versioned invalidation để tăng tốc unread count mà không coi cache là nguồn sự thật.
7. Quản lý presence, nhiều thiết bị, WebSocket reconnect, authentication và quyền xem thông báo.
8. Thiết kế client reconnect, sync lịch sử, dedup và xử lý out-of-order events.
9. Xử lý retry, DLQ, duplicate deliveries, lỗi cache, lỗi gateway, quota và hot user/group.
10. Viết ví dụ Java worker xử lý idempotent và JavaScript client kết nối/đồng bộ theo cursor.
11. Ước lượng throughput, số kết nối, fan-out, memory, network và chi phí vận hành.
12. Thiết lập metrics, SLO, alert, runbook và bài kiểm thử chaos phù hợp production.

## 2. Bài toán xuyên suốt: thông báo đơn hàng

Hãy xem một nền tảng bán hàng có ba loại thông báo:

- **OrderPaid:** khi thanh toán thành công, thông báo chủ đơn hàng.
- **ShipmentUpdated:** khi giao hàng đổi trạng thái, thông báo chủ đơn.
- **OperationalAlert:** khi cổng thanh toán gặp sự cố, thông báo những người thuộc nhóm trực vận hành.

Yêu cầu:

- Người dùng mở website nhận tín hiệu gần thời gian thực.
- Cùng một người đăng nhập trên điện thoại và hai tab trình duyệt có thể nhận trên nhiều kết nối.
- Khi offline 30 phút, thông báo vẫn còn để tải lại sau đăng nhập.
- Tin có id ổn định; client không hiển thị hai thẻ chỉ vì WebSocket reconnect.
- API đọc thông báo phải kiểm tra tenant và user ownership.
- Dữ liệu gốc và trạng thái đã đọc được lưu bền vững.
- Cache bị mất không được làm mất notification history.
- Hệ thống có thể xử lý lưu lượng tăng đột biến và thu thập telemetry để giải thích lỗi.

Một sự kiện minh họa:

~~~json
{
  "eventId": "evt-order-481-paid-1",
  "eventType": "OrderPaid",
  "schemaVersion": 1,
  "tenantId": "tenant-hcm",
  "orderId": "order-481",
  "recipientUserId": "user-91",
  "occurredAtUtc": "2026-11-20T03:10:00Z",
  "correlationId": "corr-481"
}
~~~

Đây là dữ liệu test. Không đưa số thẻ thanh toán, access token, password hoặc thông tin cá nhân không cần thiết vào broker/cache/logs.

## 3. Kiến trúc tham chiếu

~~~mermaid
flowchart LR
    ORD["Orders API"] --> DBTX["Orders database<br/>transaction + outbox"]
    DBTX --> OUT["Outbox relay"]
    OUT --> BUS["Azure Service Bus<br/>topic / subscription"]
    BUS --> WORK["Notification worker<br/>Java / Functions / Container Apps"]
    WORK --> STORE["Durable notification inbox<br/>Cosmos DB / Azure SQL"]
    WORK --> DISPATCH["Notification delivery outbox"]
    DISPATCH --> PUSH["Azure Web PubSub<br/>hoặc Azure SignalR Service"]
    PUSH --> WEB["Web / mobile clients<br/>online connections"]
    WEB --> API["Notifications API<br/>GET feed / PATCH read"]
    API --> CACHE["Azure Managed Redis<br/>unread, presence, throttling"]
    API --> STORE
    WORK -. "invalidate/update" .-> CACHE
    ID["Microsoft Entra ID<br/>identity / RBAC"] -. "auth" .-> ORD
    ID -. "auth" .-> API
    OBS["Azure Monitor / App Insights"] -. "traces / metrics" .-> WORK
    OBS -. "telemetry" .-> PUSH
~~~

Không nhất thiết phải triển khai **delivery outbox** riêng cho hệ thống thử nghiệm nhỏ; nhưng khi cần retry đáng tin sau khi lưu notification mà gateway đang lỗi, một trạng thái dispatch bền vững sẽ giúp tránh phụ thuộc hoàn toàn vào memory/process lifetime.

### 3.1. Trách nhiệm từng thành phần

| Thành phần | Điều nó nên bảo đảm | Điều không nên kỳ vọng |
|---|---|---|
| Orders DB + outbox | Lưu nghiệp vụ và ý định phát sự kiện trong cùng database transaction | Tự phát WebSocket tới browser |
| Service Bus | Lưu/chuyển message cho worker theo retention/TTL, settlement/retry/DLQ đã cấu hình | Chứng minh người dùng cuối đã đọc |
| Notification store | Lưu notification, recipient ownership, read state và cursor | Push realtime tự động |
| Redis cache | Tăng tốc dữ liệu đọc thường xuyên/presence/TTL, chịu cache miss | Là bản duy nhất của thông báo bắt buộc không mất |
| Web PubSub/SignalR | Quản lý kết nối realtime và gửi nội dung tới connections/groups | Lưu một inbox lịch sử cho người dùng offline như database |
| Notifications API | Truy vấn feed, mark-read, kiểm soát quyền và consistency | Tin một userId tự khai từ browser |
| Client | Hiển thị, dedup, reconnect, gọi API đồng bộ | Tự quyết định người khác có quyền xem nội dung |

### 3.2. Đường dữ liệu nóng và đường đồng bộ bền vững

- **Đường realtime:** push một tín hiệu nhẹ “có thay đổi” giúp UI cập nhật nhanh.
- **Đường đáng tin:** client gọi **GET notifications** để lấy các bản ghi đã lưu và đồng bộ sau khi mất kết nối.
- **Đường trạng thái:** **PATCH mark-read** cập nhật database trước, rồi cache được invalidated hoặc rebuild theo version.

Khi latency, throughput và bảo mật cho phép, push có thể chứa payload hiển thị tối thiểu. Nhưng client vẫn phải có cơ chế **resync từ nguồn bền vững** khi reconnect, khi phát hiện gap hoặc khi nghi ngờ message đến trễ.

## 4. Những khái niệm không được đánh đồng

| Khái niệm | Nghĩa chính | Ai quản lý? |
|---|---|---|
| **Domain event** | Một sự kiện đã xảy ra: OrderPaid | Domain producer |
| **Message** | Envelope vận chuyển sự kiện/command qua broker | Producer và broker |
| **Notification** | Bản ghi hướng tới một người/nhóm, có nội dung và trạng thái | Notification service |
| **Push** | Gửi tín hiệu/payload theo kết nối đang online | Realtime gateway |
| **Presence** | Ước lượng user đang có kết nối hoạt động | Gateway/ephemeral cache |
| **Delivery attempt** | Một lần cố gửi tới gateway/client | Dispatcher |
| **Gateway accepted** | Dịch vụ realtime đã chấp nhận lệnh publish | Gateway |
| **Client received** | Ứng dụng client đã nhận và xử lý callback | Client (nếu có ACK) |
| **Displayed** | UI có hiển thị notification | Client telemetry nếu cần |
| **Read** | Người dùng đánh dấu đã đọc theo hợp đồng ứng dụng | Durable store |
| **Unread count** | Projection/số đếm từ trạng thái database | Store là nguồn thật, Redis là cache |
| **Cursor** | Mốc đồng bộ cho feed của user | Notifications API/store |

Ví dụ trạng thái:

~~~text
OrderPaid event → message accepted → notification persisted
→ realtime publish accepted → browser callback fired
→ UI rendered → user clicks "Mark as read"
~~~

Mỗi mũi tên có thể thất bại hoặc xảy ra lặp. Không dùng một cờ **delivered=true** để đại diện cho tất cả những sự kiện này.

## 5. Chọn Azure messaging service

### 5.1. Azure Service Bus

**Azure Service Bus queues/topics/subscriptions** thường thích hợp khi:

- Worker phải xử lý message bất đồng bộ.
- Cần **PeekLock**, Complete/Abandon, retry, MaxDeliveryCount và DLQ.
- Có nhiều loại consumer độc lập nhận sự kiện từ một producer.
- Cần phân luồng/filter, session ordering hoặc duplicate detection theo tier và cấu hình.
- Quan trọng nhất là **xử lý nghiệp vụ có khả năng phục hồi**, không chỉ phát tín hiệu nhanh.

Ví dụ: **OrderPaid** được publish lên topic; subscription của Notification Worker nhận event và tạo inbox record. Subscription khác có thể ghi báo cáo/audit.

### 5.2. Event Grid

**Azure Event Grid** phù hợp khi:

- Cần routing thông báo sự kiện như BlobCreated, resource events hoặc các domain events.
- Luồng push/pull delivery, retries/TTL/DLQ đến destination theo loại topic/subscription và cấu hình hỗ trợ.
- Một sự kiện được định tuyến tới nhiều handlers.

Event Grid có các semantics riêng. **Không thay thế mọi workflow queue có PeekLock/session/transaction bằng Event Grid** khi các yêu cầu đó là trọng tâm.

### 5.3. Storage Queue

**Azure Queue Storage** là lựa chọn tương đối đơn giản cho background work nếu không cần nhiều tính năng nâng cao của Service Bus. Phải xét message size, visibility timeout, poison message và cách fan-out nếu có nhiều consumer types.

### 5.4. Azure Event Hubs

**Azure Event Hubs** phục vụ event stream thông lượng lớn, retention và consumer groups. Có ích cho telemetry/clickstream, nhưng không có settlement/DLQ per message như Service Bus queue. Không chọn Event Hubs chỉ vì thấy chữ “event” trong domain event.

### 5.5. Quy tắc chọn nhanh

| Nhu cầu | Ưu tiên |
|---|---|
| Orders event cần reliable worker và DLQ | Service Bus |
| BlobUpdated cần thông báo đến Functions | Event Grid |
| Job nền đơn giản, ít yêu cầu routing | Storage Queue |
| Telemetry hàng triệu events/giờ và replay | Event Hubs |
| Chỉ phát tới browser đang kết nối | Realtime gateway, nhưng vẫn cần store nếu yêu cầu offline |
| Cần nhiều notification consumers khác nhau | Service Bus topic/subscriptions hoặc Event Grid theo semantics |
| Notification tạm, mất được, rất ít hệ thống | Có thể thiết kế tối giản không broker, nhưng phải công bố rủi ro |

## 6. Redis là cache, không phải thông báo bền vững

Trong Azure, có thể đánh giá **Azure Managed Redis** cho hệ thống mới. Với những ứng dụng đang dùng **Azure Cache for Redis**, phải kiểm tra vòng đời sản phẩm, thời hạn hỗ trợ, tính tương thích và migration plan hiện hành thay vì tự mặc định hai dịch vụ có cùng SKU/tính năng.

Redis có thể giúp:

- Cache danh sách **notification preview** mới nhất với TTL ngắn.
- Cache **unread count** được tạo từ nguồn dữ liệu bền vững.
- Lưu **presence heartbeat**/ephemeral connection hints theo policy.
- Giới hạn tần suất thông báo/rate-limit counters.
- Giảm đọc lặp lại database trong những đợt traffic lớn.

Redis **không nên** là nơi duy nhất lưu các notification quan trọng nếu yêu cầu offline retrieval, audit, user read state và khôi phục dài hạn.

### 6.1. Redis Pub/Sub khác message broker bền vững

Redis **Pub/Sub** gửi đến những subscribers đang nghe. Thông điệp Pub/Sub không trở thành lịch sử durable có thể replay theo mô hình queue truyền thống. Nếu client/worker ngắt kết nối tại thời điểm publish, bạn không được mặc nhiên kỳ vọng nhận lại.

Redis **Streams** có mô hình lưu log/consumer groups khác Pub/Sub. Nó có thể phù hợp những workload được đánh giá riêng, nhưng nếu kiến trúc chính đã dùng Service Bus cho reliable events thì thêm Redis Streams như broker thứ hai có thể làm tăng state và vận hành không cần thiết.

**Quy tắc:** Service Bus chuyển message nghiệp vụ; Redis tăng tốc truy vấn/trạng thái ngắn hạn; Web PubSub/SignalR đưa cập nhật ra WebSocket.

### 6.2. Cache có thể bị mất

Các tình huống:

- Key hết TTL.
- Redis failover/restart.
- Eviction do memory pressure/policy.
- Cache invalidation bị trễ.
- Một deployment flush nhầm keys.
- Kết nối mạng tới cache gián đoạn.

**Cache miss là tình huống bình thường**, không phải lý do làm mất unread count hoặc lịch sử notifications. API phải có fallback tới durable store hoặc báo lỗi phù hợp tùy SLO, thay vì trả một trạng thái sai là “bạn không có thông báo”.

## 7. Chọn Web PubSub, SignalR hay polling?

### 7.1. Azure Web PubSub

**Azure Web PubSub** là dịch vụ managed để kết nối và phân phối message tới clients qua WebSocket với mô hình hub/group/user và handler/event patterns được dịch vụ hỗ trợ.

Phù hợp khi:

- Client web/mobile cần WebSocket protocol.
- Backend Java, .NET, JavaScript hoặc dịch vụ khác muốn đẩy tới user/group.
- Muốn giảm gánh vận hành WebSocket fleet, scale connections và fan-out.
- Client cần hỗ trợ reconnect và trao đổi payload có chủ đích.

### 7.2. Azure SignalR Service

**Azure SignalR Service** thường phù hợp khi ứng dụng dùng **ASP.NET Core SignalR** hoặc hệ sinh thái client/server SignalR có hỗ trợ. Nó cung cấp managed realtime connections và scale-out SignalR theo mô hình dịch vụ.

**SignalR và raw WebSocket không cùng một protocol contract.** Không tạo một SignalR hub rồi dùng WebSocket JavaScript thuần gửi tùy ý như Web PubSub mà không hiểu handshake/giao thức/SDK.

### 7.3. Server-Sent Events và polling

- **SSE (Server-Sent Events):** kênh server → browser theo HTTP; có thể phù hợp feed một chiều. Cần thiết kế reconnect, proxy buffering, scale, token handling.
- **Long polling:** client giữ request chờ thay đổi; dễ tích hợp nhưng tăng số requests và latency tùy interval.
- **Periodic polling:** client hỏi GET /notifications mỗi N giây; đơn giản, có thể đủ nếu lượng user nhỏ và không cần cập nhật ngay.

Đừng áp WebSocket lên mọi màn hình chỉ vì “realtime nghe hiện đại”.

### 7.4. Bảng quyết định

| Trường hợp | Lựa chọn gợi ý | Trade-off |
|---|---|---|
| Dashboard cần update mỗi 30 giây, traffic nhỏ | Polling/SSE | Đơn giản, ít state connections |
| 100.000 clients cần push gần realtime | Web PubSub/managed realtime | Quản lý reconnect, auth, connections/cost |
| ASP.NET Core có SignalR hubs sẵn | Azure SignalR Service | Phụ thuộc protocol/SDK SignalR |
| Java backend muốn push tới browser không dùng SignalR | Azure Web PubSub | Phải định nghĩa auth/negotiation và payload protocol |
| Mobile OS background/offline alert | APNs/FCM/platform push + durable inbox | WebSocket thường không tồn tại khi app bị suspend |
| Workflow cần email/SMS pháp lý | Notification provider/Logic Apps phù hợp + audit | WebSocket không thay kênh ngoài ứng dụng |

## 8. Định nghĩa hợp đồng notification

Không nên gửi raw event tới client rồi để browser tự đoán business semantics.

### 8.1. Notification object bền vững

~~~json
{
  "id": "notif-tenant-hcm-user-91-order-481-paid-v1",
  "tenantId": "tenant-hcm",
  "recipientUserId": "user-91",
  "sourceEventId": "evt-order-481-paid-1",
  "type": "ORDER_PAID",
  "schemaVersion": 1,
  "title": "Đơn hàng đã thanh toán",
  "body": "Đơn hàng của bạn đã được xác nhận thanh toán.",
  "link": "/orders/order-481",
  "createdAtUtc": "2026-11-20T03:10:03Z",
  "readAtUtc": null,
  "expiresAtUtc": null
}
~~~

**id** nên ổn định cho cùng một thông báo nghiệp vụ; có thể sinh theo rule deterministic hoặc ghi một lần và lưu mapping để dedup. Không dùng thông tin cá nhân nhạy cảm trong ID.

### 8.2. Tách business event và notification

Ví dụ cùng một **OrderPaid** có thể sinh:

- Notification cho khách hàng.
- Notification cho nhân viên phụ trách.
- Message báo cáo cho hệ thống tài chính.
- Một email receipt nếu business rule yêu cầu.

**Một domain event không đồng nghĩa một notification**. Việc quyết định người nhận, kênh, template và độ ưu tiên là trách nhiệm Notification Service.

### 8.3. Các khóa giúp idempotency

| Khóa | Vai trò |
|---|---|
| **eventId** | Dedupe domain event do producer phát |
| **notificationId** | Định danh một notification của một recipient |
| **tenantId** | Ranh giới dữ liệu nghiệp vụ |
| **recipientUserId** | Xác định inbox người nhận |
| **dispatchAttemptId** | Audit một lần thử gửi realtime |
| **correlationId/traceId** | Truy vết xuyên services |
| **cursor** | Mốc đồng bộ feed |
| **schemaVersion** | Quản lý thay đổi payload contract |

Một eventId có thể tương ứng nhiều notificationIds; không áp unique eventId toàn bộ bảng notification nếu sự kiện fan-out cho nhiều recipients.

### 8.4. Trạng thái vận chuyển và trạng thái đã đọc

Mô hình ví dụ:

~~~text
Notification:
    CREATED → AVAILABLE → READ/ARCHIVED

Delivery attempt:
    PENDING → PUBLISH_ATTEMPTED → GATEWAY_ACCEPTED/FAILED

Client state:
    CONNECTED → RECEIVED → DISPLAYED (telemetry tùy chọn)

Business acknowledgement:
    UNREAD → READ
~~~

Không gộp **GATEWAY_ACCEPTED** vào **READ**. Việc gửi frame tới connection không biết người dùng đã nhìn màn hình hay chưa.

## 9. Persistent inbox: chọn Azure SQL hay Cosmos DB

### 9.1. Azure SQL

Một schema ví dụ:

~~~sql
-- Pseudocode DDL định hướng, cần thiết kế constraint/index thực tế.
CREATE TABLE Notifications (
    NotificationId VARCHAR(160) PRIMARY KEY,
    TenantId VARCHAR(80) NOT NULL,
    RecipientUserId VARCHAR(80) NOT NULL,
    NotificationType VARCHAR(80) NOT NULL,
    SourceEventId VARCHAR(160) NOT NULL,
    CreatedAtUtc DATETIME2 NOT NULL,
    ReadAtUtc DATETIME2 NULL,
    PayloadJson NVARCHAR(MAX) NOT NULL
);

CREATE INDEX IX_Notifications_Recipient_Time
ON Notifications (TenantId, RecipientUserId, CreatedAtUtc DESC);
~~~

Có thể bổ sung unique constraint theo **tenant + recipient + event + notification type**, và thiết kế retention/partitioning tùy volume. SQL transaction giúp lưu notification cùng một **delivery-outbox record** nếu chúng nằm trong cùng database.

### 9.2. Azure Cosmos DB for NoSQL

Một item JSON là notification. Với access pattern “lấy feed cho một user trong tenant”, cần chọn partition key phục vụ phân phối và truy vấn, ví dụ **/inboxKey**, nơi inboxKey là **tenantId + userId** hoặc một hierarchical key được hỗ trợ.

~~~json
{
  "id": "notif-481-paid",
  "inboxKey": "tenant-hcm:user-91",
  "tenantId": "tenant-hcm",
  "recipientUserId": "user-91",
  "type": "ORDER_PAID",
  "sourceEventId": "evt-order-481-paid-1",
  "createdAtUtc": "2026-11-20T03:10:03Z",
  "readAtUtc": null
}
~~~

**Cần đánh giá hot users:** một tổ chức có tài khoản chung nhận hàng triệu notifications có thể làm một logical partition nóng. Với tenant/group broadcast quy mô lớn, không nên tạo một item cho mọi người nhận khi không cần, cũng không nên dùng một partition key thấp cardinality như **/read**.

### 9.3. Read patterns

| API | Đầu vào đã biết | Storage design |
|---|---|---|
| GET /notifications | tenantId, userId, limit, cursor | Indexed query trong inbox partition |
| GET /notifications/unread-count | tenantId, userId | Store query/projection, cache-aside |
| PATCH /notifications/{id}/read | tenantId, userId, id | Conditional update; check ownership |
| GET /notifications?since=cursor | Tenant/user/cursor | Keyset pagination hoặc server cursor |
| GET /notifications/{id} | Tenant/user/id | Point read/query theo key |
| Admin audit | Filter theo event/source/tenant | Có thể cần index/materialized audit model |

### 9.4. Pagination và cursor

Không dùng **OFFSET 100000** làm cơ chế duy nhất cho feed có update liên tục. Với SQL, có thể dùng keyset pagination trên cặp **(CreatedAtUtc, NotificationId)** và index phù hợp; với Cosmos DB, dùng continuation token do SDK tạo hoặc thiết kế cursor hợp lệ với query.

Không dùng **Date.now() từ trình duyệt** làm mốc duy nhất để tránh bỏ sót: đồng hồ client có thể sai, nhiều notifications có cùng timestamp và network/reconnect có thể làm thứ tự lệch.

Để client đồng bộ chắc chắn, cursor phải đại diện cho **thứ tự bền vững do server quản lý** với tie-breaker/semantics nhất quán; có thể là opaque token và cần version khi schema/query thay đổi.

## 10. Transactional outbox: ngăn mất domain event

Giả sử Orders API làm:

~~~text
INSERT/UPDATE Orders trong Azure SQL
rồi SEND OrderPaid vào Service Bus
~~~

Nếu ứng dụng crash sau DB commit nhưng trước broker send, order được đánh dấu PAID nhưng không có notification. Nếu broker đã nhận nhưng client mất HTTP response, producer retry có thể gửi trùng.

### 10.1. Lưu business change và outbox trong cùng transaction

~~~mermaid
flowchart TD
    API["Orders API"] --> TX["SQL transaction"]
    TX --> ORD["Orders: status=PAID"]
    TX --> OUT["Outbox: OrderPaid event"]
    OUT --> RELAY["Outbox relay/publisher"]
    RELAY --> SB["Service Bus topic"]
    SB --> NWORK["Notification consumer"]
~~~

Quy trình:

1. Ghi trạng thái Order và Outbox record trong **cùng transaction DB**.
2. Commit.
3. Outbox publisher đọc records chưa phát.
4. Gửi Service Bus message với **MessageId** ổn định.
5. Khi broker xác nhận, đánh dấu outbox published.
6. Nếu crash giữa bước 4 và 5, publisher có thể gửi lại: consumer xử lý idempotent.

**Transactional outbox không biến HTTP call, Service Bus và DB thành một distributed ACID transaction.** Nó lưu bền vững ý định phát event và chấp nhận **at-least-once publication** có dedup.

### 10.2. Lưu notification và delivery outbox

Notification worker nhận Service Bus message rồi có thể:

1. Xác định recipients từ dữ liệu đáng tin.
2. Trong **một transaction của notification database**, insert notification nếu chưa có và insert **delivery-outbox** record.
3. Commit DB.
4. Complete Service Bus message.
5. Dispatcher riêng lấy delivery-outbox, phát qua Web PubSub/SignalR và cập nhật attempt status.

Nếu worker crash sau DB commit trước **Complete**, message được redeliver nhưng unique key/upsert có kiểm soát giúp tránh tạo hai notification. Nếu dispatcher crash sau realtime send trước khi đánh dấu sent, client có thể nhận lặp; **client dedup theo notificationId**.

Không đưa lời gọi WebSocket gateway vào cùng transaction SQL dài nhằm tìm kiếm “exactly-once push”: gateway không tham gia transaction đó.

## 11. Service Bus topic, subscription, retry và DLQ

Một thiết kế:

~~~text
Topic: commerce-events

Subscription: notifications
    Filter: OrderPaid, ShipmentUpdated

Subscription: analytics
    Filter: domain events phù hợp

Notification consumer:
    PeekLock → durable inbox + delivery outbox → Complete

Nếu lỗi transient:
    Retry/Abandon/backoff theo policy

Nếu event sai định dạng / không thể xử lý:
    Dead-letter với reason + correlation
~~~

### 11.1. Vì sao dùng PeekLock?

Với **PeekLock**, consumer nhận message nhưng chưa xóa khỏi subscription. Nó cần **Complete** sau khi đã lưu bền vững, hoặc settle theo nhánh xử lý lỗi.

Nếu **ReceiveAndDelete**, message bị loại khi broker giao cho receiver theo semantics dịch vụ, có thể mất nếu worker crash trước DB commit.

### 11.2. Retry và idempotency

- Retry phải có giới hạn và phân loại transient/permanent errors.
- Dùng **MessageId** ổn định; nếu bật duplicate detection, phải hiểu cửa sổ dedup.
- Xử lý trùng ngay tại notification DB, không chỉ dựa vào broker duplicate detection.
- **MaxDeliveryCount** giúp gửi poison messages tới DLQ theo cấu hình.
- Không xử lý vô hạn một message lỗi khiến consumer không tiến.
- Nếu lỗi cả database, cân nhắc giảm/pause consumers thay vì dead-letter hàng triệu messages.

### 11.3. Sessions có cần thiết?

Service Bus **Sessions** có thể giúp điều phối thứ tự theo **SessionId**, ví dụ cùng orderId, nếu entity/tier được cấu hình session-enabled.

Nhưng:

- Sessions có giới hạn concurrency/throughput theo hot session.
- Không bảo đảm thứ tự toàn cục giữa users hoặc orders.
- Realtime gateway và internet có thể khiến client nhìn thấy push khác thứ tự.
- Dù có sessions, client vẫn nên dùng id/version và resync.

Chỉ bật sessions nếu thực sự cần xử lý tuần tự một nhóm nghiệp vụ.

### 11.4. Fan-out theo người nhận

Một event cần gửi tới 100.000 người:

- Không chạy 100.000 DB writes và realtime sends trong một broker transaction kéo dài.
- Phân tách công việc thành **fan-out batches** có checkpoints, idempotency và giới hạn concurrency.
- Với broadcast không yêu cầu mỗi user có inbox record riêng, có thể lưu **announcement** một lần và membership/read cursor riêng theo thiết kế.
- Với thông báo bắt buộc cho từng user, cần lưu delivery/recipient state, quản lý backlog, TTL, quota và chi phí rõ ràng.

## 12. Cache-aside cho unread count và feed preview

### 12.1. Cache key có namespace rõ

Ví dụ:

~~~text
notif:unread:v1:tenant-hcm:user-91
notif:preview:v1:tenant-hcm:user-91
presence:v1:tenant-hcm:user-91
ratelimit:v1:tenant-hcm:user-91:minute
~~~

Tránh đặt email/phone/raw token trong Redis key vì key names có thể xuất hiện trong telemetry/backup/operations. Nếu user IDs cũng nhạy cảm, cân nhắc surrogate IDs hoặc hash/HMAC có key quản lý.

### 12.2. Unread count cache-aside

~~~mermaid
flowchart TD
    API["GET /notifications/unread-count"] --> C{"Redis key tồn tại?"}
    C -->|Có| HIT["Trả count cached<br/>theo freshness contract"]
    C -->|Không| DB["Query/projection từ durable store"]
    DB --> SET["Cache SET với TTL"]
    SET --> RESP["Trả count"]
~~~

Các bước:

1. API xác thực và kiểm tra tenant/user ownership.
2. Tìm Redis key.
3. Nếu hit, trả cached value theo freshness/SLO.
4. Nếu miss, tính từ database/projection.
5. Cache lại với TTL và trả response.
6. Khi có thông báo mới/mark-read, invalidate hoặc cập nhật có điều kiện.

**Redis count không phải nguồn sự thật.** Redis có thể mất key, bị lệch hoặc stale; API phải biết fallback và tolerance.

### 12.3. Vì sao không INCR/DECR mù?

Giả sử event được Service Bus giao hai lần:

~~~text
Notification N1 được persist đúng một lần
Worker xử lý lần 1 → Redis INCR unread
Worker crash trước Complete
Worker xử lý lại → Redis INCR unread lần 2
~~~

Database có 1 thông báo chưa đọc, Redis trả 2.

Giải pháp:

- Chỉ cập nhật cache khi **thực sự insert mới** hoặc state chuyển từ UNREAD → READ.
- Đảm bảo idempotency ở DB và cache update logic.
- Cách đơn giản, ít rủi ro hơn: **invalidate** key sau DB commit, lần đọc tiếp tính lại.
- Với tải lớn có thể dùng versioned projection/counter bền vững, rồi cache snapshot.
- Định kỳ reconcile count với database.

### 12.4. Race giữa refill và invalidate

Một race phổ biến:

~~~text
T1 API đọc count=5 từ DB (trước insert N6)
T2 worker insert N6, xóa cache key
T3 API ghi count=5 vào Redis sau khi xóa
Kết quả: Redis có count cũ cho đến TTL
~~~

Đây không chỉ là lỗi race lý thuyết. Giải pháp tùy yêu cầu:

- TTL ngắn và chấp nhận eventual consistency cho badge.
- **Versioned cache** gắn với version/read model trong DB.
- Atomic compare-and-set bằng Redis Lua/transaction phù hợp.
- Read-through projection với sequence/version ordering.
- Tránh cập nhật Redis sau khi đã có version mới.
- Nếu badge phải hoàn toàn chính xác ngay, đọc trực tiếp DB hoặc dùng projection bền vững có transaction/consistency phù hợp.

Không dùng một cache invalidation callback không có bảo đảm để định nghĩa tính đúng đắn của số liệu tài chính.

## 13. Presence và nhiều kết nối của cùng user

Một người dùng có thể có:

~~~text
user-91:
    Browser tab A
    Browser tab B
    Mobile foreground session C
~~~

Presence phải được hiểu là **ước lượng online**, không phải trạng thái tuyệt đối.

### 13.1. Heartbeat với TTL

Một thiết kế ví dụ:

- Client gửi heartbeat mỗi **15 giây** khi kết nối.
- Backend/gateway ghi presence TTL **45 giây** (số liệu minh họa).
- Nếu không có heartbeat, key có thể tự hết hạn.
- Reconnect sẽ tạo connection mới; disconnect event có thể đến trễ.
- Không dùng presence để quyết định có lưu notification hay không.

**Thời gian heartbeat/TTL là giả định thiết kế**, cần kiểm thử trong điều kiện mạng mobile, browser background throttling và gateway events thực tế.

### 13.2. Connection IDs không phải danh tính bền vững

- Connection ID có thể đổi sau reconnect.
- Một user có nhiều connection IDs.
- Token kết nối có thời hạn và scope.
- Không lưu một connection ID làm foreign key cho lịch sử notification.
- Nhóm realtime theo **tenant + recipient** hoặc managed user identity giúp publish thuận tiện hơn, với authorization server-side.
- Phải kiểm soát group membership, không để client tự chọn group **admin-alerts**.

### 13.3. Khi gateway đã quản lý connections

Azure Web PubSub/SignalR có cơ chế quản lý connections/groups theo sản phẩm. Không cần nhân bản toàn bộ connection registry vào Redis nếu chỉ để gửi message và gateway đã hỗ trợ send-to-user/group. Redis presence chỉ nên lưu khi ứng dụng thực sự có use case cần, chẳng hạn gợi ý người đang online, và phải chấp nhận stale presence.

### 13.4. Không nhầm online với đã nhận

Gateway có thể cho biết một user có kết nối, nhưng:

- Client có thể vừa disconnect.
- Một tab ở background chưa render.
- Mobile app có thể bị hệ điều hành suspend.
- Người dùng chưa mở trang notification.
- Một message có thể đến trùng hoặc sai thứ tự.

Vì vậy **presence không được dùng làm điều kiện xóa inbox record**.

## 14. Đàm phán kết nối và bảo mật realtime

Với Web PubSub hoặc SignalR, client thường cần thông tin kết nối/token do backend tin cậy cung cấp theo SDK/service design.

Một giao thức minh họa:

~~~mermaid
sequenceDiagram
    participant U as Browser
    participant A as Notifications API
    participant I as Entra ID / Auth
    participant G as Realtime gateway
    U->>A: POST /realtime/negotiate + access token
    A->>I: Validate identity/claims
    I-->>A: tenantId + userId
    A->>G: Create limited-time client access URL/token
    G-->>A: Scoped connection URL
    A-->>U: Connection URL with short expiry
    U->>G: Connect WebSocket over TLS
    G-->>U: Connected
    U->>A: GET /notifications?cursor=...
    A-->>U: Durable feed snapshot
~~~

Đây là **mô hình khái niệm**; endpoint và APIs cụ thể phụ thuộc sản phẩm và SDK.

### 14.1. Không cấp quyền gửi tùy ý

Client chỉ cần **nhận notification của chính mình**. Token/role cấp cho browser không nên có quyền publish tới group tùy ý, đọc group của tenant khác hoặc tham gia nhóm admin không được xác thực.

### 14.2. Backend lấy danh tính từ token

Không làm:

~~~text
POST /realtime/negotiate
{"userId":"ceo"}
→ cấp token cho user=ceo
~~~

Thay vào đó:

~~~text
Validated access token → tenantId/userId đáng tin
→ server xác định group/user mapping
→ cấp token scope tối thiểu với TTL ngắn
~~~

### 14.3. Dữ liệu nhạy cảm trong connection URL

Access URL/token có thể xuất hiện trong logs, browser history, diagnostics hoặc proxy nếu không kiểm soát. Cần:

- TLS/WSS.
- Token ngắn hạn và không lộ server access key.
- Không log query string chứa token.
- CORS/origin restrictions theo sản phẩm và gateway configuration.
- Hạn chế TTL và scope; refresh/reconnect an toàn.
- Không lưu access token trong Redis hoặc localStorage nếu policy tổ chức không cho phép.

### 14.4. Tenant isolation

Một group name như **user-91** có thể trùng giữa tenants. Dùng identity/group mapping chứa **tenant scope** và backend authorization:

~~~text
group = "tenant-hcm:user-91"
group = "tenant-hn:user-91"
~~~

Tên group chỉ là **routing aid**, không phải thay thế kiểm tra quyền ở Notifications API.

## 15. Giao thức client: push + resync

### 15.1. Thiết kế API

~~~text
POST  /realtime/negotiate
GET   /notifications?limit=50&cursor=<opaque-cursor>
GET   /notifications/unread-count
PATCH /notifications/{notificationId}/read
POST  /notifications/read-all
~~~

Phản hồi mẫu:

~~~json
{
  "items": [
    {
      "id": "notif-481-paid",
      "type": "ORDER_PAID",
      "title": "Đơn hàng đã thanh toán",
      "createdAtUtc": "2026-11-20T03:10:03Z",
      "readAtUtc": null,
      "link": "/orders/order-481"
    }
  ],
  "nextCursor": "opaque-cursor-issued-by-server",
  "hasMore": false,
  "unreadCount": 1,
  "snapshotVersion": "v-9381"
}
~~~

Không đưa một cursor tự chế thiếu version/tie-breaker vào production và giả định nó luôn thể hiện đầy đủ thứ tự cập nhật ở nhiều region.

### 15.2. Server push nhỏ, client tải dữ liệu đáng tin

Một message realtime tối giản:

~~~json
{
  "type": "NOTIFICATION_AVAILABLE",
  "notificationId": "notif-481-paid",
  "recipientVersion": "v-9381",
  "emittedAtUtc": "2026-11-20T03:10:04Z"
}
~~~

Client có thể:

1. Nhận push.
2. Dedupe notificationId.
3. Gọi GET feed hoặc fetch notification theo id bằng token hợp lệ.
4. Cập nhật badge và danh sách.
5. Lưu cursor sau khi đã hợp nhất dữ liệu vào state.
6. Khi reconnect luôn thực hiện resync, không chỉ chờ push mới.

Nếu có payload đầy đủ, client có thể render ngay để giảm latency nhưng **backend store vẫn là nguồn đồng bộ**.

### 15.3. Hai thứ tự có thể lệch nhau

- Notification A tạo trước B trong database.
- Gateway có thể gửi B trước A vì retry/reconnect/nhiều dispatch workers.
- Client phải sort theo server-issued stable order và nhận diện bản cập nhật mới bằng version.
- Trạng thái **READ** không được bị một push cũ ghi đè thành **UNREAD**.
- Hệ thống không nên cam kết global ordering giữa mọi users nếu không thực sự cần.

## 16. Đồng bộ khi client offline hoặc reconnect

Đường WebSocket chỉ chuyển tín hiệu cho **kết nối đang tồn tại**. Khi user mất mạng, tắt browser hoặc mobile app bị suspend, hệ thống phải có đường **resync từ inbox bền vững**.

### 16.1. Quy trình reconnect

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Notifications API
    participant G as Web PubSub
    participant D as Durable inbox
    C->>A: Authenticate + POST /realtime/negotiate
    A-->>C: Short-lived, scoped WebSocket URL
    C->>G: WebSocket connect
    G-->>C: Connected
    C->>A: GET /notifications?cursor=...
    A->>D: Query authorized user inbox
    D-->>A: Page + cursor + version
    A-->>C: Durable notification items
    C->>C: Merge / dedup by notificationId
    G-->>C: NOTIFICATION_AVAILABLE hint
    C->>A: Fetch new items
~~~

**Kết nối rồi GET lại inbox** thường an toàn hơn việc chỉ chờ push. Nếu một push tới ngay khi đang GET, client có thể nhìn thấy một item hai lần; phải hợp nhất bằng **notificationId**. Nếu push tới đúng lúc một vòng sync đang chạy, client phải đặt **syncPending** rồi chạy thêm một vòng, không bỏ qua tín hiệu đó.

### 16.2. Cursor và nguồn thời gian

- Không lấy **Date.now của browser** làm cursor duy nhất.
- Dùng mốc thứ tự **do backend cấp**, có tie-breaker cho các items cùng timestamp.
- SQL có thể dùng **keyset pagination** theo cặp stable sort key; Cosmos DB có thể dùng continuation token theo query/partition.
- Với nhiều region, kiểm tra consistency và cơ chế cấp thứ tự; không tự tuyên bố timestamp của một máy là global sequence.
- Cursor phải bị ràng buộc với **user, tenant, query, schema version**; không cho caller dùng cursor của người khác để lộ dữ liệu.
- Khi có nhiều trang, lưu tiến độ chỉ sau khi các trang đã merge thành công, không đánh dấu sync complete khi còn **hasMore=true**.

### 16.3. Multiple tabs/devices

Ba kết nối của một user có thể nhận cùng notification. State READ/UNREAD thường được lưu **chung ở backend** trừ khi sản phẩm quy định theo thiết bị. Tab B mark-read cần khiến tab A đồng bộ lại state; push có thể hỗ trợ nhanh nhưng reconnect/API vẫn là đường đáng tin.

### 16.4. Mobile push không giống WebSocket

Khi app chạy nền hoặc thiết bị tắt, WebSocket thường không duy trì. Nếu cần thông báo ngoài ứng dụng, thêm **APNs/FCM** hoặc provider phù hợp. Device token, opt-in, privacy và retry cần được quản lý, nhưng durable inbox vẫn là nguồn để người dùng mở app và xem lịch sử.

## 17. Java: xử lý Service Bus message idempotent

Mẫu xử lý:

~~~text
Service Bus: OrderPaid (PeekLock)
→ validate schema + business recipient
→ transaction trong Notification DB:
      INSERT notification IF ABSENT
      INSERT delivery-outbox IF NEW
  COMMIT
→ Complete Service Bus message
→ Dispatcher riêng xử lý delivery-outbox
~~~

### 17.1. Domain types và repository

~~~java
package example.notifications;

public record OrderPaidEvent(
        String eventId,
        String tenantId,
        String orderId,
        String recipientUserId) {}

public record Notification(
        String notificationId,
        String tenantId,
        String recipientUserId,
        String sourceEventId,
        String orderId,
        String type) {}

public interface NotificationRepository {
    /**
     * Một database transaction:
     * - Insert notification theo unique notificationId nếu mới.
     * - Chỉ khi mới, insert một delivery-outbox record.
     * - Commit cả hai hoặc rollback cả hai.
     *
     * Return true nếu tạo mới; false khi event được xử lý trước đó.
     */
    boolean insertNotificationAndDispatchIntentIfAbsent(
            Notification notification);
}
~~~

Đây là ba Java types cần đặt trong các file thích hợp của Java project, chưa có implementation JDBC/Cosmos. **Unique constraint** ở database, không phải một **Set** trong RAM, là biện pháp chống trùng quan trọng khi nhiều worker scale-out.

### 17.2. Handler tách khỏi transport

~~~java
package example.notifications;

public final class OrderPaidHandler {
    private final NotificationRepository repository;

    public OrderPaidHandler(NotificationRepository repository) {
        this.repository = repository;
    }

    public boolean handle(OrderPaidEvent event) {
        if (event == null || blank(event.eventId())
                || blank(event.tenantId())
                || blank(event.orderId())
                || blank(event.recipientUserId())) {
            throw new IllegalArgumentException("Invalid event");
        }

        String notificationId =
            "order-paid:" + event.tenantId() + ":"
            + event.recipientUserId() + ":" + event.eventId();

        Notification item = new Notification(
            notificationId,
            event.tenantId(),
            event.recipientUserId(),
            event.eventId(),
            event.orderId(),
            "ORDER_PAID");

        return repository
            .insertNotificationAndDispatchIntentIfAbsent(item);
    }

    private static boolean blank(String value) {
        return value == null || value.isBlank();
    }
}
~~~

ID ghép trường chỉ là minh họa. Production có thể hash một canonical business key để tránh lộ thông tin nhạy cảm, giới hạn độ dài và áp uniqueness bằng DB.

### 17.3. Khung Service Bus processor

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.messaging.servicebus.ServiceBusClientBuilder;
import com.azure.messaging.servicebus.ServiceBusProcessorClient;

import java.util.concurrent.CountDownLatch;

// Khởi tạo qua dependency injection.
OrderPaidHandler handler = /* repository-backed handler */ null;

ServiceBusProcessorClient processor =
    new ServiceBusClientBuilder()
        .credential(
            System.getenv("SERVICEBUS_FQDN"),
            new DefaultAzureCredentialBuilder().build())
        .processor()
        .topicName("commerce-events")
        .subscriptionName("notifications")
        .disableAutoComplete()
        .processMessage(context -> {
            try {
                // parseValidatedEvent là hàm cần hiện thực.
                OrderPaidEvent event =
                    parseValidatedEvent(context.getMessage());

                handler.handle(event);
                // Chỉ complete khi durable DB commit xong.
                context.complete();
            } catch (IllegalArgumentException badPayload) {
                // Dùng deadLetter với reason qua API SDK
                // phù hợp và ghi correlation/diagnostics.
                settlePermanentFailure(context, badPayload);
            } catch (Exception transientFailure) {
                // Retry/backoff phải có giới hạn.
                context.abandon();
            }
        })
        .processError(error ->
            System.err.println(error.getThrowable()))
        .buildProcessorClient();

Runtime.getRuntime().addShutdownHook(
    new Thread(processor::close));
processor.start();
new CountDownLatch(1).await();
~~~

**Đây là code khung, không chạy nguyên trạng**: cần imports domain types, **parseValidatedEvent**, **settlePermanentFailure**, repository adapter và injected handler. SDK package/API phải được pin theo phiên bản đang dùng. Với lỗi kéo dài, không liên tục abandon thành hot loop; cân nhắc dừng consumer/circuit breaker hoặc scheduling retry có giới hạn.

### 17.4. Bảng crash window

| Điểm crash | Kết quả | Cách phục hồi |
|---|---|---|
| Trước DB commit | Broker chưa Complete | Worker nhận lại |
| Trong DB transaction | DB rollback hoặc outcome cần xác minh | Retry/idempotency |
| Sau DB commit, trước Complete | Inbox/outbox đã có, broker redeliver | Unique key → không insert trùng |
| Sau Complete, trước push | Delivery outbox pending | Dispatcher tiếp tục |
| Sau push, trước mark-dispatched | Có thể publish lại | Client dedup notificationId |

Không hứa “exactly-once WebSocket delivery”. Mục tiêu thực dụng là **durable at-least-once processing**, notification identity idempotent và client convergence.

## 18. Dispatcher: push là một tác vụ có retry riêng

### 18.1. Tách interface gateway khỏi nghiệp vụ

~~~java
package example.notifications;

public interface RealtimePublisher {
    /**
     * Push tối thiểu tới đúng user/group đã được backend authorize.
     * Thành công = gateway chấp nhận request theo adapter,
     * KHÔNG đồng nghĩa client đã đọc.
     */
    void publishToUser(
            String tenantId,
            String userId,
            String notificationId,
            String payloadJson);
}

public record DeliveryJob(
        String deliveryId,
        String tenantId,
        String userId,
        String notificationId,
        String payloadJson,
        int attempts) {}

public interface DeliveryOutboxRepository {
    DeliveryJob claimNextReady(String workerId);
    void markGatewayAccepted(String deliveryId);
    void scheduleRetry(String deliveryId, long nextAttemptEpochMs);
    void markNeedsReview(String deliveryId, String reason);
}
~~~

Adapter **RealtimePublisher** có thể sử dụng Azure Web PubSub server SDK/REST hoặc Azure SignalR SDK theo môi trường. Backend dùng managed identity/service credential đúng khả năng dịch vụ; **không đưa service key xuống frontend**.

### 18.2. Retry pseudocode

~~~text
loop:
    job = outbox.claimNextReady(workerId) # atomic claim/lease
    if job is null: wait with jitter

    try:
        gateway.publishToUser(job.tenantId, job.userId,
                              job.notificationId, job.payloadJson)
        outbox.markGatewayAccepted(job.deliveryId)
    catch transient error / throttling:
        outbox.scheduleRetry(job.deliveryId,
                             exponentialBackoffWithJitter())
    catch permanent invalid payload / authorization:
        outbox.markNeedsReview(job.deliveryId, reason)
~~~

Bài toán quan trọng:

- Claim jobs phải an toàn khi nhiều dispatchers hoạt động.
- Không giữ DB transaction mở trong HTTP call tới gateway.
- Có retry cap, visibility/lease timeout và idempotency.
- Nếu gateway đã nhận message nhưng response mất, retry có thể đẩy trùng.
- Mark-dispatched chỉ có nghĩa **gateway accepted**.
- Payload nên nhỏ, phần nhạy cảm được tải qua Notifications API khi user đã xác thực.
- Có thể điều tiết dispatch theo user/group để tránh floods.

## 19. Java cache-aside unread count

### 19.1. Các interface

~~~java
package example.notifications;

import java.time.Duration;
import java.util.OptionalLong;

public interface UnreadStore {
    long countUnread(String tenantId, String userId);
    boolean markReadIfUnread(
            String tenantId, String userId, String notificationId);
}

public interface NotificationCache {
    OptionalLong getCount(String key);
    void putCount(String key, long count, Duration ttl);
    void invalidate(String key);
}
~~~

**markReadIfUnread** phải kiểm tra recipient ownership ở query/database, không chỉ so notificationId rồi update vô điều kiện.

### 19.2. Cache-aside service

~~~java
package example.notifications;

import java.time.Duration;
import java.util.OptionalLong;

public final class UnreadCountService {
    private final UnreadStore store;
    private final NotificationCache cache;

    public UnreadCountService(
            UnreadStore store, NotificationCache cache) {
        this.store = store;
        this.cache = cache;
    }

    public long count(String tenantId, String userId) {
        String key = cacheKey(tenantId, userId);

        try {
            OptionalLong hit = cache.getCount(key);
            if (hit.isPresent()) return hit.getAsLong();
        } catch (RuntimeException ignored) {
            // Ghi metric/log được kiểm soát.
        }

        long value = store.countUnread(tenantId, userId);
        try {
            cache.putCount(key, value, Duration.ofSeconds(30));
        } catch (RuntimeException ignored) {
            // Có thể phục vụ từ DB khi cache down.
        }
        return value;
    }

    public boolean markRead(
            String tenantId, String userId, String notificationId) {
        boolean changed = store.markReadIfUnread(
                tenantId, userId, notificationId);

        if (changed) {
            try {
                cache.invalidate(cacheKey(tenantId, userId));
            } catch (RuntimeException ignored) {
                // TTL sẽ giới hạn stale cache; nếu cần
                // strong freshness, dùng versioned projection.
            }
        }
        return changed;
    }

    private static String cacheKey(String tenantId, String userId) {
        return "notif:unread:v1:" + tenantId + ":" + userId;
    }
}
~~~

Đoạn code là **mẫu eventual consistency**; refill/invalidation race có thể tồn tại. Sản phẩm cần unread count tuyệt đối chính xác ngay sau mark-read phải dùng DB-first/conditional versioned cache, không khẳng định TTL=30 giây đem lại strong consistency.

### 19.3. Redis implementation cần chú ý

- Pool, TLS, DNS/private networking, auth theo dịch vụ và SDK.
- Timeout ngắn và circuit breaker để cache lỗi không kéo sập API.
- Đặt TTL có jitter khi cần tránh stampede.
- Không dùng lệnh quét toàn keyspace trên production chỉ để tìm một user.
- Redis eviction/restart có thể mất keys; phải rebuild từ DB.
- Không dùng Redis INCR/DECR mù với retries.
- Cache payload theo data classification; tránh PII trong Redis key/log.

## 20. Browser JavaScript: reconnect, dedup và resync

Một client Web PubSub có thể dùng native WebSocket khi server trả URL/token thích hợp và hub đã cấu hình protocol. Ví dụ sau dùng backend APIs minh họa, chưa có phần rendering hay token refresh.

~~~javascript
class NotificationClient {
  constructor() {
    this.socket = null;
    this.stopped = false;
    this.reconnectAttempt = 0;
    this.cursor = null;
    this.items = new Map();
    this.syncing = false;
    this.syncPending = false;
  }

  async start() {
    this.stopped = false;
    await this.connect();
  }

  async connect() {
    if (this.stopped) return;
    try {
      // Backend xác thực qua session hoặc access token.
      const response = await fetch("/realtime/negotiate", {
        method: "POST",
        credentials: "include"
      });
      if (!response.ok) throw new Error("Negotiate failed");

      const { url } = await response.json();
      const socket = new WebSocket(url);
      this.socket = socket;

      socket.onopen = () => {
        this.reconnectAttempt = 0;
        this.requestSync();
      };
      socket.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "NOTIFICATION_AVAILABLE"
              || msg.type === "NOTIFICATION_READ") {
            this.requestSync();
          }
        } catch (_) {
          console.error("Invalid realtime payload");
        }
      };
      socket.onclose = () => this.scheduleReconnect();
      socket.onerror = () => {
        try { socket.close(); } catch (_) {}
      };
    } catch (_) {
      this.scheduleReconnect();
    }
  }

  requestSync() {
    this.syncPending = true;
    if (!this.syncing) this.syncFromStore();
  }

  async syncFromStore() {
    this.syncing = true;
    try {
      while (this.syncPending) {
        this.syncPending = false;
        let cursor = this.cursor;
        let hasMore = true;

        // Lab giới hạn 20 pages; production xử lý
        // continuation/state chính xác khi còn hasMore.
        for (let pageNo = 0; pageNo < 20 && hasMore; pageNo++) {
          const query = new URLSearchParams({ limit: "50" });
          if (cursor) query.set("cursor", cursor);

          const response = await fetch(
            "/notifications?" + query.toString(),
            { credentials: "include" }
          );
          if (!response.ok) throw new Error("Feed sync failed");

          const page = await response.json();
          for (const item of page.items) {
            const old = this.items.get(item.id);
            if (!old || (item.revision ?? 0) >=
                         (old.revision ?? 0)) {
              this.items.set(item.id, item);
            }
          }
          cursor = page.nextCursor;
          hasMore = page.hasMore;
        }

        // Đã merge thành công các trang vừa đọc, nên lưu mốc.
        // Khi còn hasMore, lần lặp kế tiếp phải TIẾN từ cursor mới,
        // không đọc lại 20 trang đầu vô hạn.
        this.cursor = cursor;
        if (hasMore) {
          this.syncPending = true;
          // Nhường event loop; production cần bounded paging budget.
          await new Promise(resolve => setTimeout(resolve, 50));
        }

        this.render();
      }
    } catch (error) {
      console.error("Cannot sync notifications", error);
    } finally {
      this.syncing = false;
    }
  }

  scheduleReconnect() {
    if (this.stopped) return;
    const delayBase = Math.min(
      30000, 1000 * 2 ** Math.min(this.reconnectAttempt++, 5)
    );
    const delay = delayBase * (0.5 + Math.random());
    setTimeout(() => this.connect(), delay);
  }

  render() {
    // Escape title/body, kiểm tra links. Không render raw HTML.
    console.info("Notifications", this.items.size);
  }

  stop() {
    this.stopped = true;
    if (this.socket) this.socket.close();
  }
}
~~~

**Giới hạn của ví dụ:** chưa có auth refresh, CSRF/CORS policy, retry khi GET lỗi, persistent client cursor, UI, snapshot semantics. API phải cung cấp **stable cursor**; không dùng local timestamp làm nguồn thật. Khi đã chạy đến page limit mà server còn hasMore, code trên cần một cơ chế schedule vòng tiếp để tránh blocking/vòng quay liên tục. Production phải thêm abort/shutdown logic và đóng kết nối cũ khi reconnect để tránh nhiều sockets cùng tồn tại.

Nếu backend dùng **Azure SignalR Service**, client phải dùng đúng SignalR Hub Protocol/SDK, không tự thay một SignalR connection bằng WebSocket thuần trong code trên.

## 21. Mark-read và read-all

### 21.1. Mark-read là thao tác nghiệp vụ bền vững

Request mẫu:

~~~http
PATCH /notifications/notif-481-paid/read
Authorization: Bearer <access-token>
Content-Type: application/json

{"read":true}
~~~

Server xử lý:

1. Kiểm tra access token/session.
2. Lấy tenantId và userId từ claims/context đáng tin.
3. Xác nhận notification thuộc user.
4. Chỉ chuyển **UNREAD → READ** nếu chưa được đánh dấu.
5. Lưu **readAtUtc** server-side và commit.
6. Invalidate/update cache theo policy.
7. Tùy chọn push **NOTIFICATION_READ** tới các tab khác.
8. Lần request lặp không được trừ unread count thêm lần thứ hai.

### 21.2. Read-all không nên UPDATE vô hạn một cách mù quáng

Với một user có 500.000 notifications, mark-read all có thể tốn nhiều writes/RU. Cân nhắc:

- Batch cập nhật có tiến độ/continuation và giới hạn concurrency.
- **LastReadCursor/watermark** nếu business semantics chấp nhận.
- Exceptions với những notification cần trạng thái riêng.
- Server snapshot boundary để không vô tình mark-read các notifications vừa phát sau khi user bấm.
- Audit riêng nếu mỗi notification phải có readAtUtc chính xác.

### 21.3. Read watermark có trade-off

Một record “mọi notification trước cursor X đã đọc” giảm updates nhưng không luôn thay thế per-item audit. Nếu backfill một notification cũ sau X, trạng thái đọc phải được quy định. Không dùng read watermark khi nghiệp vụ bắt buộc có chứng từ đọc từng item.

## 22. Fan-out tới user, group và broadcast

### 22.1. Personal notification

~~~text
OrderPaid → one notification record → one delivery intent
→ publish tới user group → mọi active connections phù hợp
~~~

Một user có thể nhận trên browser tab A/B và điện thoại; client dedup theo ID.

### 22.2. Team alert

Một OperationalAlert gửi tới 200 nhân viên:

- Membership lấy từ nguồn đã xác thực.
- Quyết định audience là **snapshot lúc phát** hay **membership hiện hành**.
- Lưu một announcement chung hoặc per-recipient records tùy yêu cầu offline/read audit.
- Group broadcast chỉ đẩy tới connected members; không chứng minh user đã đọc.
- Khi nhân viên rời team, thu hồi membership và access phù hợp.

### 22.3. Broadcast lớn

Nếu 100.000 users có trung bình 2 connections:

~~~text
Active connections ≈ 100.000 × 2 = 200.000

Một announcement đủ điều kiện cho toàn bộ
có thể tạo lượng fan-out tới 200.000 connections.
~~~

Đây là capacity estimate, không phải con số billable messages chính xác: tier/protocol/message size/quota có thể ảnh hưởng. Cần test group fan-out, publish rate, connection churn và DB read spike khi mọi browser đồng loạt refresh.

### 22.4. Khi nào không cần 100.000 inbox rows?

Một thông báo bảo trì chung có thể được lưu một lần với audience criteria và per-user read cursor. Ngược lại, một yêu cầu pháp lý cần chứng minh từng recipient nhận được notification có thể buộc lưu recipient records riêng.

Không tối ưu database writes bằng cách làm mất bằng chứng nghiệp vụ.

## 23. Backpressure, ưu tiên và load shedding

### 23.1. Nếu đầu vào nhanh hơn worker

Đặt:

- **λ**: số domain events/giây vào Service Bus.
- **μ**: số events/giây được xử lý hoàn tất và lưu inbox.
- **B(t)**: message backlog.

Nếu không có giới hạn khác:

~~~text
Backlog tăng ≈ (λ - μ) × t khi λ > μ

Ví dụ:
λ = 8.000 events/s
μ = 5.000 events/s
t = 120 giây

Backlog tăng ≈ 3.000 × 120 = 360.000 events

Nếu hệ thống hồi phục, μ = 10.000 events/s
trong khi λ vẫn 8.000 events/s:

Tốc độ giảm backlog ≈ 2.000 events/s
Thời gian catch-up lý tưởng ≈ 360.000 / 2.000 = 180 giây
~~~

Đây là mô hình lý tưởng chưa tính DB throttling, retries, partition skew, message sizes và giờ cao điểm.

### 23.2. Không tăng concurrency vô hạn

Nếu notification DB chỉ phục vụ 3.000 writes/s, tăng worker count từ 10 lên 100 có thể làm DB lỗi 429/timeout nhiều hơn.

Thiết kế:

- Bounded executor/thread pool.
- Giới hạn đồng thời DB writes và gateway publishes riêng.
- Exponential backoff + jitter.
- Retry cap, error classification và circuit breaker.
- Bulkheads theo tenant/priority.
- DLQ/quarantine cho poison events.
- Theo dõi **oldest pending outbox age**, không chỉ total pending count.

### 23.3. Mức ưu tiên

| Priority | Ví dụ | Đề xuất |
|---|---|---|
| Critical | Security incident, giao dịch thất bại quan trọng | Persist + push + kênh dự phòng, SLO chặt |
| High | Payment action required | Durable + push, retry |
| Normal | Đơn hàng đã giao | Durable + push có rate limit |
| Low | Gợi ý sản phẩm | Batch/coalesce/digest nếu nghiệp vụ cho phép |

Không **drop silently** thông báo bắt buộc về tài chính, an toàn, quyền người dùng hoặc compliance. Load shedding chỉ dành cho những event types có chính sách rõ.

### 23.4. Coalescing

Nếu một user nhận 100 thông báo “tài liệu đã sửa” trong 3 giây, có thể tổng hợp thành “12 tài liệu đã được cập nhật” theo cửa sổ nghiệp vụ. Redis có thể lưu counter tạm nhưng durable store phải ghi summary/record phù hợp nếu cần audit.

Không gom những notifications có quyền truy cập khác nhau vào một summary có thể làm lộ thông tin.

## 24. Retry semantics và các mức bảo đảm

| Mốc | Có thể xác nhận | Không thể tự suy ra |
|---|---|---|
| Broker accepted | Service Bus nhận message theo semantics | Worker hoàn tất |
| Inbox persisted | Notification trong DB | Browser nhận được |
| Gateway accepted publish | Realtime service chấp nhận lệnh | Client đang online thật |
| Client callback | Client code nhận payload | Người nhìn màn hình |
| Client display telemetry | UI đã render theo code client | Người đã đọc/hiểu |
| DB readAtUtc committed | User/session đã đánh dấu theo API | Người thật chắc chắn đã đọc nội dung |

### 24.1. Duplicate delivery là khả năng bình thường

Một dispatcher có thể:

~~~text
Publish → gateway chấp nhận
Network response bị mất
Dispatcher retry cùng job
→ Client nhận hai tín hiệu cùng notificationId
~~~

Client cần dedup/upsert, không tạo hai cards. Nếu product yêu cầu một toast không xuất hiện hai lần trên thiết bị, dùng local seen set với TTL hợp lý; durable read state vẫn phải nằm ở backend.

### 24.2. Push tối giản

Khi payload chứa dữ liệu nhạy cảm hoặc schema thường thay đổi, có thể chỉ push:

~~~json
{
  "type": "REFRESH_INBOX",
  "recipientVersion": "v-9381"
}
~~~

Sau đó client GET feed có authentication/authorization. Đổi lại một push có thể kích hoạt nhiều DB reads; dùng debounce, cache và jitter để giảm thundering herd.

## 25. Security, privacy và tenant isolation

### 25.1. Bảng least privilege

| Đường gọi | Danh tính và quyền |
|---|---|
| Orders API → Service Bus | Managed identity, **Azure Service Bus Data Sender** |
| Notification worker → Service Bus | **Data Receiver** trên subscription/namespace scope phù hợp |
| Worker/API → Notification DB | Cosmos native data-plane role hoặc SQL DB permissions |
| API/Worker → Redis | TLS + auth/Entra theo service/client model |
| Backend → Web PubSub/SignalR | Server credential/managed identity và role được hỗ trợ |
| Browser → realtime service | Short-lived client token/URL, scoped nhận message |
| Browser → Notifications API | Entra/OIDC session + tenant/user authorization |
| Operator → Azure Monitor | Azure RBAC phù hợp, logs đã mask dữ liệu nhạy cảm |

**Azure Contributor** của resource group không tự cấp Cosmos DB document data access, và private endpoint không thay application authorization.

### 25.2. Không tin recipientUserId do external client gửi

Nếu external webhook có thể tự đặt **recipientUserId**, attacker có thể hướng thông báo sang tài khoản khác. Worker phải kiểm tra producer và xác định recipient từ business ownership/membership đáng tin.

### 25.3. Không dùng group name làm authorization

Group **tenant-hcm:user-91** là routing hint. User không được tự chỉ định group khi negotiate. Server phải:

- Xác thực token.
- Kiểm tra tenant membership.
- Tạo user/group identity có namespace đúng.
- Cấp token scope tối thiểu.
- Thu hồi/expire token hoặc đóng connection khi quyền thay đổi theo khả năng dịch vụ.

### 25.4. Chống XSS, phishing và lộ payload

- Escape notification title/body khi render HTML.
- Chỉ cho phép relative URLs hoặc domain whitelist trong field link.
- Không gửi password reset token, session token hoặc PII nhạy cảm qua notification.
- Chú ý mobile lock-screen previews.
- Không log Web PubSub client access URL có token.
- Giới hạn CORS/origins và bảo vệ CSRF nếu dùng cookie sessions.
- Định nghĩa retention/legal deletion cho inbox, outbox và telemetry.

### 25.5. Mạng riêng

Service Bus, Redis, database, Web PubSub/SignalR và app runtime có các lựa chọn networking khác nhau theo tier và region. Kiểm tra VNet integration, private endpoints, DNS, TLS, routing, firewall và NAT. Không mặc định mọi dịch vụ hỗ trợ cùng một mức private networking; phải xác minh SKU trước khi triển khai.

## 26. Giám sát và correlation

### 26.1. Bảng metrics

| Thành phần | Chỉ số chính | Dùng để |
|---|---|---|
| Service Bus | Active/DLQ message counts, throttles, incoming/outgoing | Broker backlog và lỗi |
| Worker | Processing success, idempotent duplicates, DB commit latency | Xử lý message đúng |
| Notification DB | Write/query p95, RU/429 hoặc CPU/DTU, storage | Độ bền và tải database |
| Delivery outbox | Pending jobs, oldest age, retries, failed permanently | Độ trễ push sau persistence |
| Realtime gateway | Active connections, message count, errors, throttling | Năng lực kết nối/fan-out |
| Redis | Hit/miss, latency, memory, evictions, errors | Chất lượng cache |
| Notifications API | p95 GET feed, mark-read failure, auth failures | Trải nghiệm user |
| Client | Reconnect rate, resync latency, duplicate push rate | Chất lượng cuối đường |
| Business | Time from OrderPaid to inbox available, unknown recipients | SLO end-to-end |
| FinOps | Cost per persisted notification, gateway/DB/cache usage | Tối ưu chi phí |

Không phải mọi metric được Azure Monitor xuất sẵn dưới tên như trên. KPI nghiệp vụ và client events cần được instrument bằng Application Insights/OpenTelemetry/telemetry tùy policy.

### 26.2. Correlation

Ví dụ log:

~~~json
{
  "stage": "NOTIFICATION_PERSISTED",
  "sourceEventId": "evt-order-481-paid-1",
  "notificationId": "notif-481-paid",
  "correlationId": "corr-481",
  "tenantId": "tenant-hcm",
  "recipientUserHash": "hash-example",
  "durationMs": 42,
  "timestampUtc": "2026-11-20T03:10:03Z"
}
~~~

Không đưa raw recipient PII, access tokens hay payload nhạy cảm vào logs. Truy vết các bước:

~~~text
Domain commit → outbox publish → broker accepted
→ notification DB committed → gateway accepted
→ client callback → UI render → read-state DB commit
~~~

### 26.3. SLO minh họa

- 99% event OrderPaid tạo inbox record trong **5 giây**.
- 95% notifications của connected users có push được gateway chấp nhận trong **2 giây** sau persistence.
- 99% reconnect sessions tải đầy đủ feed còn retention trong **10 giây**.
- Không có dispatch jobs quá 15 phút mà không alert.
- DLQ được xử lý theo lịch vận hành.
- Cache failure không làm mất inbox records hoặc đọc sai tenant.

Các mốc là **business SLO ví dụ**, không phải SLA do Azure cam kết hoặc bảo đảm mọi client online thực sự nhận frame.

## 27. Capacity planning và phép tính

### 27.1. Connections

Giả sử:

~~~text
30.000 users online
Mỗi user trung bình 2 connections

Active connections ≈ 30.000 × 2 = 60.000

Mỗi user nhận 1 notification/phút:

Notifications created/s ≈ 30.000 / 60 = 500

Nếu push đến cả 2 connections:
Frame deliveries ≈ 500 × 2 = 1.000/s
~~~

Đây là trung bình. Peak, broadcast và reconnect storm làm tăng mạnh số operations. **Một publish request không nhất thiết bằng một billable message**; phải xem tier/meter và message-size rules của realtime service.

### 27.2. Fan-out broadcast

Nếu 1 OperationalAlert gửi tới 20.000 users, mỗi người trung bình 2 kết nối, số connection deliveries có thể xấp xỉ 40.000. Dùng group publish có thể giảm requests từ server tới gateway, nhưng vẫn cần băng thông/fan-out capacity tới clients.

Thêm debounce và jitter nếu tất cả clients đồng loạt GET inbox sau khi nhận broadcast.

### 27.3. Ước lượng cache

Giả sử cache unread count của 100.000 users, mỗi key/value cộng metadata giả định **150 bytes**:

~~~text
100.000 × 150 bytes = 15.000.000 bytes ≈ 15 MB
~~~

Đây **không phải khuyến nghị chọn Redis SKU 15 MB**: phải cộng Redis internal overhead, fragmentation, replicas, connection buffers, data khác, peak và headroom. Đo memory thật bằng benchmark.

### 27.4. Hot user và hot tenant

Nếu một admin account nhận 10.000 notifications/s, per-user inbox partition, cache key hoặc group có thể bị nóng. Có thể dùng digests, partitioning/synthetic key, priority classes và rate-limit theo user/tenant. Không tự tăng Redis memory để chữa một DB hot partition.

## 28. Chi phí và lựa chọn kiến trúc vừa đủ

| Thành phần | Nguồn chi phí cần cân nhắc |
|---|---|
| Service Bus | Tier, messaging operations, throughput và message size |
| Durable inbox | SQL vCore/DTU/storage hoặc Cosmos RU/storage/replication |
| Delivery outbox | Database writes, storage, cleanup và worker |
| Azure Managed Redis | Instance/tier/capacity/HA/networking theo model |
| Web PubSub/SignalR | Connection units, messages, bandwidth và tier |
| Java worker/Functions/Container Apps | CPU/RAM, executions/instances, scaling |
| Azure Monitor | Logs ingestion, retention và alerts |
| Private networking | Private endpoints, NAT/firewall, cross-region data transfer |
| Mobile push/email/SMS | Provider fees/quotas |

Không đưa đơn giá cố định vào thiết kế vì tier, region và bảng giá thay đổi. Dùng pricing calculator và Cost Management theo resources thực.

### 28.1. Tối giản khi chưa cần cache

~~~text
Orders outbox → Service Bus → Notification inbox
                              → Web PubSub hint

Browser → GET inbox / mark-read
~~~

Nếu unread count API chỉ phục vụ vài trăm users và database p95 vẫn tốt, có thể **chưa cần Redis**. Cache là tối ưu hóa theo số liệu, không phải điều kiện để realtime hoạt động.

### 28.2. Kiến trúc có cache khi tải cao

~~~text
Orders outbox → Service Bus → Inbox + delivery outbox
                                  ↓
                                Gateway dispatcher
                                  ↓
                              Web PubSub
                                  ↓
                                Browser

Browser → Notifications API → Redis cache-aside → Durable inbox
~~~

Thêm nhiều lớp tăng chi phí, failure modes và vận hành. Chỉ nâng mức phức tạp khi cải thiện SLO/chi phí tổng thể có thể đo.

### 28.3. KPI FinOps hợp lý

~~~text
Cost per available notification
  = (broker + worker + database + cache
     + gateway + network + monitoring + operations)
    / số notification records persist thành công
~~~

Không chia cho số push attempts rồi gọi đó là cost per delivered user notification; một notification có thể fan-out nhiều connections và không có read receipt.

## 29. Sự cố và degrade gracefully

| Sự cố | Hành vi mục tiêu |
|---|---|
| Service Bus không nhận message | Domain outbox giữ sự kiện; relay retry |
| DB inbox chậm/hỏng | Worker không Complete trước commit; backoff |
| Redis mất kết nối | Cache miss/fallback DB, không mất history |
| Redis count stale | TTL/versioned invalidation/reconciliation |
| Realtime gateway lỗi | Inbox vẫn lưu; delivery outbox retry; client resync |
| Client offline | Tải lại inbox khi reconnect |
| Client nhận trùng | Dedupe theo notificationId |
| Notification đến sai thứ tự | Server order/revision, client merge |
| Poison event | DLQ/quarantine với reason, tránh retry vô hạn |
| User bị thu hồi quyền | Token expiry/revocation, API authorization |
| Broadcast quá lớn | Fan-out budget, rate limit/debounce |
| Region outage | Failover/restore theo kiến trúc đã thử |

### 29.1. Ưu tiên thiết kế khi quá tải

1. Giữ đúng business state và không mất domain event đã commit.
2. Không phát notification tới người không có quyền.
3. Persist notification bền vững và idempotent.
4. Push nhanh khi có kết nối, nhưng có retry/resync.
5. Redis count/presence được phép stale theo ngân sách và SLO.

### 29.2. Redis failover

Nếu Redis restart và mất một phần keys, API nên query DB để rebuild. Giới hạn cache retries để không làm CPU/network quá tải; theo dõi cache hit rate, fallback DB load và evictions.

### 29.3. Reconnect storm

Sau 5 phút gateway outage, 100.000 clients có thể đồng loạt reconnect và GET inbox. Cần exponential backoff + jitter, bounded negotiation, pagination, API rate limits, DB capacity và user-friendly retry.

## 30. Lab Azure với tài nguyên được phê duyệt

Các bước sau **chỉ là hướng dẫn**, chưa triển khai vào Azure.

### 30.1. Chuẩn bị

- Subscription/resource group lab và budget.
- Service Bus Standard namespace (để dùng topic/subscription).
- Notification store SQL hoặc Cosmos DB for NoSQL.
- Azure Web PubSub instance/hub theo lựa chọn lab.
- Azure Managed Redis tùy chọn khi muốn kiểm tra cache-aside.
- Java worker, Notifications API và browser test.
- Microsoft Entra ID/managed identities, role assignments phù hợp.
- Monitoring/telemetry và kế hoạch dọn tài nguyên.

Không dùng production queues, secrets hoặc dữ liệu khách hàng thật.

### 30.2. Tạo Service Bus bằng Azure CLI

~~~bash
az login
az account set --subscription "<subscription-id>"
az account show --output table

RG="rg-realtime-notify-lab"
REGION="southeastasia"
NS="<globally-unique-servicebus-namespace>"

az group create \
  --name "$RG" \
  --location "$REGION"

az servicebus namespace create \
  --resource-group "$RG" \
  --name "$NS" \
  --location "$REGION" \
  --sku Standard

az servicebus topic create \
  --resource-group "$RG" \
  --namespace-name "$NS" \
  --name "commerce-events"

az servicebus topic subscription create \
  --resource-group "$RG" \
  --namespace-name "$NS" \
  --topic-name "commerce-events" \
  --name "notifications"
~~~

Kiểm tra:

~~~bash
az servicebus namespace show \
  --resource-group "$RG" \
  --name "$NS" \
  --output table

az servicebus topic subscription show \
  --resource-group "$RG" \
  --namespace-name "$NS" \
  --topic-name "commerce-events" \
  --name "notifications" \
  --output json
~~~

Lệnh có thể cần Azure CLI/extension phiên bản tương thích; không chạy lại create trên tài nguyên thuộc nhóm khác. Subscription có thể có default rule nhận nhiều loại event; tạo filters phù hợp khi muốn chỉ nhận OrderPaid.

### 30.3. Tạo Web PubSub và app

Trong Azure Portal:

1. Tạo **Azure Web PubSub** theo region/tier lab.
2. Cấu hình hub và service-side publishing identity/secret management.
3. Định nghĩa trusted **POST /realtime/negotiate**.
4. Backend xác thực user, sinh token/client access URL TTL ngắn và scope đúng.
5. Browser kết nối WebSocket, nhận hint.
6. Backend publish thử tới một user/group đã xác thực.
7. Bật metrics cần thiết, không log connection token.

Nếu project dùng ASP.NET Core SignalR, triển khai Azure SignalR Service với đúng SignalR SDK; code WebSocket thuần của bài không phải client SignalR Hub.

### 30.4. Lưu inbox và cache

- Tạo Notifications + DeliveryOutbox với unique notification identity.
- Dùng index theo tenant/user/time, read-state bền vững.
- Nếu Cosmos DB, thiết kế partition key phục vụ per-user feed và transaction boundary.
- Chỉ thêm Redis sau khi đo nhu cầu; cache unread count TTL phù hợp và fallback.
- Test invalidation sau DB commit, duplicate delivery, Redis down, read API cross-tenant.

### 30.5. Test end-to-end

1. Phát một OrderPaid event.
2. Xác minh broker nhận message.
3. Xác minh worker ghi một notification và dispatch intent.
4. Xác minh message Complete sau commit.
5. Xác minh dispatcher gửi gateway.
6. Browser online nhận push hint rồi GET inbox.
7. Tắt mạng, phát thêm event.
8. Bật lại, reconnect và resync đủ history.
9. Mark-read ở tab A, tab B thấy state đồng bộ.
10. Đọc logs/metrics/DLQ và dọn tài nguyên thuộc riêng lab.

## 31. Runbook chẩn đoán

| Triệu chứng | Khả năng | Hành động |
|---|---|---|
| Order PAID nhưng không có notification | Domain outbox relay, broker, worker hoặc DB commit lỗi | Trace eventId qua từng lớp |
| Notification có trong DB nhưng không tới UI | Delivery outbox/gateway/client reconnect | Kiểm tra publish/connection/sync |
| Browser có hai notifications giống nhau | Retry push, dedup thiếu | Stable notificationId + merge |
| Cache count lớn hơn DB | Duplicate INCR, stale refill | Recompute/invalidate/version |
| Tab A đọc nhưng tab B vẫn unread | Read hint bị mất/tab offline | Resync read state |
| Service Bus DLQ tăng | Payload schema sai, max delivery reached | Inspect reason, controlled replay |
| Queue backlog tăng | Worker/DB chậm | Measure λ/μ, throttle, scale có giới hạn |
| Gateway 401/403 | Token expired, scope/role/identity sai | Negotiate auth, server credentials |
| Gateway throttled | Connection/message budget | Fan-out rate, payload size, tier |
| Redis evictions | Memory pressure | Cache size/TTL/policy |
| Browser reconnect liên tục | Network/token expiry/bug | Backoff/jitter, token refresh |
| User A thấy notification User B | Tenant/group auth bug | Security incident: revoke/contain/audit |
| Chi phí tăng | Gateway connections, DB reads, Redis provisioned, logs | FinOps metrics và cost per notification |

### 31.1. Trace từ OrderPaid tới browser

1. Tìm **sourceEventId** và **correlationId**.
2. Đối chiếu Orders DB và outbox.
3. Đối chiếu Service Bus publish/accept.
4. Kiểm tra subscription Active/DLQ.
5. Kiểm tra worker validation và DB commit.
6. Xem notificationId duy nhất trong inbox.
7. Xem delivery-outbox state/retry.
8. Xem gateway publish accepted/errors.
9. Xem user/group mapping và auth.
10. Xem browser connection/cursor/sync.
11. So sánh DB readAtUtc và Redis badge.
12. Viết regression test từ root cause.

### 31.2. Khi unread count lệch

Query durable store theo đúng user, kiểm tra cache key/TTL/version, duplicate event, mark-read conditional update và refill-invalidate race. Không chỉ xóa Redis rồi tuyên bố đã sửa: cần đo lại và tìm nguồn sai lệch.

### 31.3. Security incident: cross-tenant leak

Dừng đường publish/group bị ảnh hưởng, thu hồi token/session khi có thể, kiểm tra tenant membership và server-side authorization, giữ logs theo policy, hạn chế PII trong ticket và thêm negative tests kiểm tra user không thể negotiate/GET của tenant khác.

## 32. Diễn tập kiểm thử trước production

| Kịch bản | Kết quả mong đợi |
|---|---|
| Worker crash trước DB commit | Message được xử lý lại |
| Worker crash sau DB commit trước Complete | Không insert notification trùng |
| Dispatcher crash sau gateway accepted | Client dedup nếu phát lại |
| Redis outage | Durable inbox và mark-read vẫn đúng |
| Gateway outage | Notifications vẫn persist; browser resync |
| Browser offline 30 phút | Tải đủ history còn retention |
| 3 tabs cùng user | Không có cross-user leak, read-state đồng bộ |
| Token hết hạn | Re-negotiate an toàn, scope vẫn đúng |
| Một event fan-out 20.000 recipients | Bounded concurrency, có backlog metrics |
| Message sai schema | DLQ/quarantine, không hot retry loop |
| Cache refill/invalidate race | Staleness có giới hạn, phù hợp SLO |
| Client nhận B trước A | Stable ordering/revision merge |
| User A gọi PATCH id của user B | Bị từ chối, không lộ dữ liệu |
| Reconnect storm | Backoff/jitter và API/database ổn định |

Dùng **staging resources**, không cố ý cắt kết nối production để thử. Đối soát số **unique notificationId** với sự kiện hợp lệ và recipient mapping.

## 33. Chọn độ phức tạp vừa đủ

### Mức 1: polling

~~~text
Orders DB → Notifications store
Browser → GET notifications định kỳ
~~~

Phù hợp user nhỏ, yêu cầu cập nhật mỗi 30–60 giây, không có use case realtime mạnh. Có thể chưa cần Redis hoặc managed realtime gateway.

### Mức 2: reliable broker + realtime

~~~text
Orders outbox → Service Bus → Notification store + delivery intent
                                         ↓
                                    Web PubSub
Browser → realtime hint + GET on reconnect
~~~

Phù hợp nhiều dịch vụ phát sự kiện và cần offline history.

### Mức 3: cache + resilient dispatch

~~~text
Orders outbox → Service Bus → Notification store + dispatch outbox
                                            ↓
                                       bounded dispatcher
                                            ↓
                                      realtime gateway

Browser → Notifications API → Redis cache-aside / durable DB
~~~

Phù hợp traffic lớn, unread count/presence nóng, multi-tenant, SLO/DR/observability cao. Không phải mọi ứng dụng đều cần mức 3.

## 34. Checklist production

- [ ] Domain event, broker message, notification, gateway push và read-state được phân biệt.
- [ ] Chọn Service Bus/Event Grid/Storage Queue/Event Hubs theo semantics thật.
- [ ] Không dùng Redis Pub/Sub làm nguồn bền vững duy nhất của notification.
- [ ] Durable inbox có notificationId ổn định, recipient/tenant ownership.
- [ ] Transactional outbox domain state và event intent được ghi cùng DB transaction khi cần.
- [ ] Notification và delivery-outbox có atomic commit hoặc reconciliation rõ.
- [ ] Service Bus Complete chỉ sau durable processing.
- [ ] Retry/backoff, MaxDeliveryCount, DLQ và poison handling đã có.
- [ ] Client dedup/reconnect/resync từ durable inbox.
- [ ] Cursor do server quản lý, có tie-breaker và authorization.
- [ ] Read-state có conditional/idempotent update, không trừ unread count hai lần.
- [ ] Cache unread count có TTL, invalidation/version và fallback DB.
- [ ] Đã thử cache refill/invalidation race.
- [ ] Presence TTL được xem là ước lượng.
- [ ] Nhiều tabs/devices nhận push nhưng không tự làm lộ dữ liệu.
- [ ] Realtime negotiate dùng identity thật, token TTL ngắn và least-scope roles.
- [ ] Group membership do backend quản lý, tách tenants.
- [ ] Không lộ server access keys, client tokens hoặc PII trong logs.
- [ ] Có validation notification links, escaping và bảo vệ XSS.
- [ ] Worker/dispatcher có bounded concurrency và fan-out budget.
- [ ] Có alert backlog, DLQ, dispatch-outbox age, cache evictions và gateway errors.
- [ ] Có SLO end-to-end và telemetry đủ chứng minh mốc thực sự đo được.
- [ ] Có test gateway outage, Redis outage, retry duplicate và reconnect storm.
- [ ] Có retention/backup/restore, privacy lifecycle và permission review.
- [ ] Có ước lượng phí broker, database, cache, gateway, compute và monitoring.
- [ ] Không thêm Redis nếu SLO vẫn đạt mà không có nó.

## 35. Bài tập thực hành

### Bài 1: Chọn thành phần

Chọn giải pháp cho:

1. Offline 1 giờ vẫn phải xem notification.
2. 100.000 WebSocket clients nhận announcement.
3. Unread count bị đọc 1.000 lần/giây.
4. Worker crash sau khi nhận OrderPaid.
5. Telemetry 1 triệu events/phút.
6. Website nhỏ chỉ cần cập nhật 60 giây/lần.

Giải thích vai trò Service Bus, Web PubSub, Redis, database, Event Hubs và polling; không chỉ liệt kê tên dịch vụ.

### Bài 2: Transactional outbox

Thiết kế hai outbox: **business event outbox** trong Orders DB và **delivery outbox** trong Notifications DB. Vẽ các điểm crash trước/sau publish, trước/sau Complete và sau gateway accepted. Chỉ ra idempotency key.

### Bài 3: Unread count

User có 10 notifications unread. Worker xử lý lại cùng OrderPaid hai lần, user mark-read một notification hai lần, Redis key bị eviction và một request GET race với invalidation. Thiết kế cách giữ count đúng hoặc stale trong giới hạn được công bố.

### Bài 4: Multi-tab và reconnect

Hai tabs offline 10 phút, 15 notifications được tạo. Khi reconnect, một push cũ tới trùng và user mark-read trên tab thứ hai. Thiết kế cursor, dedup, revision và resync để cả hai tabs nhất quán.

### Bài 5: Security

Hai tenants đều có local userId=91. Thiết kế group name, negotiate token, server-side tenant membership, token TTL và negative tests chứng minh User A không thể nhận/read notifications của User B.

### Bài 6: Fan-out

50.000 users, trung bình 1,5 connections/user. Tính connection deliveries lý tưởng cho một broadcast, thiết kế throttling và chọn announcement chung so với per-recipient notification records.

### Bài 7: Gateway outage

Gateway mất 5 phút. Điều gì vẫn được persist? Delivery outbox hoạt động thế nào? Sau hồi phục, rate budget và client resync phải được triển khai ra sao?

### Bài 8: Java worker

Hoàn thiện OrderPaidHandler bằng JDBC/Cosmos adapter: unique notificationId, transaction notification + outbox, manual Service Bus Complete và xử lý redelivery.

### Bài 9: FinOps

Một hệ thống có 2 triệu notifications/ngày, mỗi user trung bình hai connections, cache hit unread count là 90%. Lập bảng chi phí broker, DB, Redis, gateway, compute, networking và logs. Đề xuất giảm chi phí nhưng vẫn giữ offline notifications.

### Bài 10: Architecture review

Một nhóm muốn “chỉ dùng Redis Pub/Sub + WebSocket, không database/broker” cho nhắc thanh toán có audit 90 ngày. Phân tích điều gì xảy ra khi user offline, Redis restart, worker crash, push duplicate, hoặc cần chứng minh read-state. Đề xuất kiến trúc tối thiểu đáp ứng yêu cầu.

## 36. Câu hỏi tự kiểm tra

1. Domain event và notification khác nhau như thế nào?
2. Vì sao WebSocket push không phải bằng chứng user đã đọc?
3. Service Bus có thể thay lịch sử notification của database không?
4. Redis Pub/Sub có tự replay message khi subscriber kết nối lại không?
5. Redis Streams và Pub/Sub khác gì về persistence/consumption model?
6. Tại sao phải có durable inbox khi user có thể offline?
7. Redis nên cache những dữ liệu gì trong kiến trúc này?
8. Redis failover có được làm mất read-state nghiệp vụ không?
9. Presence TTL có chứng minh user chắc chắn online không?
10. Vì sao một user có nhiều connection IDs?
11. Azure SignalR và raw WebSocket có cùng protocol không?
12. Khi nào polling phù hợp hơn WebSocket?
13. Mobile app background nên dùng gì ngoài in-app WebSocket?
14. Transactional outbox đóng khoảng crash nào?
15. Vì sao outbox vẫn có thể gửi trùng một event?
16. Unique notificationId giúp chống trùng ở đâu?
17. Vì sao không Complete message trước DB commit?
18. Delivery outbox bảo vệ lỗi nào?
19. GatewayAccepted khác ClientReceived và Read thế nào?
20. Vì sao không Redis INCR mỗi lần worker nhận message?
21. Refill/invalidate race tạo stale count thế nào?
22. Khi nào TTL không đủ cho unread-count correctness?
23. Browser reconnect cần làm gì với durable feed?
24. Cursor theo server order khác client clock thế nào?
25. Vì sao push có thể đến sai thứ tự?
26. Tại sao group name không phải authorization?
27. Browser được cấp quyền realtime nào?
28. Có thể tin recipientUserId do browser tự khai không?
29. Một publish tới 10.000 connections có tương đương một user đã đọc không?
30. HTTP 429 ở gateway/database cần xử lý ra sao?
31. Có nên bật Service Bus Sessions cho mọi user không?
32. DLQ khác durable inbox thế nào?
33. Khi gateway outage, broker/DB còn vận hành không?
34. SLO nào đo được và chỉ số nào phụ thuộc client telemetry?
35. Khi nào không triển khai Redis lại tốt hơn?
36. Nên ưu tiên durability hay push latency khi có sự cố?

## 37. Tài liệu tham khảo

- [Azure Service Bus messaging overview — Microsoft Learn](https://learn.microsoft.com/azure/service-bus-messaging/service-bus-messaging-overview)
- [Message settlement and locks in Service Bus](https://learn.microsoft.com/azure/service-bus-messaging/message-transfers-locks-settlement)
- [Service Bus dead-letter queues](https://learn.microsoft.com/azure/service-bus-messaging/service-bus-dead-letter-queues)
- [Service Bus duplicate detection](https://learn.microsoft.com/azure/service-bus-messaging/duplicate-detection)
- [Azure Web PubSub overview](https://learn.microsoft.com/azure/azure-web-pubsub/overview)
- [Azure Web PubSub key concepts](https://learn.microsoft.com/azure/azure-web-pubsub/key-concepts)
- [Web PubSub client access URLs](https://learn.microsoft.com/azure/azure-web-pubsub/howto-generate-client-access-url)
- [Java server SDK for Azure Web PubSub](https://learn.microsoft.com/java/api/overview/azure/messaging-webpubsub-readme)
- [Azure SignalR Service overview](https://learn.microsoft.com/azure/azure-signalr/signalr-overview)
- [Azure Managed Redis overview](https://learn.microsoft.com/azure/redis/overview)
- [Azure Cache for Redis documentation and migration guidance](https://learn.microsoft.com/azure/azure-cache-for-redis/)
- [Cache-aside design pattern](https://learn.microsoft.com/azure/architecture/patterns/cache-aside)
- [Azure Cosmos DB for NoSQL overview](https://learn.microsoft.com/azure/cosmos-db/nosql/overview)
- [Service Bus trigger for Azure Functions](https://learn.microsoft.com/azure/azure-functions/functions-bindings-service-bus-trigger)
- [Managed identities for Azure resources](https://learn.microsoft.com/entra/identity/managed-identities-azure-resources/overview)
- [Azure Service Bus pricing](https://azure.microsoft.com/pricing/details/service-bus/)
- [Azure Web PubSub pricing](https://azure.microsoft.com/pricing/details/web-pubsub/)
- [Azure SignalR Service pricing](https://azure.microsoft.com/pricing/details/signalr-service/)
- [Azure Managed Redis pricing](https://azure.microsoft.com/pricing/details/redis/)





