# Xây dựng hàng đợi công việc JMS với xác nhận và rollback

Một hàng đợi công việc JMS nhận job từ producer, lưu message trong broker và giao message cho consumer. Khi xử lý thành công, consumer xác nhận message để broker loại bỏ nó khỏi queue. Khi xử lý thất bại, consumer cần rollback hoặc recover để broker có thể giao lại message. Acknowledgement quyết định điều gì xảy ra khi listener ném exception, tiến trình dừng hoặc broker mất kết nối.

Trong Spring, JmsTemplate gửi message; DefaultMessageListenerContainer nhận message và gọi listener; @JmsListener khai báo endpoint bằng annotation. Với công việc cần độ tin cậy, hãy dùng transacted JMS Session để việc nhận message và acknowledgement thuộc một giao dịch cục bộ. Listener chỉ commit khi xử lý hoàn tất; exception làm transaction rollback và provider có thể redeliver message.

Bài này dùng Spring Framework 7.0.8, Jakarta JMS, ActiveMQ Classic 6.1.5 và Java 17. ActiveMQ là provider cho bài test nhúng; transaction model thuộc JMS/Spring, còn delay, retry limit và DLQ là chính sách riêng của broker.

## 1. Luồng công việc của queue

Queue JMS hỗ trợ competing consumers: nhiều consumer lắng nghe cùng destination và broker phân phối một message cho một consumer tại một thời điểm. Mỗi consumer thường dùng một JMS Session riêng.

~~~text
Producer
   | send(jobId, payload)
   v
JMS Queue
   | deliver
   v
Listener Container
   | begin local JMS transaction
   v
Business Handler
   | success   -> commit Session   -> broker removes message
   | exception -> rollback Session -> broker redelivers
                                      |
                                      +-> retry limit exceeded -> DLQ
~~~

Cần phân biệt ba thao tác:

- Send: producer gửi message tới destination.
- Receive: broker giao message cho consumer.
- Acknowledge/commit: consumer xác nhận message đã được xử lý theo semantics của session.

Message đã được giao chưa có nghĩa business logic đã hoàn tất. Message được đọc vào memory chưa có nghĩa broker đã xóa nó. Với transacted session, commit là điểm xác nhận receipt và các thao tác JMS trong cùng session transaction.

Queue phù hợp khi mỗi job cần một consumer xử lý. Topic phù hợp khi nhiều subscriber cần nhận cùng một event. Đừng dùng topic thay queue chỉ để tăng số consumer; semantics delivery và subscription khác nhau.

## 2. Các acknowledgement mode của JMS

| Chế độ | Cách xác nhận | Hành vi và giới hạn |
|---|---|---|
| AUTO_ACKNOWLEDGE | Provider tự xác nhận theo semantics của listener/receive | Spring cảnh báo chế độ mặc định này không bảo đảm reliability cho nhiều message listener; listener lỗi có thể làm mất message |
| CLIENT_ACKNOWLEDGE | Client gọi Message.acknowledge() | Acknowledge xác nhận tất cả message đã tiêu thụ trên Session, không chỉ message hiện tại |
| DUPS_OK_ACKNOWLEDGE | Provider được phép xác nhận lười | Có thể xuất hiện duplicate; phù hợp khi throughput quan trọng hơn việc tránh duplicate |
| SESSION_TRANSACTED | Client commit hoặc rollback Session | Rollback làm message được redeliver theo chính sách provider; phù hợp với queue công việc quan trọng |

Với CLIENT_ACKNOWLEDGE, lời gọi message.acknowledge() có phạm vi toàn Session. Nếu listener xử lý nhiều message trên cùng session, phạm vi xác nhận có thể lớn hơn dự kiến.

Với transacted session, không gọi Message.acknowledge(). Listener container quản lý Session.commit() khi listener hoàn tất thành công và Session.rollback() khi listener ném exception. Hãy để một nơi duy nhất sở hữu transaction boundary.

## 3. Bật transaction cho listener

Khi listener container đặt sessionTransacted=true, mỗi lần gọi listener chạy trong local JMS transaction:

1. Container nhận message trong transacted Session.
2. Listener thực hiện business logic.
3. Listener kết thúc bình thường: container commit Session.
4. Listener ném exception: container rollback Session.
5. Broker có thể redeliver message theo provider policy.

Rollback bảo vệ message khỏi việc bị xác nhận trước khi listener xử lý xong. Tuy nhiên, rollback không tự khôi phục side effect bên ngoài JMS như ghi database, gọi HTTP hoặc tạo file.

Ví dụ: listener ghi database thành công, sau đó JMS commit thất bại. Broker giao lại message và listener có thể ghi bản ghi lần nữa. Vì vậy, transacted JMS thường tạo semantics at-least-once; ứng dụng vẫn cần idempotency và duplicate detection.

### 3.1. Cấu hình DefaultMessageListenerContainer

DefaultMessageListenerContainer là lựa chọn phổ biến vì hỗ trợ concurrency động, recovery và external transaction khi được cấu hình. Cấu hình Java cơ bản:

~~~java
@Bean
DefaultMessageListenerContainer jobsContainer(
        ConnectionFactory connectionFactory,
        MessageListener jobsListener) {

    DefaultMessageListenerContainer container =
            new DefaultMessageListenerContainer();
    container.setConnectionFactory(connectionFactory);
    container.setDestinationName("jobs.queue");
    container.setMessageListener(jobsListener);
    container.setSessionTransacted(true);
    container.setConcurrentConsumers(2);
    container.setMaxConcurrentConsumers(8);
    return container;
}
~~~

sessionTransacted=true là điểm quan trọng. Khi listener ném runtime exception, container rollback session. Provider quyết định delay, số lần redelivery và DLQ.

### 3.2. Cấu hình @JmsListener

Với annotation-driven listener endpoint, cấu hình DefaultJmsListenerContainerFactory:

~~~java
@Configuration
@EnableJms
class JmsWorkQueueConfig {

    @Bean
    DefaultJmsListenerContainerFactory workQueueFactory(
            ConnectionFactory connectionFactory) {
        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        factory.setConcurrency("2-8");
        return factory;
    }
}

@Component
class JobListener {
    private final JobProcessor processor;

    JobListener(JobProcessor processor) {
        this.processor = processor;
    }

    @JmsListener(destination = "jobs.queue",
            containerFactory = "workQueueFactory")
    public void handle(Job job) {
        processor.process(job);
    }
}
~~~

Nếu processor.process(job) ném exception, exception phải đi ra khỏi listener để container rollback. Nếu bắt exception rồi chỉ log mà không ném lại, container xem listener hoàn tất bình thường và commit message. Với lỗi có thể retry, hãy ném exception; với lỗi không thể retry, hãy chuyển message sang luồng lỗi/DLQ theo chính sách đã thiết kế.

## 4. Gửi job bằng JmsTemplate

JmsTemplate quản lý việc tạo message, gửi tới destination và giải phóng JMS resources. Ví dụ gửi job với ID ổn định:

~~~java
jmsTemplate.convertAndSend("jobs.queue", job, message -> {
    message.setStringProperty("jobId", job.id());
    message.setJMSCorrelationID(job.correlationId());
    return message;
});
~~~

jobId là khóa nghiệp vụ dùng cho idempotency. JMSCorrelationID hữu ích để liên kết request/reply hoặc log; nó không tự tạo idempotency và không thay thế unique constraint ở database.

Nếu job phải tồn tại sau broker restart, cần persistent delivery mode và broker persistence được cấu hình đúng. Persistent delivery mode không tự bảo đảm storage bền vững nếu broker chạy non-persistent hoặc storage không được vận hành an toàn.

Có thể cấu hình delivery mode rõ ràng:

~~~java
jmsTemplate.setDeliveryMode(DeliveryMode.PERSISTENT);
jmsTemplate.setExplicitQosEnabled(true);
~~~

JmsTemplate thread-safe sau khi được cấu hình. Tái sử dụng bean template thay vì tạo template mới cho từng job.

## 5. Rollback, redelivery và retry policy

Khi listener ném exception trong transacted session, container rollback. Broker nhận biết delivery chưa commit và giao lại message. Các dấu hiệu thường gặp:

- JMSRedelivered cho biết message đã được giao trước đó.
- JMSXDeliveryCount biểu thị số lần message đã được giao nếu provider hỗ trợ property này.
- Provider có thể áp dụng redelivery delay, exponential backoff và maximum redeliveries.
- Khi vượt retry limit, broker có thể chuyển message sang Dead Letter Queue (DLQ).

Không phải provider nào cũng dùng cùng property, delay hoặc DLQ name. Kiểm tra tài liệu broker đang triển khai. ActiveMQ Classic có RedeliveryPolicy với initial delay, exponential backoff và maximum redeliveries.

Ví dụ cấu hình ActiveMQ Classic:

~~~java
RedeliveryPolicy policy = new RedeliveryPolicy();
policy.setInitialRedeliveryDelay(1_000);
policy.setUseExponentialBackOff(true);
policy.setBackOffMultiplier(2.0);
policy.setMaximumRedeliveries(5);
connectionFactory.setRedeliveryPolicy(policy);
~~~

maximumRedeliveries=5 cho phép tối đa năm lần redelivery sau lần giao đầu theo semantics ActiveMQ. Tổng số lần listener được gọi có thể lớn hơn số retry. Xác nhận bằng test trên provider và phiên bản thực tế.

Không để message lỗi lặp tức thì vô hạn. Delay/backoff tránh hot loop và giảm tải khi dependency hỏng. Có thể thêm jitter nếu provider hỗ trợ để tránh nhiều message cùng retry một lúc.

## 6. Poison message và Dead Letter Queue

Poison message là message luôn thất bại do dữ liệu sai, schema không tương thích, thiếu cấu hình hoặc bug không thể tự phục hồi bằng retry. Nếu broker redeliver vô hạn, message có thể chiếm consumer và làm queue không tiến triển.

DLQ là nơi broker chuyển message sau khi vượt redelivery policy hoặc không thể giao message. DLQ cần quy trình vận hành:

1. Theo dõi số lượng và tuổi message trong DLQ.
2. Ghi nguyên nhân cuối cùng, delivery count, job ID và destination gốc.
3. Phân loại lỗi transient, lỗi dữ liệu và lỗi code.
4. Sửa nguyên nhân trước khi replay.
5. Replay có kiểm soát và bảo đảm consumer idempotent.
6. Giữ audit trail cho việc replay hoặc loại bỏ message.

ActiveMQ Classic có thể dùng ActiveMQ.DLQ mặc định; individual dead-letter strategy giúp mỗi queue có DLQ riêng. Ví dụ XML cho broker ActiveMQ Classic:

~~~xml
<destinationPolicy>
    <policyMap>
        <policyEntries>
            <policyEntry queue=">">
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

Đoạn XML thuộc cấu hình broker ActiveMQ Classic, không phải cấu hình Spring. Provider khác có thể dùng tên DLQ và routing policy khác.

## 7. Transaction JMS và database

sessionTransacted=true chỉ bảo vệ thao tác trong JMS Session. Nếu listener còn cập nhật database, hai tài nguyên không tự động trở thành một transaction nguyên tử.

Failure window phổ biến:

~~~text
JMS message delivered
       |
       v
DB transaction commits
       |
       X JVM stops before JMS commit
       |
       v
Broker redelivers the message
       |
       v
DB operation runs again
~~~

Nếu DB commit trước JMS commit và tiến trình dừng ở giữa, message sẽ được giao lại. Đây là duplicate delivery, không phải lỗi bất thường của broker.

Các cách xử lý:

- Idempotent consumer: dùng jobId/messageId làm khóa duy nhất trong DB; nếu đã xử lý thì không lặp side effect.
- Inbox table: ghi nhận message đã xử lý trong cùng DB transaction với cập nhật nghiệp vụ. Unique constraint trên message ID giúp xử lý duplicate an toàn.
- Outbox pattern: producer ghi business data và outbox row trong cùng DB transaction; relay gửi outbox message tới broker. Relay có thể publish lặp, vì vậy consumer vẫn cần idempotency.
- XA/JTA: phối hợp JMS và database trong distributed transaction nếu cả hai resource manager hỗ trợ XA và vận hành chấp nhận độ phức tạp, latency và recovery của XA.

Không cho rằng @Transactional trên listener tự động tạo distributed transaction. Nó dùng transaction manager được cấu hình. Nếu đó là database transaction manager còn listener container dùng local JMS transaction, hai transaction vẫn có thể commit độc lập.

Ví dụ inbox consumer:

~~~java
@Transactional
public void process(Job job) {
    if (!inboxRepository.insertIfAbsent(job.id())) {
        return; // Message đã được xử lý; đây là redelivery/duplicate.
    }

    orderService.apply(job);
}
~~~

insertIfAbsent phải được bảo vệ bằng unique constraint hoặc upsert phù hợp với database. Chỉ kiểm tra tồn tại rồi insert trong hai bước có thể gặp race khi hai consumer xử lý cùng ID. Inbox record và business update phải commit cùng DB transaction. Sau đó listener container mới commit JMS Session. Nếu message redeliver, consumer thấy inbox record và không lặp side effect.

## 8. Chọn retry hay kết thúc?

Không phải exception nào cũng nên redeliver:

| Loại lỗi | Ví dụ | Chính sách gợi ý |
|---|---|---|
| Transient dependency | Database timeout, HTTP 503, broker dependency tạm mất | Rollback và retry với backoff |
| Business conflict có thể giải quyết sau | Tài nguyên đang bị khóa, version chưa đồng bộ | Retry giới hạn hoặc retry queue |
| Validation/permanent | Thiếu trường bắt buộc, enum không hợp lệ | Không retry dài; chuyển DLQ/quarantine |
| Schema incompatibility | Consumer không đọc được version payload | DLQ và sửa compatibility |
| Bug code | NullPointerException lặp lại | Giới hạn retry, cảnh báo và DLQ |

Listener nên ném exception khi muốn rollback. Nếu muốn bỏ qua job theo nghiệp vụ, hãy ghi nhận quyết định đó bền vững rồi để listener hoàn tất bình thường. Không bắt exception và nuốt nó chỉ để tránh log đỏ; hành vi đó có thể khiến broker commit message dù công việc chưa thành công.

Local retry giữ message trong một lần listener invocation; broker redelivery rollback transaction và tạo lần delivery mới. Không cộng dồn nhiều lớp retry mà không tính tổng số lần thử và thời gian tối đa.

## 9. Concurrency, ordering và queue throughput

Tăng số consumer giúp xử lý nhiều job song song. Với DefaultMessageListenerContainer, concurrentConsumers là số consumer ban đầu; maxConcurrentConsumers là giới hạn khi container tự điều chỉnh. Với annotation factory, setConcurrency("2-8") khai báo khoảng concurrency.

Concurrency cao không luôn tốt:

- Database connection pool có thể nhỏ hơn số consumer.
- Downstream API có rate limit.
- Job dài có thể giữ session/consumer lâu.
- Redelivery và nhiều consumer có thể làm thay đổi thứ tự xử lý.
- Nếu nhiều job cập nhật cùng aggregate, cần khóa hoặc optimistic concurrency ở tầng nghiệp vụ.

Queue thường phân phối một message cho một consumer, nhưng không nên mặc định thứ tự hoàn tất business luôn giống thứ tự gửi khi có nhiều consumer, retry hoặc priority. Nếu cần thứ tự theo key, cân nhắc message group/partitioning theo provider hoặc xử lý tuần tự theo aggregate key.

Đặt giới hạn concurrency dựa trên năng lực downstream, không chỉ CPU. Quan sát queue depth, oldest message age, processing latency, consumer count và redelivery rate trước khi tăng worker.

## 10. Ví dụ Java 17: test rollback và redelivery thật

Test dưới đây dùng ActiveMQ Classic embedded broker qua VM transport. Listener đầu tiên ném exception có chủ đích; vì listener container dùng transacted session, message được rollback và broker giao lại. Lần thứ hai listener hoàn tất, session commit và message được xác nhận.

Test kiểm tra transaction/redelivery trong một JVM. Broker được cấu hình non-persistent để test nhanh; nó không chứng minh khả năng giữ message qua broker restart. Production cần persistent broker storage và cấu hình delivery phù hợp.

### 10.1. Maven dependencies

POM tối thiểu cho Java 17:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>jms-rollback-redelivery-test</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <spring.version>7.0.8</spring.version>
    <activemq.version>6.1.5</activemq.version>
    <junit.version>5.12.2</junit.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-jms</artifactId>
      <version>${spring.version}</version>
    </dependency>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>${spring.version}</version>
    </dependency>
    <dependency>
      <groupId>org.apache.activemq</groupId>
      <artifactId>activemq-broker</artifactId>
      <version>${activemq.version}</version>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.apache.activemq</groupId>
      <artifactId>activemq-client</artifactId>
      <version>${activemq.version}</version>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.apache.activemq</groupId>
      <artifactId>activemq-kahadb-store</artifactId>
      <version>${activemq.version}</version>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter</artifactId>
      <version>${junit.version}</version>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.0</version>
        <configuration><release>17</release></configuration>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.5.3</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

### 10.2. Test hoàn chỉnh

Lưu thành src/test/java/example/JmsRollbackRedeliveryTest.java:

~~~java
package example;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import jakarta.jms.MessageListener;
import org.apache.activemq.ActiveMQConnectionFactory;
import org.apache.activemq.RedeliveryPolicy;
import org.apache.activemq.broker.BrokerService;
import org.junit.jupiter.api.Test;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.listener.DefaultMessageListenerContainer;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class JmsRollbackRedeliveryTest {

    @Test
    void listenerFailureRollsBackAndBrokerRedelivers() throws Exception {
        BrokerService broker = new BrokerService();
        broker.setBrokerName("jms-rollback-test");
        broker.setPersistent(false);
        broker.setUseJmx(false);
        broker.addConnector("vm://jms-rollback-test");
        broker.start();
        broker.waitUntilStarted();

        ActiveMQConnectionFactory connectionFactory =
                new ActiveMQConnectionFactory("vm://jms-rollback-test?create=false");
        RedeliveryPolicy redelivery = new RedeliveryPolicy();
        redelivery.setInitialRedeliveryDelay(100);
        redelivery.setUseExponentialBackOff(false);
        redelivery.setMaximumRedeliveries(2);
        connectionFactory.setRedeliveryPolicy(redelivery);

        CountDownLatch completed = new CountDownLatch(1);
        AtomicInteger attempts = new AtomicInteger();
        AtomicInteger deliveryCount = new AtomicInteger();
        AtomicReference<String> completedJob = new AtomicReference<>();

        DefaultMessageListenerContainer container =
                new DefaultMessageListenerContainer();
        container.setConnectionFactory(connectionFactory);
        container.setDestinationName("jobs.queue");
        container.setSessionTransacted(true);
        container.setConcurrentConsumers(1);
        container.setMaxConcurrentConsumers(1);
        container.setMessageListener((MessageListener) message -> {
            int attempt = attempts.incrementAndGet();
            try {
                deliveryCount.set(message.getIntProperty("JMSXDeliveryCount"));
                String jobId = message.getStringProperty("jobId");
                if (attempt == 1) {
                    throw new IllegalStateException("simulated transient failure");
                }
                completedJob.set(jobId);
                completed.countDown();
            }
            catch (jakarta.jms.JMSException ex) {
                throw new IllegalStateException(ex);
            }
        });
        container.afterPropertiesSet();
        container.start();

        try {
            JmsTemplate template = new JmsTemplate(connectionFactory);
            template.convertAndSend("jobs.queue", "generate-report", message -> {
                message.setStringProperty("jobId", "job-42");
                return message;
            });

            assertTrue(completed.await(10, TimeUnit.SECONDS),
                    "job should be redelivered and processed");
            assertEquals("job-42", completedJob.get());
            assertEquals(2, attempts.get());
            assertEquals(2, deliveryCount.get());
        }
        finally {
            container.stop();
            container.destroy();
            broker.stop();
            broker.waitUntilStopped();
        }
    }
}
~~~

Test dùng JMSXDeliveryCount của ActiveMQ để xác nhận message đã được giao lần thứ hai. Assertion cũng kiểm tra job ID và số lần listener thực sự được gọi. CountDownLatch chờ điều kiện hoàn tất với timeout; không dùng Thread.sleep() để đoán thời điểm redelivery.

Chạy:

~~~bash
mvn test
~~~

Kết quả Surefire mong đợi:

~~~text
Tests run: 1, Failures: 0, Errors: 0, Skipped: 0
~~~

Log SLF4J có thể báo chưa có provider trong test tối thiểu; điều đó chỉ có nghĩa logging rơi về NOP, không ảnh hưởng assertion transaction/redelivery. Ứng dụng thực tế nên chọn logging provider tương thích.

## 11. Theo dõi queue và redelivery trong production

Theo dõi các chỉ số sau:

- Queue depth: số message đang chờ.
- Oldest message age: tuổi của message cũ nhất.
- Enqueue/dequeue rate: tốc độ producer gửi và consumer nhận.
- In-flight/delivering count: message đang được giao nhưng chưa commit.
- Consumer count và consumer utilization.
- Processing duration p50/p95/p99.
- Redelivery count/rate và số message có JMSRedelivered=true.
- DLQ depth, tuổi message và tốc độ chuyển vào DLQ.
- Transaction rollback/commit rate và lỗi kết nối broker.

Log mỗi job với jobId, JMSMessageID, JMSCorrelationID, destination, JMSRedelivered, JMSXDeliveryCount, consumer instance, thời gian bắt đầu/kết thúc và outcome. Không log payload nhạy cảm hoặc credential. Tránh dùng jobId làm metric tag vì cardinality không giới hạn; giữ ID trong log/trace.

Một cảnh báo queue hữu ích thường kết hợp queue depth và oldest message age. Depth cao nhưng dequeue rate vẫn lớn có thể chỉ là burst; oldest age tăng liên tục trong khi dequeue rate gần 0 báo hiệu consumer không tiến triển. DLQ tăng nhanh hoặc redelivery rate tăng đột ngột cần cảnh báo riêng.

## 12. Lỗi thường gặp

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Dùng AUTO_ACKNOWLEDGE cho công việc quan trọng | Message có thể được xác nhận dù xử lý lỗi | Dùng transacted listener session |
| Bắt exception rồi không ném lại | Container commit message | Rethrow khi cần rollback |
| Gọi Message.acknowledge() trong transacted session | Trộn hai mô hình acknowledgement | Để container commit/rollback session |
| Nghĩ CLIENT_ACKNOWLEDGE xác nhận một message | Có thể xác nhận nhiều message trên cùng session | Hiểu session scope hoặc dùng transacted session |
| Retry vô hạn | Poison message chiếm queue và worker | Giới hạn retry, backoff và DLQ |
| Chuyển message vào DLQ nhưng không theo dõi | Job lỗi bị quên | Dashboard, alert và quy trình replay |
| DB commit nhưng JMS rollback | Redelivery lặp side effect | Inbox/idempotency hoặc XA/JTA khi thực sự cần |
| Spawn async task rồi return khỏi listener | JMS transaction commit trước khi task xong | Xử lý trong listener hoặc handoff sang queue khác |
| Tăng concurrency không đo lường | DB/API quá tải, latency tăng | Giới hạn theo năng lực downstream |
| Dùng broker non-persistent trong production | Có thể mất message khi broker dừng | Persistent delivery và persistent broker store |

## 13. Checklist triển khai

- Dùng queue cho competing consumers và xác định rõ destination.
- Producer gửi persistent message nếu yêu cầu durability và broker có persistent storage.
- Listener container bật sessionTransacted=true hoặc transaction manager phù hợp.
- Listener ném exception khi muốn rollback; không nuốt lỗi.
- Redelivery policy có delay, backoff và giới hạn lần thử.
- Poison message có DLQ/quarantine và quy trình điều tra/replay.
- Consumer idempotent bằng job ID hoặc inbox table.
- Xác định ranh giới JMS transaction và database transaction.
- Chọn concurrency theo DB pool, API quota và thời gian xử lý.
- Theo dõi queue depth, oldest age, in-flight, redelivery, rollback và DLQ.
- Test failure path: listener ném exception, broker redeliver, lần xử lý sau commit.
- Test broker restart và persistence riêng trong môi trường integration phù hợp.
- Đóng listener container và broker/client resources trong test/shutdown.

## Tài liệu tham khảo

- [Spring Framework — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html)
- [Spring Framework — Receiving JMS Messages](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html)
- [Spring Framework API — DefaultMessageListenerContainer](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html)
- [ActiveMQ Classic — Redelivery Policy](https://activemq.apache.org/components/classic/documentation/redelivery-policy)
- [ActiveMQ Classic — Message Redelivery and DLQ Handling](https://activemq.apache.org/components/classic/documentation/message-redelivery-and-dlq-handling)
- [ActiveMQ Classic — VM Transport](https://activemq.apache.org/components/classic/documentation/vm-transport-reference)
