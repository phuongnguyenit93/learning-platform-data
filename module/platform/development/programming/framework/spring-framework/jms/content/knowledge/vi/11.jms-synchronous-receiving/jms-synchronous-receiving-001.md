# receive và luồng chờ message trong Spring JMS

**Chủ đề:** Nhận đồng bộ (Spring Framework – JMS). Bài học tập trung vào `receive`, cơ chế chặn luồng trong khi chờ message, timeout, kết quả `null`, quản lý connection/session, transaction, các giới hạn khi polling và cách chọn `@JmsListener`. Ví dụ dùng Java 17+, Spring Framework 6.x / Spring Boot 3.x, Jakarta Messaging và broker Apache ActiveMQ Artemis.

**Ý chính:** `JmsTemplate.receive(...)` **không đăng ký một callback để Spring gọi về sau**. Nó làm **luồng đang gọi phương thức** chờ cho đến khi có message, timeout hoặc lỗi/điều kiện đóng tài nguyên. Nếu gọi từ HTTP request thread với timeout vô hạn, request thread đó có thể bị giữ rất lâu. Ngược lại, với `@JmsListener`, Spring vận hành listener container và thread nhận message riêng.

## 1. Nhận đồng bộ nghĩa là gì?

~~~text
                         [JMS broker]
                              │
                              │ message available?
                              ▼
[Java worker thread] ── receive("jobs.queue") ──► [CHỜ MESSAGE]
                              │                         │
                              │     message / timeout    │
                              ◄─────────────────────────┘
                              │
                              ▼
                    Code sau receive() chạy tiếp

Thời gian chờ: luồng đang gọi receive() không thực thi code phía sau.
Các luồng khác: có thể tiếp tục chạy nếu còn thread và tài nguyên.
~~~

Nhận đồng bộ không đồng nghĩa JMS bị giới hạn chỉ có một consumer, cũng không có nghĩa JVM liên tục dùng CPU để dò broker. Provider thường chờ bằng network I/O hoặc primitive đồng bộ, nhưng **thread, session và consumer** gắn với lời gọi vẫn cần tài nguyên. `Thread.State.BLOCKED` trong Java còn có nghĩa hẹp là chờ monitor lock; một blocking receive có thể hiện `WAITING`, `TIMED_WAITING` hoặc `RUNNABLE` tùy đường triển khai. Vì vậy thread dump phải được đọc theo **call stack**, không chỉ theo tên trạng thái.

**Đối chiếu hai kiểu nhận:**

| Tiêu chí | `receive` | `@JmsListener` |
| --- | --- | --- |
| Ai bắt đầu nhận? | Code gọi hàm tại một thời điểm cụ thể | Listener container của Spring |
| Thread nào chờ? | Thread gọi `receive` | Worker thread do container quản lý |
| Giá trị trả về | `Message`/Object hoặc `null` | Phương thức callback xử lý message khi được giao |
| Không có message | Có thể chờ tới timeout hoặc vô hạn | Container tiếp tục vận hành theo cấu hình polling/recovery |
| Quản lý tài nguyên | `JmsTemplate` giúp mở/đóng theo một lời gọi; app tự quản vòng nhận | Container quản lý consumer lifecycle, concurrency, restart |
| Use case phù hợp | Lấy một message theo yêu cầu, công cụ quản trị, bounded poll | Worker tiêu thụ message liên tục |

Sự khác biệt này nói về **quyền điều khiển thời điểm nhận**, không nói “listener không sử dụng threads”. Callback `@JmsListener` vẫn chạy trên thread và có thể bị chặn nếu xử lý DB/HTTP chậm.

## 2. Ba cách receive trong JMS classic API

`jakarta.jms.MessageConsumer` cung cấp:

| API | Chờ bao lâu? | Trả về |
| --- | --- | --- |
| `receive()` | Không thời hạn; kết thúc khi có message, bị đóng đồng thời hoặc lỗi | `Message`, có thể `null` khi consumer đóng |
| `receive(long timeout)` | `timeout > 0`: chờ tối đa khoảng số mili-giây đã chọn; `timeout == 0`: chờ không thời hạn | `Message` hoặc `null` nếu timeout/consumer đóng |
| `receiveNoWait()` | Lấy ngay nếu message sẵn có, không đợi message tương lai | `Message` hoặc `null` |

~~~java
Message message1 = consumer.receive();        // Chờ đến khi có message
Message message2 = consumer.receive(2_000L);  // Tối đa khoảng 2 giây
Message message3 = consumer.receiveNoWait();  // Không chờ message mới
~~~

Đoạn trên là snippet cần một `MessageConsumer consumer` hợp lệ. Mỗi lời gọi có thể **tiêu thụ một message thật**. Đây không phải thao tác “peek” để xem mà không làm thay đổi trạng thái delivery. Muốn quan sát message trong queue mà không lấy đi để xử lý, cân nhắc `QueueBrowser` hoặc broker management metrics, không dùng receive rồi hy vọng message vẫn nằm đó.

**Bẫy phổ biến:** `receive(0)` **không** có nghĩa “trả ngay”. Trong JMS, `0` có nghĩa **chờ vô thời hạn**. Muốn không chờ, gọi `receiveNoWait()`.

## 3. Classic JMS cần Connection.start() để nhận

Trước khi classic `MessageConsumer` bắt đầu delivery, phải gọi `Connection.start()`. Không gọi nó thì `receive(timeout)` có thể hết hạn chờ dù broker đang giữ message; `receive()` có thể chờ vô hạn.

~~~java
import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.MessageConsumer;
import jakarta.jms.Queue;
import jakarta.jms.Session;

public final class OneShotReceiver {

    private final ConnectionFactory connectionFactory;

    public OneShotReceiver(ConnectionFactory connectionFactory) {
        this.connectionFactory = connectionFactory;
    }

    public Message receiveOnce() throws JMSException {
        try (Connection connection = connectionFactory.createConnection();
             Session session = connection.createSession(
                     false, Session.AUTO_ACKNOWLEDGE)) {

            Queue queue = session.createQueue("demo.sync.receive");

            try (MessageConsumer consumer = session.createConsumer(queue)) {
                connection.start(); // Bắt đầu JMS delivery
                return consumer.receive(3_000L);
            }
        }
    }
}
~~~

Class trên có thể biên dịch trong dự án Java 17 đã thêm JMS API và provider client tương thích; nó **không có `main`**. Để chạy phải có bean/instance `ConnectionFactory` trỏ đến broker, queue hợp lệ và quyền nhận. Tạo/đóng physical connection trên từng lần nhận chỉ phù hợp ví dụ đơn giản; hệ thống có tải nên dùng cache/pool và cơ chế quản lý lifecycle hợp lý.

`Connection.stop()` tạm dừng delivery, không cấm producer gửi message và **không dừng đồng hồ của receive timeout**: nhận đang chờ có thể hết hạn và trả `null` khi connection stopped. Với **simplified JMS API** (`JMSContext`/`JMSConsumer`), context mặc định auto-start khi tạo consumer trừ khi bạn gọi `setAutoStart(false)`; không áp dụng điều đó cho classic `Connection`.

**Spring giúp ở đâu?** `JmsTemplate.receive` quản lý connection/session/consumer và việc bắt đầu delivery phù hợp. Bạn không cần tự lấy connection để gọi `start()` trong code nhận bằng template.

## 4. Spring JmsTemplate.receive và receiveAndConvert

`org.springframework.jms.core.JmsTemplate` có thể nhận JMS Message hoặc chuyển đổi body:

~~~java
// jmsTemplate là Spring bean đã cấu hình ConnectionFactory.
jakarta.jms.Message raw =
        jmsTemplate.receive("orders.queue");

Object payload =
        jmsTemplate.receiveAndConvert("orders.queue");
~~~

Khác biệt:

- `receive` trả về **`jakarta.jms.Message`** để bạn đọc body, JMS header, message properties, redelivery metadata.
- `receiveAndConvert` gọi `MessageConverter.fromMessage` để chuyển JMS Message sang Java object. Với `SimpleMessageConverter` mặc định, `TextMessage` thường thành `String`, `BytesMessage` thành `byte[]`, `MapMessage` thành `Map`.
- Cả hai **đều chặn thread**; `convert` chỉ là bước chuyển đổi sau receive, không có nghĩa nhận bất đồng bộ.
- Cả hai có thể trả `null` khi không có message trong thời hạn chờ. Lỗi từ provider/converter sẽ là exception, không phải null.

Một số overload quan trọng:

| API | Ý nghĩa |
| --- | --- |
| `receive()` | Nhận từ **default destination** được cấu hình trên template |
| `receive(String destinationName)` | Nhận trực tiếp từ tên destination |
| `receive(Destination destination)` | Nhận từ JMS Destination object |
| `receiveAndConvert()` | Nhận rồi đổi sang Java object, từ default destination |
| `receiveAndConvert(String destinationName)` | Nhận rồi đổi sang Java object |
| `receiveSelected(String destinationName, String selector)` | Nhận message thỏa selector JMS |
| `receiveSelectedAndConvert(String destinationName, String selector)` | Nhận có selector rồi convert |

Nếu gọi overload không có destination mà chưa cấu hình `setDefaultDestinationName` hoặc `setDefaultDestination`, template có thể ném lỗi vì không biết nhận từ đâu. Chuỗi tên được `DestinationResolver` xử lý; mặc định là queue, trừ khi cấu hình `pubSubDomain=true` hoặc resolver phù hợp cho topic.

**Cẩn thận với ví dụ đọc liên tiếp:**

~~~java
Message first = jmsTemplate.receive("orders.queue");
Object second = jmsTemplate.receiveAndConvert("orders.queue");
~~~

Hai lệnh có thể lấy **hai message khác nhau** từ cùng queue. Chúng không phải hai cách lấy metadata và body của *cùng* message. Nếu cần cả header và body của một message, nhận raw Message **một lần**, rồi xử lý object đó trong cùng scope.

## 5. receiveTimeout trong JmsTemplate: 0, số dương, -1

Spring đặt timeout trên template, đơn vị **mili-giây**:

~~~java
JmsTemplate receiver = new JmsTemplate(connectionFactory);

// Đợi tối đa khoảng 2 giây.
receiver.setReceiveTimeout(2_000L);

// Không chờ message mới.
receiver.setReceiveTimeout(-1L);

// Chờ vô thời hạn.
receiver.setReceiveTimeout(0L);
~~~

| Giá trị trên `JmsTemplate` | Cách nhận |
| --- | --- |
| `0L` | **Vô thời hạn** — tương ứng `RECEIVE_TIMEOUT_INDEFINITE_WAIT`, là mặc định |
| `>0L` | Chờ tới khi message đến hoặc timeout |
| `-1L` | **No wait** — tương ứng `RECEIVE_TIMEOUT_NO_WAIT` |
| Số âm khác | Spring cũng coi là no-wait; nên dùng hằng số để rõ ý |

Hai hằng của `org.springframework.jms.support.destination.JmsDestinationAccessor`:

~~~java
JmsDestinationAccessor.RECEIVE_TIMEOUT_INDEFINITE_WAIT // 0L
JmsDestinationAccessor.RECEIVE_TIMEOUT_NO_WAIT          // -1L
~~~

**Quan trọng:** `setReceiveTimeout(0)` **không phải** giới hạn 0 mili-giây; đó là **indefinite wait**. Với classic JMS cũng vậy: `consumer.receive(0)` chờ vô thời hạn. Để kiểm tra ngay, Spring dùng `-1` còn classic JMS dùng `receiveNoWait()`.

Timeout của template là **thuộc tính dùng chung** cho các lần receive trên instance đó. Không chỉnh `setReceiveTimeout` liên tục trên singleton `JmsTemplate` đang được nhiều thread sử dụng, vì việc đổi cấu hình có thể ảnh hưởng lời gọi khác. Khi cần chính sách khác nhau, tạo **các bean/template riêng** hoặc chọn API có timeout rõ ràng trong scope có kiểm soát.

Ở Spring Boot 3.x, property `spring.jms.template.receive-timeout` có thể cấu hình template do Boot auto-configure, ví dụ:

~~~yaml
spring:
  jms:
    template:
      receive-timeout: 3s
~~~

**Không nhầm** `spring.jms.template.receive-timeout` với `spring.jms.listener.receive-timeout`. Thuộc tính listener dành cho container nhận message, có ý nghĩa và lifecycle khác. Nếu bạn tự tạo một `JmsTemplate` mới bằng `new`, property của bean template do Boot tự cấu hình **không tự động** áp dụng cho instance tự tạo ấy.

## 6. Timeout trả null, nhưng null không chứng minh queue rỗng

~~~java
JmsTemplate receiver = new JmsTemplate(connectionFactory);
receiver.setReceiveTimeout(1_000L);

Message message = receiver.receive("jobs.queue");
if (message == null) {
    System.out.println("No message in this receive attempt");
} else {
    System.out.println("Received JMSMessageID="
            + message.getJMSMessageID());
}
~~~

Đoạn code là snippet trong một method Spring có `ConnectionFactory` đã cấu hình. Khi receive không bắt được message trong khoảng timeout, `null` là **kết quả bình thường**, không phải `JmsException`.

`null` có thể xuất hiện vì:
- Queue chưa có message ở thời điểm thử nhưng producer sắp gửi ngay sau đó.
- Consumer khác đã lấy message trước.
- Message đang in-flight hoặc nằm trong session transaction của consumer khác.
- Selector không khớp (nếu dùng `receiveSelected`).
- Destination sai, broker routing khác hoặc topic subscription chưa tồn tại.
- Delivery delay, TTL/expiry hoặc policy broker ảnh hưởng thời điểm giao.
- Classic connection bị stopped, hoặc receiver không được delivery theo trạng thái phù hợp.

Do đó, câu “`receive` trả null” chỉ có nghĩa **“không nhận được message trong lần thử này”**. Không phải “queue trên toàn hệ thống chắc chắn rỗng” và cũng không phải “mọi nghiệp vụ đã hoàn tất”.

### Timeout của JMS receive không phải timeout cho cả thao tác từ đầu tới cuối

`setReceiveTimeout(3_000)` giới hạn thời gian **chờ message** ở bước nhận. Nó không nhất thiết bao trùm DNS, TCP connect, TLS, authentication, tạo session/consumer, recovery hoặc lỗi I/O. Một hệ thống có deadline HTTP 5 giây cần budget riêng cho connection setup và kết quả đầu cuối, không chỉ một `receiveTimeout=5s`.

## 7. Khi thread đang chờ, thread khác vẫn tiếp tục chạy

~~~text
Thread A - Worker                    Thread B - Producer
    |
    +-- receive("orders.queue")
    |        ... waiting ...
    |                                  +-- send(OrderCreated)
    |                                  +-- send returns
    |
    +-- receive returns Message
    +-- parse message
    +-- update business data
    +-- next statement
~~~

Thread A đứng lại tại `receive`, không đi tới `parse` và `update` khi vẫn chưa có kết quả. Thread B và các thread khác vẫn có thể gửi message hoặc làm việc độc lập.

Đừng đồng nhất “blocking” với “busy-wait”: implementation JMS có thể không dùng CPU đáng kể khi chờ, nhưng **số thread, session, consumer và connection đang sử dụng** vẫn quan trọng. Nếu 200 HTTP requests đồng thời đều gọi receive và chờ 10 giây, có thể có tới 200 request paths đang giữ threads/resources tương ứng. Khi vượt giới hạn thread pool hoặc broker capacity, requests mới có thể bị xếp hàng dù CPU còn thấp.

Nếu queue đã có message, `receive` có thể trả **gần như ngay lập tức**. Đây vẫn là API blocking vì **nó có khả năng chờ** khi không có message.

## 8. Ví dụ Spring Boot 3.x chạy được: một thread chờ, thread khác gửi

Ví dụ Java 17 này minh họa **thread đang chờ** một message trên queue test, thread chính gửi message sau đó, rồi lấy kết quả. Nó dùng **Spring Boot 3.5.0** để chỉ định một phiên bản phát hành cụ thể, không mặc định là mới nhất. Cần broker Artemis chạy ngoài app tại `tcp://localhost:61616`, user có quyền gửi/nhận và queue `demo.sync.receive` tồn tại hoặc được phép auto-create.

### 8.1. Gradle dependencies

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '1.0.0'

repositories { mavenCentral() }

java {
    toolchain { languageVersion = JavaLanguageVersion.of(17) }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
}
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'spring-sync-receive'
~~~

`src/main/resources/application.yaml`:

~~~yaml
spring:
  artemis:
    mode: native
    broker-url: tcp://localhost:61616
    user: demo
  jms:
    pub-sub-domain: false
~~~

Mật khẩu nên được cung cấp qua environment `SPRING_ARTEMIS_PASSWORD` hoặc secret manager, không đưa vào Git. Nếu broker đang dùng thông tin xác thực hoặc TCP/TLS endpoint khác, đổi cấu hình cho phù hợp. Dependency client không tự khởi động một external broker.

### 8.2. Một Java file đầy đủ

`src/main/java/example/jmssync/SyncReceiveApplication.java`:

~~~java
package example.jmssync;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class SyncReceiveApplication {

    public static void main(String[] args) {
        SpringApplication.run(SyncReceiveApplication.class, args);
    }

    @Bean
    ApplicationRunner demonstrate(
            ConnectionFactory connectionFactory,
            JmsTemplate sender) {

        return args -> {
            JmsTemplate receiver = new JmsTemplate(connectionFactory);
            receiver.setReceiveTimeout(3_000L);

            CountDownLatch ready = new CountDownLatch(1);
            ExecutorService executor = Executors.newSingleThreadExecutor();

            try {
                Future<String> result = executor.submit(() -> {
                    System.out.println("WAIT_START");
                    ready.countDown();

                    Message message =
                            receiver.receive("demo.sync.receive");

                    if (message == null) {
                        return "RECEIVE_TIMEOUT";
                    }
                    if (message instanceof TextMessage text) {
                        return "RECEIVED:" + text.getText();
                    }
                    return "RECEIVED_OTHER_MESSAGE_TYPE";
                });

                if (!ready.await(2L, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "Receiver worker did not start");
                }

                Thread.sleep(300L); // Chỉ phục vụ demo.
                sender.convertAndSend("demo.sync.receive", "hello");
                System.out.println("SEND_RETURNED");

                System.out.println(result.get(6L, TimeUnit.SECONDS));
            } finally {
                executor.shutdownNow();
            }
        };
    }
}
~~~

### 8.3. Lệnh chạy và output

Nếu dự án có Gradle wrapper và broker sẵn sàng:

~~~bash
./gradlew bootRun
~~~

Các dòng nghiệp vụ có thể quan sát khi queue test ban đầu trống và không có consumer cạnh tranh:

~~~text
WAIT_START
SEND_RETURNED
RECEIVED:hello
~~~

**Output trên chỉ là tình huống dự kiến**, không phải stdout đầy đủ cố định. Có log Spring/provider khác; nếu queue đã chứa message, worker có thể lấy message cũ; nếu broker unreachable/auth sai có thể ném exception; nếu message không được giao trong 3 giây, có thể trả `RECEIVE_TIMEOUT`. Thread worker có thể **nhận message trước** khi producer in `SEND_RETURNED` nhưng `Future.get` trong runner khiến dòng `RECEIVED:...` được **in sau** dòng `SEND_RETURNED` trong ví dụ.

`CountDownLatch` ở đây chỉ xác nhận worker đã chuẩn bị gọi receive, **không chứng minh** lời gọi đã bắt đầu chờ bên broker; `Thread.sleep(300)` chỉ tăng khả năng quan sát. Để kiểm thử chính xác trạng thái chờ, dùng broker test, timestamps, tracing hoặc công cụ điều khiển mạng phù hợp.

**Lưu ý lifecycle:** `executor.shutdownNow()` gửi interrupt, không phải bảo đảm JMS client đang blocked sẽ dừng ngay trên mọi provider. Chính `receiver.setReceiveTimeout(3_000L)` giúp giữ thời gian receive hữu hạn. Ví dụ chỉ dành cho học tập, không dùng raw executor trong `ApplicationRunner` để triển khai worker production.

## 9. receiveAndConvert và MessageConverter

~~~java
JmsTemplate receiver = new JmsTemplate(connectionFactory);
receiver.setReceiveTimeout(2_000L);

Object payload = receiver.receiveAndConvert("orders.queue");
if (payload == null) {
    System.out.println("Receive timed out or returned no payload");
} else if (payload instanceof String text) {
    System.out.println("Text payload: " + text);
} else {
    System.out.println("Type: " + payload.getClass().getName());
}
~~~

`SimpleMessageConverter` mặc định chuyển một `TextMessage` thành `String`, `BytesMessage` thành byte array, `MapMessage` thành `Map`. Nếu app có custom JSON converter, kết quả có thể là POJO và yêu cầu schema/type metadata tương thích. Conversion errors có thể ném `MessageConversionException`; không dùng `receiveAndConvert` để giả định luôn có String.

Nếu cần `JMSMessageID`, `JMSTimestamp`, `JMSRedelivered`, `JMSXDeliveryCount` hoặc custom property cho tracing/idempotency, thường nên nhận bằng `receive` và đọc các metadata từ raw `jakarta.jms.Message`. `receiveAndConvert` tập trung vào payload và không tự cung cấp header ở giá trị Java trả về.

## 10. Polling: không dùng no-wait trong một vòng lặp nóng

Vòng lặp như sau rất dễ sai:

~~~java
while (running.get()) {
    Message message = noWaitTemplate.receive("jobs.queue");
    if (message != null) {
        process(message);
    }
}
~~~

Đây là snippet, giả định `running` là cờ trạng thái và `process` do app viết. Nếu template ở chế độ `setReceiveTimeout(-1)` và queue rỗng, vòng lặp thực hiện receive không ngừng, có thể tiêu tốn CPU, connection/session churn và tải broker.

Một cách **ít gây polling churn hơn**:

~~~java
JmsTemplate receiver = new JmsTemplate(connectionFactory);
receiver.setReceiveTimeout(1_000L);

while (running.get()) {
    Message message = receiver.receive("jobs.queue");
    if (message == null) {
        continue; // Hết cửa sổ chờ, kiểm tra cờ dừng.
    }
    process(message);
}
~~~

Đây cũng chỉ là **minh họa**: chưa có retry, shutdown, error handling, transactional ACK, thread ownership hay idempotency. Về mặt quản trị, một listener container giữ consumers lâu dài và tự quản lý recovery/concurrency thường tốt hơn tự lặp `JmsTemplate.receive`.

**Không thay bằng Thread.sleep:**

~~~java
Thread.sleep(5_000L);
Message message = noWaitTemplate.receive("jobs.queue");
~~~

`sleep` chờ **thời gian**, không phải chờ **message đến**. Nếu message đến sau 10 ms, bạn vẫn ngủ gần 5 giây. `receive(5_000)` có thể trả **sớm ngay khi message đến**, giúp long polling phản hồi nhanh hơn. `sleep/backoff` chỉ có ích để chủ động giảm tải trong polling cần thiết, không thay vai trò của receive.

## 11. HTTP request chờ JMS: phải có deadline rõ

~~~java
// Snippet minh họa; thiếu imports, controller và convertToResponse.
@GetMapping("/jobs/next")
public ResponseEntity<String> nextJob() {
    Message message = jmsTemplate.receive("jobs.queue");
    return convertToResponse(message);
}
~~~

Nếu `JmsTemplate` có receiveTimeout mặc định `0` và không có message, **HTTP request thread có thể chờ vô hạn**. Rủi ro có thể là servlet thread pool bị đầy, gateway timeout trong khi server vẫn chờ, người dùng retry và lấy message cạnh tranh, connection/session bị chiếm giữ.

Với HTTP long polling cần:
1. Đặt `receiveTimeout` **dương** và phù hợp ngân sách request SLA, trừ thời gian dành cho connection setup, serialization, DB và network.
2. Giới hạn số request/consumers chờ đồng thời, quản lý executor có backpressure; không tạo raw thread không giới hạn.
3. Xử lý `null` thành trạng thái “không có job trong khoảng chờ” theo hợp đồng API, không thành một lỗi broker giả.
4. Khi client hủy request, không giả định interrupt sẽ làm JMS receive dừng tức thì.
5. Xác định ACK/transaction của việc giao job; nếu đã nhận nhưng HTTP reply mất, job có thể bị lấy khỏi queue trong khi client không biết.
6. Dùng idempotency/visibility contract thích hợp nếu queue được dùng như hệ thống phân phối tác vụ.

**Khuyến nghị:** Nếu HTTP request chỉ yêu cầu tạo việc nền, trả `202 Accepted` cùng operation ID sau khi ghi nhận yêu cầu bền vững; dùng `@JmsListener` cho worker và outcome store cho việc tra cứu kết quả. Đừng giữ một request thread chờ message chỉ để giả lập xử lý “đồng bộ”.

## 12. Executor, Future và interrupt: chuyển thread chứ không biến thành non-blocking

~~~text
Caller thread                           Executor worker
    │                                         │
    ├─ executor.submit(() -> receive()) ────► │ receive() blocks
    │                                         │
    ├─ làm việc khác                          │ ...waiting...
    │                                         │
    └─ future.get() ─────────────────────────►│ result after receive()
~~~

Đẩy receive vào `ExecutorService` giúp caller thread có thể làm việc khác **nếu không đợi Future ngay**. Nhưng một executor worker vẫn chờ. Nếu executor có 10 threads và cả 10 đều bị giữ trong receive, task thứ 11 có thể phải nằm trong queue. Không xem cách này là API JMS non-blocking.

`Future.get(2, TimeUnit.SECONDS)` giới hạn **thời gian caller chờ Future**, không trực tiếp giới hạn JMS receive. `Future.cancel(true)` yêu cầu interrupt, nhưng JMS provider hoặc network stack có thể chưa phản ứng ngay, nên cần timeout hữu hạn ở chính receive và cơ chế shutdown có kiểm chứng.

**Quan sát thread pool:** đo số receive đang chờ, p95/p99 latency, executor queue length, connection/session count, broker consumer count, success/timeout/error rate. CPU thấp không có nghĩa hệ thống không bị nghẽn nếu nhiều threads đang đợi.

## 13. Selector: chờ message phù hợp chứ không chỉ message bất kỳ

~~~java
JmsTemplate receiver = new JmsTemplate(connectionFactory);
receiver.setReceiveTimeout(1_000L);

Message message = receiver.receiveSelected(
        "orders.queue",
        "eventType = 'OrderCreated' AND priorityLevel >= 2"
);
~~~

Các field `eventType` và `priorityLevel` phải là JMS **properties** được producer đặt đúng kiểu. Selector kiểm tra header/property theo ngôn ngữ selector JMS, **không tự parse JSON body**. Nếu không có message thỏa điều kiện trong thời gian chờ, `receiveSelected` có thể trả null dù broker còn nhiều message khác.

JMS message selectors cũng không phải công cụ scan lịch sử queue không tiêu thụ. Consumer tạo bởi receive vẫn có semantics nhận/ACK. Với property `JMSXDeliveryCount` do provider gán lúc delivery, JMS không bảo đảm selector hoạt động theo cách bạn tưởng; tránh dùng nó để thay business retry policy.

### Queue và Topic khác nhau

Trong queue, các consumers có thể **cạnh tranh** nhận một message ở mỗi lần delivery. Không kết luận queue rỗng từ việc một consumer cụ thể nhận null.

Trong topic, non-durable subscription chỉ nhận được các message khi subscription đang hoạt động; một `JmsTemplate.receive` tạo consumer ngắn hạn không tự biến thành durable subscriber lưu lịch sử. Muốn durable subscription, phải cấu hình identity/lifecycle đúng. Chỉ dùng tên đuôi `.topic` không làm một destination tự thành topic nếu `pubSubDomain` của template vẫn là queue.

## 14. ACK và transaction: nhận thành công khác xử lý nghiệp vụ thành công

Đây là rủi ro quan trọng nếu dùng receive để lấy công việc:

~~~java
Message message = jmsTemplate.receive("billing.commands");
if (message != null) {
    writeInvoiceToDatabase(message);
}
~~~

`writeInvoiceToDatabase` là hàm nghiệp vụ giả định, không phải phần Spring cung cấp. Với mặc định `JmsTemplate` **không transacted**, `AUTO_ACKNOWLEDGE`, JMS receive có thể được ACK khi `receive` trả về. Nếu DB insert thất bại **sau đó**, JMS broker có thể đã ghi nhận message được tiêu thụ và **không tự phát lại**.

**Bật sessionTransacted có đủ không?** Chưa chắc. Nếu một `JmsTemplate` có `setSessionTransacted(true)` mà không có **transaction scope bao quanh business logic**, template có thể commit local JMS receive trong chính thao tác receive/cleanup trước khi code DB phía sau chạy. Cần thiết kế **ranh giới transaction**.

### Một local JMS transaction có chủ đích

~~~java
@Bean
JmsTransactionManager jmsTransactionManager(ConnectionFactory cf) {
    return new JmsTransactionManager(cf);
}
~~~

Sau đó:

~~~java
@Service
class InvoicePoller {
    private final JmsTemplate jms;
    private final InvoiceService invoices;

    InvoicePoller(JmsTemplate jms, InvoiceService invoices) {
        this.jms = jms;
        this.invoices = invoices;
    }

    @Transactional(transactionManager = "jmsTransactionManager")
    public void receiveAndProcessOnce() {
        Message msg = jms.receive("billing.commands");
        if (msg == null) {
            return;
        }
        invoices.process(msg);
    }
}
~~~

Hai khối trên là **snippets Spring**: cần imports, các class bao ngoài, bean `InvoiceService`, cùng `ConnectionFactory` cho manager và template. Gọi method phải đi qua **Spring proxy**, không phải self-invocation trong cùng class; nếu không, `@Transactional` có thể không có hiệu lực. Với local JMS transaction, exception phù hợp trong handler dẫn tới rollback receive để broker có cơ hội redeliver.

**Giới hạn quan trọng:** `JmsTransactionManager` quản lý **JMS resource**, không tự gộp PostgreSQL/MySQL/HTTP trong cùng transaction. Nếu DB đã commit nhưng JMS commit/ACK bị mất do crash, message có thể đến lần nữa. Cần **idempotent consumer** với stable business `eventId`, unique constraint/transaction DB hoặc idempotency từ hệ thống ngoài. Không suy ra exactly-once business effect chỉ từ `sessionTransacted=true`.

### CLIENT_ACKNOWLEDGE không chỉ ack một object tùy ý

Trong classic JMS `CLIENT_ACKNOWLEDGE`, `message.acknowledge()` có thể xác nhận các messages đã tiêu thụ trên cả **Session**, không chỉ một message riêng. Không dùng mode đó để “ack từng job độc lập” khi chưa hiểu session ownership và scope. `JmsTemplate` quản lý vòng đời session; nếu cần ACK/recover phức tạp, dùng thiết kế transaction/container phù hợp hoặc API thấp hơn có lifecycle rõ ràng.

## 15. Khi nào nên dùng @JmsListener thay cho receive?

Với một worker luôn nhận job liên tục, dùng:

~~~java
@Component
class OrderWorker {
    @JmsListener(destination = "jobs.queue")
    public void handle(String payload) {
        System.out.println("Processing " + payload);
    }
}
~~~

Đây là snippet; cần `@Component`, `@JmsListener` và cấu hình JMS/bean listener container trong ứng dụng. `@JmsListener` cho phép Spring quản lý listener threads, lifecycle, recovery/reconnection, concurrency và tích hợp transaction; tuy vậy thread listener vẫn có thể block khi code handler gọi DB/HTTP.

**Chọn receive khi:**
- Công cụ vận hành/test cần lấy **một message** với timeout hữu hạn và biết rõ tác dụng của ACK.
- Một workflow cần bounded pull theo yêu cầu, với scheduler và error handling rõ.
- Cần chủ động quyết định chính xác lúc nào nhận một message, không cần listener dài hạn.

**Chọn listener khi:**
- Có worker tiêu thụ liên tục, retry/redelivery/DLQ, nhiều consumer cạnh tranh.
- Cần scaling/concurrency và shutdown/recovery do Spring container quản lý.
- Không muốn mỗi vòng polling tự mở hoặc giữ resources.

Không có một API nào tự bảo đảm DB commit, retry đúng nghiệp vụ hay idempotency. Quyết định còn phụ thuộc queue/topic, broker policy và transaction boundaries.

## 16. Đóng, dừng và xử lý thread đang đợi

- Với timeout dương, code nhận có cơ hội trở lại định kỳ để kiểm tra cờ shutdown và cập nhật health.
- Với classic JMS, `MessageConsumer.close()` có quy tắc tương tác với `receive` đang chờ; có thể khiến một blocking receive hoàn tất, nhưng vẫn phải tuân thủ threading/lifecycle contract của provider.
- `Connection.stop()` làm dừng delivery, **không** “cancel toàn bộ receive”: timeout tiếp tục chạy.
- Không chia sẻ một `Session` classic JMS giữa nhiều thread mà không hiểu restriction của Jakarta Messaging.
- Không đóng session/connection của `JmsTemplate` từ code nghiệp vụ: template quản lý resources.
- `Thread.interrupt()`/`Future.cancel(true)` không được mặc định xem là cách hủy JMS I/O đáng tin cậy trên mọi provider.
- Với application shutdown, cần dừng việc tạo receive mới, cho các call hữu hạn kết thúc, đóng resources và bảo đảm message chưa ACK/commit có recovery phù hợp.

**Timeout không phải deadline tuyệt đối:** lỗi network và connection creation có thể mất thời gian riêng; đo shutdown duration thực tế và cấu hình connect/read timeout đặc thù JMS provider khi cần.

## 17. Bảng lỗi phổ biến

| Hiện tượng | Căn nguyên thường gặp | Cách kiểm tra |
| --- | --- | --- |
| `receive()` chờ mãi | Default timeout `0` và không có message, hoặc classic Connection chưa start | Kiểm tra timeout/start, stack trace, broker |
| `receive(2000)` trả null dù queue có message | Competing consumer, selector, delay, in-flight, sai destination | Broker consumer list, selector và headers |
| HTTP thread pool cạn | Chờ vô hạn trên request threads | Thread dump, active requests, load test |
| CPU cao khi queue rỗng | Vòng `receiveNoWait` không nghỉ | CPU profile, receive call rate |
| `receiveAndConvert` lỗi | Converter/schema/type mismatch | Type của JMS Message, converter config |
| Message mất sau khi “xem thử” | Receive là tiêu thụ, không phải peek | Dùng QueueBrowser/metrics |
| DB lỗi mà broker không redeliver | AUTO_ACK đã xác nhận trước business code | Transaction boundary thực tế |
| Nhận một message hai lần | JMS rollback/redelivery hoặc producer gửi duplicate | JMSMessageID, eventId và inbox |
| Async task đã cancel nhưng worker vẫn chờ | Interrupt không đảm bảo JMS client thoát | Receive timeout hữu hạn, provider shutdown |
| Topic mất message lúc offline | Subscriber không durable | Subscription identity/retention |
| 3s timeout nhưng method mất 8s | Setup network và resource acquisition thêm thời gian | Metric từng phase, provider client settings |

**Không chẩn đoán “deadlock” chỉ vì có thread trong `JmsTemplate.receive`.** Một lời gọi nhận đang chờ là hành vi bình thường của API blocking. Deadlock đòi bằng chứng chu trình chờ khóa/tài nguyên, không phải chỉ nhìn thấy từ `WAITING`.

## 18. Bài tập và câu hỏi tự kiểm tra

1. **Receive timeout:** trên queue test rỗng, gọi `setReceiveTimeout(1000)` rồi `receive`; đo gần đúng khoảng chờ và xác nhận kết quả `null`.
2. **No-wait:** đặt `-1` rồi nhận; sau đó gửi message và nhận lại. Giải thích vì sao đây không phải peek.
3. **Indefinite:** gọi receive mặc định trên một worker riêng, gửi một message sau đó để nó thoát; không dùng HTTP request thread.
4. **Classic Connection.start:** tạo consumer nhưng không start, thử `receive(1000)`; start connection rồi thử lại.
5. **Competing consumers:** hai worker nhận trên cùng queue; gửi một message và giải thích vì sao chỉ một worker nhận ở mỗi delivery.
6. **Selector:** gửi properties `eventType` khác nhau; chọn selector và quan sát timeout không đồng nghĩa queue rỗng.
7. **receiveAndConvert:** thử `TextMessage`/`BytesMessage` với converter mặc định, sau đó thay converter JSON có contract rõ.
8. **Thread pool:** với pool 2 threads, tạo 3 bounded receives; quan sát một task phải chờ slot của executor khi hai worker đang blocked.
9. **HTTP request:** dùng endpoint test với timeout dương và endpoint thiếu timeout, xem sự khác biệt về độ chiếm request threads.
10. **AUTO_ACK:** nhận message rồi cố ý ném lỗi ở business code bên ngoài receive; quan sát redelivery/không redelivery tùy cấu hình.
11. **JMS transaction:** bọc receive và xử lý trong `JmsTransactionManager`, throw exception để xem rollback; không nhầm với DB transaction.
12. **Crash sau DB commit:** mô phỏng JVM fail giữa DB và JMS commit, xác minh unique event ID bảo vệ nghiệp vụ.
13. **Shutdown:** dừng ứng dụng khi đang receive, xác minh call hữu hạn kết thúc và resources không leak.
14. **Topic:** so sánh non-durable subscription đang online và offline, tránh ngộ nhận topic giữ lịch sử cho mọi consumer.

### Checklist hoàn tất

- [ ] Biết thread nào bị giữ khi gọi `receive`.
- [ ] Nhớ rằng `receive(0)` là chờ vô thời hạn; `receiveNoWait()` không chờ.
- [ ] Biết `JmsTemplate.setReceiveTimeout(0)` = indefinite, `-1` = no-wait và số dương = bounded.
- [ ] Phân biệt `receive` (JMS Message) với `receiveAndConvert` (Java Object).
- [ ] Biết classic `Connection.start()` cần cho delivery, còn `JmsTemplate` tự quản lý connection.
- [ ] Không coi `null` là toàn bộ queue chắc chắn rỗng hoặc nghiệp vụ hoàn thành.
- [ ] Không dùng no-wait trong busy loop không kiểm soát.
- [ ] Không giữ servlet thread chờ message vô hạn.
- [ ] Không giả định `Future.cancel(true)` hủy JMS receive ngay.
- [ ] Hiểu ACK/transaction và hậu quả nếu DB fail sau khi JMS đã ACK.
- [ ] Biết khi nào một `@JmsListener` tốt hơn tự triển khai polling loop.

**Câu hỏi chốt:** “Không có message trong queue, `jmsTemplate.receive("jobs.queue")` mặc định làm gì?” — Với `receiveTimeout=0` mặc định, **thread gọi sẽ chờ vô thời hạn** tới khi có message hoặc một điều kiện khác kết thúc lời gọi. Đây là đặc tính cốt lõi cần đưa vào mọi quyết định dùng synchronous receive.

## 19. Tài liệu chính thức

1. [Spring Framework – Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html): nhận đồng bộ và blocking thread, timeout, message listener containers.
2. [Spring Framework 6.2 – JmsTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html): các overload `receive`, `receiveAndConvert`, `receiveSelected` và default session settings.
3. [Spring Framework – JmsDestinationAccessor](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/support/destination/JmsDestinationAccessor.html): các hằng `RECEIVE_TIMEOUT_INDEFINITE_WAIT`, `RECEIVE_TIMEOUT_NO_WAIT`.
4. [Spring Framework – Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): `JmsTransactionManager` và tài nguyên JMS.
5. [Jakarta Messaging 3.1 – MessageConsumer](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageconsumer): `receive`, `receive(long)`, `receiveNoWait`, `close`.
6. [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): `Connection.start/stop`, synchronous reception, ACK/transaction và threading.
7. [Spring Boot 3.5 – Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): `spring.jms.template.receive-timeout` và listener properties.

**Kết luận:** nhận đồng bộ cho phép chủ động lấy một message, nhưng cái giá là **thread phải chờ**, có thể vô thời hạn theo mặc định. Chỉ sử dụng khi đã xác định rõ timeout, tài nguyên, thread ownership, ACK/transaction và cách shutdown. Với consumer làm việc nền liên tục, ưu tiên Spring listener container nếu không có lý do cụ thể phải polling bằng `receive`.