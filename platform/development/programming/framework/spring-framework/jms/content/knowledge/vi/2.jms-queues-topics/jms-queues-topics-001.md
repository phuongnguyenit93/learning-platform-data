# Point-to-point và mô hình Queue trong Spring JMS

## 1. Mục tiêu và bối cảnh

**Point-to-point (PTP)** là mô hình gửi thông điệp đến một **Queue (hàng đợi)** để một trong các consumer đủ điều kiện xử lý mỗi lần giao thông điệp. Đây là một trong hai mô hình đích (*messaging domain*) của Jakarta Messaging (JMS); mô hình còn lại là **publish/subscribe** với Topic.

Sau bài học, bạn cần giải thích được đường đi của một message từ producer đến broker và consumer, phân biệt Queue với Topic, triển khai producer và nhiều consumer bằng Spring JMS, hiểu acknowledgment/transaction/redelivery, và nhận biết những giới hạn về thứ tự, khả năng lặp và khả năng phục hồi.

Ví dụ xuyên suốt: dịch vụ đặt hàng gửi yêu cầu `ORDER-001` vào `orders.queue`; một worker xử lý đơn. Nếu tăng số worker, chúng **cạnh tranh để lấy việc từ cùng queue**, không phải mỗi worker đều nhận một bản sao.

## 2. Các thành phần và luồng xử lý

- **Producer (sender):** tạo và gửi message, thường thông qua `JmsTemplate` hoặc `JmsClient` (Spring Framework 7+).
- **Queue:** đích JMS chứa các message đang chờ giao/xử lý theo cơ chế của broker.
- **Broker / JMS provider:** hệ thống triển khai JMS (ví dụ ActiveMQ Artemis), quản lý lưu trữ, điều phối, acknowledgment, giao lại và chính sách lỗi. Queue không đơn thuần là `java.util.Queue` nằm trong bộ nhớ ứng dụng.
- **Consumer (receiver/worker):** nhận message bằng `MessageConsumer`, `JMSConsumer` hoặc listener của Spring.
- **ConnectionFactory và Session:** cung cấp kết nối và ngữ cảnh xử lý JMS; Spring thường quản lý vòng đời thay cho mã nghiệp vụ.
- **Acknowledgment / commit:** tín hiệu giúp broker quyết định thông điệp đã được xử lý thành công hay phải tiếp tục ở trạng thái chờ/giao lại.

~~~mermaid
flowchart LR
    P1["Producer A"] --> Q[("orders.queue")]
    P2["Producer B"] --> Q
    Q --> C1["Consumer 1"]
    Q --> C2["Consumer 2"]
    Q --> C3["Consumer 3"]
~~~

**Cách đọc sơ đồ:** ba mũi tên từ queue đến các consumer biểu diễn *những lựa chọn nhận việc*. Chúng không có nghĩa rằng cùng một message được phát đồng thời đến cả ba consumer. Một lần giao message đi đến một consumer; trong trường hợp lỗi, **cùng message có thể được giao lại**.

Vòng đời điển hình:

1. Producer tạo payload và tùy chọn headers/properties như mã đơn hàng, độ ưu tiên, thời hạn sống.
2. Producer gửi tới đích `orders.queue`; khi gửi thành công theo giao thức của provider, broker tiếp nhận message. Nếu gửi trong transaction, chỉ sau commit message mới khả dụng cho consumer.
3. Broker chọn một consumer đang đủ điều kiện (có thể dựa trên khả năng nhận, selector, prefetch và chính sách của provider).
4. Consumer nhận và thực hiện nghiệp vụ. Message có thể ở trạng thái *in-flight*, chưa được xác nhận hoàn tất.
5. Khi acknowledgment hoặc JMS transaction commit thành công, broker coi lần giao đó đã hoàn tất. Nếu rollback, session mất kết nối hoặc có sự cố phù hợp với chính sách redelivery, message có thể quay lại hàng đợi để giao tiếp.

Có thể có **nhiều producer và nhiều consumer** trên cùng queue. Queue giúp tách thời điểm gửi khỏi thời điểm xử lý: khi worker bận hoặc tạm dừng, message có thể tồn đọng (backlog), tùy cấu hình dung lượng, persistence và expiry của broker.

## 3. Các quy tắc quan trọng của Queue

### 3.1. Một lần giao đến một consumer: competing consumers

Khi có ba message M1, M2, M3 và hai consumer C1, C2, một phân phối *có thể* là C1 nhận M1 và M3, C2 nhận M2. Cách phân phối thực tế không được tiêu chuẩn JMS buộc phải round-robin hay công bằng tuyệt đối.

| Đặc tính | Queue (point-to-point) | Topic (publish/subscribe) |
| --- | --- | --- |
| Mục đích | Phân phối công việc cho một consumer mỗi lần giao | Phát sự kiện tới nhiều subscription |
| Nhiều consumer/subscriber | Cạnh tranh nhận các message trên cùng queue | Mỗi subscription phù hợp có thể nhận bản sao |
| Khi bên nhận chưa chạy | Message có thể chờ trên queue theo chính sách broker | Phụ thuộc loại subscription (durable/non-durable) |
| Điển hình | Xử lý đơn hàng, tác vụ nền, gửi email | Thông báo sự kiện cho nhiều hệ thống |

**Không nhầm “một consumer mỗi lần giao” với “xử lý đúng một lần mãi mãi”.** Khi chưa commit/ack thành công, provider có thể giao lại cùng message, kể cả cho consumer khác.

### 3.2. Queue không tự hứa hẹn thứ tự xử lý toàn cục

JMS có các quy tắc thứ tự trong những điều kiện xác định, nhưng không cam kết rằng nhiều worker xử lý xong theo đúng thứ tự producer gửi. Chẳng hạn C1 nhận M1 và chạy 5 giây, C2 nhận M2 và hoàn thành sau 100 ms: kết quả M2 xuất hiện trước M1. Ngoài ra còn có priority, TTL, delivery delay, nhiều producer/session và redelivery.

Nếu yêu cầu **thứ tự nghiêm ngặt**, cân nhắc giới hạn concurrency cho luồng tương ứng xuống 1, hoặc dùng cơ chế gom nhóm/định tuyến theo khóa thực thể mà provider hỗ trợ (ví dụ message group). Cần đánh đổi throughput, và phải kiểm chứng hành vi của broker cụ thể.

### 3.3. Không đồng nhất queue với cơ sở dữ liệu công việc

Broker quản lý việc giao message, nhưng thường không tự thay thế cơ sở dữ liệu trạng thái nghiệp vụ. Với đơn hàng, payload nên mang `orderId` hoặc `eventId`; trạng thái “đã thanh toán/đã hoàn tất” cần được xác nhận trong hệ thống lưu trữ nghiệp vụ. Một message có thể hết hạn, bị đưa sang dead-letter queue hoặc bị xóa theo chính sách quản trị.

## 4. Kiến trúc Spring JMS

Trong Spring Framework, thông thường mã ứng dụng làm việc ở tầng cao:

- **`JmsTemplate`:** gửi bằng `convertAndSend`, gửi message tùy biến bằng `send`, nhận đồng bộ bằng `receive`/`receiveAndConvert`. Bean đã cấu hình có thể dùng chung giữa các thread.
- **`@JmsListener`:** khai báo hàm nhận bất đồng bộ; Spring tạo listener container và chuyển payload, headers hoặc raw `jakarta.jms.Message` vào tham số.
- **`DefaultJmsListenerContainerFactory`:** cấu hình container cho các listener, gồm connection factory, session transaction, concurrency, message converter.
- **`ConnectionFactory`:** tạo kết nối đến JMS provider; Spring Boot có auto-configuration cho Artemis khi có starter phù hợp.
- **`MessageConverter`:** biến dữ liệu Java thành JMS message và ngược lại. Với chuỗi, converter mặc định thường tạo `TextMessage`.

Từ Spring Framework 6 / Spring Boot 3, API JMS dùng namespace **`jakarta.jms.*`** thay vì `javax.jms.*` của hệ cũ; không trộn hai họ thư viện trong cùng ví dụ. Các ví dụ dưới đây dùng Java 17 và Spring Boot 3.5.x.

## 5. Ví dụ có thể chạy: một Queue, hai consumer cạnh tranh

Ứng dụng chạy **ActiveMQ Artemis embedded** để học trên máy cục bộ. Broker nhúng ở đây được cấu hình *không ghi bền xuống đĩa*, chỉ phục vụ thực hành; hệ thống thật nên cấu hình broker riêng, persistence, bảo mật và giám sát thích hợp.

Yêu cầu: **JDK 17+** và **Maven 3.6.3+**. Cấu trúc thư mục:

~~~text
queue-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/queuedemo/
    │   ├── QueueDemoApplication.java
    │   └── OrderConsumer.java
    └── resources/application.properties
~~~

### 5.1. Khai báo Maven

**`pom.xml`**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>queue-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-artemis</artifactId>
        </dependency>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>artemis-jakarta-server</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Starter Artemis cấp các thành phần cần để kết nối và tích hợp JMS; dependency `artemis-jakarta-server` cho phép dùng broker embedded. Phiên bản của dependency Artemis được quản lý bởi Spring Boot BOM.

### 5.2. Cấu hình broker và đích Queue

**`src/main/resources/application.properties`**:

~~~properties
spring.artemis.mode=embedded
spring.artemis.embedded.queues=orders.queue
spring.artemis.embedded.persistent=false
spring.jms.pub-sub-domain=false
spring.jms.listener.session.transacted=true
~~~

- `orders.queue` là queue được tạo khi broker embedded khởi động.
- `pub-sub-domain=false` xác định cách resolve tên destination mặc định theo **Queue**, không phải Topic.
- `session.transacted=true` yêu cầu listener sử dụng JMS transaction cục bộ: thực thi thành công thì commit; exception lan ra ngoài listener khiến rollback và tạo điều kiện redelivery theo broker.
- Persistence đang tắt, nên không dùng ví dụ này để suy ra bảo đảm sống sót qua việc dừng broker.

### 5.3. Producer gửi năm message

**`src/main/java/com/example/queuedemo/QueueDemoApplication.java`**:

~~~java
package com.example.queuedemo;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
@EnableJms
public class QueueDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(QueueDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner sendExample(JmsTemplate jmsTemplate) {
        return args -> {
            for (int i = 1; i <= 5; i++) {
                String orderId = "ORDER-%03d".formatted(i);
                jmsTemplate.convertAndSend("orders.queue", orderId);
                System.out.println("sent " + orderId);
            }
        };
    }
}
~~~

`ApplicationRunner` gửi message sau khi ứng dụng khởi tạo. `convertAndSend` chuyển chuỗi Java thành JMS `TextMessage` rồi gửi tới queue. Producer không cần giữ kết nối hay tự quản lý `Session`: `JmsTemplate` xử lý phần lớn công việc đó.

### 5.4. Listener với hai consumer

**`src/main/java/com/example/queuedemo/OrderConsumer.java`**:

~~~java
package com.example.queuedemo;

import jakarta.jms.JMSException;
import jakarta.jms.Message;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderConsumer {

    @JmsListener(destination = "orders.queue", concurrency = "2")
    public void handle(String orderId, Message message) throws JMSException {
        System.out.printf(
                "processed %s by %s, redelivered=%s%n",
                orderId,
                Thread.currentThread().getName(),
                message.getJMSRedelivered()
        );
    }
}
~~~

`concurrency="2"` tạo hai consumer/session đồng thời cho listener này; **mỗi message được một trong hai consumer nhận trong một lần giao**. Tham số `String` là payload đã được Spring chuyển đổi; `Message` là đối tượng JMS gốc để đọc metadata. `JMSRedelivered` giúp quan sát việc giao lại nhưng không phải khóa chống trùng.

### 5.5. Chạy và quan sát

Tại thư mục `queue-demo`:

~~~bash
mvn spring-boot:run
~~~

Trong log sẽ có **năm dòng `sent ORDER-001` đến `sent ORDER-005`** và, nếu mọi lần xử lý đều thành công, **năm dòng `processed ORDER-...`**. Các dòng gửi và nhận có thể xen kẽ; tên thread, consumer nhận từng đơn và thứ tự dòng `processed` thay đổi giữa các lần chạy. Không có một thứ tự stdout cố định để so sánh từng dòng. Nhấn Ctrl+C để dừng ứng dụng.

Hãy thử sửa `concurrency = "1"` rồi chạy lại: một consumer nhận toàn bộ công việc. Đổi lại thành `"2"` hoặc `"3"` rồi quan sát tên thread và khả năng xử lý đồng thời. Không nên dùng một lần chạy có quá ít message để kết luận broker luôn chia công việc đều.

## 6. Acknowledgment, transaction và redelivery

Độ tin cậy của Queue phụ thuộc vào **thời điểm message được xác nhận**, không chỉ vào việc Java method được gọi.

| Cơ chế | Ý nghĩa cần hiểu | Lưu ý |
| --- | --- | --- |
| `AUTO_ACKNOWLEDGE` | JMS provider/container xác nhận theo quy tắc nhận message của chế độ auto | Với Spring listener container, lỗi từ business code có thể không tạo được cơ chế khôi phục mong muốn; không mặc định xem là an toàn cho công việc quan trọng |
| `CLIENT_ACKNOWLEDGE` | Client chủ động gọi `Message.acknowledge()` | Cần hiểu phạm vi acknowledgment của cả session, không phải lúc nào cũng chỉ một message |
| `DUPS_OK_ACKNOWLEDGE` | Có thể trì hoãn acknowledgment | Chấp nhận giao lặp để đổi lấy hiệu năng trong một số trường hợp |
| **Transacted JMS session** | Commit xác nhận việc receive (và các thao tác JMS cùng transaction); rollback khiến message có thể được giao lại | Phù hợp cho listener cần xử lý đáng tin cậy; không tự bao trùm transaction cơ sở dữ liệu khác |

Với Spring, `DefaultMessageListenerContainer` có thể cấu hình `sessionTransacted=true`; khi listener ném exception chưa bị bắt, container rollback JMS transaction. Broker sau đó áp dụng chính sách giao lại, khoảng chờ, số lần thử và dead-letter queue (nếu có). **Chi tiết retry/DLQ thuộc broker và cấu hình triển khai**, không phải một con số cố định của JMS.

Ví dụ sửa tạm nội dung method listener để kiểm tra lỗi:

~~~java
// Đoạn minh họa THAY CHO thân method handle ở mục 5.4;
// cần import thêm java.util.concurrent.atomic.AtomicBoolean.
private final AtomicBoolean failOnce = new AtomicBoolean(true);

@JmsListener(destination = "orders.queue", concurrency = "2")
public void handle(String orderId, Message message) throws JMSException {
    if ("ORDER-003".equals(orderId) && failOnce.compareAndSet(true, false)) {
        throw new IllegalStateException("Lỗi thử nghiệm trước commit");
    }
    System.out.printf("processed %s, redelivered=%s%n",
            orderId, message.getJMSRedelivered());
}
~~~

**Đây là đoạn thay thế trong `OrderConsumer`, không phải tệp Java độc lập.** Khi lỗi được ném, JMS transaction rollback; nếu broker còn chạy và cho phép redelivery, `ORDER-003` có thể được nhận lại và in `redelivered=true`. Thời điểm và số lần thử do broker quyết định. Phải tránh viết code bắt exception rồi bỏ qua nếu muốn rollback:

~~~java
// Không phù hợp khi cần broker retry:
try {
    processOrder(orderId);
} catch (RuntimeException error) {
    log.warn("Processing failed", error);
    // Trả về bình thường: container có thể commit lần giao hiện tại.
}
~~~

Đoạn thứ hai chỉ minh họa lỗi thường gặp; `processOrder` và `log` là thành phần giả định, không phải chương trình tự chạy. Nếu cần bắt lỗi để bổ sung thông tin, hãy tái ném exception hoặc dùng một chiến lược lỗi được thiết kế rõ ràng.

### 6.1. At-most-once, at-least-once và “exactly once”

- **At-most-once:** xử lý tối đa một lần theo thiết kế chấp nhận mất message ở một số lỗi.
- **At-least-once:** cố gắng không bỏ mất message chưa hoàn tất; điều này cho phép **lặp** khi có lỗi kết nối, rollback hoặc crash.
- **Exactly-once *business effect*:** chỉ đạt được ở tầng nghiệp vụ nếu kết hợp ranh giới transaction, nhận diện trùng và/hoặc cơ chế đặc thù đã được kiểm chứng. **Queue + JMS transaction riêng lẻ không bảo đảm thao tác ghi DB, gửi email hay gọi HTTP chỉ xảy ra đúng một lần.**

Tình huống kinh điển:

1. Consumer nhận message `ORDER-003`.
2. Consumer ghi trạng thái đơn hàng vào DB và DB đã commit.
3. Tiến trình gặp sự cố **trước khi JMS session commit**.
4. Broker không nhận được acknowledgment/commit, có thể giao lại message.
5. Nếu xử lý lại không kiểm tra trùng, nghiệp vụ bị thực hiện lần hai.

Cách xử lý thường dùng là **idempotent consumer**: mỗi message có một `messageId` nghiệp vụ ổn định (do producer tạo), lưu dấu đã xử lý bằng khóa unique cùng transaction với thay đổi DB. Nếu bản ghi đã tồn tại, bỏ qua hiệu ứng nghiệp vụ trùng nhưng vẫn kết thúc listener thành công để xác nhận message. Có thể dùng `orderId` làm khóa nếu nghiệp vụ thực sự chỉ cho phép một lần xử lý cho mỗi đơn; còn nếu nhiều sự kiện khác nhau trên cùng đơn thì cần `eventId` riêng.

Ví dụ ý tưởng bảng dấu vết trong PostgreSQL:

~~~sql
CREATE TABLE processed_messages (
    consumer_name varchar(100) NOT NULL,
    event_id varchar(100) NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);

-- Trong CÙNG DB transaction với thay đổi nghiệp vụ:
INSERT INTO processed_messages (consumer_name, event_id)
VALUES ('billing-worker', 'event-123')
ON CONFLICT DO NOTHING;
~~~

Chỉ khi `INSERT` thực sự tạo dòng mới mới thực hiện hiệu ứng nghiệp vụ tương ứng; nếu xảy ra rollback DB, cả dấu vết và hiệu ứng phải rollback cùng nhau. SQL trên là ví dụ thiết kế cho PostgreSQL, **chưa phải toàn bộ mã transaction**. Không coi `JMSMessageID` thay cho `eventId` ổn định trong mọi cách gửi lại từ phía producer.

### 6.2. JMS transaction không tự gộp transaction của DB

`JmsTransactionManager` quản lý tài nguyên JMS cục bộ. `DataSourceTransactionManager` quản lý tài nguyên JDBC. Nếu không có phối hợp transaction phù hợp, **commit DB và commit JMS là hai việc khác nhau**; đừng suy ra có transaction phân tán chỉ vì thêm `@Transactional` mà chưa biết transaction manager nào đang hoạt động.

Nếu cần nhất quán giữa DB và gửi message, cân nhắc **transactional outbox** (ghi thay đổi DB và bản ghi outbox trong cùng DB transaction, bộ phát riêng chuyển outbox sang JMS). Với consumer, dùng idempotency/inbox; chỉ khi có yêu cầu đặc biệt và hạ tầng hỗ trợ mới cân nhắc XA/JTA. Outbox không loại bỏ duplicate tuyệt đối, vì bộ phát có thể gửi lại sau crash; consumer vẫn cần idempotent.

## 7. Điều chỉnh cách giao nhận

### 7.1. Tăng concurrency có điều kiện

Tăng `concurrency` để xử lý nhiều message song song khi các tác vụ độc lập, nhưng kiểm tra:

- Số kết nối/session, giới hạn luồng và quota của broker.
- Năng lực DB/HTTP downstream; tăng consumer không giúp nếu cổ chai nằm ở DB.
- Thứ tự nghiệp vụ; hai message cùng `orderId` có thể chạy đồng thời nếu không có khóa/nhóm.
- Backlog, thời gian xử lý, số message in-flight, tỷ lệ retry và DLQ; nên đo thay vì chỉ tăng worker.

`concurrency="2-5"` (khi cấu hình listener container hỗ trợ) có thể cho phép số consumer thay đổi trong khoảng này. Broker có thể prefetch message cho từng consumer; phân phối không nhất thiết cân bằng tức thời.

### 7.2. Selector lọc message trên cùng queue

JMS message selector sử dụng biểu thức trên **headers/properties**, không đọc tự do từng trường bên trong JSON payload. Ví dụ producer gửi message có property `region`:

~~~java
jmsTemplate.send("orders.queue", session -> {
    var message = session.createTextMessage("ORDER-101");
    message.setStringProperty("region", "VN");
    return message;
});
~~~

Consumer chỉ nhận message có property phù hợp:

~~~java
@JmsListener(destination = "orders.queue", selector = "region = 'VN'")
public void handleVn(String orderId) {
    System.out.println("VN order: " + orderId);
}
~~~

Hai đoạn trên **minh họa cách dùng riêng**, khi ghép vào ứng dụng phải đặt trong các bean thích hợp và bảo đảm không tạo hai listener chồng phạm vi ngoài ý muốn. Message không khớp selector sẽ không được listener đó nhận; nếu không có consumer phù hợp, message có thể tồn đọng. Đừng dùng selector thay cho phân quyền hoặc bảo vệ dữ liệu.

### 7.3. TTL, persistence, priority và DLQ

- **Persistent delivery** yêu cầu provider bảo quản message theo quy tắc bền vững của JMS, nhưng còn phụ thuộc cách cấu hình broker, đĩa và transaction. Ví dụ embedded `persistent=false` ở trên cố ý không minh họa cam kết sau restart.
- **Time-to-live (TTL)** có thể khiến message hết hạn trước khi xử lý; quản trị message hết hạn là chính sách của broker.
- **Priority** có thể làm message ưu tiên cao được giao trước, làm suy yếu giả định FIFO đơn giản.
- **DLQ** giữ message không thể xử lý sau chính sách retry/redelivery phù hợp. Cần quan sát và có quy trình phân loại, sửa lỗi, tái xử lý có kiểm soát; không mặc định message lỗi tự biến mất an toàn.
- **Delivery count:** với provider hỗ trợ theo đặc tả Jakarta Messaging, `JMSXDeliveryCount` cho biết số lần giao; `JMSRedelivered` báo dấu hiệu giao lại. Hai trường này phục vụ chẩn đoán, không thay thế idempotency.

Đặt tên queue rõ chức năng (`orders.commands`, `payments.requests`) và duy trì hợp đồng message: phiên bản schema, kiểu dữ liệu, ID ổn định, kích thước tối đa, lỗi serialization, bảo mật dữ liệu nhạy cảm và giới hạn thời gian xử lý.

### 7.4. Nhận đồng bộ so với listener bất đồng bộ

Có thể nhận đồng bộ:

~~~java
// Đoạn minh họa chạy trong một Spring bean đã inject JmsTemplate.
Object payload = jmsTemplate.receiveAndConvert("orders.queue");
~~~

Lời gọi này có thể chờ đến khi nhận được message hoặc tới timeout. Khi thăm dò theo chu kỳ, đặt `receiveTimeout` phù hợp và xem xét transaction. Đa số worker dài hạn thích `@JmsListener` hơn vì Spring quản lý vòng đời consumer, luồng và khôi phục kết nối.

## 8. Chẩn đoán vấn đề thường gặp

| Hiện tượng | Nguyên nhân nên kiểm tra | Cách xử lý |
| --- | --- | --- |
| Producer gửi nhưng consumer không nhận | Sai tên đích, nhầm Topic/Queue, selector không khớp, listener chưa start hoặc cấu hình kết nối sai | Kiểm tra queue trên broker, `destination`, `pubSubDomain`, selector và log kết nối |
| Một message bị xử lý hai lần | Rollback, crash trước commit, mất kết nối, producer gửi trùng | Dùng event ID ổn định, idempotency và xem delivery count |
| Message mắc kẹt trong queue | Consumer ngừng, tốc độ gửi cao, selector không khớp, downstream chậm | Xem queue depth, in-flight, tốc độ nhận, lỗi listener và giới hạn tài nguyên |
| Cùng queue nhưng consumer nhận không đều | Prefetch, tốc độ worker khác nhau, cạnh tranh consumer, broker dispatch | Đo throughput và latency, đọc cấu hình provider; đừng giả định round-robin |
| Thứ tự xử lý khác thứ tự gửi | Concurrency, nhiều producer/session, retry, priority | Quy hoạch khóa thứ tự, giới hạn đồng thời hoặc áp dụng message groups phù hợp |
| Message lỗi bị thử mãi | Không có giới hạn retry/DLQ hoặc cấu hình rollback thiếu kiểm soát | Phân biệt lỗi tạm thời và lỗi dữ liệu, đặt redelivery delay/max attempts/DLQ theo broker |
| Message mất sau restart trong demo | Embedded Artemis đang `persistent=false` | Bật persistence và cấu hình broker sản xuất đúng chuẩn khi cần độ bền |

**Quan sát vận hành tối thiểu:** queue depth, tuổi message cũ nhất, số consumer đang kết nối, tốc độ enqueue/dequeue, retry count, DLQ depth, thời gian xử lý, lỗi parse và tình trạng hệ thống downstream. Backlog tăng liên tục là triệu chứng cần tìm nguyên nhân, không tự động là chỉ cần thêm consumer.

## 9. Tự kiểm tra kiến thức

1. Có 100 message và 4 consumer cùng lắng nghe một queue. Có phải mỗi consumer nhận đủ 100 message? **Không.** Chúng chia nhau các lần giao; cách phân bổ không bảo đảm bằng nhau.
2. Consumer đã cập nhật DB nhưng crash trước JMS commit. Điều gì có thể xảy ra? **Message được giao lại**, khiến tác động DB có nguy cơ lặp nếu consumer không idempotent.
3. Tăng từ 1 lên 8 consumer có giữ được thứ tự hoàn thành M1 trước M2 không? **Không.** Song song và redelivery phá giả định thứ tự hoàn tất toàn cục.
4. Có thể dùng `@JmsListener` với queue và topic không? **Có.** Cần cấu hình loại destination và ý nghĩa subscription tương ứng; bài này chỉ triển khai Queue.
5. Khi không ai lắng nghe, message có luôn tồn tại vĩnh viễn không? **Không.** Nó còn phụ thuộc persistence, TTL, dung lượng, chính sách broker và quản trị.

## 10. Tài liệu chuẩn để đối chiếu

- [Jakarta Messaging 3.1 — mô hình point-to-point và Queue semantics](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html), mục 4.1.
- [Spring Framework — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html), `JmsTemplate`, transaction và listener container.
- [Spring Framework — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html), `@JmsListener` và concurrency.
- [Spring Framework — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html), nhận đồng bộ, bất đồng bộ và transacted listener.
- [Spring Boot 3.5 — JMS](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html), Artemis embedded và auto-configuration.

**Điểm cần nhớ:** Queue giải quyết bài toán *phân công mỗi lần giao message cho một worker*, còn tính đúng đắn nghiệp vụ phụ thuộc acknowledgment/transaction, chính sách redelivery và thiết kế idempotent của ứng dụng.
