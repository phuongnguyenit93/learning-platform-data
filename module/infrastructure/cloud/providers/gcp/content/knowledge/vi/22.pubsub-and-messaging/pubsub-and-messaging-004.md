# At-least-once, exactly-once và phạm vi bảo đảm xử lý trong Pub/Sub

Một hệ thống đặt hàng chạy trên Cloud Run phát sự kiện `OrderPaid` vào Google Cloud Pub/Sub. Một worker Java trên GKE nhận sự kiện để cập nhật bảng giao hàng. Worker ghi dữ liệu thành công, nhưng **mất kết nối trước khi Pub/Sub xác nhận ACK**; sự kiện có thể được giao lại. Nếu code chạy lại câu lệnh “tạo phiếu giao hàng” mà không kiểm tra, một đơn hàng có thể tạo hai phiếu.

Vấn đề nằm ở ranh giới giữa **giao thông điệp (delivery)** và **thực thi tác dụng nghiệp vụ (processing/side effect)**. Pub/Sub hỗ trợ mặc định **at-least-once delivery**; tính năng **exactly-once delivery** mạnh hơn trong những điều kiện cụ thể, nhưng **không phải exactly-once transaction xuyên Pub/Sub, Cloud SQL, Cloud Storage hay API thanh toán**.

Bài thuộc chương **Pub/Sub và thông điệp** của mô-đun `CLOUD_PROVIDERS_GCP`. Từ việc quản lý project, IAM, VPC, Compute Engine, GKE, Cloud Run, lưu trữ và database, người học sẽ biết thiết kế consumer an toàn, tự động hóa triển khai và theo dõi độ tin cậy cùng chi phí. Các lệnh thực hành dùng project lab được phê duyệt; không thực thi trực tiếp trên production.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **at-most-once**, **at-least-once**, **exactly-once delivery** và **exactly-once business effect**.
2. Giải thích `publish`, `pull`, `ackId`, `messageId`, `ack deadline` và vòng đời redelivery.
3. Xác định chính xác **tính năng exactly-once delivery của Pub/Sub hỗ trợ pull/StreamingPull trong một region**, không hỗ trợ push/export subscriptions.
4. Phân biệt redelivery hợp lệ, duplicate delivery và publisher-side duplicate.
5. Dùng confirmed ACK, lease extension, flow control và locational endpoint khi cần.
6. Thiết kế consumer **idempotent**, bảng dedupe và transaction để không tạo side effect lặp.
7. Chọn retry, dead-letter topic, retention, ordering và replay mà không hiểu nhầm phạm vi bảo đảm.
8. Thực hành với `gcloud` và Java subscriber có ACK response; theo dõi lỗi/chi phí.

## 1. Topic, subscription và phạm vi của một thông điệp

~~~mermaid
flowchart LR
    API["Orders API<br/>Cloud Run"] -->|"publish OrderPaid"| T["Pub/Sub topic<br/>orders-events"]
    T --> S1["Pull subscription<br/>shipping-worker"]
    T --> S2["Push subscription<br/>audit-webhook"]
    S1 --> W["Java workers<br/>GKE / Compute Engine"]
    S2 --> H["Cloud Run HTTP endpoint"]
    W --> DB[("Cloud SQL<br/>shipping_tasks")]
    H --> STORE["Audit destination"]
~~~

- **Topic** nhận messages từ publisher.
- **Subscription** có delivery state riêng. Hai subscriptions trên cùng topic nhận và xác nhận thông điệp **độc lập**; ACK ở `shipping-worker` không xác nhận thay cho `audit-webhook`.
- **Message ID** (`messageId`) do Pub/Sub cấp cho một message đã publish; ổn định qua những lần **redelivery** của chính message đó.
- **ACK ID** (`ackId`) gắn với **một lần giao** cho pull subscriber; khi có lần giao mới, ACK ID cũ có thể không còn hợp lệ.
- **Business event ID** (`eventId`) do **ứng dụng** cấp, nên ổn định qua publisher retries và cùng một nghiệp vụ, ví dụ `order-paid:A100:v3`.

Ví dụ message:

~~~json
{
  "eventId": "order-paid:A100:v3",
  "orderId": "A100",
  "type": "OrderPaid",
  "revision": 3,
  "occurredAt": "2026-11-19T04:00:00Z"
}
~~~

JSON này là **payload ứng dụng**, không phải toàn bộ Pub/Sub API response. `eventId` giúp phát hiện hai lần **publish riêng biệt** của cùng sự kiện nghiệp vụ; chỉ dùng Pub/Sub `messageId` không bắt được mọi publisher retry.

## 2. Bốn mức bảo đảm thường bị nhầm lẫn

| Khái niệm | Ý nghĩa | Điều không được suy ra |
| --- | --- | --- |
| **At-most-once** | Có thể mất, không chủ động giao lại; phù hợp vài tác vụ có thể bỏ qua | Không phù hợp sự kiện thanh toán cần bền vững |
| **At-least-once delivery** | Pub/Sub cố gắng giao message ít nhất một lần tới subscriber trong giới hạn retention, với khả năng giao lại | “Ứng dụng chỉ xử lý một lần” |
| **Exactly-once delivery (Pub/Sub)** | Với **pull subscription** bật tính năng và subscribers trong **cùng region**, message theo một `messageId` không bị giao trùng trước hạn ACK hoặc sau **ACK thành công được xác nhận** | Không có redelivery sau NACK/hết deadline, hoặc không có publisher duplicate |
| **Exactly-once business effect** | Một event nghiệp vụ chỉ gây một thay đổi hiệu lực, ví dụ chỉ tạo **một** shipping task | Pub/Sub tự bảo đảm atomic commit Cloud SQL + ACK |

**Thuật ngữ then chốt:** Pub/Sub exactly-once là **bảo đảm delivery/ack cho một Pub/Sub message trên một subscription trong phạm vi đã nêu**. Một workflow nhiều hệ thống chỉ đạt hiệu ứng nghiệp vụ một lần khi ứng dụng có idempotency/transaction phù hợp.

### 2.1. “Exactly-once” vẫn có redelivery hợp lệ

Tính năng exactly-once không hứa “callback chỉ chạy một lần dưới mọi sự cố”. Khi client **NACK** hoặc **ack deadline hết hạn** vì không gia hạn, Pub/Sub có thể giao lại **cùng message ID**. Nó hứa không có **unexpected duplicate delivery** khi message còn outstanding hợp lệ hoặc **sau khi ACK đã được service xác nhận**. Vì vậy phải phân biệt:

- **Redelivery hợp lệ:** client NACK hoặc không ACK/gia hạn đúng hạn.
- **Duplicate delivery ngoài ý muốn:** message bị giao lại **khi deadline chưa hết** hoặc **sau ACK thành công**. Exactly-once chặn loại này trong phạm vi hỗ trợ.
- **Publisher-side duplicates:** publisher gửi cùng business event hai lần, tạo **hai Pub/Sub messages khác nhau** (thường có message IDs khác). Exactly-once subscription vẫn có thể nhận cả hai.

## 3. Vòng đời ACK và những điểm có thể phát lại

~~~mermaid
sequenceDiagram
    participant P as Publisher
    participant S as Pub/Sub
    participant C as Subscriber
    participant D as Cloud SQL
    P->>S: Publish event E
    S-->>P: messageId M1
    S->>C: Deliver M1, ackId A1
    C->>D: Commit shipping task E
    D-->>C: COMMIT thành công
    Note over C,S: Network lỗi trước ACK được xác nhận
    S-->>C: Ack deadline hết
    S->>C: Redeliver M1, ackId A2
    C->>D: Thấy E đã xử lý → không ghi trùng
    C->>S: ACK A2
    S-->>C: ACK confirmed
~~~

Có ba mốc riêng biệt:

1. **Publish success:** Pub/Sub đã nhận message và trả `messageId`; không chứng minh bất cứ consumer nào đã hoàn tất.
2. **Business commit:** DB/payment/object đã được cập nhật; chưa bảo đảm Pub/Sub đã ACK.
3. **ACK confirmed:** subscription đã nhận ACK và ghi nhận thành công; với exactly-once pull, Pub/Sub không giao lại message ID đó nữa **trong phạm vi bảo đảm**.

### 3.1. ACK trước khi commit gây mất dữ liệu

~~~text
Sai:
  receive M1
  ACK M1
  cập nhật database  → app crash

Hệ quả: Pub/Sub có thể coi message xong dù nghiệp vụ chưa hoàn tất.
~~~

Mẫu chuẩn là **kiểm tra → transaction/side effect bền vững → ACK**. Nếu ACK sau commit thất bại, subscriber phải chấp nhận redelivery và phát hiện công việc đã thực hiện.

### 3.2. Cửa sổ crash sau commit

~~~text
receive → DB COMMIT → process crash → chưa ACK

Lần giao tiếp theo:
  nếu đã có durable dedupe marker → ACK, không ghi trùng;
  nếu không có marker → có nguy cơ tạo tác dụng lần hai.
~~~

Không sửa rủi ro này bằng cách tăng ack deadline vô hạn. Hãy xử lý **tính idempotent của nghiệp vụ**, kết hợp lease management để giảm redelivery không cần thiết.

## 4. At-least-once: mặc định của Pub/Sub

Pub/Sub mặc định cung cấp **at-least-once delivery** cho các subscription types, không bật ordering theo mặc định. Trong hoàn cảnh bình thường một message thường được giao một lần, nhưng người dùng **phải thiết kế chịu được redelivery**.

Những nguyên nhân thường gặp:

- Subscriber crash hoặc restart trước ACK.
- Xử lý vượt `ackDeadline` mà client không extend lease.
- Client gọi `NACK` vì dependency lỗi.
- ACK request/response bị lỗi mạng; subscriber không biết server đã chấp nhận ACK hay chưa.
- Lỗi dịch vụ tạm thời khiến xảy ra duplicate delivery hiếm gặp.
- Publisher retry không an toàn tạo **message mới** cho cùng business event.

**At-least-once không phải “thông điệp được giữ vĩnh viễn”.** Khi message retention hết hạn, dữ liệu có thể không còn được Pub/Sub giao; việc xóa topic/subscription hay retention/replay policy cũng ảnh hưởng. Thiết kế replay/backup/alert theo yêu cầu RPO.

## 5. Exactly-once delivery của Pub/Sub bảo đảm gì?

Bật tính năng `enableExactlyOnceDelivery` cho **pull subscription**:

- Subscriber có thể kiểm tra **kết quả ACK thực sự từ service** bằng supported client library.
- Pub/Sub không redeliver một message **sau ACK thành công**.
- Khi một delivery vẫn **outstanding** và deadline chưa hết, message không bị gửi trùng.
- Khi có nhiều deliveries hợp lệ của cùng message, chỉ **ACK ID của lần giao mới nhất** có thể dùng; ACK ID cũ bị từ chối.
- Bảo đảm áp dụng theo **Pub/Sub message ID**, trên **một subscription**, trong **một cloud region**.

**Không hỗ trợ:** push subscriptions, BigQuery/Cloud Storage/Bigtable export subscriptions và các mô hình nhận event qua webhook như Pub/Sub push → Cloud Run. Nếu muốn Pub/Sub exactly-once với Java, dùng **Pull hoặc StreamingPull**, client library được hỗ trợ, xác nhận ACK result và kiểm soát region kết nối.

| Tình huống | Exactly-once pull có thể ngăn? | Vì sao |
| --- | --- | --- |
| ACK thành công được xác nhận nhưng Pub/Sub gửi lại M1 | **Có**, trong phạm vi region | Đó là duplicate delivery |
| Client NACK M1, Pub/Sub giao lại M1 | **Không** | Đây là redelivery hợp lệ |
| Deadline M1 hết, giao lại cùng messageId với ackId mới | **Không** | ACK trước không hoàn tất |
| Publisher publish cùng event hai lần thành M1 và M2 | **Không** | Hai Pub/Sub messages khác nhau |
| Cloud SQL commit xong nhưng ACK M1 thất bại | **Không** | DB commit nằm ngoài giao dịch ACK |
| Hai subscriptions khác nhau cùng nhận M1 | **Không phải lỗi** | Mỗi subscription có delivery state riêng |
| Seek/replay chủ động đưa message cũ trở lại | **Không phải lỗi delivery thông thường** | Hành vi replay do người quản trị yêu cầu |

### 5.1. Chi phí của phối hợp exactly-once

Exactly-once đòi hỏi Pub/Sub phối hợp/trạng thái bổ sung nên có thể làm **publish-to-subscribe latency cao hơn** so với standard subscription. Nếu throughput lớn, Google Cloud khuyến nghị **StreamingPull**. Phải benchmark latency, throughput, quotas và phí theo bảng giá hiện hành; không bật chỉ vì tên tính năng nghe “an toàn hơn”.

## 6. Phạm vi region: điều kiện hay bị bỏ sót

Pub/Sub nêu rõ bảo đảm exactly-once chỉ áp dụng khi **các subscribers kết nối với service trong cùng region**. Nếu workers phân tán ở nhiều regions và tự dùng endpoints gần nhất, vẫn có nguy cơ duplicate delivery dù subscription bật exactly-once.

~~~mermaid
flowchart LR
    T["Pub/Sub subscription<br/>exactly-once enabled"] --> A["Worker A<br/>asia-southeast1"]
    T --> B["Worker B<br/>asia-southeast1"]
    A --> EP["Locational endpoint<br/>asia-southeast1"]
    B --> EP
    T -. "Multi-region consumers dùng nhiều endpoints<br/>không có bảo đảm giống vậy" .-> C["Worker C<br/>region khác"]
~~~

**Đề xuất:** khi muốn exactly-once, cố định tất cả subscriber clients vào **cùng một locational endpoint** được hỗ trợ, ví dụ `asia-southeast1-pubsub.googleapis.com:443`. Publishers có thể gửi từ region khác; điều kiện kết nối cùng region chủ yếu áp dụng cho **subscribers**. Đừng đánh đồng locational endpoint với bảo đảm data residency: Pub/Sub còn có **regional endpoints** và Message Storage Policy với tính chất riêng.

Với ứng dụng GKE/Compute Engine chạy trong một region, default endpoint thường định tuyến về region gần nhất tương ứng; tuy nhiên khi chuyển sang multi-region DR, phải **kiểm tra cách client thực sự kết nối**. Nếu cần active-active nhiều regions cùng consume, đánh giá lại mức delivery guarantee và idempotency trước khi quảng bá là exactly-once.

## 7. Ack deadline, lease extension và ACK IDs

Khi subscriber pull message, Pub/Sub đặt một **acknowledgment deadline**: khoảng thời gian chờ ACK trước khi message đủ điều kiện giao lại. Subscriber có thể gia hạn bằng `ModifyAckDeadline`; high-level client libraries có **lease management**.

| Tình huống | Hệ quả |
| --- | --- |
| Xử lý xong và ACK trong deadline | Message được xác nhận nếu service nhận ACK |
| Processing chậm, lease được gia hạn kịp thời | Giảm redelivery do hết hạn |
| Processing chậm, lease hết trước ACK | Có delivery mới và ACK ID mới |
| ACK với ID cũ khi exactly-once bật | Có thể nhận `INVALID_ARGUMENT`; không giả định đã ACK |
| NACK | Message có thể được giao lại tùy retry policy |
| Worker crash | Lease cuối cùng hết, message trở lại backlog |

Với exactly-once, API ACK/ModifyAckDeadline **trả lỗi rõ khi ACK ID đã hết hạn**; khác với một số hành vi best-effort khi exactly-once tắt. Trong Java client, cần xem các thiết lập `minDurationPerAckExtension`, `maxDurationPerAckExtension` (giới hạn tối đa mỗi lần gia hạn **600 giây** theo tài liệu). Đây không phải lời hứa một message được xử lý vô hạn phút.

### 7.1. Lease management không thay flow control

Nếu worker kéo 1.000 messages nhưng chỉ xử lý được 50 đồng thời, phần còn lại có thể hết deadline dù không lỗi network. Dùng **max outstanding messages/bytes**, bounded worker pool và autoscaling để giữ workload trong năng lực xử lý.

**Giảm số ACK expirations trước khi tăng instances mù quáng.** Đo CPU, DB connection pool, thời gian xử lý và subscription backlog; nếu downstream đã nghẽn, thêm workers có thể làm lỗi/trùng lặp tăng.

## 8. Publisher cũng phải idempotent

Giả sử publisher gửi `OrderPaid` tới Pub/Sub. Server đã ghi nhận thành công, nhưng HTTP/gRPC response bị mất. Publisher gửi lại **một publish request mới**, Pub/Sub có thể cấp **message ID khác**. Exactly-once subscription **không gộp hai messages này**.

~~~text
Business event: order-paid:A100:v3

Publish lần 1 → Pub/Sub messageId 701
Publish retry  → Pub/Sub messageId 702

Consumer có thể nhận cả 701 và 702 hợp lệ.
~~~

Hướng xử lý:

1. Sinh **eventId ổn định** khi sự kiện nghiệp vụ được tạo, không sinh lại mỗi publish retry.
2. Đưa `eventId` vào payload/attributes.
3. Subscriber dùng **eventId** (hoặc business transaction key) để dedupe.
4. Publisher theo dõi publish success/failure và lưu retry state khi cần.
5. Nếu thay đổi database và publish phải đi cùng nhau, áp dụng **transactional outbox**.

**Pub/Sub message ID dùng để phân biệt redelivery của cùng Pub/Sub message; business event ID dùng để phân biệt phát lại của cùng sự kiện ứng dụng.**

## 9. Consumer idempotent với Cloud SQL: transactional inbox

Thiết kế điển hình: worker cập nhật `shipping_tasks`, đồng thời chèn `eventId` vào bảng `processed_events` **trong cùng một transaction Cloud SQL**.

~~~sql
-- Ví dụ PostgreSQL; tạo bảng trong schema của môi trường lab.
CREATE TABLE processed_events (
    consumer_name TEXT NOT NULL,
    event_id TEXT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);

CREATE TABLE shipping_tasks (
    event_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    status TEXT NOT NULL
);
~~~

Pseudocode cho transaction của consumer:

~~~text
BEGIN TRANSACTION;

INSERT INTO processed_events(consumer_name, event_id)
VALUES ('shipping-worker', :eventId)
ON CONFLICT DO NOTHING
RETURNING event_id;

IF không chèn được row:
    -- Đã xử lý, không lặp side effect.
    COMMIT;
    ACK Pub/Sub message;
    RETURN;

-- Business validation: order tồn tại, event hợp lệ,
-- không vi phạm chuyển trạng thái/phiên bản.
INSERT INTO shipping_tasks(event_id, order_id, status)
VALUES (:eventId, :orderId, 'READY');

COMMIT;  -- Marker và business effect cùng bền vững.
ACK Pub/Sub message;  -- Chỉ ACK sau COMMIT.
~~~

**Đây là pseudocode transaction, không phải câu lệnh PL/pgSQL có thể paste chạy nguyên khối.** Trong Java, dùng JDBC transaction `setAutoCommit(false)` hoặc Spring `@Transactional` để **bắt buộc marker và business update cùng commit**. Nếu business validation/insert lỗi, **ROLLBACK toàn bộ**, không giữ marker “đã xử lý” sai.

### 9.1. Vì sao transaction giải quyết crash window?

- **Crash trước COMMIT:** marker và shipping task chưa được commit → redelivery xử lý lại.
- **Crash sau COMMIT nhưng trước ACK:** marker đã tồn tại → redelivery không tạo shipping task thứ hai, sau đó ACK.
- **Hai workers nhận cùng business event:** unique constraint trên `(consumer_name,event_id)` điều phối tranh chấp; một transaction thắng, transaction kia bỏ qua hoặc chờ rồi xác định duplicate.

Bảo đảm chỉ đúng khi **cả marker lẫn side effect** nằm trong **cùng database transaction**. Nếu side effect là email, thanh toán hoặc HTTP call tới bên thứ ba thì transaction Cloud SQL **không thể atomic** với API bên ngoài; cần **idempotency key tại đích**, outbox/inbox và cơ chế reconcile.

### 9.2. Đừng dùng cache RAM để dedupe

Static `HashSet<String> processedIds` trong Java chỉ sống trong một process. Khi GKE/Cloud Run scale nhiều replicas hoặc restart, cache bị mất. Dedupe cần **durable, shared store** với ràng buộc unique/transaction. TTL của marker phải đủ dài so với khả năng replay/publisher retry; xóa marker quá sớm có thể tạo hiệu ứng trùng sau này.

## 10. Transactional outbox ở phía publisher

Một trường hợp ngược lại: Orders API commit `payment_status=PAID` vào Cloud SQL nhưng crash **trước khi publish**. Nếu chỉ gọi DB rồi gọi Pub/Sub tuần tự, sự kiện có thể biến mất.

**Transactional outbox** ghi business state và sự kiện cần publish trong **cùng transaction DB**:

~~~mermaid
flowchart LR
    APP["Orders API"] --> TX["DB transaction:<br/>update order + insert outbox"]
    TX --> RELAY["Outbox relay"]
    RELAY --> PUB["Pub/Sub topic"]
    PUB --> CON["Consumer inbox + transaction"]
    CON --> DB["Shipping task"]
~~~

Pseudocode:

~~~text
BEGIN;
UPDATE orders SET payment_status = 'PAID' WHERE id = :orderId;
INSERT INTO outbox(event_id, payload, published)
VALUES (:stableEventId, :jsonPayload, false);
COMMIT;

Outbox relay:
    đọc record chưa published
    publish Pub/Sub message kèm eventId
    nhận publish response
    đánh dấu outbox record đã gửi
~~~

Nếu relay publish thành công nhưng crash trước khi đánh dấu `published`, nó có thể publish lại → consumer vẫn cần **inbox/dedupe**. Outbox giảm **nguy cơ mất sự kiện** giữa DB và Pub/Sub nhưng không tự tạo giao dịch nguyên tử xuyên hai hệ thống.

## 11. Ordering khác exactly-once

Pub/Sub hỗ trợ **message ordering theo ordering key** khi subscription bật tính năng, các messages cùng key được publish từ **cùng region** và source thực hiện đúng các điều kiện ordering.

| Nhu cầu | Tính năng |
| --- | --- |
| Không xử lý cùng Pub/Sub message sau confirmed ACK | Exactly-once delivery (pull, regional) |
| Nhận messages của cùng order theo thứ tự publish được hỗ trợ | Message ordering theo `orderingKey=orderId` |
| Một `OrderPaid` không tạo hai shipping tasks | Business idempotency + durable transaction |
| Một business event không bị publish hai lần ngoài ý muốn | Publisher eventId/outbox/dedupe |
| Không có tranh chấp trạng thái giữa hai orders khác nhau | Business transaction/partitioning phù hợp |

Với **ordering + exactly-once**, ACK của messages cùng ordering key cần được thực hiện **đúng thứ tự**. ACK out-of-order có thể nhận lỗi tạm; nếu deadline hết, có redelivery hợp lệ. Kết hợp hai tính năng có thể làm giảm throughput; không bật ordering cho toàn topic nếu business chỉ cần xử lý mỗi message độc lập.

**Một ordering key không phải khóa database.** Nếu cập nhật cùng order từ API HTTP và consumer đồng thời, cần optimistic locking/version checks trong DB.

## 12. Push, Cloud Run và Eventarc: giới hạn không thể bỏ qua

| Mô hình nhận | Exactly-once Pub/Sub? | Cách thiết kế |
| --- | --- | --- |
| Java `Subscriber` trên GKE dùng StreamingPull | **Có thể bật**, khi đáp ứng region/client library | Confirmed ACK + idempotent business |
| Batch Pull API | **Có thể bật** | ACK response/check deadline |
| Pub/Sub push → Cloud Run HTTP endpoint | **Không** | HTTP success/failure + idempotency key |
| Eventarc → Cloud Run function | **Không mặc định là Pub/Sub exactly-once** | CloudEvents event ID + durable dedupe |
| BigQuery/Cloud Storage export subscription | **Không** | Thiết kế sink/storage semantics riêng |
| Dataflow pipeline | Semantics xử lý của Dataflow **theo tài liệu riêng** | Không suy ra từ cờ exactly-once của Pub/Sub |

**Push ACK** là HTTP success response, nhưng sender không biết chắc response đã tới và được xử lý trong mọi trường hợp mạng lỗi; vì vậy push không có confirmed ACK semantics giống pull exactly-once. Nếu cần một Cloud Run service xử lý events push, dùng **inbox/idempotency**, không cố bật `--enable-exactly-once-delivery` trên push subscription.

## 13. Lab gcloud: so sánh hai pull subscriptions

**Điều kiện:** project lab có Billing/API/IAM được phê duyệt. Lệnh tạo/xóa resources có thể phát sinh phí và ảnh hưởng dữ liệu trong subscription; tuyệt đối không chạy trên topic production.

~~~bash
gcloud config get-value project

gcloud services enable pubsub.googleapis.com \
  --project=PROJECT_ID

# Topic lab mới; nếu đã có thì dùng topic lab riêng tương đương.
gcloud pubsub topics create orders-events-lab \
  --project=PROJECT_ID

# Subscription mặc định: at-least-once, pull.
gcloud pubsub subscriptions create orders-atleast-lab \
  --topic=orders-events-lab \
  --ack-deadline=30 \
  --project=PROJECT_ID

# Pull subscription có exactly-once delivery.
gcloud pubsub subscriptions create orders-exactly-lab \
  --topic=orders-events-lab \
  --ack-deadline=60 \
  --enable-exactly-once-delivery \
  --project=PROJECT_ID
~~~

Nếu gắn **hai subscriptions vào cùng topic**, mỗi subscription nhận bản message của **chính nó**, không có nghĩa Pub/Sub tạo hai publisher messages.

Kiểm tra:

~~~bash
gcloud pubsub subscriptions describe orders-atleast-lab \
  --project=PROJECT_ID \
  --format="yaml(name,topic,ackDeadlineSeconds,enableExactlyOnceDelivery)"

gcloud pubsub subscriptions describe orders-exactly-lab \
  --project=PROJECT_ID \
  --format="yaml(name,topic,ackDeadlineSeconds,enableExactlyOnceDelivery)"
~~~

Publish event test:

~~~bash
gcloud pubsub topics publish orders-events-lab \
  --message='{"eventId":"order-paid:LAB-1:v1","orderId":"LAB-1"}' \
  --project=PROJECT_ID
~~~

Pull thủ công **không tự ACK**:

~~~bash
gcloud pubsub subscriptions pull orders-atleast-lab \
  --limit=1 --project=PROJECT_ID

gcloud pubsub subscriptions pull orders-exactly-lab \
  --limit=1 --project=PROJECT_ID
~~~

Sau khi không ACK và deadline trôi qua, message **có thể** được giao lại cùng `messageId`. Đừng kỳ vọng nhận lại chính xác sau 30 hoặc 60 giây; retry policy và trạng thái delivery có thể làm trễ.

Nếu dùng:

~~~bash
gcloud pubsub subscriptions pull orders-atleast-lab \
  --limit=1 --auto-ack --project=PROJECT_ID
~~~

thì `gcloud` ACK ngay theo cơ chế CLI; lệnh này **chỉ phù hợp demo**, không đại diện việc xử lý business trước ACK và **không dùng để kiểm chứng confirmed ACK của Java exactly-once subscriber**.

**Không nên cố tạo duplicate delivery bằng cách đánh hỏng production network.** Bài lab chỉ quan sát cấu hình và semantics; bài kiểm thử ACK-confirmation nên dùng Java client ở mục sau.

## 14. Java subscriber: xử lý rồi kiểm tra ACK response

Dùng thư viện `com.google.cloud:google-cloud-pubsub` ở phiên bản hỗ trợ exactly-once (tham khảo tài liệu khuyến nghị **v1.139.0 trở lên**; production sử dụng bản đã kiểm duyệt). Xác thực bằng **Application Default Credentials**: GKE Workload Identity Federation, Compute Engine service account hoặc developer ADC; tránh service account private key nhúng source.

Ví dụ một class nhận Pub/Sub messages, xác nhận kết quả ACK:

~~~java
import com.google.cloud.pubsub.v1.AckReplyConsumerWithResponse;
import com.google.cloud.pubsub.v1.AckResponse;
import com.google.cloud.pubsub.v1.MessageReceiverWithAckResponse;
import com.google.cloud.pubsub.v1.Subscriber;
import com.google.pubsub.v1.ProjectSubscriptionName;
import com.google.pubsub.v1.PubsubMessage;
import java.util.concurrent.ExecutionException;

public class ExactlyOnceShippingSubscriber {
    public static void main(String[] args) {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: java ExactlyOnceShippingSubscriber PROJECT_ID SUBSCRIPTION_ID");
        }

        ProjectSubscriptionName subName =
                ProjectSubscriptionName.of(args[0], args[1]);

        MessageReceiverWithAckResponse receiver =
                (PubsubMessage msg, AckReplyConsumerWithResponse reply) -> {
                    String messageId = msg.getMessageId();

                    // DEMO ONLY: thay bằng Cloud SQL transaction + durable dedupe.
                    try {
                        processIdempotently(msg);
                    } catch (RuntimeException failure) {
                        System.err.println("Business error, NACK: " + messageId);
                        reply.nack();
                        return;
                    }

                    try {
                        // Chỉ ACK sau khi phần nghiệp vụ đã COMMIT.
                        AckResponse result = reply.ack().get();
                        if (result == AckResponse.SUCCESSFUL) {
                            System.out.println("ACK confirmed: " + messageId);
                        } else {
                            System.err.println("ACK not confirmed, messageId="
                                    + messageId + " result=" + result);
                            // Nếu được giao lại: dedupe trong DB sẽ bảo vệ side effect.
                        }
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                        System.err.println("ACK interrupted: " + messageId);
                    } catch (ExecutionException ex) {
                        System.err.println("ACK failed: " + messageId
                                + " cause=" + ex.getCause());
                    }
                };

        Subscriber subscriber = Subscriber.newBuilder(subName, receiver)
                .setEndpoint("asia-southeast1-pubsub.googleapis.com:443")
                .build();

        Runtime.getRuntime().addShutdownHook(
                new Thread(() -> subscriber.stopAsync().awaitTerminated()));

        subscriber.startAsync().awaitRunning();
        System.out.println("Listening: " + subName);
        subscriber.awaitTerminated();
    }

    private static void processIdempotently(PubsubMessage msg) {
        // Ví dụ không có side effect; production cần transaction như mục 9.
        System.out.println("Event received, messageId=" + msg.getMessageId());
    }
}
~~~

**Điểm cần hiểu, không chỉ copy code:**

- `MessageReceiverWithAckResponse` và `reply.ack().get()` giúp phân biệt **ACK được xác nhận** với ACK request vừa được gửi.
- `processIdempotently` trong demo **chỉ in log**, không đạt exactly-once business effect. Khi làm thực, thay bằng transaction durable `processed_events + shipping_tasks` trước ACK.
- Khi ACK thất bại, **không rollback một DB transaction đã commit**; đợi redelivery để dedupe, xem ACK ID/deadline và alert.
- Chọn **cùng locational endpoint** cho mọi subscribers được áp exactly-once trong hệ thống; nếu chạy region khác cần thiết kế lại.
- Sample chờ ACK synchronously để dễ thấy kết quả; production cần flow control, executor/lease settings, shutdown và backpressure tối ưu throughput.
- Worker và ACK callback phải thread-safe; không log payload chứa PII.

## 15. Retry, dead-letter topic và replay

### 15.1. Retry policy

Pub/Sub có retry kiểu immediate hoặc exponential backoff theo subscription. Khi message bị NACK/hết deadline, Pub/Sub có thể redeliver đến **một worker khác** đang kết nối cùng subscription. Mọi worker phải thực hiện cùng dedupe rules.

Phân loại lỗi:

| Loại lỗi | Xử lý |
| --- | --- |
| Cloud SQL timeout/503 tạm thời | NACK hoặc để redelivery; retry/backoff và giới hạn tải |
| Payload không hợp lệ vĩnh viễn | Đưa vào quy trình xử lý lỗi/DLQ, tránh poison-message loop |
| Business event đã được xử lý | ACK mà không tạo side effect lần nữa |
| KSA/service account thiếu IAM | Sửa quyền; retry vô hạn không chữa được |
| Downstream side effect không rõ đã thành công chưa | Reconcile bằng idempotency key, không gửi lặp mù quáng |

### 15.2. Dead-letter topic là best-effort, không phải exactly-once

Có thể gắn **dead-letter topic (DLT)** vào subscription khi xử lý không thành công. `maxDeliveryAttempts` cấu hình từ **5 đến 100** (mặc định 5 khi bật), nhưng **số lần thực tế xấp xỉ**, không phải giới hạn cứng. Pub/Sub service agent cần quyền **Publisher** lên DLT và quyền **Subscriber** trên source subscription để chuyển và ACK messages đúng.

~~~bash
# Ví dụ cho topic/subscription lab đã tạo.
gcloud pubsub topics create orders-dead-lab \
  --project=PROJECT_ID

gcloud pubsub subscriptions create orders-dead-inspect-lab \
  --topic=orders-dead-lab \
  --project=PROJECT_ID

gcloud pubsub subscriptions update orders-atleast-lab \
  --dead-letter-topic=orders-dead-lab \
  --max-delivery-attempts=5 \
  --project=PROJECT_ID
~~~

**Chưa đủ để DLT hoạt động:** quản trị viên phải cấp các quyền cho **Pub/Sub service agent** đúng project theo tài liệu Dead-letter topics. Sau đó kiểm tra `subscription/dead_letter_message_count`, backlog DLT và triage process.

### 15.3. Retention, seek và chủ động replay

Messages đã ACK thường không còn được giao trên subscription. Tuy nhiên nếu bật **retain acknowledged messages/topic retention**, hoặc dùng **snapshot + seek** theo điều kiện, quản trị viên có thể **chủ động đưa messages cũ trở lại luồng xử lý**. Dedupe store phải tính đến **replay theo nghiệp vụ**, không mặc định “ACK rồi nên event không bao giờ xuất hiện nữa”.

## 16. Theo dõi subscription và kiểm soát chi phí

Các metrics Cloud Monitoring hữu ích:

| Metric / dữ liệu | Hành động |
| --- | --- |
| `subscription/num_undelivered_messages` | Theo dõi backlog, capacity subscriber |
| `subscription/oldest_unacked_message_age` | Cảnh báo khi RPO/processing delay vượt mục tiêu |
| `subscription/expired_ack_deadlines_count` | Xem lease extension/processing time |
| `subscription/exactly_once_warning_count` | Đọc ACK/ModifyAckDeadline failures; **chỉ báo chẩn đoán**, có thể noisy |
| `subscription/dead_letter_message_count` | Điều tra messages không xử lý được |
| Subscriber logs `messageId`, `eventId`, delivery attempt, ackResult | Phân biệt Pub/Sub redelivery và publisher duplicate |
| DB processed-events unique conflicts | Đo nghiệp vụ dedupe, không coi mọi conflict là lỗi |
| Pub/Sub billing/egress/storage | Đánh giá chi phí message volume, retention/retries và network |

**Đừng dựa một metric để kết luận có duplicate.** `exactly_once_warning_count` có thể tăng vì các thao tác trên ACK ID đã hết hạn, không đồng nghĩa Pub/Sub vi phạm bảo đảm. Cần tương quan message ID, ACK result, deadline và client region.

### 16.1. Giá và IAM

- Pub/Sub có tính phí theo data volume, storage/retention, message delivery và các yếu tố mạng/tính năng theo bảng giá hiện hành; exactly-once, ordering, retries và DLT có thể ảnh hưởng latency/tài nguyên.
- Publisher cần `roles/pubsub.publisher` trên topic.
- Subscriber cần `roles/pubsub.subscriber` trên subscription để nhận và ACK.
- Admin tạo subscriptions/topics cần vai trò quản lý hẹp đúng tài nguyên.
- Nếu consumer ghi Cloud SQL/Cloud Storage, cấp **quyền riêng** cho runtime identity; Pub/Sub ACK không tự cấp IAM database.

Đặt Cloud Billing budget alert theo project và service, nhưng **budget alert không phải hard cap chi tiêu**. Bảo vệ dữ liệu và SLO trước khi giảm retention/flow control vì chi phí.

## 17. Tình huống tổng hợp: OrderPaid → một shipping task

**Giả định:** `orders-api` nhận thanh toán qua HTTP rồi ghi Cloud SQL, phát `OrderPaid` qua Pub/Sub. GKE `shipping-worker` dùng Pull/StreamingPull, truy cập Cloud SQL tạo `shipping_tasks` và gọi API bên vận chuyển.

| Rủi ro | Cơ chế |
| --- | --- |
| DB commit thành công nhưng publish thất bại | Transactional outbox |
| Publisher publish lại cùng sự kiện | Stable business `eventId` |
| Subscriber crash sau DB commit | Transactional inbox + unique key |
| Pub/Sub redelivery sau ack timeout | Confirmed ACK, lease management |
| Không muốn duplicate delivery ngoài ý muốn | Exactly-once pull trong cùng region |
| Gọi API vận chuyển lặp khi response mất | Gửi **idempotency key** tới đối tác hoặc có bước reconcile |
| Message payload lỗi liên tục | Retry/backoff + DLT + on-call xử lý |
| Backlog tăng khi sale peak | Flow control, autoscaling theo metrics và quota DB |

### 17.1. Ba sự cố phải diễn tập

1. **Crash trước COMMIT:** message chưa ACK → được giao lại → tạo đúng một shipping task.
2. **Crash sau COMMIT trước ACK:** được giao lại → thấy `processed_events` → ACK, không ghi trùng.
3. **Publisher retry tạo M1/M2:** cùng business `eventId` → consumer chỉ tạo một shipping task.

Với API vận chuyển ngoài Cloud SQL, vẫn cần idempotency key và reconcile. **Không thể khẳng định “tất cả side effects exactly once” chỉ bằng việc bật một subscription flag.**

## 18. Bài tập tự kiểm tra

**Câu 1.** At-least-once có nghĩa subscriber callback chỉ chạy một lần không?

*Đáp án:* Không. Message có thể được giao lại; consumer phải idempotent.

**Câu 2.** Pub/Sub exactly-once hỗ trợ push subscription tới Cloud Run không?

*Đáp án:* Không. Chính sách exactly-once delivery chỉ hỗ trợ pull/StreamingPull, không hỗ trợ push/export.

**Câu 3.** Một message được ACK thành công có phản hồi xác nhận rồi lại được giao trong cùng region khi exactly-once bật. Điều đó có đúng bảo đảm không?

*Đáp án:* Không. Sau confirmed ACK, Pub/Sub không redeliver cùng messageId trong phạm vi hỗ trợ.

**Câu 4.** Subscriber NACK M1 rồi nhận lại M1. Có vi phạm exactly-once không?

*Đáp án:* Không. Đây là redelivery hợp lệ.

**Câu 5.** Publisher retry tạo M1 và M2 cho cùng `OrderPaid`. Exactly-once có tự dedupe không?

*Đáp án:* Không. Cần business event ID hoặc idempotency key chung.

**Câu 6.** Vì sao `messageId` không đủ để ngăn tạo hai shipping tasks khi publisher retry?

*Đáp án:* Hai publishes có thể có hai Pub/Sub message IDs khác nhau; business ID phải ổn định.

**Câu 7.** Worker commit Cloud SQL rồi crash trước ACK. Làm sao tránh ghi trùng?

*Đáp án:* Ghi durable marker và business update **trong cùng DB transaction**, rồi ACK sau COMMIT.

**Câu 8.** Worker gọi email API ngay trong DB transaction. Có được atomic giữa email và DB không?

*Đáp án:* Không. External API cần idempotency key, outbox/reconcile.

**Câu 9.** Subscribers ở hai regions khác nhau cùng kết nối tới Pub/Sub. Có thể khẳng định exactly-once như khi ở một region không?

*Đáp án:* Không. Bảo đảm của Pub/Sub là regional; cần cùng locational endpoint và thiết kế dự phòng phù hợp.

**Câu 10.** `ackId` cũ còn hợp lệ sau khi message hết deadline và được giao lại với `ackId` mới không?

*Đáp án:* Với exactly-once, chỉ ACK ID delivery mới nhất hợp lệ; ID cũ sẽ bị từ chối.

**Câu 11.** Nếu kết hợp ordering và exactly-once, có thể ACK M3 trước M1/M2 cùng key để tăng tốc không?

*Đáp án:* Không nên; ACK cần theo thứ tự, nếu sai có thể bị từ chối hoặc redelivery.

**Câu 12.** `maxDeliveryAttempts=5` có bảo đảm message chắc chắn vào DLT đúng lần thứ năm không?

*Đáp án:* Không. DLT forwarding là best-effort, số lần thử chỉ xấp xỉ và cần đúng IAM.

**Câu 13.** `exactly_once_warning_count` tăng có chứng minh Pub/Sub đã gửi duplicate không?

*Đáp án:* Không. Metric cũng ghi ACK ID invalid hoặc request failures; cần correlate logs.

**Câu 14.** ACK trước khi commit vì muốn giảm độ trễ có an toàn không?

*Đáp án:* Không. Crash sau ACK trước commit có thể khiến công việc bị mất.

## 19. Checklist trước production

- [ ] Phân biệt mục tiêu **delivery** với **business effects**; ghi rõ tác dụng nào cần idempotent.
- [ ] Mỗi business event có **eventId ổn định**, không chỉ messageId của Pub/Sub.
- [ ] Consumer xử lý side effect bền vững **trước ACK**.
- [ ] Dedupe marker và DB update nằm **trong cùng transaction** khi có thể.
- [ ] External APIs có idempotency key/compensation/reconcile phù hợp.
- [ ] Nếu dùng exactly-once: subscription **pull/StreamingPull**, confirmed ACK, cùng region/endpoint.
- [ ] Lease extension, max outstanding messages/bytes và worker concurrency đã load test.
- [ ] Không giả định ACK ID cũ còn hợp lệ sau redelivery.
- [ ] Ordering key chỉ bật khi cần, ACK theo thứ tự nếu kết hợp exactly-once.
- [ ] Retry, retention, DLT IAM và poison-message handling được diễn tập.
- [ ] Nếu có replay/seek, dedupe state và business rules xử lý được events cũ.
- [ ] Có dashboards về backlog, oldest age, expired ack deadlines, ack warnings và DLT.
- [ ] IAM Publisher/Subscriber/runtime identity theo quyền tối thiểu; không đưa secrets vào payload/logs.
- [ ] Có SLO, budget alert và runbook cho crash-window/duplicate publish/ACK failure.

## 20. Kết luận

**At-least-once là mặc định; exactly-once của Pub/Sub là bảo đảm delivery/ACK có phạm vi, không phải transaction xuyên hệ thống.** Với pull/StreamingPull trong một region và confirmed ACK, Pub/Sub ngăn unexpected duplicate deliveries của cùng Pub/Sub message. Nhưng **NACK, hết deadline, publisher retries và external side effects** vẫn đòi hỏi ứng dụng thiết kế đúng.

Một consumer đáng tin cậy có công thức ngắn gọn: **business event ID ổn định → xử lý idempotent bằng durable transaction → ACK sau COMMIT → kiểm tra ACK result → quan sát retry/backlog**. Đó là cách biến mức bảo đảm giao thông điệp thành kết quả nghiệp vụ có thể kiểm chứng.

## Tài liệu tham khảo chính thức

- [Pub/Sub exactly-once delivery](https://cloud.google.com/pubsub/docs/exactly-once-delivery)
- [Pub/Sub subscription overview](https://cloud.google.com/pubsub/docs/subscription-overview)
- [Pub/Sub subscription properties](https://cloud.google.com/pubsub/docs/subscription-properties)
- [Pub/Sub pull subscriptions](https://cloud.google.com/pubsub/docs/pull)
- [Best practices for Pub/Sub subscribers](https://cloud.google.com/pubsub/docs/subscribe-best-practices)
- [Troubleshoot pull subscriptions](https://cloud.google.com/pubsub/docs/pull-troubleshooting)
- [Pub/Sub API endpoints and regional routing](https://cloud.google.com/pubsub/docs/reference/service_apis_overview)
- [Java sample: subscribe with exactly-once delivery](https://cloud.google.com/pubsub/docs/samples/pubsub-subscriber-exactly-once)
- [Pub/Sub message ordering](https://cloud.google.com/pubsub/docs/ordering)
- [Pub/Sub dead-letter topics](https://cloud.google.com/pubsub/docs/dead-letter-topics)
- [gcloud pubsub subscriptions create](https://cloud.google.com/sdk/gcloud/reference/pubsub/subscriptions/create)
- [Pub/Sub monitoring](https://cloud.google.com/pubsub/docs/monitoring)
- [Pub/Sub pricing](https://cloud.google.com/pubsub/pricing)

