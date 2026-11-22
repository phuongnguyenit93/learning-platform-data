# Thiết kế xử lý idempotent bằng khóa nghiệp vụ

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích vì sao một JMS message có thể được xử lý nhiều lần dù broker đã hỗ trợ acknowledgement và redelivery.
- Phân biệt message redelivery với producer gửi lại cùng một sự kiện nghiệp vụ.
- Chọn một business idempotency key ổn định và xác định đúng phạm vi duy nhất của khóa.
- Thiết kế inbox/processed-message table với unique constraint để ngăn side effect bị áp dụng hai lần.
- Đặt thao tác ghi nhận đã xử lý và cập nhật dữ liệu nghiệp vụ trong cùng một database transaction.
- Phối hợp database transaction với JMS local transaction để xử lý failure window giữa DB commit và JMS acknowledgement.
- Xử lý đồng thời, retention, replay, payload conflict và side effect gọi hệ thống bên ngoài.
- Hiểu vai trò của `JMSRedelivered`, `JMSXDeliveryCount`, Spring Integration `IdempotentReceiverInterceptor` và `MetadataStore`.
- Xây dựng một consumer Spring JMS có thể nhận lại cùng message nhưng chỉ ghi nhận một lần vào sổ nghiệp vụ.

## 1. Idempotent processing là gì?

Một thao tác được gọi là *idempotent* nếu thực hiện một lần hay nhiều lần với cùng một khóa nghiệp vụ đều tạo ra cùng một kết quả nghiệp vụ.

Ví dụ, sự kiện thanh toán `payment-1001` yêu cầu ghi nhận khoản thu 125.00. Nếu cùng sự kiện được giao hai lần, hệ thống chỉ được tạo một khoản ghi sổ:

~~~text
Lần nhận thứ nhất:
payment-1001
    |
    v
Ghi nhận khóa + ghi sổ 125.00
    |
    v
COMMIT

Lần nhận tiếp theo:
payment-1001
    |
    v
Khóa đã tồn tại
    |
    v
Bỏ qua side effect
~~~

Idempotency không có nghĩa là listener chỉ được gọi một lần. Listener có thể được gọi nhiều lần; điều cần bảo đảm là cùng một business operation không làm thay đổi trạng thái nghiệp vụ nhiều lần.

Trong hệ thống messaging, cách tiếp cận phổ biến là chấp nhận delivery theo kiểu *at-least-once*, sau đó làm cho consumer idempotent. Đây là cách thực tế để xử lý retry, redelivery, restart và lỗi ở ranh giới transaction.

## 2. Vì sao JMS vẫn cần idempotency?

JMS cung cấp acknowledgement, transaction và redelivery. Tuy nhiên, việc giao message và việc cập nhật database nghiệp vụ thường thuộc hai tài nguyên khác nhau.

Spring Framework giải thích rõ: khi bật `sessionTransacted=true`, mỗi lần gọi listener chạy trong JMS local transaction. Nếu listener thất bại, việc nhận message được rollback. Nhưng các thao tác database khác chạy độc lập với JMS transaction. Do đó cần duplicate detection trong listener để xử lý trường hợp database đã commit nhưng JMS transaction chưa commit. Xem [Spring Framework 6.2.19: AbstractMessageListenerContainer](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/listener/AbstractMessageListenerContainer.html).

Một failure window điển hình:

~~~text
JMS broker                 Consumer                  Database
    |                         |                          |
    |---- deliver message --->|                          |
    |                         |---- BEGIN DB TX -------->|
    |                         |---- write business ----->|
    |                         |---- COMMIT DB ---------->|
    |                         |                          |
    |                JVM / process crashes               |
    |                         X                          |
    |<--- JMS COMMIT chưa xảy ra                          |
    |                         |                          |
    |---- redeliver message ->|                          |
    |                         |---- kiểm tra business key |
    |                         |---- key đã tồn tại        |
    |                         |---- bỏ qua side effect    |
    |<--- JMS COMMIT ----------|                          |
~~~

Nếu consumer không có idempotency, lần giao lại có thể ghi sổ, trừ tiền, tạo đơn hoặc phát hành hóa đơn thêm một lần.

### Các tình huống có thể tạo ra message trùng

- Listener xử lý xong nhưng JVM dừng trước khi JMS transaction commit.
- Connection bị ngắt khi acknowledgement chưa hoàn tất.
- Consumer rollback transaction do exception.
- Broker giao lại message sau khi consumer restart.
- Producer gửi lại cùng business event sau timeout vì không biết lần gửi trước đã thành công hay chưa.
- Outbox relay publish lại một event vì process dừng sau khi publish nhưng trước khi đánh dấu outbox row đã gửi.
- Người vận hành replay message từ DLQ hoặc từ kho lưu trữ.

Cần phân biệt **redelivery của cùng JMS message** và **producer publish lại cùng business event**. Producer publish lại có thể tạo một JMS message mới với `JMSMessageID` khác, nhưng vẫn mang cùng business key.

## 3. Thiết kế business idempotency key

Business key phải nhận diện một thao tác nghiệp vụ cụ thể và giữ nguyên qua mọi lần retry hoặc publish lại.

Ví dụ:

| Nghiệp vụ | Khóa phù hợp | Khóa dễ gây lỗi |
|---|---|---|
| Ghi nhận thanh toán | `paymentId` hoặc `paymentAttemptId` | `orderId` nếu một order có nhiều lần thanh toán |
| Hoàn tiền | `refundId` | `orderId` nếu có thể hoàn nhiều lần |
| Tạo hóa đơn | `invoiceRequestId` | `customerId` |
| Cập nhật một phiên bản aggregate | `aggregateId + eventVersion` | Chỉ `aggregateId` |
| Nhận sự kiện theo tenant | `tenantId + eventId` | `eventId` nếu ID chỉ duy nhất trong tenant |

Một business key tốt có các đặc điểm:

1. **Ổn định:** producer tạo một lần và giữ nguyên khi retry.
2. **Duy nhất theo nghiệp vụ:** hai thao tác khác nhau không dùng chung key.
3. **Không phụ thuộc transport:** key không đổi khi message được gửi lại qua broker hoặc qua một producer khác.
4. **Có phạm vi rõ ràng:** xác định key duy nhất trong toàn hệ thống, theo tenant, theo loại event hay theo consumer.
5. **Không tái sử dụng:** một key đã hoàn tất không được dùng cho một business operation mới.

### Khóa ghép theo consumer và business key

Một hệ thống có thể có nhiều consumer thực hiện các side effect khác nhau cho cùng một event. Vì thế, inbox thường dùng khóa ghép:

~~~sql
PRIMARY KEY (consumer_name, business_key)
~~~

Ví dụ:

- `payment-ledger / payment-1001`
- `customer-notification / payment-1001`
- `analytics-projection / payment-1001`

Mỗi consumer có thể xử lý cùng event một lần cho side effect của riêng nó.

Nếu nhiều tenant có thể có cùng `paymentId`, hãy đưa tenant vào business key hoặc thành một cột riêng trong unique constraint:

~~~sql
PRIMARY KEY (consumer_name, tenant_id, business_key)
~~~

Không thêm version triển khai vào `consumer_name` một cách tùy tiện. Nếu đổi `payment-ledger-v1` thành `payment-ledger-v2`, hệ thống có thể coi toàn bộ message cũ là chưa xử lý và ghi sổ lần nữa. Chỉ thay namespace khi chủ động muốn tạo một luồng side effect mới hoặc replay có kiểm soát.

### Tránh dùng JMSMessageID làm business key

Các trường JMS có mục đích riêng:

| Trường | Mục đích | Dùng làm idempotency key? |
|---|---|---|
| `JMSMessageID` | Định danh message do provider gán | Không nên; producer gửi lại cùng event có thể tạo ID mới |
| `JMSCorrelationID` | Liên kết request và reply hoặc các message liên quan | Chỉ khi contract nghiệp vụ quy định rõ nó là operation key |
| `JMSRedelivered` | Cho biết message có khả năng đã được giao trước đó | Không; chỉ là dấu hiệu redelivery |
| `JMSXDeliveryCount` | Số lần provider giao message | Không; phục vụ quan sát và xử lý retry |
| Business key | Định danh thao tác nghiệp vụ | Có |

Business key nên được mang trong payload hoặc một JMS property/header đã thống nhất giữa producer và consumer. Ví dụ: `paymentId`, `refundId`, `eventId`.

## 4. JMSRedelivered và JMSXDeliveryCount chỉ là metadata chẩn đoán

Jakarta Messaging 3.1 định nghĩa:

- `JMSRedelivered`: nếu true, message có khả năng đã được giao nhưng chưa được acknowledge trước đó.
- `JMSXDeliveryCount`: số lần một message đã được giao; lần đầu có giá trị 1, từ 2 trở lên cho biết đã redeliver.

Provider phải đặt `JMSRedelivered` khi redeliver theo contract và tăng `JMSXDeliveryCount`. Tuy nhiên, specification nói giá trị `JMSXDeliveryCount` không được bảo đảm chính xác tuyệt đối sau một số lỗi provider. Xem [Jakarta Messaging 3.1, §3.4.7, §3.5.11 và §6.2.11](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.pdf).

Có thể đọc metadata để ghi log:

~~~java
boolean redelivered = message.getJMSRedelivered();

int deliveryCount = message.propertyExists("JMSXDeliveryCount")
        ? message.getIntProperty("JMSXDeliveryCount")
        : 1;

log.info(
        "JMS delivery: redelivered={}, deliveryCount={}",
        redelivered,
        deliveryCount
);
~~~

Không chỉ chạy duplicate check khi `JMSRedelivered == true`. Một producer có thể publish lại cùng payment event thành một JMS message mới, có `JMSRedelivered == false`, nhưng business operation vẫn là cùng một payment. Business key phải được kiểm tra cho mọi message.

## 5. Inbox table và unique constraint

Cách triển khai phổ biến là lưu một bản ghi cho mỗi business key đã được consumer xử lý.

Ví dụ schema:

~~~sql
CREATE TABLE processed_event (
    consumer_name VARCHAR(100) NOT NULL,
    business_key  VARCHAR(160) NOT NULL,
    processed_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    payload_hash  VARCHAR(128),
    PRIMARY KEY (consumer_name, business_key)
);

CREATE TABLE payment_ledger (
    entry_id  BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    payment_id VARCHAR(80) NOT NULL,
    account_id VARCHAR(80) NOT NULL,
    amount DECIMAL(19, 2) NOT NULL
);
~~~

`processed_event` là inbox/deduplication table. Unique constraint ở database là cơ chế phân xử cuối cùng khi nhiều thread hoặc nhiều instance cùng nhận một key.

### Dùng insert-first, không dùng check-then-insert

Cách dễ mắc race condition:

~~~text
Consumer A: SELECT key -> chưa có
Consumer B: SELECT key -> chưa có
Consumer A: ghi side effect
Consumer B: ghi side effect
Consumer A: INSERT key
Consumer B: INSERT key
~~~

Hai consumer có thể cùng thấy key chưa tồn tại trước khi một trong hai ghi nhận nó.

Cách an toàn hơn:

1. Mở database transaction.
2. Thử `INSERT` business key vào inbox table.
3. Unique constraint cho phép đúng một transaction chiếm key.
4. Chỉ transaction chèn thành công mới thực hiện business write.
5. Commit inbox row và business write cùng transaction.

~~~text
BEGIN DB TRANSACTION
        |
        v
INSERT processed_event(consumer_name, business_key)
        |
        +---- duplicate key
        |         |
        |         v
        |      ROLLBACK
        |      trả DUPLICATE
        |
        +---- insert thành công
                  |
                  v
          cập nhật dữ liệu nghiệp vụ
                  |
                  v
               COMMIT
~~~

Không dùng một `Set` trong bộ nhớ làm cơ chế duy nhất. Nó không bảo vệ nhiều instance, mất dữ liệu khi restart và không đồng bộ với transaction database. Một câu `SELECT` trước khi insert cũng không thay thế unique constraint.

### Vì sao phải cùng một DB transaction?

Nếu ghi inbox trước rồi commit riêng, sau đó mới cập nhật nghiệp vụ, process có thể dừng giữa hai bước. Lần giao lại thấy key đã có và bỏ qua, trong khi side effect chưa từng xảy ra.

Nếu cập nhật nghiệp vụ trước rồi ghi inbox ở transaction riêng, process có thể dừng sau khi business write commit nhưng trước khi inbox commit. Lần giao lại sẽ thực hiện business write lần nữa.

Đặt cả hai trong cùng transaction giúp database commit hoặc rollback toàn bộ:

- Transaction rollback: inbox row không tồn tại và business write không tồn tại; message có thể được xử lý lại.
- Transaction commit: cả inbox row và business write đều tồn tại; lần xử lý sau bị unique constraint chặn.

## 6. Phối hợp database transaction với JMS transaction

Spring listener container có thể bật local JMS transaction:

~~~java
container.setSessionTransacted(true);
~~~

Với cấu hình này, việc nhận message và acknowledgement được quản lý bởi JMS transaction. Nếu listener ném exception, container rollback JMS transaction và broker có thể redeliver message.

Tuy nhiên, `DataSourceTransactionManager` và JMS local transaction là hai transaction riêng. Spring khuyến nghị dùng local JMS transaction cùng local database transaction và duplicate detection trong logic listener để bao phủ failure window sau DB commit nhưng trước JMS commit.

### Luồng xử lý khuyến nghị

~~~text
JMS listener nhận event
        |
        v
DB transaction bắt đầu
        |
        v
INSERT inbox key (unique)
        |
        +---- duplicate
        |       |
        |       v
        |   DB rollback
        |   listener trả về bình thường
        |       |
        |       v
        |   JMS transaction commit
        |
        +---- key mới
                |
                v
        cập nhật business tables
                |
                v
           DB commit
                |
                v
        listener trả về bình thường
                |
                v
         JMS transaction commit
~~~

Nếu DB transaction thất bại vì lỗi tạm thời, hãy để exception thoát khỏi listener. Khi đó JMS transaction rollback và message được giao lại theo broker policy.

Nếu DB commit thành công nhưng JMS commit chưa xảy ra, broker có thể redeliver. Lần xử lý sau sẽ gặp unique key và bỏ qua side effect, sau đó listener hoàn tất bình thường để JMS transaction commit.

### XA/JTA là một lựa chọn khác

Có thể phối hợp JMS và database trong một transaction phân tán XA/JTA nếu cả hai resource đều hỗ trợ XA và được đăng ký với transaction coordinator.

- Message receipt và database write tham gia cùng transaction.
- Coordinator quản lý commit/rollback chung.
- Giảm failure window giữa hai resource.
- Đổi lại cần XA-capable provider, cấu hình JTA, transaction log, vận hành recovery và chi phí xử lý cao hơn.

Spring Framework nêu hai lựa chọn: duplicate detection trong listener hoặc XA transaction bao trùm message receipt và business processing. Với nhiều ứng dụng, local transaction cộng inbox unique key đơn giản và hiệu quả hơn. Chọn XA khi yêu cầu nhất quán đa resource thực sự cần thiết.

## 7. Ví dụ Java 17 hoàn chỉnh: Spring JMS + H2 inbox

Ví dụ dùng Java 17, Spring Framework 6.2.19, ActiveMQ Classic 6.2.6 và H2. Broker chạy embedded trong cùng JVM. Chương trình gửi hai JMS message riêng biệt có cùng `paymentId`; consumer chỉ tạo một ledger entry.

Cấu trúc thư mục:

~~~text
jms-idempotent-consumer/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── IdempotentConsumerDemo.java
~~~

Tệp `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>jms-idempotent-consumer</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring-framework.version>6.2.19</spring-framework.version>
        <activemq.version>6.2.6</activemq.version>
        <h2.version>2.3.232</h2.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jms</artifactId>
            <version>${spring-framework.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>${spring-framework.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-tx</artifactId>
            <version>${spring-framework.version}</version>
        </dependency>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>activemq-broker</artifactId>
            <version>${activemq.version}</version>
        </dependency>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>activemq-client</artifactId>
            <version>${activemq.version}</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>${h2.version}</version>
            <scope>runtime</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tệp `src/main/java/demo/IdempotentConsumerDemo.java`:

~~~java
package demo;

import java.math.BigDecimal;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.MessageListener;
import jakarta.jms.TextMessage;

import org.apache.activemq.ActiveMQConnectionFactory;
import org.apache.activemq.broker.BrokerService;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.listener.SimpleMessageListenerContainer;
import org.springframework.transaction.support.TransactionTemplate;

public class IdempotentConsumerDemo {

    public static void main(String[] args) throws Exception {
        // Database dùng chung cho inbox và business write.
        DriverManagerDataSource dataSource = new DriverManagerDataSource();
        dataSource.setDriverClassName("org.h2.Driver");
        dataSource.setUrl("jdbc:h2:mem:idempotent_demo;DB_CLOSE_DELAY=-1");
        dataSource.setUsername("sa");
        dataSource.setPassword("");

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);

        jdbc.execute("""
                CREATE TABLE processed_event (
                    consumer_name VARCHAR(100) NOT NULL,
                    business_key VARCHAR(160) NOT NULL,
                    processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (consumer_name, business_key)
                )
                """);

        jdbc.execute("""
                CREATE TABLE payment_ledger (
                    entry_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    payment_id VARCHAR(80) NOT NULL,
                    account_id VARCHAR(80) NOT NULL,
                    amount DECIMAL(19, 2) NOT NULL
                )
                """);

        DataSourceTransactionManager dbTransactionManager =
                new DataSourceTransactionManager(dataSource);

        TransactionTemplate dbTransaction =
                new TransactionTemplate(dbTransactionManager);

        PaymentService paymentService =
                new PaymentService(jdbc, dbTransaction);

        BrokerService broker = new BrokerService();
        broker.setBrokerName("idempotent-jms-demo");
        broker.setPersistent(false);
        broker.setUseJmx(false);
        broker.start();
        broker.waitUntilStarted();

        ActiveMQConnectionFactory connectionFactory =
                new ActiveMQConnectionFactory(
                        "vm://idempotent-jms-demo?create=false"
                );

        SimpleMessageListenerContainer container =
                new SimpleMessageListenerContainer();

        CountDownLatch handled = new CountDownLatch(2);

        try {
            container.setConnectionFactory(connectionFactory);
            container.setDestinationName("payments.idempotent.demo");
            container.setConcurrentConsumers(1);

            // JMS receipt + listener execution dùng local JMS transaction.
            container.setSessionTransacted(true);

            container.setMessageListener((MessageListener) message -> {
                try {
                    String body = ((TextMessage) message).getText();
                    String[] fields = body.split("\\|", -1);

                    if (fields.length != 3) {
                        throw new IllegalArgumentException(
                                "Expected paymentId|accountId|amount"
                        );
                    }

                    Payment payment = new Payment(
                            fields[0],
                            fields[1],
                            new BigDecimal(fields[2])
                    );

                    boolean applied = paymentService.apply(payment);

                    System.out.println(
                            "result=" + (applied ? "APPLIED" : "DUPLICATE")
                                    + " businessKey=" + payment.paymentId()
                    );

                    handled.countDown();
                }
                catch (JMSException ex) {
                    throw new IllegalStateException(
                            "Cannot read payment message",
                            ex
                    );
                }
            });

            container.afterPropertiesSet();
            container.start();

            JmsTemplate sender = new JmsTemplate(connectionFactory);

            // Hai JMS message riêng biệt nhưng cùng một business operation.
            String event = "payment-1001|account-7|125.00";
            sender.convertAndSend("payments.idempotent.demo", event);
            sender.convertAndSend("payments.idempotent.demo", event);

            if (!handled.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Timed out waiting for both messages"
                );
            }
        }
        finally {
            container.stop();
            container.destroy();
            broker.stop();
            broker.waitUntilStopped();
        }

        Integer ledgerRows = jdbc.queryForObject(
                "SELECT COUNT(*) FROM payment_ledger",
                Integer.class
        );

        BigDecimal ledgerTotal = jdbc.queryForObject(
                "SELECT COALESCE(SUM(amount), 0) FROM payment_ledger",
                BigDecimal.class
        );

        System.out.println("paymentLedgerRows=" + ledgerRows);
        System.out.println(
                "paymentLedgerTotal=" + ledgerTotal.setScale(2).toPlainString()
        );
    }

    private record Payment(
            String paymentId,
            String accountId,
            BigDecimal amount) {
    }

    private static class PaymentService {

        private static final String CONSUMER_NAME = "payment-ledger";

        private final JdbcTemplate jdbc;
        private final TransactionTemplate transaction;

        private PaymentService(
                JdbcTemplate jdbc,
                TransactionTemplate transaction) {
            this.jdbc = jdbc;
            this.transaction = transaction;
        }

        boolean apply(Payment payment) {
            try {
                transaction.executeWithoutResult(status -> {
                    // Unique constraint atomically claims the business key.
                    jdbc.update("""
                            INSERT INTO processed_event (
                                consumer_name,
                                business_key
                            ) VALUES (?, ?)
                            """,
                            CONSUMER_NAME,
                            payment.paymentId()
                    );

                    // Side effect nằm trong cùng DB transaction với inbox row.
                    jdbc.update("""
                            INSERT INTO payment_ledger (
                                payment_id,
                                account_id,
                                amount
                            ) VALUES (?, ?, ?)
                            """,
                            payment.paymentId(),
                            payment.accountId(),
                            payment.amount()
                    );
                });

                return true;
            }
            catch (DuplicateKeyException duplicate) {
                // Transaction đã rollback trước khi DuplicateKeyException
                // được bắt ở ngoài TransactionTemplate.
                return false;
            }
        }
    }
}
~~~

Chạy từ thư mục chứa `pom.xml`:

~~~bash
mvn -q compile org.codehaus.mojo:exec-maven-plugin:3.5.0:java -Dexec.mainClass=demo.IdempotentConsumerDemo
~~~

Kết quả stdout do chương trình tạo:

~~~text
result=APPLIED businessKey=payment-1001
result=DUPLICATE businessKey=payment-1001
paymentLedgerRows=1
paymentLedgerTotal=125.00
~~~

Giải thích:

1. Hai JMS message được gửi riêng biệt, nhưng cùng mang `paymentId=payment-1001`.
2. Listener gọi `PaymentService.apply()`.
3. Transaction đầu tiên insert `payment-ledger / payment-1001` vào `processed_event`, sau đó ghi một dòng vào `payment_ledger`.
4. Transaction thứ hai vi phạm primary key của `processed_event`. Spring dịch lỗi thành `DuplicateKeyException`; transaction rollback trước khi service trả về `false`.
5. Listener coi duplicate là kết quả đã xử lý, trả về bình thường và JMS transaction acknowledge message thứ hai.
6. Database chỉ có một ledger row, tổng tiền vẫn là 125.00.

Ví dụ dùng H2 in-memory và broker non-persistent để tập trung vào thuật toán idempotency. Trong production, dùng database bền vững, connection pool, broker persistence, security, schema migration và chính sách redelivery/DLQ phù hợp.

## 8. Dùng @Transactional trong ứng dụng Spring

Trong ứng dụng Spring thực tế, có thể tách listener và business service thành hai bean. Service dùng database transaction; listener container dùng local JMS transaction.

Service:

~~~java
@Service
public class PaymentService {

    private final JdbcTemplate jdbc;

    public PaymentService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(transactionManager = "transactionManager")
    public void apply(PaymentEvent event) {
        jdbc.update("""
                INSERT INTO processed_event(consumer_name, business_key)
                VALUES (?, ?)
                """,
                "payment-ledger",
                event.paymentId()
        );

        jdbc.update("""
                INSERT INTO payment_ledger(payment_id, account_id, amount)
                VALUES (?, ?, ?)
                """,
                event.paymentId(),
                event.accountId(),
                event.amount()
        );
    }
}
~~~

Listener bắt duplicate bên ngoài transaction proxy:

~~~java
@Component
public class PaymentListener {

    private final PaymentService paymentService;

    public PaymentListener(PaymentService paymentService) {
        this.paymentService = paymentService;
    }

    @JmsListener(destination = "payments.queue")
    public void receive(PaymentEvent event) {
        try {
            paymentService.apply(event);
        }
        catch (DuplicateKeyException duplicate) {
            // DB transaction trong service đã rollback.
            // Trả về bình thường để JMS container acknowledge duplicate.
            log.info("Duplicate payment ignored: {}", event.paymentId());
        }
    }
}
~~~

Cấu hình listener container:

~~~java
@Bean
public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
        ConnectionFactory connectionFactory) {

    DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();

    factory.setConnectionFactory(connectionFactory);
    factory.setSessionTransacted(true);
    factory.setConcurrency("2-5");

    return factory;
}
~~~

Cấu hình database transaction manager:

~~~java
@Bean
public PlatformTransactionManager transactionManager(DataSource dataSource) {
    return new DataSourceTransactionManager(dataSource);
}
~~~

Các điểm cần chú ý:

- `PaymentService` phải là bean riêng được gọi qua Spring proxy; self-invocation trong cùng bean có thể bỏ qua transactional proxy.
- Bắt `DuplicateKeyException` ở ngoài phương thức transactional để transaction đã rollback hoàn toàn trước khi listener trả về bình thường.
- Nếu exception không phải duplicate mà là lỗi database/network, để nó thoát khỏi listener để JMS transaction rollback và broker có thể redeliver.
- Không nuốt tất cả exception rồi trả về bình thường; như vậy container có thể commit message dù business processing thất bại.
- Nếu có nhiều transaction manager, chỉ rõ tên manager cho `@Transactional`.

## 9. Xử lý nhiều consumer và nhiều instance

Unique constraint phải nằm trong kho dữ liệu dùng chung giữa các instance.

Giả sử hai instance nhận cùng business event gần như đồng thời:

~~~text
Instance A                    Database                    Instance B
    |                            |                            |
    |---- INSERT key ----------->|<----------- INSERT key -----|
    |                            |                            |
    |                     unique constraint                   |
    |                            |                            |
    |<--- INSERT succeeds -------|------ duplicate error ---->|
    |                            |                            |
    |---- business write ------->|                            |
    |---- COMMIT --------------->|                            |
    |                            |<---- ROLLBACK --------------|
~~~

Database đảm bảo chỉ một transaction chiếm được khóa. Instance còn lại nhận duplicate key và bỏ qua side effect.

Không dựa vào:

- `synchronized` trong một JVM.
- `ConcurrentHashMap` hoặc `HashSet` cục bộ.
- Một câu SELECT trước INSERT.
- Lock chỉ tồn tại trong bộ nhớ của một node.

Nếu dùng Redis hoặc Spring Integration `ConcurrentMetadataStore`, cần dùng thao tác atomic put-if-absent hoặc selector tương ứng. Tuy nhiên, nếu metadata store và business database là hai hệ thống khác nhau, vẫn còn failure window giữa việc đánh dấu key và business commit. Với side effect trong database, inbox row trong cùng DB transaction thường dễ bảo đảm nhất.

## 10. Payload conflict: cùng key nhưng nội dung khác

Một trường hợp nguy hiểm là cùng business key nhưng payload khác nhau.

Ví dụ:

~~~text
paymentId=payment-1001, amount=125.00
paymentId=payment-1001, amount=950.00
~~~

Không nên tự động coi message thứ hai là duplicate hợp lệ. Nó có thể là:

- Producer bug tạo hai nội dung cho cùng operation.
- Một event bị sửa sau khi đã phát hành.
- Key collision do thiết kế business key chưa đủ phạm vi.
- Message giả mạo hoặc dữ liệu bị hỏng.

Có thể lưu thêm `payload_hash`, event type và schema version trong inbox table:

~~~sql
ALTER TABLE processed_event
    ADD COLUMN payload_hash VARCHAR(128);
~~~

Khi gặp key đã tồn tại:

1. Đọc hash đã lưu.
2. So sánh với hash của payload mới.
3. Nếu giống nhau, coi là duplicate của cùng nội dung.
4. Nếu khác nhau, phát cảnh báo, ghi audit và chuyển message vào quarantine/DLQ theo chính sách.
5. Không âm thầm bỏ qua một business conflict.

Hash nên được tạo từ representation ổn định (canonical serialization), không dùng JSON bytes tùy ý nếu thứ tự field hoặc whitespace có thể thay đổi mà nội dung nghiệp vụ không đổi.

## 11. Retention và replay

Inbox table có thể tăng liên tục. Việc xóa key cần dựa trên thời gian hệ thống còn có khả năng nhận lại event.

Retention phải dài hơn:

- Broker redelivery window.
- Retry của producer.
- Thời gian message nằm trong DLQ.
- Thời gian vận hành cho phép replay.
- Thời gian event được giữ trong event archive.
- Các cửa sổ retry của hệ thống ngoài.

Nếu xóa key quá sớm, một message cũ được replay có thể trở thành side effect mới.

Các lựa chọn:

- Giữ key lâu dài cho nghiệp vụ chỉ được thực hiện một lần, như payment capture hoặc refund.
- Giữ key theo retention policy đã được thống nhất với producer, broker và DLQ.
- Dùng partition theo tháng/ngày khi lượng event lớn, nhưng bảo đảm partition retention không xóa nhầm key còn trong replay window.
- Dùng business table unique key làm bằng chứng xử lý nếu bản ghi nghiệp vụ tồn tại suốt vòng đời cần bảo vệ.

Không dùng TTL mặc định ngắn chỉ để giới hạn kích thước inbox. Thời hạn dedupe là một phần của contract reliability.

## 12. Side effect bên ngoài database

Một database transaction không thể tự rollback một HTTP request đã thành công ở hệ thống khác.

Ví dụ:

~~~text
BEGIN DB TX
  INSERT inbox key
  gọi Payment Provider
  provider đã charge thành công
  DB transaction rollback
END
~~~

Khi message được redeliver, consumer có thể charge lần nữa. Ghi inbox key trong DB không đủ để bảo vệ một side effect nằm ngoài transaction đó.

Các cách xử lý:

### Idempotency key của provider

Gửi business key tới API bên ngoài nếu provider hỗ trợ:

~~~http
Idempotency-Key: payment-1001
~~~

Provider lưu key và trả lại kết quả của operation cũ khi nhận lại cùng key. Cần đọc contract của provider về scope, retention và hành vi khi payload thay đổi.

### Transactional Outbox

Nếu cần publish event sau khi cập nhật database:

1. Cập nhật business tables.
2. Insert outbox row trong cùng DB transaction.
3. Commit.
4. Relay đọc outbox và publish JMS message.
5. Relay đánh dấu đã publish sau khi gửi thành công.

Nếu relay crash sau publish nhưng trước khi đánh dấu, nó có thể publish lại. Consumer vẫn cần idempotency key.

### Inbox + Outbox

Kết hợp inbox và outbox để tạo chuỗi xử lý:

- Inbox ngăn một input event gây side effect DB hai lần.
- Outbox bảo đảm event đầu ra được lưu cùng business update.
- Consumer tiếp theo dùng inbox riêng để dedupe event đầu ra.

Đây là cách phổ biến để xây dựng workflow event-driven không cần một transaction phân tán cho mọi service.

## 13. Spring Integration IdempotentReceiverInterceptor và MetadataStore

Nếu message đi qua Spring Integration flow, có thể dùng `IdempotentReceiverInterceptor` để hỗ trợ Enterprise Integration Pattern Idempotent Receiver.

Interceptor là AOP Advice áp dụng lên `MessageHandler.handleMessage()`. Nó dùng `MessageSelector` hoặc `MetadataStoreSelector` để quyết định message đã được xử lý hay chưa. Khi bị xem là duplicate, interceptor có thể:

- Đánh dấu header `duplicateMessage=true` để handler quyết định cách xử lý.
- Chuyển message tới `discardChannel`.
- Ném exception nếu cấu hình `throwExceptionOnRejection`.

Ví dụ Java configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.handler.advice.IdempotentReceiverInterceptor;
import org.springframework.integration.metadata.ConcurrentMetadataStore;
import org.springframework.integration.selector.MetadataStoreSelector;

@Bean
public IdempotentReceiverInterceptor idempotentReceiverInterceptor(
        ConcurrentMetadataStore metadataStore) {

    return new IdempotentReceiverInterceptor(
            new MetadataStoreSelector(
                    message -> (String) message.getHeaders().get("businessKey"),
                    message -> "processed",
                    metadataStore
            )
    );
}
~~~

Sau đó gắn interceptor vào endpoint Spring Integration bằng `@IdempotentReceiver` hoặc cấu hình endpoint advice.

### Chọn MetadataStore phù hợp

Spring Integration có nhiều implementation:

- `SimpleMetadataStore`: lưu trong bộ nhớ, không giữ trạng thái qua restart.
- `PropertiesPersistingMetadataStore`: lưu file properties; mặc định flush khi application context đóng bình thường.
- `JdbcMetadataStore`: lưu trong database.
- Redis, MongoDB, Hazelcast và các implementation khác.

Nếu chạy nhiều instance, cần một `ConcurrentMetadataStore` có thao tác atomic. Không dùng metadata store in-memory làm nguồn dedupe duy nhất trong production.

`IdempotentReceiverInterceptor` giúp lọc và đánh dấu duplicate, nhưng ứng dụng vẫn phải thiết kế business key, retention và transaction đúng. Nếu metadata store không cùng transaction với business database, hãy tính đến failure window giữa hai nơi. Với side effect quan trọng trong cùng database, unique inbox table và business write trong cùng transaction thường là lựa chọn dễ kiểm soát hơn.

Tham khảo [Spring Integration: Idempotent Receiver](https://docs.spring.io/spring-integration/reference/6.5/handler-advice/idempotent-receiver.html) và [Metadata Store](https://docs.spring.io/spring-integration/reference/6.5/meta-data-store.html).

## 14. Redelivery limit, poison message và DLQ

Idempotency bảo vệ message được xử lý thành công nhiều lần. Nó không giải quyết message không thể xử lý vì dữ liệu sai hoặc lỗi vĩnh viễn.

Cần phân loại:

- **Transient failure:** database tạm thời mất kết nối, service ngoài timeout. Có thể retry với backoff.
- **Permanent business failure:** dữ liệu thiếu hoặc vi phạm quy tắc nghiệp vụ. Có thể chuyển sang rejection/quarantine.
- **Poison message:** luôn làm listener thất bại, khiến broker giao lại vô hạn nếu không có giới hạn.
- **Duplicate:** business key đã được xử lý với cùng payload. Thường ghi nhận duplicate và hoàn tất listener bình thường.

Cấu hình broker redelivery policy với:

- Số lần thử tối đa.
- Delay/backoff giữa các lần thử.
- Dead-letter queue (DLQ).
- Quy trình điều tra và replay DLQ.
- Metrics cho redelivery count và message age.

Không dùng `JMSXDeliveryCount` làm business key hoặc làm điều kiện duy nhất để bỏ qua message. Dùng nó để quan sát retry và phát hiện poison message.

Khi replay từ DLQ, giữ nguyên business key gốc. Nếu thay key trong quá trình replay, hệ thống sẽ coi đó là operation mới.

## 15. Lỗi thường gặp

1. **Dùng JMSMessageID làm idempotency key.** Producer gửi lại cùng event có thể tạo JMSMessageID mới. Dùng business key ổn định trong payload/property.
2. **Chỉ dedupe khi JMSRedelivered=true.** Producer có thể publish lại event thành message mới với cờ false.
3. **Dùng orderId cho mọi thao tác.** Một order có thể có nhiều payment, refund hoặc invoice. Chọn key đại diện cho đúng operation.
4. **Dùng check-then-insert.** Hai consumer đồng thời có thể cùng thấy key chưa tồn tại. Dùng unique constraint và insert-first.
5. **Dùng in-memory Set làm nguồn sự thật.** Nó mất khi restart và không đồng bộ giữa các instance.
6. **Ghi inbox và business data trong hai transaction riêng.** Crash giữa hai commit có thể làm mất side effect hoặc áp dụng hai lần.
7. **Ghi inbox trước side effect rồi commit riêng.** Nếu process dừng sau khi đánh dấu, message replay bị bỏ qua dù business work chưa chạy.
8. **Ghi business data trước rồi đánh dấu riêng.** Nếu process dừng giữa hai bước, lần redelivery có thể lặp side effect.
9. **Bắt mọi exception rồi trả về bình thường.** JMS container có thể commit message dù business processing thất bại. Chỉ coi duplicate đã xác nhận là kết quả thành công.
10. **Dùng một key cho các consumer có side effect độc lập.** Đặt scope theo consumer/operation để mỗi consumer có thể xử lý một lần.
11. **Bỏ qua cùng key nhưng payload khác.** So sánh payload hash hoặc event version và đưa conflict vào quarantine.
12. **Xóa inbox key quá sớm.** Replay từ DLQ hoặc producer retry có thể tạo side effect mới.
13. **Cho rằng JMS transaction tự bao gồm database.** Local JMS transaction và local DB transaction độc lập; dùng inbox pattern hoặc XA/JTA.
14. **Gọi API ngoài rồi chỉ dựa vào DB inbox.** Dùng idempotency key của provider hoặc transactional outbox/saga.
15. **Cho rằng idempotency đồng nghĩa exactly-once end-to-end.** Mỗi ranh giới side effect cần cơ chế riêng; delivery vẫn có thể lặp.
16. **Bỏ qua concurrency.** Cấu hình nhiều listener thread đòi hỏi database unique constraint hoặc atomic store dùng chung.
17. **Replay DLQ với business key mới.** Làm mất khả năng nhận diện operation đã xử lý.
18. **Không kiểm thử crash window.** Kiểm tra cả lỗi trước DB commit, sau DB commit nhưng trước JMS commit, và lỗi khi publish event đầu ra.

## 16. Checklist thiết kế idempotent consumer

- [ ] Xác định chính xác business operation cần bảo vệ.
- [ ] Chọn business key ổn định, không phụ thuộc JMS transport ID.
- [ ] Xác định scope theo consumer, tenant, event type hoặc aggregate version.
- [ ] Đưa business key vào payload hoặc JMS property theo contract rõ ràng.
- [ ] Tạo inbox table với unique constraint.
- [ ] Dùng insert-first thay vì SELECT rồi INSERT.
- [ ] Ghi inbox key và business side effect trong cùng DB transaction.
- [ ] Bắt duplicate key ở ngoài transaction đã rollback.
- [ ] Chỉ coi duplicate là thành công nếu payload/key nhất quán.
- [ ] Bật `sessionTransacted=true` hoặc transaction strategy phù hợp cho listener container.
- [ ] Để lỗi transient thoát khỏi listener để JMS rollback/redelivery.
- [ ] Thiết kế listener idempotent khi nhiều consumer instance chạy song song.
- [ ] Giữ key đủ lâu cho redelivery, retry và DLQ replay.
- [ ] Dùng provider idempotency key hoặc outbox cho side effect bên ngoài DB.
- [ ] Cấu hình redelivery limit, backoff và DLQ.
- [ ] Theo dõi duplicate count, redelivery count, payload conflict và xử lý DLQ.
- [ ] Kiểm thử restart, concurrent duplicate, DB rollback và failure giữa DB/JMS commit.

## 17. Kết luận

Xử lý idempotent bằng business key là lớp bảo vệ quan trọng cho JMS consumer theo mô hình at-least-once. Chọn khóa đại diện cho đúng business operation, ghi khóa vào inbox table có unique constraint và thực hiện inbox insert cùng business write trong một database transaction. Kết hợp với JMS local transaction, cách này xử lý được trường hợp DB commit thành công nhưng JMS acknowledgement chưa hoàn tất: message có thể được giao lại nhưng side effect không bị lặp. `JMSRedelivered` và `JMSXDeliveryCount` giúp quan sát retry; chúng không thay thế business key. Với side effect bên ngoài database, dùng idempotency contract của provider, outbox/inbox hoặc XA/JTA tùy yêu cầu nhất quán.

## Tài liệu tham khảo chính thức

- [Spring Framework 6.2.19 Javadoc: AbstractMessageListenerContainer](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/listener/AbstractMessageListenerContainer.html) — sessionTransacted, duplicate message detection, DB/JMS transaction boundary và XA/JTA.
- [Spring Framework 6.2 Reference: Receiving a Message](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html) — listener container, local JMS transaction và redelivery khi listener thất bại.
- [Spring Framework 6.2.19 Javadoc: DefaultMessageListenerContainer](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html) — transaction manager, concurrency, acknowledgement và container behavior.
- [Jakarta Messaging 3.1 Specification, §3.4.7, §3.5.11, §6.2.11](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.pdf) — JMSRedelivered, JMSXDeliveryCount, acknowledgement và duplicate delivery.
- [Spring Integration 6.5 Reference: Idempotent Receiver](https://docs.spring.io/spring-integration/reference/6.5/handler-advice/idempotent-receiver.html) — IdempotentReceiverInterceptor, MetadataStoreSelector, duplicate header và discard behavior.
- [Spring Integration 6.5 Reference: Metadata Store](https://docs.spring.io/spring-integration/reference/6.5/meta-data-store.html) — persistent MetadataStore implementations, ConcurrentMetadataStore và retention.
