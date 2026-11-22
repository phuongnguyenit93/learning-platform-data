# Hàng đợi công việc và nhóm consumer xử lý nền

> **Chương:** Mẫu tích hợp  
> **Phạm vi:** Thiết kế **work queue** (*task queue*) trên Apache ActiveMQ Classic/Artemis, để một producer giao việc bất đồng bộ cho **nhóm competing consumers**. Bài tập trung vào điều phối công việc, mở rộng worker, thời điểm ACK/commit, retry/redelivery, DLQ, idempotency, khả năng quan sát và giới hạn thứ tự. Mã Java chính dùng **ActiveMQ Classic 5.x + `javax.jms` (JMS 1.1)**; phần Artemis dùng cấu hình address/anycast và chỉ rõ khác biệt provider.

## 1. Vì sao cần hàng đợi công việc?

Một ứng dụng nhận yêu cầu tạo báo cáo PDF. Nếu HTTP handler trực tiếp tổng hợp dữ liệu và dựng PDF trong 30 giây thì kết nối có thể timeout, mỗi request chiếm một web thread và việc tăng tải làm nghẽn hệ thống.

Thay vào đó, web/API service tạo một **job** rồi đưa vào queue `background.jobs`. Một hoặc nhiều worker chạy nền lấy job, xử lý, cập nhật trạng thái và xác nhận JMS message:

~~~mermaid
flowchart LR
    API["API / Producer"] -->|send jobId| Q["JMS Queue: background.jobs"]
    Q --> W1["Worker 1"]
    Q --> W2["Worker 2"]
    Q --> W3["Worker 3"]
    W1 --> DB[("Trạng thái job / dữ liệu nghiệp vụ")]
    W2 --> DB
    W3 --> DB
~~~

**Đặc tính cốt lõi:** với **một queue và nhiều consumer**, các worker là *competing consumers*. Broker phân phối **mỗi lần delivery** tới một consumer phù hợp; không phát một bản cho **mỗi** worker như với nhiều topic subscriptions độc lập.

Từ đó cần phân biệt:

- **Bất đồng bộ:** API có thể trả về khi ý định tạo job đã được lưu/gửi, không cần đợi render hoàn tất.
- **Đệm tải:** queue giữ backlog khi có nhiều job hơn năng lực worker tại một thời điểm.
- **Scale-out:** có thể mở thêm worker **cùng tiêu thụ một queue**.
- **Tách vòng đời:** producer và worker không nhất thiết chạy đồng thời.
- **Nhận lại khi lỗi:** job chưa được broker xác nhận có thể được giao lại.

Cụm từ “mỗi job chỉ một worker” phải hiểu là **mỗi lần phân phối trong queue thường đến một consumer**, không phải **đúng một lần thực thi nghiệp vụ trong mọi sự cố**. Redelivery và producer retry vẫn có thể khiến cùng `jobId` được nhìn thấy hơn một lần.

### 1.1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt work queue với topic fan-out và với nhóm consumer theo mô hình khác.
2. Xác định ranh giới message **pending → dispatched/in-flight → ACK/commit → hoàn tất**.
3. Viết một producer Java gửi job persistent và nhiều worker Java độc lập xử lý cùng queue.
4. Chọn cấu hình prefetch, số worker, transaction và redelivery/DLQ cho tải nền.
5. Xử lý tình huống crash sau khi side effect đã commit nhưng trước JMS ACK.
6. Đo queue lag, job age, throughput, retry và chứng minh hệ thống không xử lý nghiệp vụ trùng.

## 2. Queue và competing consumers hoạt động như thế nào?

Producer gửi message vào **một destination dạng queue**. Broker duy trì các message có trách nhiệm giao và chọn một trong các consumer có thể nhận.

~~~text
                         JMS Queue: background.jobs
                        +---------------------------+
Producer A ------------>| J1 | J2 | J3 | J4 | J5  |
Producer B ------------>|                         |
                        +------+-------+----------+
                               |       |
                       dispatch|       |dispatch
                               v       v
                            Worker A  Worker B
                          Session A   Session B
~~~

Giả sử hai worker cùng đang hoạt động:

| Message | Lần dispatch đầu | Kết quả ví dụ |
|---|---|---|
| J1 | Worker A | A xử lý và commit |
| J2 | Worker B | B xử lý và commit |
| J3 | Worker A | A crash trước commit |
| J4 | Worker B | B xử lý và commit |
| J3 (redelivery) | Worker B hoặc worker mới | Có thể được xử lý lại |

**Lưu ý:** bảng chỉ là kịch bản minh họa, không phải lịch phân phối cố định hay cam kết round-robin của ActiveMQ.

Một JMS queue có thể có một consumer hoặc hàng chục consumer; không cần dùng “consumer group ID” trong mỗi worker như một mô hình partitioned log. Với JMS **Queue**, việc cùng đăng ký destination `background.jobs` đã làm các consumer cạnh tranh nhận message.

### 2.1. Work queue khác topic fan-out

| Tiêu chí | JMS Queue (competing consumers) | JMS Topic |
|---|---|---|
| Mục tiêu | Chia một tập job cho một pool worker | Phát sự kiện tới nhiều subscription độc lập |
| Cùng một message | Một consumer xử lý **mỗi lần delivery** ở queue | Mỗi subscription phù hợp có thể nhận bản của nó |
| Scale thêm 3 worker | Tăng số consumer cùng chia backlog | Nếu mỗi worker tạo subscription riêng, có thể nhân bản xử lý |
| Consumer offline | Message persistent có thể tiếp tục chờ trong queue | Phụ thuộc durable/non-durable subscription |
| Ví dụ | Render report, gửi email theo hàng chờ, resize ảnh | OrderCreated cho Billing, Analytics, Fraud cùng nhận |

Nếu **Billing** và **Analytics** đều phải nhận mỗi sự kiện OrderCreated, không nên đặt cả hai nhóm vào **cùng một work queue** rồi kỳ vọng mỗi bên nhận đủ. Hãy dùng topic/durable subscriptions, hoặc Artemis multicast address route tới **hai queue độc lập**: một queue cho Billing, một queue cho Analytics; mỗi queue có pool competing consumers riêng.

### 2.2. Artemis: phân biệt address và queue

Trong Artemis, **address** là nơi producer gửi; **queue** nhận message theo routing type. Với một work queue, dùng **anycast**. Worker nhận từ cùng một queue vật lý; không tạo một queue mới cho mỗi worker.

Ví dụ:

~~~xml
<!-- Fragment bên trong <addresses> của etc/broker.xml -->
<address name="background.jobs">
  <anycast>
    <queue name="background.jobs" durable="true"/>
  </anycast>
</address>
~~~

Với một address có **nhiều anycast queues**, broker có thể định tuyến message giữa các queue theo semantics anycast; điều đó **khác** việc nhiều consumers cùng đọc **một** queue. Để có một pool worker chia chung backlog, hãy bắt đầu bằng **một anycast queue**, nhiều consumers.

Ở ActiveMQ Classic, JMS Queue mang tên `background.jobs`; cấu hình destination policy của Classic có syntax riêng, không sao chép fragment `<addresses>` của Artemis vào `activemq.xml`.

## 3. Thiết kế hợp đồng job: dữ liệu phải đủ để retry và kiểm toán

Một job nên có **định danh ổn định**, loại công việc, phiên bản, thời gian tạo, tham số tối thiểu và quy tắc xử lý khi trùng.

Ví dụ payload:

~~~json
{
  "jobId": "job-20261117-0001",
  "jobType": "report.generate.v1",
  "reportId": "R-1001",
  "requestedAt": "2026-11-17T03:00:00Z",
  "parameters": {
    "format": "pdf",
    "language": "vi"
  }
}
~~~

Trong JMS, có thể đưa những trường thường dùng để lọc/quan sát thành properties:

~~~java
TextMessage message = session.createTextMessage(payloadJson);
message.setStringProperty("jobId", stableJobId);
message.setStringProperty("jobType", "report.generate.v1");
message.setJMSType("report.generate.v1");
~~~

**Ba định danh cần tách biệt:**

- `jobId`: ID nghiệp vụ ổn định qua **mọi lần gửi lại** của cùng một job; làm idempotency key.
- `JMSMessageID`: provider tạo cho một JMS message/lần send; không bảo đảm giữ nguyên nếu producer tạo message mới khi retry.
- `JMSCorrelationID`: tùy hợp đồng, dùng để liên kết request/trace; không mặc nhiên là job ID.

Nếu job tạo file lớn, thường đưa **URI đối tượng đã lưu an toàn + checksum** trong message, thay vì nhét toàn bộ file vào body. Nếu muốn body lớn do broker quản lý, Artemis có large-message streaming riêng, nhưng điều đó không thay thế quy trình kiểm tra hoàn tất job.

### 3.1. Kết quả job nằm ở đâu?

Đừng yêu cầu HTTP request ban đầu chờ consumer ACK. Hai mô hình thông dụng:

1. API nhận job, lưu trạng thái `QUEUED`, trả `202 Accepted` và `jobId`. Client tra `GET /jobs/{jobId}` hoặc đăng ký thông báo riêng.
2. Worker phát sự kiện `JobCompleted/JobFailed` sau commit kết quả vào hệ thống dữ liệu. Dịch vụ khác lắng nghe theo hợp đồng event.

**JMS ACK không phải “job thành công” từ góc nhìn người dùng**. ACK chỉ là xác nhận delivery của messaging session. Một job có thể thất bại nghiệp vụ, cần trạng thái lỗi hoặc DLQ, dù broker vẫn hoạt động.

## 4. Vòng đời một job trong work queue

Một message có thể đi qua các bước:

~~~mermaid
stateDiagram-v2
    [*] --> Pending: Producer send/commit
    Pending --> Delivering: Broker dispatch
    Delivering --> Completed: Worker xử lý + JMS ACK/commit
    Delivering --> Pending: Rollback / mất connection
    Pending --> Expired: TTL hết hạn
    Delivering --> DeadLetter: Vượt chính sách redelivery
    DeadLetter --> Pending: Redrive có kiểm soát
    Completed --> [*]
    Expired --> [*]
~~~

Sơ đồ là **mô hình vận hành**, không phải tên state nội bộ chính thức của Classic/Artemis.

### 4.1. “Đã gửi” khác “đã xử lý”

| Mốc | Ý nghĩa có thể khẳng định |
|---|---|
| Producer tạo `TextMessage` | Job mới là object trong bộ nhớ ứng dụng |
| `producer.send()` trên session transacted | Message nằm trong transaction chưa commit |
| `session.commit()` gửi thành công | Broker/provider đã xác nhận transaction gửi theo semantics cấu hình |
| Broker dispatch | Message đã giao tới client/consumer, có thể còn in-flight |
| Worker ghi kết quả DB | Side effect nghiệp vụ đã commit theo transaction DB |
| Worker `session.commit()` nhận | Transaction nhận JMS đã commit; broker không còn nghĩa vụ giao lần đó |
| Producer/consumer mất response commit | Kết quả có thể **unknown**; không được suy là chưa commit |

**Quan trọng:** local JMS transaction không tự bao gồm transaction của PostgreSQL/S3/API thanh toán. Worker phải xử lý idempotency ở tầng lưu trữ nghiệp vụ.

### 4.2. Những lý do message có thể xuất hiện lại

- Worker nhận rồi **rollback** vì lỗi xử lý.
- Worker chết trước khi ACK/commit có hiệu lực.
- Connection mất giữa processing/commit; broker chuyển message về trạng thái có thể giao lại.
- Producer retry sau khi không nhận được phản hồi commit, tạo thêm một message mới có cùng `jobId`.
- Admin redrive DLQ/replay event.

Vì vậy **tên “work queue” không đồng nghĩa exactly-once processing**.

## 5. Java ActiveMQ Classic 5.x: chuẩn bị môi trường lab

Ví dụ sau dùng **Java 11+, ActiveMQ Classic 5.x và `javax.jms` (JMS 1.1)**, broker lab tại `tcp://localhost:61616`. Cần một queue `background.jobs` và user demo `app/lab-secret` có quyền send/consume. Thay bằng credentials thực tế của môi trường lab.

Nếu dùng Maven với phiên bản client Classic 5.x phù hợp broker, dependency ví dụ:

~~~xml
<dependency>
  <groupId>org.apache.activemq</groupId>
  <artifactId>activemq-client</artifactId>
  <version>5.18.3</version>
</dependency>
~~~

Các class này import `javax.jms`, **không** phải `jakarta.jms`. Ở Spring Boot 3.x hoặc Artemis Jakarta client, namespace và dependency thay đổi; không copy nguyên mã Classic 5.x vào classpath Jakarta rồi sửa một import đơn lẻ.

### 5.1. Producer: gửi job persistent và giữ jobId qua retry

File `WorkProducer.java`:

~~~java
import javax.jms.Connection;
import javax.jms.DeliveryMode;
import javax.jms.MessageProducer;
import javax.jms.Queue;
import javax.jms.Session;
import javax.jms.TextMessage;
import org.apache.activemq.ActiveMQConnectionFactory;

public final class WorkProducer {
    private static final String BROKER = "tcp://localhost:61616";

    public static void main(String[] args) throws Exception {
        if (args.length != 2 || args[0].trim().isEmpty()) {
            throw new IllegalArgumentException(
                    "Usage: WorkProducer <jobId> <jobPayload>");
        }
        String jobId = args[0];  // ID ổn định, tạo/lưu ở tầng nghiệp vụ.
        String payload = args[1];

        ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory(BROKER);

        Connection connection =
                factory.createConnection("app", "lab-secret");
        try {
            Session session = connection.createSession(
                    true, Session.SESSION_TRANSACTED);
            try {
                Queue queue = session.createQueue("background.jobs");
                MessageProducer producer = session.createProducer(queue);
                try {
                    producer.setDeliveryMode(DeliveryMode.PERSISTENT);

                    TextMessage message = session.createTextMessage(payload);
                    message.setStringProperty("jobId", jobId);
                    message.setJMSType("background.job.v1");
                    message.setLongProperty(
                            "enqueuedByAppAtMs", System.currentTimeMillis());

                    try {
                        producer.send(message);
                        session.commit(); // Send được xác nhận tại đây.
                        System.out.println("PUBLISHED jobId=" + jobId
                                + " jmsId=" + message.getJMSMessageID());
                    } catch (Exception sendFailure) {
                        // Kết quả commit có thể UNKNOWN khi mất phản hồi.
                        try {
                            session.rollback();
                        } catch (Exception rollbackFailure) {
                            sendFailure.addSuppressed(rollbackFailure);
                        }
                        throw sendFailure;
                    }
                } finally {
                    producer.close();
                }
            } finally {
                session.close();
            }
        } finally {
            connection.close();
        }
    }
}
~~~

**Điểm cần kiểm tra:**

- Một **queue duy nhất** được dùng cho mọi job; không tạo queue theo job ID.
- `DeliveryMode.PERSISTENT` yêu cầu lưu bền theo semantics của JMS provider/broker.
- Với session transacted, `commit()` mới xác nhận nhóm gửi.
- `jobId` do caller cung cấp. Một retry cùng job phải dùng **đúng jobId và payload đã lưu**, không sinh ID khác.
- Không dùng `connection.start()` cho producer-only; nó cần cho việc bật delivery tới consumer.
- JMS 1.1 `Connection`/`Session` không hỗ trợ `try-with-resources` theo contract API này, do đó dùng `try/finally`.

**Giới hạn:** ví dụ chưa có transactional outbox. Nếu producer xử lý request HTTP, commit DB thành công rồi chết **trước** JMS send, broker không biết job tồn tại. Với job quan trọng, nên lưu một outbox row trong cùng DB transaction với yêu cầu tạo job và để dispatcher gửi lại.

## 6. Java worker: một process, một JMS session, một consumer

File `WorkConsumer.java` sử dụng **local JMS transaction** cho mỗi lần nhận. Nếu business xử lý thành công, worker gọi `session.commit()`; nếu lỗi, gọi `session.rollback()` để message có thể được redeliver theo policy.

~~~java
import javax.jms.Connection;
import javax.jms.JMSException;
import javax.jms.Message;
import javax.jms.MessageConsumer;
import javax.jms.Queue;
import javax.jms.Session;
import javax.jms.TextMessage;
import org.apache.activemq.ActiveMQConnectionFactory;

public final class WorkConsumer {
    private static final String BROKER = "tcp://localhost:61616";

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: WorkConsumer <workerId> <maxSuccessJobs>");
        }
        String workerId = args[0];
        int maxSuccessJobs = Integer.parseInt(args[1]);
        if (maxSuccessJobs <= 0) {
            throw new IllegalArgumentException("maxSuccessJobs must be > 0");
        }

        ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory(BROKER);

        // Classic-specific: tránh một worker giữ quá nhiều job trong prefetch.
        factory.getPrefetchPolicy().setQueuePrefetch(1);

        // Chỉ phục vụ lab; cần kiểm tra policy thực tế của client/broker.
        factory.getRedeliveryPolicy().setInitialRedeliveryDelay(1000L);
        factory.getRedeliveryPolicy().setRedeliveryDelay(2000L);
        factory.getRedeliveryPolicy().setUseExponentialBackOff(true);
        factory.getRedeliveryPolicy().setBackOffMultiplier(2.0);
        factory.getRedeliveryPolicy().setMaximumRedeliveries(5);

        Connection connection =
                factory.createConnection("app", "lab-secret");

        try {
            Session session = connection.createSession(
                    true, Session.SESSION_TRANSACTED);
            try {
                Queue queue = session.createQueue("background.jobs");
                MessageConsumer consumer = session.createConsumer(queue);
                try {
                    connection.start(); // Cho phép provider deliver message.

                    int completed = 0;
                    while (completed < maxSuccessJobs) {
                        Message message = consumer.receive(5000L);
                        if (message == null) {
                            System.out.println("IDLE worker=" + workerId);
                            break;
                        }

                        String jobId = message.getStringProperty("jobId");
                        System.out.printf(
                                "RECEIVED worker=%s jobId=%s "
                              + "jmsId=%s redelivered=%s%n",
                                workerId, jobId,
                                message.getJMSMessageID(),
                                message.getJMSRedelivered());

                        try {
                            if (!(message instanceof TextMessage)) {
                                throw new IllegalArgumentException(
                                        "Expected TextMessage");
                            }
                            if (jobId == null || jobId.trim().isEmpty()) {
                                throw new IllegalArgumentException(
                                        "Missing jobId");
                            }

                            String payload =
                                    ((TextMessage) message).getText();
                            doBackgroundWork(jobId, payload, workerId);

                            // Chỉ sau khi công việc được coi thành công.
                            session.commit();
                            completed++;
                            System.out.println(
                                    "COMMITTED " + workerId + " " + jobId);
                        } catch (Exception workFailure) {
                            System.err.println(
                                    "FAILED " + workerId + " "
                                    + jobId + ": " + workFailure);
                            try {
                                session.rollback();
                            } catch (JMSException rollbackFailure) {
                                workFailure.addSuppressed(rollbackFailure);
                                throw workFailure; // Session không còn tin cậy.
                            }
                            // Thực tế cần phân loại lỗi và policy DLQ;
                            // đừng retry nóng vô hạn trên message poison.
                        }
                    }
                } finally {
                    consumer.close();
                }
            } finally {
                session.close();
            }
        } finally {
            connection.close();
        }
    }

    private static void doBackgroundWork(
            String jobId, String payload, String workerId)
            throws Exception {
        if ("always-fail".equals(payload)) {
            throw new IllegalStateException("Fault injection for " + jobId);
        }
        // "slow" giúp đủ thời gian kill worker khi thử crash.
        long workMs = "slow".equals(payload) ? 10000L : 300L;
        System.out.println("PROCESSING " + workerId + " " + jobId);
        Thread.sleep(workMs);
        System.out.println("WORK_DONE " + workerId + " " + jobId);

        // Mô phỏng: CHƯA có durable business DB transaction.
        // Production: commit DB + inbox idempotent trước JMS commit.
    }
}
~~~

**Giải thích chính xác:**

1. Mỗi process worker có **Connection**, **Session** và **MessageConsumer** riêng nhưng cùng queue `background.jobs`.
2. `Session.SESSION_TRANSACTED` làm cho ACK của receive được quản lý bởi `commit()/rollback()`; không cần gọi `message.acknowledge()`.
3. Nếu xử lý thành công nhưng crash trước `session.commit()`, broker có thể giao lại job cho worker khác.
4. `Session` JMS **không được dùng đồng thời bởi nhiều thread**. Ví dụ mỗi JVM chỉ có một consumer loop; muốn tạo nhiều thread thì tạo **mỗi thread một session/consumer** hoặc dùng listener container quản lý concurrency.
5. `queuePrefetch(1)` là API **Classic-specific** nhằm giảm việc một worker chậm giữ nhiều message; không bảo đảm round-robin tuyệt đối.
6. Redelivery policy ở đoạn này là **cấu hình client Classic**, không phải syntax Artemis; tham số `maximumRedeliveries=5` là số lần giao lại tối đa trong policy client, khác cách Artemis đếm delivery attempts.
7. Hàm `doBackgroundWork` chỉ sleep/log. **Chưa đủ an toàn cho công việc có tác động thật**; triển khai idempotency ở mục 9 trước khi đưa vào production.

### 6.1. Tại sao không dùng một session chung cho nhóm worker?

Một lỗi thường gặp:

~~~java
// Sai ý tưởng: chia một JMS Session và MessageConsumer cho nhiều
// threads tự gọi receive()/commit()/rollback() lẫn nhau.
ExecutorService pool = Executors.newFixedThreadPool(8);
for (int i = 0; i < 8; i++) {
    pool.submit(() -> receiveAndCommitOnTheSameSession(sharedSession));
}
~~~

JMS Session là ngữ cảnh **đơn luồng theo hợp đồng sử dụng**, và transaction/ack scope thuộc session. Hai thread có thể vô tình commit/rollback delivery của nhau. Giải pháp là tạo session riêng cho từng worker, hoặc để Spring JMS listener container quản lý số session/consumer.

Snippet trên là **minh họa lỗi**, không phải code đầy đủ để chạy; các tên `sharedSession` và `receiveAndCommitOnTheSameSession` là giả định.

## 7. Chạy nhiều worker để quan sát competing consumers

Sau khi biên dịch và cấu hình classpath Classic 5.x đúng, thử trong **ba cửa sổ terminal** hoặc IDE Run Configurations.

Đầu tiên khởi động hai process worker:

~~~text
WorkConsumer worker-A 100
WorkConsumer worker-B 100
~~~

Sau đó ở producer, gửi nhiều job có ID khác nhau:

~~~text
WorkProducer job-001 render-report-R001
WorkProducer job-002 render-report-R002
WorkProducer job-003 render-report-R003
WorkProducer job-004 render-report-R004
WorkProducer job-005 render-report-R005
WorkProducer job-006 render-report-R006
~~~

Những dòng này thể hiện **tên main class và đối số**. Khi chạy thực, sử dụng IDE, Maven Exec hoặc lệnh `java -cp ... WorkProducer ...` có classpath đúng. Ví dụ worker có timeout idle 5 giây; nếu khởi động worker quá lâu trước khi gửi job, chúng có thể thoát ở lần `receive()` trả null. Trong lab có thể **gửi backlog trước**, rồi chạy worker A và B gần như đồng thời.

**Kỳ vọng quan sát:**

- Mỗi `jobId` được một worker log `RECEIVED` trong lượt xử lý thông thường.
- Không có bảo đảm luân phiên A–B–A–B tuyệt đối.
- Worker nhanh hơn có thể nhận nhiều job hơn.
- Khi một worker ngừng, worker còn lại vẫn có thể xử lý **các message chưa được ACK** sau khi broker phát hiện connection mất.
- Nếu một job gây rollback liên tục, hãy quan sát redelivery trước khi job vào DLQ theo cấu hình.

Để đo lượng việc theo worker, đếm số dòng `COMMITTED worker-A/B` theo run, không chỉ đếm `RECEIVED` vì một message có thể đã được nhận nhưng rollback.

### 7.1. Thử crash không cần code gây lỗi hủy process

1. Gửi job với payload `slow` rồi chạy một worker.
2. Đợi log `PROCESSING` xuất hiện.
3. Trong môi trường lab, **dừng cưỡng bức** process worker trước log `COMMITTED`.
4. Khởi động worker khác, quan sát cùng `jobId` có thể được redeliver.
5. Kiểm tra `getJMSRedelivered()` và nếu client hỗ trợ, `JMSXDeliveryCount`.

Nếu worker cũ chỉ sleep/log, việc redelivery chứng minh **semantics của queue/ACK**, chưa chứng minh side effect trùng. Muốn thử ranh giới nguy hiểm hơn, mô phỏng DB commit trước JMS commit và dùng inbox như mục 9.

## 8. Prefetch, công bằng và mở rộng số worker

Broker thường cố gắng dispatch message tới các consumer có khả năng nhận. Nhưng **không có hợp đồng JMS yêu cầu chia đều số job cho mọi worker**.

Giả sử:

- Worker A xử lý một job trong 100 ms.
- Worker B xử lý một job trong 2 giây.
- Broker prefetch sẵn 100 job cho mỗi worker.

Worker B có thể **giữ nhiều job in-flight**, dù A đã rảnh hoặc xử lý xong batch trước. Đó là lý do cần xem **prefetch** khi job có thời gian xử lý không đồng đều.

### 8.1. Prefetch ở ActiveMQ Classic

Đối với lab Classic, đặt trên connection factory **trước khi tạo consumer**:

~~~java
factory.getPrefetchPolicy().setQueuePrefetch(1);
~~~

Có thể cấu hình bằng connection URL theo tùy chọn Classic client tương ứng với phiên bản đang dùng, nhưng ví dụ Java trên giúp nhìn rõ phạm vi của cài đặt.

| Prefetch | Điểm có lợi | Đánh đổi |
|---|---|---|
| Thấp, ví dụ 1 | Ít job bị giữ sẵn ở worker chậm; dễ quan sát phân phối | Tăng trao đổi broker/client, có thể giảm throughput |
| Cao | Giảm round-trip khi mỗi job rất ngắn | Một worker có thể giữ nhiều message chưa xử lý, làm công việc phân phối kém cân bằng |
| 0 (nếu cơ chế client cho phép) | Kéo message theo nhu cầu, hữu ích một số mẫu polling | Cần kiểm tra cách `receive()` và đặc tính pull của client, có overhead |

**Prefetch không phải số thread**, không phải số job xử lý song song trong một Session, và không phải bảo đảm thứ tự hoàn thành.

### 8.2. Artemis không dùng API prefetch Classic

Artemis có **consumer window/flow control** ở Artemis client; hành vi cấp message không giống hệt API `ActiveMQPrefetchPolicy` của Classic. Nếu cần điều chỉnh mức message/bytes client nhận trước, hãy dùng tùy chọn Artemis client/URI/`ServerLocator` tương ứng **đúng version và protocol**.

**Không đặt `factory.getPrefetchPolicy()` trên Artemis Jakarta JMS client** rồi kỳ vọng nó tồn tại. Mọi quyết định tuning phải được đo với message size, processing time và broker memory/network.

### 8.3. Cân đối công suất và backlog

Nếu mỗi worker xử lý trung bình 4 job/giây và có 3 worker độc lập:

~~~text
Công suất lý tưởng = 3 × 4 = 12 jobs/s
Producer đưa đến = 15 jobs/s
Backlog tăng gần = 15 - 12 = 3 jobs/s
Sau 10 phút       = 3 × 600 = 1.800 job mới chờ
~~~

Các phép tính chỉ là **mô hình trung bình**, bỏ qua variance, retry, IO, DB bottleneck, prefetch và latency. Nếu mở worker thứ tư, công suất lý tưởng 16 jobs/s nhưng margin chỉ 1 job/s; vẫn dễ nghẽn khi có đỉnh tải.

Đánh giá scale-out phải xét:

- CPU, memory và concurrency thật của worker.
- Giới hạn database, API upstream và object storage.
- Số connection/session/consumer broker cho phép.
- Phân bố thời gian xử lý (p95/p99), không chỉ trung bình.
- Tỷ lệ rollback/poison jobs làm giảm công suất hữu ích.
- Tốc độ drain backlog sau khi tăng worker.

**Thêm consumer không giúp nếu nghẽn chính nằm ở database hoặc dịch vụ downstream.** Khi đó thêm worker còn có thể gây retry storm.

## 9. Idempotent worker: không xử lý trùng side effect

Ví dụ worker gọi API tạo hóa đơn. Diễn biến nguy hiểm:

~~~text
Worker A nhận job-001
    -> tạo invoice trong DB, COMMIT thành công
    -> crash trước JMS session.commit()
Broker thấy delivery chưa ACK
    -> redeliver job-001 cho Worker B
Worker B tạo thêm invoice thứ hai nếu không kiểm tra jobId
~~~

Cần thiết kế *idempotent consumer*: cùng `jobId` được giao nhiều lần nhưng tác động nghiệp vụ chỉ được commit một lần.

### 9.1. Inbox với unique key

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE processed_jobs (
    consumer_name TEXT NOT NULL,
    job_id        TEXT NOT NULL,
    processed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, job_id)
);

CREATE TABLE generated_reports (
    job_id        TEXT PRIMARY KEY,
    location      TEXT NOT NULL,
    generated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Trong **một transaction DB**, worker:

~~~sql
BEGIN;

-- Ứng dụng kiểm tra có row được INSERT hay không.
INSERT INTO processed_jobs(consumer_name, job_id)
VALUES ('report-worker-group', 'job-001')
ON CONFLICT DO NOTHING
RETURNING job_id;

-- Chỉ khi INSERT trả về row mới:
INSERT INTO generated_reports(job_id, location)
VALUES ('job-001', 's3://report-bucket/output/job-001.pdf');

COMMIT;
~~~

Đoạn trên diễn tả **nhánh điều kiện**: dòng `INSERT INTO generated_reports` phải được ứng dụng thực hiện **chỉ nếu** câu INSERT đầu tiên có row mới, không chạy vô điều kiện trong một script SQL bất kể kết quả.

Thứ tự đúng ở worker có side effect trong cùng database:

~~~text
receive JMS message
  -> BEGIN DB TX
  -> INSERT unique inbox(jobId)
       nếu đã tồn tại: bỏ qua side effect
       nếu mới: thực hiện business mutation
  -> COMMIT DB TX
  -> JMS session.commit()  (ACK delivery)
~~~

Nếu DB rollback, worker **không commit JMS**. Nếu DB commit rồi JMS commit thất bại, redelivery sau đó thấy inbox row và không ghi side effect lần hai.

### 9.2. Với API ngoài DB: idempotency key hoặc saga

Nếu job gọi email provider, payment gateway hay upload object storage, việc ghi inbox trước rồi gọi service bên ngoài có thể tạo **khoảng lỗi**:

- Inbox commit nhưng service chưa được gọi → message lần sau bị bỏ qua.
- Service đã xử lý nhưng worker chưa lưu kết quả → retry có thể tạo side effect trùng.

Khi tác động ở hệ ngoài database, cần **idempotency key** được service ngoài hỗ trợ, hoặc một state machine/workflow có cơ chế đối soát. Ví dụ đặt object key theo `jobId` và dùng conditional put/etag; với thanh toán phải dùng khóa idempotency của payment provider.

**Không tuyên bố JMS transaction + inbox luôn đạt exactly once với mọi external side effect.** Phải xác định hệ thống nào là nguồn sự thật và transaction boundary ở đâu.

## 10. Retry/redelivery và Dead Letter Queue cho job lỗi

Một job có thể thất bại vì:

- **Lỗi tạm thời:** network tới DB chập chờn, API trả 503, storage timeout.
- **Lỗi vĩnh viễn:** dữ liệu không hợp lệ, schema không hỗ trợ, thiếu quyền không thể tự sửa.
- **Poison job:** xử lý lần nào cũng ném cùng exception.

Nếu worker rollback vô hạn và broker lập tức phát lại poison job, queue có thể bị chiếm bởi job đó. Cần **giới hạn attempts + backoff + DLQ** và có quy trình sửa/replay.

### 10.1. Classic: redelivery policy ở client, DLQ strategy ở broker

Trong ví dụ `WorkConsumer`, Classic client cấu hình:

~~~java
factory.getRedeliveryPolicy().setInitialRedeliveryDelay(1000L);
factory.getRedeliveryPolicy().setRedeliveryDelay(2000L);
factory.getRedeliveryPolicy().setUseExponentialBackOff(true);
factory.getRedeliveryPolicy().setBackOffMultiplier(2.0);
factory.getRedeliveryPolicy().setMaximumRedeliveries(5);
~~~

Khi redelivery vượt chính sách của Classic client, broker có thể nhận **poison acknowledgment** và gửi message vào DLQ theo dead-letter strategy đã cấu hình. Hành vi mặc định, tên DLQ và chi tiết gửi lại phải được kiểm tra đúng client/broker version.

Classic thường có default DLQ tên `ActiveMQ.DLQ` nếu chưa chọn chiến lược riêng. Nếu muốn chia DLQ theo queue, có thể dùng fragment **bên trong `<broker>` của `activemq.xml`**:

~~~xml
<destinationPolicy>
  <policyMap>
    <policyEntries>
      <policyEntry queue="background.jobs">
        <deadLetterStrategy>
          <individualDeadLetterStrategy
              queuePrefix="DLQ."
              useQueueForQueueMessages="true"/>
        </deadLetterStrategy>
      </policyEntry>
    </policyEntries>
  </policyMap>
</destinationPolicy>
~~~

Đây là một **fragment chính sách Classic**, không phải cấu hình Artemis. Với prefix `DLQ.`, DLQ của queue lab có thể là `DLQ.background.jobs`. Thực tế cần kiểm tra dead-letter strategy đã có trong broker hiện tại để tránh chồng policy hoặc thay đổi destination ngoài ý muốn.

### 10.2. Artemis: redelivery/DLQ tại broker address settings

Artemis cấu hình redelivery dựa trên **address settings**. Fragment ví dụ trong `<core>` của `broker.xml`:

~~~xml
<addresses>
  <address name="background.jobs">
    <anycast>
      <queue name="background.jobs" durable="true"/>
    </anycast>
  </address>

  <address name="DLQ">
    <anycast>
      <queue name="DLQ" durable="true"/>
    </anycast>
  </address>
</addresses>

<address-settings>
  <address-setting match="background.jobs">
    <dead-letter-address>DLQ</dead-letter-address>
    <max-delivery-attempts>6</max-delivery-attempts>
    <redelivery-delay>1000</redelivery-delay>
  </address-setting>
</address-settings>
~~~

Ý nghĩa:

- `max-delivery-attempts=6` được Artemis diễn giải theo **tổng số attempts** của message, khác với ý niệm “maximum redeliveries sau lần đầu” trong một số Classic client policy.
- `redelivery-delay=1000` đặt khoảng chờ trước delivery lại, theo semantics của Artemis.
- `dead-letter-address=DLQ` đòi DLQ address/queue/routing đủ điều kiện, nếu không message lỗi có thể không tới nơi cần giám sát.
- Việc đặt `<addresses>` và `<address-settings>` phải tuân theo schema/thứ tự phần tử của bản Artemis đang chạy. Đây là **fragment minh họa**, không phải `broker.xml` hoàn chỉnh.

**Không mặc định rằng sửa `spring.jms.*` trong Spring Boot có thể thay thế `redelivery-delay`/`dead-letter-address` của Artemis broker.**

### 10.3. Phân loại lỗi và xử lý poison

Trong worker production:

1. Lỗi validation chắc chắn không hồi phục → đánh dấu job FAILED hoặc chuyển sang DLQ theo chính sách; tránh retry nóng.
2. Lỗi mạng/timeout tạm thời → rollback và redelivery sau delay/backoff có giới hạn.
3. Lỗi không rõ → ghi attempt/eventId/exception class, tránh lộ payload nhạy cảm; có cơ chế quan sát.
4. Tới DLQ → alert, phân tích root cause, sửa dữ liệu/code rồi **redrive có kiểm soát**, giữ cùng `jobId`.
5. Nếu job quá hạn nghiệp vụ → xử lý expired/terminal theo hợp đồng, không để TTL tự xóa mà mất trace trạng thái.

**Không xem DLQ là một nhóm consumer làm việc bình thường.** Đây là nơi cách ly thông điệp không xử lý được sau policy, cần quy trình vận hành riêng.

## 11. Ordering, job affinity và nhóm consumer

Queue với nhiều consumers tối ưu **phân phối công việc**, không tối ưu **thứ tự hoàn thành toàn cục**.

Ví dụ producer gửi:

~~~text
J1: cập nhật Account A, sequence=1
J2: cập nhật Account A, sequence=2
J3: cập nhật Account B, sequence=1
~~~

Worker A nhận J1 và xử lý chậm; Worker B nhận J2, xử lý nhanh. **J2 có thể commit trước J1**, gây vi phạm thứ tự đối với Account A.

Một số giải pháp:

- **Thiết kế job độc lập/idempotent**, không yêu cầu thứ tự; phù hợp nhất với competing consumers.
- **Message groups** như property `JMSXGroupID` khi Classic/Artemis client và broker hỗ trợ: các message cùng khóa được gắn với một consumer theo policy của provider, giúp bảo vệ thứ tự tương đối trong điều kiện hoạt động phù hợp.
- **Tách queue/partition theo business key** hoặc dùng một worker tuần tự cho nhóm có yêu cầu strict ordering.
- **Optimistic locking/sequence check** ở database để phát hiện xử lý out-of-order.

Ví dụ property group:

~~~java
message.setStringProperty("JMSXGroupID", accountId);
~~~

Đây là **JMSX provider extension được broker hỗ trợ theo version**, không phải cam kết sẽ luôn giữ tuyệt đối cùng một worker sau crash/rebalance. Một group nóng có thể trở thành bottleneck, và backlog/retry vẫn cần kiểm thử.

### 11.1. Selector không phải cơ chế chia tải mặc định

Có thể tạo consumer với selector:

~~~java
MessageConsumer pdfWorker = session.createConsumer(
    queue, "jobType = 'report.generate.v1'");
~~~

Khi đó consumer chỉ nhận message có property phù hợp. Tuy nhiên nếu các worker trong pool sử dụng selector khác nhau, chúng **không còn thực sự chia đều toàn bộ backlog**, vì mỗi worker chỉ đủ điều kiện nhận một tập message.

Đối với một pool worker tương đương nhau, bắt đầu bằng **cùng queue, cùng contract message, không selector**, rồi bổ sung selector/queue riêng khi có nhu cầu tách workload thực sự.

## 12. Spring Boot: pool listener mà không tự tạo thread dùng chung Session

Nếu ứng dụng sử dụng Spring Boot và Spring JMS, có thể triển khai worker bằng `@JmsListener`. Spring listener container quản lý consumer/session concurrency; không cần tự chia một Session sang nhiều thread.

Ví dụ Boot 3.x/Jakarta JMS, khi dự án đã có starter tương ứng **chỉ một provider**:

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class BackgroundJobListener {

    @JmsListener(
        destination = "background.jobs",
        concurrency = "3-6")
    public void receive(String payload) {
        processJob(payload); // Cần idempotency nếu có side effect.
    }

    private void processJob(String payload) {
        // Demo: production ghi business result + inbox theo jobId.
        System.out.println(payload);
    }
}
~~~

Để kiểm soát ACK/rollback, cần **listener container factory** có transaction phù hợp, ví dụ dùng `DefaultJmsListenerContainerFactory`, thiết lập `sessionTransacted=true`, và kiểm tra error handler/transaction manager. **Chỉ thêm `concurrency="3-6"` không tự tạo đúng semantics ACK sau database commit.**

Tại mỗi instance Spring Boot, concurrency 3–6 nghĩa là một instance có thể chạy nhiều consumer. Nếu có 4 replicas, tổng số consumer có thể lên tới 12–24; phải tính cả DB capacity và broker connection/session limits.

Artemis hay Classic đều có thể cung cấp JMS `ConnectionFactory` cho Spring, nhưng **`spring.activemq.*` và `spring.artemis.*` là cấu hình provider khác nhau**; không copy XML hay client API của một bên cho bên kia.

## 13. Theo dõi queue và job để biết khi nào cần scale

Một work queue cần metric cho cả **messaging** và **business completion**.

| Metric | Câu hỏi trả lời | Hành động |
|---|---|---|
| `queue_pending_messages` | Bao nhiêu job đang chờ broker dispatch? | Theo dõi backlog và tốc độ tăng |
| `queue_delivering_messages` | Bao nhiêu message đã dispatch nhưng chưa ACK? | Phát hiện worker giữ job lâu |
| `enqueue_rate / dequeue_rate` | Producer nhanh hơn worker bao nhiêu? | Quyết định scale/rate limit |
| `oldest_job_age_seconds` | Job lâu nhất chưa hoàn tất đã chờ bao lâu? | Cảnh báo vi phạm deadline |
| `job_processing_seconds` p50/p95/p99 | Một worker cần bao lâu xử lý? | Capacity planning, tìm job chậm |
| `worker_busy_ratio` | Worker đang bão hòa? | Scale khi downstream còn năng lực |
| `redelivery_total` | Bao nhiêu message bị nhận lại? | Điều tra crash/retry/poison |
| `dlq_messages_total` | Bao nhiêu job không xử lý sau policy? | Alert và runbook redrive |
| `job_completed_total / job_failed_total` | Nghiệp vụ có thực sự hoàn thành không? | Không nhầm ACK với completion |

Các tên metric ở bảng là **đề xuất quan sát ở tầng ứng dụng/management**, không phải tên JMX/management attribute chính xác tồn tại giống hệt trên mọi phiên bản Classic/Artemis.

### 13.1. Khi nào nên tăng worker?

Giả sử độ trễ xử lý trung bình ~250 ms/job (4 job/s/worker). Tăng worker có ích khi:

1. `enqueue_rate` cao hơn `completion_rate` đủ lâu để backlog tích tụ.
2. Worker đang bão hòa CPU hoặc chờ I/O nhưng tài nguyên downstream vẫn còn công suất.
3. Broker có đủ connection/session và disk/store capacity.
4. Tỷ lệ lỗi/redelivery thấp; tăng consumer không làm poison job tắc nghẽn thêm.

Nếu DB đã đạt giới hạn 500 queries/s, tăng số worker có thể làm timeout nhiều hơn và **giảm** throughput hữu ích. Nên rate-limit, batch hợp lý hoặc tách loại job sang queue/worker pool khác.

### 13.2. Backpressure phải giữ lại ý định làm việc

Nếu broker chậm/đầy:

- Producer cần giới hạn thời gian send, phân loại lỗi và không retry nóng vô hạn.
- Với job quan trọng, lưu pending job/outbox trong DB để process restart không làm mất ý định.
- Không tạo một queue mới cho mỗi request để “đỡ backlog”; sẽ làm tăng overhead quản lý destination.
- Có thể tách job chậm/nhanh vào hai queue với pool riêng nếu một lớp chiếm hết worker.
- Với workload cần được hủy khi quá hạn, định nghĩa deadline nghiệp vụ và trạng thái FAILED/EXPIRED thay vì chỉ dựa TTL JMS.

## 14. Bài thực hành có kiểm chứng

### A — Hai worker cạnh tranh một queue

1. Dọn queue lab, giữ broker persistence.
2. Gửi 20 job với `jobId` khác nhau.
3. Mở hai worker cùng đọc `background.jobs`, prefetch=1.
4. Ghi mapping `jobId → workerId` từ dòng `COMMITTED`.

**Kỳ vọng:** Mỗi job được một worker commit trong lượt bình thường; số job giữa workers có thể không đều. Không có cam kết A/B luân phiên cứng.

### B — Một worker crash giữa job chậm

1. Gửi `WorkProducer job-slow slow`.
2. Mở worker A và đợi log `PROCESSING worker-A job-slow`.
3. Kill worker A trước `COMMITTED`.
4. Mở worker B, quan sát job có thể được giao lại và commit.

**Giải thích:** Broker chưa nhận ACK/commit của worker A. Redelivery không phải producer gửi mới; cần phân biệt JMSMessageID và `jobId`.

### C — Job poison

1. Gửi `WorkProducer job-bad always-fail`.
2. Chạy worker, theo dõi rollback và số lần nhận.
3. Khi đạt ngưỡng redelivery policy, quan sát DLQ theo cấu hình broker.
4. Không redrive ngay trước khi sửa nguyên nhân thất bại.

**Giải thích:** Retry vô hạn khiến throughput hữu ích giảm; DLQ dùng để cách ly job lỗi.

### D — Crash sau side effect DB nhưng trước JMS commit

1. Dùng phiên bản worker thực sự ghi database và inbox với unique jobId.
2. Chèn fault injection sau DB commit, trước JMS session.commit.
3. Restart worker, message có thể được giao lại.
4. Kiểm tra `processed_jobs` có một row duy nhất và báo cáo/hóa đơn không được tạo lần hai.

**Giải thích:** Đây là phép thử idempotency quan trọng nhất; `JMSRedelivered` không thể thay thế business unique key.

### E — Nhiều worker nhưng throughput không tăng

1. Đo một worker, hai worker, bốn worker với cùng một tập job.
2. Ghi CPU/DB utilization, processing p95, queue lag, redelivery.
3. Nếu DB bão hòa từ hai worker, mở thêm worker có thể không tăng completion rate.

**Giải thích:** Scale consumer không tạo thêm capacity cho database hoặc API downstream.

### F — Dùng topic nhầm cho job queue

Một producer gửi `JobCreated` lên topic, ba worker tạo ba non-shared subscriptions khác nhau.

**Kỳ vọng:** Cả ba subscription có thể cùng nhận event; một job có nguy cơ được xử lý ba lần. Dùng **một JMS queue** cho một pool cùng chia việc, không dùng một topic subscription độc lập cho mỗi worker.

### G — Artemis: hai queue anycast cùng address

Một address anycast có queue Q1 và Q2, mỗi queue có hai consumers. Producer gửi vào address.

**Giải thích:** Đây **không** phải một queue có bốn consumers. Broker có thể route message giữa Q1/Q2 theo cơ chế anycast, rồi mỗi queue tiếp tục dispatch tới consumers của riêng nó. Nếu muốn một backlog chung với bốn workers, khai báo **một queue** và bốn consumers.

## 15. Những lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Tạo queue riêng cho mỗi worker | Không còn một backlog chung; routing/scale phức tạp | Một queue, nhiều competing consumers |
| Dùng topic subscriptions độc lập cho pool xử lý việc | Mỗi worker có thể nhận một bản event | Queue hoặc một subscription được chia sẻ theo contract phù hợp |
| Coi `send()` thành công là job hoàn tất | API báo success quá sớm, không biết worker lỗi | Lưu trạng thái job, completion event/query |
| Dùng `AUTO_ACKNOWLEDGE` khi side effect cần commit trước ACK nhưng không kiểm tra semantics | Có thể ACK trước khi DB commit | Transacted receive hoặc ACK có kiểm soát sau DB commit |
| Chia chung JMS Session cho 8 threads | Race/ACK/rollback đè nhau | Mỗi worker/session riêng, hoặc Spring JMS listener container |
| Dùng `JMSMessageID` làm khóa nghiệp vụ | Producer retry tạo message mới gây trùng | `jobId` ổn định + inbox unique key |
| Giả định queue luôn round-robin | Worker chậm giữ nhiều job, tải lệch | Điều chỉnh prefetch/concurrency dựa trên đo |
| Rollback poison job vô hạn | Retry storm, các job tốt bị chậm | Giới hạn attempts, backoff và DLQ |
| Tăng consumer khi downstream đã bão hòa | Thêm timeout và redelivery | Rate limit, tối ưu DB/IO hoặc tách queue |
| Dựa vào JMS ACK để cập nhật “job hoàn tất” | ACK không đồng nghĩa business commit | Business state riêng và idempotency |
| Dùng một queue cho event cần fan-out tới ba service | Mỗi service chỉ nhận một phần message | Topic/durable subscriptions hoặc multicast → queue riêng |
| Cho rằng nhiều consumer giữ global FIFO | Job sau có thể hoàn tất trước job trước | Grouping/partition/sequence control |
| Chỉ đếm queue depth khi autoscale | Không thấy in-flight, job lâu nhất và poison | Đo backlog age, in-flight, completion, retry |
| Đặt huge payload vào JMS message nhỏ không kiểm soát | Heap/disk/network tăng, worker xử lý chậm | Object storage + URI/checksum khi phù hợp |

## 16. Checklist trước production

- [ ] Pool worker thực sự cần **chia một tập job**, không phải mỗi nhóm nhận đủ bản event?
- [ ] Tất cả workers dùng cùng physical JMS queue; Artemis có đúng anycast address/queue?
- [ ] Producer gửi job có `jobId` cố định, schema version và durable publishing/transaction theo yêu cầu?
- [ ] API trả trạng thái queued/accepted, không coi send thành công là kết quả business đã hoàn tất?
- [ ] Mỗi worker/thread có JMS session/consumer riêng hoặc dùng container quản lý concurrency?
- [ ] Có ranh giới DB commit trước JMS commit/ACK và inbox/idempotency theo jobId?
- [ ] Đã thử worker crash trước commit, crash sau side effect, rollback, redelivery, producer retry?
- [ ] Có prefetch/consumer window hợp lý với thời gian xử lý job, không giữ quá nhiều message in-flight?
- [ ] Có policy redelivery/backoff/attempts/DLQ đúng Classic hay Artemis, cùng runbook redrive?
- [ ] Đã đo throughput, p95/p99 processing, oldest pending age, backlog drain và downstream capacity?
- [ ] Có cách xử lý job lỗi vĩnh viễn, job quá hạn, hủy job, truy vết jobId?
- [ ] Có điều kiện nào cần ordering per business key và đã chọn grouping/partition/DB sequence đúng?
- [ ] Đã bảo vệ broker/queue với credentials, ACL, TLS và kiểm tra message validation?
- [ ] Có phương án producer outbox/khôi phục khi broker down, cùng metric producer unknown commit?
- [ ] Đã thử scale từ 1 lên N workers và dừng một worker mà các job còn lại vẫn hoàn tất?

## 17. Kết luận

**Hàng đợi công việc + nhóm competing consumers** là mẫu phù hợp khi nhiều worker cần **chia nhau xử lý một backlog**: producer gửi vào một JMS Queue, broker dispatch cho consumer phù hợp, worker xử lý và ACK/commit. ActiveMQ Classic dùng JMS Queue/destination policy; Artemis thường triển khai bằng **một anycast queue với nhiều consumers**.

Điểm quyết định độ tin cậy **không phải** “message chỉ tới một worker”, mà là **job được hoàn tất an toàn khi có crash, redelivery, retry và scale-out**. Muốn vậy, cần một `jobId` ổn định, transaction/ACK rõ ràng, inbox/idempotency ở nơi lưu kết quả, redelivery có giới hạn và DLQ, đồng thời đo backlog age và công suất downstream. Khi yêu cầu là **fan-out tới nhiều service**, hãy chuyển sang topic/multicast với subscription/queue độc lập thay vì ép nhiều nhóm nghiệp vụ cạnh tranh trên một work queue.
