# CompletionListener xác nhận thao tác gửi khác với hoàn tất tiêu thụ (Spring JMS)

## 1. Bài toán: gửi thành công có nghĩa là gì?

Dịch vụ đặt hàng gửi sự kiện `OrderCreated(order-42)` vào queue JMS. Sau khi gọi gửi, ứng dụng muốn trả kết quả cho người dùng. Tuy nhiên, có ít nhất bốn mốc khác nhau:

1. **Yêu cầu gửi được khởi tạo:** producer gọi API `send`.
2. **Thao tác gửi được xác nhận:** JMS provider báo rằng lần gửi đã thành công với mức bảo đảm tương đương một lần gửi đồng bộ của cùng provider.
3. **Consumer nhận message:** JMS provider chuyển message đến một consumer đủ điều kiện.
4. **Nghiệp vụ hoàn tất:** phía nhận xử lý và commit thay đổi trạng thái nghiệp vụ (nếu nghiệp vụ có transaction).

`jakarta.jms.CompletionListener` cung cấp tín hiệu ở **mốc 2** cho cơ chế **asynchronous send**, không phải tín hiệu cho mốc 3 hay 4.

Ví dụ: producer gửi `OrderCreated` và nhận `onCompletion` ngay cả khi không có consumer online, miễn broker/provider chấp nhận message theo cấu hình hiện có. Một consumer cũng có thể nhận message sau đó nhưng xử lý thất bại và bị redelivery. Cả hai tình huống vẫn tương thích với việc phía gửi đã được `onCompletion` báo thành công.

Hệ quả thực tế: nếu HTTP API trả về `"đơn hàng đã được xử lý"` ngay từ `onCompletion`, phản hồi đó có thể **không đúng với trạng thái bên nhận**. Nếu cần biết nghiệp vụ đã xong, phải thiết kế một tín hiệu xác nhận khác từ consumer hoặc hệ thống sở hữu nghiệp vụ.

**Mục tiêu bài học:** hiểu rõ `CompletionListener`, cơ chế gửi bất đồng bộ, hai callback thành công/lỗi, cách dùng bên cạnh Spring `JmsTemplate`, giới hạn threading/transaction/lifecycle, và thiết kế xác nhận nghiệp vụ đúng.

## 2. API CompletionListener

`CompletionListener` thuộc Jakarta Messaging (có từ JMS 2.0). Trong Spring Boot 3.x/Spring Framework 6.x, import thuộc namespace `jakarta.jms`:

```java
package jakarta.jms;

public interface CompletionListener {
    void onCompletion(Message message);
    void onException(Message message, Exception exception);
}
```

Đây là **chữ ký minh họa API**, không phải một class phải tự viết lại.

| Callback | Điều nó xác nhận | Điều nó không xác nhận |
| --- | --- | --- |
| `onCompletion(Message)` | Thao tác **gửi** đã hoàn tất thành công theo mức bảo đảm của provider | Consumer đã nhận, ACK, hoàn tất logic, commit database |
| `onException(Message, Exception)` | Provider phát hiện lỗi khi gửi mà không thể ném ngay trong lời gọi `send` | Message chắc chắn chưa từng được broker nhận |
| Exception ném trực tiếp từ `send` | Thao tác gặp lỗi ngay ở thread gọi | Provider cũng sẽ gọi `onException` sau đó |

Theo Jakarta Messaging 3.1 `7.3.1–7.3.2`, khi `send` phát sinh một lỗi có thể ném ngay trong thread gọi, provider phải ném lỗi ở đó và **không gọi** `onCompletion` hoặc `onException` cho cùng lần gửi. Khi lỗi được phát hiện sau khi `send` đã trả về, provider gọi `onException`.

Chuẩn cũng ghi rõ: **nếu có exception trong quá trình gửi, không xác định được chắc chắn message đã gửi thành công hay chưa**. Có thể broker đã nhận message trước khi kết nối mạng gặp sự cố làm mất xác nhận. Vì vậy `onException` và timeout không tự động có nghĩa `NOT_SENT`.

### Trạng thái nên tách biệt

| Trạng thái ứng dụng | Nguồn bằng chứng |
| --- | --- |
| `SEND_REQUESTED` | Ứng dụng đã yêu cầu producer gửi |
| `SEND_PENDING` | Chưa có kết quả xác nhận gửi |
| `SEND_CONFIRMED` | `onCompletion` đã được gọi |
| `SEND_UNCERTAIN` | Exception/timeout không đủ chứng minh broker đã nhận hay chưa |
| `CONSUMER_RECEIVED` | Theo dõi từ phía nhận (listener/tracing) |
| `BUSINESS_COMPLETED` | Bằng chứng nghiệp vụ đã commit theo hợp đồng hai hệ thống |

Các tên trạng thái trên là **quy ước ứng dụng**, không phải enum có sẵn của Jakarta Messaging. Không gộp `SEND_CONFIRMED` vào `BUSINESS_COMPLETED`.

## 3. Asynchronous send và vị trí của callback

Jakarta Messaging cung cấp hai cách chính để đăng ký `CompletionListener`:

- **Classic API:** các overload của `jakarta.jms.MessageProducer.send(...)` nhận thêm `CompletionListener`.
- **Simplified API:** gọi `jakarta.jms.JMSProducer.setAsync(listener)` rồi `send(destination, ...)`.

Ví dụ classic API, **đoạn trong một method đã có `MessageProducer producer` và `Message message` hợp lệ**:

```java
producer.send(message, new jakarta.jms.CompletionListener() {
    @Override
    public void onCompletion(jakarta.jms.Message sent) {
        System.out.println("SEND_CONFIRMED");
    }

    @Override
    public void onException(
            jakarta.jms.Message attempted, Exception failure) {
        System.err.println("SEND_UNCERTAIN: "
                + failure.getClass().getSimpleName());
    }
});
```

Ví dụ simplified API, **đoạn có sẵn `JMSContext context`, `Destination queue` và `CompletionListener listener`**:

```java
context.createProducer()
        .setAsync(listener)
        .send(queue, context.createTextMessage("OrderCreated:order-42"));
```

Sơ đồ thời gian:

```text
Producer thread                   JMS provider                    Consumer
---------------                   ------------                    --------
send(message, listener)  -------> bắt đầu xử lý gửi
send() trả về                    ... xác nhận thao tác gửi ...
ứng dụng tiếp tục                gọi onCompletion()
hoặc chủ động chờ                hoặc onException()                 |
                                                                   có thể chưa online,
                                                                   nhận trễ, rollback,
                                                                   xử lý thất bại...
                                                                   |
                                                              business commit?
```

Provider quyết định bao nhiêu công việc chạy trước khi `send` trả về và bao nhiêu công việc chạy nền. Callback phải chạy trong **thread khác thread gọi asynchronous `send`**, nhưng không được suy ra rằng callback luôn chạy sau mọi dòng log đặt ngay phía sau `send`: các thread có thể tranh lịch rất sát nhau.

**Mức tin cậy của `onCompletion`:** Jakarta Messaging xác định callback chỉ được gọi khi gửi thành công với mức tin cậy **giống gửi đồng bộ của cùng provider**. Điều này không tự nâng non-persistent thành persistent, không xác minh transaction nghiệp vụ và không ngầm tạo cơ chế request/reply tới consumer.

## 4. CompletionListener khác callback của Spring JmsTemplate

`JmsTemplate` là API tiện ích của Spring JMS. Ví dụ:

```java
jmsTemplate.send("orders.in", session ->
        session.createTextMessage("OrderCreated:order-42"));
```

Tham số lambda ở đây là **`org.springframework.jms.core.MessageCreator`**. Spring cung cấp `Session` để ứng dụng tạo một JMS `Message` rồi `JmsTemplate` thực hiện gửi. Đây **không phải** completion callback.

| API | Callback nhận gì? | Dùng để làm gì? |
| --- | --- | --- |
| `JmsTemplate.send(..., MessageCreator)` | `Session` do template cấp | Tạo `TextMessage`, `MapMessage`, gắn properties/headers trước khi gửi |
| `JmsTemplate.convertAndSend(..., MessagePostProcessor)` | `Message` đã được convert | Chỉnh message trước khi gửi |
| `JMSProducer.setAsync(CompletionListener)` | `Message` thành công hoặc `Message + Exception` thất bại | Quan sát kết quả asynchronous send |
| `@JmsListener` | Payload/`Message` được phía consumer nhận | Chạy logic nhận và xử lý phía consumer |

`JmsTemplate.send(String, MessageCreator)` là method `void`, không có tham số `CompletionListener` trong API thông thường của Spring Framework 6.2. Nếu muốn dùng chính Jakarta Messaging asynchronous send, có thể inject `ConnectionFactory` do Spring Boot cấu hình và tạo `JMSContext`/`JMSProducer` như ví dụ bên dưới.

**Hai lưu ý:**

1. Bọc `jmsTemplate.send(...)` trong một method Spring `@Async` chỉ đưa lời gọi template sang một worker thread. Future trả về của method đó biểu diễn **lời gọi gửi kết thúc**, không trở thành `CompletionListener` hay thông báo consumer đã xử lý.
2. Không tự đưa asynchronous `MessageProducer.send(..., CompletionListener)` vào `JmsTemplate.execute(...)` rồi để callback thoát khỏi vòng đời tài nguyên do template quản lý. Việc đóng producer/session có quy tắc chờ callback, nên phải thiết kế rõ ownership và completion.

Nếu ứng dụng chỉ cần gửi thông thường, `JmsTemplate` có thể đủ. Chỉ bổ sung asynchronous send callback khi thực sự cần theo dõi ranh giới send completion mà API đồng bộ không thể hiện theo cách mong muốn.

## 5. Ví dụ đầy đủ: Spring Boot 3.x/Java 17+ và JMSProducer.setAsync

Ví dụ tạo một ứng dụng **Spring Boot chạy standalone như Java SE client**, kết nối ActiveMQ Artemis đã chạy ở `tcp://localhost:61616`. Giả định broker có queue `orders.in` và tài khoản ứng dụng có quyền send. Đây là ví dụ phụ thuộc Spring Boot/Jakarta JMS provider, **không phải chương trình Java SE độc lập chỉ chạy bằng `javac`**.

Ví dụ **chủ động đợi `onCompletion`** để người học quan sát khác biệt giữa `send()` trả về và gửi được xác nhận. Method này đợi kết quả nên không được quảng bá như API hoàn toàn non-blocking.

### 5.1. Dependency

Trong `build.gradle` của project Spring Boot Groovy DSL đã cấu hình plugin Boot và dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
}
```

Spring Boot 3.x sử dụng namespace `jakarta.jms`; không trộn `javax.jms` cũ.

### 5.2. application.yml

File `src/main/resources/application.yml`:

```yaml
spring:
  artemis:
    mode: native
    broker-url: "${JMS_BROKER_URL:tcp://localhost:61616}"
    user: "${JMS_USER}"
    password: "${JMS_PASSWORD}"

app:
  jms:
    queue: "${JMS_QUEUE_NAME:orders.in}"
```

Cung cấp biến môi trường `JMS_USER`, `JMS_PASSWORD`; chỉ đặt thông tin đăng nhập thật trong cấu hình quản lý secrets. Nếu có nhiều broker/môi trường, đặt đúng `JMS_BROKER_URL` và `JMS_QUEUE_NAME`. Tên queue không tự chứng minh tài nguyên vật lý đã được provision.

### 5.3. Service tạo JMSContext và CompletionListener

File `src/main/java/demo/jms/AsyncOrderPublisher.java`:

```java
package demo.jms;

import jakarta.jms.CompletionListener;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSContext;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

@Service
public class AsyncOrderPublisher {
    private final ConnectionFactory connectionFactory;
    private final String queueName;

    public AsyncOrderPublisher(
            ConnectionFactory connectionFactory,
            @Value("${app.jms.queue}") String queueName) {
        this.connectionFactory = connectionFactory;
        this.queueName = queueName;
    }

    public void sendAndWait(String orderId, String eventId)
            throws Exception {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId is blank");
        }
        if (eventId == null || eventId.isBlank()) {
            throw new IllegalArgumentException("eventId is blank");
        }

        CompletableFuture<Void> sendFinished = new CompletableFuture<>();

        try (JMSContext context =
                     connectionFactory.createContext(JMSContext.AUTO_ACKNOWLEDGE)) {
            Queue queue = context.createQueue(queueName);
            TextMessage message =
                    context.createTextMessage("OrderCreated:" + orderId);
            message.setStringProperty("eventId", eventId);

            CompletionListener listener = new CompletionListener() {
                @Override
                public void onCompletion(Message sent) {
                    sendFinished.complete(null);
                }

                @Override
                public void onException(
                        Message attempted, Exception failure) {
                    sendFinished.completeExceptionally(failure);
                }
            };

            context.createProducer()
                    .setAsync(listener)
                    .send(queue, message);

            System.out.println("send() đã trả về");
            sendFinished.get(10, TimeUnit.SECONDS);
            System.out.println("onCompletion xác nhận gửi thành công");
        }
    }
}
```

Giải thích từng phần:

1. `ConnectionFactory` do Spring Boot cung cấp; service tạo `JMSContext` riêng cho lần thử, không chia sẻ context/session giữa các thread.
2. `context.createQueue(queueName)` tạo đối tượng JMS mô tả queue. Broker có thể yêu cầu queue đã được tạo trước; gọi method này không phải chuẩn để provision queue vật lý.
3. `TextMessage` mang body `OrderCreated:order-42` và property `eventId` được ứng dụng đặt trước khi send.
4. `setAsync(listener)` đăng ký callback. `onCompletion` hoàn tất `CompletableFuture`; `onException` báo lỗi qua `completeExceptionally`.
5. `sendFinished.get(10, TimeUnit.SECONDS)` buộc thread demo **chờ kết quả gửi**. `ExecutionException` có thể biểu diễn exception callback, còn `TimeoutException` có nghĩa thời hạn đợi callback đã hết: **trạng thái gửi lúc đó chưa xác định**.
6. `try-with-resources` đóng `JMSContext`. Theo Jakarta Messaging `7.3.4`, đóng context/producer/session/connection phải chờ những asynchronous sends chưa xong và callbacks trở về; timeout 10 giây của `get` **không là hạn cuối toàn bộ method**. Không dùng pattern này để hứa một request HTTP sẽ luôn kết thúc sau 10 giây.

Không gọi `context.close()`, `commit()`, `rollback()` ngay trong callback. Không đọc hoặc sửa `message` từ thread gọi trong lúc async send còn dở.

### 5.4. Lớp chạy thử

File `src/main/java/demo/jms/AsyncSendApplication.java`:

```java
package demo.jms;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Profile;

@SpringBootApplication
public class AsyncSendApplication {
    public static void main(String[] args) {
        SpringApplication.run(AsyncSendApplication.class, args);
    }

    @Bean
    @Profile("completion-demo")
    ApplicationRunner demo(AsyncOrderPublisher publisher) {
        return args -> publisher.sendAndWait(
                "order-42", "event-order-42-created");
    }
}
```

Khởi động broker có queue `orders.in` và thông tin truy cập phù hợp, rồi chạy trong project có task `bootRun`:

```bash
./gradlew bootRun --args='--spring.profiles.active=completion-demo'
```

Nếu `send` và callback đều thành công, hai dòng **do code ứng dụng in** sẽ xuất hiện theo thứ tự sau (ngoài các log khác của Spring Boot):

```text
send() đã trả về
onCompletion xác nhận gửi thành công
```

Do hai lệnh `println` đều nằm trong thread gọi, dòng thứ hai chỉ xuất hiện sau khi `CompletableFuture` được hoàn tất thành công. Provider có thể gọi callback trước hoặc sau thời điểm dòng đầu được in; mã trên không áp đặt thứ tự thread callback, chỉ áp đặt thứ tự **hai dòng của ứng dụng**.

Nếu `send(...)` ném exception ngay thì có thể không có dòng đầu. Nếu callback báo lỗi hoặc đợi timeout thì dòng thứ hai không xuất hiện. **Không có consumer trong project này**, nhưng producer vẫn có thể được xác nhận đã gửi nếu broker chấp nhận message: đó chính là điểm cần quan sát.

Đừng bật profile `completion-demo` trong production vì mỗi lần khởi động nó sẽ cố gửi thêm event cùng ID.

### 5.5. Listener tùy chọn để thấy mốc nhận

Nếu muốn kiểm tra rõ hơn mốc nhận, thêm vào chính project một consumer:

```java
package demo.jms;

import org.springframework.context.annotation.Profile;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
@Profile("consumer-demo")
public class OrderConsumer {
    @JmsListener(destination = "${app.jms.queue}")
    public void receive(String body) {
        System.out.println("consumer đã nhận: " + body);
    }
}
```

Lưu file trên tại `src/main/java/demo/jms/OrderConsumer.java` và thêm `@EnableJms` (import `org.springframework.jms.annotation.EnableJms`) vào class `AsyncSendApplication` để bật annotation listener một cách tường minh. Khi bật `consumer-demo`, listener có thể in:

```text
consumer đã nhận: OrderCreated:order-42
```

Dòng này là dấu hiệu **method consumer được gọi**. Nó không chứng minh consumer đã commit transaction nghiệp vụ; ví dụ thậm chí chưa có database. Nếu chạy đồng thời hai profile `completion-demo,consumer-demo`, log producer và consumer có thể xen kẽ theo nhiều thứ tự; không dùng thứ tự log làm hợp đồng bảo đảm của JMS.

## 6. Ba kiểu kết quả gửi và cách xử lý lỗi

### 6.1. onCompletion: một tín hiệu dương cho send

Khi provider gọi `onCompletion(message)`, ứng dụng có thể ghi trạng thái `SEND_CONFIRMED` cho một event có ID bất biến. Có thể đo độ trễ từ `sendRequestedAt` tới `sendConfirmedAt` để theo dõi chất lượng hạ tầng gửi. **Không** tăng bộ đếm `business_completed` tại đây.

### 6.2. onException: kết quả lỗi nhưng có thể mơ hồ

Giả sử broker đã nhận event `E-901` nhưng đường kết nối bị cắt trước khi producer nhận được xác nhận. Một exception có thể xuất hiện, trong khi message vẫn đã tới broker. Đặc tả không cho phép ứng dụng kết luận chắc chắn “message chưa gửi”.

Vì vậy, khi quyết định retry:

- Giữ cùng `eventId` cho cùng một ý định nghiệp vụ.
- Đặt retry/backoff và giới hạn số lần thử; giám sát trường hợp trạng thái không xác định.
- Consumer dùng cơ chế idempotency hoặc inbox/deduplication để xử lý event trùng.
- Khi cần kết hợp thay đổi database với publication, xem xét transactional outbox và quy trình reconciliation; không tự cho rằng lỗi send đồng nghĩa an toàn khi phát lại không kiểm soát.

### 6.3. Exception từ lời gọi send

Nếu `send(...)` ném lỗi ngay (ví dụ không tạo được producer/destination hoặc kết nối bị lỗi sớm), callback **không cần và không được** gọi cho cùng lỗi đó theo quy tắc `7.3.2`. Mã ứng dụng cần bắt exception ở **lời gọi send** nếu muốn ghi nhận/điều phối lỗi.

Trong simplified API, các thao tác có thể ném `JMSRuntimeException`; lúc gọi các setter của `TextMessage` cũng có thể gặp checked `JMSException`. Trong code demo, method khai báo `throws Exception` để Runner hiển thị lỗi khởi động; ứng dụng thật nên phân loại rõ lỗi transient/permanent và trạng thái không xác định.

## 7. CompletionListener và transaction

Trong local JMS transaction, callback có thể xảy ra khi thao tác send đã hoàn tất nhưng transaction **chưa commit**. Đặc tả Jakarta Messaging `7.3.4` yêu cầu `commit()`/`rollback()` đợi asynchronous sends chưa xong và callbacks hoàn tất trước khi xử lý transaction.

```text
begin local JMS transaction
     |
     +-- async send(message, listener)
     |        |
     |        +-- onCompletion => đã hoàn tất thao tác gửi
     |
     +-- commit() hoặc rollback()
              |
              +-- outcome của transaction JMS
```

`onCompletion` không đồng nghĩa `commit`. Nếu transaction rollback, hiệu lực của message thay đổi theo transaction. Nếu commit thất bại hoặc kết nối lỗi, cần đánh giá riêng outcome và khả năng retry.

- Không gọi `close`, `commit`, `rollback` từ chính callback.
- `@Transactional` trong Spring chỉ có ý nghĩa dựa trên transaction manager đang sử dụng; một transaction database và một transaction JMS không mặc nhiên atomic.
- Nếu cần bảo đảm dữ liệu database và publication phối hợp an toàn, thiết kế outbox/XA hoặc cơ chế khác theo yêu cầu. Đây là giới hạn kiến trúc, không giải quyết được bằng việc chỉ đăng ký `CompletionListener`.

## 8. Threading, quyền sở hữu Message và vòng đời JMSContext

### 8.1. Callback chạy trên thread khác

Jakarta Messaging yêu cầu provider **không** gọi callback trên chính thread gọi asynchronous `send`. Một `Session` chỉ gọi một callback tại một thời điểm; các callbacks trên cùng `MessageProducer` hoặc `JMSContext` phải được gọi theo thứ tự các lời gọi asynchronous send tương ứng.

Tuy nhiên, thứ tự callbacks cùng producer **không phải** thứ tự consumer hoàn tất nghiệp vụ. Trong hệ thống có nhiều consumer, message có thể được xử lý song song hoặc redeliver.

Callback nên làm việc ngắn: ghi nhận kết quả theo `eventId`, hoàn tất một future hoặc chuyển sự kiện trạng thái cho thành phần xử lý khác. Không chạy tác vụ I/O chậm hay thao tác broker phức tạp ngay trên thread callback.

### 8.2. Không đọc Message khi asynchronous send còn dở

Sau khi `send` trả về và trước khi `CompletionListener` được gọi, code **không được đọc/sửa headers, properties hoặc body của chính đối tượng `Message` đang gửi**, vì provider có thể đang thay đổi nó ở thread khác. Đặc tả `7.3.9` quy định nếu truy cập sớm thì provider có thể ném `JMSException`; nếu không ném, hành vi không được xác định.

Sau `onCompletion`, các provider-generated header như `JMSMessageID` mới có thể được truy cập theo điều kiện API. Sau `onException`, trạng thái header/property do provider đặt có thể không xác định. Do đó, trong ứng dụng thực tế nên giữ `eventId` là dữ liệu bất biến độc lập với object `Message`.

### 8.3. Không chia sẻ Session tùy tiện

`Session` không được dùng đồng thời bởi nhiều thread theo quy tắc Jakarta Messaging. `CompletionListener` không được dùng `Session` nếu application thread có thể vẫn đang dùng nó. Không giữ một `JMSContext` trong field singleton rồi sử dụng đồng thời từ nhiều request mà không có thiết kế đồng bộ và lifecycle rõ ràng.

### 8.4. close() có thể đợi callbacks

Khi ứng dụng đóng producer/session/connection hoặc `JMSContext`, provider phải chờ các send chưa hoàn tất và callbacks trả về. Đó là lý do code dưới đây **không bảo đảm fire-and-forget không block**:

```java
try (JMSContext context = connectionFactory.createContext()) {
    context.createProducer()
            .setAsync(listener)
            .send(queue, message);
}
// close() phải chờ các send/callback chưa hoàn tất.
```

Đây chỉ là **đoạn minh họa lifecycle**, giả định biến `connectionFactory`, `listener`, `queue`, `message` đã được cấu hình đúng; không phải chương trình độc lập. Với hệ thống cần throughput cao, hãy có một thành phần chịu trách nhiệm giữ context/producer còn sống, theo dõi các sends đang pending, shutdown có kiểm soát và backpressure. Đừng trả về future cho caller rồi đóng context ngay mà mong công việc JMS vẫn tiếp tục độc lập theo ý mình.

### 8.5. Giới hạn trong Jakarta EE container

Theo Jakarta Messaging `7.3.5`, asynchronous send với `CompletionListener` **không được phép** trong Jakarta EE web container hoặc Enterprise Beans container. Provider có thể ném `JMSException`/`JMSRuntimeException` ở các API liên quan. Ví dụ trong mục 5 là Spring Boot chạy standalone kiểu Java SE. Nếu triển khai WAR/EJB trong application server Jakarta EE, phải kiểm tra ràng buộc container và cách gửi phù hợp; không copy tùy tiện `setAsync(listener)` vào EJB hoặc servlet Jakarta EE.

## 9. Muốn biết consumer hoàn tất: tạo một giao thức kết quả riêng

Giả sử Order Service cần biết Inventory Service đã trừ tồn kho, **commit database**, và công khai kết quả. Luồng mong muốn:

```text
Order Service                    Broker                   Inventory Service
-------------                    ------                   -----------------
send eventId=E-901 -----------> queue orders.in
onCompletion
  => SEND_CONFIRMED
                                  ---------------------> consume E-901
                                                        kiểm tra idempotency
                                                        cập nhật tồn kho
                                                        COMMIT database
                                                        phát kết quả đã xử lý
                                  <--------------------- ProcessingCompleted(E-901)
nhận ProcessingCompleted(E-901)
đối chiếu eventId
  => BUSINESS_COMPLETED
```

Đây là luồng **kiến trúc do ứng dụng thiết kế**, không phải hành vi tự phát sinh từ `CompletionListener`. Tín hiệu kết quả chỉ đáng tin nếu được phát theo hợp đồng nhất quán với transaction phía nhận, ví dụ qua outbox sau khi business state đã commit.

Các lớp tín hiệu dễ bị nhầm:

| Tín hiệu | Bên tạo | Nó thực sự cho biết |
| --- | --- | --- |
| `onCompletion` | JMS provider phía producer | Send hoàn tất với mức bảo đảm đồng bộ tương đương |
| Broker enqueue/dequeue metrics | Broker | Hoạt động lưu/phân phối theo định nghĩa broker |
| JMS consumer ACK | Consumer/container/transaction phía nhận | Trạng thái acknowledgment của JMS, không mặc nhiên là business commit |
| `@JmsListener` chạy xong | Phía consumer | Method listener trở về; transaction/ACK còn tùy cấu hình |
| `ProcessingCompleted(eventId)` | Dịch vụ nghiệp vụ | Mốc hoàn tất theo hợp đồng mà dịch vụ đó công bố |

Nếu cần request/reply, sử dụng một response destination, `JMSCorrelationID` hoặc `eventId` để đối chiếu, và xử lý timeout, duplicate, reply trễ, cũng như phần xử lý đã commit nhưng phản hồi bị mất.

Đừng đồng nhất `JMSMessageID` do provider cấp khi gửi với `eventId` của nghiệp vụ: event có thể retry và nhận message ID khác, trong khi ý định nghiệp vụ vẫn là một.

## 10. Kiểm thử và quan sát vận hành

Kiểm thử nên tách **gửi thành công** khỏi **tiêu thụ hoàn tất**.

| Kịch bản | Bằng chứng nên thu thập | Kết luận |
| --- | --- | --- |
| Broker chạy, không có consumer | `onCompletion`, queue metrics | Gửi có thể hoàn tất khi chưa có consumer |
| Consumer xử lý chậm | Thời điểm send callback và thời điểm business commit | Hai mốc tách biệt |
| Consumer rollback/retry | Producer callback, consumer redelivery | Send success không bảo đảm business success |
| Mất mạng đúng thời điểm gửi | Exception/timeout và kiểm tra broker | Outcome có thể không xác định |
| Local JMS transaction rollback | Send callback và transaction outcome | `onCompletion` không thay thế commit |
| Nhiều message/consumer | Tracing bằng eventId và trạng thái từng event | Thứ tự callback không xác nhận thứ tự business completion |

### Unit test và integration test khác nhau thế nào?

Unit test có thể giả lập callback `onCompletion`/`onException` để xác minh logic cập nhật trạng thái phía producer. Điều đó **không kiểm tra** broker, provider threading, mức tin cậy send hoặc consumer processing.

Integration test cần broker thực, queue thử nghiệm và một consumer riêng. Chạy cả kịch bản consumer tắt, consumer thất bại, và callback lỗi. Dùng `CountDownLatch`/`CompletableFuture`, timeout có điều kiện và eventId; không phụ thuộc một `Thread.sleep(...)` tùy ý để kết luận "callback phải luôn chạy trước consumer".

Metrics hữu ích do ứng dụng tự đặt có thể là:

- `send_requested_total`: số yêu cầu publish.
- `send_confirmed_total`: số lần `onCompletion` thành công.
- `send_uncertain_total`: lỗi/timeout chưa chắc broker đã nhận.
- `consumer_received_total`: số lần nhận, có thể gồm redelivery.
- `business_completed_total`: số event đạt mốc nghiệp vụ đã commit.
- `send_confirmation_latency` và `business_completion_latency`: hai độ trễ khác nhau.

Không ghi payload nhạy cảm nguyên văn vào log callback. Sử dụng eventId, destination, thời điểm, exception class và correlation ID vừa đủ để điều tra.

## 11. Lỗi phổ biến

| Hiểu nhầm / sai lầm | Hậu quả | Sửa thế nào |
| --- | --- | --- |
| `onCompletion = consumer xử lý xong` | Báo trạng thái nghiệp vụ quá sớm | Theo dõi business reply/result sau commit |
| `send() trả về = send đã xác nhận` | Bỏ sót lỗi phát sinh sau | Dùng completion signal/đợi callback khi cần |
| `onException = chắc chắn chưa gửi` | Retry gây duplicate | Giữ eventId, dùng idempotency và trạng thái unknown |
| Gắn `CompletionListener` vào `JmsTemplate.send` như một `MessageCreator` | Nhầm API, mã không đúng | Phân biệt callback tạo message với callback báo send |
| `@Async` của Spring = asynchronous JMS send | Nhầm future method với JMS completion | Phân biệt worker thread và `JMSProducer.setAsync` |
| Đọc `Message` trước callback | Data race với provider | Chỉ đọc sau callback theo đặc tả |
| Đóng context rồi kỳ vọng không block | Provider phải chờ pending send/callback | Thiết kế lifecycle/shutdown |
| Gọi `close/commit/rollback` trong callback | Vi phạm quy tắc reentrancy | Quản lý tài nguyên/transaction ngoài callback |
| Xem `onCompletion` là transaction commit | Rollback/commit thất bại vẫn có thể xảy ra | Tách transaction outcome |
| Coi consumer ACK bằng DB commit | Trạng thái nghiệp vụ chưa chắc bền vững | Phản hồi sau commit/outbox phù hợp |
| Dùng async send trong Jakarta EE web/EJB container | API không được phép theo đặc tả | Tuân thủ container/provider |
| Timeout và retry mỗi lần với eventId mới | Có thể nhân đôi ý định nghiệp vụ | Giữ định danh ổn định, reconcile |

## 12. Tự kiểm tra

1. Ai gọi `CompletionListener.onCompletion`? Nó xác nhận mốc nào trong chuỗi producer → broker → consumer → database?
2. Nếu một queue không có consumer, producer có thể nhận `onCompletion` không? Điều kiện nào phụ thuộc broker/provider?
3. Nếu `send` ném exception trong thread gọi, có nên chờ thêm `onException` cho cùng lần gửi không?
4. Vì sao sau async `send` trả về, ứng dụng không được đọc/sửa object `Message` trước callback?
5. Tại sao `sendFinished.get(10, TimeUnit.SECONDS)` timeout không bảo đảm cả method kết thúc trong 10 giây?
6. Tại sao `onCompletion` trong local JMS transaction chưa đủ để chứng minh transaction đã commit?
7. Cần xây dựng tín hiệu gì nếu phía gửi muốn biết phía nhận đã cập nhật database thành công? Dùng `eventId` và idempotency để chống lỗi nào?

**Ghi nhớ:** `CompletionListener` chỉ xác nhận **kết quả thao tác asynchronous send** theo mức bảo đảm JMS provider. Nó không xác nhận consumer đã nhận, ACK hay commit nghiệp vụ. Khi cần trạng thái xử lý cuối, phải có một hợp đồng phản hồi riêng từ dịch vụ tiêu thụ.

### Tài liệu tham khảo

- Jakarta Messaging 3.1 Specification — `7.3 Asynchronous send`, `7.3.1–7.3.9` (exceptions, close/transaction, threading, message access, hạn chế Jakarta EE): https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Jakarta Messaging 3.1 API — `CompletionListener`: https://javadoc.io/static/jakarta.jms/jakarta.jms-api/3.1.0/jakarta.messaging/jakarta/jms/CompletionListener.html
- Jakarta Messaging 3.1 API — `MessageProducer`: https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageproducer
- Spring Framework 6.2 — Sending a Message, `JmsTemplate` và `MessageCreator`: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/sending.html
- Spring guide — Messaging with JMS: https://spring.io/guides/gs/messaging-jms/
