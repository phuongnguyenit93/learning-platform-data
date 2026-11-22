# Time-to-live (TTL) và message hết hạn trước khi được giao trong Spring JMS

## 1. Bài toán: thông điệp đã quá hạn còn giá trị không?

Giả sử ứng dụng thương mại điện tử đưa công việc vào queue để một consumer xử lý bất đồng bộ:

- Đơn hàng vừa tạo cần gửi email xác nhận; nếu backlog lớn, email trễ vài phút vẫn có thể chấp nhận.
- Thông báo “giá ưu đãi còn hiệu lực trong 30 giây” không nên được gửi sau một giờ.
- Tác vụ cập nhật cache chỉ còn hữu ích trong vài giây.
- Một lệnh thanh toán lại có thể **không được tự ý hủy** chỉ vì queue đang chậm; cần quy tắc nghiệp vụ và đối soát riêng.

Trong Jakarta Messaging (JMS), **time-to-live (TTL)** là khoảng thời gian tối đa mà một message được xem là còn hiệu lực để nhà cung cấp dịch vụ giao cho consumer. Khi vượt qua thời điểm hết hạn, provider **nên loại bỏ** message chưa được giao, và consumer thông thường không nên nhận nó nữa. Tuy nhiên, đặc tả không cam kết tuyệt đối rằng một client sẽ không bao giờ nhìn thấy message đã hết hạn; ứng dụng có yêu cầu chặt chẽ vẫn phải tự kiểm tra deadline nghiệp vụ.

TTL là **một chính sách chất lượng gửi (quality of service – QoS)**. Nó được đặt từ phía **producer** khi gửi, không phải là khoảng chờ receive của consumer và cũng không phải thời gian xử lý tối đa cho một job đã được giao.

### 1.1. Phân biệt các mốc thời gian

~~~text
t = 0 ms     Producer gửi message "refresh cache", TTL = 5 000 ms
                 |
                 +--> JMS provider tính JMSExpiration ~= sendTime + 5 000
                 |
t = 1 000    Message vẫn đang chờ trong queue        (còn hạn)
t = 4 000    Consumer nhận được                       (hợp lệ)
t = 5 000    Deadline vận chuyển theo JMS
t = 8 000    Nếu tới đây message vẫn chưa được giao,
             provider nên loại bỏ nó thay vì giao mới.
~~~

Nếu consumer nhận ở t=4 giây rồi xử lý tới t=9 giây, TTL **không tự ngắt callback** ở t=5 giây. Muốn dừng một tác vụ sau một business deadline, consumer cần logic riêng: kiểm tra timestamp/deadline trước khi áp dụng side effect, giới hạn thời gian thực thi, transaction và cơ chế hủy có kiểm soát.

### 1.2. Vì sao TTL quan trọng?

TTL tránh cho các queue chứa hàng loạt message đã mất giá trị, giảm độ trễ cho message mới và giới hạn một loại công việc tồn đọng. Nhưng đặt TTL quá ngắn có thể khiến **message biến mất mà chưa hề được consumer xử lý**, đặc biệt trong lúc deploy, mất kết nối, broker quá tải hoặc consumer bị dừng. Vì thế phải cân nhắc tính chất dữ liệu, SLA, backlog và khả năng khôi phục.

## 2. Định nghĩa chính xác: TTL và JMSExpiration

Jakarta Messaging 3.1 quy định **TTL có đơn vị millisecond**. Giá trị mặc định của MessageProducer là **0**, nghĩa là **không hết hạn theo TTL**. Với TTL dương, JMS provider tính thời điểm hết hạn tuyệt đối:

\[
\text{JMSExpiration} = \text{thời điểm gửi} + \text{timeToLive}
\]

Ở đây “thời điểm gửi” dùng để tính là lúc **client gửi message**, không phải lúc transaction commit. JMSExpiration là số millisecond tính từ Unix epoch (1970-01-01T00:00:00Z).

Ví dụ giả định:

| Thuộc tính | Giá trị | Ý nghĩa |
| --- | --- | --- |
| Thời điểm gửi | 2026-10-30T08:00:00Z | Mốc mẫu |
| TTL | 30.000 ms | 30 giây |
| JMSExpiration | 2026-10-30T08:00:30Z | Mốc hết hạn tuyệt đối |
| Consumer khả dụng lúc 08:01:00Z | Muộn 30 giây | Message chưa giao thường đã hết giá trị để deliver |

Mốc trên chỉ minh họa cách tính, không phải thời gian thực của môi trường. Nếu send bị hoãn bởi transaction hoặc tầng truyền tải, TTL vẫn đã bắt đầu tính theo mốc client send.

**Ba lưu ý quan trọng:**

1. **TTL=0 không phải hết hạn tức thì.** Trong JMS, 0 nghĩa là “không hết hạn”. Trong một số cấu hình expiry riêng của broker, số 0 có thể có ý nghĩa khác; không được đem ý nghĩa đó gán cho JMS MessageProducer.
2. **Không tự gọi message.setJMSExpiration(...) để thiết lập TTL.** Setter này dành cho provider để ghi header khi gửi. Producer ứng dụng phải dùng MessageProducer.setTimeToLive(...) hoặc send(..., timeToLive), hay API gửi tương ứng của Spring.
3. **JMSExpiration khác JMSTimestamp.** JMSTimestamp mô tả thời điểm message được handed off để gửi; JMSExpiration là deadline. Khi producer đưa hint tắt timestamp, JMSTimestamp có thể là 0; không dùng nó thay cho contract JMSExpiration.

### 2.1. Giá trị trong header được đặt khi nào?

Trước khi send, code ứng dụng có thể tạo TextMessage nhưng giá trị JMSExpiration chưa được provider thiết lập. Sau khi send hoàn tất, provider điền JMSExpiration trên message đã gửi; khi consumer nhận, header mang giá trị tương ứng.

~~~java
TextMessage message =
        session.createTextMessage("refresh-cache");

// Không dùng setJMSExpiration(...) từ application.
producer.send(
        message,
        DeliveryMode.PERSISTENT,
        4,
        5_000L);

long expiresAtEpochMs = message.getJMSExpiration();
System.out.println(expiresAtEpochMs > 0);
~~~

Đây là **snippet** cần Session/producer đã tạo, chưa phải chương trình độc lập. Khi gửi thành công với TTL 5 giây, điều kiện phía cuối thông thường là true; con số epoch cụ thể phụ thuộc thời gian chạy nên không đưa vào stdout cố định.

Với TTL=0, JMSExpiration bằng 0, nghĩa là không có thời điểm hết hạn do TTL.

### 2.2. TTL âm và giá trị tràn

TTL phải là một khoảng thời gian hợp lệ **không âm**; tránh truyền số âm và không giả định mọi JMS provider tự xử lý thống nhất. Khi chuyển cấu hình từ Duration sang millisecond, kiểm tra giá trị có vừa miền long, có bị nhầm đơn vị và có ý nghĩa thực tế hay không. Không tùy tiện đặt Long.MAX_VALUE để biểu diễn vô hạn; dùng TTL=0 nếu contract cho phép không hết hạn.

## 3. Vòng đời: message còn hạn, message hết hạn và thời điểm giao

~~~mermaid
stateDiagram-v2
    [*] --> Created: Tạo message
    Created --> Sent: producer.send
    Sent --> Waiting: Broker lưu/chờ
    Waiting --> Delivered: Consumer nhận khi còn hạn
    Waiting --> Expired: Đã vượt JMSExpiration
    Expired --> Discarded: Provider loại bỏ
    Expired --> ExpiryAddress: Broker cấu hình expiry address
    Delivered --> Processed: Ứng dụng xử lý/ack hoặc commit
    Delivered --> Redelivered: Xử lý lỗi và broker giao lại nếu còn điều kiện
    Redelivered --> Delivered: Giao lại theo chính sách
~~~

Sơ đồ diễn giải luồng phổ biến, không mô tả chính xác mọi trạng thái nội bộ của từng broker. Bước từ Expired có thể diễn ra lúc broker quét định kỳ, trước dispatch hoặc khi consumer yêu cầu; do đó không nên suy đoán thời điểm queue depth giảm chỉ bằng đồng hồ.

### 3.1. Nếu message hết hạn trong queue

Kịch bản cơ bản:

1. Producer gửi message ở thời điểm t0 với TTL 2 giây.
2. Broker nhận message nhưng consumer đang offline.
3. Sau 5 giây, consumer khởi động.
4. Provider có trách nhiệm tuân thủ cơ chế expiration và **nên bỏ message đã quá hạn**; client thông thường receive(timeout) không lấy được message cũ nữa.
5. Nếu không có message khác, receive(timeout) trả null khi hết thời gian chờ.

Không nên ghi thành “JMS bảo đảm 100% không bao giờ giao message quá hạn”: đặc tả nói client **không nên** nhận message đã hết hạn nhưng **không bảo đảm điều đó tuyệt đối**. Nếu hậu quả nghiệp vụ lớn, kiểm tra deadline tại consumer và thiết kế xử lý idempotent.

### 3.2. Nếu message đã được giao trước khi hết hạn

Giả sử TTL 5 giây, consumer nhận ở giây thứ 4 và cần 8 giây để xử lý:

~~~text
t=0s             t=4s                 t=5s             t=12s
send              receive              JMSExpiry         xử lý hoàn tất
 |------------------|--------------------|-------------------|
                    ^ consumer đã nhận trước hạn
~~~

TTL không phải timeout cho method onMessage, không kill Java thread và không tự rollback transaction đang xử lý. Nếu nghiệp vụ yêu cầu không xử lý quá thời hạn, consumer phải có deadline check trước side effect hoặc checkpoint phù hợp, nhưng vẫn cần xem xét race condition và transaction.

### 3.3. Retry/redelivery có làm TTL bắt đầu lại?

**Không theo nghĩa JMS gốc.** Với cùng một message chưa ack/commit, broker có thể giao lại do rollback hoặc consumer failure; deadline JMSExpiration đã được ghi khi gửi ban đầu và không tự reset chỉ vì có thêm một lần delivery.

Ngược lại, nếu ứng dụng nhận message rồi **tạo một message mới** gửi lại, đó là một lần send mới; TTL của message mới được tính theo thời điểm gửi mới, trừ khi ứng dụng tự mang business deadline và áp dụng chính sách khác.

Vì thế retry theo kiểu re-publish có thể kéo dài công việc vượt hạn một cách vô ý. Nếu business deadline phải được giữ xuyên suốt, gắn deadline tuyệt đối vào payload/metadata và tính TTL còn lại lúc republish:

~~~text
remainingMs = max(0, deadlineEpochMillis - currentTimeMillis)
~~~

Khi remainingMs <= 0, **không gửi lại**: vì đặt JMS TTL=0 sẽ biến message thành không hết hạn, ngược hẳn mục tiêu.

## 4. API JMS thuần: đặt TTL ở producer hoặc từng lần send

### 4.1. Thiết lập TTL mặc định trên MessageProducer

~~~java
MessageProducer producer = session.createProducer(queue);
producer.setTimeToLive(5_000L);  // 5 giây, áp cho send sau đó.
producer.send(session.createTextMessage("update-1"));
producer.send(session.createTextMessage("update-2"));
~~~

Đây là snippet: Queue và Session phải có sẵn. Nếu không chỉ định QoS trong send(...), producer sử dụng các setting hiện hành. Default TTL của MessageProducer theo API là 0: message không hết hạn. Một số provider cho phép cấu hình mặc định ở cấp quản trị; cần đối chiếu môi trường chạy.

Chú ý: không gọi setTimeToLive(...) trên Message. QoS được điều khiển từ producer/send, còn JMSExpiration do provider ghi lên Message sau khi gửi.

### 4.2. Ghi đè TTL cho đúng một lần gửi

~~~java
producer.send(
        session.createTextMessage("flash-sale-alert"),
        DeliveryMode.PERSISTENT,
        6,
        2_000L); // TTL 2 giây

producer.send(
        session.createTextMessage("audit-event"),
        DeliveryMode.PERSISTENT,
        4,
        0L); // Không tự hết hạn theo JMS TTL
~~~

Overload send(message, deliveryMode, priority, timeToLive) cho phép mỗi message có TTL riêng. DeliveryMode và priority không đồng nhất với TTL: message PERSISTENT **vẫn hết hạn** nếu TTL dương; message NON_PERSISTENT có TTL=0 **không tự dưng trở thành persistent**.

Khi dùng producer chung nhiều thread, nhớ tuân thủ quy tắc JMS Session không được sử dụng đồng thời tùy tiện. Tốt nhất quản lý Session/Producer trong bối cảnh thích hợp và tránh đổi global TTL từ nhiều thread cạnh tranh.

### 4.3. Simplified API (JMSContext/JMSProducer)

Trong Jakarta Messaging 3.x, simplified API có:

~~~java
try (JMSContext context = factory.createContext()) {
    JMSProducer producer = context.createProducer()
            .setTimeToLive(5_000L);
    producer.send(destination, "hello");
}
~~~

Đây là snippet; factory và destination là các đối tượng đã được cung cấp. JMSProducer.setTimeToLive(long) trả lại JMSProducer để chain method; khác với MessageProducer.setTimeToLive(long) của classic API trả void. Không nhầm namespace jakarta.jms.* với javax.jms.* trong các ứng dụng Spring Boot 3/Spring Framework 6.

## 5. Spring JmsTemplate: gắn TTL với Quality of Service

### 5.1. Vì sao setTimeToLive thôi chưa chắc đủ?

JmsTemplate dùng cơ chế QoS của MessageProducer. Theo tài liệu Spring, khi **explicit QoS chưa bật**, lời gọi send thông thường có thể dùng giá trị mặc định của provider thay vì các giá trị do JmsTemplate cấu hình.

Để yêu cầu Spring gửi với TTL nhất định:

~~~java
JmsTemplate template = new JmsTemplate(connectionFactory);
template.setTimeToLive(5_000L);
template.setExplicitQosEnabled(true);

template.convertAndSend("orders.notifications", "expires-in-5s");
~~~

Đây là snippet trong ứng dụng đã có ConnectionFactory. Phương thức **setExplicitQosEnabled(true)** rất quan trọng nếu muốn chắc chắn template đưa deliveryMode, priority và timeToLive vào overload send có QoS thay vì dựa vào defaults của provider.

Những thiết lập liên quan:

| API JmsTemplate | Công dụng |
| --- | --- |
| setTimeToLive(long) | TTL của message được gửi, đơn vị millisecond. |
| setExplicitQosEnabled(boolean) | Bật dùng bộ QoS cấu hình trực tiếp khi send. |
| setDeliveryMode(int) | PERSISTENT hoặc NON_PERSISTENT. |
| setPriority(int) | Ưu tiên 0–9, mặc định JMS là 4. |
| setDeliveryDelay(long) | Trì hoãn thời điểm sớm nhất message được giao; **khác TTL**. |
| setReceiveTimeout(long) | Thời gian chờ một lời gọi receive; **không làm message hết hạn**. |

Khi dùng JmsTemplate như một Spring bean chia sẻ nhiều thread, cấu hình các property **trước khi bắt đầu sử dụng**. JmsTemplate thread-safe sau khi được cấu hình ổn định; không thay đổi TTL của bean dùng chung liên tục theo từng request vì có nguy cơ race condition.

### 5.2. Bean cấu hình rõ ràng

~~~java
@Configuration
class JmsQosConfig {

    @Bean
    JmsTemplate notificationTemplate(ConnectionFactory factory) {
        JmsTemplate template = new JmsTemplate(factory);
        template.setExplicitQosEnabled(true);
        template.setDeliveryMode(DeliveryMode.PERSISTENT);
        template.setPriority(4);
        template.setTimeToLive(30_000L);
        return template;
    }
}
~~~

Đây là snippet cấu hình, cần các import jakarta.jms.ConnectionFactory, DeliveryMode, org.springframework.context.annotation.Bean/Configuration và org.springframework.jms.core.JmsTemplate. Khi ứng dụng có nhiều TTL policy, thường rõ ràng hơn khi dùng **nhiều template/producer cấu hình tĩnh** theo lớp message, thay vì chỉnh TTL của cùng một bean trước mỗi send.

### 5.3. Cấu hình qua Spring Boot properties

Spring Boot 3.3 hỗ trợ cấu hình template bằng properties:

~~~properties
spring.jms.template.time-to-live=30s
spring.jms.template.receive-timeout=2s
~~~

Trong auto-configuration của Boot, việc đặt time-to-live (hoặc delivery-mode/priority) sẽ **bật explicit QoS** theo cơ chế của Spring Boot. Nếu tự tạo JmsTemplate bean hoàn toàn riêng và bỏ qua cấu hình tự động của Boot, các properties trên **không nhất thiết được áp dụng**; khi đó chủ động gọi setTimeToLive và setExplicitQosEnabled như ví dụ 5.1.

Nếu muốn biểu đạt rõ:

~~~properties
spring.jms.template.qos-enabled=true
spring.jms.template.time-to-live=30s
~~~

Lưu ý Spring Boot property dùng kiểu duration và nhận hậu tố 30s, 500ms..., còn API setTimeToLive(long) nhận **millisecond dạng số**. Đừng nhầm 30 với 30 giây: setTimeToLive(30L) nghĩa là 30 **milli**giây.

### 5.4. Một message cần TTL khác với policy chung

JmsTemplate.convertAndSend(...) với MessagePostProcessor phù hợp để gắn property/header nghiệp vụ, nhưng không có nghĩa MessagePostProcessor có thể gọi setJMSExpiration để thay TTL một cách chuẩn.

~~~java
jmsTemplate.convertAndSend(
        "orders.events",
        "order-created",
        message -> {
            message.setJMSType("order.created.v1");
            message.setStringProperty("TenantId", "acme");
            return message;
        });
~~~

Đây là snippet: nó thay đổi metadata, **không thiết lập TTL riêng**. Muốn TTL theo từng message, cân nhắc:

1. Tách các JmsTemplate bean với policy TTL riêng.
2. Sử dụng **ProducerCallback** và gọi producer.send(message, deliveryMode, priority, ttl) trực tiếp.
3. Tạo abstraction gửi của ứng dụng được inject cấu hình TTL, bảo đảm đồng bộ policy và kiểm tra.

~~~java
jmsTemplate.execute("orders.events", (session, producer) -> {
    TextMessage message =
            session.createTextMessage("short-lived");
    producer.send(
            message,
            DeliveryMode.PERSISTENT,
            4,
            750L);
    return null;
});
~~~

Đây là snippet trong Spring bean; cần import TextMessage, DeliveryMode. Khi tự gọi MessageProducer.send(...) trong callback, QoS ở overload đó quyết định cho lời gửi cụ thể; không giả định JmsTemplate tự ghi đè TTL của lệnh send do callback thực hiện.

## 6. Ví dụ tính thời hạn: TTL, receive timeout và queue backlog

Giả sử producer gửi vào queue Q lúc 10:00:00, TTL 3 giây, consumer tạo sau đó.

| Thời điểm | Sự kiện | Kết quả dự kiến |
| --- | --- | --- |
| 10:00:00 | Send m1, TTL=3s | Provider tính JMSExpiration 10:00:03 |
| 10:00:01 | Consumer chưa kết nối | m1 còn hạn |
| 10:00:03 | m1 hết hạn nhưng chưa được giao | Provider nên loại bỏ/expire theo policy |
| 10:00:06 | Consumer gọi receive(2s) | Thường nhận null nếu không có message khác |
| 10:00:08 | receive timeout hết | Thread không chờ nữa; **không liên quan đến TTL của m1** |

**Receive timeout không làm message biến mất.** Nếu consumer gọi receive(timeout=1000ms) mà không nhận được message, đó là giới hạn thời gian chờ của caller; các message còn sống vẫn có thể chờ consumer sau. TTL là thuộc tính được đặt từ lúc send.

### 6.1. Không nhầm TTL với thời gian lưu trữ vô hạn

Một message TTL=0 có nghĩa JMS không yêu cầu hết hạn theo TTL, nhưng điều này **không bảo đảm nó tồn tại mãi**. Những yếu tố có thể làm message không còn:

- DeliveryMode.NON_PERSISTENT và provider/broker restart.
- Queue bị xóa, quá giới hạn dung lượng, policy eviction/retention hoặc quản trị viên purge.
- Consumer khác đã nhận rồi acknowledge/commit.
- Bản thân broker hoặc hạ tầng bị mất dữ liệu/sự cố.
- Chính sách expiry/retention mà broker áp đặt từ phía quản trị.

TTL chỉ là **một yếu tố** trong lifecycle của message; không phải thỏa thuận lưu trữ vĩnh viễn.

## 7. Dự án chạy được: Spring Boot 3.3, Java 17, Artemis

Ví dụ thực hành cho thấy hai nhóm message cùng được gửi khi consumer chưa đọc:

- Message A có TTL ngắn: 250ms, sẽ quá hạn sau khi chương trình chờ 1,2 giây.
- Message B có TTL dài: 60 giây, vẫn được nhận bình thường.

Để tránh ảnh hưởng backlog từ lần chạy trước, mỗi lượt chạy tạo **hai tên queue duy nhất** bằng UUID. Trên Artemis demo cho phép auto-create, không cần cố định queue trước. Các dòng stdout được thiết kế không phụ thuộc UUID hoặc absolute expiration timestamp.

### 7.1. Chuẩn bị broker

Cần JDK 17+, Maven, Docker, cổng 61616 còn trống. Chạy container Apache ActiveMQ Artemis:

~~~bash
docker run --detach --rm --name ttl-demo-broker \
  -p 61616:61616 -p 8161:8161 \
  apache/artemis:latest-alpine
~~~

Chờ broker khởi động xong; dùng docker logs ttl-demo-broker nếu chưa kết nối được. Image demo dùng username/password artemis/artemis mặc định, **không dùng credentials demo trong production**. Nếu broker dùng cấu hình không cho tự tạo queue, hãy tạo các destination theo đúng permission thay vì cố khắc phục bằng tăng TTL.

Cấu trúc:

~~~text
jms-ttl-demo/
├── pom.xml
└── src/main/
    ├── java/example/jmsttl/TtlDemoApplication.java
    └── resources/application.properties
~~~

### 7.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>jms-ttl-demo</artifactId>
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
~~~

Spring Boot 3.x + Spring Framework 6.x sử dụng **jakarta.jms**, không phải javax.jms của các bản cũ. Dependency starter cung cấp Spring JMS và Artemis client; code không tự mở Connection hay Session vì JmsTemplate thực hiện việc đó.

### 7.3. application.properties

~~~properties
spring.main.web-application-type=none
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=artemis
spring.artemis.password=artemis
~~~

Ứng dụng là một CommandLineRunner, không mở HTTP server. Các ví dụ TTL được thiết lập trên những JmsTemplate local bên trong runner, để thấy chính xác API áp dụng QoS. Không cần cấu hình spring.jms.template.time-to-live cho demo này.

### 7.4. TtlDemoApplication.java

~~~java
package example.jmsttl;

import java.util.UUID;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class TtlDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(TtlDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(ConnectionFactory connectionFactory) {
        return args -> {
            String runId = UUID.randomUUID().toString().replace("-", "");
            String shortQueue = "demo.ttl.short." + runId;
            String longQueue = "demo.ttl.long." + runId;

            JmsTemplate shortLived = new JmsTemplate(connectionFactory);
            shortLived.setExplicitQosEnabled(true);
            shortLived.setDeliveryMode(DeliveryMode.PERSISTENT);
            shortLived.setPriority(4);
            shortLived.setTimeToLive(250L);

            JmsTemplate longLived = new JmsTemplate(connectionFactory);
            longLived.setExplicitQosEnabled(true);
            longLived.setDeliveryMode(DeliveryMode.PERSISTENT);
            longLived.setPriority(4);
            longLived.setTimeToLive(60_000L);

            JmsTemplate reader = new JmsTemplate(connectionFactory);
            reader.setReceiveTimeout(1_000L);

            shortLived.convertAndSend(shortQueue, "too-late");
            longLived.convertAndSend(longQueue, "still-valid");

            // Consumer chỉ bắt đầu nhận sau khi TTL ngắn đã qua.
            Thread.sleep(1_200L);

            Object expired = reader.receiveAndConvert(shortQueue);
            Message fresh = reader.receive(longQueue);

            if (!(fresh instanceof TextMessage text)) {
                throw new IllegalStateException(
                        "Expected unexpired TextMessage");
            }

            System.out.println("expired: " + expired);
            System.out.println("valid: " + text.getText());
            System.out.println(
                    "has-expiration: " + (text.getJMSExpiration() > 0));
        };
    }
}
~~~

Giải thích theo từng bước:

1. Mỗi lần chạy có hai tên queue với UUID khác nhau; tránh nhận nhầm message cũ từ những lượt demo trước.
2. Hai template đều được bật explicit QoS, nên setTimeToLive(250L) và setTimeToLive(60_000L) được dùng trong send.
3. Cả hai message được gửi trước khi reader bắt đầu receive. Nếu broker hỗ trợ auto-create queue, message nằm trong queue chờ.
4. Thread.sleep(1_200L) dài hơn TTL 250ms. Khi receiveAndConvert(shortQueue), message quá hạn thông thường đã bị broker loại bỏ nên kết quả null.
5. TTL 60 giây cho message còn lại cho phép reader.receive(longQueue) trả TextMessage; getJMSExpiration() có giá trị dương.
6. reader.setReceiveTimeout(1_000L) là timeout của **thao tác nhận**, không có tác động tới TTL được gửi ở hai template trước.
7. Không có consumer cạnh tranh trong demo, không dùng listener nền; thử nghiệm phản ánh rõ mối quan hệ giữa thời gian gửi và thời gian bắt đầu nhận.

### 7.5. Chạy project và output

Từ thư mục jms-ttl-demo:

~~~bash
mvn spring-boot:run
~~~

Khi broker chạy bình thường, không có bất thường lớn về đồng hồ/tài nguyên và message thứ hai được giao trong thời hạn, stdout của chương trình là:

~~~text
expired: null
valid: still-valid
has-expiration: true
~~~

Các log của Spring Boot/provider có thể xuất hiện thêm. Đặc tả JMS không bảo đảm tuyệt đối rằng mọi implementation sẽ loại bỏ message expired trước khi caller đọc; dự đoán này là đường chạy **thông thường trên Artemis đã cấu hình expiry**. Nếu expired khác null, cần kiểm tra đồng hồ, TTL đang được áp dụng thật hay không, broker version và chính sách expiration; không nên đơn giản khẳng định mã Java hỏng.

Dừng container demo:

~~~bash
docker stop ttl-demo-broker
~~~

### 7.6. Thí nghiệm sau khi chạy thành công

- Đổi shortLived.setTimeToLive(250L) thành 0L. Nếu không có provider-specific expiry override, message "too-late" sẽ **không hết hạn theo JMS TTL** và có thể nhận được sau 1,2 giây.
- Đổi 250L thành 10_000L: thời gian chờ 1,2 giây chưa vượt TTL, nên message còn đủ hạn.
- Đổi reader.setReceiveTimeout(1_000L) thành 2_000L: thời gian gọi receive có thể thay đổi nhưng **deadline expiration không đổi**.
- Đổi shortLived.setExplicitQosEnabled(true) thành false: kiểm tra lại TTL được áp dụng hay default provider được dùng. Đây là thí nghiệm quan trọng để hiểu explicit QoS.
- Tạo một listener tiêu thụ sớm hơn 250ms và xem message có thể được giao trước khi hết hạn; TTL không cấm giao khi còn hạn.
- Dùng cách gửi với MessageProducer.send(..., ttl) khác nhau và đọc JMSExpiration của message nhận.

## 8. TTL và delivery delay không phải cùng một khái niệm

JMS 2.0+/Jakarta Messaging hỗ trợ **delivery delay**: số millisecond message phải chờ trước khi sớm nhất được giao. Provider tính **JMSDeliveryTime** theo thời điểm gửi cộng delivery delay.

| Thuộc tính | Ý nghĩa | Header liên quan |
| --- | --- | --- |
| Time-to-live (TTL) | Thời gian tối đa message được xem là còn hạn | JMSExpiration |
| Delivery delay | Thời gian chờ tối thiểu trước khi message có thể deliver | JMSDeliveryTime |
| Receive timeout | Giới hạn thời gian thread client chờ một receive call | Không làm thay đổi header expiry |
| Transaction timeout | Giới hạn giao dịch theo transaction manager | Không trực tiếp đặt JMSExpiration |

Minh họa:

~~~text
Send ở t=0:
  deliveryDelay = 8 giây
  TTL           = 5 giây

  t=0:     message được gửi
  t=5:     message hết hạn (JMSExpiration)
  t=8:     thời điểm sớm nhất được phép giao (JMSDeliveryTime)

  => Không có khoảng thời gian hợp lệ để deliver trước khi hết hạn.
~~~

Một provider tuân thủ delay không được giao trước JMSDeliveryTime; message đã hết hạn trước mốc đó sẽ không còn phù hợp để giao. Vì vậy không kết hợp deliveryDelay > TTL rồi kỳ vọng message vẫn đến đúng hẹn.

### 8.1. Cấu hình Spring

~~~java
JmsTemplate template = new JmsTemplate(connectionFactory);
template.setDeliveryDelay(2_000L);
template.setTimeToLive(10_000L);
template.setExplicitQosEnabled(true);
~~~

Đây là snippet; ConnectionFactory có từ bên ngoài. Trong ví dụ, message có cửa sổ từ sớm nhất khoảng 2 giây sau send tới hết hạn khoảng 10 giây sau send, nhưng thời điểm provider deliver thực tế còn phụ thuộc queue, subscriber, broker và transaction.

Khi dùng các cơ chế scheduling riêng của broker, kiểm tra cách chúng tương tác với JMS standard delivery delay và TTL; không tự giả định scheduler sẽ reset TTL.

## 9. TTL và JMS transaction: deadline tính từ send, không từ commit

Một trường hợp khó thấy trong thử nghiệm là Session transacted:

~~~text
12:00:00  Session transacted: producer.send(m, TTL = 5s)
12:00:04  Business logic vẫn chưa commit
12:00:07  session.commit()
12:00:07  Message đã quá hạn tính từ 12:00:00
~~~

Theo đặc tả JMS, TTL tính từ lúc client send **kể cả trong transaction**, không bắt đầu lại tại commit. Vì vậy message có thể quá hạn trước khi commit và không bao giờ được giao sau commit. Không nhầm:

- **commit**: xác nhận transaction JMS.
- **JMSExpiration**: giới hạn vòng đời message tính từ lúc send.
- **acknowledgement**: xác nhận message nhận.
- **business deadline**: chính sách ứng dụng, có thể cần sống xuyên suốt nhiều transaction và retry.

Đối với transaction lâu, nên chọn TTL có dư địa cho thời gian trước commit, backlog và delivery, hoặc thiết kế producer gửi message ở thời điểm hợp lý. Không chọn TTL quá ngắn để tiết kiệm queue mà bỏ qua thời gian transaction.

Khi Spring dùng JmsTransactionManager hoặc JTA, boundary commit/rollback do transaction manager quản lý. JmsTemplate chỉ tham gia theo cấu hình; setTimeToLive không tự tạo transaction và cũng không thay thế transaction manager. Đặc biệt, thao tác DB và JMS không tự nguyên tử nếu chỉ dùng transaction cục bộ riêng.

## 10. TTL, redelivery và lỗi consumer

### 10.1. Message còn hạn nhưng consumer xử lý lỗi

Nếu consumer nhận message trước thời điểm hết hạn, rồi ném exception khiến transaction rollback hoặc yêu cầu recover, provider có thể redeliver theo chính sách. TTL không phải số lần retry; số lần delivery có thể được quan sát qua JMSXDeliveryCount trên message nhận.

~~~java
int count = message.getIntProperty("JMSXDeliveryCount");
long expiration = message.getJMSExpiration();
boolean expiredByClock =
        expiration != 0 && System.currentTimeMillis() >= expiration;
~~~

Đây là snippet trong consumer, message là jakarta.jms.Message. Đồng hồ của process chỉ có tính tham khảo; không thay thế logic/provider. Nếu expiredByClock=true và side effect không được phép chạy sau deadline, consumer cần thực hiện policy phù hợp thay vì xử lý như bình thường.

### 10.2. Khi đã nhận trước hạn nhưng xử lý chậm

Không có bảo đảm TTL sẽ tự ngăn side effect chạy sau khi hết hạn. Để xử lý công việc có deadline chặt chẽ:

1. Truyền deadline nghiệp vụ **tuyệt đối** hoặc phiên bản trạng thái trong body/properties.
2. Khi bắt đầu xử lý, xác thực job vẫn hợp lệ theo domain state (ví dụ đơn hàng chưa hủy).
3. Ngay trước side effect quan trọng, kiểm tra điều kiện còn hiệu lực và transaction/optimistic locking phù hợp.
4. Thiết kế idempotency để redelivery không tạo tác vụ lặp.
5. Có đường quan sát/hậu kiểm nếu message expired mà nghiệp vụ cần thông báo cho người dùng.

Nếu cần hủy lệnh thanh toán hoặc hoàn tiền, **không dựa vào JMS TTL làm cơ chế duy nhất**: phải có state machine và quy trình đối soát độc lập.

### 10.3. TTL so với giới hạn retry

Các broker thường có policy retry, redelivery delay, max-delivery-attempts và dead-letter address/queue. Đây là cơ chế khác TTL. Một message có TTL ngắn có thể hết hạn khi chờ retry; việc này khác với vượt quá số lần thử và bị đưa vào DLQ.

Hãy theo dõi riêng:

- Message bị **expiry** vì TTL/deadline.
- Message bị **dead-letter** vì lỗi xử lý hoặc vượt retry policy.
- Message được **ack/commit** sau xử lý thành công.
- Message bị **purge** thủ công hoặc xóa do retention/broker policy.

Gộp tất cả thành một metric “lost” khiến khó chẩn đoán.

## 11. Broker xử lý expiry thế nào? Ví dụ Apache ActiveMQ Artemis

Jakarta Messaging chỉ đưa ra semantics TTL và JMSExpiration, **không định nghĩa chuẩn một expiry queue hay callback expiration**. Broker có chính sách riêng:

- Xóa message đã hết hạn khỏi queue.
- Chuyển message tới **expiry address/queue** để hệ thống điều tra nếu được cấu hình.
- Quét expiry theo chu kỳ hoặc phát hiện lúc chuẩn bị giao; queue depth có thể giảm sau thời điểm deadline.
- Áp dụng những rule riêng như expiry-delay, max-expiry-delay hoặc no-expiry tùy cấu hình quản trị.

### 11.1. Artemis expiry address

Apache ActiveMQ Artemis hỗ trợ gán expiry address để thu thập message đã hết hạn. Ví dụ trích đoạn broker.xml:

~~~xml
<address-settings>
    <address-setting match="orders.notifications">
        <expiry-address>expiry.notifications</expiry-address>
    </address-setting>
</address-settings>
~~~

Đây là **trích đoạn cấu hình** minh họa; expiry address, queue gắn với nó, quyền, kiểu routing và auto-create expiry resources phải được cấu hình theo môi trường. Không chép nguyên block này vào XML hiện hữu mà không xét cấu trúc address-settings của broker.

Khi không cấu hình expiry address thích hợp, Artemis có thể **xóa** expired message thay vì chuyển sang nơi lưu giữ. Vì vậy “TTL làm message hết hạn” **không đồng nghĩa** “message chắc chắn được chuyển đến DLQ”. DLQ phục vụ lỗi/undelivered-policy; expiry address phục vụ expiration. Hai đường xử lý có thể dùng các tên, retention và quyền khác nhau.

### 11.2. Expiry có thể được quét trễ

Artemis có expiry reaper/scan period để kiểm tra message expired. Thời gian quét, prefetch/buffering và cách provider dispatch có thể khiến message vẫn xuất hiện trong thống kê queue trong một khoảng sau khi JMSExpiration đã qua.

Ví dụ:

~~~text
t=0s      send TTL 3s, queue depth +1
t=3s      deadline đã đến
t=6s      broker expiry scan loại message, queue depth -1
~~~

Đây là timeline minh họa, không phải lịch quét cố định của mọi Artemis version. Không nhầm **metric queue depth chưa giảm** với “message còn hợp lệ để xử lý”. Có thể quan sát expiry count hoặc expiry address để xác minh.

### 11.3. Đồng bộ đồng hồ

JMSExpiration là epoch timestamp, producer và broker có thể chạy trên các host với clock khác nhau. Drift/skew có thể làm message bị đánh giá quá hạn quá sớm hoặc quá muộn tùy hệ thống. Vận hành nên đồng bộ NTP/chrony, log timestamp kèm timezone và giám sát clock drift. Tránh tính TTL business từ DateTime không có timezone hay từ clock không đáng tin.

## 12. Chọn TTL theo loại công việc

Không có một TTL “đúng nhất” cho mọi queue. Hãy tính từ **giá trị nghiệp vụ của message**:

| Loại message | Hướng lựa chọn | Lý do |
| --- | --- | --- |
| Cache refresh / invalidation có thể tái tạo | TTL ngắn khi bản cập nhật cũ không còn giá trị | Tránh xử lý backlog không cần thiết; cần nguồn sự thật để refresh lại. |
| Thông báo marketing có thời hạn | TTL theo khung chiến dịch, kèm kiểm tra business deadline | Không gửi nội dung hết hiệu lực. |
| Event audit bắt buộc ghi nhận | TTL=0 hoặc rất dài theo quy định lưu trữ, nhưng cần bảo đảm độ bền và backlog | Không muốn tự biến mất khi consumer chậm. |
| Gửi email không cấp bách | TTL theo SLA thực tế, có giám sát và đường xử lý khi expired | Tránh gửi rất muộn nếu nghiệp vụ không mong muốn. |
| Thanh toán/đơn hàng cần bảo toàn | Không dùng TTL ngắn như cơ chế xóa lệnh nghiệp vụ | Cần state machine, đối soát, idempotency và compensation. |
| Request-reply có timeout | TTL tương ứng giới hạn hữu ích của request/reply nhưng **không đồng nhất** với thời gian chờ caller | Request hoặc reply có thể mất giá trị sau khi caller từ bỏ. |

Một ước lượng cho TTL gửi message theo deadline là:

~~~text
TTL đủ lớn cho:
  thời gian producer/transaction
+ độ trễ broker/queue trong điều kiện tải chấp nhận được
+ thời gian consumer offline ngắn hạn nếu nghiệp vụ chấp nhận
+ vùng đệm clock/network (nếu cần)

nhưng không vượt quá thời gian message còn có ích về nghiệp vụ.
~~~

Nếu hai yêu cầu này xung đột, không thể giải bằng “tăng TTL tùy ý”; cần cải thiện throughput, tự động mở rộng consumer, tách hàng đợi ưu tiên, hoặc thay đổi quy trình nghiệp vụ.

## 13. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Gửi bằng setTimeToLive(30) nhưng hết hạn tức thì | Tưởng 30 là giây, thật ra 30ms | Dùng 30_000L hoặc Boot property 30s. |
| JmsTemplate gửi nhưng message không hết hạn | Chưa bật explicit QoS; provider dùng default TTL | Gọi setExplicitQosEnabled(true) và xác minh JMSExpiration. |
| TTL=0 khiến message luôn được giữ | Hiểu nhầm 0 là hết hạn ngay | Trong JMS 0 = không hết hạn. |
| Có JMSExpiration nhưng consumer không nhận | Message quá hạn trước delivery; queue có backlog/consumer offline | Kiểm tra deadline, broker metrics và expiry address. |
| Expired message không thấy trong DLQ | Expiry và dead-letter là hai policy khác | Cấu hình expiry address/queue nếu cần lưu vết. |
| Đã hết hạn nhưng queue depth chưa giảm ngay | Broker quét expiry theo chu kỳ | Xem scan period, expiry count, thời gian metrics cập nhật. |
| Message xử lý quá thời hạn | TTL không ngắt callback sau receive | Kiểm tra deadline trong business handler. |
| Gửi bằng ProducerCallback không dùng TTL template | Code gọi producer.send trực tiếp | Dùng overload send có QoS cho lời gửi cụ thể. |
| Consumer timeout nhưng message vẫn tồn tại | Receive timeout khác TTL | Phân biệt timeout chờ với expiration. |
| Message expired ngay sau transaction commit | TTL tính từ send trước commit, transaction kéo dài | Điều chỉnh luồng gửi hoặc TTL theo yêu cầu. |
| TTL và deliveryDelay mâu thuẫn | Delay > TTL, không còn cửa sổ deliver | Thiết kế lại hai policy. |
| Message được giao lại sau lỗi, vượt business deadline | Broker retry không tự kiểm tra business state | Idempotency, deadline validation, state machine. |
| Clock trên host không đồng bộ | JMSExpiration epoch time, broker/client drift | Đồng bộ NTP, kiểm tra logs/timezone. |
| Đổi TTL bean dùng chung theo request | JmsTemplate đã được nhiều thread sử dụng | Dùng template riêng hoặc ProducerCallback để set TTL per send. |

## 14. Checklist điều tra sự cố hết hạn

1. **Producer:** TTL được đặt ở đâu? MessageProducer, JMSProducer, JmsTemplate, property Boot, hay broker default?
2. **Đơn vị:** 250, 5_000, 30s là ms hay duration? Có phép đổi sang milliseconds an toàn không?
3. **QoS:** JmsTemplate có setExplicitQosEnabled(true) chưa? Nếu dùng Boot auto-configuration, có override template bằng bean tùy chỉnh không?
4. **Header:** quan sát JMSExpiration sau send hoặc trên message được nhận; 0 có nghĩa không hết hạn.
5. **Mốc gửi:** producer gửi lúc nào? Transaction có commit muộn so với send không?
6. **Delivery delay:** có JMSDeliveryTime muộn hơn JMSExpiration không?
7. **Broker:** expiry address đã cấu hình chưa, message expire bị drop hay move, scan period bao nhiêu?
8. **Consumer:** listener đã start, queue/topic đúng, selector có match, timeout nhận và acknowledgement có hợp lý?
9. **Redelivery:** có rollback/recover kéo dài thời gian chờ hay tạo lại message mới reset TTL không?
10. **Clock:** producer, broker, consumer có đồng bộ thời gian không?
11. **Business:** phải phục hồi/ghi nhận một tác vụ đã expired thế nào; có audit/metric và đường bù không?

Ưu tiên chẩn đoán theo từng lớp thay vì chỉ nhìn kết quả receive null: null có thể vì queue rỗng, selector không match, consumer chưa start, message hết hạn, hoặc receive timeout quá ngắn.

## 15. Bài tập và câu hỏi tự kiểm tra

**Câu 1. TTL=0 có nghĩa gì?** Không hết hạn theo cơ chế JMS TTL. Nó không bảo đảm message luôn tồn tại khi có broker restart, purge hoặc retention khác.

**Câu 2. TTL=5.000ms, send ở t=0, commit ở t=7s thì JMSExpiration tính từ đâu?** Từ thời điểm client send, khoảng t=5s; không tính lại từ commit.

**Câu 3. Sau khi consumer nhận message còn hạn, 10 giây sau message hết hạn thì callback đang xử lý có tự bị dừng không?** Không. TTL quản lý expiration/delivery; cần business timeout/deadline riêng.

**Câu 4. JmsTemplate.setTimeToLive(10_000L) nhưng không bật explicit QoS có chắc áp dụng 10 giây không?** Không nên giả định. Bật setExplicitQosEnabled(true) khi cấu hình JmsTemplate thủ công; Spring Boot có cơ chế tự bật QoS khi set property template TTL.

**Câu 5. Gọi message.setJMSExpiration(...) có phải cách chuẩn để đặt TTL không?** Không. Đây là header setter dành cho provider, không phải API cấu hình TTL của ứng dụng.

**Câu 6. Delivery delay=10s, TTL=2s thì điều gì xảy ra?** Message hết hạn trước thời điểm sớm nhất được phép giao; không có khoảng giao phù hợp.

**Câu 7. Consumer.receive(timeout=1s) trả null có đồng nghĩa message đã expire không?** Không. Nó chỉ cho thấy không nhận được message trong lần chờ ấy.

**Câu 8. TTL của message có tự reset khi broker redeliver do rollback không?** Không theo nghĩa expiration của cùng message. Nếu ứng dụng republish một message mới thì phải chủ động giữ business deadline nếu cần.

**Câu 9. Expired message có tự vào DLQ không?** Không bắt buộc. Broker có thể drop hoặc chuyển tới expiry address theo cấu hình; DLQ là khái niệm policy khác.

**Câu 10. TTL có phù hợp làm cơ chế hủy một lệnh thanh toán không?** Không nếu đứng một mình. Phải có state machine, idempotency và đối soát vì message có thể đã được consumer nhận trước hạn nhưng còn xử lý.

### Bài tập thực hành

1. Chạy mục 7 với TTL 250ms, xác nhận message ngắn không nhận được sau 1,2s trong broker demo; đọc stdout và metrics.
2. Đổi TTL ngắn thành 5_000ms. Xác nhận receive có thể lấy message trong cùng độ trễ 1,2s.
3. Đặt TTL=0 và giải thích JMSExpiration=0 khác với “expire now”.
4. Dùng MessageProducer.send(message, mode, priority, ttl) để gửi hai message vào cùng queue với TTL khác nhau; kiểm chứng message nào được deliver.
5. Tạo transaction JMS và commit trễ hơn TTL; quan sát kết quả để hiểu mốc send-time.
6. Bật delivery delay trong Spring, thay TTL ngắn hơn delay; giải thích không có cửa sổ hợp lệ để deliver.
7. Cấu hình expiry address trong một broker Artemis thử nghiệm và quan sát expired message được chuyển sang queue quan sát thế nào.
8. Viết consumer kiểm tra deadline nghiệp vụ trong payload và deduplicate bằng BusinessId, ngay cả nếu JMS message vẫn còn hạn.
9. Theo dõi metric: sent, consumed, expired, dead-lettered, timeout và backlog; kiểm tra vì sao nhận null không đồng nghĩa chỉ có một nguyên nhân.

## 16. Tài liệu chuẩn

- [Jakarta Messaging 3.1 Specification, mục 3.4.9 JMSExpiration](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): mốc expiration, TTL trong transaction, giới hạn bảo đảm.
- [Jakarta Messaging 3.1 API — Message](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message): JMSExpiration, JMSTimestamp, JMSDeliveryTime và giá trị mặc định.
- [Jakarta Messaging 3.1 API — MessageProducer](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageproducer): setTimeToLive và send với QoS.
- [Spring Framework 6.2 — JMS Using](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html): cấu hình explicit QoS trên JmsTemplate.
- [Spring Framework 6.2 — JmsTemplate API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html): setTimeToLive, setExplicitQosEnabled, setReceiveTimeout.
- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/docs/3.3.0/reference/html/application-properties.html): spring.jms.template.time-to-live và qos-enabled.
- [Apache ActiveMQ Artemis — Message Expiry](https://artemis.apache.org/components/artemis/documentation/latest/message-expiry.html): expiry-address, drop policy, expiry scan.
