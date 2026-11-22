# SimpleMessageListenerContainer và mô hình callback của nhà cung cấp

## 1. SimpleMessageListenerContainer là gì?

`org.springframework.jms.listener.SimpleMessageListenerContainer` (SMLC) là một message listener container của Spring JMS. Nó kết nối ứng dụng với JMS provider, tạo các `Session` và `MessageConsumer`, đăng ký listener rồi để provider gọi listener khi có message.

Điểm đặc trưng của SMLC là sử dụng callback chuẩn của JMS: `MessageConsumer.setMessageListener(...)`. Provider quản lý việc nhận message và gọi callback. Spring quản lý cấu hình container, số consumer, resource lifecycle, transaction/acknowledgement, exception handling và recovery.

SMLC phù hợp với ứng dụng chạy độc lập hoặc môi trường provider cho phép đăng ký `MessageListener` trực tiếp. Nó có cấu trúc đơn giản, số consumer cố định và hỗ trợ transaction JMS cục bộ. SMLC không hỗ trợ scaling động hoặc tham gia transaction do bên ngoài quản lý; trong Jakarta EE, nó nhìn chung không phù hợp với một số hạn chế JMS của container.

## 2. Mô hình provider callback hoạt động như thế nào?

SMLC không chạy một vòng lặp `receive()` để chủ động lấy từng message. Khi khởi tạo, container tạo các JMS resource và đăng ký listener với từng consumer. Sau đó JMS provider gọi listener khi message đến.

Luồng khái quát:

~~~text
Spring Application Context
          |
          v
SimpleMessageListenerContainer
          |
          +--> shared JMS Connection
          |
          +--> Session 1 --> MessageConsumer 1
          |                      |
          |                      +--> setMessageListener(listener)
          |
          +--> Session 2 --> MessageConsumer 2
                                 |
                                 +--> setMessageListener(listener)

JMS Provider nhận message
          |
          v
Provider gọi MessageListener.onMessage(message)
          |
          v
SMLC xử lý callback và gọi listener ứng dụng
          |
          v
Hoàn tất acknowledgement hoặc commit/rollback
~~~

Với cấu hình mặc định một consumer, container tạo một `Session` và một `MessageConsumer`. Nếu cấu hình ba consumer, container tạo ba cặp Session/Consumer trên connection dùng chung. Mỗi consumer nhận callback từ provider theo cơ chế của provider.

Trong quá trình xử lý, SMLC gọi listener thông qua pipeline nội bộ của `AbstractMessageListenerContainer`. Pipeline này xử lý việc expose session nếu được cấu hình, chuyển exception về cơ chế Spring và áp dụng acknowledgement/transaction theo chế độ đã chọn.

### 2.1. Ai sở hữu thread gọi listener?

Mặc định, SMLC không cấu hình `TaskExecutor`. Listener chạy trực tiếp trên thread nhận message của JMS provider. Khi listener thực thi, endpoint nhận của provider bị chiếm cho tới khi callback kết thúc.

Điều này có nghĩa thời gian xử lý listener ảnh hưởng trực tiếp tới khả năng nhận message tiếp theo của consumer tương ứng. Một listener chạy lâu có thể làm giảm throughput của consumer đó. Có thể tăng số consumer để xử lý song song, nhưng phải cân nhắc thứ tự message và tải lên broker.

### 2.2. Connection, Session và Consumer

SMLC luôn dùng một shared JMS `Connection` cho container. Nó tạo số lượng `Session` và `MessageConsumer` cố định theo cấu hình concurrency. Session được gắn với consumer tương ứng và được dùng trong vòng đời consumer đó.

JMS `Session` không được thiết kế để nhiều thread tùy ý thao tác đồng thời. Mô hình mặc định của SMLC giữ quan hệ giữa callback và Session rõ ràng: provider gọi listener cho consumer, container xử lý message với Session tương ứng. Nếu bật `TaskExecutor`, quy tắc thread và acknowledgement thay đổi đáng kể; cần đọc kỹ phần riêng về executor.

## 3. Các kiểu listener mà SMLC có thể gọi

### 3.1. Jakarta JMS MessageListener

`jakarta.jms.MessageListener` là callback chuẩn của JMS:

~~~java
public interface MessageListener {
    void onMessage(Message message);
}
~~~

Provider gọi `onMessage` khi consumer nhận được message. Listener nhận JMS `Message` như `TextMessage`, `BytesMessage`, `MapMessage` hoặc `ObjectMessage`, rồi đọc payload và thực hiện nghiệp vụ.

Đây là lựa chọn đơn giản khi listener chỉ cần nội dung message và không cần thao tác trực tiếp với `Session`.

### 3.2. SessionAwareMessageListener của Spring

Spring cung cấp `org.springframework.jms.listener.SessionAwareMessageListener<M>` để listener nhận cả message và JMS `Session`:

~~~java
public interface SessionAwareMessageListener<M extends jakarta.jms.Message> {
    void onMessage(M message, jakarta.jms.Session session)
            throws jakarta.jms.JMSException;
}
~~~

Listener có thể dùng Session được truyền vào để tạo response hoặc thực hiện thao tác JMS liên quan. Khi `sessionTransacted=true`, thao tác gửi response qua chính Session đó có thể nằm trong cùng local JMS transaction với việc nhận message.

Không giữ Session sau khi callback kết thúc và không chia sẻ Session cho thread khác. Đặc biệt, không kết hợp `SessionAwareMessageListener` với việc dispatch callback đồng thời qua `TaskExecutor` nếu listener thực hiện công việc trên Session được truyền vào.

### 3.3. POJO listener qua adapter

Nếu muốn listener là một class nghiệp vụ thông thường thay vì triển khai interface JMS, có thể dùng `MessageListenerAdapter`. Adapter nhận JMS callback, chuyển payload theo converter rồi gọi method trên delegate object. Cần phân biệt adapter này với callback provider: provider vẫn gọi listener mà container đã đăng ký; adapter chỉ là lớp chuyển tiếp tới method POJO.

## 4. Cấu hình SMLC và các thuộc tính quan trọng

SMLC có thể cấu hình bằng Java, XML hoặc Spring container. Những thuộc tính thường cần xem xét:

| Thuộc tính | Mặc định/ý nghĩa | Khi nào điều chỉnh? |
| --- | --- | --- |
| `connectionFactory` | JMS `ConnectionFactory` do provider/server cung cấp | Luôn phải cấu hình đúng provider và môi trường |
| `destinationName` hoặc `destination` | Tên hoặc object Queue/Topic cần lắng nghe | Chọn đúng destination đã provision |
| `messageListener` | Listener được provider gọi | Dùng `MessageListener`, `SessionAwareMessageListener` hoặc adapter phù hợp |
| `concurrentConsumers` | Mặc định `1`; số consumer cố định được tạo | Tăng cho queue khi cần throughput và chấp nhận xử lý song song |
| `sessionTransacted` | Mặc định `false` | Bật `true` khi cần rollback và redelivery theo local JMS transaction |
| `sessionAcknowledgeMode` | Mặc định `AUTO_ACKNOWLEDGE` | Chọn chế độ ack phù hợp; thường ưu tiên `sessionTransacted=true` cho reliability |
| `taskExecutor` | Mặc định không có; listener chạy trên provider thread | Chỉ dùng khi hiểu rõ thay đổi về ack, Session và concurrency |
| `connectLazily` | Mặc định `false`; kết nối sớm trong giai đoạn khởi tạo | Bật nếu muốn trì hoãn việc kết nối tới giai đoạn start của container |
| `recoverOnException` | Mặc định `true` | Tắt khi chủ động dựa vào cơ chế automatic recovery của provider |
| `errorHandler` | Không có handler riêng mặc định | Cấu hình để ghi nhận uncaught listener exception theo chính sách ứng dụng |

`SimpleMessageListenerContainer` cũng nhận cấu hình dạng chuỗi `concurrency`, nhưng nó luôn tạo số consumer bằng giới hạn trên và không tự scale giữa hai giới hạn. Với SMLC, nên dùng trực tiếp `setConcurrentConsumers(int)` để thể hiện rõ số consumer cố định.

### 4.1. Khởi động và dừng container

SMLC triển khai Spring lifecycle (`SmartLifecycle`). Khi Spring context khởi động, container được khởi tạo và tự start theo cấu hình lifecycle mặc định. Có thể điều khiển `start()`/`stop()` nếu cần tạm dừng tiếp nhận message.

Khi initialize, SMLC tạo connection dùng chung và các Session/Consumer tương ứng. Khi shutdown, container đóng các consumer và Session đã đăng ký. Nên để Spring quản lý lifecycle của bean thay vì tự đóng Session hoặc Consumer bên trong listener.

`connectLazily=true` trì hoãn việc thiết lập connection, Session và Consumer tới giai đoạn start của container. Thuộc tính này thay đổi thời điểm kết nối; nó không thay thế cơ chế retry/recovery khi broker mất kết nối.

## 5. Concurrency: số consumer cố định

`setConcurrentConsumers(int)` chỉ định số consumer SMLC tạo. Mặc định là `1`. Số consumer được tạo khi container khởi tạo và giữ cố định trong vòng đời container; SMLC không tăng hoặc giảm số consumer theo backlog.

Với queue, nhiều consumer có thể cùng nhận message từ một destination. Điều này tăng khả năng xử lý song song, nhưng thứ tự xử lý tổng thể không còn được bảo đảm. Ví dụ message thứ hai có thể được consumer 2 xử lý xong trước message thứ nhất ở consumer 1.

Với topic, tăng số consumer có thể khiến mỗi consumer nhận cùng một publication. Vì vậy không nên tăng `concurrentConsumers` cho topic trừ khi thực sự muốn nhiều consumer/subscription xử lý bản sao của publication.

Quy tắc chọn ban đầu:

- Queue tải thấp hoặc cần giữ thứ tự xử lý gần nhất có thể: bắt đầu với một consumer.
- Queue cần throughput cao: tăng dần consumer và đo độ trễ, backlog, tải DB và khả năng xử lý song song.
- Topic: thường giữ một consumer cho mỗi subscription/container nếu không có lý do rõ ràng để tạo nhiều subscription nhận cùng publication.

Concurrency ở container không thay thế idempotency. Broker có thể redeliver cùng message sau rollback hoặc lỗi kết nối; nhiều consumer cũng có thể cùng cập nhật dữ liệu liên quan. Cần thiết kế xử lý đồng thời và chống trùng ở tầng nghiệp vụ.

## 6. Acknowledgement và transaction

Đây là phần cần cấu hình cẩn thận nhất. Mặc định SMLC dùng `AUTO_ACKNOWLEDGE`. Với SMLC, acknowledgement diễn ra sau khi listener thực thi. Nếu listener ném exception do người dùng, message không được redeliver theo mặc định; vẫn có khả năng redelivery nếu JVM chết trong lúc listener đang chạy.

Spring không mặc định truyền exception listener lên JMS provider như một callback thất bại. Container ghi log exception và có thể gọi `ErrorHandler` đã cấu hình. Vì vậy không nên kỳ vọng provider tự redeliver chỉ vì method listener ném exception khi đang dùng `AUTO_ACKNOWLEDGE`.

| Chế độ | Hành vi trong SMLC | Nhận xét |
| --- | --- | --- |
| `AUTO_ACKNOWLEDGE` | Acknowledge sau listener execution | Exception nghiệp vụ không bảo đảm redelivery; có thể mất message khi listener lỗi hoặc container dừng ở thời điểm bất lợi |
| `DUPS_OK_ACKNOWLEDGE` | Acknowledge lười ngay sau listener execution | Không bảo đảm redelivery khi listener ném exception; có thể có duplicate trong một số failure window |
| `CLIENT_ACKNOWLEDGE` | Container acknowledge sau khi listener thành công; redelivery khi exception là best effort | Không tạo local transaction cho các thao tác khác trên Session |
| `sessionTransacted=true` | Acknowledge/commit theo local JMS transaction sau listener thành công; rollback khi listener thất bại | Thường là lựa chọn nên dùng khi cần reliability và redelivery nhất quán |

### 6.1. Local JMS transaction với sessionTransacted

Bật transaction cho Session:

~~~java
container.setSessionTransacted(true);
~~~

Mỗi lần listener xử lý message chạy trong một local JMS transaction. Nếu listener hoàn thành bình thường, container commit transaction. Nếu listener ném exception ra ngoài, container rollback; provider có thể giao lại message theo redelivery policy của broker.

Không bắt exception rồi bỏ qua nếu nghiệp vụ chưa hoàn tất. Ví dụ, nếu listener bắt `RuntimeException`, chỉ ghi log rồi return, container thấy callback kết thúc bình thường và có thể commit message. Hãy để lỗi cần rollback truyền ra ngoài, hoặc chủ động đánh dấu transaction rollback-only theo cơ chế phù hợp.

### 6.2. CLIENT_ACKNOWLEDGE

`CLIENT_ACKNOWLEDGE` có thể cung cấp best-effort redelivery khi listener ném exception, nhưng Session không phải transacted Session. Các thao tác JMS khác trên Session, chẳng hạn gửi reply, không được gom vào cùng transaction protocol như `sessionTransacted=true`.

Nếu cần nhận message, thực hiện xử lý và gửi response như một đơn vị JMS nguyên tử, local transacted Session phù hợp hơn.

### 6.3. Database và JMS là hai resource

`sessionTransacted=true` chỉ quản lý transaction của JMS Session. Nếu listener cập nhật database qua JDBC, transaction database là resource khác và không tự commit/rollback cùng JMS.

Ví dụ database commit thành công nhưng JMS commit thất bại có thể khiến message được redeliver; consumer cần idempotency. Ngược lại, nếu message được commit nhưng database rollback do cấu hình transaction không phối hợp, dữ liệu nghiệp vụ có thể không phản ánh kết quả xử lý.

Khi cần phối hợp database và JMS, có thể cân nhắc transactional outbox/inbox hoặc transaction manager JTA/XA với provider hỗ trợ. SMLC không tham gia transaction do bên ngoài quản lý; nếu cần externally managed transaction/XA, xem `DefaultMessageListenerContainer` và cấu hình XA phù hợp.

## 7. TaskExecutor: thay đổi thread và acknowledgement

SMLC có thể nhận một `TaskExecutor` để chạy listener trên thread do ứng dụng quản lý:

~~~java
container.setTaskExecutor(taskExecutor);
~~~

Khi không có executor, provider gọi listener trên thread nhận message và thread đó bị chiếm cho tới khi listener hoàn tất. Khi có executor, provider callback giao công việc cho executor để listener chạy ở thread khác.

Thiết lập này có hệ quả đặc biệt: message được acknowledge trước khi listener thực thi, và Session bên dưới được tái sử dụng ngay để nhận message tiếp theo. Kết hợp `TaskExecutor` với `sessionTransacted=true` hoặc `CLIENT_ACKNOWLEDGE` dẫn tới hành vi không được xác định theo contract của SMLC. Không dùng cấu hình đó khi cần rollback/redelivery dựa trên listener exception.

Executor cũng có thể khiến nhiều message đã nhận trên cùng Session được xử lý đồng thời. Listener kiểu `MessageListener` thông thường thường phù hợp hơn; không nên dùng `SessionAwareMessageListener` để thao tác Session trong các callback đồng thời như vậy.

Nếu dùng executor, hãy đặt giới hạn thread/queue, rejection policy và shutdown behavior. Executor vô hạn có thể tích lũy task khi producer nhanh hơn consumer, gây tăng bộ nhớ và độ trễ.

## 8. Exception, ErrorHandler và phục hồi kết nối

Cần phân biệt hai nhóm lỗi:

- **Lỗi xử lý message:** listener không parse được payload, vi phạm nghiệp vụ hoặc gọi database thất bại. `setErrorHandler(...)` có thể ghi nhận uncaught exception trong quá trình xử lý.
- **Lỗi JMS connection/provider:** provider báo `JMSException` qua `ExceptionListener`. SMLC triển khai `ExceptionListener` và đăng ký chính nó trên shared connection để phát hiện lỗi kết nối.

Mặc định `recoverOnException=true`: khi connection chuyển exception tới listener, SMLC làm mới shared connection và khởi tạo lại các Session/Consumer. Có thể đặt `false` nếu muốn dựa vào automatic recovery của provider và giữ các handle hiện tại; chỉ chọn sau khi kiểm tra cơ chế recovery của provider cụ thể.

Container có thể được cấu hình `ErrorHandler` để ghi log hoặc phát cảnh báo:

~~~java
container.setErrorHandler(error ->
        logger.error("Uncaught exception in JMS listener", error));
~~~

ErrorHandler phục vụ quan sát và xử lý lỗi ở tầng ứng dụng; nó không tự cấu hình retry, redelivery hoặc dead-letter queue. Những chính sách đó thuộc acknowledgement/transaction và broker/provider.

Với message lỗi không thể xử lý (poison message), cần có giới hạn redelivery và dead-letter queue ở broker. Nếu rollback vô hạn, cùng một message có thể quay lại liên tục và chiếm consumer. Khi gửi lại hoặc replay, consumer vẫn cần idempotency.

## 9. SMLC và DefaultMessageListenerContainer khác nhau thế nào?

Spring có hai listener container JMS tiêu chuẩn. Cả hai đều quản lý listener, resource và transaction/acknowledgement, nhưng mô hình nhận khác nhau.

| Tiêu chí | SimpleMessageListenerContainer | DefaultMessageListenerContainer |
| --- | --- | --- |
| Cách nhận | Đăng ký `MessageConsumer.setMessageListener()`; provider gọi callback | Vòng lặp `MessageConsumer.receive()` do Spring điều phối |
| Consumer/session | Số lượng cố định tạo khi khởi động | Có thể cache và điều chỉnh theo cấu hình |
| Dynamic scaling | Không | Có |
| Thread nhận | Thread callback của provider theo mặc định | Task/invoker thread do Spring quản lý |
| Local JMS transaction | Có qua `sessionTransacted=true` | Có |
| External transaction/JTA | Không hỗ trợ | Có thể tham gia khi cấu hình transaction manager và resource phù hợp |
| Mức độ phức tạp | Đơn giản, yêu cầu tối thiểu với provider | Nhiều tính năng và khả năng cấu hình hơn |
| Môi trường Jakarta EE | Nhìn chung không phù hợp với một số JMS restrictions | Thường phù hợp hơn |

Chọn SMLC khi cần mô hình callback provider đơn giản, số consumer cố định và local JMS transaction là đủ. Chọn DMLC khi cần scaling, recovery/polling do Spring điều phối, tham gia transaction bên ngoài hoặc tích hợp môi trường Jakarta EE.

## 10. Ví dụ Java 17 + Spring Framework 6.2

Ví dụ cấu hình SMLC để nhận text message từ queue. Listener đọc nội dung, kiểm tra loại message và để exception truyền ra ngoài để local JMS transaction rollback.

Ví dụ này cần một JMS provider đang hoạt động và một `ConnectionFactory` được cung cấp từ provider/JNDI. Spring không tự tạo broker hoặc queue.

Cấu trúc project:

~~~text
simple-listener-container-demo/
  pom.xml
  src/main/java/com/example/messaging/JmsListenerConfiguration.java
  src/main/java/com/example/messaging/OrderMessageListener.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>simple-listener-container-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.18</spring.version>
        <jakarta.jms.version>3.1.0</jakarta.jms.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jms</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>jakarta.jms</groupId>
            <artifactId>jakarta.jms-api</artifactId>
            <version>${jakarta.jms.version}</version>
            <scope>provided</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`src/main/java/com/example/messaging/JmsListenerConfiguration.java`:

~~~java
package com.example.messaging;

import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.listener.SimpleMessageListenerContainer;

@Configuration
public class JmsListenerConfiguration {

    @Bean
    public SimpleMessageListenerContainer ordersListenerContainer(
            ConnectionFactory connectionFactory,
            OrderMessageListener listener) {
        SimpleMessageListenerContainer container =
                new SimpleMessageListenerContainer();
        container.setConnectionFactory(connectionFactory);
        container.setDestinationName("orders.queue");
        container.setMessageListener(listener);
        container.setConcurrentConsumers(2);
        container.setSessionTransacted(true);
        container.setRecoverOnException(true);
        return container;
    }
}
~~~

`src/main/java/com/example/messaging/OrderMessageListener.java`:

~~~java
package com.example.messaging;

import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.MessageListener;
import jakarta.jms.TextMessage;

import org.springframework.stereotype.Component;

@Component
public class OrderMessageListener implements MessageListener {

    @Override
    public void onMessage(Message message) {
        try {
            if (!(message instanceof TextMessage textMessage)) {
                throw new IllegalArgumentException(
                        "Expected TextMessage but received "
                                + message.getClass().getName());
            }

            String body = textMessage.getText();
            if (body == null || body.isBlank()) {
                throw new IllegalArgumentException("Order message body is empty");
            }

            System.out.println("received=" + body);
            processOrder(body);
        } catch (JMSException ex) {
            throw new IllegalStateException("Cannot read JMS message", ex);
        }
    }

    private void processOrder(String body) {
        // Thực hiện nghiệp vụ; ném RuntimeException nếu cần rollback JMS.
    }
}
~~~

Spring tự quản lý lifecycle của bean container. Ứng dụng cần đăng ký `ConnectionFactory` phù hợp và đảm bảo queue `orders.queue` tồn tại hoặc provider cho phép tạo queue theo tên.

Khi provider giao message text, listener ghi một dòng dạng `received=OrderPlaced: ORD-2048`. Thời điểm và số dòng phụ thuộc message thực tế, concurrency và broker; ví dụ không đưa ra stdout cố định vì không kèm broker cụ thể.

Trong cấu hình này, hai consumer có thể xử lý song song. Nếu `processOrder` ném `RuntimeException`, `sessionTransacted=true` cho phép container rollback JMS transaction để broker redeliver theo redelivery policy. Hãy cấu hình DLQ/giới hạn redelivery ở provider và làm `processOrder` idempotent.

## 11. Kiểm thử và quan sát

Kiểm thử SMLC cần xác nhận cả callback model và failure semantics:

1. Khi container start, provider có đúng số consumer được cấu hình không?
2. Message đến queue có kích hoạt `MessageListener.onMessage` mà không cần gọi `receive()` không?
3. Với một consumer, callback có chạy trên provider receive thread theo cấu hình mặc định không?
4. Với nhiều consumer, queue có xử lý song song và có thay đổi thứ tự hoàn tất không?
5. Với `sessionTransacted=true`, listener thành công có commit và listener ném exception có rollback không?
6. Với `AUTO_ACKNOWLEDGE`, có xác nhận đúng giới hạn redelivery của SMLC không?
7. Khi broker ngắt kết nối, `ExceptionListener` và `recoverOnException` có khởi tạo lại consumer không?
8. Khi stop context, consumer và Session có được đóng không?
9. Nếu dùng `TaskExecutor`, có xác nhận acknowledgement xảy ra trước listener và không dùng transacted/client ack không?
10. Poison message có bị retry vô hạn hay được chuyển DLQ theo chính sách broker?

Quan sát production nên gồm số consumer đang hoạt động, tốc độ nhận/xử lý, thời gian listener, exception count, redelivery count, DLQ depth, connection recovery, backlog và tuổi message cũ nhất. Không log toàn bộ payload nếu chứa dữ liệu nhạy cảm.

## 12. Lỗi thường gặp

- **Cho rằng SMLC tự polling bằng `receive()`:** SMLC đăng ký `MessageListener` qua `setMessageListener`; provider gọi callback.
- **Mong số consumer tự tăng giảm:** SMLC tạo số consumer cố định; `setConcurrency("2-8")` không tạo cơ chế scale động.
- **Tăng consumer trên topic mà không hiểu subscription:** mỗi consumer có thể nhận cùng publication.
- **Dùng AUTO_ACKNOWLEDGE cho xử lý cần redelivery:** listener exception không bảo đảm message quay lại.
- **Bắt và nuốt exception khi dùng transacted Session:** callback return bình thường có thể khiến transaction commit.
- **Kỳ vọng database tự rollback cùng JMS:** local JMS transaction không tự enlist JDBC transaction.
- **Dùng TaskExecutor cùng sessionTransacted hoặc CLIENT_ACKNOWLEDGE:** acknowledgement/session semantics không được xác định.
- **Chia sẻ Session cho nhiều thread:** JMS Session không thread-safe; mỗi consumer nên làm việc trên Session của nó.
- **Cho rằng ErrorHandler tự retry:** ErrorHandler chỉ xử lý uncaught exception ở ứng dụng; retry/DLQ do transaction và provider policy quyết định.
- **Dùng SMLC khi cần JTA/XA:** SMLC không tham gia external transaction; cân nhắc DMLC.
- **Không cấu hình recovery hoặc DLQ:** connection failure và poison message có thể làm listener ngừng hoạt động hoặc lặp vô hạn.
- **Đóng ConnectionFactory/Session trong listener:** container sở hữu lifecycle của các resource mà nó tạo và quản lý.

## 13. Checklist chọn và cấu hình SMLC

1. JMS provider có hỗ trợ callback `MessageConsumer.setMessageListener` trong môi trường triển khai không?
2. Ứng dụng có cần fixed consumer count hay cần dynamic scaling?
3. Destination là queue hay topic? Số consumer có phù hợp semantics subscription không?
4. Listener chạy trên provider thread hay cần executor? Đã hiểu acknowledgement caveat chưa?
5. Có cần redelivery khi listener lỗi không? Nếu có, đã bật `sessionTransacted=true` hoặc chọn acknowledgement mode phù hợp chưa?
6. Listener có để exception cần rollback truyền ra ngoài không?
7. Database và JMS có cần outbox/inbox hoặc JTA/XA không?
8. `recoverOnException` có phù hợp với automatic recovery của provider không?
9. Có ErrorHandler, retry policy và DLQ rõ ràng không?
10. Shutdown có đóng consumer/session và dừng nhận message đúng cách không?
11. Có theo dõi consumer count, processing latency, redelivery và DLQ không?
12. Consumer có idempotent để xử lý duplicate sau crash/retry không?

## 14. Ghi nhớ

`SimpleMessageListenerContainer` tạo số lượng cố định các JMS Session và MessageConsumer, đăng ký listener bằng `MessageConsumer.setMessageListener()` rồi để JMS provider gọi callback. Mặc định callback chạy trên provider receive thread; `TaskExecutor` có thể tách thread nhưng làm thay đổi acknowledgement và không phù hợp với transacted/client-ack Session theo contract của SMLC. SMLC hỗ trợ local JMS transaction qua `sessionTransacted=true`, nhưng không hỗ trợ external transaction/JTA hoặc dynamic scaling. `AUTO_ACKNOWLEDGE` không bảo đảm redelivery khi listener ném exception; với yêu cầu reliability, ưu tiên transacted Session, cấu hình redelivery/DLQ ở broker và làm consumer idempotent. Chọn `DefaultMessageListenerContainer` khi cần polling do Spring quản lý, dynamic scaling hoặc tham gia transaction bên ngoài.

### Tài liệu tham khảo

- [Spring Framework 6.2 — Using Spring JMS](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html)
- [Spring Framework 6.2 — Receiving a Message](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html)
- [Spring Framework 6.2.x — SimpleMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/SimpleMessageListenerContainer.html)
- [Spring Framework 6.2.x — AbstractMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/AbstractMessageListenerContainer.html)
- [Spring Framework 6.2.x — DefaultMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html)