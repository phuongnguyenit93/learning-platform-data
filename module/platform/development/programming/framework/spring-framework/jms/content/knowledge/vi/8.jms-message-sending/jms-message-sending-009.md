# Ngoại lệ lúc gửi và giới hạn suy luận về kết quả phía broker trong Spring JMS

## 1. Mục tiêu của bài học

Khi ứng dụng gọi `JmsTemplate.send(...)` hoặc `convertAndSend(...)`, một message được tạo trong JVM rồi được chuyển cho JMS provider để gửi đến Queue hoặc Topic. Lời gọi có thể trả về bình thường, ném ngoại lệ trước khi provider gửi, hoặc ném lỗi khi broker có thể đã nhận message nhưng client không nhận được phản hồi.

Với sự kiện quan trọng như tạo đơn hàng, thanh toán hay cập nhật tồn kho, đây là ranh giới cần hiểu chính xác: **một exception không tự chứng minh message chưa tới broker**, và **send trả về bình thường không tự chứng minh consumer đã xử lý thành công**.

~~~text
Producer application         JMS client/broker             Consumer
        |                            |                         |
        |---- convertAndSend() ----->|                         |
        |                            |--- route/store -------->|
        |<--- return/exception ------|                         |
        |                            |                         |--- xử lý
        |                            |                         |--- ACK/commit
        |                            |                         |
        v                            v                         v
  Kết quả lời gọi         Trạng thái broker        Kết quả nghiệp vụ
~~~

Sau bài này bạn sẽ:

- Nhận biết `JMSException` của Jakarta Messaging và `JmsException` của Spring.
- Phân biệt lỗi **trước thao tác gửi**, lỗi **khi đang gửi** và lỗi **khi commit**.
- Diễn giải đúng ý nghĩa của `convertAndSend` trả về bình thường và những điều chưa được bảo đảm.
- Hiểu cửa sổ *outcome unknown* khi timeout, connection reset, broker failover hoặc ACK gửi bị mất.
- Thiết kế retry với event ID ổn định, consumer idempotent và transactional outbox khi cần.
- Biết test điều gì bằng mock và điều gì cần integration test với broker thật.

## 2. Hai lớp ngoại lệ: Jakarta Messaging và Spring

### 2.1. Jakarta JMS: checked JMSException

Ở API thấp, `jakarta.jms.MessageProducer.send(...)` khai báo `throws JMSException`. Các subclass thường gặp:

| Ngoại lệ Jakarta JMS | Ý nghĩa điển hình |
| --- | --- |
| `JMSSecurityException` | Xác thực hoặc phân quyền JMS không thành công |
| `InvalidDestinationException` | Destination không hợp lệ đối với provider |
| `MessageFormatException` | Kiểu/định dạng message không phù hợp |
| `ResourceAllocationException` | Broker hoặc provider thiếu tài nguyên |
| `TransactionRolledBackException` | Transaction đã bị rollback |
| `JMSException` | Lỗi chung hoặc lỗi provider chưa phân loại |

`JMSException.getErrorCode()` có thể mang mã lỗi do provider quy định, còn `getLinkedException()` có thể chứa nguyên nhân cấp thấp. Đừng xây chính sách retry chung cho mọi broker chỉ từ một chuỗi error code của một vendor.

### 2.2. Spring JMS: runtime JmsException

`JmsTemplate` quản lý connection/session/producer và chuyển checked `JMSException` sang các runtime exception thuộc họ `org.springframework.jms.JmsException`. Ví dụ Spring có `JmsSecurityException`, `InvalidDestinationException`, `ResourceAllocationException` và `UncategorizedJmsException`. Lỗi chuyển đổi message hoặc phân giải destination cũng có thể phát sinh từ tầng Spring trước khi thao tác send xảy ra.

Ví dụ sử dụng:

~~~java
// Snippet trong method đã có JmsOperations operations:
try {
    operations.convertAndSend("orders.events", "ORDER_CREATED:O-42");
} catch (org.springframework.jms.JmsException failure) {
    String errorCode = failure.getErrorCode();
    Throwable root = failure.getMostSpecificCause();
    // Ghi log phù hợp, giữ eventId để retry/reconcile.
    throw failure;
}
~~~

`JmsOperations` là interface; `JmsTemplate` là implementation thường dùng. Nếu gọi Spring API, application code thường bắt `JmsException` thay vì checked `JMSException`.

**Lưu ý:** không phải mọi exception khi gọi `convertAndSend` đều thuộc `JmsException`. Validation tự viết hoặc callback có thể ném `IllegalArgumentException`/runtime exception khác. Cách xử lý phải xét **điểm xảy ra lỗi** và hợp đồng từng method, không dùng `catch (RuntimeException)` rồi luôn cho rằng broker chưa nhận.

## 3. Những mốc khác nhau trong một lần gửi

Một chu kỳ gửi có thể đi qua các trách nhiệm sau:

~~~text
[1] Ứng dụng validate eventId và body
       |
[2] Spring/JMS tạo message, convert và thêm metadata
       |
[3] Provider thực hiện send qua connection/session
       |
[4] Broker nhận, định tuyến, lưu theo policy
       |
[5] Transaction commit (nếu có)
       |
[6] Consumer nhận và chạy handler
       |
[7] Xử lý nghiệp vụ commit và JMS ACK/commit
~~~

Đây là sơ đồ **ranh giới trách nhiệm**, không phải thứ tự tuyệt đối của từng lời gọi implementation: session có thể được lấy trước converter; trong giao dịch bên ngoài, commit có thể xảy ra sau khi method gửi kết thúc.

| Quan sát | Có thể khẳng định | Không được suy luận |
| --- | --- | --- |
| Validation từ chối trước lời gọi JMS | Lần thử hiện tại chưa vào thao tác gửi | Không có một lần gửi khác cho cùng event |
| Chứng minh converter lỗi trước producer send | Lần thử chưa tới tầng gửi | Broker chưa bao giờ có event đó |
| Exception do kết nối không mở được | Connection hiện tại thất bại | Không có event từ một lần thử trước |
| Timeout/reset trong send/commit | Kết quả phía broker có thể không xác định | “Chắc chắn chưa gửi” |
| `convertAndSend` trả về bình thường | Method gửi hoàn tất theo hợp đồng client/provider | Consumer đã nhận hoặc xử lý |
| Queue depth bằng 0 | Không có backlog ở thời điểm đo theo metric | Message chưa từng vào Queue |
| Listener đã in log “received” | Handler chạy tới dòng log đó | DB và ACK đã commit |
| Có chứng cứ DB commit của consumer | Tác dụng phụ DB đã commit | Broker không bao giờ redeliver |

## 4. Tại sao timeout khi gửi có thể gây kết quả không xác định?

Giả sử broker đã ghi nhận message nhưng phản hồi bị mất trên mạng:

~~~text
Producer                         Broker
  |                                 |
  |----- SEND eventId=evt-42 ------>|
  |                                 |-- có thể đã lưu/accept
  |<---------- ACK --X--------------|
  |                                 |
  +-- connection reset / timeout
  +-- client không biết chắc broker đã nhận chưa
~~~

Từ producer, có hai lịch sử khác nhau nhưng cùng biểu hiện timeout:

- **Kịch bản A:** request chưa tới broker; message chưa được chấp nhận.
- **Kịch bản B:** broker đã chấp nhận nhưng phản hồi bị mất; message có thể đang chờ consumer.

Nếu thử lại bằng một message mới, kịch bản B có thể đưa đến **hai bản của cùng sự kiện nghiệp vụ**. Nếu không thử lại, kịch bản A có thể làm mất sự kiện. Vì thế chính sách retry phải dựa vào **event ID ổn định** và consumer có khả năng chống xử lý lặp.

Theo Jakarta Messaging, khi **asynchronous send** với `CompletionListener` báo lỗi qua lời gọi hoặc callback, trạng thái gửi thành công hay chưa có thể **không được xác định**. Với synchronous send, độ xác nhận từ phương thức `send` tùy hợp đồng API và cách provider thực hiện acknowledgement theo delivery mode/QoS; không có kết luận chung cho mọi lỗi mạng.

**Không nhầm asynchronous send của Jakarta JMS** với dùng `@Async` để gọi `JmsTemplate` trên một thread khác. Thread khác không tự biến một lời gọi synchronous `convertAndSend` thành broker confirmation mới.

## 5. Send trả về bình thường nói lên điều gì?

Xét:

~~~java
operations.convertAndSend("orders.events", payload);
System.out.println("SEND_METHOD_RETURNED");
~~~

Sau khi dòng log được in, có thể nói **lời gọi `convertAndSend` đã trở về bình thường trong JVM**. Điều đó không chứng minh:

1. Consumer đang hoạt động hoặc đã nhận message.
2. Consumer đã validate, ghi DB hoặc hoàn thành tác dụng phụ.
3. Session transaction bên ngoài đã commit.
4. Message sẽ không hết TTL hoặc chuyển DLQ.
5. Một non-durable Topic subscriber đang offline đã được dành backlog.
6. Broker có thể tồn tại qua mọi failure dù chưa kiểm tra cấu hình persistence/HA.
7. Chưa từng có bản message trùng từ một retry trước đó.

Trong vận hành, nên đặt tên log rõ mức bằng chứng: `SEND_METHOD_RETURNED`, `BROKER_CONFIRMED` (chỉ khi có chứng cứ provider tương ứng), `CONSUMER_RECEIVED`, `BUSINESS_COMMITTED` và `JMS_ACK_COMMITTED`. Không viết `ORDER_PROCESSED` ngay sau send.

### 5.1. QoS và persistence ảnh hưởng kết luận

JMS có `DeliveryMode.PERSISTENT` và `NON_PERSISTENT`. Persistent dùng mức bảo vệ bền vững hơn theo yêu cầu chuẩn, nhưng cần kiểm tra cách broker ghi journal, HA và trạng thái commit trước khi tuyên bố “đã fsync tới mọi node”. Non-persistent có thể tối ưu latency với mức bảo đảm thấp hơn. Cả hai **không** tự xác nhận consumer xử lý.

Muốn template thực sự gửi với QoS do ứng dụng cấu hình tường minh, cần `setExplicitQosEnabled(true)`:

~~~java
// Snippet cấu hình một JmsTemplate trước khi sử dụng chung:
template.setExplicitQosEnabled(true);
template.setDeliveryPersistent(true);
template.setPriority(4);
template.setTimeToLive(60_000L);
~~~

TTL 60 giây nghĩa là message có thể hết hạn trước khi consumer nhận. Đừng gọi setter `setJMSExpiration` trực tiếp để giả định nó áp TTL trước send; hãy dùng tùy chọn producer/template.

### 5.2. Giao dịch làm thay đổi mốc xác nhận

Khi gửi trong JMS transaction, một lời gọi `send` có thể hoàn tất trước khi toàn bộ transaction commit. Nếu sau đó rollback thì message sẽ không được phân phối như một giao dịch đã commit.

~~~text
begin transaction
  send E42  -> method returns
  send E43  -> method returns
  commit    -> mất kết nối đúng lúc commit
~~~

Lúc mất kết nối ở `commit`, trạng thái commit có thể không rõ. Với transaction do framework/JTA quản lý bên ngoài, `publish()` có thể trả về **trước** mốc transaction commit.

`@Transactional` dùng cho database thông thường không có nghĩa JDBC/JPA và JMS tự động chia sẻ một giao dịch XA. Nếu cần nhất quán DB + messaging, hãy thiết kế outbox hoặc một transaction manager phối hợp đúng nghĩa, theo giới hạn của môi trường.

## 6. Ví dụ Spring Boot 3.3 / Java 17: không gọi thất bại là “chưa gửi”

Mẫu sau sử dụng **ActiveMQ Artemis** và `JmsOperations` (do `JmsTemplate` triển khai). Nó phân biệt được lỗi validation trước JMS và lỗi JMS có kết quả không chắc chắn. Message mang `eventId` ổn định để tiện deduplicate.

### 6.1. Khởi động Artemis local

Máy có Docker:

~~~bash
docker run --detach --rm --name artemis-send-check -p 127.0.0.1:61616:61616 -p 127.0.0.1:8161:8161 -e ARTEMIS_USER=demo -e ARTEMIS_PASSWORD=demo apache/artemis:latest
~~~

Chờ broker sẵn sàng và xem `docker logs artemis-send-check`. Tài khoản `demo` chỉ dành cho thử nghiệm; khi production, dùng secret và ACL tối thiểu. Nếu môi trường broker không cho tự tạo Queue, cần tạo trước `orders.events` và cấp quyền send/consume.

### 6.2. Cấu trúc dự án

~~~text
spring-jms-send-outcome/
  settings.gradle
  build.gradle
  src/main/resources/application.properties
  src/main/java/demo/jms/
    SendOutcomeApplication.java
    OrderEventPublisher.java
    SendUnconfirmedException.java
    OrderEventListener.java
  src/test/java/demo/jms/
    OrderEventPublisherTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'spring-jms-send-outcome'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'demo'
version = '1.0.0'

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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`src/main/resources/application.properties`:

~~~properties
spring.main.web-application-type=none
spring.artemis.mode=native
spring.artemis.broker-url=${JMS_BROKER_URL:tcp://localhost:61616}
spring.artemis.user=${JMS_BROKER_USER:demo}
spring.artemis.password=${JMS_BROKER_PASSWORD:demo}
spring.jms.pub-sub-domain=false
app.jms.orders-destination=orders.events
~~~

Các placeholder trong file trên dùng cú pháp chuẩn Spring (ví dụ `$` + `{JMS_BROKER_URL:tcp://localhost:61616}`). Trên production hãy bỏ credential mặc định và dùng secret injection. Project dùng Spring Boot 3.3.0 như mốc minh họa; với sản phẩm thật phải chọn bản maintenance/security phù hợp.

### 6.3. Entry point

`src/main/java/demo/jms/SendOutcomeApplication.java`:

~~~java
package demo.jms;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;

@SpringBootApplication
@EnableJms
public class SendOutcomeApplication {

    public static void main(String[] args) {
        SpringApplication.run(SendOutcomeApplication.class, args);
    }

    @Bean
    CommandLineRunner sendOnce(OrderEventPublisher publisher) {
        return args -> {
            publisher.publish("evt-order-42",
                    "{\"orderId\":\"O-42\",\"status\":\"created\"}");
            System.out.println("SEND_METHOD_RETURNED eventId=evt-order-42");
        };
    }
}
~~~

`CommandLineRunner` chỉ để mô phỏng một lần gửi khi khởi chạy. Nếu chạy lại, ứng dụng sẽ phát lại một sự kiện mang cùng event ID. Trong production, sự kiện phải được phát khi nghiệp vụ thật sự diễn ra hoặc từ hàng đợi outbox.

### 6.4. Publisher và ngoại lệ diễn đạt đúng giới hạn quan sát

`src/main/java/demo/jms/OrderEventPublisher.java`:

~~~java
package demo.jms;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.jms.JmsException;
import org.springframework.jms.core.JmsOperations;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final JmsOperations operations;
    private final String destination;

    public OrderEventPublisher(
            JmsOperations operations,
            @Value("${app.jms.orders-destination}") String destination) {
        this.operations = operations;
        this.destination = destination;
    }

    public void publish(String eventId, String jsonBody) {
        if (eventId == null || eventId.isBlank()) {
            throw new IllegalArgumentException("eventId must not be blank");
        }
        if (jsonBody == null || jsonBody.isBlank()) {
            throw new IllegalArgumentException("body must not be blank");
        }

        try {
            operations.convertAndSend(destination, jsonBody, message -> {
                message.setStringProperty("eventId", eventId);
                message.setJMSType("order.created.v1");
                return message;
            });
        } catch (JmsException failure) {
            throw new SendUnconfirmedException(eventId, failure);
        }
    }
}
~~~

- Validation xảy ra trước lời gọi JMS. Nếu eventId hoặc body trống, **lần thử này** chưa gọi `JmsOperations`.
- `convertAndSend` chuyển `String` sang `TextMessage` theo converter mặc định của Spring.
- `MessagePostProcessor` đặt business `eventId` ở property và `JMSType` ở header trước khi send.
- `catch (JmsException)` không khẳng định message chưa được broker nhận. Nó bọc lỗi để lớp gọi biết kết quả gửi **không được xác nhận chắc chắn từ ứng dụng**.
- `JmsTemplate` có thể được share sau khi cấu hình; application service không được tự đổi broker URL, transaction hay template setter theo từng event.

`src/main/java/demo/jms/SendUnconfirmedException.java`:

~~~java
package demo.jms;

public final class SendUnconfirmedException extends RuntimeException {

    private final String eventId;

    public SendUnconfirmedException(String eventId, Throwable cause) {
        super("JMS send unconfirmed for eventId=" + eventId, cause);
        this.eventId = eventId;
    }

    public String eventId() {
        return eventId;
    }
}
~~~

Không swallow `SendUnconfirmedException` rồi báo nghiệp vụ thành công. Lớp gọi cần giữ sự kiện để retry, lưu lại kết quả `UNKNOWN` và/hoặc trả thông tin phù hợp hợp đồng API. Không nên đổi event ID khi thử lại.

### 6.5. Listener minh họa việc nhận chưa bằng xử lý hoàn tất

`src/main/java/demo/jms/OrderEventListener.java`:

~~~java
package demo.jms;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderEventListener {

    @JmsListener(destination = "${app.jms.orders-destination}")
    public void onMessage(String jsonBody) {
        System.out.println("CONSUMER_HANDLER_ENTERED body=" + jsonBody);
    }
}
~~~

Dòng log chỉ chứng minh method handler đã chạy tới đó; ứng dụng minh họa chưa ghi DB hay áp idempotency. Spring listener container xử lý ACK/transaction tùy cấu hình, nên đừng đặt tên log này là `BUSINESS_COMMITTED`.

### 6.6. Chạy

~~~bash
gradle test
gradle bootRun
~~~

Nếu kết nối, credential, Queue và listener hợp lệ, console ứng dụng có thể chứa:

~~~text
SEND_METHOD_RETURNED eventId=evt-order-42
CONSUMER_HANDLER_ENTERED body={"orderId":"O-42","status":"created"}
~~~

Hai dòng **có thể xuất hiện theo thứ tự khác** vì listener chạy thread riêng; log Spring và broker cũng xuất hiện xen kẽ. Nếu kết nối thất bại, `convertAndSend` có thể ném exception, khi đó không in `SEND_METHOD_RETURNED`.

Để kết thúc broker local:

~~~bash
docker stop artemis-send-check
~~~

## 7. Unit test: chứng minh code gọi đúng interface, không suy ra kết quả broker

Mockito chỉ kiểm tra tương tác trong JVM. Đây là giới hạn cố ý của unit test; kiểm chứng send thực tế cần một broker trong integration test.

`src/test/java/demo/jms/OrderEventPublisherTest.java`:

~~~java
package demo.jms;

import jakarta.jms.JMSException;
import jakarta.jms.Message;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.jms.UncategorizedJmsException;
import org.springframework.jms.core.JmsOperations;
import org.springframework.jms.core.MessagePostProcessor;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

class OrderEventPublisherTest {

    @Test
    void sendsCorrectDestinationAndBusinessEventId()
            throws JMSException {
        JmsOperations operations = mock(JmsOperations.class);
        var publisher = new OrderEventPublisher(operations, "orders.events");

        String body = "{\"orderId\":\"O-42\"}";
        publisher.publish("evt-42", body);

        ArgumentCaptor<MessagePostProcessor> post =
                ArgumentCaptor.forClass(MessagePostProcessor.class);

        verify(operations).convertAndSend(
                eq("orders.events"), eq(body), post.capture());

        Message message = mock(Message.class);
        assertSame(message, post.getValue().postProcessMessage(message));
        verify(message).setStringProperty("eventId", "evt-42");
        verify(message).setJMSType("order.created.v1");
    }

    @Test
    void rejectsInvalidInputBeforeJms() {
        JmsOperations operations = mock(JmsOperations.class);
        var publisher = new OrderEventPublisher(operations, "orders.events");

        assertThrows(IllegalArgumentException.class,
                () -> publisher.publish("  ", "{}"));
        verifyNoInteractions(operations);
    }

    @Test
    void reportsJmsFailureAsUnconfirmed() {
        JmsOperations operations = mock(JmsOperations.class);
        var publisher = new OrderEventPublisher(operations, "orders.events");

        doThrow(new UncategorizedJmsException(
                new JMSException("simulated transport error")))
                .when(operations)
                .convertAndSend(
                    eq("orders.events"), eq("{}"),
                    any(MessagePostProcessor.class));

        SendUnconfirmedException error =
                assertThrows(SendUnconfirmedException.class,
                        () -> publisher.publish("evt-42", "{}"));

        assertEquals("evt-42", error.eventId());
        verify(operations).convertAndSend(
                eq("orders.events"), eq("{}"),
                any(MessagePostProcessor.class));
    }
}
~~~

Ba test kiểm tra: payload/destination/property, validation trước JMS, và cách ứng dụng không gán nhầm lỗi JMS thành “definitely unsent”. Chúng không mô phỏng transaction commit, broker journal hay mất acknowledgement. Cần test với broker thật và fault injection có kiểm soát để học các tình huống đó.

## 8. Retry an toàn trong tình trạng kết quả không xác định

### 8.1. Đừng đổi business event ID khi retry

~~~text
Lần thử 1: eventId=evt-order-42 -> timeout; có thể đã tới broker
Lần thử 2: eventId=evt-order-42 -> send trả về bình thường

Nếu broker nhận cả hai:
  Consumer thấy hai JMS messages nhưng cùng eventId nghiệp vụ.
  Consumer phải bảo vệ để tác dụng phụ chỉ commit một lần.
~~~

`JMSMessageID` là ID vận chuyển của một JMS message, thường do provider cấp. Một lần **republish** cùng nghiệp vụ có thể có JMSMessageID khác, nên không dùng nó thay cho business event ID ổn định.

### 8.2. Lỗi nào nên retry?

- **Lỗi vĩnh viễn:** validation/schema sai, destination chưa được cấp quyền, username/password sai. Cần sửa hợp đồng/cấu hình; retry dày liên tục không giúp.
- **Lỗi tạm thời:** broker restart, connection reset, quota tạm thời, timeout. Có thể retry với exponential backoff, giới hạn attempts, cảnh báo và DLQ/reconciliation.
- **Lỗi outcome không xác định:** chưa chứng minh broker nhận chưa. Có thể retry **cùng eventId**, chấp nhận duplicate và thiết kế consumer idempotent.

Một retry policy đúng phải xét provider, loại exception, thời điểm lỗi và SLA nghiệp vụ. Không có một câu lệnh `catch (JmsException) { retry(); }` dùng đúng cho mọi hệ thống.

### 8.3. Consumer idempotent

Mẫu logic (pseudocode, không phải SQL độc lập chạy trên mọi DB):

~~~text
BEGIN DB TRANSACTION
  INSERT processed_events(event_id='evt-order-42') nếu chưa tồn tại

  Nếu đã có event_id:
      bỏ qua tác dụng phụ bị trùng
  Nếu insert mới:
      cập nhật đơn hàng / tồn kho / sổ cái

COMMIT DB TRANSACTION
JMS ACK hoặc commit theo chính sách listener
~~~

Việc **ghi dấu processed event** và **cập nhật nghiệp vụ** nên nằm trong cùng DB transaction. Nếu DB commit nhưng JMS ACK chưa được broker ghi nhận, message có thể redeliver; consumer nhìn eventId đã xử lý và không thực hiện tác dụng phụ lần thứ hai.

Nếu side effect là email hoặc gọi API bên ngoài, cần thêm cơ chế idempotency cho side effect đó. Chỉ dùng một `HashSet` trong bộ nhớ sẽ mất trạng thái sau restart.

## 9. Transactional outbox khi DB và JMS phải nhất quán

Nếu ứng dụng làm:

~~~text
COMMIT database order O-42
SEND JMS event evt-order-42
~~~

và crash ở giữa, DB có đơn hàng nhưng broker có thể không có event. Nếu gửi JMS trước khi DB commit, lại có khả năng broker nhận event nhưng DB rollback.

**Transactional outbox** lưu sự kiện trong **cùng DB transaction** với nghiệp vụ:

~~~text
BEGIN DB TRANSACTION
  INSERT/UPDATE orders(...)
  INSERT outbox(event_id, payload, state='PENDING')
COMMIT DB TRANSACTION

Outbox worker:
  đọc các row PENDING
  send JMS mang chính event_id
  nếu send returns thì cập nhật trạng thái gửi
  nếu lỗi/unknown thì giữ để thử lại có backoff
~~~

Outbox giúp event tồn tại trong DB dù process crash. Nhưng nếu broker đã nhận JMS message và outbox worker crash **trước khi đánh dấu sent**, worker sẽ gửi lại. Vì thế outbox đem lại cơ sở cho **at-least-once publication** kết hợp consumer idempotent; nó không tự tạo exactly-once toàn hệ thống.

Một `@Transactional` chỉ bao quanh JPA/JDBC không mặc nhiên khiến JMS thuộc cùng transaction XA. Muốn atomic commit giữa hai hệ tài nguyên, cần cơ chế transaction được thiết kế và cấu hình phù hợp; với nhiều service, outbox + idempotency thường dễ vận hành hơn.

## 10. Chẩn đoán lỗi bằng dấu vết phù hợp

Với mỗi event ID, nên log an toàn:

| Trường | Vai trò |
| --- | --- |
| `eventId` | Liên hệ các attempts của cùng sự kiện nghiệp vụ |
| `destination` | Queue/Topic định gửi |
| `attempt` | Thứ tự lần thử |
| `startedAt` / latency | Theo dõi timeout và độ trễ |
| `status` | `SEND_RETURNED` hoặc `UNCONFIRMED` theo mức bằng chứng |
| Exception class/root cause | Phân biệt converter/auth/network/transaction |
| Provider error code | Hỗ trợ chẩn đoán lỗi vendor-specific |
| Transaction/correlation ID | Liên hệ trace xuyên tiến trình |

Không in password, secret, payload nhạy cảm, header chứa token. Đừng ghi log “ORDER_COMPLETED” trong publisher nếu chưa có bằng chứng consumer đã hoàn thành.

Phía broker cần quan sát connection failures, enqueue/dequeue counts, Queue depth, expired messages, DLQ, redelivery, transaction outcomes, durable backlog, persistence và HA. Nhưng **metric tổng** không tự chứng minh trạng thái một event ID cụ thể nếu không có correlation phù hợp.

## 11. Các thí nghiệm nên thực hiện

1. **Validation lỗi trước send:** gọi publisher với `eventId=" "`; unit test verify `JmsOperations` không được gọi.
2. **Broker tắt trước send:** chạy app khi Artemis chưa khởi động; quan sát nguyên nhân connection và wrapper exception. Không dùng trường hợp này thay cho lỗi mất ACK sau send.
3. **Sai credential:** thay password; phân biệt lỗi authentication với timeout mạng. Không retry vô hạn bằng secret sai.
4. **Dừng consumer nhưng giữ broker:** gửi vào Queue hợp lệ; send có thể trả về bình thường trong khi consumer chưa xử lý. Quan sát backlog.
5. **Mất kết nối trong send:** trong môi trường thử nghiệm có fault proxy, cắt mạng khi gửi; giữ nguyên eventId khi retry và kiểm tra duplicate ở broker/consumer.
6. **Crash outbox worker sau send:** cho worker gửi thành công nhưng chưa đánh dấu sent; restart và xác minh consumer idempotent không ghi nghiệp vụ hai lần.
7. **TTL ngắn:** gửi một message TTL vài giây khi không có consumer, chờ hết hạn rồi bật consumer; phân biệt hết hạn với exception gửi.

Để một thí nghiệm có thể lặp lại, ghi rõ broker/client version, mode Queue/Topic, QoS/TTL, transaction boundaries, số lần retry, thời điểm lỗi và dấu mốc producer/consumer. Không tạo fault injection trên hệ thống production.

## 12. Những kết luận sai thường gặp

| Kết luận sai | Điều cần nhớ |
| --- | --- |
| “Send không báo lỗi thì consumer đã xử lý” | Sender và consumer có các bước ACK/commit riêng |
| “Có JmsException nghĩa là chắc chắn chưa gửi” | Lỗi lúc send/commit có thể để outcome unknown |
| “Mỗi retry dùng event ID mới để khỏi trùng” | Cần cùng business event ID để dedup |
| “JMSMessageID tự giải quyết mọi duplicate” | Republish có thể sinh JMSMessageID khác |
| “PERSISTENT đồng nghĩa exactly-once” | Persistence và idempotency là hai vấn đề khác |
| “Queue depth bằng 0 chứng minh chưa gửi” | Consumer có thể nhận ngay hoặc message hết hạn |
| “Listener in received tức là DB đã commit” | Handler có thể lỗi sau khi in log |
| “@Transactional DB tự bao cả JMS” | Không có giao dịch phối hợp thì không atomic |
| “Outbox bảo đảm không bao giờ gửi trùng” | Crash sau send trước cập nhật outbox có thể gây retry |
| “Async callback onException chứng minh chưa gửi” | Theo JMS, trạng thái gửi khi lỗi có thể không xác định |

## 13. Câu hỏi tự đánh giá

**1.** `convertAndSend` trả về bình thường nhưng consumer chưa chạy. Gửi có được coi là lỗi không?

Không nhất thiết. Send theo hợp đồng producer đã hoàn tất; processing downstream là bước khác.

**2.** Một timeout xảy ra ngay sau broker có thể đã ghi message. Có thể khẳng định message chưa được gửi không?

Không. Đây có thể là **outcome unknown**; retry cần giữ eventId và chống duplicate.

**3.** Khi nào có thể xác nhận lần thử chưa gọi JMS?

Khi validation/conversion được chứng minh thất bại trước thao tác send và không có đường send khác trong lần thử đó.

**4.** Một message `PERSISTENT` có bảo đảm consumer xử lý duy nhất một lần không?

Không. Delivery, redelivery, ACK, DB commit và idempotency đều cần được xử lý.

**5.** Vì sao `JMSMessageID` không đủ cho dedup khi producer gửi lại?

Một lần republish có thể nhận message ID mới dù cùng nghiệp vụ. Dùng business eventId ổn định.

**6.** Outbox có thể tạo duplicate trong tình huống nào?

Khi broker đã nhận message nhưng outbox worker crash trước khi đánh dấu event đã gửi; worker sau đó retry.

**7.** Mockito unit test có chứng minh broker đã nhận message không?

Không. Nó chỉ verify application gọi đúng contract; cần broker test thực tế.

## 14. Tài liệu tham khảo chính thức

- Jakarta Messaging 3.1 Specification (send, transaction và xử lý lỗi): https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Jakarta Messaging 3.1 `MessageProducer` API (synchronous và asynchronous send): https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageproducer
- Spring Framework 6.1 `JmsTemplate` API: https://docs.spring.io/spring-framework/docs/6.1.1/javadoc-api/org/springframework/jms/core/JmsTemplate.html
- Spring Framework `JmsException` API: https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/jms/JmsException.html
- Spring Framework — Using Spring JMS: https://docs.spring.io/spring-framework/reference/integration/jms/using.html
- Spring Boot 3.3 — JMS và Artemis: https://docs.spring.io/spring-boot/3.3/reference/messaging/jms.html
- Apache Artemis — Broker persistence: https://artemis.apache.org/components/artemis/documentation/latest/persistence.html

**Ghi nhớ:** `JmsException` là dấu hiệu một thao tác gặp lỗi **từ góc nhìn client**. Khi không có chứng cứ đủ mạnh rằng broker đã hoặc chưa nhận, trạng thái phải được coi là **không xác nhận được**. Hệ thống bền vững xử lý vùng mơ hồ đó bằng eventId ổn định, retry có giới hạn, consumer idempotent và outbox khi cần đồng bộ với DB.
