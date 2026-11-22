# Gửi bất đồng bộ bằng CompletionListener trong API JMS

## 1. Mục tiêu và bối cảnh

Trong JMS, phương thức gửi thông điệp thường được viết `producer.send(message)`. Ở dạng **gửi đồng bộ (synchronous send)**, thread gọi phải đợi `send` trả về; mức độ bảo đảm khi lệnh trả về phụ thuộc delivery mode, chính sách broker/provider và transaction.

Từ JMS 2.0, Jakarta Messaging cung cấp **asynchronous send** với `jakarta.jms.CompletionListener`. Thay vì đợi toàn bộ quá trình gửi hoàn thành trong thread gọi, ứng dụng cung cấp callback để JMS provider thông báo kết quả ở thời điểm thích hợp. Đây là API **gửi bất đồng bộ**, không phải API nhận message bất đồng bộ và cũng không phải Spring `@Async`.

Bài thuộc nội dung **chất lượng gửi** của Spring JMS, tập trung vào:

- Cách đăng ký `CompletionListener` trên `MessageProducer` và `JMSProducer`.
- Hành vi `onCompletion(Message)`, `onException(Message, Exception)` và trường hợp `send()` ném lỗi ngay.
- Ý nghĩa chính xác của “gửi thành công” với `PERSISTENT`, transaction, acknowledgement và khả năng duplicate.
- Threading, giới hạn sử dụng `Message`, thứ tự callback, quy tắc `close/commit/rollback`.
- Ví dụ Spring Boot dùng **API JMS gốc** để gửi ba message bất đồng bộ nhưng kiểm soát thời điểm hoàn tất.
- Quan hệ với `JmsTemplate` và ranh giới tối ưu hóa/ownership của Spring.
- Testing, observability, timeout, backpressure, retry và các lỗi phổ biến.

Ví dụ dùng **Java 17+, Spring Boot 3.5.8, Jakarta Messaging 3.x** và Apache ActiveMQ Artemis. Trong ứng dụng Spring Framework hiện đại, import là `jakarta.jms.*`; phiên bản cũ có thể dùng `javax.jms.*`. Riêng Jakarta EE **web container/Enterprise Beans container** có hạn chế quan trọng với async send (mục 10).

## 2. So sánh gửi đồng bộ và gửi bất đồng bộ

### 2.1. Gửi đồng bộ

```java
producer.send(message);
// Thread tiếp tục sau khi lệnh send trả về.
```

Cú pháp trên là snippet nằm trong method đã có `MessageProducer producer` và `Message message`. Với nhiều JMS provider, gửi `PERSISTENT` có thể yêu cầu chờ broker xác nhận trước khi `send` trả về. Tuy nhiên, đặc tả cũng cho phép một số mức độ tin cậy thấp hơn không phải đợi cùng loại acknowledgement; không nên suy từ tên “synchronous” rằng mọi lệnh đã được fsync bền vững trên mọi broker.

### 2.2. Gửi bất đồng bộ với CompletionListener

```java
producer.send(message, new CompletionListener() {
    @Override
    public void onCompletion(Message sentMessage) {
        // JMS provider thông báo thao tác gửi hoàn tất thành công.
    }

    @Override
    public void onException(Message attemptedMessage, Exception error) {
        // Lỗi được phát hiện sau khi send() đã được gọi.
    }
});
// Thread gọi có thể tiếp tục mà chưa có callback.
```

Snippet cần các import `jakarta.jms.CompletionListener`, `jakarta.jms.Message` và một `MessageProducer` đã tạo. Ở đây **`send(...)` trả về không đồng nghĩa `onCompletion` đã được gọi**. Provider quyết định phần xử lý nào diễn ra trong thread gọi và phần nào chạy bất đồng bộ, miễn đáp ứng contract Jakarta Messaging.

### 2.3. Dòng thời gian

```text
Thread ứng dụng                         JMS provider / broker
      |                                           |
      | producer.send(message, listener)          |
      |------------------------------>            |
      |          (lệnh có thể trả về)              |
      |<------------------------------            |
      |                                           |
      | làm việc tiếp                            xử lý gửi / chờ ack nếu cần
      |                                           |
      |                                      thành công hoặc lỗi
      |                                           |
      |                         provider thread gọi CompletionListener
      |                                      | onCompletion(...)
      |                                      | hoặc onException(...)
      |                                           |
      | ứng dụng cập nhật trạng thái / quan sát kết quả qua thread-safe signal
```

Lợi ích chính là **không buộc thread gửi phải đợi hoàn tất mỗi message** trước khi làm việc khác hoặc yêu cầu gửi tiếp. Đổi lại, ứng dụng phải theo dõi các thao tác đang chờ, xử lý lỗi ở cả hai đường và quản lý tài nguyên đủ lâu.

## 3. Các API hỗ trợ asynchronous send

### 3.1. Classic JMS API: MessageProducer

`MessageProducer` có các overload phù hợp:

```java
// Producer gắn với một destination:
void send(Message message, CompletionListener listener) throws JMSException;

void send(Message message,
          int deliveryMode,
          int priority,
          long timeToLive,
          CompletionListener listener) throws JMSException;

// Producer không định danh destination:
void send(Destination destination,
          Message message,
          CompletionListener listener) throws JMSException;

void send(Destination destination,
          Message message,
          int deliveryMode,
          int priority,
          long timeToLive,
          CompletionListener listener) throws JMSException;
```

Các chữ ký trên để học API, **không phải những method cần định nghĩa lại**. Tham số `listener` cho phép JMS provider gọi callback sau khi thao tác kết thúc. Chúng xuất hiện từ JMS 2.0; chọn đúng Jakarta Messaging API và provider hỗ trợ.

Có thể gắn producer với một Queue từ khi tạo:

```java
Queue queue = session.createQueue("orders.queue");
MessageProducer producer = session.createProducer(queue);
producer.send(session.createTextMessage("order-42"), listener);
```

Hoặc tạo producer không gắn destination, sau đó chỉ rõ Queue trên từng lần gửi:

```java
MessageProducer producer = session.createProducer(null);
producer.send(
        session.createQueue("orders.queue"),
        session.createTextMessage("order-42"),
        listener);
```

Cả hai là snippet: biến `session` và `listener` cần tồn tại trong một method; ứng dụng phải đóng producer do mình tạo.

### 3.2. Simplified JMS API: JMSContext/JMSProducer

Với `JMSContext`, bạn có thể tạo `JMSProducer` và chỉ định listener bằng `setAsync`:

```java
try (JMSContext context =
             connectionFactory.createContext(JMSContext.AUTO_ACKNOWLEDGE)) {

    Queue queue = context.createQueue("orders.queue");
    JMSProducer producer = context.createProducer()
            .setAsync(listener);
    producer.send(queue, "order-42");

    // Cần xử lý kết quả callback nếu logic gọi phải biết gửi thành công.
}
```

Đây là snippet thuộc phương thức đã có `connectionFactory` và `listener`. `JMSContext` đóng ở cuối `try-with-resources` và theo đặc tả việc đóng phải đợi các async send/callback còn dang dở trước khi hoàn tất. Vì vậy đoạn này có callback bất đồng bộ, nhưng **không nên quảng cáo phương thức bọc `try-with-resources` này sẽ trả về ngay**.

Các khác biệt API:

| Classic JMS API | Simplified JMS API |
| --- | --- |
| `Connection + Session + MessageProducer` | `JMSContext + JMSProducer` |
| `producer.send(message, completionListener)` | `producer.setAsync(completionListener).send(destination, body)` |
| Thường có checked `JMSException` | Nhiều thao tác sử dụng unchecked `JMSRuntimeException` |
| Chủ động quản lý vòng đời producer/session/connection | `JMSContext` gom nhiều trách nhiệm và là `AutoCloseable` |
| Dễ tùy biến mức thấp với `Session` | Gọn khi ứng dụng không cần classic API |

`JMSProducer.setAsync(null)` được dùng để quay lại hành vi gửi đồng bộ. Không share một `JMSContext` mutable tùy ý giữa nhiều thread: nó biểu diễn một session và chịu quy tắc threading của JMS.

## 4. Contract chính xác của CompletionListener

Interface `jakarta.jms.CompletionListener` có hai phương thức:

```java
public interface CompletionListener {
    void onCompletion(Message message);
    void onException(Message message, Exception exception);
}
```

### 4.1. onCompletion: thao tác gửi hoàn tất với mức bảo đảm tương đương synchronous send

Provider chỉ được gọi `onCompletion(message)` khi send đã thành công với **cùng mức độ chắc chắn** mà một `send` đồng bộ tương đương phải cung cấp. Nghĩa cụ thể vẫn phụ thuộc delivery mode, provider và transaction. `onCompletion` **không** có nghĩa consumer đã nhận, xử lý xong, commit database hay gửi response nghiệp vụ.

Với session có **local JMS transaction**, callback gửi thành công có thể xảy ra **trước** khi application gọi `session.commit()`. Message trong transaction đó chưa được coi là đã commit chỉ vì callback đã chạy. `CompletionListener` là tín hiệu **hoàn thành thao tác gửi**, không phải callback “JMS transaction committed”.

Khi callback thành công, mã có thể ghi metrics, hoàn thành một future, cập nhật trạng thái job ở bộ nhớ hoặc chuyển một signal nhẹ sang executor xử lý tiếp. Nếu cần độ tin cậy qua restart, trạng thái quan trọng phải được ghi bền vững trong thiết kế nghiệp vụ.

### 4.2. onException: lỗi không thể ném trực tiếp từ send

Nếu provider phát hiện lỗi **sau khi lệnh `send` đã trả về**, nó gọi `onException(message, exception)`. **Không thể khẳng định chắc chắn message chưa tới broker**; đặc tả nêu rằng khi có lỗi, việc gửi thành công hay không có thể ở trạng thái không xác định.

Ví dụ mất kết nối giữa chừng: broker có thể đã nhận message nhưng confirmation chưa đến client. Retry vô điều kiện có thể tạo message trùng nghiệp vụ. Hãy gắn `eventId`/`orderId` và thiết kế consumer idempotent.

### 4.3. Exception ném ngay trong send(): không có callback cho lần gửi đó

Nếu một exception xảy ra và được ném **trực tiếp trong thread đang gọi `send(...)`**, provider **không** gọi `onCompletion` hoặc `onException` cho cùng invocation đó.

Điều này đặc biệt quan trọng khi đếm `CountDownLatch`. Nếu chương trình chỉ giảm latch trong callback mà `send` ném lỗi đồng bộ, chương trình có thể chờ mãi. Mẫu đúng phải có cả:

```java
try {
    producer.send(message, listener);
} catch (JMSException | RuntimeException immediateFailure) {
    // Không chờ callback cho invocation đã ném exception đồng bộ.
    // Cập nhật failure và signal completion ở đây.
}
```

`onException` nhận `Exception`, không chỉ `JMSException`. Tuy nhiên application không nên xử lý mọi lỗi theo cùng một kiểu retry; cần phân biệt lỗi cấu hình/quyền, lỗi payload và lỗi transport.

### 4.4. Threading và cách dùng Message

Theo Jakarta Messaging:

- Provider gọi `CompletionListener` trên **thread khác** với thread đang thực hiện lệnh async `send`. Vì vậy callback phải thread-safe.
- Một `Session` không được sử dụng đồng thời tùy ý từ nhiều thread. Callback **không nên** truy cập cùng session khi application thread vẫn có thể đang dùng session đó.
- Với cùng `MessageProducer`, thứ tự callback tương ứng với thứ tự các lời gọi async `send`. Với nhiều producer/session/thread, không suy ra thứ tự callback toàn cục.
- Sau khi `send` trả về nhưng **trước khi callback chạy**, ứng dụng không được đọc/chỉnh sửa headers, properties hoặc body của chính `Message` đang gửi. Provider có thể đang thay đổi message trên thread khác.
- Trong `onException`, một số header/property do provider thiết lập khi gửi có trạng thái **không xác định**; không xây quy trình lỗi phụ thuộc các trường đó.
- Mỗi message đang gửi nên có **đối tượng `Message` riêng**. Đừng gửi xong rồi sửa lại cùng instance để dùng cho message kế tiếp trước callback.

Vì vậy callback tốt nhất giữ **eventId là biến final/effectively final ở ngoài**, rồi dùng eventId đó để log/tracking thay vì đọc các field mutable của message lúc lỗi.

## 5. Quy tắc close, commit, rollback — phần dễ bị hiểu nhầm

Jakarta Messaging đặt ra hai quy tắc rất quan trọng cho asynchronous send:

1. Khi ứng dụng gọi `close()` trên `MessageProducer`, `Session` hoặc `Connection`, provider phải **đợi các asynchronous send còn dang dở hoàn thành và các callback tương ứng trả về** trước khi hoàn tất `close()`.
2. Với **local transacted Session**, khi ứng dụng gọi `commit()` hoặc `rollback()`, provider phải đợi các asynchronous send còn dang dở và callback của chúng kết thúc rồi mới tiến hành commit/rollback.

Nói cách khác, **gửi bất đồng bộ không làm cho `close` hoặc `commit` trở thành non-blocking**. Đó là lý do code “gửi async rồi ngay lập tức đóng producer” có thể không có lợi về latency như mong đợi.

Một `CompletionListener` **không được** gọi `close()` của chính producer/session/connection liên quan đến lần gửi hoặc gọi `commit()`/`rollback()` trên session liên quan. Provider sẽ ném `IllegalStateException` hoặc `IllegalStateRuntimeException` thích hợp.

Ví dụ **không nên viết**:

```java
producer.send(message, new CompletionListener() {
    @Override
    public void onCompletion(Message ignored) {
        producer.close(); // SAI: không close producer trong callback của nó.
    }

    @Override
    public void onException(Message ignored, Exception error) {
        // Cũng không commit/rollback session trong callback.
    }
});
```

Đoạn trên là ví dụ **anti-pattern**, không phải code để chạy. Trong ứng dụng thật, callback chỉ báo kết quả qua `CompletableFuture`, `CountDownLatch`, queue nội bộ hoặc trạng thái an toàn thread. Một **owner khác** chịu trách nhiệm đóng tài nguyên sau khi biết callback đã trả về.

**Lưu ý về timeout:** `latch.await(10, SECONDS)` chỉ giới hạn thời gian chờ của application thread ở lời gọi đó; `close()` trong `finally`/`try-with-resources` còn có quy tắc chờ callback nên timeout của latch **không bảo đảm** tổng thời gian kết thúc phương thức là 10 giây. Thời gian kết nối, gửi, close/recovery cần cấu hình và đo theo provider.

## 6. Ví dụ Spring Boot chạy được: gửi ba message bất đồng bộ

Ví dụ là một **Spring Boot client application**, không phải Jakarta EE WAR trong application server. Nó để Spring Boot tạo `ConnectionFactory` cho Artemis, rồi sử dụng **Jakarta Messaging API gốc** bên trong `ApplicationRunner`.

Mục tiêu kỹ thuật của ví dụ:

1. Gửi ba `TextMessage` khác nhau bằng overload `MessageProducer.send(message, CompletionListener)`.
2. Không đợi callback sau **từng** send; gửi các invocation tuần tự qua cùng session.
3. Dùng `CountDownLatch` và `AtomicInteger` để đợi callback theo thread-safe cách trước khi kết luận.
4. Xử lý riêng hai đường lỗi: exception đồng bộ tại `send` và callback `onException`.
5. Đóng resource do ứng dụng mở đúng lifecycle; không đóng trong callback.

### 6.1. Điều kiện chạy

- JDK 17+, Maven.
- Một Apache ActiveMQ Artemis broker chạy tại `tcp://localhost:61616`, hoặc sửa endpoint theo môi trường.
- `demo.async.queue` đã tồn tại trên broker hoặc broker cho phép auto-create Queue ANYCAST phù hợp.
- Tài khoản JMS được phép gửi. Đặt `JMS_USERNAME` và `JMS_PASSWORD` trong environment; không hardcode password production.
- Broker/client hỗ trợ Jakarta Messaging async send theo phiên bản dependency. Một số provider có tối ưu hóa/buffer khác nhau, nên đo thực tế trước khi dùng thông lượng production.

### 6.2. Maven dependency

**`pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.8</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>async-jms-completion</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-artemis</artifactId>
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
```

`spring-boot-starter-artemis` mang Spring JMS và Artemis Jakarta client tương thích qua dependency management của Boot. Không cần thêm `javax.jms-api`; mã của ví dụ import `jakarta.jms`.

### 6.3. application.properties

**`src/main/resources/application.properties`**

```properties
spring.artemis.mode=native
spring.artemis.broker-url=${JMS_BROKER_URL:tcp://localhost:61616}
spring.artemis.user=${JMS_USERNAME}
spring.artemis.password=${JMS_PASSWORD}
spring.jms.pub-sub-domain=false
```

Các giá trị `JMS_USERNAME` và `JMS_PASSWORD` **không có default** trong ví dụ để tránh tự động dùng tài khoản không chủ đích. Chúng phải được cấp khi khởi động. `spring.artemis.mode=native` yêu cầu Artemis broker bên ngoài; ứng dụng không khởi động embedded broker.

### 6.4. Toàn bộ Java code

**`src/main/java/example/jms/AsyncCompletionApplication.java`**

```java
package example.jms;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import jakarta.jms.CompletionListener;
import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.MessageProducer;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class AsyncCompletionApplication {

    private static final String QUEUE_NAME = "demo.async.queue";
    private static final int MESSAGE_COUNT = 3;

    public static void main(String[] args) {
        SpringApplication.run(AsyncCompletionApplication.class, args);
    }

    @Bean
    ApplicationRunner demo(ConnectionFactory factory) {
        return args -> sendMessages(factory);
    }

    static void sendMessages(ConnectionFactory factory) throws Exception {
        CountDownLatch callbacks = new CountDownLatch(MESSAGE_COUNT);
        AtomicInteger successes = new AtomicInteger();
        AtomicInteger failures = new AtomicInteger();
        AtomicInteger sendCallsReturned = new AtomicInteger();

        try (Connection connection = factory.createConnection();
             Session session =
                     connection.createSession(Session.AUTO_ACKNOWLEDGE);
             MessageProducer producer =
                     session.createProducer(session.createQueue(QUEUE_NAME))) {

            for (int i = 1; i <= MESSAGE_COUNT; i++) {
                String eventId = "event-" + i;
                TextMessage message =
                        session.createTextMessage("payload-" + eventId);
                message.setStringProperty("eventId", eventId);

                CompletionListener listener = new CompletionListener() {
                    @Override
                    public void onCompletion(Message ignored) {
                        // Provider thread; không thao tác với Session tại đây.
                        successes.incrementAndGet();
                        callbacks.countDown();
                    }

                    @Override
                    public void onException(
                            Message ignored, Exception error) {
                        // Không đọc trạng thái mutable của Message nếu lỗi.
                        failures.incrementAndGet();
                        System.err.println(
                                "callbackFailed=" + eventId + ":"
                                + error.getClass().getSimpleName());
                        callbacks.countDown();
                    }
                };

                try {
                    producer.send(message, listener);
                    sendCallsReturned.incrementAndGet();
                } catch (JMSException | RuntimeException immediateError) {
                    // Theo spec, invocation ném lỗi trực tiếp
                    // sẽ không nhận thêm callback.
                    failures.incrementAndGet();
                    System.err.println(
                            "sendFailedImmediately=" + eventId + ":"
                            + immediateError.getClass().getSimpleName());
                    callbacks.countDown();
                }
            }

            System.out.println(
                    "sendCallsReturned=" + sendCallsReturned.get());

            boolean allSignalled =
                    callbacks.await(15, TimeUnit.SECONDS);
            if (!allSignalled) {
                throw new IllegalStateException(
                        "Timeout waiting for send completion callbacks");
            }
            if (failures.get() != 0) {
                throw new IllegalStateException(
                        "Failed sends=" + failures.get());
            }

            System.out.println(
                    "callbacksSucceeded=" + successes.get());
        }
        // Không gọi Connection.start() vì ví dụ chỉ gửi.
        // close() chờ các async send/callback còn dang dở.
    }
}
```

**Tại sao mẫu này an toàn hơn demo “fire-and-forget”?**

- Session chỉ được thread `ApplicationRunner` sử dụng cho các lời gọi `send` tuần tự; callback chỉ cập nhật biến thread-safe.
- Ba `TextMessage` riêng biệt được chuẩn bị trước mỗi invocation. Không sửa lại message sau khi `send` trả về.
- `CountDownLatch` nhận tín hiệu khi callback chạy **hoặc** khi `send` ném exception trực tiếp. Theo JMS spec, hai tình huống này không cùng xảy ra cho một invocation.
- Callback không gọi `close/commit/rollback` và không truy cập session.
- Producer, session và connection được đóng ngoài callback; không rò rỉ tài nguyên nếu gửi lỗi.
- `sendCallsReturned` chỉ đếm lời gọi `send` trả về bình thường; `callbacksSucceeded` mới đếm số callback thành công. Hai đại lượng khác nhau.
- Không dùng `@Async`, `CompletableFuture.runAsync` hoặc thread pool tự tạo để “bọc” lời gọi JMS; tính bất đồng bộ đến từ **Jakarta Messaging provider**.

Một lưu ý đặc biệt: trong ứng dụng Spring Boot mặc định, `ConnectionFactory` có thể là wrapper caching. `close()` trên connection/session wrapper có thể là trả về cache, nhưng contract JMS về xử lý async còn dang dở vẫn cần được provider/wrapper thực hiện đúng; kiểm tra với phiên bản và provider triển khai.

### 6.5. Chạy

Tạo cấu trúc project tương ứng:

```text
async-jms-completion/
├── pom.xml
└── src/main/
    ├── java/example/jms/AsyncCompletionApplication.java
    └── resources/application.properties
```

PowerShell:

```powershell
$env:JMS_BROKER_URL = "tcp://localhost:61616"
$env:JMS_USERNAME = "dev-user"
$env:JMS_PASSWORD = "dev-password"
mvn spring-boot:run
```

Shell POSIX:

```bash
JMS_BROKER_URL=tcp://localhost:61616 \
JMS_USERNAME=dev-user \
JMS_PASSWORD=dev-password \
mvn spring-boot:run
```

Thay account và endpoint theo broker thật. Khi ba lệnh gửi được chấp nhận, ba callback báo thành công và không có lỗi, **hai dòng do ứng dụng in** là:

```text
sendCallsReturned=3
callbacksSucceeded=3
```

Spring Boot/Artemis có thể ghi thêm log; các callback có thể chạy trước, trong hoặc sau vòng `for`, nhưng lệnh in `callbacksSucceeded` chỉ được thực hiện sau khi latch hoàn tất. Nếu provider không báo kết quả trong 15 giây, chương trình báo lỗi timeout; **thời gian close** sau đó vẫn có thể dài hơn. Nếu broker dừng, Queue không hợp lệ hoặc thiếu quyền, chương trình sẽ in lỗi hoặc ném exception; không khẳng định kết quả trên mọi môi trường.

Để build mà chưa chạy broker:

```bash
mvn -q -DskipTests package
```

Để kiểm chứng message thật, cần integration test hoặc broker console/metrics. Dòng `callbacksSucceeded=3` **không phải bằng chứng ba consumer đã xử lý** hay transaction database downstream đã commit.

## 7. Hai đường lỗi và cách thiết kế Future/CompletionStage

Ứng dụng thực có thể muốn trả `CompletionStage` thay vì chờ `CountDownLatch` trong request thread. Mô hình là gán **mỗi invocation** một `CompletableFuture`, rồi hoàn thành trong callback:

```java
CompletableFuture<Void> result = new CompletableFuture<>();

CompletionListener listener = new CompletionListener() {
    @Override
    public void onCompletion(Message message) {
        result.complete(null);
    }

    @Override
    public void onException(Message message, Exception exception) {
        result.completeExceptionally(exception);
    }
};

try {
    producer.send(message, listener);
} catch (JMSException | RuntimeException ex) {
    result.completeExceptionally(ex);
}
```

Đây là **snippet** với `producer` và `message` đã được tạo; cần import `java.util.concurrent.CompletableFuture`. Không được quên đường `catch`, vì callback không tới nếu send ném lỗi trực tiếp.

### Future hoàn thành chưa đồng nghĩa được đóng resource

Đoạn trên chỉ cho thấy cách chuyển kết quả JMS callback sang Future. **Nó chưa phải một hàm non-blocking hoàn chỉnh**, vì `producer`, `session` và `connection` phải tiếp tục tồn tại cho đến khi send/callback hoàn thành. Không viết:

```java
CompletionStage<Void> sendAndReturn() {
    try (Connection c = factory.createConnection();
         Session s = c.createSession(Session.AUTO_ACKNOWLEDGE);
         MessageProducer p = s.createProducer(s.createQueue("orders.queue"))) {

        CompletableFuture<Void> future = new CompletableFuture<>();
        p.send(s.createTextMessage("event"), new CompletionListener() {
            @Override
            public void onCompletion(Message m) {
                future.complete(null);
            }

            @Override
            public void onException(Message m, Exception e) {
                future.completeExceptionally(e);
            }
        });
        return future;
    }
}
```

Đoạn này là **anti-pattern minh họa**, thiếu imports/fields và không dùng làm code sản xuất. `return future` xảy ra trước khi rời `try`, nhưng Java bắt buộc chạy `close()` rồi mới thực sự trả kết quả; `close` có thể đợi callback. Bạn đã vô tình chặn thread dù API bên trong là async.

Thiết kế lâu dài cần **resource owner rõ ràng** (component quản lý connection/session/producer hoặc executor riêng theo pool), lifetime tương ứng với các send đang chờ và cleanup ở một **thread điều phối khác**, **không** trong `CompletionListener` của chính producer/session đó. Nếu không có nhu cầu duy trì resource phức tạp, mẫu ở mục 6 chủ động chờ callback rồi đóng là lựa chọn dễ kiểm chứng hơn.

### Nếu Future bị timeout hoặc cancel?

Một `CompletableFuture.orTimeout(...)`/`cancel(...)` thường chỉ thay đổi trạng thái Future ở tầng Java; nó **không mặc định hủy** thao tác gửi JMS đang chạy hoặc làm broker rollback. Sau timeout, callback vẫn có thể đến. Cần lưu eventId, thực hiện reconciliation với broker/consumer và có quy tắc quản lý tài nguyên khi request lifecycle kết thúc.

## 8. CompletionListener, transaction JMS và chất lượng gửi

### 8.1. Callback thành công khác với commit thành công

Giả sử bạn dùng local transacted session:

```java
try (Connection connection = factory.createConnection();
     Session session =
             connection.createSession(Session.SESSION_TRANSACTED);
     MessageProducer producer =
             session.createProducer(session.createQueue("orders.queue"))) {

    CountDownLatch latch = new CountDownLatch(1);
    AtomicReference<Exception> asyncError = new AtomicReference<>();

    producer.send(session.createTextMessage("order-42"),
            new CompletionListener() {
                @Override
                public void onCompletion(Message message) {
                    latch.countDown();
                }

                @Override
                public void onException(Message message, Exception error) {
                    asyncError.set(error);
                    latch.countDown();
                }
            });

    if (!latch.await(15, TimeUnit.SECONDS)) {
        session.rollback();
        throw new IllegalStateException("Async completion timeout");
    }
    if (asyncError.get() != null) {
        session.rollback();
        throw new IllegalStateException(
                "Async send failure", asyncError.get());
    }

    session.commit();
}
```

Đây là **snippet đặt trong method `throws Exception`** đã có `factory`, imports JMS/CountDownLatch/TimeUnit/AtomicReference; nó không phải chương trình độc lập. Về mặt lý thuyết, `session.commit()` sẽ chờ callback còn dang dở trước khi commit local transaction, nên việc `await` trước `commit` không bắt buộc để provider chờ, nhưng hữu ích khi ứng dụng muốn tự phân loại lỗi trước khi quyết định rollback.

**Không gọi `commit/rollback` từ callback.** Callback có thể chạy trước khi transaction commit; `onCompletion` không chứng minh transaction đã commit. Nếu `commit` ném lỗi do mất kết nối, kết quả có thể không xác định với client; do đó cần eventId/idempotency. `rollback` cũng có thể thất bại khi broker mất kết nối.

### 8.2. Khi Spring đang quản lý transaction

Nếu session đã tham gia `JmsTransactionManager` hoặc JTA, không gọi `session.commit()`/`rollback()` thủ công. Transaction manager sở hữu boundary. Trong Spring, phải bảo đảm callback kết quả/lỗi được đưa vào logic transaction **trước khi manager quyết định commit/rollback**; nếu callback `onException` xảy ra nhưng service đã trả về bình thường và không đánh dấu lỗi transaction, bạn có thể có sai lệch so với kỳ vọng nghiệp vụ.

Khi ứng dụng cần nhiều send atomic trong Spring, API đơn giản hơn thường là `JmsTemplate` với `JmsTransactionManager` và `@Transactional`/`TransactionTemplate`, chứ không bắt buộc dùng `CompletionListener`. Chọn async send chỉ khi nó giải quyết yêu cầu latency/throughput rõ ràng và lifecycle được thiết kế đúng.

**Quan trọng:** Transaction JMS local không tự atomic với transaction SQL. Nếu ứng dụng cập nhật DB và gửi JMS, cân nhắc transactional outbox hoặc JTA/XA thực sự khi cần bảo đảm nhất quán.

### 8.3. Delivery mode và những cam kết thực tế

| Thiết lập hoặc tín hiệu | Điều nó nói | Điều nó không cam kết |
| --- | --- | --- |
| `DeliveryMode.PERSISTENT` | Yêu cầu mức đảm bảo persistent theo JMS/provider | Không thay thế hoàn toàn cấu hình replication/HA/broker backup. |
| `DeliveryMode.NON_PERSISTENT` | Cho phép mức đảm bảo thấp hơn để tối ưu hiệu năng | Không cam kết message tồn tại qua broker crash. |
| `onCompletion` | Gửi hoàn thành với mức tin cậy như synchronous send tương đương | Không chứng minh consumer đã xử lý hoặc DB downstream commit. |
| `onException` | Provider phát hiện lỗi async | Không chứng minh broker chưa từng nhận message. |
| `JmsTransactionManager.commit` thành công | Transaction JMS của session đã commit theo provider | Không đồng nghĩa transaction DB của hệ thống khác commit. |
| `message.setJMSCorrelationID` | Tạo correlation cho tracing/request-reply | Không tạo idempotency hoặc chống duplicate tự động. |
| `timeToLive` | Giới hạn thời gian sống của message theo JMS | Không phải timeout đợi callback và không bảo đảm processing deadline. |

**Nhầm lẫn nguy hiểm:** “send callback success” và “message processed exactly once” là hai bài toán khác nhau. Downstream có thể redeliver sau lỗi consumer, message hết TTL, bị DLQ hoặc được nhiều hệ thống xử lý theo policy.

## 9. Thứ tự gọi send, thứ tự callback và thứ tự xử lý

Jakarta Messaging yêu cầu khi cùng một `MessageProducer` gửi nhiều message, các quy tắc thứ tự JMS phải được tôn trọng, kể cả khi trộn synchronous/async send. Ứng dụng **không bắt buộc** đợi callback đầu tiên mới được gửi message tiếp theo.

Với cùng producer, provider gọi các callback theo thứ tự tương ứng các invocation async send. Tuy vậy:

- **Callback order** không phải **business completion order** của consumer: một Queue có nhiều consumer xử lý song song.
- Các session khác nhau hoặc nhiều producer khác nhau **không có một thứ tự callback toàn cục**.
- Priority, redelivery, expiration, message grouping và provider policy có thể ảnh hưởng thứ tự delivery/processing thực tế.
- Với hai Queue khác nhau, không có thứ tự business processing chung chỉ vì ứng dụng gửi chúng liên tiếp.
- Với một send thất bại, callback tương ứng có thể là `onException` hoặc **không có callback** nếu exception được ném trực tiếp trong thread gọi.

Nếu ứng dụng cần ordering theo `orderId`, hãy kết hợp single-consumer/partition/message-group theo khả năng broker và idempotency, không dựa vào thứ tự log callback.

## 10. Giới hạn nền tảng: Jakarta EE container và Spring Boot

Jakarta Messaging 3.1 quy định **asynchronous send bằng `CompletionListener` không được dùng trong Jakarta EE web container hoặc Enterprise Beans container**. Những API có hạn chế này gồm các overload `MessageProducer.send(..., CompletionListener)` và `JMSProducer.setAsync(CompletionListener)`. Provider được phép ném `JMSException` hoặc `JMSRuntimeException` trong môi trường đó.

Điều này **không đồng nghĩa cấm mọi async JMS send trong Spring Boot standalone**. Ví dụ mục 6 là Spring Boot Java application chạy ngoài Jakarta EE web/EJB container nên không gặp hạn chế container đó chỉ do dùng `@SpringBootApplication`. Nhưng nếu triển khai Spring thành WAR chạy **bên trong một Jakarta EE application server** hoặc dùng resource adapter/container-managed JMS, phải kiểm tra rõ quy định và cách tích hợp hạ tầng. Không giả định cùng một đoạn code được phép chạy y hệt ở mọi kiểu deployment.

Với ứng dụng Spring quản lý resource thông qua `JmsTemplate`:

- `JmsTemplate.send`/`convertAndSend` là facade **đồng bộ theo lời gọi** thông thường, không mặc nhiên nhận `CompletionListener`.
- Có thể chạm API gốc qua `JmsTemplate.execute(SessionCallback)` để tạo producer và gọi overload async, **nhưng** callback kết thúc rồi template dọn resource, `close` có thể phải chờ async completion. Mẫu đó không tự động tạo một non-blocking service API.
- `@Async` hoặc `CompletableFuture.supplyAsync` bọc quanh `jmsTemplate.convertAndSend` là **offload đồng bộ sang thread pool ứng dụng**, khác bản chất JMS native async send.
- `@JmsListener` dùng cho **nhận** message bất đồng bộ, không thay cho `CompletionListener` của **gửi**.

Ví dụ tích hợp Spring ở mức thấp (không phải ví dụ non-blocking khuyến nghị):

```java
jmsTemplate.execute((SessionCallback<Void>) session -> {
    try (MessageProducer producer =
                 session.createProducer(session.createQueue("orders.queue"))) {
        TextMessage message =
                session.createTextMessage("order-42");
        producer.send(message, completionListener);
    }
    return null;
});
```

Đây là snippet có sẵn `jmsTemplate`, `completionListener` và các import. `MessageProducer.close()` ở cuối callback có thể **đợi callback hoàn thành**, do đó không nên hứa request sẽ trả về trước khi gửi xong. Chỉ dùng khi hiểu lifecycle/performance và bảo đảm transaction manager không bị vượt qua.

## 11. Hiệu năng, backpressure và quản lý tải

Async send hữu ích khi **latency chờ acknowledgement** đang chiếm phần lớn thời gian của caller. Nhưng nếu ứng dụng có thể phát message nhanh hơn broker xử lý, hàng đợi in-flight sẽ lớn dần. Không có `CompletionListener` nào tự giới hạn số yêu cầu đang chờ.

Các nguyên tắc thực tế:

1. **Giới hạn in-flight:** dùng `Semaphore` hoặc một hàng đợi nội bộ có sức chứa hữu hạn. Chỉ mở thêm send khi số chưa hoàn tất thấp hơn ngưỡng. Khi callback xong, giải phóng permit ở mã thread-safe.
2. **Đo callback latency:** tính thời gian từ trước `send` đến callback; dùng percentiles (p50/p95/p99), không chỉ thời gian `send` trả về.
3. **Tách hai counters:** số invocation `send` trả về và số `onCompletion` thành công; hai số có thể khác nhau tại thời điểm quan sát.
4. **Giám sát lỗi đồng bộ và bất đồng bộ:** đếm riêng `send` ném exception, `onException`, timeout của Future/latch và lỗi broker disconnect.
5. **Không block lâu trong callback:** tránh gọi database/HTTP hoặc giữ khóa trong callback. Provider có thể tuần tự hóa callback của cùng session; callback chậm gây ảnh hưởng hiệu năng và `close`.
6. **Tính toàn bộ lifecycle:** đo `close()` và `commit()`; gửi nhanh trong vòng `for` nhưng đợi rất lâu ở close chưa chắc cải thiện throughput.
7. **Giữ eventId bất biến:** khi có lỗi mơ hồ, retry cần kết hợp idempotency, không chỉ phát lại cùng message mà không phân biệt lần thử.
8. **Tối ưu sau khi đo:** JMS persistent/non-persistent, batch size, TTL, broker paging, socket timeout và session caching có thể ảnh hưởng lớn hơn lựa chọn API callback.

### Ví dụ kiến trúc backpressure

```text
Request / event source
      |
      +--> acquire permit (tối đa N in-flight)
               |
               +--> producer.send(message, listener)
                          |
                          +--> callback success: cập nhật result, release permit
                          |
                          +--> callback failure: cập nhật failure, release permit
               |
               +--> exception đồng bộ: release permit ngay, không chờ callback
```

Nếu dùng semaphore thật, phải bảo đảm **mỗi invocation release đúng một lần**, kể cả `send` ném lỗi trực tiếp. Không được release thêm trong callback nếu invocation đã ném lỗi trực tiếp; spec bảo đảm callback không chạy cho đường đó. Những lỗi khác (tạo message, tạo producer, đóng kết nối) cũng cần dọn tài nguyên/permit phù hợp.

## 12. Retry, duplicate và trạng thái không xác định

Giả sử lệnh async gửi `event-17`. Broker nhận message, nhưng đường mạng mất kết nối trước confirmation. `onException` có thể báo lỗi mặc dù broker đã có message. Nếu producer phát lại tự động `event-17`, downstream có thể thấy hai message cùng eventId.

Một thiết kế thực tế:

- Mỗi sự kiện có `eventId` duy nhất, bền vững, không đổi qua các lần retry.
- Người nhận có bảng/dedup store hoặc logic idempotency để không thực hiện tác dụng phụ hai lần.
- Áp dụng retry giới hạn, exponential backoff có jitter và phân loại lỗi.
- Theo dõi trạng thái `PENDING`, `ACKNOWLEDGED`, `FAILED`/`UNKNOWN` với policy reconciliation; không tự coi timeout là “chắc chắn thất bại”.
- Nếu phát message là một phần của transaction database, cân nhắc **transactional outbox** và background publisher bền vững.
- Khi event có TTL, kiểm tra deadline trước khi retry; gửi lại thông điệp đã hết ý nghĩa có thể gây tác dụng phụ không mong muốn.

Lưu ý `onCompletion` không phải chứng nhận consumer đã ack. Consumer có thể nhận message rồi rollback, broker redeliver, và ứng dụng cần idempotent logic ngay cả khi gửi một lần.

## 13. Các lỗi phổ biến và cách sửa

| Lỗi | Hậu quả | Hướng sửa |
| --- | --- | --- |
| Coi `send(..., listener)` trả về là gửi xong | Trả HTTP 200/commit business state quá sớm | Chỉ khẳng định mức bảo đảm gửi khi có `onCompletion` hoặc transaction commit phù hợp. |
| Chỉ bắt `onException`, quên catch lỗi đồng bộ | Latch/Future không hoàn tất, yêu cầu treo | Bắt `JMSException`/unchecked ở `send` và signal ngay trong `catch`. |
| Đóng producer/session trong callback | Vi phạm JMS; bị `IllegalStateException` hoặc deadlock-like failure | Để owner bên ngoài callback thực hiện cleanup. |
| Đóng ngay sau `send` rồi gọi đó là “hoàn toàn non-blocking” | `close` có thể đợi callback, mất lợi ích async | Thiết kế lifetime resource phù hợp hoặc chấp nhận mẫu await rõ ràng. |
| Đọc/sửa `Message` ngay sau `send` trước callback | Undefined behavior, provider có thể ném lỗi | Mỗi in-flight send dùng message riêng; đợi callback mới đọc headers. |
| Đọc JMS headers trong `onException` rồi coi là chắc chắn | Trạng thái headers do provider set có thể undefined | Log eventId lưu riêng thay vì dựa vào JMSMessageID trong thất bại. |
| Callback gọi cùng `Session` trong lúc thread khác dùng | Vi phạm threading restriction | Callback chỉ cập nhật thread-safe state; không dùng Session. |
| Dùng `onCompletion` như “transaction committed” | Có thể callback trước `commit` | Commit đúng boundary; kiểm tra kết quả commit riêng. |
| Dùng `onCompletion` như “consumer processed once” | Duplicate/redelivery/DB failure vẫn xảy ra | Idempotent consumer, retries/DLQ, business ack riêng. |
| Chia sẻ một `JMSContext` mutable qua thread | Race/concurrency trên JMS session | Tạo context theo scope phù hợp hoặc dùng resource manager/pool đúng. |
| Chờ callback vô hạn trong request | Thread exhaustion khi broker lỗi | Timeout, bounded in-flight, circuit breaker và recovery policy. |
| Chặn callback bằng HTTP/DB | Provider callback thread bị giữ, ảnh hưởng throughput | Làm tối thiểu và chuyển xử lý nặng sang executor có giới hạn. |
| Dùng async send trong Jakarta EE web/EJB container | Vi phạm giới hạn API JMS | Chọn API và mô hình gửi được container hỗ trợ. |
| Coi timeout Future là hủy JMS send | Message có thể tiếp tục đến broker | Theo dõi kết quả trễ, reconciliation và idempotency. |
| Giữ payload lớn và vô hạn message in-flight | Tăng bộ nhớ và áp lực broker | Bounded queue/semaphore, giám sát heap và broker paging. |

## 14. Checklist kiểm thử

### 14.1. Happy path

- Khởi động broker Artemis, tạo `demo.async.queue` hoặc bật auto-create phù hợp.
- Chạy ví dụ với `MESSAGE_COUNT=3` và credentials đúng.
- Kiểm tra `sendCallsReturned=3` và `callbacksSucceeded=3` sau khi latch hoàn tất.
- Kiểm tra Queue thực tế có ba message hoặc consumer test nhận đúng ba message với property `eventId` lần lượt `event-1`, `event-2`, `event-3`. Nếu có consumer khác, không đo bằng pending count đơn thuần.
- Không thấy producer/session bị rò rỉ sau khi context shutdown.

### 14.2. Lỗi được ném trực tiếp

- Cấu hình một provider/connection không hợp lệ hoặc làm giả `MessageProducer` trong unit test để `send` ném exception ngay.
- Kiểm tra callback không chạy cho invocation lỗi trực tiếp và latch/future vẫn được signal từ `catch`.
- Xác minh code không đợi mãi vì callback không đến.

### 14.3. Lỗi đến trong onException

- Dùng môi trường integration test có thể tiêm lỗi transport/ack sau khi `send` đã trả về.
- Kiểm tra listener nhận lỗi, metrics failure tăng, log chứa eventId và ứng dụng không kết luận chắc chắn message vắng mặt ở broker.
- Tránh giả định mọi ngắt mạng đều kích hoạt một đường lỗi cố định; phụ thuộc thời điểm và provider.

### 14.4. Thread safety và message lifecycle

- Gửi nhiều message khác nhau trên cùng producer, nhưng gọi `send` từ **một thread theo session scope**; không chạy `parallelStream` trên cùng `Session`.
- Cố tình tắt thao tác đọc message trước callback trong test/code review; việc provider đôi khi không ném lỗi **không** chứng minh cách sử dụng hợp lệ.
- Đảm bảo callback không gọi `close/commit/rollback` của chính tài nguyên đang gửi.
- Đo callback latency và thứ tự callback của cùng producer; không suy ra thứ tự consumer xử lý.

### 14.5. Timeout, shutdown, commit

- Kiểm tra trường hợp callback đến trễ hơn `await` timeout: chương trình báo timeout nhưng close có thể vẫn đợi.
- Trong test riêng, sử dụng local transacted session; xác nhận `onCompletion` trước commit không làm message trở thành committed.
- Dừng ứng dụng khi có in-flight sends và kiểm tra graceful shutdown, timeout provider, broker state.
- Thử broker restart/HA theo hạ tầng thực và quan sát các send có trạng thái UNKNOWN/duplicate.

## 15. So sánh nhanh các cách làm trong Spring

| Kỹ thuật | Dùng cho | Thread chờ ở đâu? | Ai theo dõi kết quả? |
| --- | --- | --- | --- |
| `JmsTemplate.convertAndSend` | Gửi tiện lợi, thông thường là đồng bộ theo lời gọi | Thread gọi đợi operation của template | Exception đồng bộ từ template; transaction manager nếu có. |
| `MessageProducer.send(..., CompletionListener)` | JMS native async send | Thread gửi có thể tiếp tục; close/commit/await vẫn có thể chặn | `CompletionListener` + exception tại `send`. |
| `JMSProducer.setAsync(listener)` | Simplified Jakarta Messaging API | Tương tự, cần quản lý `JMSContext` | `CompletionListener` + `JMSRuntimeException`. |
| `@Async` bọc `JmsTemplate` | Offload thao tác template đồng bộ sang application executor | Một thread trong executor có thể bị block | Spring `Future`/`CompletableFuture`; vẫn phải quản lý executor. |
| `@JmsListener` | Nhận/tiêu thụ message bất đồng bộ | Listener container dùng worker threads | Listener container, acknowledge/transaction/retry. |
| `JmsTemplate` + `JmsTransactionManager` | Gửi JMS transaction an toàn và rõ ràng | Caller/transaction boundary đợi commit | Transaction manager, exception/rollback. |

Chọn `CompletionListener` nếu mục tiêu thực sự là giảm việc caller chờ confirmation gửi và có thiết kế in-flight/recovery đủ chặt chẽ. Nếu mục tiêu chỉ là “đừng chặn HTTP request”, có thể cần outbox hoặc background publisher bền vững thay vì chuyển toàn bộ rủi ro sang callback.

## 16. Câu hỏi tự kiểm tra

**1.** Sau khi `producer.send(message, listener)` trả về bình thường, có được coi message đã gửi thành công với đầy đủ mức bảo đảm của synchronous send chưa?

**Không.** Phải đợi `onCompletion` cho mức bảo đảm tương ứng, trừ khi có quy trình xác nhận riêng do provider/transaction cung cấp.

**2.** Nếu `send` ném `JMSException` ngay, `onException` có bắt buộc được gọi sau đó không?

**Không; ngược lại, provider không được gọi callback cho invocation đã ném exception trực tiếp.** Ứng dụng tự xử lý lỗi trong `catch`.

**3.** Có được gọi `producer.close()` trong `onCompletion` của chính producer không?

**Không.** Điều đó vi phạm contract. Owner khác đóng tài nguyên ngoài callback.

**4.** Vì sao `CompletionListener` không đồng nghĩa consumer xử lý đúng một lần?

Vì callback báo kết quả **phát** message, không phải acknowledgement/transaction của consumer. Redelivery và duplicate nghiệp vụ vẫn có thể xảy ra.

**5.** Trong local transacted session, `onCompletion` chạy thì message đã commit chưa?

**Chưa chắc.** Cần `session.commit()` thành công hoặc transaction manager commit; callback không thay thế commit.

**6.** Có thể dùng cùng `Message`, thay body ngay sau lần gửi async đầu rồi gửi lần hai không?

**Không.** Không đọc/chỉnh sửa `Message` đang in-flight trước callback; dùng object riêng.

**7.** Lý do `CompletionListener` không tự động cải thiện latency khi gọi bên trong `JmsTemplate.execute` rồi rời callback là gì?

Vì template/producer cleanup có thể gọi `close()`; theo spec, `close` phải chờ các async send/callback chưa hoàn tất. Cần thiết kế vòng đời resource rõ ràng, không chỉ chọn overload async.

## Kết luận

`CompletionListener` là cơ chế **asynchronous send ở tầng Jakarta Messaging**, cho phép provider thông báo thành công hoặc lỗi sau khi caller phát lệnh gửi. Kết quả cần được xử lý qua **hai đường**: lỗi trực tiếp từ `send` và callback `onCompletion`/`onException`. Callback thành công chỉ đạt mức bảo đảm của send tương đương, không chứng minh consumer đã xử lý hay transaction database đã commit.

Trong Spring, bạn có thể dùng JMS API gốc qua `ConnectionFactory` hoặc `SessionCallback`, nhưng phải lưu ý vòng đời của template và quy tắc `close/commit` chờ callback. Với hệ thống production, bổ sung idempotency, bounded in-flight, metrics/timeout và chính sách retry. Không dùng async send trong Jakarta EE web/EJB container nếu môi trường đó tuân theo hạn chế của đặc tả Jakarta Messaging 3.1.

## Tài liệu tham khảo

- Jakarta Messaging 3.1 Specification — phần 7.3 *Asynchronous send*, quality of service, exceptions, ordering, threading, close/commit/rollback: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Jakarta Messaging 3.1 API — `CompletionListener`: https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/completionlistener
- Jakarta Messaging 3.1 API — `MessageProducer`, các overload `send(..., CompletionListener)`: https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageproducer
- Jakarta Messaging 3.1 API — `JMSProducer` và `setAsync`: https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/jmsproducer
- Spring Framework — Sending a message, `JmsTemplate` và callbacks: https://docs.spring.io/spring-framework/reference/integration/jms/sending.html
- Spring Framework — Using Spring JMS: https://docs.spring.io/spring-framework/reference/integration/jms/using.html
- Spring Framework — `JmsTemplate` Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/core/JmsTemplate.html
- Spring Boot — Artemis/JMS integration: https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html
- Apache ActiveMQ Artemis — Using JMS: https://artemis.apache.org/components/artemis/documentation/latest/using-jms