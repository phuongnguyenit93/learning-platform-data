# Publish–subscribe và mô hình Topic trong Spring JMS

## 1. Mục tiêu và bối cảnh

Sau bài này, bạn có thể giải thích cách một `Topic` phân phối sự kiện đến các `subscription`, phân biệt Topic với Queue, lựa chọn subscription `durable/non-durable` và `shared/unshared`, cấu hình publisher và listener bằng Spring JMS, và nhận diện rủi ro mất hoặc xử lý trùng sự kiện.

`JMS` (Jakarta Messaging; tên cũ là Java Message Service) là API nhắn tin bất đồng bộ. `Broker` là hệ thống trung gian tiếp nhận, định tuyến và lưu trữ thông điệp theo cấu hình. `Destination` là đích gửi/nhận; hai mô hình chính là Queue và Topic. Trong Spring Framework 6 / Spring Boot 3, API JMS nằm dưới package `jakarta.jms` (không phải `javax.jms`).

**Publish–subscribe (pub/sub)** giải quyết tình huống một sự kiện cần đến nhiều hệ thống độc lập. Ví dụ: khi đơn hàng được tạo, hệ thống kế toán, phân tích dữ liệu và thông báo đều muốn biết, nhưng publisher không cần gọi riêng từng hệ thống.

## 2. Topic thực sự phân phối thông điệp như thế nào?

~~~text
OrderService (publisher)
        |
        |  publish "OrderCreated:42"
        v
   Topic: events.orders
        |
        +--> Subscription A --> Accounting consumer
        |
        +--> Subscription B --> Analytics consumer
        |
        +--> Subscription C --> Notification consumer
~~~

- **Publisher** gửi một message đến Topic, không cần biết có bao nhiêu người nhận. Publisher và subscriber được tách rời về địa chỉ, thời gian và vòng đời triển khai.
- **Topic** là đích logic phía broker. Broker định tuyến một bản thông điệp cho **mỗi subscription phù hợp** tại thời điểm gửi (hoặc giữ lại cho durable subscription).
- **Subscription** mới là đơn vị nhận và xác nhận thông điệp. A xử lý xong không đồng nghĩa B đã xử lý xong; nếu B rollback, việc phát lại cho B không buộc A xử lý lại.
- **Consumer** là tiến trình/luồng đọc từ subscription. Một subscription kiểu shared có thể có nhiều consumer cạnh tranh xử lý **cùng một bản dành cho subscription đó**.

Câu quan trọng: **“Một message đến mọi subscription phù hợp” không có nghĩa “mỗi instance đang chạy đều nhận một message”.** Hai instance cùng dùng **một shared subscription** chia việc; hai subscription **độc lập** mỗi bên nhận một bản.

Trình tự cơ bản: (1) broker cung cấp Topic; (2) consumer đăng ký subscription; (3) publisher gửi message; (4) broker sao/phân phối theo subscription và selector; (5) mỗi consumer xử lý và xác nhận theo chế độ acknowledgement/transaction của mình. Việc subscription có tồn tại khi consumer tắt hay không phụ thuộc durability.

## 3. So sánh Queue và Topic

| Tiêu chí | Queue — point-to-point | Topic — publish–subscribe |
|---|---|---|
| Đơn vị nhận | Một message thường được giao cho **một** consumer trong nhóm cạnh tranh của Queue. | Mỗi **subscription phù hợp** nhận bản của message; trong shared subscription, một consumer nhận mỗi bản. |
| Nhu cầu phổ biến | Phân việc: xử lý ảnh, gửi email, thực thi job. | Phát sự kiện: OrderCreated cho kế toán, báo cáo, thông báo. |
| Nhiều consumer | Cạnh tranh nhận message từ cùng Queue. | Có thể là các subscriber độc lập (fan-out) hoặc các consumer cạnh tranh trong cùng shared subscription. |
| Consumer tắt | Message có thể chờ trong Queue, tùy TTL, chính sách broker và acknowledgement. | Non-durable không giữ message khi subscription không còn consumer; durable có thể giữ message sau khi đã đăng ký. |
| Mở rộng | Thêm consumer vào Queue để chia tải. | Thêm subscription để có luồng xử lý độc lập; thêm consumer vào **shared subscription** để chia tải của riêng luồng đó. |

Không nên đổi Queue thành Topic chỉ để “tăng tốc”. Topic thường tạo nhiều bản giao theo số subscription; cùng một message có thể gây N lần xử lý nghiệp vụ. Chọn mô hình theo **ngữ nghĩa giao nhận**, sau đó mới tối ưu tải.

## 4. Bốn kiểu subscription và vòng đời

Hai trục độc lập tạo thành bốn dạng:

| Dạng | Khi không còn consumer hoạt động | Nhiều consumer cùng subscription? | Trường hợp phù hợp |
|---|---|---|---|
| Non-durable, unshared | Subscription kết thúc; message gửi lúc không có consumer sẽ bị bỏ qua đối với subscription đó. | Không, mỗi subscription unshared chỉ có một consumer. | UI cập nhật tức thời, dữ liệu có thể làm mới. |
| Non-durable, shared | Tồn tại khi có ít nhất một consumer; bị xóa khi consumer cuối đóng. | Có; mỗi message chỉ đến một consumer trong nhóm. | Nhóm xử lý sự kiện trực tuyến, chấp nhận bỏ lỡ lúc cả nhóm offline. |
| Durable, unshared | Broker giữ trạng thái và message chưa xử lý cho subscription đã đăng ký, theo TTL/chính sách lưu trữ. | Không, tối đa một consumer hoạt động trên cùng subscription. | Audit/reporting cần bắt kịp sau gián đoạn và chỉ chạy một consumer. |
| Durable, shared | Broker giữ subscription khi không có consumer; nhiều consumer chia tải khi hoạt động. | Có; mỗi message trong subscription được một consumer nhận. | Một nghiệp vụ cần không bỏ lỡ khi offline và muốn scale nhiều instance. |

**Chi tiết dễ nhầm:**

1. Durable phải **được tạo trước** thời điểm publisher gửi message cần giữ. Không tự động lấy lại những message đã gửi trước lần đăng ký đầu tiên. Durable không đồng nghĩa lưu lịch sử vô hạn.
2. Non-durable không có “hàng chờ lâu dài” khi client offline. Dù publisher dùng delivery mode `PERSISTENT`, message vẫn có thể mất với một non-durable subscription đã kết thúc.
3. Durable có định danh ổn định: với **unshared durable**, cặp `clientId + subscriptionName` xác định subscription; lần kết nối sau phải dùng lại đúng định danh. Shared durable dùng tên subscription và client ID nếu có; tuân theo yêu cầu riêng của provider. Đừng tự thay tên theo pod ID nếu muốn cùng tiêu thụ một luồng.
4. Với shared subscription, 3 instance cùng chia một subscription không nhận 3 bản. Muốn 3 dịch vụ đều thấy sự kiện, thiết kế **3 subscription độc lập**; mỗi dịch vụ có thể scale nội bộ bằng shared subscription.
5. Durable cần tài nguyên lưu trữ; phải giám sát backlog, TTL, quota và dọn subscription không còn sử dụng. Cách quản lý/xóa subscription phụ thuộc broker.
6. Khi subscriber có `message selector`, broker chỉ đưa vào subscription các message có **JMS property/header** khớp điều kiện. Selector không tự đọc JSON hoặc nội dung `TextMessage`.

### Dòng thời gian để tự kiểm tra

Giả sử Topic `events.orders` có S1 non-durable và S2 durable (S2 đã được tạo từ trước):

~~~text
09:00  S1 online, S2 online       --> publish E1 --> S1 có E1, S2 có E1
09:05  S1 tắt, S2 tắt             --> publish E2 --> S1 không có E2; S2 giữ E2
09:10  S1 lên, S2 lên             --> S2 nhận E2 còn tồn; S1 không nhận lại E2
~~~

Đây là sơ đồ về **subscription**. Nếu broker hết lưu trữ, message hết hạn hoặc cấu hình retention khác đi, kết quả thực tế có thể thay đổi. Nếu S2 chưa từng được tạo trước 09:05, S2 cũng không thể “truy hồi” E2 từ quá khứ.

## 5. Một ứng dụng Spring Boot 3 + Artemis để quan sát fan-out

Ví dụ dùng Java 17, Spring Boot 3.3.5, Gradle và một broker **Apache ActiveMQ Artemis nhúng** phục vụ học tập. Chương trình có hai listener đăng ký độc lập trên cùng Topic; gọi HTTP sau khi ứng dụng khởi động để chủ động publish. Broker nhúng đặt `persistent: false`, vì vậy ví dụ **không** chứng minh khả năng khôi phục qua việc tắt hẳn broker.

Cấu trúc tập tin:

~~~text
topic-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── resources/application.yml
    └── java/demo/topic/
        ├── TopicDemoApplication.java
        ├── TopicConfiguration.java
        ├── AccountingListener.java
        ├── AnalyticsListener.java
        └── PublishController.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'topic-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
    runtimeOnly 'org.apache.activemq:artemis-jakarta-server'
}
~~~

`src/main/resources/application.yml`:

~~~yaml
spring:
  artemis:
    mode: embedded
    embedded:
      topics: events.orders
      persistent: false
  jms:
    cache:
      enabled: false
~~~

`cache.enabled: false` giữ ví dụ dễ quan sát: listener tạo connection riêng, đặc biệt hữu ích khi sau này cấu hình client ID cho durable subscription. Ứng dụng production có thể dùng caching/pooling nhưng phải chọn connection factory và client ID đúng với mô hình subscription.

`src/main/java/demo/topic/TopicDemoApplication.java`:

~~~java
package demo.topic;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TopicDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(TopicDemoApplication.class, args);
    }
}
~~~

`src/main/java/demo/topic/TopicConfiguration.java`:

~~~java
package demo.topic;

import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;

@Configuration
@EnableJms
public class TopicConfiguration {
    @Bean
    JmsTemplate topicTemplate(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setPubSubDomain(true); // true = Topic, false = Queue
        return template;
    }

    @Bean
    DefaultJmsListenerContainerFactory topicListenerFactory(
            ConnectionFactory connectionFactory) {
        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(true);       // Đăng ký với Topic
        factory.setConcurrency("1");        // Một consumer cho mỗi unshared subscription
        factory.setSessionTransacted(true); // Commit/rollback JMS khi listener xử lý
        return factory;
    }
}
~~~

Hai bean sau là **hai subscription độc lập**, vì mỗi `@JmsListener` tạo listener container riêng cho Topic.

`src/main/java/demo/topic/AccountingListener.java`:

~~~java
package demo.topic;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class AccountingListener {
    @JmsListener(
        destination = "events.orders",
        containerFactory = "topicListenerFactory"
    )
    public void onOrderCreated(String text) {
        System.out.println("accounting <- " + text);
    }
}
~~~

`src/main/java/demo/topic/AnalyticsListener.java`:

~~~java
package demo.topic;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class AnalyticsListener {
    @JmsListener(
        destination = "events.orders",
        containerFactory = "topicListenerFactory"
    )
    public void onOrderCreated(String text) {
        System.out.println("analytics <- " + text);
    }
}
~~~

`src/main/java/demo/topic/PublishController.java`:

~~~java
package demo.topic;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.ResponseEntity;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PublishController {
    private final JmsTemplate topicTemplate;

    public PublishController(@Qualifier("topicTemplate") JmsTemplate topicTemplate) {
        this.topicTemplate = topicTemplate;
    }

    @PostMapping("/publish/{orderId}")
    public ResponseEntity<String> publish(@PathVariable String orderId) {
        String event = "OrderCreated:" + orderId;
        topicTemplate.convertAndSend("events.orders", event);
        return ResponseEntity.accepted().body("published " + event);
    }
}
~~~

Chạy ở thư mục `topic-demo` (cần JDK 17+ và Gradle tương thích Spring Boot 3.3; nếu đã có Gradle Wrapper thì dùng `./gradlew` thay `gradle`):

~~~bash
gradle bootRun
~~~

Khi server báo đã khởi động và các listener đã đăng ký, mở terminal khác:

~~~bash
curl -X POST http://localhost:8080/publish/42
~~~

HTTP body dự kiến:

~~~text
published OrderCreated:42
~~~

Trong log ứng dụng phải xuất hiện **một dòng cho mỗi listener** (thứ tự hai dòng không được đảm bảo):

~~~text
accounting <- OrderCreated:42
analytics <- OrderCreated:42
~~~

Đây là fan-out: một lần `convertAndSend`, hai nghiệp vụ độc lập cùng xử lý. Java file trong ví dụ là mã thực sự của ứng dụng Spring Boot; không thể chỉ dùng `javac`/`java` thuần vì còn cần dependency và broker. `JmsTemplate.convertAndSend` biến `String` thành `TextMessage` qua converter mặc định.

Nếu thay Topic bằng Queue, cấu hình `pubSubDomain` phải đổi nhất quán ở **cả publisher và listener**; khi đó hai listener thường cạnh tranh và chỉ một bên nhận một message. Với broker/provider hỗ trợ kiểu destination tường minh, có thể sử dụng `jakarta.jms.Topic` để tránh nhập nhằng tên.

## 6. Cấu hình durable hoặc shared subscription trong Spring JMS

Khi cần giữ message trong lúc một nghiệp vụ offline, dùng một factory **riêng cho durable Topic**. Ví dụ này là phần mở rộng về mặt cấu hình; nếu đưa vào ứng dụng ở trên, khai báo bean trong một lớp `@Configuration` và listener trong một `@Component`, đồng thời cấu hình broker có persistence nếu muốn thử phục hồi qua lần khởi động lại broker.

~~~java
@Bean
DefaultJmsListenerContainerFactory durableTopicFactory(
        ConnectionFactory connectionFactory) {
    DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setPubSubDomain(true);
    factory.setSubscriptionDurable(true);
    factory.setClientId("reporting-service"); // Định danh ổn định, duy nhất cho connection
    factory.setConcurrency("1");               // Unshared durable: chỉ một consumer
    factory.setSessionTransacted(true);
    return factory;
}
~~~

~~~java
@JmsListener(
    destination = "events.orders",
    subscription = "reporting-orders",
    containerFactory = "durableTopicFactory"
)
public void onEvent(String event) {
    System.out.println("reporting <- " + event);
}
~~~

Ý nghĩa:
- `setPubSubDomain(true)`: destination là Topic.
- `setSubscriptionDurable(true)`: broker giữ subscription sau khi consumer đóng.
- `setClientId("reporting-service")` và `subscription = "reporting-orders"`: định danh unshared durable ổn định để kết nối lại đúng backlog; **không** cho hai process chạy đồng thời dùng cùng unshared durable/client ID.
- `setSessionTransacted(true)`: nếu listener ném exception, JMS session rollback để message có cơ hội redelivery theo cấu hình provider. Không tự động gộp commit cơ sở dữ liệu với commit JMS thành một transaction phân tán.

Muốn nhiều replica **chia tải cùng một subscription**, thay đổi thiết kế sang shared durable với `factory.setSubscriptionShared(true)` cùng `setSubscriptionDurable(true)` và một subscription name nhất quán. Provider phải hỗ trợ JMS 2.0+/Jakarta Messaging shared subscriptions. Với shared durable, mỗi message đi đến **một replica trong nhóm**, không đến mọi replica. Cần thống nhất cách dùng client ID và connection ở môi trường triển khai thực tế; đừng copy cấu hình unshared có `clientId` cố định vào mọi pod rồi tăng `concurrency`.

### Chọn nhanh theo nhu cầu

- Phải gửi tới **cả kế toán lẫn phân tích**: tạo hai subscription độc lập trên cùng Topic.
- Kế toán có 5 replica nhưng mỗi sự kiện chỉ được kế toán xử lý một lần theo luồng nhận: dùng **một shared subscription cho kế toán**; phân tích có subscription riêng.
- Phân tích có thể tạm offline và cần bắt kịp: dùng **durable subscription**, cấu hình lưu trữ/TTL phù hợp.
- Subscriber chỉ cần biết “trạng thái mới nhất”, có thể nạp lại dữ liệu khi reconnect: cân nhắc **non-durable** để tránh backlog không cần thiết.

## 7. Message selector, thứ tự và độ tin cậy

### Chỉ nhận sự kiện phù hợp

`@JmsListener` có thuộc tính `selector` nhận biểu thức JMS selector. Ví dụ publisher gắn property `region`:

~~~java
topicTemplate.convertAndSend("events.orders", "OrderCreated:43", message -> {
    message.setStringProperty("region", "VN");
    return message;
});
~~~

Listener chỉ quan tâm thị trường Việt Nam:

~~~java
@JmsListener(
    destination = "events.orders",
    containerFactory = "topicListenerFactory",
    selector = "region = 'VN'"
)
public void onOrderCreatedInVn(String text) {
    System.out.println("VN <- " + text);
}
~~~

Selector chạy trên **JMS headers/properties**, không truy vấn trường bên trong chuỗi `OrderCreated:43`. Message không có `region` tương ứng sẽ không khớp. Tránh đổi selector của một durable subscription đang dùng mà không hiểu tác động lên subscription cũ và backlog.

### Delivery, acknowledgement, transaction

1. **Acknowledgement là riêng từng subscription.** A đã commit không giúp B commit; B lỗi có thể được giao lại mà không ảnh hưởng A.
2. **Persistent delivery không thay thế durable subscription.** Muốn nhận message phát lúc consumer offline, subscription cần bền vững **và đã tồn tại**, đồng thời broker lưu message theo chính sách phù hợp.
3. **Không suy ra exactly-once nghiệp vụ từ JMS.** Sau crash, timeout, rollback hoặc bước ghi DB đã commit trước khi JMS commit, cùng event có thể bị xử lý lại. Thiết kế consumer **idempotent** bằng event ID/khóa nghiệp vụ, unique constraint, hoặc inbox/deduplication.
4. **Thứ tự là theo phạm vi giao nhận được bảo đảm, không phải thứ tự hoàn tất toàn hệ thống.** Các subscription chạy độc lập; xử lý song song, selector, retry và nhiều producer có thể làm log giữa các dịch vụ khác thứ tự. Nếu cần thứ tự theo đơn hàng, thiết kế key/luồng xử lý tuần tự và kiểm tra khả năng của broker.
5. **Đừng bắt exception rồi coi như đã xử lý xong.** Nếu listener nuốt lỗi, transaction có thể commit và message được xác nhận dù nghiệp vụ thất bại. Xác định rõ retry, dead-letter queue (DLQ), backoff, maximum delivery attempts và cảnh báo.
6. **Đừng xem Topic là event store.** Replay lịch sử, giữ sự kiện hàng tháng và tìm kiếm theo thời gian cần yêu cầu riêng; JMS Topic/subscription thông thường chịu TTL, quota và chính sách broker.

### Checklist vận hành

Theo dõi tối thiểu: số message publish và consume trên từng subscription; backlog/độ trễ của durable subscriptions; số lần redelivery và DLQ; trạng thái kết nối listener; message TTL, kích thước và quota broker. Đặt tên Topic và subscription ổn định, quản lý schema phiên bản của payload, tránh logging dữ liệu nhạy cảm, và thử các tình huống restart consumer, rollback, trùng lặp, chậm xử lý.

## 8. Những hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu đúng |
|---|---|
| “Topic lưu mọi message cho tất cả người đăng ký trong tương lai.” | Non-durable bỏ lỡ khi offline; durable chỉ nhận backlog kể từ lúc subscription được tạo và còn theo chính sách broker. |
| “Có 3 instance subscribe Topic thì chắc chắn cả 3 đều nhận.” | Phải hỏi đó là **3 subscription độc lập** hay **3 consumer của cùng shared subscription**. |
| “Đặt `pubSubDomain=true` ở producer là đủ.” | Listener container cũng phải resolve đúng Topic; cấu hình sai dễ khiến một bên làm việc với Queue cùng tên. |
| “Durable nghĩa là exactly-once từ đầu đến cuối.” | Durable giúp giữ backlog; application vẫn cần xử lý duplicate, retry và transaction boundary. |
| “Tăng concurrency cho unshared durable để scale.” | Unshared durable chỉ cho một consumer hoạt động; muốn nhiều consumer, dùng shared subscription và provider phù hợp. |
| “Selector lọc được JSON body.” | JMS selector lọc header/property; muốn lọc theo trường nghiệp vụ, publisher phải đưa thuộc tính cần thiết vào JMS property hoặc dùng routing phù hợp. |

## 9. Bài tập tự kiểm tra

**Tình huống:** Topic `orders.created` có ba subscription: `accounting` durable unshared, `analytics` non-durable unshared, và `notifications` shared durable với hai consumer N1, N2. Khi một sự kiện `E7` được publish, analytics đang offline; hai nhóm còn lại hoạt động.

1. Bao nhiêu **subscription** nhận/giữ `E7`? Vì sao?
2. N1 và N2 mỗi bên có nhận một bản `E7` không?
3. Nếu accounting tắt trước `E8`, mở lại sau `E8` thì điều kiện nào giúp nó bắt kịp?
4. Nếu accounting đã ghi DB nhưng ứng dụng crash trước khi commit JMS, phải phòng lỗi gì?

**Đáp án:** (1) Hai: accounting và notifications; analytics non-durable offline không giữ E7. (2) Không: trong cùng shared subscription, chỉ một consumer xử lý bản E7. (3) Durable subscription đã tồn tại, đúng định danh và broker còn giữ E8 theo chính sách lưu trữ/TTL. (4) E8 có thể redeliver và ghi DB trùng; dùng idempotency/deduplication và thiết kế transaction phù hợp.

## 10. Tài liệu tham khảo chính thức

- [Jakarta Messaging 3.1 — Publish/subscribe model và subscription lifecycle](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html).
- [Spring Framework — JMS annotation-driven listener](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html).
- [Spring Framework — JMS listener, transaction và acknowledgement](https://docs.spring.io/spring-framework/reference/integration/jms/using.html).
- [Spring — Getting Started: Messaging with JMS](https://spring.io/guides/gs/messaging-jms/).
