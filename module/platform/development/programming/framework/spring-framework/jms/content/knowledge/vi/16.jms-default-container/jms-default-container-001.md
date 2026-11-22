# DefaultMessageListenerContainer và cơ chế nhận dựa trên polling trong Spring JMS

## 1. Bài toán: vì sao cần một listener container?

Ứng dụng JMS thường phải nhận liên tục thông điệp từ Queue hoặc Topic, chuyển thành dữ liệu Java rồi gọi business handler. Nếu tự viết vòng lặp mở `Connection`, tạo `Session`, nhận message, ACK và reconnect, mỗi service sẽ phải tự giải quyết vòng đời tài nguyên, exception, concurrency và shutdown.

Spring Framework cung cấp `org.springframework.jms.listener.DefaultMessageListenerContainer` (viết tắt **DMLC**) để vận hành các bước đó. DMLC là một **message listener container**: ứng dụng chỉ định destination, consumer configuration và một listener; container tự đảm nhiệm việc đăng ký consumer, nhận JMS message, gọi handler, quản lý transaction, mở rộng số consumer và phục hồi kết nối.

Điểm quan trọng nhất của bài:

> **DMLC dùng vòng lặp `MessageConsumer.receive(...)` dạng blocking/polling từ các consumer task của Spring. Nó không đăng ký callback bằng `MessageConsumer.setMessageListener(...)` như `SimpleMessageListenerContainer`.**

Trong tài liệu Spring, DMLC được gọi là container dựa trên *polling*. Điều đó **không** có nghĩa mỗi 1.000 ms ứng dụng mới kiểm tra broker một lần. Khi một `receive(timeout)` đang chờ, message xuất hiện có thể đánh thức lời gọi **ngay khi provider chuyển được message**; timeout chỉ quy định thời gian chờ tối đa khi **chưa có message**.

Bài nằm trong nhóm **Default container** của Spring Framework – JMS. Bạn sẽ:
1. Phân biệt DMLC với `SimpleMessageListenerContainer` và `JmsTemplate.receive(...)`.
2. Hiểu chính xác receive loop, `receiveTimeout`, số lần receive trả `null`, consumer task và thread.
3. Cấu hình `DefaultJmsListenerContainerFactory` cho `@JmsListener` hoặc dùng bean DMLC trực tiếp.
4. Điều chỉnh `concurrentConsumers`, `maxConcurrentConsumers`, caching, idle/task scheduling và recovery.
5. Hiểu ảnh hưởng của local JMS transaction, XA/JTA, acknowledgment, Queue/Topic và durable subscriptions.
6. Chạy một project Java 17 + Spring Boot + Artemis embedded, xác nhận ứng dụng nhận ba message dù không tự viết vòng lặp polling.
7. Có checklist kiểm thử, chẩn đoán và vận hành production.

Các ví dụ chính dùng **Java 17+, Spring Framework 6.x, Spring Boot 3.x, `jakarta.jms.*`**. Không sử dụng `javax.jms.*` của Spring Framework 5 cho project Boot 3.

## 2. Ba cách nhận message thường bị nhầm

| Cơ chế | Ai thực hiện receive? | API chính | Hành vi |
|---|---|---|---|
| `JmsTemplate.receive(...)` | Thread **đang gọi** template | `JmsTemplate.receive`, `receiveSelected` | Nhận **đồng bộ**, trả message/object hoặc `null` khi timeout; ứng dụng phải chủ động gọi tiếp. |
| `SimpleMessageListenerContainer` | JMS provider gọi listener | `MessageConsumer.setMessageListener(...)` | Tạo số Session/Consumer tương đối cố định, callback qua JMS API; ít hỗ trợ dynamic scaling và external transaction. |
| **`DefaultMessageListenerContainer`** | Consumer tasks do Spring quản lý | Vòng lặp `MessageConsumer.receive(...)` | Nhận blocking/polling, gọi listener trong task, hỗ trợ dynamic concurrency, caching, transaction và recovery. |

Đặc biệt:

~~~text
JmsTemplate.receive()
    service thread --------> receive(timeout) --------> return message/null

SimpleMessageListenerContainer
    provider --------> MessageConsumer.setMessageListener(listener)
                         provider gọi callback khi có message

DefaultMessageListenerContainer
    Spring consumer task:
       while (container running) {
           Message message = consumer.receive(timeout);
           if (message != null) invoke listener(message);
           maintain transaction / cache / scaling / recovery...
       }
~~~

Sơ đồ trên là **mô hình tư duy**, không phải mã nguồn DMLC chính xác từng dòng. Trong Spring Framework thực tế, logic trải qua các lớp `AbstractPollingMessageListenerContainer`, `DefaultMessageListenerContainer` và các consumer invoker. Không copy vòng lặp trong sơ đồ làm một listener thứ hai.

**Vì sao gọi là polling nếu `receive` đang block?** Vì Spring chủ động lặp lại lời gọi receive để lấy từng message, thay vì đăng ký `setMessageListener` rồi để JMS provider gọi một callback. Các lời gọi receive **không nhất thiết là HTTP requests** hoặc truy vấn broker qua mạng tại mỗi vòng; JMS client/provider có thể nhận data bằng protocol và buffer bên trong.

## 3. Dòng đời của một consumer task

~~~text
ApplicationContext refresh
   |
   +-> Khởi tạo ConnectionFactory / listener factory
   |
   +-> Tạo DefaultMessageListenerContainer cho endpoint
   |      - destination, selector, QoS/transaction
   |      - concurrentConsumers / maxConcurrentConsumers
   |      - cacheLevel, receiveTimeout, TaskExecutor
   |
   +-> start container (SmartLifecycle)
           |
           +-> Schedule ConsumerInvoker task
                   |
                   +-> Open/obtain Connection, Session, MessageConsumer
                   |
                   +-> consumer.receive(receiveTimeout)
                   |      |
                   |      +-- JMS Message -> gọi listener/adapter/handler
                   |      |                   -> commit/ACK hoặc rollback
                   |      |
                   |      +-- null        -> idle receive / tiếp tục vòng lặp
                   |
                   +-> Có tải: có thể schedule thêm consumer tasks
                   |
                   +-> Khi stop / mất kết nối: shutdown/recovery theo policy
~~~

Ba ranh giới cần hiểu:

- **JMS Session không phải thread-safe tùy ý**. DMLC cấp Session/Consumer trong phạm vi invoker theo policy, thay vì để nhiều handler tự chia chung một Session một cách bất cẩn.
- Một listener Java bean có thể là **singleton**. Nhiều invoker đồng thời có thể gọi cùng method `@JmsListener`; code handler vẫn phải thread-safe.
- Việc nhận message và xử lý thành công là **hai mốc khác nhau**. Một receive trả message không bảo đảm database transaction đã commit hoặc API bên ngoài đã xử lý xong.

### Polling không tương đương busy-wait

Với `receiveTimeout=1000`, một invoker có thể chờ tới 1 giây nếu không có message. Nếu message đến sau 30 ms, receive **có thể trả về ngay**. Đây không phải một vòng:

~~~java
while (true) {
    if (queueHasMessage()) {
        // ...
    }
    Thread.sleep(1_000);
}
~~~

Đoạn trên không phải DMLC và không nên dùng để mô phỏng latency. DMLC dựa trên JMS `MessageConsumer.receive`. Con số timeout là **mức chờ tại receive**, không phải sleep cứng giữa hai message.

## 4. receiveTimeout: con số dễ hiểu sai nhất

`DefaultMessageListenerContainer` kế thừa `setReceiveTimeout(long)` từ `AbstractPollingMessageListenerContainer`. Theo Spring Framework 6.2, mặc định là **1.000 mili giây**.

| Giá trị | Ý nghĩa | Khuyến nghị |
|---|---|---|
| `1000L` | Nếu chưa có message, một receive đợi tối đa xấp xỉ 1 giây trước khi trả `null`. | Mặc định phù hợp nhiều ứng dụng. |
| `500L` | Tối đa xấp xỉ nửa giây chờ khi không có message. | Demo đơn giản; có thể làm nhiều lần timeout/idle accounting hơn. |
| `5000L` | Mỗi receive có thể đợi tới 5 giây khi queue rỗng. | Giảm tần suất empty returns nhưng ảnh hưởng responsiveness/tuning/transaction timeout. |
| `0L` | Chờ vô thời hạn tại receive. | **Thường tránh**: khó dừng container gọn và không thích hợp với transaction manager có timeout. |
| `-1L` (âm) | Thực hiện `receiveNoWait()`. | Không dùng như mặc định để “tăng tốc”; có thể tạo polling quá tích cực/chi phí không cần thiết. |

**Lưu ý transaction:** nếu sử dụng external transaction manager, `receiveTimeout` cần **nhỏ hơn transaction timeout** tương ứng. Một receive bị block lâu hơn thời gian giao dịch có thể gây rollback/timeout ngay cả khi chưa có message.

### Timeline ví dụ

~~~text
receiveTimeout = 1000 ms

t=0      ConsumerInvoker gọi receive(1000)
t=200    Message A đến -> receive trả A (không đợi tới t=1000)
t=205    Handler A hoàn tất; invoker gọi receive tiếp
t=1205   Không có message -> receive trả null
t=1206   Invoker tiếp tục hoặc kiểm tra trạng thái idle
t=1230   Message B đến, receive mới có thể trả về ngay
~~~

Các mốc chỉ **minh họa**; scheduling, transaction, network và handler duration làm thời gian thực thay đổi. DMLC không cam kết đúng mili giây, và một receive có thể không hoàn tất nếu mạng/provider gặp sự cố cho tới khi cơ chế recovery phát hiện.

### receiveTimeout không phải thuộc tính nào khác?

- Không phải **`JmsTemplate.setReceiveTimeout`**: setter đó chỉ quản lý synchronous receive của template khác.
- Không phải **broker message TTL**: TTL quyết định message hết hạn, không quyết định listener đợi bao lâu.
- Không phải **delivery delay**: delay là mốc sớm nhất message được giao; timeout là thời gian chờ mỗi receive.
- Không phải **business handler timeout**: method đang xử lý HTTP/DB lâu không tự bị Spring hủy sau receiveTimeout.
- Không phải **recoveryInterval**: thời gian thử kết nối lại broker khi có lỗi.
- Không phải **batch interval**: DMLC có thể nhận nhiều message liên tiếp nhanh hơn receiveTimeout nhiều lần.

## 5. Tạo DMLC thông qua DefaultJmsListenerContainerFactory

Với `@JmsListener`, cách phổ biến là tạo bean `DefaultJmsListenerContainerFactory`. **Factory không trực tiếp nhận message**; nó tạo một `DefaultMessageListenerContainer` cho mỗi endpoint được đăng ký.

Ví dụ trong Spring Framework 6.x:

`src/main/java/example/jms/PollingContainerConfig.java`:

~~~java
package example.jms;

import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.listener.DefaultMessageListenerContainer;

@Configuration
@EnableJms
public class PollingContainerConfig {

    @Bean("pollingJmsListenerContainerFactory")
    DefaultJmsListenerContainerFactory pollingFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(false);                 // JMS Queue
        factory.setSessionTransacted(true);             // JMS local transaction
        factory.setConcurrency("1-3");                  // core 1, max 3
        factory.setReceiveTimeout(1_000L);             // wait at most ~1 s
        factory.setCacheLevel(
                DefaultMessageListenerContainer.CACHE_CONSUMER);
        factory.setRecoveryInterval(5_000L);
        return factory;
    }
}
~~~

Đây là class có thể biên dịch trong project Spring có `spring-jms`, và một `ConnectionFactory` hợp lệ. Với Spring Boot auto-configuration, **không buộc phải tự khai báo factory** khi mặc định đã đúng; khai báo factory riêng khi cần ranh giới chính sách cụ thể.

Listener chọn factory:

~~~java
package example.jms;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderQueueListener {

    @JmsListener(
            id = "pollingOrderConsumer",
            destination = "orders.commands",
            containerFactory = "pollingJmsListenerContainerFactory",
            concurrency = "2-3")
    public void onOrder(String text) {
        System.out.println("received=" + text);
    }
}
~~~

`concurrency="2-3"` ở annotation **ghi đè** `setConcurrency("1-3")` của factory cho endpoint này. `id` là tên container trong `JmsListenerEndpointRegistry`, **không** phải tên JMS consumer trên broker hay subscription name.

### Default factory name

Nếu `@JmsListener` không có `containerFactory`, Spring thường tra bean `jmsListenerContainerFactory` làm factory mặc định. Nếu bạn chỉ tạo bean tên `pollingJmsListenerContainerFactory`, phải khai báo tên đó trong annotation hoặc đăng ký default qua cấu hình. Tránh đặt tên factory khác rồi nghĩ mọi listener tự sử dụng nó.

### Spring Boot tạo gì cho bạn?

Với `spring-boot-starter-artemis`, Spring Boot có thể tự tạo `ConnectionFactory`, `JmsTemplate` và JMS listener factory phù hợp khi conditions của auto-configuration thỏa mãn. Spring Boot cũng hỗ trợ khám phá `@JmsListener` khi JMS infrastructure có sẵn. Tuy nhiên, **đừng đồng nhất “có Boot starter” với “đã có broker hoạt động”**; endpoint/credentials/Queue, broker routing và transaction vẫn phải đúng.

## 6. DMLC trực tiếp: không bắt buộc dùng @JmsListener

Nếu cần tích hợp legacy listener thực thi `jakarta.jms.MessageListener`, có thể tạo bean container trực tiếp:

~~~java
package example.jms;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.Message;
import jakarta.jms.MessageListener;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.listener.DefaultMessageListenerContainer;

@Configuration
public class DirectContainerConfig {

    @Bean
    DefaultMessageListenerContainer directContainer(
            ConnectionFactory connectionFactory) {

        DefaultMessageListenerContainer container =
                new DefaultMessageListenerContainer();
        container.setConnectionFactory(connectionFactory);
        container.setDestinationName("orders.commands");
        container.setPubSubDomain(false);
        container.setConcurrency("1-2");
        container.setReceiveTimeout(1_000L);
        container.setSessionTransacted(true);

        MessageListener listener = (Message message) -> {
            try {
                System.out.println("jmsMessageId="
                        + message.getJMSMessageID());
            } catch (jakarta.jms.JMSException ex) {
                throw new IllegalStateException(
                        "Cannot read JMSMessageID", ex);
            }
        };
        container.setMessageListener(listener);
        return container;
    }
}
~~~

**Không copy bean này vào cùng app demo `@JmsListener` trỏ đến cùng Queue** nếu bạn kỳ vọng output xác định: hai containers sẽ là **hai nhóm consumer cạnh tranh**. Đoạn này là lựa chọn **thay thế** factory/annotation khi dùng direct listener.

DMLC là `SmartLifecycle` bean; trong Spring context bình thường nó được initialize/start/stop theo vòng đời container. Không gọi thủ công `start()` nhiều lần từ constructor hoặc request HTTP nếu chưa xem lifecycle.

## 7. Concurrency: core, max và consumer invoker

DMLC có hai tham số chính:
- `setConcurrentConsumers(int)`: số consumer **core/tối thiểu** cần duy trì, mặc định 1.
- `setMaxConcurrentConsumers(int)`: số tối đa container có thể tăng tới, mặc định 1.

Cách rút gọn:

~~~java
container.setConcurrency("2-5");
// tương đương ý định core=2, max=5
~~~

| Cấu hình | Ý nghĩa |
|---|---|
| `"1-1"` | Một consumer cố định. |
| `"3-3"` | Ba consumer cố định; có thể xử lý Queue song song. |
| `"2-5"` | Giữ ít nhất hai, tăng tối đa năm khi có tải rồi giảm về hai khi idle. |
| `"5"` | Lower mặc định là 1, **upper=5**, không phải cố định năm. |
| Bỏ qua concurrency | Mặc định thường core=max=1 ở DMLC. |

Dynamic scaling phụ thuộc message load, invoker scheduling, idle counters, `TaskExecutor` và giới hạn provider; `maxConcurrentConsumers=5` là **trần**, không phải số thread chắc chắn đang hoạt động.

### Minh họa ba bản sao ứng dụng

~~~text
3 replicas × (core 2, max 5) trên cùng một Queue

Tổng core khoảng 6 JMS consumers
Tổng max khoảng 15 JMS consumers
(chưa kể endpoint khác)
~~~

Khi cùng một Queue có nhiều consumers, message có thể được giao cho một consumer bất kỳ đủ điều kiện, và **thứ tự hoàn tất** nghiệp vụ không còn được bảo đảm. Mỗi Session tuân theo quy tắc tuần tự của JMS, nhưng nhiều sessions/consumers cho phép chạy song song. Nếu business yêu cầu thứ tự theo `accountId` hoặc `orderId`, cần message grouping/partitioning hoặc sequence/idempotency, không chỉ tăng `concurrency`.

### Vì sao thêm consumer chưa chắc tăng throughput?

- Broker client prefetch giữ sẵn message tại một consumer.
- Database pool bị cạn, thread handler đợi kết nối.
- Downstream API rate-limits hoặc shared lock.
- Transaction kéo dài làm tăng in-flight/rollback.
- Message group yêu cầu affinity nên không thể chia đều.
- Nhiều replicas tự phát làm tăng cạnh tranh thay vì xử lý nhanh hơn.

Tăng concurrency bằng phép đo **Queue depth, oldest message age, processing time, activeConsumers, DB pool, broker prefetch**, không mặc định dùng số core CPU làm max.

## 8. TaskExecutor và maxMessagesPerTask

Mỗi consumer invoker là một task được DMLC gửi vào `TaskExecutor`. Với executor mặc định, Spring thường dùng `SimpleAsyncTaskExecutor` và các invoker có thể tồn tại lâu, giữ một thread cho công việc nhận.

`setMaxMessagesPerTask(int)` giới hạn số **lần cố gắng nhận** trong một lần thực thi task, **bao gồm cả receive trả `null`**, chứ không chỉ những lần xử lý message thành công.

~~~java
container.setMaxMessagesPerTask(50);
~~~

Với cấu hình này, một invoker task sẽ nhường việc/reschedule sau tối đa 50 receive attempts (nếu không bị kết thúc sớm bởi idle/error/shutdown). Đừng gọi nó là batch-size của business payload hay “50 message chắc chắn được xử lý”.

### Giá trị mặc định phụ thuộc executor

- Với một `TaskExecutor` thông thường, mặc định `maxMessagesPerTask=-1`: một task có thể chạy dài hạn cho tới shutdown/idle policy.
- Với `SchedulingTaskExecutor` nói rằng ưu tiên task sống ngắn, mặc định có thể là **10 receive attempts/task** để thread pool dễ reschedule.
- Giá trị 10–100 có thể là điểm bắt đầu khi thật sự cần share executor/task pool, nhưng phải đo hiệu năng và thời điểm dừng/scale.

Một thread pool nhỏ đặt `maxPoolSize=4` không nhất thiết xử lý được DMLC với 10 consumer tasks dài hạn: các task chiếm thread vì chúng liên tục chờ receive. **Không dùng chung thread pool hạn chế với những công việc không liên quan** nếu nó có thể bị polling tasks chiếm hết.

### Khi nào nên tùy chỉnh TaskExecutor?

Thường chỉ khi:
- Môi trường Jakarta EE có executor được quản lý.
- Có yêu cầu thread naming, lifecycle hoặc tài nguyên pool cụ thể.
- Muốn dùng Java 21 virtual threads với phiên bản Spring hỗ trợ (không cần cho ví dụ Java 17).
- Cần kiểm soát cách reschedule và theo dõi task khi đổi concurrency.

Nếu không có yêu cầu thực, nên để Spring DMLC quản lý executor mặc định. Tăng max messages/task chỉ để “giảm độ trễ” không nhất thiết cải thiện responsiveness.

## 9. Idle counters: vì sao consumer tăng rồi giảm?

DMLC có thể tạo thêm **surplus consumers** khi Queue bận và giảm chúng khi Queue idle.

Ba thuộc tính dễ bị nhầm:

| Thuộc tính | Ý nghĩa thực tế |
|---|---|
| `idleConsumerLimit` | Cho phép bao nhiêu consumer **idle đồng thời** trước khi hạn chế tạo invoker mới; mặc định 1. |
| `idleTaskExecutionLimit` | Sau bao nhiêu task executions được xem là idle thì surplus invoker có thể dừng; mặc định 1. |
| `idleReceivesPerTaskLimit` | Số lần receive liên tiếp trả `null` trước khi task được đánh dấu idle; thường mặc định 10 cho surplus consumers với executor mặc định của Spring 6.2. |

Ví dụ một Queue có `core=1,max=4`: khi có backlog, DMLC có thể tạo thêm consumer thứ 2–4. Khi backlog hết, surplus consumers trải qua các lần receive timeout trả `null`, rồi dừng theo idle policies. **Consumer core tối thiểu vẫn được giữ** (trừ khi container stop/failure).

### Tình huống minh họa

~~~text
receiveTimeout = 1000 ms
maxConcurrency = 4
idleReceivesPerTaskLimit = 10

Queue vừa hết message
  |
  +-> surplus consumer nhận null nhiều lần
  |
  +-> sau khoảng 10 lượt idle (thời gian thực phụ thuộc load)
  |
  +-> surplus consumer được thu hẹp về core
~~~

Đây là mô tả gần đúng, không phải đồng hồ SLA cố định 10 giây. Nếu có message mới xen giữa, bộ đếm/đánh dấu idle thay đổi. Với một `TaskExecutor` chọn short-lived tasks, cơ chế `maxMessagesPerTask` và `idleTaskExecutionLimit` cũng tham gia quyết định reschedule.

**Tránh tinh chỉnh tất cả idle knobs ngay từ đầu.** Với traffic có các đợt burst, một limit quá thấp có thể tạo/đóng consumer liên tục; limit quá cao có thể giữ tài nguyên broker vô ích. Hãy quan sát số active/scheduled consumers qua nhiều chu kỳ tải trước khi điều chỉnh.

## 10. Caching: Connection, Session và Consumer

DMLC có thể cache tài nguyên JMS để giảm chi phí tạo lại Connection/Session/MessageConsumer giữa các lần nhận.

| Cache level | Ý nghĩa |
|---|---|
| `CACHE_NONE` | Không giữ tài nguyên JMS cho lần nhận sau; tạo/lấy lại khi cần. |
| `CACHE_CONNECTION` | Cache Connection, lấy Session/Consumer theo từng lần nhận. |
| `CACHE_SESSION` | Cache Connection và Session, nhưng không giữ Consumer. |
| `CACHE_CONSUMER` | Cache Connection, Session và MessageConsumer; hiệu quả cho receive loop dài hạn. |
| `CACHE_AUTO` | Spring chọn mức caching theo transaction strategy. |

**Mặc định thực tế của `CACHE_AUTO`:**
- **Không có external transaction manager:** DMLC thường chọn `CACHE_CONSUMER`.
- **Có external transaction manager:** DMLC mặc định chọn `CACHE_NONE` để tài nguyên JMS được enlist đúng vào mỗi transaction trong môi trường XA/Jakarta EE.

Điều này đặc biệt quan trọng khi dùng `JtaTransactionManager`. Một số app server yêu cầu connection/session được lấy mới trong transaction scope để enlist XA. Không nên cố áp `CACHE_CONSUMER` khi có XA nếu chưa xác minh compatibility; có thể dẫn đến message không nằm trong giao dịch dự kiến.

### CachingConnectionFactory bên ngoài có cần không?

Không mặc định. DMLC đã có cơ chế caching **bên trong vòng đời container**. Dùng thêm `org.springframework.jms.connection.CachingConnectionFactory` có thể tạo **caching hai tầng**, khó dự đoán với dynamic scaling và container restart. Spring Javadoc lưu ý consumer được cache bên ngoài có thể giữ message prefetched dù đã rời khỏi container.

Nếu ứng dụng có CachingConnectionFactory cho **producer `JmsTemplate`**, chưa chắc listener container cũng nên dùng cùng wrapper đó. Đọc tài liệu Spring/provider và thử shutdown/restart/failover trước khi áp dụng.

### Caching và Topic non-durable

Topic subscription non-durable có thể biến mất khi consumer đóng. Nếu cache bị tắt và container liên tục tạo/đóng consumer, message được publish vào khoảng không có subscription có thể **không được lưu để nhận sau**. Với Topic, caching level và subscription durability cần được thiết kế cùng nhau.

## 11. Transaction, ACK và lỗi handler

Container nhận message không đồng nghĩa message **đã hoàn tất**. Hành vi khi lỗi phụ thuộc transaction hoặc ACK mode.

| Cấu hình | Khi handler thành công | Khi handler ném exception |
|---|---|---|
| `AUTO_ACKNOWLEDGE` theo DMLC mặc định | Message có thể đã được ACK **trước** khi listener chạy. | **Không bảo đảm redelivery**; Spring cảnh báo auto-ack trước listener execution. |
| `sessionTransacted=true` (local JMS transaction) | Session commit sau invocation thành công. | Container rollback JMS session; provider áp dụng redelivery policy. |
| External `PlatformTransactionManager` phù hợp | Receive/handler có thể tham gia transaction manager. | Transaction có thể rollback; cần xác minh resource enlistment/XA. |
| `CLIENT_ACKNOWLEDGE`/mode khác | Theo contract container/provider cụ thể. | Không suy ra exactly-once chỉ từ ACK mode. |

**Lựa chọn an toàn phổ biến:** cấu hình `setSessionTransacted(true)` cho listener Queue quan trọng, rồi xác minh broker redelivery, max attempts, backoff, DLQ và idempotency.

Ví dụ:

~~~java
factory.setSessionTransacted(true);
factory.setConcurrency("1-3");
~~~

Nếu `@JmsListener` ném unchecked exception, JMS local transaction thường rollback, message có thể được giao lại. Nhưng **rollback không tự giới hạn số lần thử** và không tự tạo DLQ. Những policy đó thuộc provider/broker; phải cấu hình riêng.

### Database không tự nằm trong cùng JMS transaction

Giả sử handler:
1. Cập nhật database thành công, commit DB.
2. Sau đó JMS commit thất bại hoặc process bị kill.
3. Broker redeliver cùng message.
4. Handler lặp tác dụng phụ.

`sessionTransacted=true` **không bảo đảm atomicity DB+JMS**. Dùng business event ID + unique constraint/idempotent consumer, transactional outbox/inbox hoặc JTA/XA nếu thực sự cần và được hỗ trợ. Cần test cả crash sau DB commit nhưng trước JMS commit.

### Poison messages

Một message malformed JSON có thể khiến converter/adapter ném exception mỗi lần; nếu broker retry vô hạn, container bị kẹt. Thiết kế max delivery attempts, DLQ/parking queue, replay sau sửa lỗi và metrics. **Không nuốt mọi exception trong listener rồi trả bình thường** nếu nghiệp vụ chưa xử lý xong, vì transaction có thể commit message lỗi.

## 12. Recovery khi broker mất kết nối

DMLC có khả năng tự phục hồi khi `ConnectionFactory`/broker tạm thời lỗi. Theo Spring Javadoc, mặc định dùng khoảng cách thử lại **5.000 ms**, có thể điều chỉnh:

~~~java
factory.setRecoveryInterval(5_000L);
~~~

hoặc sử dụng một `BackOff` object hỗ trợ chiến lược khác khi tạo factory/container, với thứ tự cấu hình phù hợp. Một ví dụ dạng bean container:

~~~java
import org.springframework.util.backoff.ExponentialBackOff;

// Mảnh cấu hình nếu đã có DefaultMessageListenerContainer container.
ExponentialBackOff backOff = new ExponentialBackOff();
backOff.setInitialInterval(1_000L);
backOff.setMultiplier(2.0);
backOff.setMaxInterval(30_000L);
container.setBackOff(backOff);
~~~

Đoạn này chỉ là **mảnh cấu hình** trong project Spring đã import các class tương ứng. Việc sử dụng backoff không tự chữa broker mất dữ liệu hoặc credentials hết hạn. Khi chọn `setRecoveryInterval` và `setBackOff`, kiểm tra **setting nào áp dụng cuối** theo API; đừng cấu hình cả hai tùy tiện.

### Recovery không tự bảo đảm không trùng message

Khi network bị đứt:
- Container phát hiện lỗi nhận hoặc lỗi tài nguyên.
- Container có thể đóng/refresh session/consumer/connection rồi thử lại.
- Những message đã broker nhận nhưng chưa ACK/commit có thể redeliver.
- Những message đã business side effect nhưng JMS commit chưa xác nhận có thể **xử lý lại**.

Vì vậy cần kiểm tra broker state, `JMSXDeliveryCount`, idempotency và outcome DB. Recovery container là **khả năng vận hành**, không phải bằng chứng exactly-once business semantics.

### Kết nối thất bại không giống Queue trống

- **Queue trống:** `receive(timeout)` có thể trả `null`; container tiếp tục receive/idle accounting bình thường.
- **Broker/Connection lỗi:** `receive`/session có thể ném JMS exception; container đi theo đường setup/recovery, không nên ghi “không có việc”.
- **Sai Queue/destination hoặc ACL:** container có thể lặp lỗi provisioning/authorization; cần alert, không kỳ vọng retry vô hạn sẽ tự sửa.
- **Message có nhưng selector không match:** consumer vẫn có thể nhận `null` và Queue backlog tăng; cần inspect JMS properties/selector.

## 13. Queue và Topic: vì sao polling có các giới hạn riêng?

### Queue

Với Queue, mỗi JMS message thường được giao cho một consumer trong nhóm phù hợp. DMLC có thể tăng số consumer `1-4` để chia tải. Nếu business handler độc lập, đây là trường hợp DMLC thể hiện lợi thế rõ nhất: vừa polling ổn định vừa scale khi backlog tăng.

Tuy nhiên, multiple consumers có thể phá thứ tự hoàn tất, và consumer prefetch có thể làm phân phối không đều. DMLC không tự biết “job B phải đợi job A của cùng order”.

### Topic

Với Topic, mỗi subscription độc lập có thể nhận một **bản sao** event. Nếu bạn tăng concurrency ở Topic non-shared, bạn có thể tạo nhiều subscriptions độc lập và nhận **trùng bản sao** từ góc nhìn một service. Theo Spring Javadoc, không nên tăng concurrent consumers của Topic thông thường nếu không có thiết kế broker-specific phù hợp.

Nếu cần nhiều replica cùng chia một subscription, hãy cấu hình **shared subscription** (và **durable** khi cần backlog trong lúc offline) với `pubSubDomain=true`, `subscriptionShared=true`, `subscriptionDurable=true` và subscription name ổn định. Provider/client phải hỗ trợ JMS 2.0+ shared subscription semantics.

DMLC `CACHE_NONE` với Topic non-durable có nguy cơ làm subscription biến mất giữa các lần consumer được tạo mới. Đối với Topic, caching, durability và lifecycle phải được xem cùng nhau, không chỉ tối ưu throughput.

### Selector đi kèm consumer

Một listener có `@JmsListener(selector = "region = 'EU'")` chỉ chọn message có property tương ứng. Selector không đọc JSON body. Message không match trên Queue có thể ở lại Queue cho consumer khác, không tự được đưa vào DLQ. Với Topic, selector thường quyết định message nào được thêm vào subscription khi publish.

**Selector không thay thế isolation/bảo mật**. Nếu message mang tenant/region nhạy cảm, dùng ACL/broker namespace hoặc Queue riêng; property do producer có thể bị gắn sai.

## 14. Lifecycle: start, stop và trạng thái container

DMLC là Spring `SmartLifecycle` component. Với `@JmsListener`, container được quản lý thông qua `JmsListenerEndpointRegistry` theo `id` annotation.

Ví dụ class đầy đủ dùng để quan sát:

~~~java
package example.jms;

import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.listener.MessageListenerContainer;
import org.springframework.stereotype.Service;

@Service
public class ListenerStatus {
    private final JmsListenerEndpointRegistry registry;

    public ListenerStatus(JmsListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public boolean isRunning(String id) {
        MessageListenerContainer container =
                registry.getListenerContainer(id);
        return container != null && container.isRunning();
    }
}
~~~

Với một DMLC cụ thể, có thể xem `getConcurrentConsumers()`, `getMaxConcurrentConsumers()`, `getActiveConsumerCount()` và `getScheduledConsumerCount()` để chẩn đoán, thông qua reference container thích hợp.

**Phân biệt:**
- `configured core/max`: giới hạn được đặt.
- `scheduled consumers`: số invokers đã được schedule.
- `active consumers`: số consumer đang hoạt động theo quản lý container.
- `message throughput`: số message thực sự xử lý, không phải số consumer được schedule.

Không dùng cách đếm thread JVM rồi tự kết luận “đang có 4 consumer”; threads có thể thuộc task executor và framework khác. Tương tự, `start/stop` container không đồng nghĩa tạo/xóa durable subscription; semantics thực tế tùy subscription identity và broker.

### Shutdown an toàn

Khi pod/service cần dừng:
1. Ngừng nhận công việc mới qua lifecycle/graceful shutdown.
2. Đợi message đang xử lý đến điểm commit/rollback hợp lệ.
3. Đóng consumer/session/connection theo container.
4. Kiểm tra uncommitted message được broker xử lý đúng policy.
5. Dùng readiness/termination grace period đủ cho business handler; không dừng process ngay khi vừa stop receive nếu có work chưa hoàn thành.

Đừng coi `receiveTimeout=1000` là **giới hạn tổng shutdown**. Method business đang xử lý có thể mất lâu hơn; transaction/recovery/connection close cũng cần thời gian.

## 15. Demo chạy thực tế: DMLC polling cùng Spring Boot và Artemis embedded

Demo sử dụng **Java 17 + Spring Boot 3.5.16 + Artemis embedded**:
- Tạo một Queue `demo.polling` trên broker nhúng.
- Tạo `DefaultJmsListenerContainerFactory` với `receiveTimeout=500 ms`, `concurrency="1-2"` và JMS local transaction.
- `@JmsListener` được đăng ký qua factory đó; Spring tạo DMLC bên dưới.
- Một `ApplicationRunner` gửi ba message bằng `JmsTemplate` sau một khoảng idle ngắn.
- `CountDownLatch` đợi ba message và `ConcurrentSkipListSet` sắp output, nên kết quả không lệ thuộc thứ tự callback của hai consumers.

**Quan trọng:** producer **không tự gọi `receive`**. DMLC làm việc đó trong listener threads. Thử nghiệm minh họa cơ chế polling có timeout và lời gọi handler tự động.

### 15.1. Cấu trúc

~~~text
jms-polling-lab/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── resources/application.yml
    └── java/example/jms/PollingLabApplication.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'jms-polling-lab'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
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
    runtimeOnly 'org.apache.activemq:artemis-jakarta-server'
}
~~~

Gradle Spring Boot plugin dùng BOM Spring tương ứng, tránh ghép các dependency JMS Jakarta của nhiều major version. Project cần JDK 17+ và Gradle tương thích plugin. Đây là broker **embedded cho lab**, không có yêu cầu TLS/failover như production.

`src/main/resources/application.yml`:

~~~yaml
spring:
  main:
    web-application-type: none
  artemis:
    mode: embedded
    embedded:
      queues: demo.polling
      persistent: false
~~~

Artemis embedded ở đây dùng storage không persistent để giảm cấu hình; không dùng demo để khẳng định message sống qua restart.

### 15.2. File Java hoàn chỉnh

`src/main/java/example/jms/PollingLabApplication.java`:

~~~java
package example.jms;

import java.util.List;
import java.util.concurrent.ConcurrentSkipListSet;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import jakarta.jms.ConnectionFactory;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.listener.DefaultMessageListenerContainer;
import org.springframework.jms.listener.MessageListenerContainer;

@SpringBootApplication
@EnableJms
public class PollingLabApplication {
    private static final String QUEUE = "demo.polling";

    public static void main(String[] args) {
        SpringApplication.run(PollingLabApplication.class, args);
    }

    @Bean("pollingFactory")
    DefaultJmsListenerContainerFactory pollingFactory(
            ConnectionFactory connectionFactory) {
        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(false);          // Queue
        factory.setSessionTransacted(true);      // JMS local transaction
        factory.setConcurrency("1-2");          // Core 1, max 2
        factory.setReceiveTimeout(500L);        // Mỗi receive tối đa 500 ms
        factory.setCacheLevel(
                DefaultMessageListenerContainer.CACHE_CONSUMER);
        return factory;
    }

    static final class Results {
        private final ConcurrentSkipListSet<String> messages =
                new ConcurrentSkipListSet<>();
        private final CountDownLatch received =
                new CountDownLatch(3);

        void add(String body) {
            if (messages.add(body)) {
                received.countDown();
            }
        }

        void awaitAll() throws InterruptedException {
            if (!received.await(15, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Timed out waiting for three JMS messages");
            }
        }

        List<String> snapshot() {
            return List.copyOf(messages);
        }
    }

    @Bean
    Results results() {
        return new Results();
    }

    static final class PollingListener {
        private final Results results;

        PollingListener(Results results) {
            this.results = results;
        }

        @JmsListener(
                id = "pollingOrders",
                destination = QUEUE,
                containerFactory = "pollingFactory")
        public void handle(String body) {
            results.add(body);
        }
    }

    @Bean
    PollingListener pollingListener(Results results) {
        return new PollingListener(results);
    }

    @Bean
    ApplicationRunner demonstrate(
            JmsTemplate template,
            Results results,
            JmsListenerEndpointRegistry registry) {

        return args -> {
            MessageListenerContainer container =
                    registry.getListenerContainer("pollingOrders");
            if (!(container instanceof DefaultMessageListenerContainer)) {
                throw new IllegalStateException(
                        "Expected DefaultMessageListenerContainer");
            }

            System.out.println(
                    "CONTAINER=DefaultMessageListenerContainer");

            // Cho container có thời gian receive khi Queue đang trống.
            Thread.sleep(1_200L);

            // Producer gửi ba message; DMLC polling và gọi handler.
            template.convertAndSend(QUEUE, "order-C");
            template.convertAndSend(QUEUE, "order-A");
            template.convertAndSend(QUEUE, "order-B");

            results.awaitAll();

            List<String> actual = results.snapshot();
            List<String> expected =
                    List.of("order-A", "order-B", "order-C");

            if (!actual.equals(expected)) {
                throw new IllegalStateException(
                        "Unexpected results: " + actual);
            }

            for (String item : actual) {
                System.out.println("RECEIVED=" + item);
            }

            System.out.println("ALL_RECEIVED=true");
        };
    }
}
~~~

### 15.3. Giải thích từng phần

1. `pollingFactory` được Spring JMS dùng để tạo một **DMLC** khi đăng ký `@JmsListener`.
2. DMLC duy trì receive loop cho Queue `demo.polling`. `setReceiveTimeout(500L)` làm receive trả `null` khi trống sau thời gian chờ, **không** ép mỗi message phải đợi 500 ms.
3. `setConcurrency("1-2")` cho phép một consumer core và có thể thêm một consumer nữa nếu tải đủ; **không có bảo đảm nhất thiết tăng lên 2** chỉ vì gửi ba message rất nhanh.
4. `setSessionTransacted(true)` bao quanh receive/handler với JMS local transaction; message chưa commit có thể redeliver nếu có failure.
5. `@JmsListener` hoạt động tự động, không có code `while/receive` do người viết ứng dụng tạo.
6. `Results` dùng cấu trúc concurrent và `CountDownLatch` để tránh đọc collection khi handler khác còn thêm item.
7. `snapshot()` có thứ tự từ `ConcurrentSkipListSet`, nên stdout xác định dù callback có thể song song và xử lý không theo send order.
8. `Thread.sleep(1_200L)` chỉ làm Runner chờ trước khi **gửi** để minh họa container vẫn đang receive khi Queue trống; không phải một phần bắt buộc của DMLC.
9. Kiểm tra registry xác nhận container Spring thật sự thuộc loại `DefaultMessageListenerContainer`. Các dòng log Spring Boot/Artemis khác nhau theo môi trường.

Lưu ý: `Results.add` trong handler ghi bộ nhớ **trước** khi transaction JMS commit; demo không chứng minh database commit đúng một lần. Với ứng dụng thật, kết quả nghiệp vụ nên được lưu trong transactional resource/idempotent storage trước khi đánh dấu success, và cần test failure/recovery riêng.

### 15.4. Cách chạy và stdout

Tại thư mục `jms-polling-lab`, dùng JDK 17+ và Gradle tương thích.

Nếu đã có Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

Nếu chưa có Wrapper, dùng Gradle đã cài:

~~~bash
gradle bootRun
~~~

Windows PowerShell với Wrapper:

~~~powershell
.\gradlew.bat bootRun
~~~

Sau log khởi động, **các dòng do ứng dụng in** khi lab thành công:

~~~text
CONTAINER=DefaultMessageListenerContainer
RECEIVED=order-A
RECEIVED=order-B
RECEIVED=order-C
ALL_RECEIVED=true
~~~

DMLC có thể scale từ một lên hai consumers hoặc tiếp tục dùng một, tùy tải và scheduling. Output ở trên được sort trong ứng dụng, **không phản ánh thứ tự broker dispatch**. Nếu broker không lên, Queue không tồn tại hoặc consumer chưa đăng ký kịp, Runner có thể timeout trong 15 giây; đây là phép kiểm tra chủ động, không phải guarantee thời gian của JMS.

### 15.5. Thử nghiệm có kiểm soát

- Đổi `factory.setReceiveTimeout(500L)` thành `2_000L`: thông thường handler vẫn nhận message nhanh khi message đến; không có “đợi đúng 2 giây”.
- Đổi `setConcurrency("1-2")` thành `"1-1"`: một consumer duy nhất; kết quả của ba message vẫn đúng.
- Đặt `setConcurrency("3-3")`: có nhiều core consumers; output vẫn đúng nhưng có thêm Session/Consumer và khả năng callback song song.
- Giả lập exception trong handler: với `setSessionTransacted(true)`, quan sát rollback/redelivery theo broker policy, **không** tự mong đợi exactly-once.
- Dừng broker hoặc sai credentials trên môi trường tích hợp: xem container recovery và log setup failures, không dùng embedded lab để kết luận về failover production.
- Thử nhiều replica và broker prefetch: so sánh active consumers với Queue depth và tốc độ xử lý.

## 16. Ví dụ Java 17 độc lập: hình dung polling chờ có timeout

Chương trình nhỏ dưới đây chỉ mô phỏng **nguyên tắc waiting/polling** bằng `BlockingQueue` của Java, **không phải** JMS implementation. Nó giúp hiểu “timeout” khác “sleep cố định” và có stdout xác định không phụ thuộc broker:

Tạo file `PollingMentalModel.java`:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.TimeUnit;

public class PollingMentalModel {
    public static void main(String[] args) throws Exception {
        BlockingQueue<String> queue = new ArrayBlockingQueue<>(2);

        String empty = queue.poll(50, TimeUnit.MILLISECONDS);
        System.out.println("EMPTY=" + (empty == null));

        queue.add("job-1");
        String received = queue.poll(50, TimeUnit.MILLISECONDS);
        System.out.println("RECEIVED=" + received);

        System.out.println("POLLING_IS_NOT_FIXED_SLEEP=true");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 PollingMentalModel.java
java PollingMentalModel
~~~

Stdout:

~~~text
EMPTY=true
RECEIVED=job-1
POLLING_IS_NOT_FIXED_SLEEP=true
~~~

`BlockingQueue.poll(timeout)` không gửi network traffic, không có JMS transaction, broker hoặc duplicate; đây chỉ là **tương tự hóa cơ chế chờ**. Trong DMLC, chờ được thực hiện qua `MessageConsumer.receive(timeout)` của JMS provider và vòng đời tài nguyên phức tạp hơn.

## 17. Quan sát và vận hành production

Các số liệu có giá trị:

| Metric | Tại sao hữu ích |
|---|---|
| `activeConsumerCount` và `scheduledConsumerCount` của DMLC | Biết invoker có thực sự tăng/giảm theo concurrency không. |
| `concurrentConsumers` và `maxConcurrentConsumers` | Giới hạn cấu hình; không phải số thực đang hoạt động. |
| Queue depth, oldest message age, enqueue/dequeue rate | Phát hiện backlog và khả năng consumer bắt kịp. |
| Receive timeouts/idle invokers | Đánh giá nhịp idle/dynamic scaling, không xem mỗi timeout là lỗi. |
| Handler duration p50/p95/p99 | Xác định nghẽn business processing thay vì broker. |
| DB pool saturation, HTTP downstream latency | Chứng minh tăng concurrency có hoặc không có ích. |
| JMS exception, recovery count, last recovery cause | Phân biệt broker mất kết nối với Queue không có message. |
| JMS transaction rollback/redelivery/DLQ | Giám sát lỗi nội dung, poison message và tính tin cậy. |
| Broker connection/session/consumer count | Tránh vượt quota khi nhân max consumers với replicas. |
| Provider prefetch/cache and consumer lag | Phát hiện phân phối lệch hoặc consumer giữ message khi shutdown. |

Khi theo dõi container qua `JmsListenerEndpointRegistry`, sử dụng `@JmsListener(id=...)` ổn định, không gắn id thay đổi theo pod vào registry. Lưu metrics theo destination, listener ID và outcome, hạn chế dynamic labels như userId hoặc correlationId để tránh cardinality lớn.

### Kiểm tra thread và pool

Nếu DMLC `concurrency="2-6"` chạy 4 replicas, trần lý thuyết là `4 × 6 = 24` consumers cho **một endpoint**. Nếu ứng dụng có 3 endpoints tương tự thì tổng có thể lên 72, chưa kể connection/session pools. Nên xét:

- Broker connection và consumer quotas.
- Thread scheduling của Spring TaskExecutor.
- Memory và CPU trên từng replica.
- Pool database và HTTP connections downstream.
- Chi phí transaction/serialization và max in-flight.
- Prefetch/message grouping, ảnh hưởng ordering.

Đừng tăng tất cả thông số đồng thời. Đặt một giả thuyết, thay một số knob, đo tối thiểu một chu kỳ traffic đủ đại diện rồi quyết định.

## 18. Lỗi phổ biến và cách xử lý

| Triệu chứng/nhầm lẫn | Nguyên nhân thực | Cách sửa |
|---|---|---|
| “receiveTimeout 1s làm mỗi message chậm 1s” | Timeout là thời gian chờ tối đa khi **không có message**. | Thử gửi message khi receive đang block; đo handler latency thực. |
| “DMLC dùng setMessageListener callback của JMS” | Đó là cơ chế của `SimpleMessageListenerContainer`. | Nhìn `MessageConsumer.receive` loop của DMLC. |
| “Queue trống = broker mất kết nối” | Empty receive trả null khác JMS exception/recovery. | Theo dõi log failure và broker availability riêng. |
| “concurrency='4' nghĩa là có đúng 4 consumers” | DMLC hiểu 4 là upper bound, lower mặc định 1. | Dùng `"4-4"` nếu muốn fixed và có resource. |
| “maxMessagesPerTask=100 xử lý đúng 100 messages” | Có tính cả receive attempts trả null. | Xem idle/executor settings, không gọi là business batch size. |
| “Đặt receiveTimeout=0 để nhanh nhất” | 0 là chờ vô thời hạn, có thể gây shutdown/transaction vấn đề. | Dùng timeout hữu hạn, thường khoảng 1 giây và tuning bằng đo. |
| “Dùng CACHE_NONE giúp tốt mọi nơi” | Có thể tạo/đóng Session/Consumer thường xuyên, Topic non-durable có nguy cơ mất message. | Chọn cache theo transaction strategy, test provider. |
| “Luôn đặt CACHE_CONSUMER dù dùng JTA/XA” | Một số app server chỉ enlist tài nguyên JMS mới lấy trong transaction. | Dùng CACHE_AUTO/default rồi xác minh XA. |
| “DMLC cần thêm CachingConnectionFactory để nhanh” | Caching hai tầng có thể gây consumer prefetched không thuộc container sau scale-down. | Ưu tiên caching nội bộ, test khi dùng wrapper. |
| “Set concurrency cao trên Topic để scale” | Non-shared Topic có thể tạo nhiều bản sao/subscriptions. | Chọn shared subscription nếu broker/contract hỗ trợ. |
| “Exception trong AUTO_ACK luôn redeliver” | DMLC có thể ACK **trước** khi gọi handler. | Cấu hình sessionTransacted và provider retry/DLQ. |
| “Recovery 5 giây bảo đảm mọi message không mất” | Recovery chỉ quản lý reconnect; transaction state, expiry và provider policy vẫn quyết định. | Thiết kế idempotency/retention/failover, test crash. |
| “Handler ghi DB một lần nghĩa là JMS exactly-once” | Redelivery sau DB commit có thể lặp side effect. | Dùng event ID/unique constraints/outbox-inbox. |
| “Đã tăng max consumers nhưng không tăng throughput” | DB/pretech/selector/prefetch/handler mới là bottleneck. | Đo cả pipeline, không chỉ số consumer. |

## 19. Bộ kiểm thử dành cho DMLC

1. **Startup:** Container được tạo đúng từ factory, listener id/destination/selector hợp lệ, broker authentication thành công.
2. **Idle receive:** Queue trống lâu hơn vài receiveTimeout nhưng listener vẫn sẵn sàng; empty returns không bị coi là handler failure.
3. **Wake-up:** Gửi message ngay giữa một receive blocking; handler có thể được gọi sớm hơn receiveTimeout.
4. **Concurrency:** Gửi nhiều messages độc lập, kiểm tra số consumers core/max và thay đổi khi burst/idle. So sánh broker session/consumer counts.
5. **Cache:** Thử CACHE_AUTO/CACHE_CONSUMER phù hợp; với external TM, kiểm tra enlistment trước khi chỉnh cache.
6. **Transaction:** Throw exception, test rollback/redelivery; kiểm tra ACK mode mặc định, DLQ và max delivery attempts.
7. **Recovery:** Tắt broker, bật lại, xem log exception/backoff, khả năng tự hoạt động trở lại và duplicate handling.
8. **Shutdown:** Dừng app trong lúc có task đang nhận và trong lúc handler đang xử lý; xác minh không mất message do ACK sớm.
9. **Topic:** Nếu dùng Topic, thử non-durable vs durable/shared, caching và thời điểm tạo subscription.
10. **TaskExecutor:** Đặt executor custom khi cần; đo thread pool starvation, maxMessagesPerTask, idle counters và CPU.
11. **Provider-specific:** Benchmark prefetch, queue depth, client buffer, redelivery count và selector để không suy diễn từ Artemis embedded.
12. **Security:** Kiểm tra broker ACL, TLS/credentials, thay đổi connection/recovery; không đưa secrets vào log.

### Checklist triển khai

- [ ] Đã hiểu DMLC polling qua `MessageConsumer.receive` chứ không phải `setMessageListener`.
- [ ] `receiveTimeout` hữu hạn và phù hợp transaction timeout/shutdown.
- [ ] `concurrentConsumers`/`maxConcurrentConsumers` dựa trên Queue load và downstream capacity.
- [ ] Không tăng concurrency Topic thường nếu chưa thiết kế shared subscriptions đúng.
- [ ] Chọn cache level phù hợp local JMS hoặc external XA/JTA; tránh caching hai tầng vô cớ.
- [ ] Có JMS local transaction hoặc transaction manager được kiểm thử; ACK, rollback, DLQ rõ.
- [ ] Broker recovery/backoff, liveness/readiness, shutdown và restart có integration test.
- [ ] Consumer handler thread-safe, idempotent; kiểm soát thứ tự business key khi cần.
- [ ] Đã quan sát active/scheduled consumers, Queue depth, oldest message, handler p95 và DB pool.
- [ ] Không đồng nhất message nhận được với nghiệp vụ đã commit.

## 20. Câu hỏi tự kiểm tra

**Câu 1.** DMLC đang gọi `receive(1000)`. Message đến sau 25 ms. Listener có phải chờ hết 1 giây mới được xử lý không?

**Đáp án:** Không. Blocking receive có thể trả về ngay khi provider có message. 1000 ms là cận trên chờ khi không có message.

**Câu 2.** Điểm cốt lõi phân biệt DMLC và `SimpleMessageListenerContainer` về cách nhận là gì?

**Đáp án:** DMLC dùng vòng lặp `MessageConsumer.receive` do Spring invoker thực hiện. Simple container đăng ký `MessageConsumer.setMessageListener` để provider callback.

**Câu 3.** `concurrency="2-5"` trên hai replicas tạo tối đa bao nhiêu consumers cho một endpoint?

**Đáp án:** Tối đa khoảng `2 × 5 = 10` consumers, core khoảng 4. Số active thực phụ thuộc load, scheduling và resource.

**Câu 4.** `receiveTimeout=0` nghĩa là không đợi đúng không?

**Đáp án:** Không. Nó nghĩa là receive chờ vô thời hạn. Giá trị âm như -1 mới có ý nghĩa no-wait receive trong Spring.

**Câu 5.** Khi thêm `JtaTransactionManager`, vì sao DMLC có thể mặc định bỏ cache Session/Consumer?

**Đáp án:** Với external transaction manager, DMLC thường dùng CACHE_NONE để lấy tài nguyên mới trong transaction scope, giúp JMS resources enlist đúng với XA theo yêu cầu app server.

**Câu 6.** Vì sao `maxMessagesPerTask=20` không đảm bảo đúng 20 business messages được xử lý?

**Đáp án:** Nó đếm receive attempts, gồm cả lần receive trả null. Không phải kích thước batch nghiệp vụ.

**Câu 7.** Consumer Queue vẫn online nhưng liên tục receive null, trong khi broker báo Queue có backlog. Có những khả năng nào?

**Đáp án:** Message không match selector, prefetched vào consumer khác, message chưa eligible/delivery delay, transaction hoặc routing/ACL sai; cần inspect raw properties, broker consumer counts và metrics.

**Câu 8.** Bật `sessionTransacted(true)` có đảm bảo mỗi business event cập nhật DB đúng một lần không?

**Đáp án:** Không. JMS local transaction và DB transaction khác nhau; redelivery sau DB commit vẫn có thể lặp side effect. Cần idempotent handler/unique event ID hoặc transaction strategy phù hợp.

**Câu 9.** DMLC mất kết nối broker trong 20 giây rồi hoạt động lại. Có thể khẳng định không mất/không trùng bất kỳ message nào không?

**Đáp án:** Không chỉ dựa trên recovery. Cần kiểm tra durability, ACK/commit, expiry, redelivery, broker storage và idempotency; recovery chỉ giúp container thiết lập lại khả năng nhận.

## 21. Nguồn tham khảo chính thức

- [Spring Framework 6.2 — DefaultMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html).
- [Spring Framework 6.2 — AbstractPollingMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/AbstractPollingMessageListenerContainer.html).
- [Spring Framework 6.2 — DefaultJmsListenerContainerFactory Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html).
- [Spring Framework — Using JMS: lựa chọn listener container](https://docs.spring.io/spring-framework/reference/integration/jms/using.html).
- [Spring Framework — Annotation-driven listener endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html).
- [Spring Framework — Receiving JMS messages, transaction và ACK](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html).
- [Spring Boot — Messaging with JMS / Artemis](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html).
- [Jakarta Messaging 3.1 specification — MessageConsumer, receive, transactions, Queue/Topic semantics](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html).
