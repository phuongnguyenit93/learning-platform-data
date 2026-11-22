# Phân biệt JMS với Kafka, AMQP và Spring Messaging

## Mục tiêu học tập

Sau bài này, bạn có thể: (1) xác định JMS, Kafka, AMQP và Spring Messaging thuộc tầng nào; (2) giải thích sự khác nhau giữa hàng đợi công việc, phát sự kiện và nhật ký sự kiện có thể đọc lại; (3) chọn công nghệ phù hợp với yêu cầu phân phối, lưu trữ, replay và tích hợp Spring; (4) tránh nhầm lẫn giữa JMS Topic, Kafka Topic, giao thức AMQP và các API Spring.

**Ý chính:** bốn tên gọi này không phải bốn broker tương đương. JMS/Jakarta Messaging là **chuẩn API Java**; Kafka là **nền tảng lưu trữ và xử lý dòng sự kiện**; AMQP là **giao thức trao đổi thông điệp trên mạng**; Spring Messaging là **bộ trừu tượng lập trình** trong hệ sinh thái Spring.

## 1. Đặt đúng tầng kiến trúc

| Thành phần | Nó thực sự là gì? | Phần nó quy định/cung cấp | Ví dụ liên quan |
|---|---|---|---|
| **JMS (Jakarta Messaging)** | Chuẩn API gửi/nhận thông điệp cho ứng dụng Java | `ConnectionFactory`, `Session`/`JMSContext`, `Message`, `Queue`, `Topic`, cơ chế acknowledgement, selector, transaction | Jakarta Messaging API với nhà cung cấp như ActiveMQ Artemis, IBM MQ; Spring JMS gọi API này |
| **Apache Kafka** | Nền tảng event streaming có broker, log phân vùng và giao thức/client riêng | `topic`, `partition`, `offset`, retention, consumer group, khả năng đọc lại dữ liệu còn được lưu | Kafka brokers, Kafka clients, Spring for Apache Kafka |
| **AMQP** | Họ giao thức chuẩn hóa việc truyền message giữa client và broker | Định dạng frame, tương tác trên đường truyền; mô hình routing phụ thuộc phiên bản giao thức | AMQP 0-9-1 thường dùng với RabbitMQ; AMQP 1.0 dùng bởi nhiều client/broker |
| **Spring Messaging** | Trừu tượng của Spring Framework trong mã ứng dụng | `org.springframework.messaging.Message<T>`, headers, `MessageChannel`, `MessageHandler`, chuyển đổi payload | Spring Integration, STOMP/WebSocket, các adapter tích hợp transport |

Sự khác biệt nằm ở **câu hỏi mỗi công nghệ trả lời**:

- JMS: “Mã Java nói chuyện với nhà cung cấp dịch vụ nhắn tin bằng hợp đồng API nào?”
- Kafka: “Sự kiện được ghi vào log nào, chia partition ra sao, nhóm consumer đọc đến offset nào và có thể đọc lại không?”
- AMQP: “Client và broker truyền frame/message theo chuẩn mạng nào?”
- Spring Messaging: “Trong ứng dụng Spring, biểu diễn payload, header và luồng xử lý message bằng interface nào?”

**Đừng đồng nhất API, giao thức, broker và framework.** Một ứng dụng Spring có thể dùng Spring JMS để gọi JMS API; một JMS provider có thể giao tiếp bằng AMQP 1.0. Trong khi đó, `@KafkaListener` và `@RabbitListener` tích hợp những mô hình và client khác.

~~~text
Ứng dụng Java + Spring
  ├─ Spring JMS    → Jakarta Messaging API → JMS provider/broker
  ├─ Spring Kafka  → Kafka client          → Kafka cluster
  ├─ Spring AMQP   → AMQP/RabbitMQ client  → RabbitMQ/broker tương thích
  └─ Spring Messaging: Message, headers, channel, handler
       (trừu tượng dùng bên trong hoặc được adapter kết nối với transport)
~~~

Sơ đồ chỉ thể hiện quan hệ khái niệm. Một broker có thể hỗ trợ nhiều giao thức và một transport có thể được tích hợp với nhiều module Spring.

## 2. JMS: API cho message queue và publish/subscribe trong Java

### 2.1. Cơ chế cơ bản

JMS là tên quen thuộc của **Java Message Service**. Với các phiên bản Jakarta Messaging hiện đại, package API là `jakarta.jms`; tài liệu và thư viện cũ thường dùng `javax.jms`. Khi học Spring Framework 6/7 hay Spring Boot 3/4, cần kiểm tra sự tương thích giữa hai namespace này.

Một luồng điển hình:

1. Ứng dụng nhận `ConnectionFactory` do JMS provider cung cấp.
2. Producer tạo hoặc chuyển đổi một `Message`, gửi đến `Destination`.
3. Broker/provider phân phối thông điệp theo semantics của destination, thiết lập persistence, TTL, selector và các chính sách riêng.
4. Consumer nhận message, xử lý rồi acknowledgement hoặc commit transaction. Nếu thất bại, có thể có redelivery tùy cách cấu hình.

JMS quy định hợp đồng Java và các semantics cốt lõi; nó **không quy định một giao thức wire chung** mà mọi provider bắt buộc phải dùng. JMS API cũng không tự khởi chạy broker hay đảm bảo mọi nhà cung cấp có cùng chính sách vận hành.

### 2.2. Queue và Topic không giống nhau

**Queue — point-to-point/competing consumers:**

~~~text
Producer ──► [Queue: payment.requests]
                  ├─► Worker A
                  ├─► Worker B
                  └─► Worker C
Mỗi message được giao cho một consumer đủ điều kiện trong queue.
~~~

Nếu ba worker cùng nghe một queue, thông điệp không được tự động nhân thành ba bản cho cả ba. Queue hợp với “một công việc cần một worker xử lý”, như tạo hóa đơn hoặc gửi email.

**Topic — publish/subscribe:**

~~~text
Producer ──► [Topic: order.events]
                  ├─► Subscription A → Billing
                  └─► Subscription B → Analytics
Mỗi subscription đủ điều kiện nhận bản message riêng.
~~~

Topic phát đến các **subscription** khác nhau. Với **non-durable subscription**, thông điệp phát lúc không có subscriber hoạt động thường không được giữ để subscriber đó đọc sau. Với **durable subscription**, provider duy trì subscription và tích lũy thông điệp hợp lệ khi consumer ngắt kết nối, cho đến khi được nhận/acknowledge hoặc hết hạn theo chính sách. Một shared subscription có thể phân phối công việc cho nhiều consumer; không nên mặc định rằng mỗi instance nhận mọi thông điệp.

### 2.3. Độ tin cậy và giới hạn

- **Acknowledgement/transaction:** một message chưa được ghi nhận hoàn tất có thể được giao lại. Không mặc định hàm xử lý chỉ chạy đúng một lần.
- **Persistence:** chế độ `PERSISTENT` tăng bảo đảm khi broker gặp sự cố; nó không bỏ qua giới hạn tài nguyên, cấu hình retention hay các failure bên ngoài broker.
- **Selector:** consumer có thể lọc dựa trên thuộc tính message (ví dụ `region = 'VN'`); đây không phải câu truy vấn nội dung bất kỳ của event log.
- **TTL, priority, redelivery, dead-letter queue (DLQ):** một phần là khái niệm/API chuẩn, còn lịch redelivery và cách thiết lập DLQ thường phụ thuộc broker.
- **Order:** JMS mô tả thứ tự phân phối trong những điều kiện nhất định, nhưng cạnh tranh giữa nhiều consumer, selector, retry và xử lý song song có thể làm thứ tự **hoàn tất nghiệp vụ** khác thứ tự gửi.
- **Replay:** JMS không định nghĩa cơ chế đặt lại offset để chạy lại toàn bộ lịch sử đã tiêu thụ như Kafka. Browser, DLQ, archive hoặc redrive nếu có là tính năng/chính sách cụ thể của provider.

**Chọn JMS khi** hệ thống Java đã dùng JMS provider, cần queue hoặc topic kiểu enterprise messaging, transaction/acknowledgement và tích hợp với Spring; đặc biệt khi không có nhu cầu coi luồng message là log lịch sử độc lập để nhiều nhóm đọc lại.

## 3. Kafka: event log được lưu giữ, phân vùng và có offset

Kafka dùng `topic` để chứa các record được nối thêm vào **log**. Mỗi topic chia thành một hoặc nhiều `partition`; record có offset trong **chính partition đó**, không có “offset toàn cục” cho cả topic. Producer có thể chọn key để các record cùng key thường được định tuyến nhất quán vào cùng partition trong một giai đoạn cấu hình thích hợp.

~~~text
Topic: orders.events
  partition 0: [offset 0][offset 1][offset 2]...
  partition 1: [offset 0][offset 1][offset 2]...
  partition 2: [offset 0][offset 1][offset 2]...

Consumer group "billing":   lưu vị trí đọc riêng
Consumer group "analytics": lưu vị trí đọc riêng
~~~

Khác biệt quan trọng:

1. **Đọc không đồng nghĩa xóa record.** Record thường vẫn ở log sau khi consumer đọc và commit offset, cho đến khi bị xóa bởi retention theo thời gian/dung lượng, chính sách compaction hoặc cấu hình khác.
2. **Nhiều consumer group đọc độc lập.** Billing và Analytics có thể theo các offset khác nhau mà không tranh cùng “bản message” theo kiểu queue.
3. **Replay có điều kiện.** Consumer có thể seek/reset offset để đọc lại phần dữ liệu **vẫn còn**; Kafka không mặc nhiên giữ lịch sử vĩnh viễn.
4. **Thứ tự có phạm vi.** Kafka giữ thứ tự theo partition. Nếu một nghiệp vụ đòi hỏi thứ tự theo orderId, hãy thiết kế key/partition phù hợp; không khẳng định thứ tự tuyệt đối trên toàn topic.
5. **Song song phụ thuộc partition.** Trong mô hình consumer group thông thường, một partition được giao cho tối đa một consumer đang hoạt động của nhóm tại một thời điểm. Tăng instance vượt số partition không tự tạo thêm song song hữu ích.
6. **Giao nhận và xử lý nghiệp vụ là hai tầng khác nhau.** Kafka có cơ chế transaction/exactly-once cho một số luồng xử lý và ghi vào Kafka, nhưng điều đó **không tự làm cho** email, API thanh toán hoặc cập nhật cơ sở dữ liệu ngoài Kafka thành exactly-once.

Kafka thường phù hợp khi cần event history có retention rõ ràng, nhiều consumer group độc lập, replay để sửa logic hoặc xây lại materialized view, ingest lượng lớn dữ liệu và stream processing. Không chọn Kafka chỉ vì “nhanh hơn queue”: phải đánh giá thông lượng, độ trễ, thứ tự, độ phức tạp vận hành và dữ liệu giữ lại trong bối cảnh thực tế.

### 3.1. “JMS Topic” khác “Kafka Topic” ở điểm nào?

Hai chữ *topic* giống nhau nhưng mô hình khác:

- JMS Topic phân phối thông điệp đến subscription; durable subscription có thể giữ backlog cho subscriber, nhưng API JMS không cung cấp một log offset để mọi consumer chủ động tua lại lịch sử đã acknowledge.
- Kafka Topic là log phân vùng có retention; consumer group quản lý vị trí đọc và có thể đọc lại record còn tồn tại.
- Cả hai đều hỗ trợ phát cho nhiều bên theo những cách khác nhau. Cần hỏi rõ “mỗi bên” nghĩa là **subscription**, **consumer instance** hay **consumer group**.

Ví dụ: hệ thống ban đầu có sự kiện `OrderCreated`; một tháng sau đội phân tích cần dựng lại báo cáo cho dữ liệu 14 ngày qua. Kafka đáp ứng thuận lợi nếu retention của topic vẫn còn đủ dữ liệu và quyền đọc được cấp. JMS Topic không mặc định cung cấp khả năng tua lại toàn bộ thông điệp trước đó đã được xử lý.

## 4. AMQP: giao thức truyền message, không phải tên của một broker

AMQP là **Advanced Message Queuing Protocol**. Cần luôn ghi rõ phiên bản:

- **AMQP 0-9-1:** mô hình được nhiều người biết qua RabbitMQ. Producer publish vào **exchange**, exchange định tuyến đến **queue** qua **binding** (ví dụ direct, topic, fanout, headers exchange), rồi consumer nhận từ queue.
- **AMQP 1.0:** chuẩn wire khác biệt đáng kể, sử dụng khái niệm connection, session, link và transfer. Không được suy luận rằng mọi thao tác exchange/binding của 0-9-1 đều tồn tại y hệt ở 1.0. Tính năng cụ thể cần đối chiếu broker/client.

~~~text
AMQP 0-9-1 (ví dụ RabbitMQ):
Publisher ─► Exchange("orders") ──binding/routing key──► Queue("billing")
                                              └────────► Queue("analytics")
                                                           │
                                                        Consumer
~~~

Một broker RabbitMQ có thể cung cấp AMQP 0-9-1, AMQP 1.0 và những giao thức khác; **RabbitMQ là sản phẩm broker**, còn **AMQP là giao thức**. Những tên như Kafka, RabbitMQ và ActiveMQ Artemis mới nằm gần tầng nền tảng triển khai, dù kiến trúc vẫn khác nhau.

### 4.1. JMS và AMQP có dùng chung được không?

**Có, với provider/client phù hợp.** Ví dụ **Apache Qpid JMS** triển khai Jakarta Messaging API cho ứng dụng Java nhưng truyền dữ liệu bằng **AMQP 1.0**. Do đó “dùng JMS” và “dùng AMQP 1.0” không loại trừ nhau: một cái mô tả API mà mã nguồn gọi, cái còn lại mô tả protocol trên mạng.

Ngược lại, dùng `RabbitTemplate` của Spring AMQP để nói chuyện với RabbitMQ qua AMQP 0-9-1 **không đồng nghĩa** đang sử dụng JMS API. Đừng coi `JmsTemplate` và `RabbitTemplate` là hai tên của cùng một API.

### 4.2. Semantics phải hỏi đúng broker

Delivery confirmation, consumer acknowledgement, persistent message, DLQ, retry, routing, queue type, ordering và transaction có cách hỗ trợ khác nhau theo **phiên bản AMQP + broker + client + cấu hình**. Bản thân chữ “AMQP” không bảo đảm mọi tính năng giống JMS hay Kafka.

## 5. Spring Messaging nằm ở đâu trong hệ sinh thái?

`spring-messaging` cung cấp các hợp đồng lập trình phổ quát, ví dụ:

- `org.springframework.messaging.Message<T>`: một payload đi kèm headers.
- `MessageChannel`: hợp đồng gửi message đến channel.
- `MessageHandler`: xử lý message; các module khác có thể cài đặt cách định tuyến/chạy bất đồng bộ.
- `MessageConverter` và cơ sở hỗ trợ annotation: biến đổi và ràng buộc payload/headers ở tầng ứng dụng.

Nó **không tự là broker**, không tự cung cấp Kafka partition, JMS durable subscription hay AMQP exchange. Một `MessageChannel` chạy trong JVM không được coi là hàng đợi bền vững giữa các tiến trình nếu chưa kết nối với transport/persistent store phù hợp.

Phân biệt thêm các module hay gặp:

| Module Spring | API thường nhìn thấy | Nền tảng/ý nghĩa |
|---|---|---|
| **Spring JMS** (`spring-jms`) | `JmsTemplate`, `@JmsListener`, `DefaultJmsListenerContainerFactory` | Tích hợp Jakarta Messaging/JMS provider |
| **Spring for Apache Kafka** (`spring-kafka`) | `KafkaTemplate`, `@KafkaListener`, listener container | Kafka producer/consumer/offset |
| **Spring AMQP / Spring Rabbit** | `RabbitTemplate`, `@RabbitListener`, `RabbitAdmin` | Tích hợp AMQP, đặc biệt RabbitMQ |
| **Spring Messaging** (`spring-messaging`) | `Message<T>`, `MessageChannel`, `MessageHandler` | Trừu tượng nội bộ, được các tích hợp khác tận dụng |
| **Spring Integration** | flow, channel, gateway, adapter | Kết nối các endpoint và áp dụng Enterprise Integration Patterns |
| **Spring Cloud Stream** | function/binder | Một tầng lập trình event-driven khác; binder nối tới broker như Kafka/RabbitMQ |

`org.springframework.messaging.Message<?>` **khác kiểu** `jakarta.jms.Message`. Hai kiểu có thể xuất hiện trong cùng một ứng dụng; Spring JMS có converter/adapter để chuyển đổi ở ranh giới tích hợp. Trong Spring Framework 7 còn có `JmsClient` như API fluent bổ sung cho `JmsTemplate`; mã sử dụng bản Framework cũ phải kiểm tra API có sẵn.

## 6. So sánh theo hành vi vận hành

| Câu hỏi cần trả lời | JMS / JMS broker | Kafka | AMQP / AMQP broker | Spring Messaging |
|---|---|---|---|---|
| Đơn vị trừu tượng chủ yếu? | Queue, Topic, Message, subscription | Topic, partition, record, offset, group | Frame/protocol; queue/exchange/binding tùy phiên bản | Message, header, channel, handler |
| Nhận một việc bởi một worker? | Queue và competing consumers | Consumer group xử lý từng partition, phải tự thiết kế mô hình task | Queue của broker thích hợp (ví dụ RabbitMQ) | Tùy channel/transport cụ thể |
| Phát cho nhiều hệ thống? | Nhiều Topic subscription | Nhiều consumer group | Nhiều queue/binding hoặc cơ chế broker | Chỉ khi có implementation phù hợp |
| Lịch sử có thể đọc lại? | Không có replay-offset chuẩn JMS; tùy broker và archive | Có khi record vẫn nằm trong retention | Không suy ra được từ protocol; tùy broker | Không tự cung cấp |
| Thứ tự? | Có quy tắc JMS, thay đổi theo concurrency/selector/redelivery | Đảm bảo thứ tự trong từng partition | Tùy broker, queue, retry, concurrency | Tùy triển khai |
| Ghi nhận đã xử lý? | Ack/transaction của session | Commit offset; transaction cho các phạm vi được hỗ trợ | Ack/settlement theo protocol/broker | Không có semantics chung xuyên broker |
| Trọng tâm tích hợp Spring? | `JmsTemplate`, `@JmsListener` | `KafkaTemplate`, `@KafkaListener` | `RabbitTemplate`, `@RabbitListener` với Spring Rabbit | `Message<?>` và channel/handler |
| Dữ liệu còn lại sau consumer đọc? | Thường xử lý và ack khỏi queue; topic theo subscription | Retention độc lập với việc consumer đã đọc | Tùy queue/broker | Không xác định |

**Lưu ý:** cột “AMQP” chỉ nói được những điều chuẩn giao thức xác định; muốn so sánh mức lưu trữ hoặc phân phối phải chỉ đích danh RabbitMQ/Artemis và cấu hình tương ứng. Các ô của bảng là mô hình mặc định/điển hình, không thay thế kiểm thử trong môi trường triển khai.

## 7. Một tình huống chung: đơn hàng thương mại điện tử

Giả sử Order Service phát sự kiện khi đơn hàng được tạo, Payment Service thực hiện lệnh thanh toán và Analytics Service cập nhật báo cáo.

### Phương án A — JMS Queue cho lệnh xử lý

Order Service gửi `ChargePayment(orderId)` vào `payment.commands`. Nhiều worker thanh toán cạnh tranh đọc cùng queue; mỗi lệnh được phân phối cho một worker. Khi xử lý thành công, worker commit/ack. Nếu lỗi tạm thời, chính sách retry/redelivery và DLQ cần cấu hình ở consumer và broker.

Phù hợp khi mục tiêu chính là **phân chia việc cần làm**, không phải lưu một log sự kiện để nhóm mới đọc lại sau nhiều ngày.

### Phương án B — JMS Topic cho sự kiện phát tới các subscription

Order Service publish `OrderCreated` đến JMS Topic. Billing và Analytics có subscription riêng. Muốn consumer nhận backlog khi offline, phải thiết kế durable subscription đúng cách, cùng chính sách tồn trữ/phân phối. Durable subscription không tương đương replay log Kafka.

Phù hợp khi đã có JMS provider và cần pub/sub tin cậy theo mô hình subscription.

### Phương án C — Kafka Topic cho lịch sử sự kiện

Order Service append `OrderCreated` vào `orders.events` với key là `orderId`. Billing group và Analytics group đọc độc lập. Khi cần đổi logic báo cáo, Analytics có thể dùng group mới hoặc quản lý reset/seek offset để tái xử lý **phần log còn trong retention**.

Phù hợp khi lịch sử có giá trị, có nhiều pipeline độc lập và nhu cầu replay thực tế. Không nên phát “lệnh thanh toán” thiếu kiểm soát duplicate như event vô hại: consumer phải bảo đảm idempotency và kiểm soát business invariants.

### Phương án D — RabbitMQ và AMQP 0-9-1

Order Service publish vào exchange `orders.exchange` với routing key `order.created`. Binding đưa một bản tới `billing.queue` và một bản tới `analytics.queue`; trong mỗi queue có thể có nhiều competing consumers. Routing linh hoạt là điểm mạnh thường gặp.

Đây là một **triển khai broker + protocol cụ thể**, không có nghĩa rằng mọi AMQP broker đều giống RabbitMQ.

### Spring Messaging trong các phương án trên

Đội phát triển có thể biểu diễn message bằng `Message<T>`, xử lý qua channel/handler hoặc sử dụng adapter. Tuy nhiên, cần lựa chọn và vận hành **JMS broker, Kafka cluster hoặc RabbitMQ** riêng cho yêu cầu lưu trữ, giao nhận và kết nối liên dịch vụ. Chỉ thêm dependency `spring-messaging` sẽ không tạo ra message broker.

## 8. Mẫu triển khai Java 17: nhìn rõ API Spring JMS

Ví dụ dưới đây dùng **Spring Boot 3.4.5, Java 17, ActiveMQ Artemis**. Nó có thể chạy khi máy đã có **broker Artemis tại localhost:61616**, thông tin xác thực và quyền truy cập được cấu hình phù hợp, queue `orders.queue` tồn tại hoặc broker cho phép tự tạo queue. Đây là dự án minh họa đầu-cuối, không mô phỏng Kafka/AMQP.

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.4.5</version>
    <relativePath/>
  </parent>
  <groupId>example</groupId>
  <artifactId>jms-compare-demo</artifactId>
  <version>0.0.1-SNAPSHOT</version>
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

`src/main/resources/application.properties` (điều chỉnh bảo mật theo broker của bạn):

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
~~~

`src/main/java/example/JmsCompareDemoApplication.java`:

~~~java
package example;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class JmsCompareDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(JmsCompareDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner produce(JmsTemplate jmsTemplate) {
        return args -> jmsTemplate.convertAndSend("orders.queue", "order-123");
    }

    @Component
    public static class OrderConsumer {
        @JmsListener(destination = "orders.queue")
        public void receive(String orderId) {
            System.out.println("Handled: " + orderId);
        }
    }
}
~~~

Chạy từ thư mục chứa `pom.xml` bằng lệnh:

~~~bash
mvn spring-boot:run
~~~

Nếu broker kết nối được, destination khả dụng và không có consumer khác lấy message trước, dòng output do code nghiệp vụ in ra là:

~~~text
Handled: order-123
~~~

Spring Boot còn in log khởi động. Kết quả trên giả định một lần xử lý thành công; redelivery hoặc chạy nhiều instance có thể làm output khác. Trong dự án thuần Spring Framework, cần tự cấu hình `ConnectionFactory`, listener container và thường bật `@EnableJms`; Spring Boot có JMS auto-configuration có thể làm giúp khi đủ dependency.

**Giải thích:** `JmsTemplate.convertAndSend` gửi `String` dưới dạng JMS `TextMessage` bằng converter mặc định; `@JmsListener` gọi method khi JMS provider giao một message tới queue. Dù mã nguồn không gọi trực tiếp `jakarta.jms.Message`, Spring JMS vẫn dùng JMS API ở tầng dưới. Kết nối broker là yêu cầu thực, không có “message tự truyền trong JVM” chỉ vì dùng annotation.

### 8.1. Các API tương ứng khi đổi transport

Những đoạn sau chỉ là **mã đặt trong bean Spring đã cấu hình đúng transport**, không phải chương trình Java độc lập. Chúng giúp đối chiếu API, không ngụ ý semantics tương đương.

**Kafka** (cần Spring Kafka, Kafka broker, topic và serializer/deserializer):

~~~java
// Trong một bean có KafkaTemplate<String, String> kafkaTemplate:
kafkaTemplate.send("orders.events", "order-123", "{\"type\":\"OrderCreated\"}");

// Trong một bean consumer:
@KafkaListener(topics = "orders.events", groupId = "analytics")
public void consumeEvent(String json) {
    System.out.println(json);
}
~~~

Với Kafka, `"order-123"` là key dùng cho partitioning, `"analytics"` là consumer group. Muốn bảo đảm xử lý nghiệp vụ có thể retry mà không gây side effect lặp, cần thêm chiến lược commit, retry và idempotency.

**RabbitMQ/AMQP 0-9-1** (cần Spring Rabbit, RabbitMQ broker và binding exchange→queue):

~~~java
// Trong bean có RabbitTemplate rabbitTemplate:
rabbitTemplate.convertAndSend("orders.exchange",
        "order.created", "{\"type\":\"OrderCreated\"}");

// Trong bean listener:
@RabbitListener(queues = "analytics.queue")
public void consumeEvent(String json) {
    System.out.println(json);
}
~~~

Ở đây `"orders.exchange"` và `"order.created"` thuộc mô hình routing AMQP 0-9-1; không phải destination JMS và không phải Kafka offset.

**Spring Messaging** (đoạn Java trong method có import `Message` và `MessageBuilder`):

~~~java
Message<String> event = MessageBuilder.withPayload("order-123")
        .setHeader("eventType", "OrderCreated")
        .build();
~~~

Đối tượng `event` gồm payload và header ở tầng ứng dụng. Đoạn code **chưa gửi nó ra broker**; phải gọi một adapter/template/channel có implementation tương ứng.

## 9. Chọn công nghệ qua yêu cầu, không qua tên gọi

Hãy trả lời các câu hỏi theo thứ tự:

1. **Dữ liệu là command/job hay event history?** Job chỉ cần một worker hoàn tất thường hợp queue. Event history có nhiều consumer và replay thường hợp Kafka.
2. **Có cần đọc lại sau khi đã xử lý?** Nếu có, cần xác định retention, offset/seek và cửa sổ replay; Kafka cho mô hình này trực tiếp. JMS/RabbitMQ cần chiến lược archive/replay riêng nếu muốn lịch sử tương tự.
3. **Ai cần nhận mỗi thông điệp?** Một worker, mỗi subscription, mỗi queue được bind hay mỗi consumer group? Viết rõ số bản sao và phạm vi cạnh tranh.
4. **Đang bị ràng buộc bởi hệ thống nào?** Ứng dụng enterprise đã có JMS provider và transaction; RabbitMQ đang có topology exchange/queue; Kafka đang là nền tảng event? Chi phí đổi semantic thường lớn hơn đổi tên API.
5. **Yêu cầu thứ tự, độ trễ, lượng dữ liệu, đa ngôn ngữ?** Phải kiểm chứng theo partition, concurrency, protocol và broker. JMS là Java API; AMQP và Kafka có client nhiều ngôn ngữ.
6. **Failure được xử lý thế nào?** Cần chính sách retry, DLQ, idempotency key, correlation ID, quan sát consumer lag/backlog, giới hạn lưu trữ và cảnh báo vận hành.

| Tình huống | Hướng chọn thường hợp lý | Điều kiện phải kiểm tra |
|---|---|---|
| Nhiều worker thực hiện một tác vụ một lần về mặt nghiệp vụ | JMS Queue hoặc RabbitMQ queue | Ack/transaction, retry, DLQ, idempotency |
| Phát sự kiện cho nhiều hệ thống Java đã dùng JMS | JMS Topic với subscription phù hợp | Durable/shared subscription, TTL và lưu backlog |
| Audit, analytics, stream processing, rebuild view | Kafka | Retention, partition key, offset, schema evolution |
| Routing theo exchange và routing key | RabbitMQ qua AMQP 0-9-1 | Exchange/binding, publisher confirm, queue type |
| Interoperability JMS API qua AMQP 1.0 | JMS provider/client như Apache Qpid JMS | Broker hỗ trợ AMQP 1.0 và đúng version `jakarta.jms` |
| Dùng cùng mô hình payload/header trong Spring | Spring Messaging và adapter cần thiết | Transport thực tế và semantics của adapter |

Đây là tiêu chí kiến trúc, không phải khẳng định hiệu năng tuyệt đối. Hai công nghệ có thể cùng giải được một bài toán, nhưng chi phí xử lý sự cố, vận hành và mức phù hợp với dữ liệu sẽ khác.

## 10. Lỗi tư duy và rủi ro thường gặp

**Lỗi 1 — “JMS và Kafka đều có topic nên thay dependency là xong”.** Sai: JMS dùng subscription, Kafka dùng log/offset/consumer group. Migration phải thiết kế lại replay, ordering, retry, storage và contract event.

**Lỗi 2 — “AMQP chính là RabbitMQ”.** Sai: RabbitMQ là một broker hỗ trợ nhiều giao thức; AMQP còn có các phiên bản không tương thích wire-level. Luôn nêu broker và phiên bản giao thức.

**Lỗi 3 — “Dùng Spring Messaging là đã có durable queue”.** Sai: `MessageChannel` và `Message<T>` là hợp đồng/đối tượng. Persistence và giao nhận liên dịch vụ phải đến từ implementation và broker.

**Lỗi 4 — “Đã ack hoặc commit thì toàn bộ nghiệp vụ chắc chắn exactly-once”.** Sai: thất bại có thể xảy ra giữa ghi database, gọi API ngoài, gửi message và commit/ack. Thiết kế **consumer idempotent**, khóa nghiệp vụ/unique constraint, deduplication; nếu phát event gắn với database transaction, cân nhắc **transactional outbox**.

**Lỗi 5 — “Tăng consumer là thứ tự và tốc độ đều tăng”.** Không mặc định: nhiều JMS worker có thể hoàn tất lệch thứ tự, Kafka có trần song song theo số partition mỗi group, RabbitMQ bị ảnh hưởng bởi prefetch/ack/queue type.

**Lỗi 6 — “Persistent nghĩa là lưu vĩnh viễn”.** JMS PERSISTENT hướng đến độ tin cậy trong vận chuyển; Kafka retention có chính sách; RabbitMQ persistence và queue retention tùy cấu hình. Cần xác định SLA dữ liệu cụ thể.

**Lỗi 7 — “Mọi transport đều chuyển đối tượng Java tùy ý được”.** Nên dùng wire format có version (JSON/Avro/Protobuf...), xác thực schema, không phụ thuộc mặc định vào Java serialization. Trong Spring JMS, converter mặc định hỗ trợ String/byte[]/Map; object nghiệp vụ tùy ý cần converter phù hợp.

**Lỗi 8 — “Retry vô hạn sẽ tự sửa vấn đề”.** Có lỗi không thể phục hồi (payload sai schema, dữ liệu vi phạm invariant). Phân biệt lỗi tạm thời và lỗi vĩnh viễn; giới hạn retry, DLQ/quarantine, thêm correlation ID và theo dõi backlog/consumer lag.

## 11. Tự kiểm tra hiểu đúng

1. **Một việc in hóa đơn cần đúng một worker nhận:** JMS Queue hoặc RabbitMQ queue là mô hình trực tiếp; vẫn phải xử lý redelivery và đảm bảo in không lặp bằng logic nghiệp vụ.
2. **Ba nhóm muốn đọc cùng lịch sử thay đổi giá, nhóm mới cần chạy lại tuần trước:** Kafka phù hợp nếu retention chứa dữ liệu tuần trước. JMS Topic durable không tự cho phép tua lại toàn bộ lịch sử đã ack.
3. **Java gọi JMS API qua AMQP 1.0 có mâu thuẫn không?** Không. JMS mô tả API; Qpid JMS là ví dụ client dùng AMQP 1.0.
4. **Đã có `org.springframework.messaging.Message<String>` thì broker ở đâu?** Chưa có broker. Cần triển khai channel/adapter và cấu hình transport thực tế.
5. **Một Kafka topic có 4 partition, trong cùng consumer group mở 10 consumer:** thường chỉ tối đa 4 consumer có partition được giao để đọc topic này cùng lúc; các instance còn lại không tăng độ song song cho riêng topic đó.
6. **JMS Topic có 2 subscription durable, mỗi subscription có 3 shared consumer:** mỗi subscription nhận một bản phù hợp, rồi các shared consumer trong subscription đó chia nhau nhận message; không phải cả 6 instance đều nhận mỗi message.

## 12. Tài liệu tham khảo chính thức

- [Jakarta Messaging 3.1 specification](https://jakarta.ee/specifications/messaging/3.1/) — semantics Queue, Topic, acknowledgement, durable subscription, message selector.
- [Spring Framework — JMS integration](https://docs.spring.io/spring-framework/reference/integration/jms.html) — `JmsTemplate`, `@JmsListener`, listener container và transaction.
- [Spring Boot — JMS và Artemis](https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html) — auto-configuration và cấu hình broker cho ví dụ.
- [Apache Kafka — Design](https://kafka.apache.org/40/design/design/) — partition, consumer và offset/replay.
- [RabbitMQ — AMQP 0-9-1 concepts](https://www.rabbitmq.com/tutorials/amqp-concepts) và [protocols](https://www.rabbitmq.com/docs/protocols) — exchange, binding và sự khác nhau giữa AMQP 0-9-1/1.0.
- [Apache Qpid JMS](https://qpid.apache.org/components/jms/index.html) — JMS API chạy qua AMQP 1.0.
- [Spring for Apache Kafka](https://spring.io/projects/spring-kafka/) và [Spring AMQP](https://spring.io/projects/spring-amqp) — nhận diện đúng template/listener theo transport.

**Ghi nhớ:** Khi so sánh giải pháp messaging, luôn ghi đủ bốn lớp **API ứng dụng → protocol/client → broker/storage → semantics xử lý**. Chỉ khi đó câu hỏi “JMS hay Kafka hay AMQP hay Spring Messaging?” mới được chuyển thành quyết định kỹ thuật có thể kiểm chứng.
