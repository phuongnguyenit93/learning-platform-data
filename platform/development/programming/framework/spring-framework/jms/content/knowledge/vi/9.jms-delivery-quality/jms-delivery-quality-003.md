# Priority và việc ưu tiên không thay thế hợp đồng thứ tự trong Spring JMS

## 1. Vấn đề: message quan trọng hơn có nên được xử lý trước?

Một queue chứa hai sự kiện của cùng một đơn hàng:

1. `OrderCreated(order-42, sequence=1)` được gửi trước, priority 4.
2. `OrderCancelled(order-42, sequence=2)` được gửi sau, priority 8.

Đội phát triển muốn sự kiện hủy được xử lý nhanh vì khách hàng đang chờ. Nếu broker chuyển `sequence=2` tới consumer trước `sequence=1`, consumer có thể cố hủy đơn hàng chưa được tạo trong dữ liệu của mình. **Đó không nhất thiết là lỗi của broker:** JMS priority có thể thay đổi thứ tự chuyển phát, còn quy tắc *phải áp dụng Created trước Cancelled* là hợp đồng nghiệp vụ riêng.

Cần phân biệt ba câu hỏi:

- **Ưu tiên chuyển phát:** broker có cố gắng chuyển các message khẩn cấp trước không?
- **Thứ tự chuyển phát/nhận:** khi nào chuẩn Jakarta Messaging đặt ra ràng buộc thứ tự cho message?
- **Thứ tự áp dụng nghiệp vụ:** hệ thống có bảo đảm cập nhật trạng thái đúng trình tự, kể cả khi message đến trễ, bị gửi lại hoặc nhiều consumer làm việc song song không?

`JMSPriority` tác động câu hỏi đầu tiên; nó **không thay thế** việc định nghĩa và thực thi hợp đồng thứ tự nghiệp vụ.

### Mục tiêu học tập

Sau bài này, bạn có thể xác định phạm vi giá trị priority, cấu hình priority thật sự có hiệu lực với `JmsTemplate`, giải thích các ngoại lệ của quy tắc thứ tự JMS, thiết kế consumer có `aggregateId`/`sequence` để nhận biết sai thứ tự, và kiểm thử ưu tiên mà không biến hành vi “best effort” thành một assertion sai.

## 2. JMSPriority là gì?

Jakarta Messaging định nghĩa **10 mức priority nguyên từ 0 đến 9** cho message:

| Giá trị | Ý nghĩa của chuẩn |
| --- | --- |
| `0` | Mức thấp nhất |
| `1..3` | Các mức thuộc nhóm ưu tiên thông thường |
| `4` | Mức mặc định, vẫn thuộc nhóm thông thường |
| `5..8` | Các mức thuộc nhóm ưu tiên chuyển phát nhanh |
| `9` | Mức cao nhất |

Theo API, nên xem `0..4` là các mức *normal priority*, `5..9` là *expedited priority*. Provider được yêu cầu **cố gắng** chuyển message expedited trước message normal, nhưng chuẩn **không yêu cầu provider duy trì hàng đợi sắp xếp tuyệt đối theo mức priority**. Cấu hình broker, những message đã được dispatch/prefetch, số consumer và trạng thái tải hệ thống đều ảnh hưởng kết quả quan sát được.

Một số điểm thiết yếu:

- `JMSPriority` là **JMS standard header** kiểu `int`, đọc bằng `message.getJMSPriority()`.
- Priority được chọn khi **gửi**, thông qua `MessageProducer.setPriority(...)` hoặc biến thể `send(...)` có tham số QoS. Trong Spring, `JmsTemplate` có thuộc tính `priority` để dùng khi gửi.
- Không dùng `message.setJMSPriority(8)` trong `MessageCreator` làm cách cấu hình ưu tiên. Tài liệu API `jakarta.jms.Message` nói setter này dành cho **provider** điền header trong quá trình gửi.
- Priority **không phải** `deliveryMode` (persistent/non-persistent), `timeToLive` (hết hạn), `deliveryDelay` (gửi có thời điểm khả dụng), hay **consumer priority** (ưu tiên phân phối cho consumer trên một số broker). Chúng có mục đích và hành vi khác nhau.

> **Quy tắc:** “priority 8” có nghĩa là gửi message với mức ưu tiên 8; không có nghĩa là “phải xử lý trước tất cả message priority 4”, cũng không có nghĩa là “xử lý trong vòng 8 giây”.

## 3. Ưu tiên, thứ tự nhận và thứ tự xử lý là ba lớp khác nhau

Hãy xem sơ đồ sau:

```text
Producer                              Broker                  Consumer
--------                              ------                  --------
send A, priority 4  ----------------> queue
send B, priority 8  ----------------> queue
                                       |
                         provider chọn thứ tự dispatch
                                       |
                             B? ------+------> xử lý B?
                             A? ------------- > xử lý A?

Hợp đồng nghiệp vụ riêng của order-42:
apply sequence=1  ->  apply sequence=2
```

**A và B có thể đến theo thứ tự nào?** Phụ thuộc điều kiện và provider. Nếu consumer đã nhận A trước khi B tới, B không thể “quay thời gian” để đến trước A. Nếu cả hai nằm chờ trên broker, B có thể được ưu tiên và vượt A; tuy nhiên điều đó không được bảo đảm. Nếu nhiều consumer cùng nhận, thứ tự **hoàn tất tác vụ nghiệp vụ** còn có thể khác thứ tự từng message được chuyển tới consumer.

Một bảng phân biệt:

| Khía cạnh | Có thể dựa vào điều gì? | Không nên suy ra |
| --- | --- | --- |
| Priority | Mức ưu tiên từ `0` đến `9` là thông tin gửi của message; provider cố gắng ưu tiên expedited | Priority cao chắc chắn vượt mọi priority thấp |
| JMS message order | Chuẩn có ràng buộc thứ tự đối với các message một session gửi vào cùng destination, **với các ngoại lệ được định nghĩa** | Mọi message trên broker luôn theo một FIFO toàn cục |
| Queue có nhiều consumer | Một message queue được phân phối cho một consumer phù hợp | Mọi consumer cùng xử lý theo thứ tự gửi; thứ tự hoàn tất giống thứ tự nhận |
| Nhiều producer/session | Thứ tự phải được thiết kế rõ nếu cần liên kết giữa các luồng | JMS bảo đảm thứ tự của message gửi từ những session khác nhau |
| Business consistency | Sequence, idempotency, đồng bộ trên từng aggregate và cách xử lý gap/out-of-order | Có priority là không cần sequence hoặc kiểm soát tranh chấp |

## 4. Chuẩn Jakarta Messaging thực sự quy định thứ tự thế nào?

Phần **6.2.9 Message order** của Jakarta Messaging 3.1 đặt ra ràng buộc *một phần* (partial ordering), không phải FIFO toàn cục.

### 4.1. Phạm vi có ràng buộc thứ tự

Với các message một `Session` gửi đến **cùng một destination**, chuẩn yêu cầu thứ tự nhận theo thứ tự gửi, **sau khi xét các ngoại lệ**. Những ngoại lệ quan trọng bao gồm:

1. **Priority cao có thể vượt** message priority thấp đã gửi trước.
2. Message có **delivery time muộn hơn** có thể được chuyển sau message có thời điểm khả dụng sớm hơn.
3. Message `NON_PERSISTENT` có thể bị mất khi provider gặp lỗi.
4. Khi trộn `PERSISTENT` và `NON_PERSISTENT`, không được suy ra một thứ tự tổng quát giữa hai delivery mode; chuẩn duy trì ràng buộc trong phạm vi delivery mode và các điều kiện tương ứng.
5. Transaction có thể nhóm các message gửi thành một đơn vị atomic trên JMS; thứ tự trong transaction đối với **một destination** có ý nghĩa, không suy ra thứ tự xuyên nhiều destination.

Ví dụ khi mọi điều kiện thích hợp được giữ cố định:

```text
Cùng một Session, cùng queue Q, cùng priority và delivery mode,
không delivery delay can thiệp:
send A -> send B -> send C
  Ràng buộc thứ tự JMS có ý nghĩa cho phía nhận.

Cùng Session, Q:
send A (priority=4) -> send B (priority=8)
  B có thể vượt A theo ngoại lệ priority.

Session S1 send A; Session S2 send B:
  Không có thứ tự chung do JMS bảo đảm giữa hai session.
```

Lưu ý: nhiều lần gọi độc lập `JmsTemplate.send(...)` **không tự tạo thành một `Session` liên tục duy nhất**. Template có thể lấy session qua connection/session factory hoặc session gắn transaction phù hợp. Vì thế, không nên dựa vào “hai dòng Java gọi `send` liên tiếp” để suy ra toàn bộ điều kiện của bảo đảm thứ tự theo session.

### 4.2. Những tác nhân làm thay đổi trật tự quan sát

- **Concurrent consumers:** nhiều listener container thread nhận các message khác nhau. Task xử lý lâu/chậm có thể hoàn tất sau task đến sau.
- **Prefetch/client buffering:** message có thể đã được dispatch vào buffer consumer trước khi message priority cao tới broker.
- **Redelivery:** rollback, lỗi hoặc mất kết nối có thể làm message được phân phối lại; ứng dụng cần idempotency.
- **Selector, topic subscription, nhiều destination:** mỗi consumer chỉ thấy tập message phù hợp; không thể suy ra một thứ tự toàn cục từ log của một consumer.
- **Delayed delivery, expiration và mixed delivery modes:** message có thể sẵn sàng vào các thời điểm khác nhau hoặc không còn khả dụng.
- **Provider-specific policy:** cùng một priority value nhưng các broker khác nhau có thể áp dụng thuật toán scheduling và prefetch khác nhau.

Ngay cả trong một consumer tuần tự, “nhận theo thứ tự” và “đã ghi dữ liệu thành công theo thứ tự” là hai trạng thái khác nhau. Nếu callback xử lý chuyển việc sang một executor rồi acknowledgment ngay, quá trình xử lý song song vẫn có thể đảo thứ tự.

## 5. Vì sao setPriority chưa chắc đã có tác dụng trong JmsTemplate?

`org.springframework.jms.core.JmsTemplate` hỗ trợ các thuộc tính Quality of Service (QoS):

- `setDeliveryMode(int)`: chế độ persistent/non-persistent.
- `setPriority(int)`: mức priority 0..9.
- `setTimeToLive(long)`: thời gian sống tính bằng millisecond; 0 thường nghĩa là không hết hạn do TTL.
- `setExplicitQosEnabled(boolean)`: quyết định template có dùng **các giá trị QoS của chính nó** khi gửi hay không.

**Điểm cần nhớ:** đặt `template.setPriority(8)` một mình **chưa đủ**. Phải bật `template.setExplicitQosEnabled(true)` nếu muốn `JmsTemplate` truyền các QoS values đã cấu hình vào lệnh gửi. Khi cờ này tắt, lệnh gửi sử dụng default QoS của `MessageProducer`/provider, có thể đã được admin cấu hình ngoài ứng dụng.

Ví dụ đơn giản:

```java
JmsTemplate template = new JmsTemplate(connectionFactory);
template.setPriority(8);
template.setExplicitQosEnabled(true);
```

Đây là một **đoạn Java bên trong phương thức cấu hình** có biến `connectionFactory` kiểu `jakarta.jms.ConnectionFactory`. Không cần tự tạo `MessageProducer` khi chỉ muốn chỉnh một mức priority cho tất cả message của template.

Cảnh báo quan trọng: bật explicit QoS sẽ khiến **deliveryMode, priority và timeToLive** đều đến từ cấu hình `JmsTemplate`, không chỉ mỗi priority. Nếu broker có chính sách default delivery mode/TTL riêng, bạn cần xác định và khai báo đủ ba giá trị mong muốn; đừng vô tình thay đổi độ bền message hay thời gian sống chỉ để tăng priority.

## 6. Ví dụ Spring Boot 3.x: normal và urgent dùng hai JmsTemplate

Ví dụ dùng Java 17+, Spring Boot 3.x/Spring Framework 6.x và ActiveMQ Artemis. Giả định broker đã chạy, có queue `orders.events` và user có quyền gửi; đây là **ứng dụng Spring Boot**, không phải chương trình Java SE chỉ cần `javac`.

Mục tiêu: gửi `OrderCreated` có priority 4 và `OrderCancelled` có priority 8 vào **cùng queue**. Việc gửi thành công **không cam kết** consumer sẽ nhận sự kiện hủy trước sự kiện tạo.

### 6.1. Dependency và cấu hình ngoài mã

Trong một dự án Spring Boot Gradle Groovy DSL đã có plugin Boot và dependency management, thêm:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
}
```

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
    destination: "${ORDERS_EVENTS_QUEUE:orders.events}"
```

Tài khoản broker và destination phải được provision đúng môi trường. Spring không tự bảo đảm queue vật lý đã tồn tại khi bạn gõ tên queue trong YAML.

### 6.2. Tạo hai template có QoS rõ ràng

File `src/main/java/demo/priority/JmsPriorityConfiguration.java`:

```java
package demo.priority;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;

@Configuration
public class JmsPriorityConfiguration {

    @Bean("normalJmsTemplate")
    public JmsTemplate normalJmsTemplate(ConnectionFactory connectionFactory) {
        return createTemplate(connectionFactory, 4);
    }

    @Bean("urgentJmsTemplate")
    public JmsTemplate urgentJmsTemplate(ConnectionFactory connectionFactory) {
        return createTemplate(connectionFactory, 8);
    }

    private static JmsTemplate createTemplate(
            ConnectionFactory connectionFactory, int priority) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setExplicitQosEnabled(true);
        template.setDeliveryMode(DeliveryMode.PERSISTENT);
        template.setPriority(priority);
        template.setTimeToLive(0L);
        return template;
    }
}
```

Vì cả hai template là singleton đã cấu hình xong, service có thể tái sử dụng chúng an toàn theo hợp đồng của `JmsTemplate`. Không thay đổi `setPriority` trên một singleton đang được nhiều luồng sử dụng để xử lý riêng từng request: đó là **thay đổi trạng thái chia sẻ**. Hai template có tên rõ ràng tránh nhầm lẫn trong ví dụ.

`DeliveryMode.PERSISTENT` và TTL bằng 0 là lựa chọn minh họa, **cần đối chiếu chính sách hạ tầng** trước khi áp dụng. Chúng không tự biến quy trình xử lý thành exactly-once.

### 6.3. Service gửi message có sequence riêng

File `src/main/java/demo/priority/OrderEventPublisher.java`:

```java
package demo.priority;

import jakarta.jms.TextMessage;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {
    private final JmsTemplate normalTemplate;
    private final JmsTemplate urgentTemplate;
    private final String destination;

    public OrderEventPublisher(
            @Qualifier("normalJmsTemplate") JmsTemplate normalTemplate,
            @Qualifier("urgentJmsTemplate") JmsTemplate urgentTemplate,
            @Value("${app.jms.destination}") String destination) {
        this.normalTemplate = normalTemplate;
        this.urgentTemplate = urgentTemplate;
        this.destination = destination;
    }

    public void publishCreated(String orderId) {
        send(normalTemplate, "OrderCreated", orderId, 1L);
    }

    public void publishCancelled(String orderId) {
        send(urgentTemplate, "OrderCancelled", orderId, 2L);
    }

    private void send(
            JmsTemplate template, String eventType,
            String orderId, long sequence) {
        template.send(destination, session -> {
            TextMessage message =
                    session.createTextMessage(eventType + ":" + orderId);
            message.setStringProperty("eventType", eventType);
            message.setStringProperty("aggregateId", orderId);
            message.setLongProperty("sequence", sequence);
            return message;
        });
    }
}
```

`aggregateId` và `sequence` là **application properties**, phục vụ kiểm tra thứ tự nghiệp vụ. `JMSPriority` là **standard header** do provider điền theo QoS của lệnh gửi. Không gọi `message.setJMSPriority(...)` trong callback; code dùng mức priority của từng template.

Đây là ví dụ với thứ tự cố định 1 và 2 để quan sát hai message. Trong ứng dụng thật, sequence phải đến từ nguồn trạng thái có kiểm soát (database/aggregate/outbox) và tăng một cách nhất quán theo từng `aggregateId`, chứ không hardcode theo tên loại sự kiện.

### 6.4. Main và runner dùng cho demo

File `src/main/java/demo/priority/DemoApplication.java`:

```java
package demo.priority;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

File `src/main/java/demo/priority/PriorityDemoRunner.java`:

```java
package demo.priority;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("priority-demo")
public class PriorityDemoRunner implements ApplicationRunner {
    private final OrderEventPublisher publisher;

    public PriorityDemoRunner(OrderEventPublisher publisher) {
        this.publisher = publisher;
    }

    @Override
    public void run(ApplicationArguments args) {
        publisher.publishCreated("order-42");
        System.out.println("Đã gửi OrderCreated (priority 4)");
        publisher.publishCancelled("order-42");
        System.out.println("Đã gửi OrderCancelled (priority 8)");
    }
}
```

Thiết lập `JMS_USER`, `JMS_PASSWORD` và broker/queue trước. Trong dự án Gradle Spring Boot có task `bootRun`, chạy:

```bash
./gradlew bootRun --args='--spring.profiles.active=priority-demo'
```

Nếu cả hai lần `JmsTemplate.send(...)` kết thúc thành công, **hai dòng ứng dụng** xuất hiện theo thứ tự:

```text
Đã gửi OrderCreated (priority 4)
Đã gửi OrderCancelled (priority 8)
```

Đây không phải toàn bộ stdout của Spring Boot và **không phải thứ tự mà consumer đã xử lý**. Broker có thể nhận/chuyển message đầu tiên trước khi message thứ hai được gửi, hoặc trì hoãn việc dispatch theo chính sách của nó. Không dùng hai dòng log này để chứng minh priority đã làm đảo thứ tự.

Chỉ bật profile `priority-demo` trong môi trường thử nghiệm; mỗi lần khởi động sẽ gửi lại cùng hai message có `aggregateId`/`sequence`, điều này phải được tách biệt với dữ liệu production.

## 7. Cách đọc JMSPriority ở phía nhận

Một message nhận được qua listener có thể được kiểm tra header chuẩn trực tiếp. Ví dụ sau là một **đoạn method** trong bean listener Spring JMS đã bật `@EnableJms` và có listener container được cấu hình:

```java
@JmsListener(destination = "${app.jms.destination}")
public void inspect(jakarta.jms.Message message)
        throws jakarta.jms.JMSException {
    String aggregateId = message.getStringProperty("aggregateId");
    long sequence = message.getLongProperty("sequence");
    int priority = message.getJMSPriority();
    System.out.printf(
            "aggregate=%s sequence=%d JMSPriority=%d%n",
            aggregateId, sequence, priority);
}
```

Để biên dịch đoạn này trong class listener, cần import `org.springframework.jms.annotation.JmsListener`; ứng dụng phải kích hoạt `@EnableJms` trong một lớp cấu hình. Nếu số liệu quan sát được phù hợp cấu hình template thì:

```text
aggregate=order-42 sequence=1 JMSPriority=4
aggregate=order-42 sequence=2 JMSPriority=8
```

Hai dòng này là **ví dụ các dòng có thể xuất hiện**, không khẳng định chúng xuất hiện theo thứ tự đó. Vị trí log thực tế cũng còn tùy broker và nhiều consumer. Đặc biệt, chỉ riêng việc nhìn thấy header priority 8 **không chứng minh broker đã ưu tiên dispatch message đó**.

Lưu ý: nếu listener ném lỗi/rollback và nhận lại message, log có thể xuất hiện nhiều lần. Không dùng log thô như một bảng thứ tự tác động nghiệp vụ đã commit thành công.

## 8. Priority không bảo đảm FIFO nghiệp vụ: ba tình huống

### Tình huống A: message mới có priority cao hơn

```text
t0: order-42 / sequence=1 / priority=4  -> tới queue
t1: order-42 / sequence=2 / priority=8  -> tới queue
t2: consumer nhận sequence=2            -> có thể xảy ra
t3: consumer nhận sequence=1
```

Nếu cập nhật trạng thái theo đúng thứ tự nghiệp vụ là yêu cầu bắt buộc, consumer phải nhận biết `sequence=2` chưa sẵn sàng khi `sequence=1` chưa được áp dụng. Ưu tiên chỉ là gợi ý lịch điều phối message.

### Tình huống B: cùng priority nhưng nhiều session

```text
Producer A / Session A ---- send "order-42#1" ---\
                                               \ 
                                                > queue Q
                                               /
Producer B / Session B ---- send "order-42#2" ---/
```

Jakarta Messaging không cung cấp thứ tự toàn cục giữa hai session. Mỗi producer nhìn thấy log “send thành công” cũng không đủ để xác định event nào có quyền được áp dụng trước về mặt nghiệp vụ. Sequence phải được tạo tại nguồn có thứ tự đáng tin cậy; nếu hai producer tự tăng bộ đếm độc lập, sequence đã sai ngay từ đầu.

### Tình huống C: delivery đúng nhưng xử lý xong đảo thứ tự

```text
Consumer 1 nhận #1 -> gọi API mất 3 giây -> commit muộn
Consumer 2 nhận #2 -> gọi API mất 0,1 giây -> commit trước
```

Ngay cả khi broker đã phân phát `#1` trước `#2`, xử lý song song có thể commit sai thứ tự. Cách giải quyết thuộc về **concurrency control, idempotency và transaction boundary** của nghiệp vụ, không nằm trong `JMSPriority`.

## 9. Thiết kế hợp đồng thứ tự rõ ràng khi nghiệp vụ cần nó

### 9.1. Chỉ định aggregate và sequence

Một hợp đồng event điển hình có thể gồm:

| Trường | Ý nghĩa |
| --- | --- |
| `eventId` | ID duy nhất của một event, dùng deduplication |
| `aggregateId` | ID đối tượng cần giữ thứ tự cục bộ, ví dụ `order-42` |
| `sequence` | Số phiên bản tăng dần theo aggregate, ví dụ 1, 2, 3 |
| `eventType` | Loại sự kiện và cách áp dụng |
| `schemaVersion` | Phiên bản schema để tương thích |
| `JMSPriority` | Gợi ý QoS khi gửi, **không phải nguồn xác định thứ tự** |

Với những event ảnh hưởng cùng một aggregate, **quy tắc xử lý** có thể là:

- `sequence == lastApplied + 1`: đủ điều kiện áp dụng theo thứ tự.
- `sequence <= lastApplied`: có thể là bản trùng/lỗi phát lại; đối chiếu `eventId`, bỏ qua tác động lặp khi thích hợp.
- `sequence > lastApplied + 1`: có gap; không tự ý commit event vượt trước mà cần chính sách đợi, retry/backoff hoặc lưu pending có kiểm soát.

Nếu sequence không liên tục do hệ thống có ý nghĩa riêng (ví dụ dùng database version khác nhau), điều kiện phải được điều chỉnh theo hợp đồng thật, không áp dụng máy móc công thức `last + 1`.

### 9.2. Ví dụ Java 17 độc lập: nhận ra event tới sai thứ tự

Ví dụ sau chỉ mô phỏng **business sequence**. Nó không gọi JMS và không tạo queue; nhờ vậy có thể biên dịch/chạy độc lập và chứng minh cách xử lý thứ tự trước khi tích hợp với broker.

File `SequenceGateDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;

public class SequenceGateDemo {
    private final Map<String, Long> lastApplied = new HashMap<>();

    void onEvent(String aggregateId, long sequence) {
        long last = lastApplied.getOrDefault(aggregateId, 0L);

        if (sequence <= last) {
            System.out.println("DUPLICATE " + aggregateId + "#" + sequence);
            return;
        }
        if (sequence > last + 1) {
            System.out.println("GAP " + aggregateId + "#" + sequence
                    + " (waiting for " + (last + 1) + ")");
            return;
        }

        lastApplied.put(aggregateId, sequence);
        System.out.println("APPLY " + aggregateId + "#" + sequence);
    }

    public static void main(String[] args) {
        SequenceGateDemo gate = new SequenceGateDemo();

        gate.onEvent("order-42", 2);
        gate.onEvent("order-42", 1);
        gate.onEvent("order-42", 2);
        gate.onEvent("order-42", 2);
    }
}
```

Biên dịch/chạy:

```bash
javac SequenceGateDemo.java
java SequenceGateDemo
```

Stdout chính xác:

```text
GAP order-42#2 (waiting for 1)
APPLY order-42#1
APPLY order-42#2
DUPLICATE order-42#2
```

Đây là **mô hình học thuật chạy trong một JVM và một thread**. Với production:

- Không lưu `lastApplied` chỉ trong `HashMap`; ứng dụng restart sẽ mất trạng thái.
- Cập nhật `lastApplied` cùng tác động nghiệp vụ bằng transaction/CAS/optimistic lock có kiểm soát.
- Đồng bộ việc xử lý cùng một `aggregateId` để hai consumer không cùng vượt qua check `last + 1`.
- Message bị gap phải có nơi lưu chờ hoặc cơ chế retry an toàn, giám sát và dead-letter sau giới hạn; đừng vô hạn reject để broker redeliver nóng liên tục.
- Quy tắc duplicate cần `eventId` và định nghĩa idempotency phù hợp, vì `sequence <= last` không bao quát mọi trường hợp replay/schema.
- Nếu event có thể mất hẳn, “đợi sequence thiếu” cần chính sách timeout/reconciliation, không thể đợi mãi.

Hợp đồng này cho phép business giữ trật tự **dù broker đôi lúc giao message priority cao trước**.

### 9.3. Message groups và giới hạn của chúng

Một số broker hỗ trợ message grouping theo `JMSXGroupID` hoặc cơ chế tương đương để gắn các message thuộc cùng một nhóm vào một consumer. Ví dụ đặt application property:

```java
message.setStringProperty("JMSXGroupID", orderId);
```

Đây là một **đoạn trong `MessageCreator`** có biến `message` và `orderId`, yêu cầu kiểm tra khả năng hỗ trợ của provider. Message grouping có thể giúp tránh nhiều consumer xử lý cùng nhóm song song, nhưng **không tự khôi phục event đã đảo thứ tự bởi priority**, không thay thế sequence/idempotency, và cần xác minh hành vi khi consumer failover/rebalance.

Nếu nghiệp vụ yêu cầu thứ tự tuyệt đối giữa Created và Cancelled trên cùng order, giải pháp chắc chắn hơn có thể là cùng một luồng cho aggregate, không cấp priority khác nhau giữa các event phụ thuộc thứ tự, dùng grouping phù hợp và kiểm tra sequence tại consumer. Vẫn phải xử lý redelivery và sự cố.

## 10. Kiểm thử priority đúng cách

Một bài kiểm thử cần phân biệt ba cấp độ:

| Cấp độ | Điều nên xác nhận | Điều không nên assert |
| --- | --- | --- |
| Unit test cấu hình | Normal template có priority 4, urgent có priority 8, explicit QoS bật, deliveryMode/TTL đúng | Message nào sẽ đến consumer trước |
| Integration test với broker | Message khi gửi có `JMSPriority` mong đợi, tài khoản/destination đúng, hai message được chuyển phát trong điều kiện thử | Mọi broker/mọi lúc đều đưa priority cao lên đầu |
| Kiểm thử nghiệp vụ | Consumer không commit `#2` trước `#1` và xử lý duplicate/gap đúng | Chỉ cần tăng priority là đạt thứ tự |

### 10.1. Unit test cấu hình không cần broker

Với `spring-boot-starter-test` và JUnit Jupiter, file `src/test/java/demo/priority/JmsPriorityConfigurationTest.java`:

```java
package demo.priority;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import org.junit.jupiter.api.Test;
import org.springframework.jms.core.JmsTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;

class JmsPriorityConfigurationTest {
    private final JmsPriorityConfiguration config =
            new JmsPriorityConfiguration();

    @Test
    void templatesUseExpectedQos() {
        ConnectionFactory connectionFactory = mock(ConnectionFactory.class);

        JmsTemplate normal = config.normalJmsTemplate(connectionFactory);
        JmsTemplate urgent = config.urgentJmsTemplate(connectionFactory);

        assertTrue(normal.isExplicitQosEnabled());
        assertTrue(urgent.isExplicitQosEnabled());
        assertEquals(4, normal.getPriority());
        assertEquals(8, urgent.getPriority());
        assertEquals(DeliveryMode.PERSISTENT, normal.getDeliveryMode());
        assertEquals(DeliveryMode.PERSISTENT, urgent.getDeliveryMode());
        assertEquals(0L, normal.getTimeToLive());
        assertEquals(0L, urgent.getTimeToLive());
    }
}
```

Với dependency test:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Chạy:

```bash
./gradlew test --tests demo.priority.JmsPriorityConfigurationTest
```

Khi test chạy thành công, Gradle có thể báo `BUILD SUCCESSFUL`, nhưng log chi tiết phụ thuộc phiên bản và task configuration. Test này chỉ xác minh cấu hình bean, **không gửi message thật**.

### 10.2. Integration test với broker

Để kiểm tra hành vi thật, hãy:

1. Tạo queue thử nghiệm riêng, cấu hình chính sách priority của broker và xác minh nó đã có.
2. Dừng consumer trước khi gửi các message nếu mục tiêu là quan sát broker chọn từ backlog có cả priority thấp/cao; ghi rõ consumer prefetch và broker version.
3. Gửi các message có `eventId`/`sequence`/priority khác nhau, đọc `getJMSPriority()` tại consumer và ghi thời điểm nhận/commit.
4. Lặp trên kịch bản một consumer, nhiều consumer, nhiều session/producer, restart broker và redelivery nếu môi trường cho phép.
5. Kiểm tra cả SLA/độ trễ nhóm khẩn cấp lẫn việc các message bình thường có bị **starvation** khi luồng priority cao liên tục không.

Một lần chạy có kết quả `priority 8` trước `priority 4` chỉ chứng minh **một quan sát** ở điều kiện đó. Không viết một integration test bắt buộc thứ tự cố định `8 -> 4` cho mọi broker; đó không phải hợp đồng chuẩn. Với hợp đồng nghiệp vụ `sequence=1 -> 2`, hãy kiểm thử việc commit theo thứ tự đúng một cách độc lập với thứ tự nhận.

## 11. Các lỗi thường gặp

| Sai lầm | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Gọi `setPriority(9)` mà không bật `explicitQosEnabled` | Template có thể tiếp tục dùng QoS mặc định của provider | Bật `setExplicitQosEnabled(true)` và xác nhận cả deliveryMode/TTL |
| `message.setJMSPriority(9)` trong `MessageCreator` | Setter header này dành cho provider khi gửi | Cấu hình QoS trên `JmsTemplate`/`MessageProducer` |
| Cho rằng priority 9 chắc chắn nhận trước priority 4 | Jakarta Messaging chỉ yêu cầu cố gắng ưu tiên, không strict ordering | Tách mục tiêu độ trễ khỏi hợp đồng thứ tự |
| Dùng `priority` thay cho `sequence` | Priority thể hiện mức quan trọng, không phải phiên bản sự kiện | Dùng `aggregateId`, `sequence`, `eventId` |
| Gửi bằng nhiều template/session rồi khẳng định FIFO | Bảo đảm thứ tự JMS không phải thứ tự toàn cục giữa session | Thiết kế ordering theo aggregate tại nguồn và consumer |
| Tăng đồng thời listener concurrency để nhanh hơn, nhưng bỏ kiểm soát trạng thái | Xử lý song song có thể commit đảo thứ tự | Kiểm soát tranh chấp, grouping và version check |
| Thấy hai message được log theo thứ tự producer và suy ra consumer giống vậy | Send completion không phải consume/business commit | Theo dõi log/metrics nhận và transaction nghiệp vụ |
| Nhầm `JMSPriority` với consumer priority | Một cái áp dụng message, cái kia áp dụng chính sách phân phối consumer tùy broker | Gọi đúng tên cơ chế và kiểm tra tài liệu provider |
| Bật explicit QoS chỉ để chỉnh priority, vô tình thay đổi TTL/delivery mode | Cờ tác động cả ba QoS parameters | Khai báo toàn bộ QoS hoặc dùng producer-level API có chủ đích |
| Tin rằng grouping loại bỏ redelivery/out-of-order | Grouping chủ yếu hỗ trợ phân phối cùng nhóm, có giới hạn provider | Vẫn cần idempotency, sequence và recovery policy |

## 12. Câu hỏi tự kiểm tra

1. Priority mặc định của JMS là bao nhiêu? Mức `0..4` và `5..9` biểu thị điều gì?
2. Tại sao `template.setPriority(8)` có thể chưa làm message được gửi ở mức 8?
3. Nếu producer gửi `#1` priority 4 rồi `#2` priority 8 vào cùng queue, chuẩn có buộc consumer nhận `#1` trước `#2` không? Ngoại lệ nào áp dụng?
4. Tại sao hai lần gọi `JmsTemplate.send` liên tiếp không đủ để khẳng định chúng sử dụng cùng một JMS `Session`?
5. `JMSXGroupID` giải quyết vấn đề nào và tại sao vẫn cần `sequence`?
6. Nếu `#2` đến trước `#1`, consumer nên làm gì để không commit sai trạng thái? Việc giữ state đó cần điều kiện concurrency/transaction nào?

**Ghi nhớ:** Priority là **gợi ý QoS khi gửi** giúp broker có thể ưu tiên message khẩn cấp. Thứ tự JMS chỉ được quy định trong các phạm vi cụ thể và có ngoại lệ. Trật tự nghiệp vụ cần một hợp đồng riêng dựa trên phiên bản/số thứ tự, idempotency và xử lý tranh chấp.

### Tài liệu tham khảo

- Jakarta Messaging 3.1, `6.2.9 Message order` và `3.4 Message header fields`: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Jakarta Messaging 3.1 API, `Message.getJMSPriority()` và `setJMSPriority(int)`: https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message
- Jakarta Messaging API, `MessageProducer.setPriority(int)`: https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageproducer
- Spring Framework 6.2, Using `JmsTemplate` và explicit QoS: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html
- Spring Framework 6.2, `JmsTemplate` API: https://docs.spring.io/spring-framework/docs/6.2.x-SNAPSHOT/javadoc-api/org/springframework/jms/core/JmsTemplate.html
- ActiveMQ Artemis, Message Priority: https://artemis.apache.org/components/artemis/documentation/latest/examples.html
