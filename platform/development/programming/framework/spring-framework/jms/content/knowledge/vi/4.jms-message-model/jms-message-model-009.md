# JMSDeliveryMode, JMSPriority và JMSExpiration

> **Chủ đề:** Mô hình Message trong Spring Framework – JMS (Jakarta Messaging). Ba header này cho biết một thông điệp được gửi với mức bảo đảm truyền tải nào, mức ưu tiên nào và còn hợp lệ đến thời điểm nào. Hiểu đúng chúng giúp thiết kế hàng đợi ổn định, giảm message lỗi thời và tránh kỳ vọng sai về “gửi chắc chắn”, “ưu tiên tuyệt đối” hay “tự hủy tác vụ”.

## 1. Ba header trả lời ba câu hỏi khác nhau

Mỗi message JMS có **body**, **headers** do chuẩn định nghĩa và **properties** dùng cho dữ liệu bổ sung. Khi gửi message, producer có thể chỉ định các tham số chất lượng dịch vụ (QoS): **delivery mode**, **priority**, **time-to-live (TTL)**. JMS provider/broker ghi những thông số đã áp dụng vào các header tương ứng:

| Header trên `jakarta.jms.Message` | Ý nghĩa | Giá trị mặc định của producer | Đơn vị/phạm vi |
| --- | --- | --- | --- |
| `JMSDeliveryMode` | Mức bảo đảm truyền tải khi broker/provider gặp lỗi | `DeliveryMode.PERSISTENT` (giá trị số `2`) | `PERSISTENT` hoặc `NON_PERSISTENT` |
| `JMSPriority` | Mức ưu tiên tương đối khi phân phối message | `4` | Số nguyên từ `0` (thấp nhất) đến `9` (cao nhất) |
| `JMSExpiration` | Mốc thời gian message hết hạn | `0`, vì TTL mặc định bằng `0` | Epoch milliseconds; `0` nghĩa là không hết hạn theo TTL |

**Mối liên hệ quan trọng:** người gửi **không** trực tiếp cấu hình ba trường này bằng `message.setJMSDeliveryMode(...)`, `message.setJMSPriority(...)` hay `message.setJMSExpiration(...)`. Những setter đó phục vụ provider ghi header khi gửi. Ứng dụng phải đặt delivery mode, priority, TTL ở **`MessageProducer` / `JMSProducer` hoặc tham số phương thức `send`**. Sau khi `send` đồng bộ trả về, producer và consumer có thể đọc header để quan sát giá trị thực tế.

Ngoài giá trị do code yêu cầu, broker hoặc cấu hình quản trị có thể **ghi đè** delivery mode, priority, TTL và delivery delay nếu provider hỗ trợ. Khi đó header nhận được phải phản ánh giá trị đã được áp dụng, nên điều cần kiểm tra là **message sau khi gửi/nhận**, không chỉ cấu hình phía Java.

~~~text
Producer (chọn QoS)                    Broker / JMS provider               Consumer
---------------------                  ----------------------               --------
deliveryMode=PERSISTENT  -----+
priority=7                -----+-----> áp dụng chính sách, ghi headers ----> getJMSDeliveryMode()
timeToLive=30_000 ms      -----+        lưu/chuyển/hủy theo cấu hình        getJMSPriority()
                                                                            getJMSExpiration()
~~~

## 2. `JMSDeliveryMode` – độ tin cậy của đường truyền

### 2.1. Hai chế độ được chuẩn hóa

`jakarta.jms.DeliveryMode` định nghĩa đúng hai giá trị:

- **`DeliveryMode.PERSISTENT` (2)**: producer yêu cầu provider dùng cách gửi/lưu bền vững để message có thể sống sót khi provider gặp lỗi theo hợp đồng JMS. Đây là mặc định. Thường phát sinh chi phí ghi lưu trữ, đồng bộ và I/O cao hơn.
- **`DeliveryMode.NON_PERSISTENT` (1)**: ưu tiên giảm overhead; provider không bắt buộc lưu message vào stable storage. Message có thể mất khi provider dừng hoặc hỏng. Hợp với dữ liệu có thể tạo lại hay bỏ lỡ một số lần cập nhật.

Theo hợp đồng *delivery* của Jakarta Messaging, `NON_PERSISTENT` có ngữ nghĩa **at-most-once**; `PERSISTENT` yêu cầu **once-and-only-once** trong điều kiện quản lý và giữ message phù hợp. Phải hiểu giới hạn đó đúng phạm vi: **đây là bảo đảm truyền/giao của JMS provider, không phải bằng chứng side effect của ứng dụng sẽ được thực thi đúng một lần trên database hoặc dịch vụ ngoài**.

Ví dụ: consumer ghi dữ liệu vào database thành công nhưng bị mất kết nối trước khi ack/commit JMS. Sau khi phục hồi, message có thể được redeliver, khiến nghiệp vụ chạy lại nếu không có cơ chế chống trùng. Tương tự, producer gặp timeout sau `send` có thể không biết broker đã nhận hay chưa; retry mù có thể tạo hai message có cùng ý nghĩa nghiệp vụ.

### 2.2. Persistent vẫn có điều kiện

Đặt `PERSISTENT` không tự giải quyết mọi trường hợp sau:
1. Message **hết TTL** trước khi được giao đến consumer.
2. Queue bị xóa/purge, quota hoặc chính sách lưu giữ gây loại bỏ message.
3. Topic dùng **non-durable subscription** và subscriber không hoạt động khi message được publish.
4. Consumer nhận message nhưng lỗi nghiệp vụ/ghi database hoặc ack sai thời điểm.
5. Broker storage/HA được vận hành thiếu dung lượng hoặc chính sách durability không đáp ứng yêu cầu.

Với dữ liệu bắt buộc xử lý (đơn hàng, thanh toán, audit quan trọng), kết hợp `PERSISTENT` với queue bền vững/durable subscription phù hợp, transaction/acknowledge, idempotency, giám sát và chính sách xử lý message lỗi. Với cập nhật trạng thái có thể tạo lại (ví dụ ảnh chụp metrics thường xuyên), `NON_PERSISTENT` có thể hợp lý nếu mất vài bản cập nhật là chấp nhận được.

### 2.3. Đặt delivery mode đúng cách

API cổ điển:

~~~java
// Snippet: producer và message đã được tạo từ một Session hợp lệ.
producer.setDeliveryMode(DeliveryMode.PERSISTENT);
producer.send(message); // Áp dụng mặc định của producer.
~~~

Hoặc chỉ định riêng cho một lần gửi:

~~~java
// Tham số lần lượt: message, deliveryMode, priority, timeToLive (mili giây).
producer.send(message, DeliveryMode.NON_PERSISTENT, 2, 5_000L);
~~~

API rút gọn `JMSProducer`:

~~~java
// Snippet: context là một JMSContext hợp lệ, destination tồn tại.
context.createProducer()
        .setDeliveryMode(DeliveryMode.PERSISTENT)
        .send(destination, "order-created");
~~~

Trong các snippet trên, cần import `jakarta.jms.DeliveryMode` và dùng producer/context do ứng dụng hoặc framework quản lý. Đặt `NON_PERSISTENT` không có nghĩa “luôn nhanh hơn”: tác động tốc độ phải đo với provider, ổ đĩa, ACK, kích cỡ message và tải thực tế.

## 3. `JMSPriority` – ưu tiên phân phối, không phải lịch xử lý tuyệt đối

JMS quy định **10 mức**, từ `0` đến `9`, mặc định `4`:
- `0–4`: các mức *normal priority*.
- `5–9`: các mức *expedited priority*.

Provider được khuyến khích cố gắng giao message ưu tiên cao trước message bình thường, **nhưng đặc tả không bắt buộc sắp xếp tuyệt đối theo priority**. Một message có priority `9` không được bảo đảm đến consumer trước mọi message `4` đã gửi trước đó, đặc biệt khi có nhiều consumer, prefetch/buffer, message đã được giao trước, transaction hoặc cạnh tranh tài nguyên.

Ví dụ: hàng đợi có 10.000 yêu cầu tạo báo cáo ở priority `4`, sau đó có một yêu cầu cảnh báo khẩn cấp priority `9`. Broker có thể ưu tiên message cảnh báo còn đang ở queue; nhưng **không thể “rút lại” một tác vụ dài mà consumer đã nhận và đang xử lý**. Tăng priority cũng không tạo thêm CPU, thread hay database connection.

**Rủi ro starvation:** nếu liên tục có lượng lớn message mức cao, nhóm mức thấp có thể đợi lâu. Vì thế, khi hai loại công việc có SLA rất khác nhau, cân nhắc **queue riêng**, hạn mức concurrency và capacity planning thay vì chỉ dựa vào con số `9`.

### 3.1. Cấu hình và quan sát

~~~java
// Snippet: dùng mặc định cho các send tiếp theo của producer.
producer.setPriority(7);
producer.send(message);

// Hoặc chỉ định cho duy nhất một lần gửi.
producer.send(message, DeliveryMode.PERSISTENT, 7, 30_000L);
~~~

Sau gửi hoặc trong consumer:

~~~java
int appliedPriority = receivedMessage.getJMSPriority(); // 0..9
~~~

`message.setJMSPriority(9)` **không phải** cách chọn priority cho lần gửi: provider sẽ đặt lại header theo thiết lập producer/send và cấu hình quản trị. Nếu muốn gán mức khẩn cấp theo nghiệp vụ, ánh xạ có kiểm soát (ví dụ `NORMAL=4`, `URGENT=7`) và bảo đảm producer không vô tình gửi tất cả message với priority `9`.

### 3.2. Priority khác với thời hạn

**Urgent** không đồng nghĩa **còn giá trị lâu**. Message cập nhật báo giá nóng có thể priority cao nhưng TTL rất ngắn; message tạo hóa đơn có thể priority trung bình nhưng TTL không hết hạn hoặc thời hạn nghiệp vụ dài. Hãy đưa ra quyết định **độc lập** cho priority và TTL.

## 4. `JMSExpiration` – thời điểm hết hạn, bắt nguồn từ time-to-live

### 4.1. Phân biệt TTL và expiration

- **TTL (`timeToLive`)**: khoảng thời gian producer yêu cầu message còn hợp lệ, tính bằng **mili giây**. Đặt qua `MessageProducer.setTimeToLive(long)`, `JMSProducer.setTimeToLive(long)` hoặc tham số `send`.
- **`JMSExpiration`**: timestamp tuyệt đối do provider tính và ghi vào header khi gửi; đơn vị là **mili giây kể từ 1970-01-01T00:00:00Z**.

Với TTL lớn hơn `0` và không bị cấu hình quản trị ghi đè:

~~~text
JMSExpiration = thời điểm send + timeToLive (milliseconds)
~~~

Với TTL bằng `0`, `JMSExpiration = 0`, nghĩa là **không hết hạn do JMS TTL**. Giá trị `0` **không có nghĩa “hết hạn ngay”**; cũng không đảm bảo message được giữ vô hạn vì broker còn có retention, quota và chính sách vận hành riêng.

Ví dụ minh họa bằng mốc thời gian:

~~~text
Producer gửi: 10:00:00.000 UTC
TTL:           30_000 ms (30 giây)
JMSExpiration: 10:00:30.000 UTC

10:00:02  Broker nhận, message còn hợp lệ
10:00:15  Consumer có thể nhận
10:00:30  Mốc hết hạn với message chưa được giao
10:00:40  Consumer bắt đầu nhận mới: message đã hết hạn không nên được giao
~~~

Khi message chưa được giao mà hết hạn, provider **nên loại bỏ** message. JMS không định nghĩa một thông báo hết hạn chuẩn gửi cho producer. Ứng dụng **không nên nhận** message đã hết hạn, nhưng đặc tả không bảo đảm tuyệt đối điều đó sẽ không xảy ra; provider cũng không có độ chính xác tính giờ được chuẩn hóa đến từng mili giây.

### 4.2. TTL tính từ lúc send, kể cả khi dùng transaction

Giả sử producer gửi trong JMS transacted session lúc `10:00:00` với TTL `5 s`, nhưng transaction chỉ commit lúc `10:00:08`. Theo Jakarta Messaging, expiration vẫn tính từ **thời điểm client gọi send**, không tính lại từ lúc commit. Do đó message có thể hết hạn trước khi transaction làm nó khả dụng cho consumer.

Điều này quan trọng khi có batching lớn, transaction dài hoặc network congestion. **TTL ngắn + transaction commit chậm** là một nguyên nhân khiến message “gửi thành công” nhưng không được consumer thấy.

### 4.3. Expiration không phải hủy tác vụ đang chạy

Nếu consumer đã nhận message trước mốc hết hạn và đang gọi database hoặc dịch vụ khác, **TTL không tự dừng thread, rollback transaction hoặc hủy request ngoài**. Nếu nghiệp vụ phải dừng sau deadline, consumer cần kiểm tra deadline nghiệp vụ một cách độc lập và định nghĩa hành động khi quá hạn.

Ngược lại, `JMSExpiration = 0` không thay thế cơ chế xử lý poison message, retry limit hay DLQ. Đó là những chính sách khác.

### 4.4. Đặt và đọc TTL/expiration

~~~java
// Snippet: TTL cho các lần gửi tiếp theo bằng producer này.
producer.setTimeToLive(15_000L); // 15 giây
producer.send(message);

// TTL cụ thể cho một lần gửi, đồng thời chỉ định mode + priority.
producer.send(message, DeliveryMode.PERSISTENT, 7, 15_000L);

// Trên message sau send đồng bộ, hoặc trên message đã nhận:
long expiresAtMillis = message.getJMSExpiration();
boolean neverExpiresByTtl = (expiresAtMillis == 0L);
~~~

Đừng gọi `message.setJMSExpiration(System.currentTimeMillis() + 15_000)` để cấu hình TTL: provider có thể ghi đè hoàn toàn. Cũng không dùng một giá trị TTL âm; dùng `0` khi không muốn TTL. `JMSExpiration` là timestamp tuyệt đối, **không phải số mili giây còn lại**; nếu cần biểu diễn thời gian còn lại, tính bằng `expiresAtMillis - System.currentTimeMillis()` và chỉ coi là ước lượng tại thời điểm quan sát.

## 5. Ba thuộc tính phối hợp trong cùng một message

Một message `create-report` có thể cấu hình:

~~~text
deliveryMode = PERSISTENT
priority     = 7
timeToLive   = 60_000 ms
                    |
                    v
JMSDeliveryMode = 2 (PERSISTENT)
JMSPriority     = 7
JMSExpiration   = thời điểm gửi + 60 giây
~~~

Ý nghĩa: yêu cầu được lưu/truyền theo chế độ persistent, được ưu tiên hơn các mức normal *nếu broker có thể sắp xếp lại*, nhưng không còn giá trị để **giao mới** sau mốc hết hạn. **Không có mâu thuẫn** giữa `PERSISTENT` và TTL: “bền vững khi broker gặp lỗi” không có nghĩa “không bao giờ hết hạn”.

| Tình huống | Delivery mode gợi ý | Priority gợi ý | TTL gợi ý | Lưu ý |
| --- | --- | --- | --- | --- |
| Sự kiện tạo đơn bắt buộc không bỏ sót | `PERSISTENT` | `4` | `0` hoặc theo SLA nghiệp vụ rõ ràng | Dùng durable queue/transaction/idempotency; tránh TTL ngắn không có căn cứ |
| Snapshot cảm biến lặp lại liên tục | `NON_PERSISTENT` nếu chịu được mất mẫu | `2–4` | Rất ngắn, ví dụ vài giây | Giá trị cũ vô ích; kiểm tra sampling/replay requirement |
| Lệnh cập nhật trạng thái khẩn cấp | `PERSISTENT` nếu quan trọng | `7–9` | Theo deadline thực tế | Priority không preempt tác vụ đang chạy |
| Thông báo quảng bá ít quan trọng | Tùy mức chấp nhận mất | `1–4` | Theo thời điểm còn hữu ích | Không giữ message lỗi thời gây tồn đọng |
| Job tạo báo cáo dài | Thường `PERSISTENT` | `4` | Có thể `0` | Theo dõi timeout ở job state; TTL không tự hủy job |

Các con số trên chỉ là ví dụ **quyết định nghiệp vụ**, không phải mặc định bắt buộc hay SLA của Artemis/Spring. Bắt đầu từ hậu quả khi mất message, mức độ khẩn cấp và thời gian dữ liệu còn có ích; sau đó chọn QoS phù hợp.

## 6. So sánh API cách đặt QoS và cách đọc header

| Cách gửi | Cú pháp chính | Phạm vi hiệu lực |
| --- | --- | --- |
| JMS classic API | `producer.setDeliveryMode(mode)`, `setPriority(n)`, `setTimeToLive(ms)` | Giá trị mặc định cho các send của producer |
| JMS classic API | `producer.send(message, mode, priority, ttl)` | Ghi đè giá trị mặc định của producer cho lần gửi cụ thể |
| JMS simplified API | `context.createProducer().setDeliveryMode(...).setPriority(...).setTimeToLive(...).send(destination, body)` | QoS trên `JMSProducer` đó |
| Spring `JmsTemplate` | `setDeliveryMode`, `setPriority`, `setTimeToLive` + `setExplicitQosEnabled(true)` | Các send qua template đó khi bật explicit QoS |
| Bên nhận | `getJMSDeliveryMode()`, `getJMSPriority()`, `getJMSExpiration()` | Đọc header do provider thiết lập |

Ba header thuộc **JMS-defined headers**, không phải custom application properties. `message.setStringProperty("priority", "7")` chỉ tạo một property tùy ý tên `priority`, **không** thay đổi `JMSPriority`. Ngược lại, JMS message selector có thể sử dụng `JMSPriority` làm điều kiện số; khi dùng `JMSDeliveryMode` trong selector, giá trị được biểu diễn bằng chuỗi `'PERSISTENT'` hoặc `'NON_PERSISTENT'`. Tránh phụ thuộc selector để “bù” cho một policy ưu tiên/TTL chưa được thiết kế.

## 7. Ví dụ chạy được: Jakarta JMS qua Spring Boot và ActiveMQ Artemis

Đây là một ứng dụng Java 17 chạy bằng Gradle, dùng Spring Boot 3.3.x để tạo `ConnectionFactory` và sử dụng trực tiếp API `jakarta.jms` nhằm nhìn thấy các header thực tế **sau khi send và sau khi receive**.

**Điều kiện chạy:** có ActiveMQ Artemis broker ở `tcp://localhost:61616`, tài khoản `demo/demo`, queue `demo.qos` (tạo sẵn hoặc broker cho phép auto-create) và quyền producer/consumer. Đây là cấu hình demo local; môi trường thật nên dùng secret và TLS theo chính sách hệ thống. Với demo này không cần cài Spring MVC hoặc chạy HTTP server.

**Cấu trúc:**

~~~text
jms-qos-headers/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/QosHeadersApplication.java
    └── resources/application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'jms-qos-headers'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
}
~~~

`src/main/resources/application.yml`:

~~~yaml
spring:
  main:
    web-application-type: none
  artemis:
    mode: native
    broker-url: tcp://localhost:61616
    user: demo
    password: demo
  jms:
    cache:
      enabled: false
~~~

Tắt cache trong demo chỉ để việc cấp phát/đóng connection phản ánh JMS API trực tiếp; **không** phải một khuyến nghị mặc định cho ứng dụng production.

`src/main/java/demo/QosHeadersApplication.java`:

~~~java
package demo;

import java.util.UUID;

import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import jakarta.jms.Message;
import jakarta.jms.MessageConsumer;
import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class QosHeadersApplication implements ApplicationRunner {

    private final ConnectionFactory connectionFactory;

    public QosHeadersApplication(ConnectionFactory connectionFactory) {
        this.connectionFactory = connectionFactory;
    }

    public static void main(String[] args) {
        SpringApplication.run(QosHeadersApplication.class, args);
    }

    @Override
    public void run(ApplicationArguments args) throws Exception {
        String traceKey = UUID.randomUUID().toString();

        try (Connection connection = connectionFactory.createConnection();
             Session session =
                     connection.createSession(Session.AUTO_ACKNOWLEDGE)) {

            Queue destination = session.createQueue("demo.qos");
            String selector = "traceKey = '" + traceKey + "'";

            try (MessageProducer producer = session.createProducer(destination);
                 MessageConsumer consumer =
                         session.createConsumer(destination, selector)) {

                TextMessage outgoing = session.createTextMessage("create-report");
                outgoing.setStringProperty("traceKey", traceKey);

                // QoS của đúng lần gửi này: persistent, priority 7, TTL 60s.
                producer.send(
                        outgoing,
                        DeliveryMode.PERSISTENT,
                        7,
                        60_000L
                );

                printHeaders("sent", outgoing);

                // Classic JMS Connection chỉ giao message khi started.
                connection.start();
                Message incoming = consumer.receive(5_000L);

                if (!(incoming instanceof TextMessage textMessage)) {
                    throw new IllegalStateException(
                            "Did not receive expected TextMessage");
                }

                System.out.println("received.body=" + textMessage.getText());
                printHeaders("received", incoming);
            }
        }
    }

    private static void printHeaders(String prefix, Message message)
            throws Exception {
        int mode = message.getJMSDeliveryMode();
        String modeName = switch (mode) {
            case DeliveryMode.PERSISTENT -> "PERSISTENT";
            case DeliveryMode.NON_PERSISTENT -> "NON_PERSISTENT";
            default -> "UNKNOWN";
        };

        System.out.println(prefix + ".mode=" + modeName);
        System.out.println(prefix + ".priority=" + message.getJMSPriority());
        System.out.println(prefix + ".hasExpiration="
                + (message.getJMSExpiration() > 0L));
    }
}
~~~

Chạy tại thư mục dự án với JDK 17+ và Gradle đã cài (hoặc Gradle wrapper nếu đã tạo):

~~~bash
gradle bootRun
~~~

Với broker hoạt động, queue khả dụng, không có cấu hình ghi đè QoS và message được nhận trong 5 giây, phần **stdout của ứng dụng** là:

~~~text
sent.mode=PERSISTENT
sent.priority=7
sent.hasExpiration=true
received.body=create-report
received.mode=PERSISTENT
received.priority=7
received.hasExpiration=true
~~~

Spring Boot và Artemis có thể in thêm log khởi động/kết nối. `traceKey` ngẫu nhiên được dùng trong selector để chỉ nhận message thuộc lần chạy hiện tại, tránh nhầm với bản ghi tồn từ lần chạy trước. Đoạn này **không khẳng định thứ tự phân phối message theo priority** vì chỉ gửi một message.

**Giải thích từng bước:**
1. Spring Boot cấu hình `ConnectionFactory` cho Artemis dựa trên `application.yml`.
2. Chương trình tạo connection, session, queue, producer và consumer có selector riêng.
3. `outgoing.setStringProperty("traceKey", ...)` đặt property phục vụ lọc; nó **không** đặt QoS.
4. `producer.send(outgoing, DeliveryMode.PERSISTENT, 7, 60_000L)` yêu cầu provider áp dụng ba tham số cho lần gửi này.
5. Khi `send` đồng bộ hoàn tất, producer đọc `JMSDeliveryMode`, `JMSPriority`, `JMSExpiration` từ message mà provider đã cập nhật.
6. `connection.start()` bật nhận; consumer đọc cùng bộ header và body. Khi kết thúc, `try-with-resources` đóng tài nguyên.

Nếu broker không tồn tại, thông tin truy cập sai, destination chưa được tạo và broker không cho auto-create, message hết hạn quá sớm, hoặc có consumer khác cạnh tranh theo selector, kết quả có thể khác hoặc chương trình ném exception. Không dùng output mẫu để khẳng định mọi provider luôn áp dụng QoS giống nhau. Với ứng dụng đã được quản lý bởi Spring, nên dùng `JmsTemplate`/listener container như phần tiếp theo.

## 8. Thiết lập QoS trong Spring `JmsTemplate`

Spring `JmsTemplate` nhận `ConnectionFactory`, thực hiện gửi/nhận và dọn tài nguyên theo cấu hình framework. Với nhu cầu QoS, chi tiết dễ bị bỏ quên là:

**`setDeliveryMode`, `setPriority`, `setTimeToLive` phải được kết hợp với `setExplicitQosEnabled(true)`** nếu muốn `JmsTemplate` chủ động truyền các giá trị đó vào phương thức send. Khi `explicitQosEnabled=false` (mặc định), template sử dụng các mặc định do producer/provider/thiết lập quản trị quyết định; ba field cấu hình trên template không tự động ghi đè send.

Ví dụ cấu hình bean (đây là **đoạn mã Spring**, sử dụng cùng project/ConnectionFactory; không phải file Java độc lập):

~~~java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;

@Configuration
public class ReportMessagingConfig {

    @Bean
    JmsTemplate reportJmsTemplate(ConnectionFactory factory) {
        JmsTemplate template = new JmsTemplate(factory);
        template.setExplicitQosEnabled(true);
        template.setDeliveryMode(DeliveryMode.PERSISTENT);
        template.setPriority(7);
        template.setTimeToLive(60_000L);
        return template;
    }
}
~~~

Dùng bean trong một Spring service (snippet cần import `org.springframework.stereotype.Service`):

~~~java
@Service
public class ReportPublisher {

    private final JmsTemplate reportJmsTemplate;

    public ReportPublisher(JmsTemplate reportJmsTemplate) {
        this.reportJmsTemplate = reportJmsTemplate;
    }

    public void publish(String reportId) {
        reportJmsTemplate.convertAndSend("demo.qos", reportId);
    }
}
~~~

Hai snippet `ReportMessagingConfig` và `ReportPublisher` là các class minh họa khi đã có Spring context; nếu thêm vào **cùng** ứng dụng `QosHeadersApplication` ở mục 7, cần đặt file tương ứng dưới package `demo` và thêm `package demo;` để Spring component scan tìm thấy. Đây không phải code có thể chạy trực tiếp bằng `javac ReportPublisher.java` mà không có Spring dependencies.

Một `JmsTemplate` chia sẻ giữa nhiều thread nên được **cấu hình một lần khi khởi tạo**, không sửa `setPriority(...)` hoặc `setTimeToLive(...)` qua lại ngay trước mỗi `convertAndSend` vì các lệnh gửi concurrent có thể dùng giá trị của nhau. Nếu từng loại message cần QoS khác nhau, cân nhắc **template/producer chuyên dụng** hoặc dùng classic JMS `send(message, mode, priority, ttl)` theo từng lần gửi. Tránh dựa vào `MessagePostProcessor` để gọi trực tiếp các setter `setJMSPriority`/`setJMSExpiration`: đây là header do provider quản lý.

Spring cũng hỗ trợ `QosSettings` để nhóm delivery mode, priority và TTL; bản chất vẫn là cấu hình QoS trên template, không thay đổi hợp đồng JMS.

## 9. Những giới hạn phải hiểu trước khi đưa vào production

### 9.1. TTL khác delivery delay

`JMSExpiration` trả lời **“đến khi nào message còn được giao”**, còn `JMSDeliveryTime` trả lời **“sớm nhất khi nào message có thể được giao”** khi có delivery delay. Hai mốc là độc lập, được tính từ thời điểm send theo tham số tương ứng.

Ví dụ gửi lúc `10:00:00`, delivery delay `20 s`, TTL `10 s`: message hết hạn lúc `10:00:10` trước khi được phép giao sớm nhất lúc `10:00:20`. Đừng đặt delay dài hơn TTL trừ khi có mục đích rõ và biết hệ quả. API `JMSProducer.setDeliveryDelay(...)` hoặc cơ chế của producer là một tính năng riêng, không thay thế TTL.

### 9.2. Expiration không phải deadline nghiệp vụ

Giả sử job phải kết thúc trước 12:00. Nếu gửi message lúc 11:59:59 với TTL `30 s`, message có thể được consumer nhận sau 12:00 mà vẫn chưa hết TTL. Deadline nghiệp vụ phải được lưu tường minh, ví dụ `businessDeadline` trong payload/property, và được kiểm tra ở consumer trước khi thực hiện hành động.

Ngược lại, nếu đã giao message và worker đang chạy, JMS TTL không thu hồi những thay đổi database hay ngắt tác vụ. Dùng cancellation/timeout/idempotency riêng nếu cần.

### 9.3. Priority không đảm bảo SLA cứng

Một queue chung với nhiều loại message có thể gây head-of-line blocking, đặc biệt khi consumer đã lấy một batch lớn vào buffer. Không dùng priority thay thế cho tách luồng khẩn cấp, giới hạn tải, quota, autoscaling hoặc thiết kế công việc có thể dừng an toàn. Đo **queue age theo mức ưu tiên**, không chỉ tổng queue depth.

### 9.4. Persistent không bảo đảm exactly-once cho database

Với message quan trọng, phân biệt ba lớp:
1. **Producer → broker**: đã gửi thành công, có thể gặp kết quả mơ hồ do mất kết nối.
2. **Broker → consumer**: phụ thuộc retention, persistent/non-persistent, TTL, ack và transaction.
3. **Consumer → side effect**: database/API khác nằm ngoài hợp đồng delivery mode; cần thiết kế idempotency hoặc transaction phù hợp.

Để chống trùng do retry/redelivery, message nên có **eventId/commandId** ổn định. Consumer ghi nhận ID đã xử lý trong cùng transaction database với side effect, dùng unique constraint hoặc cơ chế nguyên tử tương đương. Tăng priority hay đặt persistent không tự giải quyết trạng thái trùng lặp.

### 9.5. Broker có thể ghi đè và loại bỏ message

Điều kiện vận hành có thể ảnh hưởng hành vi quan sát được: địa chỉ queue, durable subscription, storage sync, expiry address, dead-letter address, limits, TTL overrides, max delivery attempts và cách provider xử lý expired message. JMS API không quy định việc expiry message nhất thiết sẽ được đưa vào DLQ hoặc gửi thông báo cho producer. Kiểm tra cấu hình và số liệu thực tế của Artemis/broker đang dùng.

## 10. Kiểm thử và giám sát có ý nghĩa

| Ca kiểm thử | Thiết lập | Điều cần xác nhận |
| --- | --- | --- |
| Header mặc định | Gửi không cấu hình QoS | Mode mặc định `PERSISTENT`, priority `4`, expiration `0` nếu broker không override |
| Gửi explicit QoS | Send mode `PERSISTENT`, priority `7`, TTL `60_000` | Header thực tế của message sau send và ở consumer |
| Message hết hạn | Đặt TTL ngắn, cho consumer nhận trễ có kiểm soát | Message không còn được giao theo chính sách provider; đo expired count, không suy diễn từ mỗi `receive` timeout |
| Ưu tiên cao | Tạo backlog mức `4` rồi thêm mức `9` | Đo độ trễ; **không** viết test yêu cầu luôn nhận priority `9` trước mọi message khác |
| Broker restart | Gửi persistent và non-persistent, dừng rồi khởi động lại theo điều kiện test | Xác minh kết quả với cấu hình storage/retention; không đồng nhất tất cả provider |
| Transaction dài | Send có TTL ngắn, trì hoãn commit | Xác minh expiry tính từ send, không được reset bởi commit |
| Spring QoS | Tắt/bật `explicitQosEnabled` | Xác nhận các setter trên template chỉ được áp dụng theo chế độ explicit |
| DLQ và expiry | Đặt policy rõ ràng của broker | Xác minh expired message đi đâu và quy trình giám sát/cleanup |

Trong hệ thống thực, nên theo dõi số message **persistent/non-persistent**, phân bố priority, tuổi message còn chờ, tỷ lệ expired, queue depth, send latency, redelivery, DLQ/expiry queue, lỗi disk/broker và SLA xử lý nghiệp vụ. Các chỉ số này giúp xác định TTL quá ngắn, priority gây starvation hoặc retention không phù hợp.

**Lưu ý kiểm thử:** dùng broker cô lập và queue riêng cho bài thử, vì gửi message với TTL ngắn hay restart broker có thể làm mất dữ liệu thử nghiệm. Không áp dụng thử nghiệm phá hủy lên queue nghiệp vụ.

## 11. Các lỗi phổ biến và cách sửa

| Cách hiểu/cách làm sai | Vì sao sai | Cách đúng |
| --- | --- | --- |
| `message.setJMSPriority(9)` để gửi ưu tiên | Provider ghi đè header khi gửi | Dùng `producer.setPriority(9)` hoặc tham số `send` |
| `message.setJMSExpiration(now + ttl)` để đặt TTL | Expiration được provider tính từ time-to-live | Dùng `producer.setTimeToLive(ttl)`/`send(..., ttl)` |
| `JMSExpiration=0` là hết hạn ngay | `0` nghĩa là không hết hạn theo TTL | Chọn TTL dương khi message cần có hạn |
| `PERSISTENT` là chắc chắn database cập nhật đúng một lần | JMS delivery và side effect là hai phạm vi khác nhau | Transaction/ack, idempotency và kiểm soát retry |
| Priority `9` chắc chắn chạy trước priority `4` | Đặc tả chỉ yêu cầu provider cố gắng ưu tiên | Benchmark, tách queue/SLA khi cần |
| Bật `setPriority(7)` trên `JmsTemplate` là đủ | Mặc định explicit QoS tắt | Kết hợp `setExplicitQosEnabled(true)` |
| TTL `5000` được hiểu là 5000 giây | TTL tính bằng mili giây | `5000 ms = 5 giây` |
| TTL tự dừng job đã nhận | TTL chi phối khả năng giao message, không hủy side effect | Consumer kiểm tra deadline và cancellation riêng |
| Message hết hạn chắc chắn vào DLQ | Đặc tả không bắt buộc cách xử lý expiry | Xem broker expiry address/retention policy |
| Đặt `NON_PERSISTENT` cho event đơn hàng để tối ưu throughput | Có thể mất message khi broker failure | Đánh giá chi phí mất message và chọn mode phù hợp |

## 12. Câu hỏi tự kiểm tra

1. Tại sao `JMSExpiration` lưu epoch milliseconds trong khi producer cấu hình bằng TTL tương đối?
2. `JMSExpiration=0` có bảo đảm broker giữ message mãi không? Vì sao?
3. Một message `PERSISTENT`, priority `9` nhưng đã hết hạn có bắt buộc đến consumer không?
4. Khi consumer đã nhận message, TTL hết hạn có làm Spring tự rollback database transaction không?
5. Vì sao `JmsTemplate.setTimeToLive(10_000L)` chưa chắc được áp dụng nếu thiếu `setExplicitQosEnabled(true)`?
6. Khi dùng `producer.send(message, DeliveryMode.NON_PERSISTENT, 3, 5_000L)`, các setter QoS mặc định trước đó trên producer còn chi phối lần gửi này không?
7. Nếu một message priority cao bị kẹt sau nhiều tác vụ đang chạy, dùng priority `9` có đủ để cam kết SLA không?
8. Tại sao “JMS once-and-only-once delivery” khác với “database side effect exactly-once”?

**Ghi nhớ:**
- `JMSDeliveryMode`: chính sách độ tin cậy khi **truyền/giao** message.
- `JMSPriority`: **gợi ý mức ưu tiên** từ `0` đến `9`, không phải thứ tự bắt buộc.
- `JMSExpiration`: **thời điểm hết hạn** được provider tính từ TTL; `0` nghĩa là không hết hạn theo TTL.
- Đặt QoS trên **producer/send/JmsTemplate với explicit QoS**; kiểm tra header thực tế để biết provider đã áp dụng gì.
- Đánh giá đầy đủ consumer, transaction, retention và deadline nghiệp vụ trước khi chọn giá trị production.

## Tài liệu tham khảo

1. Jakarta Messaging 3.1 Specification, `3.4.2`, `3.4.9–3.4.12`, `7.4`, `7.7–7.9`: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
2. Jakarta Messaging 3.1 API – Message: https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message
3. Jakarta Messaging 3.1 API – MessageProducer: https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageproducer
4. Jakarta Messaging 3.1 API – DeliveryMode: https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/deliverymode
5. Spring Framework – JMS: https://docs.spring.io/spring-framework/reference/integration/jms.html
6. Spring Framework – JmsTemplate Javadoc: https://docs.spring.io/spring-framework/docs/6.1.16/javadoc-api/org/springframework/jms/core/JmsTemplate.html
7. Spring Boot – Messaging / JMS: https://docs.spring.io/spring-boot/3.3/reference/messaging/jms.html
