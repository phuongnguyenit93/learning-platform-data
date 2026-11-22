# Acknowledgment deadlines và xử lý redelivery trong Pub/Sub

> **Chương:** Pub/Sub và thông điệp  
> **Bài học:** Acknowledgment deadlines và xử lý redelivery  
> **Mô-đun:** CLOUD_PROVIDERS_GCP

Trong mô-đun **CLOUD_PROVIDERS_GCP**, người học tìm hiểu Google Cloud từ tổ chức project, IAM, VPC đến Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu. Với hệ thống Java giao tiếp qua **Pub/Sub**, độ tin cậy không kết thúc khi publisher gửi thành công: subscriber phải biết **khi nào xác nhận đã xử lý, khi nào để message gửi lại và cách bảo vệ nghiệp vụ trước tác động trùng**.

Pub/Sub mặc định có mô hình **at-least-once delivery**. Sau khi message được chuyển cho một subscription, Pub/Sub chờ **acknowledgment** trong khoảng **acknowledgment deadline**. Nếu subscriber **nack**, hoặc deadline hết mà chưa có xác nhận hợp lệ, message có thể **redeliver**. Tính năng này giúp hệ thống phục hồi khi worker lỗi nhưng có thể gây cập nhật đơn hàng hoặc thanh toán **hai lần** nếu code thiếu **idempotency**.

**Nguyên tắc:** **ghi kết quả bền vững rồi mới ack**, dùng lease extension cho công việc lâu, retry/backoff và dead-letter topic cho lỗi kéo dài, đồng thời xây dựng idempotency ngay cả khi bật exactly-once delivery. Các ví dụ dùng project sandbox giả định; lệnh tạo/xóa tài nguyên có thể phát sinh chi phí và không được chạy trên production nếu chưa được phê duyệt.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt `messageId`, `ackId`, ack, nack, ack deadline và message retention.
2. Giải thích thời điểm và nguyên nhân **redelivery** trong pull/StreamingPull và push.
3. Chọn initial deadline: mặc định **10 giây**, phạm vi **10–600 giây**; biết khi nào dùng `ModifyAckDeadline`.
4. Sử dụng automatic **lease management** và flow control trong Java subscriber.
5. Phân biệt **retry immediately**, **exponential backoff** và **push backoff**.
6. Thiết kế **dead-letter topic (DLQ)**, IAM cho Pub/Sub service agent và quy trình replay an toàn.
7. Hiểu ranh giới của **exactly-once delivery** so với **exactly-once business effects**.
8. Viết và kiểm tra Java subscriber ack/nack đúng thứ tự giao dịch.
9. Quan sát backlog, expired ack deadlines, push failures, DLQ và chi phí.
10. Xử lý worker crash, poison message, ordering key và lỗi downstream.

## 2. Message, subscription và trạng thái acknowledgment

~~~mermaid
sequenceDiagram
    participant P as Publisher
    participant T as Pub/Sub Topic
    participant S as Subscription
    participant W as Java Worker
    P->>T: Publish(orderId=OD-42)
    T->>S: Message đến subscription
    S-->>W: Deliver(messageId=M, ackId=A1)
    Note over W: Ack deadline bắt đầu
    W->>W: Xử lý và commit bền vững
    W->>S: Acknowledge(A1)
    Note over S: Ghi nhận xử lý cho subscription
~~~

| Thuật ngữ | Nghĩa |
|---|---|
| **Topic** | Điểm publisher gửi messages |
| **Subscription** | Một luồng nhận có ack state riêng; hai subscriptions cùng topic nhận message độc lập |
| **Message ID** | Định danh do Pub/Sub gán khi publish; hữu ích theo dõi một message |
| **Ack ID** | Token của **lần delivery hiện tại**, dùng để ack/nack/gia hạn; có thể **thay đổi sau redelivery** |
| **Outstanding** | Message đã được deliver nhưng chưa được ack hoàn tất |
| **Ack deadline** | Khoảng chờ acknowledgment của lần delivery |
| **Nack** | Báo chưa xử lý thành công để message được retry |
| **Redelivery** | Cùng Pub/Sub message được chuyển lại |
| **Backlog** | Messages chưa được ack trong subscription |
| **Retention** | Thời gian lưu message, **khác** ack deadline |

**Không nhầm fan-out với duplicate:** cùng message đến hai subscriptions `billing-sub` và `shipping-sub` là hành vi bình thường. Hai lần nhận **cùng messageId trong cùng subscription** thường thể hiện redelivery/duplicate delivery.

### 2.1. Điều gì xảy ra khi worker crash?

~~~text
t=0s   Worker A nhận message M, ackId=A1; deadline 10s
t=2s   Worker A commit kết quả vào Cloud SQL
t=3s   Worker A crash trước khi ack
t>=10s Lease hết hạn; M có thể được gửi lại
t=12s  Worker B nhận cùng messageId M, ackId=B2
t=13s  Worker B thấy business event đã xử lý trong DB
t=14s  Worker B bỏ qua side effect và ack B2
~~~

Redelivery **không cam kết xảy ra đúng ngay tại giây thứ 10**; thời điểm còn phụ thuộc retry policy, flow control, network và khả năng phục vụ. Ở at-least-once, vẫn cần chịu được duplicate ngay cả khi một lần ack trước đó được gửi.

## 3. Acknowledgment deadline và các thao tác ack

### 3.1. Thông số cấp subscription

| Thuộc tính | Giá trị |
|---|---|
| Ack deadline mặc định | **10 giây** |
| Nhỏ nhất / lớn nhất | **10 / 600 giây** |
| Phạm vi | Initial deadline sau mỗi lần delivery |
| Pull/StreamingPull | Có thể kéo dài từng message bằng `ModifyAckDeadline` |
| Push | Deadline cũng xác định timeout của HTTP request; **không gia hạn riêng một message** |
| Message retention mặc định | **7 ngày**, có giới hạn cấu hình riêng; không phải thời gian xử lý |

Một subscription có ack deadline 60 giây **không xóa message sau 60 giây**. Nếu chưa ack, message vẫn có thể nằm trong retention window và được gửi lại.

### 3.2. Các hành động và hệ quả

| Hành động | Điều Pub/Sub hiểu | Hệ quả |
|---|---|---|
| `ack(ackId)` | Message đã xử lý | Không cần delivery tiếp theo theo semantics hiện tại |
| `nack()` | Chưa xử lý xong | Retry theo policy |
| `ModifyAckDeadline(ackId, 120)` | Cấp thêm thời gian xử lý | Dời deadline của delivery hiện tại |
| `ModifyAckDeadline(ackId, 0)` | Tương đương nack với pull | Message đủ điều kiện retry |
| Không gửi ack/nack | Chưa có kết quả | Hết deadline có thể redeliver |

**Không dùng `messageId` thay `ackId`** trong API Acknowledge/ModifyAckDeadline. Ack ID cũ sau redelivery có thể không còn hợp lệ, đặc biệt trên subscription bật exactly-once.

### 3.3. Deadline thấp và cao đều có đánh đổi

- **Quá thấp:** worker xử lý 45 giây, deadline 10 giây; message có thể đến worker khác trong khi việc cũ chưa xong.
- **Quá cao:** worker lỗi sau 1 giây nhưng deadline 600 giây; message có thể không được retry sớm nếu không có tín hiệu khác.
- **Phù hợp:** dựa trên p95/p99 thời gian xử lý và lease extension, cân bằng duplicate risk với recovery latency.

Đừng đặt `600` cho mọi subscription chỉ để “chắc chắn không trùng”. Cần đo thời gian xử lý, giới hạn job timeout và quan sát ack expirations.

## 4. Pull, StreamingPull và push khác nhau thế nào?

| Thuộc tính | Pull / StreamingPull | Push |
|---|---|---|
| Ai lấy message? | Subscriber chủ động kết nối | Pub/Sub gửi HTTPS request |
| Cách ack | `Acknowledge(ackId)` hoặc client `ack()` | HTTP status thành công |
| Nack | `nack()`/deadline 0 | HTTP lỗi hoặc timeout |
| Gia hạn từng delivery | **Có** | **Không** |
| Exactly-once delivery | **Có**, theo điều kiện hỗ trợ | **Không** |
| Kiểu ứng dụng phù hợp | Java worker trên GKE/VM, xử lý thay đổi thời gian | HTTP endpoint Cloud Run, công việc ngắn |

### 4.1. Push: trả HTTP status là một lần ack

Pub/Sub chấp nhận các HTTP status `102`, `200`, `201`, `202` và `204` là acknowledgment thành công. Các response khác hoặc timeout có thể làm Pub/Sub redeliver.

~~~text
Pub/Sub push → Cloud Run /pubsub
  1. Cloud Run xác minh OIDC push identity và Invoker IAM
  2. Java handler decode/validate message
  3. Commit DB hoặc ghi task vào hàng đợi bền vững
  4. Trả HTTP 204
~~~

**Lỗi phổ biến:** trả `202 Accepted` ngay rồi chỉ lưu message vào biến in-memory và xử lý ở thread nền. Nếu instance bị hủy, Pub/Sub đã coi message là ack và không tự gửi lại. Với tác vụ bất đồng bộ, phải đưa vào **durable queue/store trước khi trả 2xx**.

Với Cloud Run private, dùng authenticated push và cấp `roles/run.invoker` cho đúng push service account. Không bật unauthenticated access chỉ để sửa 403.

### 4.2. Push backoff độc lập với retry policy

Khi push endpoint trả nhiều lỗi/timeout, Pub/Sub có **push backoff** tự động (xấp xỉ **100 ms–60 giây**), có thể chậm **toàn subscription**. Retry exponential backoff là cơ chế khác; khi cả hai áp dụng, thời gian retry dùng mức trì hoãn lớn hơn theo semantics dịch vụ. Vì vậy một poison message hoặc endpoint lỗi hàng loạt có thể làm tốc độ push giảm dù còn message hợp lệ.

## 5. Lease management cho công việc Java lâu

Với **high-level Java StreamingPull client**, thư viện tự gọi `ModifyAckDeadline` khi message chưa ack. Nó có thể chọn thời lượng lease dựa trên độ trễ acknowledgment lịch sử (ví dụ p99) và gia hạn nhiều lần.

~~~mermaid
sequenceDiagram
    participant S as Pub/Sub
    participant J as Java Subscriber
    S-->>J: Message M (initial 10s)
    Note over J: Công việc mất 90s
    J->>S: ModifyAckDeadline(M, 45s)
    J->>S: ModifyAckDeadline(M, 45s)
    J->>J: Commit thành công
    J->>S: Ack(M)
~~~

**Các điểm thực hành:**

- High-level libraries mặc định có thể gia hạn **tổng khoảng một giờ**; tổng lease và thời lượng mỗi lần gia hạn có các option riêng.
- Khi subscriber crash, mất network hoặc hết tổng lease period, message có thể redeliver.
- **Gia hạn không đồng nghĩa khóa độc quyền vĩnh viễn** trong at-least-once; idempotency vẫn cần.
- Nếu một job kéo dài hàng giờ, cân nhắc **chia tác vụ, checkpoint bền vững, Cloud Tasks/Workflows hoặc quy trình job riêng**.
- **Flow control** giới hạn messages/bytes outstanding. Để worker 8 threads nhận 10.000 messages có thể làm hàng nghìn deliveries chờ và hết lease trước khi được xử lý.

## 6. Java pull subscriber: ack sau thành công, nack khi lỗi

### 6.1. Maven POM tối giản

Ví dụ JDK 17; dùng Google Cloud Libraries BOM để quản lý dependency versions:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example.messaging</groupId>
  <artifactId>orders-subscriber</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
  </properties>
  <dependencyManagement>
    <dependencies>
      <dependency>
        <groupId>com.google.cloud</groupId>
        <artifactId>libraries-bom</artifactId>
        <version>26.90.0</version>
        <type>pom</type>
        <scope>import</scope>
      </dependency>
    </dependencies>
  </dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>com.google.cloud</groupId>
      <artifactId>google-cloud-pubsub</artifactId>
    </dependency>
  </dependencies>
</project>
~~~

BOM `26.90.0` là một phiên bản tham khảo theo tài liệu Google Cloud Java tại thời điểm viết; với project thật, pin và đánh giá version phù hợp, dependency scan và compatibility.

### 6.2. Mã Java cho StreamingPull

~~~java
package com.example.messaging;

import com.google.cloud.pubsub.v1.AckReplyConsumer;
import com.google.cloud.pubsub.v1.MessageReceiver;
import com.google.cloud.pubsub.v1.Subscriber;
import com.google.pubsub.v1.ProjectSubscriptionName;
import com.google.pubsub.v1.PubsubMessage;

public final class OrdersSubscriber {
    public static void main(String[] args) {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                "Usage: OrdersSubscriber PROJECT_ID SUBSCRIPTION_ID");
        }
        ProjectSubscriptionName name =
            ProjectSubscriptionName.of(args[0], args[1]);

        MessageReceiver receiver =
            (PubsubMessage msg, AckReplyConsumer consumer) -> {
                String data = msg.getData().toStringUtf8();
                try {
                    // DEMO: production phải dùng DB commit + idempotency.
                    if (data.startsWith("FAIL")) {
                        throw new IllegalStateException("Simulated error");
                    }
                    System.out.println("Processed " + msg.getMessageId()
                        + " data=" + data);
                    consumer.ack(); // Chỉ ACK khi thực sự thành công.
                } catch (Exception error) {
                    System.err.println("Failed " + msg.getMessageId()
                        + ": " + error.getMessage());
                    consumer.nack(); // Retry theo subscription policy.
                }
            };

        Subscriber subscriber = Subscriber.newBuilder(name, receiver).build();
        Runtime.getRuntime().addShutdownHook(
            new Thread(() -> subscriber.stopAsync()));
        subscriber.startAsync().awaitRunning();
        System.out.println("Listening on " + name);
        subscriber.awaitTerminated();
    }
}
~~~

Lưu tại `src/main/java/com/example/messaging/OrdersSubscriber.java`. Build bằng Maven/IDE và chạy với đầy đủ dependencies; chương trình là **ví dụ pull worker**, không phải production-ready database processor.

**Giới hạn:** `System.out.println` không phải side effect bền vững. Trong production, **commit DB hoặc durable downstream operation trước khi `consumer.ack()`**. Mọi exception đều nack trong demo; hệ thống thực phải phân biệt lỗi tạm thời với poison message và dùng DLQ để tránh vòng lặp.

### 6.3. IAM và xác thực

| Danh tính | Quyền phù hợp |
|---|---|
| Publisher service account | `roles/pubsub.publisher` trên topic |
| Java subscriber runtime identity | `roles/pubsub.subscriber` trên subscription |
| Deployer/CI | Quyền triển khai Compute Engine/GKE riêng |
| Pub/Sub service agent | Chỉ có thêm IAM DLQ khi cần forwarding |

Sử dụng Application Default Credentials (ADC) với service account gắn VM, Workload Identity Federation for GKE hoặc service identity phù hợp. Trên máy developer, `gcloud auth application-default login` theo chính sách nội bộ. **Không commit JSON key hoặc access token vào Git/log**.

## 7. Redelivery và durable idempotency

### 7.1. Cửa sổ “DB commit xong, ack chưa xong”

~~~mermaid
sequenceDiagram
    participant S as Pub/Sub
    participant A as Worker A
    participant DB as Cloud SQL
    participant B as Worker B
    S-->>A: M (eventId=e-42)
    A->>DB: COMMIT business update
    Note over A: Crash trước ACK
    S-->>B: Redeliver M
    B->>DB: Kiểm tra unique eventId
    DB-->>B: Event đã xử lý
    B->>S: ACK, không tạo side effect mới
~~~

Pub/Sub acknowledgment và Cloud SQL transaction là **hai giao dịch riêng**. Exactly-once delivery cũng không làm hai hệ thống commit atomically. Cách an toàn là **durable deduplication**.

### 7.2. SQL tham khảo với unique constraint

~~~sql
CREATE TABLE processed_events (
    consumer_name TEXT NOT NULL,
    event_key     TEXT NOT NULL,
    processed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_key)
);

CREATE TABLE order_status (
    order_id      TEXT PRIMARY KEY,
    status        TEXT NOT NULL,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Trong **một transaction**, Java thực hiện:

1. `INSERT INTO processed_events ... ON CONFLICT DO NOTHING`.
2. **Nếu affected rows = 0:** message đã xử lý → commit transaction và ack, **không chạy lại business effect**.
3. **Nếu affected rows = 1:** cập nhật `order_status`, commit, rồi ack.
4. Nếu DB commit thất bại, **nack**; nếu ack network failure, message có thể redeliver nhưng marker ngăn làm lại.

~~~sql
BEGIN;

INSERT INTO processed_events (consumer_name, event_key)
VALUES ('orders-worker', 'ORDER_CONFIRMED:OD-42')
ON CONFLICT DO NOTHING;

-- Java kiểm tra số dòng INSERT ở trên.
-- CHỈ khi INSERT thật sự thêm một hàng mới:
INSERT INTO order_status (order_id, status)
VALUES ('OD-42', 'CONFIRMED')
ON CONFLICT (order_id)
DO UPDATE SET status = EXCLUDED.status, updated_at = now();

COMMIT;
~~~

Đoạn SQL là **quy trình minh họa**: bước UPDATE không tự bỏ qua khi INSERT trả 0; code Java cần kiểm tra affected rows và rẽ nhánh.

### 7.3. Chọn idempotency key đúng nguồn duplicate

| Kiểu trùng | Key phù hợp |
|---|---|
| Pub/Sub redelivery cùng message | `subscriptionId + messageId` nếu chỉ cần dedup ở subscription |
| Publisher publish cùng business event nhiều lần | **business eventId ổn định** |
| Yêu cầu charge tiền | `paymentId + operationType`, cùng idempotency của payment provider |
| Replay/seek hoặc rebuild consumer | Business eventId + version, theo policy replay |

**Không dùng `HashSet` trong RAM làm hệ thống dedup duy nhất**: restart hoặc scale nhiều Pods làm mất trạng thái. Với side effect ngoài DB (email, payment, HTTP), cần **transactional outbox** hoặc downstream idempotency; unique marker DB không thể tự rollback một HTTP call đã hoàn tất.

## 8. Retry immediately và exponential backoff

| Chính sách subscription | Ý nghĩa | Tác động |
|---|---|---|
| **Retry immediately** (mặc định) | Gửi lại sớm sau nack/timeout | Hồi phục nhanh nhưng dễ lặp lỗi liên tục |
| **Exponential backoff** | Chờ tăng dần trong khoảng min/max | Hữu ích khi downstream đang quá tải |
| **Push backoff** (tự động) | Throttle push khi nhiều request thất bại | Có thể làm chậm cả subscription |

**Phân biệt ba đồng hồ:** ack deadline = thời gian cho delivery hiện tại; retry backoff = khoảng chờ trước delivery sau; retention = thời gian message còn được lưu. Ví dụ Java cần 50 giây xử lý nhưng ack deadline 10 giây, tăng retry backoff lên 60 giây **không giải quyết việc lease bị hết**.

### 8.1. Xử lý lỗi theo loại

| Lỗi | Chiến lược |
|---|---|
| Cloud SQL timeout/HTTP 503 | Local retry ngắn, sau đó nack; exponential backoff |
| Publisher gửi JSON sai vĩnh viễn | Validate schema; cho lỗi vào DLQ, không retry nóng vô hạn |
| Event ID đã có trong bảng processed_events | Ack, không gọi lại downstream |
| 403 do IAM sai | Báo động vận hành; retry chỉ giúp sau khi sửa policy |
| GKE worker OOM | Giảm outstanding/concurrency, sửa JVM/resources và DB pool |
| Quota 429 downstream | Backoff có giới hạn, tôn trọng retry hints |

Không giữ delivery outstanding bằng `sleep` kéo dài hàng giờ chỉ để retry: nó giữ lease, làm tăng backlog và chi phí.

## 9. Dead-letter topic và poison messages

~~~mermaid
flowchart LR
    T["orders-topic"] --> S["orders-sub"]
    S --> J["Java worker"]
    J -->|"ACK"| OK["Hoàn thành"]
    J -. "NACK / hết deadline" .-> S
    S -->|"Best-effort sau max attempts"| DLQ["orders-dlq topic"]
    DLQ --> DLS["orders-dlq-sub"]
    DLS --> OPS["Điều tra / replay"]
~~~

- DLQ được cấu hình trên **subscription**, không trên source topic.
- `maxDeliveryAttempts` trong khoảng **5–100**; nếu bật và bỏ trống thì mặc định **5**.
- Số lần delivery trước khi chuyển DLQ là **best effort**, **không** chính xác tuyệt đối ở lần thứ N; đếm có thể reset.
- Pub/Sub **service agent thuộc project chứa source subscription** cần `roles/pubsub.publisher` trên DLQ topic và `roles/pubsub.subscriber` trên source subscription.
- **Tạo một subscription riêng trên DLQ topic** để quan sát các messages đã được forward.
- Một DLQ message có attributes mô tả source subscription và attempt count; dùng để điều tra, không tự động sửa schema.

**Java delivery attempts:** tài liệu mô tả attribute `googclient_deliveryattempt` trên Java client khi DLQ được cấu hình phù hợp. Bộ đếm có tính xấp xỉ; không dùng làm bằng chứng nghiệp vụ duy nhất.

### 9.1. Runbook DLQ

1. Đọc nguồn, event ID, schema version và error logs; tránh in PII/credentials.
2. Phân loại lỗi cố định (poison), lỗi tạm thời hoặc deploy lỗi.
3. Sửa dữ liệu/schema/permission và kiểm tra idempotency.
4. Replay vài event đã chọn trong sandbox.
5. Replay có kiểm soát vào topic hoặc quy trình xử lý riêng, đo duplicate effects.
6. Theo dõi backlog/DLQ sau thay đổi, cập nhật alert và runbook.

## 10. Exactly-once delivery: đúng phạm vi

Pub/Sub hỗ trợ **exactly-once delivery** cho **pull/StreamingPull subscriptions**, **không hỗ trợ push**. Theo điều kiện dịch vụ:

- Subscriber có thể **nhận phản hồi xác nhận ACK từ server**.
- Message **đã ACK thành công được xác nhận** sẽ không redeliver trong phạm vi bảo đảm.
- Khi message còn outstanding, không redeliver trước khi deadline hết.
- Nếu có nhiều deliveries vì hết deadline/nack, chỉ **ack ID của delivery mới nhất** hợp lệ.
- Bảo đảm có **giới hạn theo region**, nên cần dùng một regional endpoint phù hợp nếu subscriber phân tán đa region.
- Exactly-once có thêm quota và overhead; cần đo trước khi bật rộng.

| Tình huống | Exactly-once delivery có tự ngăn? |
|---|---|
| Redelivery sau ack **được xác nhận thành công** | **Có**, trong phạm vi bảo đảm |
| Worker commit DB rồi crash trước ack | **Không** |
| Publisher publish cùng event hai lần với **hai message IDs** | **Không** |
| Subscription chủ động `seek`/replay messages cũ | **Không**, replay có chủ đích |
| External API charge hai lần trước ack | **Không**, cần downstream idempotency |
| Push/HTTP subscription | **Không được hỗ trợ** |
| Các subscriber ở nhiều regions không thống nhất locational endpoint | Không được mặc định bảo đảm đầy đủ |

**Exactly-once delivery ≠ exactly-once business effect.** Luôn giữ unique constraint/transaction/outbox theo yêu cầu.

### 10.1. Ví dụ Java ack có xác nhận

Với `MessageReceiverWithAckResponse` và `AckReplyConsumerWithResponse`:

~~~java
MessageReceiverWithAckResponse receiver = (message, consumer) -> {
    // CHỈ SAU KHI đã commit nghiệp vụ bền vững.
    try {
        AckResponse response = consumer.ack().get();
        if (response == AckResponse.SUCCESSFUL) {
            System.out.println("ACK confirmed " + message.getMessageId());
        } else {
            System.err.println("ACK not confirmed: " + response);
        }
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        System.err.println("Interrupted while waiting for ACK");
    } catch (ExecutionException e) {
        System.err.println("ACK result unknown: " + e.getCause());
    }
};
~~~

Đoạn mã này là **phần receiver minh họa**, cần imports và tạo `Subscriber.newBuilder(subscription, receiver)`, subscription bật exactly-once. Blocking trên future thuận tiện để hiểu nhưng có thể giảm throughput; trong production xử lý completion bất đồng bộ, cần kế hoạch khi ack result lỗi/unknown.

### 10.2. Message ordering

Khi ordering bật và publisher gắn cùng ordering key:

- Pub/Sub giao messages của **cùng key** theo thứ tự trong điều kiện hỗ trợ.
- Khi một message redeliver, những message **sau cùng key** có thể cũng redeliver, kể cả đã ack, để duy trì thứ tự.
- Với **exactly-once + ordering**, ACK phải theo thứ tự; ACK ngoài thứ tự có thể lỗi tạm thời và gây redelivery.
- DLQ + ordering có ngoại lệ best-effort khi message được forward.

Không bật ordering cho mọi message nếu ứng dụng không cần thứ tự theo key; nó có thể giảm throughput và khiến một poison message ảnh hưởng các message phía sau.

## 11. Thực hành A — Quan sát ack deadline bằng gcloud

**Chỉ tạo và chạy trên project sandbox**; không dùng topic chung có consumer production.

### 11.1. Tạo topic và pull subscription

~~~bash
gcloud auth list
gcloud config get-value project

gcloud pubsub topics create orders-ack-lab \
  --project=PROJECT_ID

gcloud pubsub subscriptions create orders-ack-sub \
  --project=PROJECT_ID \
  --topic=orders-ack-lab \
  --ack-deadline=30

gcloud pubsub subscriptions describe orders-ack-sub \
  --project=PROJECT_ID
~~~

Kiểm tra `ackDeadlineSeconds` tương ứng. Nếu tên đã tồn tại, xác minh ownership; không xóa tài nguyên lạ để làm lab.

### 11.2. Publish và pull không auto-ack

~~~bash
gcloud pubsub topics publish orders-ack-lab \
  --project=PROJECT_ID \
  --message='{"eventId":"evt-001","orderId":"OD-42"}'

gcloud pubsub subscriptions pull orders-ack-sub \
  --project=PROJECT_ID \
  --limit=1
~~~

Ghi lại `MESSAGE_ID` và `ACK_ID` trong output. Các lệnh tiếp theo dùng **ACK_ID thực của delivery**, trước khi hết hạn nếu muốn thao tác trên delivery hiện tại.

**Ack thủ công:**

~~~bash
gcloud pubsub subscriptions ack orders-ack-sub \
  --project=PROJECT_ID \
  --ack-ids=ACK_ID
~~~

**Gia hạn delivery 120 giây:**

~~~bash
gcloud pubsub subscriptions modify-message-ack-deadline orders-ack-sub \
  --project=PROJECT_ID \
  --ack-ids=ACK_ID \
  --ack-deadline=120
~~~

**Nack / yêu cầu retry:**

~~~bash
gcloud pubsub subscriptions modify-message-ack-deadline orders-ack-sub \
  --project=PROJECT_ID \
  --ack-ids=ACK_ID \
  --ack-deadline=0
~~~

Thử bốn lần với **message riêng biệt**: ack kịp thời; để hết deadline; gia hạn trước rồi ack; nack ngay. Theo dõi `messageId`, từng `ackId` và thời gian redelivery. Không dùng `--auto-ack` khi muốn quan sát retry vì nó ack ngay khi pull.

## 12. Thực hành B — Retry backoff và dead lettering

### 12.1. Cấu hình exponential backoff

~~~bash
gcloud pubsub subscriptions update orders-ack-sub \
  --project=PROJECT_ID \
  --min-retry-delay=10s \
  --max-retry-delay=60s

gcloud pubsub subscriptions describe orders-ack-sub \
  --project=PROJECT_ID
~~~

Nếu nack, Pub/Sub có thể áp backoff trong phạm vi cấu hình. Không viết test kỳ vọng redelivery chính xác ở một giây cố định.

### 12.2. Tạo DLQ và subscription cho DLQ

~~~bash
gcloud pubsub topics create orders-ack-dlq \
  --project=PROJECT_ID

gcloud pubsub subscriptions create orders-ack-dlq-sub \
  --project=PROJECT_ID \
  --topic=orders-ack-dlq

gcloud pubsub subscriptions update orders-ack-sub \
  --project=PROJECT_ID \
  --dead-letter-topic=projects/PROJECT_ID/topics/orders-ack-dlq \
  --max-delivery-attempts=5
~~~

Lấy **project number**:

~~~bash
gcloud projects describe PROJECT_ID \
  --format="value(projectNumber)"
~~~

Cấp role cho Pub/Sub **service agent của project source subscription**; thay `PROJECT_NUMBER` thật (không phải runtime Java service account):

~~~bash
gcloud pubsub topics add-iam-policy-binding orders-ack-dlq \
  --project=PROJECT_ID \
  --member="serviceAccount:service-PROJECT_NUMBER@gcp-sa-pubsub.iam.gserviceaccount.com" \
  --role="roles/pubsub.publisher"

gcloud pubsub subscriptions add-iam-policy-binding orders-ack-sub \
  --project=PROJECT_ID \
  --member="serviceAccount:service-PROJECT_NUMBER@gcp-sa-pubsub.iam.gserviceaccount.com" \
  --role="roles/pubsub.subscriber"
~~~

Sau khi IAM có hiệu lực, thử **poison message** bằng subscriber demo để quan sát nack, attempts và eventual DLQ. **Đếm 5 lần là ngưỡng best effort**, không cam kết luôn đúng năm.

### 12.3. Cleanup sau lab

**Chỉ xóa các tài nguyên lab do bạn tạo và không còn consumer:**

~~~bash
gcloud pubsub subscriptions delete orders-ack-sub --project=PROJECT_ID
gcloud pubsub subscriptions delete orders-ack-dlq-sub --project=PROJECT_ID
gcloud pubsub topics delete orders-ack-lab --project=PROJECT_ID
gcloud pubsub topics delete orders-ack-dlq --project=PROJECT_ID
~~~

Xóa subscription có thể xóa backlog không còn khôi phục được theo đường thông thường; cần xác nhận trước khi dọn.

## 13. Monitoring và chẩn đoán redelivery

| Dấu hiệu | Metric / nguồn | Diễn giải |
|---|---|---|
| Backlog theo region | `subscription/num_unacked_messages_by_region` | Tốc độ xử lý không theo kịp publish, hoặc worker lỗi |
| Tuổi message cũ nhất | `subscription/oldest_unacked_message_age_by_region` | Có thể bị kẹt poison message/thiếu capacity |
| Pull ack deadline expired | `subscription/expired_ack_deadlines_count` | Chọn deadline/lease/flow-control chưa phù hợp |
| Push HTTP errors | `subscription/push_request_count` theo response code | Timeout, 401/403, 429 hoặc 5xx |
| Delivery latency health | `subscription/delivery_latency_health_score` | Tổng quan sức khỏe delivery |
| DLQ forwarding | `subscription/dead_letter_message_count` | Message lỗi chuyển khỏi subscription chính |
| Java processing time | p50/p95/p99 qua metrics của app | Cơ sở chọn deadline/lease |
| DB errors và dedup hits | Logs/tracing/DB metrics | Tìm downstream bottleneck và business duplicate |
| Chi phí và lưu trữ | Cloud Billing | Retry, backlog, retention và compute |

Ưu tiên metrics có hậu tố **`_by_region`** khi xây dashboard chống lỗi từng region. Backlog tăng cùng oldest age tăng → throughput xử lý thường không đủ; backlog nhỏ nhưng oldest age tăng → nghi poison message.

### 13.1. Bảng xử lý sự cố

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
|---|---|---|
| Cùng `messageId` nhận nhiều lần | Hết lease, nack hoặc ack failure | Expired deadlines, subscriber logs |
| Payload giống nhưng `messageId` khác | Publisher phát trùng | Business event ID, publisher retry |
| Java OOM | Quá nhiều messages outstanding | Flow control, heap, GC, thread pool |
| DB bị ghi trùng | Commit trước ack nhưng không idempotent | Unique constraint, DB transaction/outbox |
| Exactly-once ack trả `INVALID_ARGUMENT` | Ack ID cũ/hết hạn | Lease và ack response, delivery mới |
| Push 403 | Push auth service account thiếu Invoker/audience sai | Cloud Run IAM và OIDC token |
| Push chậm dù Cloud Run healthy | Push backoff hoặc quota | Push error count, retry config |
| DLQ trống dù nack nhiều | Thiếu agent IAM hoặc chưa đạt threshold | Pub/Sub service agent, DLQ config |
| Ordering key bị kẹt | Event trước cùng key chưa ack | Delivery attempts, DLQ, key-specific logs |
| Backlog mất sau thời gian dài | Retention hết/seek/delete | Subscription policy, backup/replay plan |

### 13.2. Runbook ngắn

1. Xác định **subscription, messageId/eventId, delivery type, region**.
2. Soi expired ack deadlines (pull) hoặc push HTTP response classes.
3. Xác định worker health, CPU/RAM, restart, processing p99 và DB latency.
4. Đối chiếu initial deadline với **lease manager max extension** và **flow control**.
5. Kiểm tra retry policy, DLQ IAM và poison messages.
6. Bảo vệ/kiểm tra durable idempotency **trước** khi replay backlog.
7. Sửa một nguyên nhân, test worker crash/DB failure trong sandbox, đo kết quả.
8. Điều chỉnh capacity/concurrency theo downstream giới hạn; cập nhật alert và runbook.

**Không sửa bằng cách ack trước commit, đặt deadline 600 giây cho mọi job hoặc xóa subscription đang có dữ liệu thật.**

## 14. Case study: Orders Worker trên GKE và Cloud SQL

**Tình huống giả định:** Java worker nhận `ORDER_CONFIRMED`, ghi Cloud SQL PostgreSQL rồi phát tín hiệu kho vận. Bình thường xử lý 1–4 giây, nhưng giờ cao điểm p99 lên 50–70 giây. Subscription có ack deadline 10 giây; GKE Pod OOM khi lấy quá nhiều outstanding messages.

**Vì sao lỗi lan rộng?** Lease không đủ hoặc client quá tải → redelivery → hai worker xử lý cùng event → DB ghi trùng do thiếu unique constraint → tăng DB load → càng chậm → backlog và Pub/Sub costs tăng.

**Kế hoạch sửa theo thứ tự:**

1. Thêm `eventId` ổn định; unique constraint cho consumer + event.
2. Transaction ghi marker và state rồi **commit trước ack**; external side effects qua outbox.
3. Bật/high-level lease management và điều chỉnh theo p99, có max processing timeout.
4. Giới hạn outstanding messages, Java concurrency và Cloud SQL connection pool.
5. Retry exponential backoff cho lỗi tạm thời; DLQ cho message schema sai.
6. Kiểm tra IAM của Pub/Sub service agent đối với DLQ; bật metrics/alerts.
7. Diễn tập **crash sau DB commit trước ack**, xác minh redelivery **không tạo thêm order**.
8. Nếu muốn exactly-once, kiểm tra regional endpoint/ack result; giữ idempotency.

Đây là **bài toán tính đúng đắn hệ thống**, không phải chỉ tăng CPU hoặc nâng giới hạn ack.

## 15. Bài tập và tự đánh giá

### Bài 1 — Hết deadline

Subscription deadline 10 giây, Java worker chạy 45 giây và không gia hạn; worker khác nhận lại cùng message. **Đây có phải lỗi Pub/Sub không?** Nêu hai cách giảm hiện tượng.

**Gợi ý:** Không; dùng automatic lease extension hoặc right-size deadline và flow control.

### Bài 2 — Ack ID khác message ID

A nhận `messageId=M42, ackId=A1`; sau hết deadline, B nhận `messageId=M42, ackId=B2`. **B dùng giá trị nào để ack?** Nên log key nào để xác định redelivery?

**Gợi ý:** `B2` là token ack mới; `M42` giúp theo dõi delivery của cùng một message.

### Bài 3 — Ack trước DB commit

Java gọi `ack()` trước khi INSERT order. Worker crash sau ack nhưng trước INSERT. **Có thể mất công việc không?** Đổi thứ tự thế nào?

**Gợi ý:** Có; commit bền vững trước ack.

### Bài 4 — Nack và retry nóng

Message có JSON sai vĩnh viễn, subscriber luôn nack, retry immediate, không DLQ. **Điều gì xảy ra với throughput và hóa đơn?** Đề xuất guardrails.

**Gợi ý:** Poison loop gây redelivery và chi phí; validation, DLQ, retry backoff, alert.

### Bài 5 — Push và 202 Accepted

Cloud Run push handler trả `202` rồi chỉ lưu dữ liệu trong RAM để xử lý sau. **Pub/Sub coi đã ack chưa?** Nếu instance bị hủy thì sao?

**Gợi ý:** Đã ack; dữ liệu có thể mất. Chỉ 2xx sau durable enqueue/commit.

### Bài 6 — Exactly-once

Subscription pull bật exactly-once. Worker commit DB rồi crash trước ack; publisher còn gửi một business event tương đương với message ID khác. **Có thể double charge không?**

**Gợi ý:** Có; exactly-once không bảo đảm business transaction xuyên hệ thống, cần idempotency.

### Bài 7 — DLQ best effort

`maxDeliveryAttempts=5`, message xuất hiện 6 lần mới đi DLQ. **Có phải vi phạm bảo đảm không?** Kiểm tra IAM nào nếu không có DLQ message?

**Gợi ý:** Best effort; Pub/Sub service agent cần Publisher trên DLQ topic và Subscriber trên source subscription.

### Bài 8 — Ordering key

A1, A2, A3 cùng ordering key. A2 redeliver. **A3 có thể redeliver dù đã ack không?** Khi nào ordering là quá mức cần thiết?

### Bài 9 — Tối ưu worker

Java worker 8 threads nhưng nhận 10.000 outstanding messages, p99 processing 35 giây, ack expirations tăng. Đề xuất **flow control, lease settings, DB tuning, DLQ, idempotency và metrics**.

### Bài 10 — Thiết kế kịch bản thử

Hãy thiết kế test chứng minh xử lý một order **chỉ một lần về mặt nghiệp vụ** khi: (a) worker OOM, (b) ack network failure, (c) publisher publish duplicate, (d) replay từ DLQ. Nêu bằng chứng cần lưu.

## 16. Checklist trước production

- [ ] Xác định pull/StreamingPull hay push, yêu cầu latency và số lượng messages.
- [ ] Phân biệt **ack deadline, retention và retry backoff**.
- [ ] Initial deadline phù hợp p95/p99, high-level lease manager được cấu hình/giám sát.
- [ ] **Ack sau DB commit/durable processing**, không ack sớm.
- [ ] Có durable idempotency cho **redelivery và publisher duplication**.
- [ ] Có max outstanding messages/bytes, giới hạn concurrency và DB connection pool.
- [ ] Retry backoff và push backoff được hiểu riêng, có alert khi lỗi.
- [ ] DLQ có topic, subscriber, service agent IAM và runbook replay.
- [ ] Hiểu delivery attempts là **best effort**, không dựa vào N tuyệt đối.
- [ ] Exactly-once chỉ áp cho pull, đã thử ack confirmation và regional constraints.
- [ ] Nếu bật ordering, đã kiểm tra redelivery messages phía sau cùng key.
- [ ] Push endpoint có authentication, trả success **sau durable enqueue**.
- [ ] Có dashboards về backlog regional, oldest age, expired ack deadlines, push errors và DLQ.
- [ ] Diễn tập worker crash, downstream timeout, poison message, duplicate và replay.
- [ ] Đã tính chi phí Pub/Sub traffic, retention, compute, logs, redeliveries.
- [ ] Cleanup sandbox đúng tài nguyên, không xóa subscription có dữ liệu cần giữ.

## 17. Tài liệu chính thức

Đối chiếu giới hạn/flags/client versions hiện hành trước khi triển khai:

- [Pub/Sub — Subscription properties](https://docs.cloud.google.com/pubsub/docs/subscription-properties)
- [Pub/Sub — Lease management](https://docs.cloud.google.com/pubsub/docs/lease-management)
- [Pub/Sub — Pull subscriptions](https://docs.cloud.google.com/pubsub/docs/pull-messages)
- [Pub/Sub — Push subscriptions](https://docs.cloud.google.com/pubsub/docs/push)
- [Pub/Sub — Retry policy](https://docs.cloud.google.com/pubsub/docs/subscription-retry-policy)
- [Pub/Sub — Dead-letter topics](https://docs.cloud.google.com/pubsub/docs/dead-letter-topics)
- [Pub/Sub — Exactly-once delivery](https://docs.cloud.google.com/pubsub/docs/exactly-once-delivery)
- [Pub/Sub — Message ordering](https://docs.cloud.google.com/pubsub/docs/ordering)
- [Pub/Sub — Monitoring](https://docs.cloud.google.com/pubsub/docs/monitoring)
- [Pub/Sub — Troubleshooting pull](https://docs.cloud.google.com/pubsub/docs/pull-troubleshooting)
- [Pub/Sub — Troubleshooting push](https://docs.cloud.google.com/pubsub/docs/push-troubleshooting)
- [Google Cloud Pub/Sub Java client library](https://docs.cloud.google.com/java/docs/reference/google-cloud-pubsub/latest/overview)
- [gcloud pubsub subscriptions](https://docs.cloud.google.com/sdk/gcloud/reference/pubsub/subscriptions)
- [Pub/Sub pricing](https://cloud.google.com/pubsub/pricing)

**Điểm cần nhớ:** **Ack deadline** là thời gian chờ xác nhận **một delivery**, không phải retention. Pull worker có thể gia hạn lease; push phải trả HTTP success trong deadline. Message chưa ack/nack có thể **redeliver**; retry backoff và DLQ giúp quản lý lỗi nhưng **không thay durable idempotency**. Đối với Java xử lý dữ liệu quan trọng, thứ tự an toàn là **commit bền vững → ack**, giám sát backlog/ack expirations và diễn tập worker crash/replay — kể cả khi bật exactly-once delivery.
