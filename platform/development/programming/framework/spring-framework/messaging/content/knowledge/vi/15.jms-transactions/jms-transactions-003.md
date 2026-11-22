# Thời điểm xác nhận phụ thuộc chế độ và loại listener container

## Mục tiêu

Trong JMS, nhận được message và xác nhận đã nhận message là hai sự kiện khác nhau. Thời điểm xác nhận (acknowledgement) phụ thuộc vào acknowledgement mode của JMS Session, cách ứng dụng nhận message và cách Spring listener container triển khai việc nhận.

Cùng một cấu hình `AUTO_ACKNOWLEDGE` có thể có thời điểm xác nhận khác nhau giữa `SimpleMessageListenerContainer` và `DefaultMessageListenerContainer`. Nếu chỉ nhìn tên mode mà không xét loại container, bạn có thể đánh giá sai khả năng redelivery và độ tin cậy của hệ thống.

Sau bài này, bạn có thể:

- Phân biệt delivery, listener completion, acknowledgement, commit và rollback.
- Giải thích bốn cách quản lý acknowledgement của JMS.
- Xác định thời điểm ack của synchronous receive, provider callback và Spring listener container.
- So sánh `SimpleMessageListenerContainer` (SMLC) với `DefaultMessageListenerContainer` (DMLC).
- Hiểu ảnh hưởng của `TaskExecutor` trong SMLC.
- Cấu hình `CLIENT_ACKNOWLEDGE` hoặc transacted session trong Spring.
- Dự đoán khi nào message được redeliver và khi nào có thể bị mất.
- Thiết kế idempotency, retry và dead-letter handling phù hợp.
- Chạy ví dụ Spring Boot + embedded Artemis để quan sát AUTO ack và transactional rollback.

## 1. Phân biệt delivery, xử lý và acknowledgement

Một message có thể đi qua nhiều mốc:

1. Broker chọn message và giao nó cho consumer.
2. JMS provider chuyển message tới ứng dụng.
3. Listener hoặc code nghiệp vụ bắt đầu xử lý.
4. Nghiệp vụ hoàn tất hoặc phát sinh lỗi.
5. Client xác nhận message, hoặc transaction commit/rollback.
6. Broker loại message khỏi luồng giao nhận hoặc chuẩn bị giao lại.

Các thuật ngữ:

| Thuật ngữ | Ý nghĩa |
|---|---|
| Delivery | Provider giao message cho consumer/session. |
| Listener completion | Phương thức xử lý message đã trả về. |
| Acknowledgement (ack) | Client/session xác nhận đã nhận message theo mode đang dùng. |
| Commit | Hoàn tất một transaction JMS; input message được acknowledge và output message trong transaction được gửi. |
| Rollback | Hủy transaction JMS; message đầu vào được phục hồi để có thể giao lại. |
| Redelivery | Provider giao lại message chưa được xác nhận hoặc đã được phục hồi sau rollback/recover. |

**Ack không tự chứng minh nghiệp vụ đã hoàn tất.** Nếu message được ack trước khi handler cập nhật database, lỗi trong handler có thể làm message biến mất khỏi queue trong khi nghiệp vụ chưa chạy xong.

Ngược lại, nếu nghiệp vụ đã commit database nhưng JMS transaction chưa commit, process có thể chết và message được giao lại. Consumer khi đó có thể chạy side effect lần thứ hai.

## 2. Các acknowledgement mode của Jakarta Messaging

Ack mode được cấu hình trên JMS `Session` nếu session không transacted.

### AUTO_ACKNOWLEDGE

Provider tự động xác nhận message:

- Với synchronous receive, khi lời gọi `receive()` trả về thành công.
- Với asynchronous `MessageListener`, sau khi callback `onMessage()` xử lý message và trả về thành công.

Với synchronous receive, ứng dụng nhận message trước, rồi mới chạy logic nghiệp vụ sau khi `receive()` trả về. Do đó, ack đã xảy ra trước phần xử lý nghiệp vụ bên ngoài lời gọi receive.

Với callback bất đồng bộ thuần JMS, callback trả về bình thường là mốc ack. Tuy nhiên, Spring container có thể thay đổi thứ tự nội bộ bằng cách dùng polling receive hoặc tự bắt exception; xem các phần tiếp theo.

### CLIENT_ACKNOWLEDGE

Ứng dụng xác nhận message bằng cách gọi:

~~~java
message.acknowledge();
~~~

Một điểm dễ bỏ sót: theo JMS, gọi `acknowledge()` trên một message sẽ xác nhận **tất cả message đã được giao bởi cùng Session** kể từ lần ack trước. Nó không chỉ xác nhận riêng message đang cầm.

Nếu cần xác nhận từng message độc lập, phải xem xét khả năng của provider và chế độ individual acknowledgement riêng của sản phẩm. Đây không phải semantics chuẩn của `CLIENT_ACKNOWLEDGE`.

Nếu muốn phục hồi session về message chưa ack đầu tiên, có thể gọi `session.recover()`. Provider bắt đầu giao lại từ điểm sau message cuối cùng đã được xác nhận.

### DUPS_OK_ACKNOWLEDGE

Provider được phép xác nhận message một cách trì hoãn (lazy acknowledgement) để giảm overhead.

Đổi lại, nếu provider hoặc client gặp lỗi, một số message đã được giao có thể được giao lại. Consumer phải chấp nhận duplicate và xử lý idempotent.

Mode này phù hợp khi throughput quan trọng và nghiệp vụ chịu được duplicate. Nó không phải lựa chọn tốt nếu mỗi message tạo side effect không thể lặp.

### Transacted Session

Khi Session là transacted, ack được quản lý bởi transaction:

- `commit()`: xác nhận các message đầu vào của transaction và hoàn tất các message đầu ra đã gửi trong transaction.
- `rollback()`: phục hồi các message đầu vào để provider có thể giao lại; message đầu ra trong transaction bị hủy.

Với Spring listener container, cấu hình `sessionTransacted=true` khiến mỗi lần listener xử lý chạy trong local JMS transaction. Listener hoàn tất thành công thì container commit; listener ném exception thì container rollback.

Không đặt một acknowledgement mode không transacted rồi kỳ vọng nó điều khiển session transacted. Transactional session dùng commit/rollback để quản lý ack.

## 3. Thời điểm ack theo cách nhận message

Đặc tả JMS mô tả mốc ack theo API nhận message:

~~~mermaid
flowchart TD
    A["Broker giao message"] --> B{"Cách nhận"}
    B -->|Synchronous| C["receive()"]
    C --> D["receive() trả về"]
    D --> E["AUTO ack"]
    E --> F["Ứng dụng xử lý nghiệp vụ"]
    B -->|Asynchronous| G["Provider gọi onMessage()"]
    G --> H["Listener xử lý"]
    H --> I["onMessage() trả về thành công"]
    I --> J["AUTO ack"]
~~~

Với synchronous receive, nếu ứng dụng làm như sau:

~~~java
Message message = consumer.receive();
processBusinessLogic(message);
~~~

thì trong `AUTO_ACKNOWLEDGE`, mốc ack gắn với việc `receive()` trả về. Nếu `processBusinessLogic` thất bại sau đó, message đã được xác nhận và không được tự động giao lại chỉ vì nghiệp vụ thất bại.

Với asynchronous JMS callback thuần, provider gọi `onMessage`; nếu callback trả về thành công, message được xác nhận. Nếu callback ném `RuntimeException`, hành vi redelivery theo JMS spec phụ thuộc mode. Nhưng trong Spring, listener container thường bắt exception và áp dụng policy của container trước khi provider nhìn thấy callback kết thúc.

## 4. Spring thay đổi thời điểm ack theo listener container

Spring có hai listener container tiêu chuẩn:

- `SimpleMessageListenerContainer` (SMLC).
- `DefaultMessageListenerContainer` (DMLC).

Cả hai đều quản lý consumer, session và listener, nhưng cách nhận message khác nhau.

### SimpleMessageListenerContainer

SMLC tạo một số lượng cố định các JMS Session và consumer khi container khởi động. Nó đăng ký listener qua API chuẩn:

~~~java
messageConsumer.setMessageListener(listener);
~~~

Provider gọi listener khi có message. Nếu không cấu hình `TaskExecutor`, callback chạy trong thread nhận message của provider.

Với `AUTO_ACKNOWLEDGE` mặc định:

- Provider gọi listener.
- Spring container gọi listener.
- Listener hoàn tất.
- Ack xảy ra sau listener callback.

Tuy nhiên, Spring `AbstractMessageListenerContainer` mặc định bắt exception của listener, ghi log và không truyền exception đó lên provider. Vì provider không nhìn thấy một callback thất bại, exception nghiệp vụ thông thường không làm SMLC tự động redeliver trong AUTO mode.

Nếu JVM chết trong lúc listener đang chạy trước khi callback hoàn tất, provider có thể giao lại message vì ack chưa xảy ra. Đây là tình huống khác với listener tự ném exception nhưng container đã bắt và xử lý.

SMLC hỗ trợ native JMS transaction qua `sessionTransacted=true`, nhưng không tham gia external transaction theo cách DMLC hỗ trợ.

### DefaultMessageListenerContainer

DMLC thường là lựa chọn phổ biến trong ứng dụng Spring. Thay vì đăng ký callback trực tiếp với provider, nó chủ động gọi các phương thức nhận message như `MessageConsumer.receive()` trong vòng lặp polling rồi dispatch message tới listener.

Với `AUTO_ACKNOWLEDGE` mặc định:

1. DMLC gọi `receive()`.
2. `receive()` trả về message.
3. JMS tự động ack message theo semantics synchronous receive.
4. DMLC gọi listener để xử lý message.

Vì ack đã xảy ra trước khi listener được gọi, exception trong listener không thể khiến message được redeliver theo AUTO mode.

DMLC có thể điều chỉnh concurrency theo tải và tham gia external transaction khi được cấu hình với transaction manager phù hợp, thường là JTA/XA.

### Bảng so sánh thời điểm xác nhận

| Cấu hình | Mốc ack | Listener ném exception |
|---|---|---|
| JMS synchronous receive + AUTO | Khi `receive()` trả về, trước logic xử lý sau receive | Message đã ack; không tự redeliver do lỗi xử lý sau receive |
| JMS provider callback + AUTO thuần | Sau khi `onMessage()` trả về thành công | Theo JMS provider semantics; callback lỗi có thể khiến provider redeliver |
| SMLC + AUTO, không TaskExecutor | Sau callback listener | Spring bắt exception nên user exception không tạo redelivery; JVM chết giữa callback có thể dẫn tới redelivery |
| DMLC + AUTO | Trước khi gọi listener, ngay sau polling receive | Không redelivery khi listener lỗi |
| SMLC + AUTO + TaskExecutor | Trước khi task listener chạy | Task thất bại sau ack không làm message tự redeliver |
| SMLC/DMLC + DUPS_OK | Lazy ack trong hoặc ngay sau xử lý, tùy container | Không redelivery do user exception; có thể duplicate khi process/provider lỗi |
| SMLC/DMLC + CLIENT_ACKNOWLEDGE | Spring container ack sau listener thành công theo mặc định | Best-effort redelivery khi listener lỗi hoặc execution bị gián đoạn |
| SMLC/DMLC + `sessionTransacted=true` | Commit sau listener thành công | Rollback khi listener lỗi; message được giao lại theo provider policy |

Bảng trên mô tả hành vi mặc định của Spring container và JMS mode. Provider, custom listener container, custom acknowledgement mode hoặc executor có thể làm thay đổi chi tiết.

## 5. Vì sao AUTO_ACKNOWLEDGE không bảo đảm xử lý tin cậy?

Tên `AUTO_ACKNOWLEDGE` dễ tạo cảm giác rằng message sẽ chỉ được ack sau khi nghiệp vụ hoàn tất. Điều đó không đúng với mọi cách nhận.

Với DMLC, mốc ack nằm ngay sau `receive()` và trước listener. Nếu listener ghi database thất bại, message đã được ack.

Với SMLC, ack nằm sau callback provider, nhưng Spring container bắt exception và không truyền nó lên provider. Vì vậy một exception nghiệp vụ cũng không tự tạo redelivery trong AUTO mode.

Ví dụ:

~~~text
Broker giao message
        |
        v
Listener bắt đầu
        |
        v
Database update thất bại
        |
        v
Listener ném exception
        |
        +---- DMLC + AUTO: message đã ack trước listener
        |
        +---- SMLC + AUTO: Spring bắt exception, provider không thấy callback thất bại
~~~

Nếu cần redelivery khi listener thất bại, hãy dùng transacted session hoặc CLIENT_ACKNOWLEDGE theo yêu cầu và semantics cụ thể. Spring khuyến nghị dùng `sessionTransacted=true` cho phần lớn use case cần độ tin cậy.

## 6. CLIENT_ACKNOWLEDGE trong Spring container

Theo JMS chuẩn, client gọi `Message.acknowledge()`. Nhưng khi dùng Spring listener container, Spring thường quản lý việc xác nhận sau callback.

Với `sessionAcknowledgeMode=CLIENT_ACKNOWLEDGE`, Spring container mặc định xác nhận message sau khi listener xử lý thành công. Nếu listener ném exception, container không xác nhận message và provider có thể giao lại khi session được phục hồi.

Cấu hình:

~~~java
container.setSessionAcknowledgeMode(Session.CLIENT_ACKNOWLEDGE);
~~~

Hoặc với factory:

~~~java
factory.setSessionAcknowledgeMode(Session.CLIENT_ACKNOWLEDGE);
~~~

Cần nhớ:

- Redelivery được Spring mô tả là best-effort trong mode này.
- Theo semantics JMS chuẩn, một lần `acknowledge()` xác nhận tất cả message đã được giao bởi cùng Session.
- Nếu container quản lý ack sau listener, không nên đồng thời gọi `message.acknowledge()` tùy tiện trong listener.
- Spring Framework từ 6.2.6 cung cấp `setAcknowledgeAfterListener(false)` để tắt acknowledgement tự động sau listener trong các tình huống cần xử lý manual/vendor-specific acknowledgement. Hãy đọc kỹ Javadoc của provider nếu dùng individual acknowledgement.

Với một message listener cần xử lý tin cậy, local transacted session thường dễ hiểu hơn việc tự quản lý CLIENT_ACKNOWLEDGE.

## 7. DUPS_OK_ACKNOWLEDGE và duplicate delivery

`DUPS_OK_ACKNOWLEDGE` cho phép provider xác nhận message muộn hơn để giảm overhead. Spring mô tả thời điểm lazy ack phụ thuộc container:

- DMLC: ack lazy trong quá trình listener execution.
- SMLC: ack lazy ngay sau listener execution.

Không nên chọn mode này nếu nghiệp vụ không thể xử lý duplicate.

Một số tình huống có thể tạo duplicate:

- JVM dừng trước khi provider hoàn tất ack.
- Provider mất kết nối khi ack đang được gửi.
- Message được phục hồi sau lỗi session.
- Consumer nhận lại message do broker redelivery policy.

Kiểm tra các metadata:

- `message.getJMSRedelivered()`: cho biết message có thể đã được giao trước đó.
- `JMSXDeliveryCount`: số lần provider giao message, nếu provider hỗ trợ thuộc tính chuẩn này.

Hai trường này hữu ích để quan sát và chẩn đoán. Chúng không thay thế idempotency key của nghiệp vụ.

## 8. Transacted session: ack sau commit

Khi cấu hình:

~~~java
container.setSessionTransacted(true);
~~~

Spring tạo một local JMS transaction cho mỗi lần listener xử lý message.

Luồng thành công:

~~~text
Receive message
      |
      v
Begin JMS transaction
      |
      v
Run listener
      |
      v
Listener returns successfully
      |
      v
Commit
      |
      v
Message acknowledged
~~~

Luồng thất bại:

~~~text
Receive message
      |
      v
Begin JMS transaction
      |
      v
Run listener
      |
      v
Listener throws exception
      |
      v
Rollback
      |
      v
Message becomes eligible for redelivery
~~~

Cấu hình DMLC:

~~~java
@Bean
DefaultMessageListenerContainer ordersContainer(
        ConnectionFactory connectionFactory,
        MessageListener listener) {

    DefaultMessageListenerContainer container =
            new DefaultMessageListenerContainer();
    container.setConnectionFactory(connectionFactory);
    container.setDestinationName("orders.queue");
    container.setMessageListener(listener);
    container.setSessionTransacted(true);
    return container;
}
~~~

Cấu hình factory cho `@JmsListener`:

~~~java
@Bean
DefaultJmsListenerContainerFactory reliableJmsFactory(
        ConnectionFactory connectionFactory) {

    DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setSessionTransacted(true);
    factory.setConcurrency("2-8");
    return factory;
}
~~~

Sử dụng:

~~~java
@JmsListener(
        destination = "orders.queue",
        containerFactory = "reliableJmsFactory"
)
public void handle(String orderId) {
    processOrder(orderId);
}
~~~

Nếu `processOrder` ném exception, Spring rollback JMS session. Provider có thể giao lại message theo redelivery policy.

SMLC cũng hỗ trợ native JMS transaction bằng `sessionTransacted=true`. SMLC không tham gia external transaction theo cách DMLC hỗ trợ.

## 9. SMLC và TaskExecutor: một ngoại lệ quan trọng

SMLC mặc định chạy listener trong thread callback của provider. Có thể cấu hình `TaskExecutor` để chuyển listener execution sang thread khác:

~~~java
container.setTaskExecutor(taskExecutor);
~~~

Điều này tách việc provider nhận message khỏi thời gian listener xử lý. Nhưng nó cũng thay đổi acknowledgement semantics:

- Message được ack trước khi listener task chạy.
- Session được tái sử dụng ngay để nhận message tiếp theo.
- Listener có thể xử lý đồng thời nhiều message đã nhận từ cùng Session.
- Kết hợp TaskExecutor này với transacted session hoặc CLIENT_ACKNOWLEDGE dẫn tới kết quả không được đặc tả rõ.

Vì vậy, không dùng SMLC `TaskExecutor` như một cách đơn giản để tăng concurrency mà vẫn mong giữ nguyên transaction/ack semantics.

Nếu cần tăng số consumer, hãy cấu hình số consumer phù hợp trên container và cân đối với khả năng xử lý của downstream. Nếu cần transaction tin cậy, ưu tiên container/session được cấu hình transacted.

## 10. Exception handling và redelivery

Spring `AbstractMessageListenerContainer` mặc định bắt exception do listener ném ra, ghi log ở mức WARN và không truyền exception đó lên JMS provider. Container có thể được cấu hình `ErrorHandler` để xử lý lỗi ứng dụng.

Ví dụ:

~~~java
container.setErrorHandler(error ->
        log.error("JMS listener failed", error)
);
~~~

Không nên nhầm ErrorHandler với acknowledgement:

- ErrorHandler ghi nhận hoặc điều phối lỗi.
- Acknowledgement mode/transaction quyết định message đã được xác nhận hay chưa.
- Redelivery policy của provider quyết định số lần giao lại, delay và dead-letter handling.

Trong AUTO mode của DMLC, ErrorHandler được gọi sau khi message đã ack. Ghi log lỗi không thể làm message sống lại.

Trong transacted session, listener exception làm transaction rollback. Broker có thể giao lại message. Số lần redelivery, delay, giới hạn delivery và dead-letter queue phụ thuộc provider.

Một poison message có thể gây vòng lặp rollback/redelivery. Cần cấu hình giới hạn lần giao, backoff và DLQ/quarantine theo sản phẩm broker.

## 11. Local JMS transaction và database transaction

`sessionTransacted=true` quản lý transaction của JMS Session. Nó có thể gom message nhận và message gửi qua cùng session thành một đơn vị công việc.

Ví dụ, listener nhận OrderCreated rồi gửi InventoryReservationRequested qua cùng session. Nếu cùng session và transaction, commit xác nhận input và hoàn tất output; rollback phục hồi input và hủy output.

Nhưng database transaction độc lập không tự động tham gia local JMS transaction.

Một failure window:

1. Listener cập nhật database thành công và database commit.
2. Process chết trước khi JMS transaction commit.
3. Broker giao lại message.
4. Listener chạy lại và có thể cập nhật database lần nữa.

Để xử lý:

- Dùng idempotency key/event ID để nhận biết message đã áp dụng.
- Lưu inbox/processed-message record trong cùng database transaction với nghiệp vụ.
- Dùng transactional outbox cho chiều publish từ database sang broker.
- Chỉ dùng XA/JTA khi thật sự cần transaction phân tán và hạ tầng hỗ trợ.

DMLC có thể tham gia external JTA transaction nếu được cấu hình với transaction manager và XA-capable ConnectionFactory. SMLC không hỗ trợ external transaction theo cách đó.

## 12. Bảng chọn cấu hình theo yêu cầu

| Yêu cầu | Cấu hình nên cân nhắc | Lý do |
|---|---|---|
| Nhận đơn giản, chấp nhận mất message khi handler lỗi | AUTO_ACKNOWLEDGE | Cấu hình đơn giản, nhưng cần hiểu timing của container |
| Queue cần redelivery khi handler ném exception | `sessionTransacted=true` | Rollback transaction khi listener thất bại |
| Topic durable subscription cần xử lý tin cậy | `sessionTransacted=true` cùng durable subscription | Message được commit/rollback theo transaction |
| Muốn dùng acknowledgement tường minh | CLIENT_ACKNOWLEDGE | Client/container kiểm soát ack; phải hiểu ack theo Session |
| Ưu tiên throughput và chịu được duplicate | DUPS_OK_ACKNOWLEDGE | Provider có thể ack lazy |
| Cần phối hợp JMS và database trong một transaction | DMLC + JTA/XA | Receipt và database work có thể cùng commit/rollback |
| Chỉ cần nhận đồng bộ trong một đoạn code | `JmsTemplate.receive(...)` | Calling thread đợi message; AUTO ack xảy ra khi receive trả về |
| Muốn callback provider đơn giản | SMLC | Gần JMS provider callback; số consumer cố định |
| Cần scaling, recovery và external transaction | DMLC | Có polling loop, dynamic adaptation và JTA support |

Đối với phần lớn listener cần xử lý tin cậy, hãy bắt đầu với DMLC hoặc factory mặc định phù hợp và `sessionTransacted=true`. Sau đó đo throughput, latency và redelivery để điều chỉnh concurrency.

## 13. Ví dụ Java 17+ chạy được: quan sát AUTO ack và transaction rollback

Ví dụ này dùng Spring Boot 4.1.2 và embedded ActiveMQ Artemis. Hai DMLC nhận message từ hai queue:

- `auto.queue` dùng mặc định AUTO_ACKNOWLEDGE. Listener ném exception ngay lần đầu. Vì DMLC ack sau polling receive và trước listener, message không được giao lại.
- `tx.queue` dùng `sessionTransacted=true`. Listener ném exception ở lần đầu. Spring rollback transaction, broker giao lại message và listener thành công ở lần thứ hai.

Ví dụ giúp quan sát trực tiếp rằng thời điểm ack phụ thuộc container và session mode.

### Cấu trúc project

~~~text
jms-ack-timing-demo/
  pom.xml
  src/
    main/
      java/
        demo/
          AckTimingDemoApplication.java
          AckProbe.java
      resources/
        application.properties
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>jms-ack-timing-demo</artifactId>
    <version>1.0.0</version>

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
            <scope>runtime</scope>
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

### application.properties

~~~properties
spring.artemis.mode=embedded
spring.artemis.embedded.queues=auto.queue,tx.queue
spring.artemis.embedded.persistent=false
spring.jms.pub-sub-domain=false
~~~

Embedded broker dùng trong bộ nhớ để demo. Không dùng cấu hình này để suy ra durability của broker production.

### AckProbe.java

~~~java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import jakarta.jms.JMSException;
import jakarta.jms.Message;

import org.springframework.stereotype.Component;

@Component
public class AckProbe {

    private final AtomicInteger autoAttempts = new AtomicInteger();
    private final AtomicInteger txAttempts = new AtomicInteger();
    private final AtomicBoolean txRedelivered = new AtomicBoolean();
    private final CountDownLatch completed = new CountDownLatch(2);

    public void onAutoMessage(Message message) {
        autoAttempts.incrementAndGet();

        try {
            throw new IllegalStateException("simulated AUTO listener failure");
        }
        finally {
            completed.countDown();
        }
    }

    public void onTransactedMessage(Message message) {
        int attempt = txAttempts.incrementAndGet();

        if (attempt == 1) {
            throw new IllegalStateException("simulated first-attempt failure");
        }

        try {
            txRedelivered.set(message.getJMSRedelivered());
        }
        catch (JMSException ex) {
            throw new IllegalStateException("Cannot inspect redelivery flag", ex);
        }

        completed.countDown();
    }

    public boolean await(long timeout, TimeUnit unit)
            throws InterruptedException {
        return completed.await(timeout, unit);
    }

    public int autoAttempts() {
        return autoAttempts.get();
    }

    public int txAttempts() {
        return txAttempts.get();
    }

    public boolean txRedelivered() {
        return txRedelivered.get();
    }
}
~~~

### AckTimingDemoApplication.java

~~~java
package demo;

import java.util.concurrent.TimeUnit;

import jakarta.jms.ConnectionFactory;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.listener.DefaultMessageListenerContainer;

@SpringBootApplication
public class AckTimingDemoApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(AckTimingDemoApplication.class, args)) {
            // ApplicationRunner waits for both listener outcomes.
        }
    }

    @Bean
    DefaultMessageListenerContainer autoAckContainer(
            ConnectionFactory connectionFactory,
            AckProbe probe) {

        DefaultMessageListenerContainer container =
                new DefaultMessageListenerContainer();
        container.setConnectionFactory(connectionFactory);
        container.setDestinationName("auto.queue");
        // Default mode is AUTO_ACKNOWLEDGE.
        container.setMessageListener(probe::onAutoMessage);
        return container;
    }

    @Bean
    DefaultMessageListenerContainer transactedContainer(
            ConnectionFactory connectionFactory,
            AckProbe probe) {

        DefaultMessageListenerContainer container =
                new DefaultMessageListenerContainer();
        container.setConnectionFactory(connectionFactory);
        container.setDestinationName("tx.queue");
        container.setSessionTransacted(true);
        container.setMessageListener(probe::onTransactedMessage);
        return container;
    }

    @Bean
    ApplicationRunner sendMessages(
            JmsTemplate jmsTemplate,
            AckProbe probe) {

        return args -> {
            jmsTemplate.convertAndSend("auto.queue", "AUTO");
            jmsTemplate.convertAndSend("tx.queue", "TRANSACTED");

            if (!probe.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Timed out waiting for acknowledgement demo"
                );
            }

            System.out.println("AUTO attempts=" + probe.autoAttempts());
            System.out.println("TRANSACTED attempts=" + probe.txAttempts());
            System.out.println("TRANSACTED redelivered=" + probe.txRedelivered());
        };
    }
}
~~~

Chạy bằng Java 17+ và Maven:

~~~bash
mvn spring-boot:run
~~~

Các dòng stdout do ứng dụng in ra (bỏ qua log khởi động và WARN do listener cố ý ném exception):

~~~text
AUTO attempts=1
TRANSACTED attempts=2
TRANSACTED redelivered=true
~~~

Giải thích:

1. DMLC của `auto.queue` nhận message bằng polling receive. AUTO ack xảy ra khi receive trả về, trước listener.
2. Listener AUTO ném exception. Spring container ghi nhận lỗi, nhưng message đã ack nên broker không giao lại. Số lần listener được gọi là 1.
3. DMLC của `tx.queue` nhận message trong local JMS transaction.
4. Lần gọi đầu ném exception. Container rollback transaction.
5. Broker giao lại message. JMS redelivery flag được đặt thành true.
6. Lần gọi thứ hai thành công. Container commit transaction và message được xác nhận.
7. Kết quả cho thấy AUTO mặc định của DMLC có thể làm mất message khi listener lỗi; transacted session cho phép redelivery.

Ví dụ dùng lỗi có chủ đích để quan sát behavior. Trong production, hãy giới hạn redelivery, cấu hình DLQ và xử lý poison message để tránh rollback vô hạn.

## 14. Failure window và idempotency

Ngay cả khi dùng transacted session, duplicate vẫn có thể xuất hiện ở một số thời điểm.

Ví dụ:

~~~text
Listener nhận message
       |
       v
Database commit thành công
       |
       v
JVM dừng trước JMS commit
       |
       v
Broker rollback/recover message
       |
       v
Message được giao lại
       |
       v
Listener có thể cập nhật database lần nữa
~~~

JMS transaction chỉ bao phủ các thao tác JMS trong session. Nó không tự động bao phủ database transaction.

Một consumer idempotent nên có event ID hoặc business key ổn định. Trước khi thực hiện side effect, consumer kiểm tra message đã được xử lý chưa; trạng thái processed và thay đổi nghiệp vụ nên được ghi trong cùng database transaction.

Nếu yêu cầu atomicity giữa JMS và database, DMLC có thể tham gia JTA/XA khi ConnectionFactory và database đều hỗ trợ XA. XA tăng chi phí vận hành và cần transaction coordinator. Với nhiều hệ thống, transactional outbox/inbox và idempotent consumer là cách thực tế hơn.

## 15. Redelivery, retry và dead-letter queue

Ack/rollback chỉ quyết định message có được xác nhận hay phục hồi. Provider/broker quyết định chính sách giao lại cụ thể:

- Số lần redelivery tối đa.
- Redelivery delay và backoff.
- Message expiration.
- Dead-letter address/queue.
- Cách xử lý poison message.
- Header hoặc property theo dõi delivery count.

Không giả định mọi broker có cùng policy. Kiểm tra tài liệu và cấu hình của Artemis, ActiveMQ Classic, IBM MQ hoặc provider đang dùng.

Khi xử lý lỗi:

- Lỗi hạ tầng tạm thời: retry có giới hạn và backoff.
- Dữ liệu malformed hoặc không hợp lệ cố định: chuyển DLQ/quarantine sau số lần thử phù hợp.
- Lỗi nghiệp vụ có thể khắc phục: phát trạng thái/retry event theo hợp đồng.
- Message duplicate: idempotency key bảo vệ side effect.

Theo dõi `JMSRedelivered`, `JMSXDeliveryCount`, queue depth, DLQ depth, listener exception rate và processing latency.

## 16. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| DMLC không redeliver khi listener ném exception | AUTO ack đã xảy ra sau polling receive và trước listener | Dùng `sessionTransacted=true` hoặc mode phù hợp |
| SMLC không redeliver dù listener ném exception | Spring bắt exception và không truyền nó lên provider trong AUTO mode | Dùng transacted session nếu cần redelivery |
| SMLC mất message khi bật TaskExecutor | Message được ack trước khi task listener chạy | Không dùng TaskExecutor theo cách này nếu cần transaction/client ack |
| Message được giao lại sau khi database đã commit | JMS commit thất bại hoặc process chết trước commit | Dùng idempotency/inbox hoặc XA khi cần |
| Nhiều message được ack cùng lúc trong CLIENT_ACKNOWLEDGE | JMS ack áp dụng cho mọi message đã giao bởi Session | Thiết kế session/consumer phù hợp; dùng provider individual ack nếu thật sự cần |
| DUPS_OK có duplicate | Provider trì hoãn ack | Consumer phải idempotent |
| Listener lỗi nhưng broker không thấy exception | Spring container bắt/log listener exception | Kiểm tra ErrorHandler và transaction mode |
| Message lặp vô hạn | Rollback/redelivery không có giới hạn | Cấu hình retry, backoff và DLQ |
| AUTO ack xảy ra trước xử lý dù JMS spec nói sau callback | DMLC dùng synchronous polling receive nội bộ | Hiểu semantics riêng của từng container |

## 17. Checklist cấu hình acknowledgement

- [ ] Xác định ứng dụng nhận message đồng bộ hay bất đồng bộ.
- [ ] Xác định container là SMLC hay DMLC.
- [ ] Kiểm tra có cấu hình `TaskExecutor` cho SMLC hay không.
- [ ] Không giả định AUTO_ACKNOWLEDGE luôn ack sau listener.
- [ ] Nếu listener lỗi phải redeliver, ưu tiên `sessionTransacted=true`.
- [ ] Nếu dùng CLIENT_ACKNOWLEDGE, hiểu rằng ack chuẩn có phạm vi toàn Session.
- [ ] Nếu dùng DUPS_OK_ACKNOWLEDGE, chuẩn bị xử lý duplicate.
- [ ] Cấu hình ErrorHandler và quan sát listener exception.
- [ ] Cấu hình provider redelivery limit, backoff và DLQ.
- [ ] Consumer có idempotency key hoặc processed-message record.
- [ ] Kiểm thử listener exception, JVM shutdown và broker reconnect.
- [ ] Nếu kết hợp database và JMS, quyết định rõ local transaction, XA/JTA hoặc outbox/inbox.

## Ghi nhớ

- JMS AUTO ack xảy ra khi synchronous `receive()` trả về hoặc khi asynchronous `onMessage()` trả về thành công.
- DMLC dùng polling receive nên AUTO ack xảy ra trước listener execution.
- SMLC dùng provider callback nên AUTO ack xảy ra sau callback; Spring bắt exception nên user exception không tự tạo redelivery.
- SMLC với TaskExecutor ack trước listener task; kết hợp với transacted/client ack có kết quả không được đặc tả rõ.
- CLIENT_ACKNOWLEDGE chuẩn xác nhận tất cả message đã giao bởi cùng Session khi gọi `acknowledge()`.
- DUPS_OK_ACKNOWLEDGE xác nhận lazy và cho phép duplicate.
- `sessionTransacted=true` commit sau listener thành công và rollback khi listener ném exception; provider có thể redeliver.
- Local JMS transaction không tự bao gồm database transaction; cần idempotency hoặc XA/outbox/inbox.
- Ack là xác nhận giao nhận, không phải bằng chứng nghiệp vụ đã hoàn tất.

## Tài liệu chính thức

- [Jakarta Messaging 3.1 Specification — Transactions and acknowledgement](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html#transactions)
- [Jakarta Messaging 3.1 Specification — Message acknowledgement, section 6.2.10](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)
- [Jakarta Messaging 3.1 Specification — Receiving messages asynchronously, section 8.7](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)
- [Spring Framework 7.0.10 Reference — Receiving a Message](https://docs.spring.io/spring-framework/reference/7.0/integration/jms/receiving.html)
- [Spring Framework 7.0.10 Reference — Using Spring JMS](https://docs.spring.io/spring-framework/reference/7.0/integration/jms/using.html)
- [Spring Framework 7.0.10 Javadoc — AbstractMessageListenerContainer](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/jms/listener/AbstractMessageListenerContainer.html)
- [Spring Framework 7.0.10 Javadoc — SimpleMessageListenerContainer](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/jms/listener/SimpleMessageListenerContainer.html)
- [Spring Framework 7.0.10 Javadoc — DefaultMessageListenerContainer](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html)
- [Spring Framework Javadoc — JmsTemplate](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/core/JmsTemplate.html)
