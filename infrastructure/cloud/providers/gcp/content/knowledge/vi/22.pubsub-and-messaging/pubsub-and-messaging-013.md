# Thực hành publisher và subscriber Java có xử lý trùng trong Pub/Sub

Giả sử dịch vụ `orders-api` trên Cloud Run phát sự kiện **OrderPaid** vào Pub/Sub. Worker Java chạy trên GKE nhận sự kiện để tạo phiếu giao hàng trong Cloud SQL PostgreSQL. Có hai tình huống dễ tạo phiếu trùng:

1. Publisher đã gửi thành công nhưng mất response, nên gửi lại **cùng sự kiện nghiệp vụ** thành một Pub/Sub message khác.
2. Subscriber đã **COMMIT** database nhưng crash trước khi ACK, nên Pub/Sub có thể giao lại message cũ.

Bài thực hành xây dựng **publisher, pull subscriber và bộ lưu dấu xử lý trùng**. Mục tiêu không phải chỉ in “received message”, mà chứng minh **hai message cùng `eventId` chỉ tạo một shipping task**.

Đây là bài thuộc chương **Pub/Sub và thông điệp**, mô-đun `CLOUD_PROVIDERS_GCP`. Kỹ thuật có thể áp dụng cho các ứng dụng Java trên Compute Engine, GKE hoặc Cloud Run kết hợp IAM, VPC, Cloud SQL, Cloud Storage, tự động hóa phát hành, giám sát độ tin cậy và chi phí. Phần thực hành sử dụng project và database **lab**, không thay đổi tài nguyên production.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Viết publisher Java gửi `PubsubMessage` với `eventId` ổn định.
- Viết subscriber Java nhận message, thực hiện transaction PostgreSQL, **ACK sau COMMIT** và NACK khi gặp lỗi tạm thời.
- Phân biệt `messageId` của Pub/Sub với `eventId` của ứng dụng.
- Dùng unique constraint để xử lý duplicate ngay cả khi có **nhiều worker replicas**.
- Chạy hai lần publish cùng event và xác minh database chỉ có một shipping task.
- Phân tích redelivery do ack deadline/crash, confirmed ACK và giới hạn của exactly-once delivery.
- Theo dõi backlog, retry, IAM, bảo mật thông tin và chi phí.

## 1. Kiến trúc và ranh giới bảo đảm

~~~mermaid
flowchart LR
    P["Java Publisher<br/>eventId ổn định"] -->|"publish"| TOPIC["Topic: orders-events-lab"]
    TOPIC --> SUB["Pull subscription<br/>orders-worker-lab"]
    SUB --> W["Java Subscriber<br/>transaction + ACK"]
    W --> DB[("PostgreSQL<br/>processed_events + shipping_tasks")]
    W -. "NACK / chưa ACK" .-> SUB
    DB --> OBS["Kiểm tra số rows + metrics"]
~~~

**At-least-once** là mặc định: một Pub/Sub message có thể được giao lại. **Exactly-once delivery** của Pub/Sub chỉ có thể bật cho **pull/StreamingPull**, theo bảo đảm trong **cùng region**; nó không hợp nhất các lần publish khác nhau và **không tạo transaction xuyên Pub/Sub và PostgreSQL**.

| Định danh | Ai cấp? | Dùng để làm gì? |
| --- | --- | --- |
| `eventId=order-paid:LAB-1:v1` | Ứng dụng, trước lần publish đầu tiên | Nhận diện **cùng sự kiện nghiệp vụ** qua publisher retries |
| `messageId` | Pub/Sub sau mỗi lần publish được chấp nhận | Nhận diện một Pub/Sub message, ổn định khi message đó được redeliver |
| `ackId` | Pub/Sub cho **mỗi lần giao pull** | ACK/NACK một delivery; có thể đổi sau redelivery |
| `orderId=LAB-1` | Hệ thống nghiệp vụ | Xác định đơn hàng, không nhất thiết đủ để dedupe mọi event của đơn |

**Quy tắc thiết kế:** subscriber dedupe theo **eventId** hoặc khóa nghiệp vụ phù hợp, **không chỉ messageId**. Hai publishes riêng của cùng event thường có hai `messageId` khác nhau.

## 2. Điều kiện lab và IAM

Cần Java 21, Maven 3.9+, Google Cloud CLI, project có billing/API Pub/Sub, PostgreSQL 16 (local hoặc Cloud SQL được phép) và quyền tạo tài nguyên trong **project lab**. Các đoạn shell dùng **Bash**; trên PowerShell, chuyển `export NAME=value` thành `$env:NAME="value"`.

Danh tính:

| Người/tiến trình | Quyền tối thiểu cần xem xét |
| --- | --- |
| Người thiết lập lab | Quyền tạo topic/subscription thích hợp |
| Publisher identity | `roles/pubsub.publisher` trên topic |
| Subscriber identity | `roles/pubsub.subscriber` trên subscription |
| Worker truy cập Cloud SQL | Quyền kết nối DB phù hợp, database user/role chỉ đọc-ghi bảng cần thiết |
| Production deployer | Quyền triển khai GKE/VM/Cloud Run tương ứng, tách khỏi runtime identity |

Trên máy local, dùng **Application Default Credentials (ADC)**:

~~~bash
gcloud auth application-default login
gcloud auth application-default set-quota-project PROJECT_ID

gcloud services enable pubsub.googleapis.com --project=PROJECT_ID
~~~

**Không đưa service account JSON keys vào repository.** Trên GKE dùng Workload Identity Federation for GKE; trên Compute Engine dùng service account gắn VM; trên Cloud Run dùng runtime service account. Với Cloud SQL production, ưu tiên Cloud SQL connector/Auth Proxy, TLS và Secret Manager/IAM database authentication theo yêu cầu.

### 2.1. Tạo topic và pull subscription

~~~bash
gcloud pubsub topics create orders-events-lab \
  --project=PROJECT_ID

gcloud pubsub subscriptions create orders-worker-lab \
  --topic=orders-events-lab \
  --ack-deadline=30 \
  --project=PROJECT_ID

gcloud pubsub subscriptions describe orders-worker-lab \
  --project=PROJECT_ID \
  --format="yaml(name,topic,ackDeadlineSeconds,enableExactlyOnceDelivery)"
~~~

**Các lệnh `create` có tác động thật và có thể phát sinh phí.** Nếu resource trùng tên đã tồn tại, xác minh chủ sở hữu thay vì xóa/ghi đè. Lab ban đầu sử dụng **at-least-once**, không cần bật exactly-once để chứng minh idempotency.

## 3. Cấu trúc Maven project

Để thử, tạo các file sau **trong một thư mục lab riêng trên máy của người học**:

~~~text
pubsub-java-lab/
├── pom.xml
└── src/main/java/lab/pubsub/
    ├── PublishOrder.java
    └── ConsumeOrder.java
~~~

Bài cung cấp toàn bộ nội dung hai Java classes; code minh họa thao tác vào PostgreSQL đơn giản bằng JDBC, không dùng Spring Boot để người học thấy rõ điểm **COMMIT trước ACK**.

### 3.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>lab.pubsub</groupId>
  <artifactId>pubsub-java-lab</artifactId>
  <version>1.0.0</version>

  <properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
    <dependency>
      <groupId>org.postgresql</groupId>
      <artifactId>postgresql</artifactId>
      <version>42.7.14</version>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.0</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.6.4</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Cloud Java BOM quản lý phiên bản Pub/Sub và các thư viện Google liên quan. Phiên bản ở đây là **mốc ví dụ đã xác minh**, không phải yêu cầu khóa vô thời hạn; production cần cập nhật và quét phụ thuộc theo chính sách.

## 4. PostgreSQL: marker xử lý trùng và business effect chung transaction

Tạo hai bảng:

~~~sql
CREATE TABLE IF NOT EXISTS processed_events (
    consumer_name TEXT NOT NULL,
    event_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);

CREATE TABLE IF NOT EXISTS shipping_tasks (
    event_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    status TEXT NOT NULL
);
~~~

**Hai bảng nằm trong cùng database** để có thể commit nguyên tử:

1. Thử `INSERT` vào `processed_events` với khóa `(consumer_name, event_id)`.
2. Nếu **thêm được**, tạo một row `shipping_tasks`.
3. Nếu **đã tồn tại**, không tạo task lần nữa.
4. `COMMIT` cả marker và task; **chỉ sau đó mới ACK Pub/Sub**.

Unique constraint hoạt động ngay cả khi hai subscribers xử lý đồng thời. Một Java `HashSet` trong RAM **không đủ**, vì mỗi Pod/VM có bộ nhớ riêng và restart làm mất cache.

### 4.1. PostgreSQL cục bộ phục vụ lab

Nếu máy có Docker và chưa có PostgreSQL lab riêng:

~~~bash
docker run -d --rm --name orders-pg-lab \
  -e POSTGRES_PASSWORD=lab-only-change-me \
  -e POSTGRES_DB=orders_lab \
  -p 127.0.0.1:5432:5432 \
  postgres:16
~~~

Dùng:

~~~bash
docker exec -it orders-pg-lab psql -U postgres -d orders_lab
~~~

Tại prompt `psql`, chạy hai câu `CREATE TABLE` ở trên, rồi gõ `\q`. Mật khẩu `lab-only-change-me` **chỉ dành cho container thử nghiệm trên loopback**, không phải giá trị production.

Thiết lập biến môi trường trong terminal sẽ chạy subscriber:

~~~bash
export JDBC_URL="jdbc:postgresql://127.0.0.1:5432/orders_lab"
export DB_USER="postgres"
export DB_PASSWORD="lab-only-change-me"
~~~

Production không dùng database user `postgres`, không lưu password cố định trong scripts và không mở public database; sử dụng DB principal giới hạn quyền cùng secret injection.

## 5. Publisher Java: eventId phải ổn định qua retries

File `src/main/java/lab/pubsub/PublishOrder.java`:

~~~java
package lab.pubsub;

import com.google.api.core.ApiFuture;
import com.google.cloud.pubsub.v1.Publisher;
import com.google.protobuf.ByteString;
import com.google.pubsub.v1.PubsubMessage;
import com.google.pubsub.v1.TopicName;
import java.util.concurrent.TimeUnit;

public class PublishOrder {
    public static void main(String[] args) throws Exception {
        if (args.length != 4) {
            throw new IllegalArgumentException(
                "Usage: PROJECT_ID TOPIC_ID EVENT_ID ORDER_ID");
        }
        String eventId = args[2];
        String orderId = args[3];
        if (eventId.isBlank() || orderId.isBlank()) {
            throw new IllegalArgumentException("IDs must not be blank");
        }

        TopicName topic = TopicName.of(args[0], args[1]);
        Publisher publisher = Publisher.newBuilder(topic).build();
        try {
            PubsubMessage message = PubsubMessage.newBuilder()
                .setData(ByteString.copyFromUtf8("OrderPaid"))
                .putAttributes("eventId", eventId)
                .putAttributes("orderId", orderId)
                .build();

            ApiFuture<String> future = publisher.publish(message);
            String messageId = future.get(30, TimeUnit.SECONDS);
            System.out.println("publish confirmed, messageId=" + messageId
                + ", eventId=" + eventId);
        } finally {
            publisher.shutdown();
            publisher.awaitTermination(1, TimeUnit.MINUTES);
        }
    }
}
~~~

**Điểm quan trọng:** `future.get()` cho biết kết quả publish mà client nhận được. Nếu request đến Pub/Sub nhưng response bị mất, publisher có thể không biết message đã được chấp nhận; gọi lại chương trình với **cùng EVENT_ID** tạo publish khác nhưng vẫn là **một sự kiện nghiệp vụ** theo logic dedupe.

Code dùng `eventId` và `orderId` trong message **attributes** để đơn giản hóa lab. Khi dùng JSON/Avro/Protobuf thực tế, định nghĩa schema, validation và version rõ ràng; không tin attributes bên ngoài nếu chưa xác thực nguồn.

## 6. Subscriber Java: commit một lần, sau đó ACK

File `src/main/java/lab/pubsub/ConsumeOrder.java`:

~~~java
package lab.pubsub;

import com.google.cloud.pubsub.v1.AckReplyConsumerWithResponse;
import com.google.cloud.pubsub.v1.AckResponse;
import com.google.cloud.pubsub.v1.MessageReceiverWithAckResponse;
import com.google.cloud.pubsub.v1.Subscriber;
import com.google.pubsub.v1.ProjectSubscriptionName;
import com.google.pubsub.v1.PubsubMessage;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.concurrent.TimeUnit;

public class ConsumeOrder {
    private static final String CONSUMER = "shipping-worker";

    public static void main(String[] args) {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                "Usage: PROJECT_ID SUBSCRIPTION_ID");
        }

        String url = requiredEnv("JDBC_URL");
        String user = requiredEnv("DB_USER");
        String password = requiredEnv("DB_PASSWORD");

        MessageReceiverWithAckResponse receiver =
            (PubsubMessage msg, AckReplyConsumerWithResponse reply) -> {
                String eventId = msg.getAttributesOrDefault("eventId", "");
                String orderId = msg.getAttributesOrDefault("orderId", "");

                if (!"OrderPaid".equals(msg.getData().toStringUtf8())
                        || eventId.isBlank() || orderId.isBlank()) {
                    System.err.println("Invalid event, messageId="
                        + msg.getMessageId());
                    // Production: cấu hình DLQ/quarantine cho poison messages.
                    reply.nack();
                    return;
                }

                boolean created;
                try {
                    created = persistOnce(url, user, password, eventId, orderId);
                } catch (SQLException error) {
                    System.err.println("DB transaction failed, messageId="
                        + msg.getMessageId() + ", retry later");
                    reply.nack(); // Không ACK nếu transaction lỗi.
                    return;
                }

                System.out.println((created ? "CREATED" : "DUPLICATE_SKIPPED")
                    + " eventId=" + eventId
                    + " messageId=" + msg.getMessageId());

                // Lúc này transaction đã COMMIT. Không NACK nếu chỉ ACK lỗi.
                try {
                    AckResponse result = reply.ack().get(30, TimeUnit.SECONDS);
                    System.out.println("ACK result=" + result
                        + " messageId=" + msg.getMessageId());
                    if (result != AckResponse.SUCCESSFUL) {
                        System.err.println("ACK chưa được xác nhận");
                    }
                } catch (Exception error) {
                    System.err.println("ACK outcome uncertain; dedupe"
                        + " sẽ bảo vệ nếu message được giao lại");
                    if (error instanceof InterruptedException) {
                        Thread.currentThread().interrupt();
                    }
                }
            };

        ProjectSubscriptionName sub =
            ProjectSubscriptionName.of(args[0], args[1]);

        Subscriber.Builder builder = Subscriber.newBuilder(sub, receiver);
        // Optional: pin endpoint khi dùng exactly-once trong một region.
        String endpoint = System.getenv("PUBSUB_ENDPOINT");
        if (endpoint != null && !endpoint.isBlank()) {
            builder.setEndpoint(endpoint);
        }

        Subscriber subscriber = builder.build();
        Runtime.getRuntime().addShutdownHook(
            new Thread(() -> subscriber.stopAsync()));

        subscriber.startAsync().awaitRunning();
        System.out.println("Listening on " + sub);
        subscriber.awaitTerminated();
    }

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing env: " + name);
        }
        return value;
    }

    private static boolean persistOnce(
        String url, String user, String password,
        String eventId, String orderId) throws SQLException {

        try (Connection db =
                 DriverManager.getConnection(url, user, password)) {
            db.setAutoCommit(false);
            try {
                int inserted;
                try (PreparedStatement p = db.prepareStatement(
                    "INSERT INTO processed_events "
                    + "(consumer_name, event_id, order_id) "
                    + "VALUES (?, ?, ?) ON CONFLICT DO NOTHING")) {
                    p.setString(1, CONSUMER);
                    p.setString(2, eventId);
                    p.setString(3, orderId);
                    inserted = p.executeUpdate();
                }

                if (inserted == 0) {
                    // Không silently ignore khi cùng ID mang payload khác.
                    try (PreparedStatement p = db.prepareStatement(
                        "SELECT order_id FROM processed_events "
                        + "WHERE consumer_name=? AND event_id=?")) {
                        p.setString(1, CONSUMER);
                        p.setString(2, eventId);
                        try (ResultSet rs = p.executeQuery()) {
                            if (!rs.next() || !orderId.equals(rs.getString(1))) {
                                throw new SQLException(
                                    "Reused eventId with different orderId");
                            }
                        }
                    }
                    db.commit();
                    return false;
                }

                try (PreparedStatement p = db.prepareStatement(
                    "INSERT INTO shipping_tasks "
                    + "(event_id, order_id, status) VALUES (?, ?, ?)")) {
                    p.setString(1, eventId);
                    p.setString(2, orderId);
                    p.setString(3, "READY");
                    p.executeUpdate();
                }

                db.commit(); // Marker + shipping task cùng COMMIT.
                return true;
            } catch (SQLException error) {
                db.rollback();
                throw error;
            }
        }
    }
}
~~~

### 6.1. Vì sao code này chống trùng?

| Điểm lỗi | Trạng thái database | Khi Pub/Sub giao lại |
| --- | --- | --- |
| Crash trước transaction | Chưa có gì | Xử lý bình thường |
| Crash sau chèn marker nhưng trước COMMIT | PostgreSQL rollback transaction | Xử lý bình thường |
| Crash sau COMMIT, trước ACK | Có cả marker và shipping task | `DUPLICATE_SKIPPED` rồi ACK |
| Publisher publish hai Pub/Sub messages cùng `eventId` | Chỉ transaction đầu thêm được marker | Message thứ hai bỏ qua business effect |
| Hai workers cùng xử lý một event | Unique constraint điều phối tại DB | Một transaction thắng, một transaction thấy duplicate |

**Giới hạn:** giao dịch này chỉ bảo vệ **hai bảng trong cùng PostgreSQL**. Nếu gọi API thanh toán, gửi email hoặc ghi vào hệ thống ngoài, bạn cần **idempotency key ở bên nhận**, transactional outbox/saga hoặc bước đối soát; không thể dùng `COMMIT` của PostgreSQL để làm cho HTTP call bên ngoài thành atomic.

### 6.2. ACK response có ý nghĩa gì?

`AckReplyConsumerWithResponse.ack()` trả future chứa `AckResponse`. Khi subscription **bật exactly-once** và ACK được xác nhận thành công, Pub/Sub bảo đảm message đó không bị giao lại **trong phạm vi region hỗ trợ**. Với subscription at-least-once mặc định, future có thể trả thành công ngay mà **không** mang cùng ý nghĩa confirmed ACK phía server.

Ngay cả khi ACK đã được xác nhận, **hai publishes khác nhau** mang cùng business event vẫn có thể đến. Vì vậy bảng dedupe là thành phần bắt buộc, không phải biện pháp dự phòng chỉ khi tắt exactly-once.

## 7. Chạy end-to-end

Mở ba terminal: **PostgreSQL**, **subscriber**, **publisher**. Bảo đảm database đã có hai bảng ở mục 4 và ứng dụng đã lấy ADC. Trong thư mục `pubsub-java-lab`:

~~~bash
mvn -B -ntp -DskipTests compile
~~~

**Terminal subscriber** (sau khi thiết lập `JDBC_URL`, `DB_USER`, `DB_PASSWORD`):

~~~bash
mvn -q exec:java \
  -Dexec.mainClass=lab.pubsub.ConsumeOrder \
  -Dexec.args="PROJECT_ID orders-worker-lab"
~~~

**Terminal publisher**:

~~~bash
mvn -q exec:java \
  -Dexec.mainClass=lab.pubsub.PublishOrder \
  -Dexec.args="PROJECT_ID orders-events-lab order-paid:LAB-1:v1 LAB-1"
~~~

Output có thể tương tự:

~~~text
Publisher: publish confirmed, messageId=123456789, eventId=order-paid:LAB-1:v1

Subscriber: CREATED eventId=order-paid:LAB-1:v1 messageId=123456789
Subscriber: ACK result=SUCCESSFUL messageId=123456789
~~~

`messageId` trên chỉ là ví dụ. Nếu subscription mặc định không bật exactly-once, kết quả `SUCCESSFUL` của client **không đồng nghĩa bảo đảm ACK confirmed như exactly-once**.

### 7.1. Kiểm tra database

~~~sql
SELECT event_id, order_id, status
FROM shipping_tasks
ORDER BY event_id;

SELECT consumer_name, event_id, order_id, processed_at
FROM processed_events
ORDER BY processed_at;
~~~

Kỳ vọng **một row** cho `order-paid:LAB-1:v1` trong mỗi bảng.

## 8. Thử publisher duplicate có thể tái hiện

**Chạy lại đúng lệnh publisher**, giữ nguyên `eventId` và `orderId`:

~~~bash
mvn -q exec:java \
  -Dexec.mainClass=lab.pubsub.PublishOrder \
  -Dexec.args="PROJECT_ID orders-events-lab order-paid:LAB-1:v1 LAB-1"
~~~

Pub/Sub có thể cấp **messageId mới** vì đây là **lần publish thứ hai**. Subscriber sẽ thấy:

~~~text
DUPLICATE_SKIPPED eventId=order-paid:LAB-1:v1 messageId=987654321
ACK result=SUCCESSFUL messageId=987654321
~~~

Chạy SQL kiểm tra số rows:

~~~sql
SELECT count(*) AS tasks
FROM shipping_tasks
WHERE event_id = 'order-paid:LAB-1:v1';

SELECT count(*) AS markers
FROM processed_events
WHERE consumer_name = 'shipping-worker'
  AND event_id = 'order-paid:LAB-1:v1';
~~~

**Kỳ vọng:** `tasks=1` và `markers=1` sau **cả hai lần publish**. Đây là bài kiểm thử chắc chắn hơn việc chờ Pub/Sub ngẫu nhiên redeliver.

### 8.1. Đừng đổi nội dung rồi giữ nguyên ID

Nếu cùng `eventId` nhưng `orderId` khác, code trả lỗi SQL và NACK (không silently bỏ sự kiện). Trong hệ thống thực, đó có thể là bug publisher hoặc payload tampering: cần log an toàn, điều tra và đưa vào quarantine/DLQ theo chính sách. Không tạo vô hạn retry bằng cách tiếp tục publish payload sai.

## 9. Thử redelivery khi chưa ACK

Để quan sát **at-least-once redelivery**, **dừng Java subscriber trước** (Ctrl+C) rồi publish một `eventId` mới. Dùng lệnh pull thử nghiệm **không có `--auto-ack`**:

~~~bash
gcloud pubsub topics publish orders-events-lab \
  --message="OrderPaid" \
  --attribute="eventId=order-paid:LAB-2:v1,orderId=LAB-2" \
  --project=PROJECT_ID

gcloud pubsub subscriptions pull orders-worker-lab \
  --limit=1 --project=PROJECT_ID
~~~

Không gửi ACK. Sau khi **ack deadline hết**, tiếp tục pull để quan sát message có thể được giao lại:

~~~bash
gcloud pubsub subscriptions pull orders-worker-lab \
  --limit=1 --project=PROJECT_ID
~~~

Thời điểm redelivery **không phải đồng hồ 30 giây chính xác**: retry policy, backoff và tình trạng subscription có thể làm lệch. Sau khi thử, khởi động lại Java subscriber để xử lý rồi ACK. Không dùng `--auto-ack` nếu đang kiểm tra redelivery.

**Thử crash sau COMMIT trước ACK** đòi hỏi fault injection ở môi trường riêng. Nếu chủ động dừng process ngay sau COMMIT, marker đã bền vững nên lần giao sau chỉ ACK và không tạo task khác. Đừng tạo fault injection trên workload sản xuất hoặc giết pod đang xử lý giao dịch thật.

## 10. Bật exactly-once khi nào?

Có thể tạo **một pull subscription khác** cho lab để so sánh (không thay đổi subscription đang chạy):

~~~bash
gcloud pubsub subscriptions create orders-worker-exactly-lab \
  --topic=orders-events-lab \
  --enable-exactly-once-delivery \
  --ack-deadline=60 \
  --project=PROJECT_ID
~~~

Dùng cùng Java subscriber nhưng đổi subscription ID và chọn **một region** cho tất cả subscribers:

~~~bash
export PUBSUB_ENDPOINT="asia-southeast1-pubsub.googleapis.com:443"

mvn -q exec:java \
  -Dexec.mainClass=lab.pubsub.ConsumeOrder \
  -Dexec.args="PROJECT_ID orders-worker-exactly-lab"
~~~

**Phạm vi bảo đảm:** exactly-once chỉ cho **pull/StreamingPull** với các subscribers kết nối **cùng region**. Có thể nhận redelivery hợp lệ nếu NACK hoặc deadline hết; ACK ID cũ có thể bị từ chối. Exactly-once **không** hỗ trợ Pub/Sub push subscription vào Cloud Run HTTP service và **không** ngăn publisher publish hai messages khác ID cho cùng nghiệp vụ.

**Cảnh báo khi dùng hai subscriptions trên cùng topic:** mỗi subscription có delivery state riêng. Nếu chạy **hai Java consumers cùng xử lý cùng bảng**, consumer thứ hai có thể thấy `DUPLICATE_SKIPPED`; đó là kết quả đúng của dedupe toàn nghiệp vụ, không phải lỗi của subscription. Để so sánh riêng throughput/ACK semantics, dùng dữ liệu/bảng độc lập hoặc dọn lab có kiểm soát.

## 11. Các tình huống lỗi phải xử lý khác nhau

| Trường hợp | Kết quả đúng | Không nên làm |
| --- | --- | --- |
| Database timeout trước COMMIT | Rollback; NACK/đợi retry | ACK trước khi DB hoàn tất |
| Commit xong nhưng ACK future lỗi | Log ACK không chắc chắn; redelivery dùng marker | Xóa marker hoặc ghi business effect lần nữa |
| Hai publishes cùng `eventId` | Một row; message sau bỏ qua | Dedupe chỉ theo messageId |
| Payload thiếu `eventId` | Quarantine/DLQ, cảnh báo theo event source | NACK vô hạn không có giới hạn |
| Same eventId, different orderId | Chặn và điều tra conflict | Silently bỏ payload bất thường |
| Subscriber không có quyền | Sửa IAM rồi retry | Cấp Editor toàn project |
| Database mất kết nối kéo dài | Alert backlog/oldest age, giảm tốc nhận | Tăng số workers vô hạn |
| Tăng số Pod từ 1 lên 10 | Unique index vẫn chặn trùng | Dùng Java local `HashSet` |
| Pub/Sub message bị replay theo `seek` | Dedupe dựa trên retention của markers/business rules | Giả định ACK cũ ngăn mọi replay |
| Có email/payment API ngoài DB | Outbox/idempotency key/reconcile | Khẳng định transaction JDBC bao trùm API ngoài |

### 11.1. Lưu ý publisher-side outbox

Nếu Orders API cập nhật đơn thành `PAID` trong Cloud SQL rồi crash **trước khi publish**, sự kiện có thể bị mất. Mẫu **transactional outbox** lưu đồng thời thay đổi đơn hàng và record sự kiện trong cùng transaction, sau đó một relay publish với `eventId` ổn định. Relay có thể publish lại nếu mất response; chính consumer idempotent ở bài này xử lý trường hợp đó.

~~~mermaid
flowchart LR
    TX["DB transaction: order PAID + outbox row"]
    TX --> RELAY["Publisher relay<br/>retry cùng eventId"]
    RELAY --> PUB["Pub/Sub"]
    PUB --> INBOX["Consumer DB transaction<br/>unique processed_events"]
    INBOX --> TASK["Một shipping task"]
~~~

## 12. Concurrency và tuning khi đưa vào GKE/VM

Ví dụ mở **một JDBC connection cho mỗi message** để dễ thấy transaction. Production nên dùng connection pool có giới hạn (như HikariCP), validation và timeouts; không tạo quá nhiều Cloud SQL connections khi autoscale.

Một số tham số Subscriber Builder có thể chỉnh:

~~~java
// Trích đoạn tùy chọn trong quá trình tạo Subscriber.
import com.google.api.gax.batching.FlowControlSettings;

FlowControlSettings flow = FlowControlSettings.newBuilder()
    .setMaxOutstandingElementCount(100L)
    .setMaxOutstandingRequestBytes(10L * 1024 * 1024)
    .build();

Subscriber subscriber = Subscriber.newBuilder(sub, receiver)
    .setFlowControlSettings(flow)
    .build();
~~~

**Đây là đoạn thay thế cho phần builder trong class**, không dán thành Java class thứ ba. Nếu muốn vừa đặt `PUBSUB_ENDPOINT` vừa đặt flow control, gọi **cả hai setters trên cùng một builder** rồi `build()` một lần.

| Tham số | Điều cần cân bằng |
| --- | --- |
| `maxOutstandingElementCount/Bytes` | Giới hạn messages đang xử lý, giảm quá tải memory/DB |
| ACK deadline/lease extension | Giảm redelivery khi processing hợp lệ mất thời gian |
| Số workers/Pod replicas | Năng lực xử lý so với connection pool và quota |
| Batch sizes/publisher flow control | Throughput so với latency, memory và publish retries |
| Retry policy / dead-letter topic | Tránh poison messages làm nghẽn subscription |
| Exactly-once | Đánh đổi thêm phối hợp/latency để có confirmed ACK semantics |

**Không coi scale-out là giải pháp cho mọi backlog.** Nếu bottleneck là Cloud SQL connection pool, tăng số Pods có thể tăng timeout, NACK và chi phí.

## 13. Theo dõi đúng tín hiệu và chi phí

Theo dõi trong **Cloud Monitoring** và logs:

| Tín hiệu | Diễn giải |
| --- | --- |
| `subscription/num_undelivered_messages` | Backlog còn chờ |
| `subscription/oldest_unacked_message_age` | Độ trễ của message cũ nhất |
| `subscription/expired_ack_deadlines_count` | Processing/lease management có vấn đề |
| `subscription/exactly_once_warning_count` | ACK/ModifyAckDeadline warnings, không chứng minh duplicate |
| Số log `CREATED` và `DUPLICATE_SKIPPED` | Đo công việc mới và số lần dedupe |
| `processed_events` count / `shipping_tasks` count | Bằng chứng business effect đúng |
| JDBC connection errors, transaction latency | Sức khỏe Cloud SQL và giới hạn downstream |
| Pub/Sub data volume, retention, retry và egress | Phí giao nhận, lưu giữ, network |

**Không log raw payload chứa PII, token, dữ liệu thanh toán hoặc DB_PASSWORD.** Với production, structured logs nên có `eventId` đã xác minh, `messageId`, service/instance, error code và trace/correlation ID; bảo đảm metrics không dùng `eventId` làm label có cardinality vô hạn.

## 14. Bảo mật và tính đúng đắn ngoài phạm vi lab

- **IAM:** Publisher và subscriber dùng service identities khác nhau; chỉ cấp `pubsub.publisher` hoặc `pubsub.subscriber` trên tài nguyên thật cần thiết.
- **Auth:** ADC trên local, Workload Identity Federation for GKE/VM service account trong production; không dùng service-account key hardcoded.
- **Cloud SQL:** private connectivity/TLS, DB role tối thiểu, pool/timeout và migrations có kiểm soát.
- **Schema:** payload có version; validate type, eventId/orderId, source authorization và business state transition.
- **Exactly-once:** bảo đảm delivery theo Pub/Sub message ID/region, không bao quát DB + Pub/Sub + email.
- **Durable dedupe:** giữ marker đủ lâu cho retention, publisher retries, seek/replay và yêu cầu nghiệp vụ.
- **Observability:** alerts cho backlog, age, timeout, DLQ, transaction failures và không cân đối row count.
- **Cost:** Cloud Billing budget alerts, subscription retention hợp lý, giới hạn workers, không tăng retry vô hạn.

## 15. Troubleshooting lab

| Triệu chứng | Kiểm tra |
| --- | --- |
| `NOT_FOUND` topic/subscription | Project ID, topic/subscription name, region endpoint |
| `PERMISSION_DENIED` Pub/Sub | Principal ADC và roles trên topic/subscription |
| `JDBC_URL` missing | Đã đặt biến trong **terminal subscriber** chưa? |
| `Connection refused` PostgreSQL | Container chạy, port 127.0.0.1, database/user/password |
| Publisher log thành công, subscriber không nhận | Subscription tạo trước publish? đúng subscription? worker chạy? |
| Subscriber nhận nhưng SQL không có row | Transaction exception, rollback, DB connection và permissions |
| Có hai Pub/Sub message IDs, nhưng chỉ một SQL row | **Đúng** nếu eventId giống nhau |
| Có hai SQL rows cho cùng event | Thiếu unique key/transaction hoặc đã dùng hai dedupe namespaces |
| `ACK outcome uncertain` | Kiểm tra deadline/ACK ID/region; DB marker tránh hiệu ứng lặp |
| NACK liên tục | Poison message, DB không khả dụng, DLQ/retry policy |
| Backlog tăng sau scale-out | DB pool, quota, CPU/memory/flow control, ack deadlines |
| Java compile lỗi | JDK 21, Maven dependencies, package/class/file paths |

**Không sửa bằng cách ACK ngay khi nhận message.** Điều đó có thể làm mất nghiệp vụ khi DB commit thất bại. Nếu cần dừng tạm thời, ngừng consumer an toàn và điều tra backlog trước khi replay.

## 16. Bài tập thực hành và tự kiểm tra

**Bài 1 — Hai publishes, một task.** Chạy `PublishOrder` hai lần với `order-paid:LAB-1:v1`; chạy hai truy vấn count. 

*Kỳ vọng:* Pub/Sub cấp hai message IDs khác nhau; PostgreSQL chỉ có một marker và một shipping task.

**Bài 2 — Cùng eventId nhưng payload khác.** Thử cùng eventId với orderId mới trong môi trường lab riêng.

*Giải thích:* Consumer phát hiện reuse key không nhất quán, rollback/NACK; cần sửa publisher hoặc quarantine.

**Bài 3 — Publish sự kiện mới.** Đổi eventId thành `order-paid:LAB-1:v2` nhưng giữ orderId.

*Giải thích:* Đây là sự kiện mới; thiết kế hiện tại tạo task mới vì dedupe theo eventId. Nếu nghiệp vụ chỉ cho phép **một task trên mỗi order**, thêm unique constraint/business rule trên `order_id` thay vì tưởng dedupe theo eventId là đủ.

**Bài 4 — Crash window.** Trong môi trường thử có fault injection, dừng worker sau COMMIT trước ACK.

*Kỳ vọng:* Pub/Sub có thể giao lại; marker ngăn tạo shipping task thứ hai.

**Bài 5 — Hai subscribers.** Chạy hai tiến trình `ConsumeOrder` cùng subscription và database, publish một event.

*Kỳ vọng:* Unique constraint bảo vệ khi có cạnh tranh; không có hai task cho cùng eventId.

**Câu 6.** Vì sao `messageId` không đủ dedupe publisher retry?

*Đáp án:* Hai publishes của cùng event có thể có hai messageId khác nhau.

**Câu 7.** Vì sao ACK phải sau COMMIT?

*Đáp án:* ACK trước khi commit rồi crash có thể làm mất công việc mà Pub/Sub đã coi là xong.

**Câu 8.** Pub/Sub exactly-once có hỗ trợ push tới Cloud Run HTTP endpoint không?

*Đáp án:* Không. Chỉ pull/StreamingPull trong các điều kiện hỗ trợ.

**Câu 9.** Bật exactly-once có loại bỏ việc xử lý trùng do publisher gửi lại event không?

*Đáp án:* Không. Cần eventId ổn định và dedupe ở consumer.

**Câu 10.** Tại sao không dùng `HashSet` static để lưu processed event IDs?

*Đáp án:* Không chia sẻ giữa instances và mất khi restart; cần shared durable store.

**Câu 11.** Khi DB đã COMMIT mà ACK future timeout, nên NACK ngay để “chạy lại” nghiệp vụ không?

*Đáp án:* Không cần. Giữ marker, theo dõi kết quả không chắc chắn; nếu redelivery xảy ra, consumer ACK sau khi thấy duplicate.

**Câu 12.** Unique `eventId` có bảo đảm chỉ một shipping task trên mỗi order không?

*Đáp án:* Không nếu mỗi order có nhiều event IDs; business invariant phải có constraint riêng khi yêu cầu.

## 17. Checklist trước production

- [ ] Business eventId sinh một lần và giữ ổn định qua publish retries.
- [ ] Publisher đợi publish result, có retry/backoff và outbox nếu DB + publish cần đồng bộ.
- [ ] Subscriber có validation, transaction và ACK **sau COMMIT**.
- [ ] Dedupe nằm trong DB chung với side effect hoặc thiết kế atomic tương đương.
- [ ] Unique keys đáp ứng **cả event identity và business invariants**.
- [ ] Nếu dùng exactly-once: pull/StreamingPull, compatible client, single region/endpoint, confirmed ACK.
- [ ] Có timeout, flow control, lease extension và max concurrent DB connections.
- [ ] Poison events, invalid payload và downstream outages có retry/DLQ rõ ràng.
- [ ] Có thử nghiệm duplicate publish, crash trước/sau COMMIT và nhiều replicas.
- [ ] Có dashboard backlog, expired ACK deadlines, retries, DB errors và business row counts.
- [ ] IAM tối thiểu, ADC/WIF, TLS, secrets management và không log dữ liệu nhạy cảm.
- [ ] Có budget, retention/cleanup policy và runbook replay/rollback.

## 18. Dọn tài nguyên lab và kết luận

Sau khi kết thúc và **xác nhận không có consumer/workload khác dùng**:

~~~bash
# Dừng Java subscriber trước; xóa riêng từng tài nguyên lab.
gcloud pubsub subscriptions delete orders-worker-lab \
  --project=PROJECT_ID

# Nếu đã tạo subscription phụ ở mục 10:
gcloud pubsub subscriptions delete orders-worker-exactly-lab \
  --project=PROJECT_ID

gcloud pubsub topics delete orders-events-lab \
  --project=PROJECT_ID

# Nếu dùng PostgreSQL Docker riêng của lab:
docker stop orders-pg-lab
~~~

Đây là **các lệnh xóa thật**, có thể làm mất message backlog và dữ liệu lab; đừng chạy nếu tài nguyên được sử dụng chung. Xử lý IAM bindings, DB data, billing alerts và artifacts theo chính sách tổ chức.

**Kết luận:** Pub/Sub giúp chuyển sự kiện giữa services nhưng **delivery guarantee không tự trở thành business transaction guarantee**. Với Java publisher/subscriber, mẫu đáng tin cậy là **publish kèm eventId bền vững → subscriber validate → unique dedupe + business update trong transaction → COMMIT → ACK → quan sát khi retry**. Kết quả kiểm thử **hai publishes, một shipping task** là bằng chứng trực tiếp rằng hệ thống xử lý trùng đúng phạm vi cần thiết.

## Tài liệu tham khảo chính thức

- [Pub/Sub publish và nhận messages bằng client libraries](https://cloud.google.com/pubsub/docs/publish-receive-messages-client-library)
- [Java sample: publish custom attributes](https://cloud.google.com/pubsub/docs/samples/pubsub-publish-custom-attributes)
- [Java sample: pull subscriber](https://cloud.google.com/pubsub/docs/samples/pubsub-quickstart-subscriber)
- [Exactly-once delivery](https://cloud.google.com/pubsub/docs/exactly-once-delivery)
- [Java sample: confirmed ACK](https://cloud.google.com/pubsub/docs/samples/pubsub-subscriber-exactly-once)
- [Subscriber best practices](https://cloud.google.com/pubsub/docs/subscribe-best-practices)
- [Troubleshoot pull subscriptions](https://cloud.google.com/pubsub/docs/pull-troubleshooting)
- [Retry policy](https://cloud.google.com/pubsub/docs/subscription-retry-policy)
- [Dead-letter topics](https://cloud.google.com/pubsub/docs/dead-letter-topics)
- [Pub/Sub Monitoring](https://cloud.google.com/pubsub/docs/monitoring)
- [Cloud Java libraries BOM](https://cloud.google.com/java/docs/bom)
- [Pub/Sub pricing](https://cloud.google.com/pubsub/pricing)

