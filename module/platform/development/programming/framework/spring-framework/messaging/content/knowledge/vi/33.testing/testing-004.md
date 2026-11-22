# Kiểm thử JmsTemplate và listener với broker thực trong Spring JMS

## Mục tiêu

Một unit test có thể mock `JmsTemplate` để xác nhận ứng dụng gọi `convertAndSend` với đúng tham số. Nhưng test đó không chứng minh message đã được serialize đúng, kết nối tới broker thành công, destination tồn tại, listener nhận được message hoặc transaction/acknowledgement hoạt động như mong đợi.

Để kiểm tra luồng messaging thực tế, hãy chạy một broker JMS thật trong integration test. Với Spring Boot, một lựa chọn gọn là Apache ActiveMQ Artemis chạy trong Testcontainers. Test sẽ khởi động broker bằng Docker, cấu hình Spring kết nối tới cổng động của container, gửi message bằng `JmsTemplate`, rồi xác nhận một `@JmsListener` thực sự đã nhận và xử lý message.

Mục tiêu của bài này là kiểm tra đường đi:

`test → JmsTemplate → ConnectionFactory → broker → destination → listener container → @JmsListener`

Đây là integration test của hạ tầng messaging. Unit test vẫn hữu ích cho logic nghiệp vụ thuần, nhưng không thể thay thế kiểm thử với broker.

## 1. Những gì cần kiểm tra với broker thật

Broker thật giúp phát hiện các lỗi mà mock hoặc embedded broker có thể bỏ sót:

- URL, cổng, username/password và giao thức kết nối không đúng.
- Queue hoặc topic chưa được tạo, sai tên destination hoặc sai chế độ queue/topic.
- Message converter serialize/deserialize không tương thích giữa producer và consumer.
- JMS header, property, correlation ID, delivery mode, priority hoặc time-to-live bị mất hay sai.
- Listener container không khởi động, cấu hình concurrency sai hoặc kết nối lại không hoạt động.
- Message bị acknowledge quá sớm, rollback, redelivery hoặc chuyển sang dead-letter queue (DLQ) không như dự kiến.
- Broker-specific behavior khác với cấu hình giả lập hoặc provider khác.

Không phải test nào cũng cần chạy qua broker. Hãy chọn các luồng quan trọng: gửi/nhận cơ bản, converter, routing tới queue/topic, transaction, redelivery/DLQ và các cấu hình bảo mật liên quan.

## 2. Dependency cho Spring Boot và Testcontainers

Ví dụ dưới đây dùng Java 17+, Spring Boot với Jakarta JMS, JUnit 5 và Testcontainers 2.x. Spring Boot quản lý phiên bản các dependency Spring. Testcontainers module và JUnit integration phải dùng cùng một phiên bản.

Maven:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-artemis</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>testcontainers-junit-jupiter</artifactId>
        <version>2.0.5</version>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>testcontainers-activemq</artifactId>
        <version>2.0.5</version>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Nếu dùng Gradle:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-artemis")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.testcontainers:testcontainers-junit-jupiter:2.0.5")
    testImplementation("org.testcontainers:testcontainers-activemq:2.0.5")
}
~~~

Testcontainers cung cấp `ArtemisContainer` cho ActiveMQ Artemis. Module này hỗ trợ image Artemis và cho phép cấu hình username/password, khởi động container, lấy broker URL đã ánh xạ và dừng container sau test.

Dùng image có version cố định thay vì `latest`. Ví dụ dùng trong bài là `apache/activemq-artemis:2.32.0-alpine`, cùng họ image được tài liệu Testcontainers minh họa. Khi nâng version, hãy kiểm tra image tag và khả năng tương thích với broker mà môi trường production đang chạy.

## 3. Cấu hình Spring kết nối tới broker container

Khi test dùng Artemis container, Spring Boot phải kết nối tới broker bên ngoài. Đặt rõ:

- `spring.artemis.mode=native` để dùng broker chạy trong container, tránh tự khởi động embedded broker.
- `spring.artemis.broker-url` lấy từ `ArtemisContainer.getBrokerUrl()`.
- Username và password lấy từ chính container.
- Queue/topic được cấu hình nhất quán cho producer và listener.

Spring Boot auto-configure `ConnectionFactory`, `JmsTemplate` và listener infrastructure khi có starter Artemis. Các thuộc tính Artemis nằm dưới prefix `spring.artemis.*`; các thiết lập chung của JMS nằm dưới `spring.jms.*`.

Ví dụ cấu hình runtime trong `application-test.yml` khi broker có địa chỉ cố định:

~~~yaml
spring:
  artemis:
    mode: native
    broker-url: tcp://localhost:61616
    user: testcontainers
    password: testcontainers
  jms:
    pub-sub-domain: false

app:
  jms:
    orders-queue: orders.integration
~~~

Trong Testcontainers, không hard-code `localhost:61616`. Testcontainers ánh xạ cổng container sang một cổng trống trên host. Dùng URL mà container trả về sau khi khởi động.

## 4. Tạo listener có thể quan sát trong test

Listener chạy ở thread của listener container, độc lập với thread của test. Vì vậy không thể gọi method listener trực tiếp rồi kết luận broker đã chuyển message thành công.

Trong ví dụ này, listener ghi payload vào một `BlockingQueue`. Test chờ có giới hạn thời gian để nhận message; không dùng `Thread.sleep` cố định.

~~~java
import java.time.Duration;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import org.springframework.jms.annotation.JmsListener;

public class CapturingOrderListener {

    private final BlockingQueue<String> received =
            new LinkedBlockingQueue<>();

    @JmsListener(
            id = "orders-test-listener",
            destination = "${app.jms.orders-queue}")
    public void onMessage(String body) {
        received.add(body);
    }

    public String awaitMessage(Duration timeout)
            throws InterruptedException {
        return received.poll(
                timeout.toMillis(),
                TimeUnit.MILLISECONDS);
    }
}
~~~

Đây là listener dành cho test. Trong ứng dụng thật, listener thường gọi application service và chỉ giữ trạng thái quan sát tối thiểu. Không dùng collection không thread-safe để chia sẻ dữ liệu giữa listener thread và test thread.

## 5. Integration test hoàn chỉnh với ArtemisContainer

Test sau khởi động broker thật, đưa địa chỉ động vào Spring context, gửi một chuỗi qua `JmsTemplate`, rồi đợi listener nhận đúng nội dung.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Duration;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.activemq.ArtemisContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest(properties = {
        "spring.artemis.mode=native",
        "app.jms.orders-queue=orders.integration",
        "spring.jms.pub-sub-domain=false"
})
@Import(JmsBrokerIntegrationTest.ListenerConfig.class)
class JmsBrokerIntegrationTest {

    private static final String QUEUE = "orders.integration";

    @Container
    static final ArtemisContainer broker =
            new ArtemisContainer("apache/activemq-artemis:2.32.0-alpine")
                    .withUser("testcontainers")
                    .withPassword("testcontainers");

    @DynamicPropertySource
    static void brokerProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.artemis.mode", () -> "native");
        registry.add("spring.artemis.broker-url", broker::getBrokerUrl);
        registry.add("spring.artemis.user", broker::getUser);
        registry.add("spring.artemis.password", broker::getPassword);
    }

    @Autowired
    JmsTemplate jmsTemplate;

    @Autowired
    CapturingOrderListener listener;

    @Test
    void sendsMessageThroughBrokerAndReceivesIt() throws Exception {
        String payload = "order-" + UUID.randomUUID();

        jmsTemplate.convertAndSend(QUEUE, payload);

        assertEquals(
                payload,
                listener.awaitMessage(Duration.ofSeconds(10)));
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class ListenerConfig {

        @Bean
        CapturingOrderListener capturingOrderListener() {
            return new CapturingOrderListener();
        }
    }
}
~~~

Các chi tiết quan trọng:

1. `@Container` khai báo Artemis container do Testcontainers quản lý. Vì là field static, container có vòng đời theo test class và được chia sẻ giữa các method trong class.
2. `@Testcontainers` đăng ký JUnit 5 extension để khởi động container trước test và dừng nó sau test.
3. `@DynamicPropertySource` đăng ký các thuộc tính sau khi Testcontainers đã cung cấp endpoint động. Spring context vì vậy nhận đúng broker URL, user và password.
4. `spring.artemis.mode=native` buộc ứng dụng dùng broker trong container.
5. `JmsTemplate.convertAndSend` gửi payload qua JMS provider thật.
6. `@JmsListener` được listener container quản lý và nhận message bất đồng bộ.
7. `BlockingQueue.poll` chờ tối đa 10 giây. Nếu listener không nhận được message, test thất bại với giá trị nhận là null thay vì treo vô hạn.

Ví dụ dùng chuỗi để tập trung kiểm tra kết nối và delivery. Với DTO, cần cấu hình `MessageConverter` và viết thêm test chứng minh object được chuyển đổi chính xác theo cả hai chiều.

Trong Spring Boot, listener infrastructure được auto-configure khi JMS có trên classpath; thường không cần tự thêm `@EnableJms`. Nếu dùng Spring Framework thuần, hãy khai báo `@EnableJms`, `ConnectionFactory`, `JmsTemplate` và `JmsListenerContainerFactory` phù hợp.

## 6. Kiểm tra MessageConverter và payload có kiểu

Một test gửi String chỉ xác nhận đường truyền cho kiểu đơn giản. Nếu ứng dụng gửi POJO, JSON hoặc message có header tùy chỉnh, phải kiểm tra converter thật.

Các trường hợp nên kiểm tra:

- Producer tạo đúng loại JMS message, ví dụ `TextMessage` hoặc `BytesMessage`.
- Consumer giải mã về đúng kiểu DTO và giữ nguyên các field.
- Field null, Unicode, ngày giờ, số thập phân và collection được serialize theo hợp đồng.
- Type mapping chỉ cho phép những kiểu đã đăng ký. Không tin một class name tùy ý lấy từ message property để nạp class động.
- Content type và message property cần thiết được giữ nguyên.
- Message không hợp lệ tạo ra lỗi conversion có thể quan sát và xử lý theo chính sách.

Có thể dùng một `MessageConverter` bean chung để Spring Boot gắn vào `JmsTemplate` và listener factory auto-configured. Nếu tạo listener factory riêng, phải cấu hình converter tương ứng cho factory đó; nếu không, producer và consumer có thể dùng hai quy tắc chuyển đổi khác nhau.

Ví dụ gửi message có correlation ID:

~~~java
String correlationId = UUID.randomUUID().toString();

jmsTemplate.send(QUEUE, session -> {
    var message = session.createTextMessage("order-created");
    message.setJMSCorrelationID(correlationId);
    message.setStringProperty("eventType", "OrderCreated");
    return message;
});
~~~

Nếu correlation ID hoặc property là một phần của hợp đồng, listener test nên nhận `jakarta.jms.Message` hoặc `TextMessage` và assert cả body lẫn header/property. Không chỉ kiểm tra payload rồi bỏ qua metadata.

## 7. Queue, topic và destination

JMS phân biệt queue và topic:

- **Queue:** một message thường được phân phối cho một consumer trong nhóm cạnh tranh. Dùng cho work queue và command processing.
- **Topic:** message được phân phối tới các subscriber đang đăng ký. Cần kiểm tra subscription, durable subscription và thời điểm subscriber bắt đầu lắng nghe.

Spring Boot mặc định cấu hình `JmsTemplate` và listener container theo queue mode (`pubSubDomain=false`). Nếu kiểm thử topic, cấu hình cả producer lẫn listener container sang topic mode. Hai phía không thống nhất sẽ làm test gửi vào một loại destination nhưng consumer nghe loại khác.

Destination phải được broker tạo hoặc cho phép auto-create theo cấu hình. Trong production, nên quản lý queue/topic, DLQ và policy bằng cấu hình broker hoặc hạ tầng triển khai. Test có thể dùng destination riêng như `orders.integration`; không dùng chung queue production hoặc queue của test khác.

Với topic durable, cần kiểm tra tên subscription, client ID, persistent delivery và việc subscriber có thể nhận message sau khi offline. Test subscriber thông thường chỉ chứng minh subscriber đang hoạt động nhận được message.

## 8. Transaction, acknowledgement và redelivery

Một listener thành công thường acknowledge message sau khi xử lý. Nếu xử lý thất bại, session transaction và broker policy quyết định message được rollback, redelivery hoặc chuyển DLQ.

Spring Boot cấu hình listener factory mặc định theo hướng transactional. Nếu có JTA transaction manager, nó được gắn vào listener container; nếu không, `sessionTransacted` được bật. Có thể phối hợp transaction lưu trữ cục bộ với việc xử lý message bằng `@Transactional` trên listener hoặc service được gọi từ listener. Tuy nhiên, không nên mặc định rằng một transaction cục bộ tự động tạo ra atomic commit giữa nhiều hệ thống độc lập; hãy chọn XA/JTA hoặc outbox/inbox khi cần đảm bảo nhất quán xuyên resource.

Nên viết integration test cho các tình huống:

1. **Xử lý thành công:** listener cập nhật trạng thái, message được acknowledge và không xuất hiện lại.
2. **Ném exception:** transaction rollback theo cấu hình, broker thực hiện redelivery theo policy.
3. **Hết số lần thử:** message được chuyển tới dead-letter queue theo policy.
4. **Lỗi sau side effect:** kiểm tra idempotency để redelivery không tạo bản ghi hoặc giao dịch trùng.
5. **Broker tạm thời mất kết nối:** producer/consumer phục hồi theo reconnect policy và không làm mất message đã được broker xác nhận.

Không kiểm tra redelivery bằng cách chỉ đếm số lần method listener được gọi nếu test không cấu hình transaction và broker redelivery policy rõ ràng. Số lần gọi có thể khác với số lần message được broker gửi lại. Hãy quan sát delivery count, trạng thái queue và DLQ bằng API/management phù hợp với broker.

Đặc biệt, test cancellation hoặc timeout ở phía producer không chứng minh message chưa được broker xử lý. Khi kết quả gửi không rõ, hãy dùng message ID, business key hoặc idempotency key để xác định trạng thái và ngăn side effect trùng.

## 9. Kiểm tra listener container và xử lý bất đồng bộ

`@JmsListener` không được gọi trực tiếp bởi `JmsTemplate`; Spring tạo một listener container để nhận message ở thread riêng. Integration test cần xác nhận container đang chạy và chờ kết quả bằng cơ chế có timeout.

Có thể lấy container qua `JmsListenerEndpointRegistry` nếu cần kiểm tra trạng thái:

~~~java
@Autowired
JmsListenerEndpointRegistry registry;

@Test
void listenerContainerIsRunning() {
    var container =
            registry.getListenerContainer("orders-test-listener");

    assertNotNull(container);
    assertTrue(container.isRunning());
}
~~~

ID phải khớp với thuộc tính `id` trên `@JmsListener`. Kiểm tra `isRunning()` chỉ xác nhận container đang hoạt động; test gửi/nhận vẫn cần để chứng minh message đi qua broker.

Không dùng `JmsTemplate.receive()` như cơ chế chính cho consumer bất đồng bộ. `receive` là thao tác đồng bộ và block thread gọi. Với ứng dụng nhận message liên tục, listener container như `DefaultMessageListenerContainer` phù hợp hơn.

Khi cấu hình concurrency, hãy kiểm thử số consumer thực tế, thứ tự message trong phạm vi broker đảm bảo, và việc xử lý cùng lúc có gây race condition hay không. Không giả định thứ tự toàn cục nếu có nhiều consumer cạnh tranh hoặc nhiều producer.

## 10. Cách tránh integration test chập chờn

- Dùng timeout hữu hạn và polling assertion; tránh `Thread.sleep(1000)` hoặc chờ cố định tùy ý.
- Dùng payload hoặc correlation ID duy nhất để nhận diện message của test hiện tại.
- Không chia sẻ destination giữa các test chạy song song nếu chúng có thể đọc message của nhau.
- Dọn trạng thái listener test giữa các method hoặc dùng queue riêng theo test.
- Đảm bảo broker đã sẵn sàng trước khi Spring context kết nối.
- Dùng static container cho các test trong cùng class để tránh khởi động broker lặp lại.
- Nếu Spring TestContext cache một context giữa nhiều test class, bảo đảm container không bị dừng trong khi context đó vẫn được tái sử dụng. Có thể dùng singleton container cho cả suite hoặc quản lý context/container lifecycle nhất quán.
- Khi cần kiểm tra chính xác số message, dùng destination riêng và xác nhận cả số lượng lẫn nội dung.
- Không để message còn tồn đọng làm test sau nhận nhầm kết quả của test trước.
- Ghim version broker image và dependency Testcontainers để kết quả CI có thể lặp lại.

Integration test yêu cầu Docker hoặc container runtime tương thích trên máy dev và CI. Nếu Docker không khả dụng, test cần báo rõ môi trường không đáp ứng; không âm thầm thay broker thật bằng mock mà vẫn báo integration test đã pass.

## 11. Chạy test và chẩn đoán lỗi

Với Maven:

~~~bash
./mvnw test
~~~

Với Gradle:

~~~bash
./gradlew test
~~~

Khi test thất bại, phân loại theo tầng:

| Triệu chứng | Điều cần kiểm tra |
| --- | --- |
| Container không khởi động | Docker daemon, image pull, architecture và log container |
| Connection refused | Broker URL, mapped port, thời điểm container ready và transport |
| Authentication failed | Username/password cấu hình trong container và Spring properties |
| Listener không nhận message | Queue/topic mode, destination name, listener container state và auto-startup |
| Payload sai kiểu | MessageConverter, JMS message type và type mapping |
| Message đến nhiều lần | Session transaction, exception path, acknowledgement và redelivery policy |
| Message vào DLQ | Broker address/queue policy, số lần thử, exception và routing DLQ |
| Test pass riêng nhưng fail khi chạy song song | Destination dùng chung, message tồn đọng, container/context lifecycle và race condition |

Khi debug, đọc log của broker container cùng log Spring listener container. Có thể bật log phù hợp cho package JMS/provider trong profile test; tránh bật log payload nhạy cảm hoặc để log quá chi tiết trong CI lâu dài.

## 12. Phạm vi test nên có

| Loại test | Mục tiêu | Broker thật? |
| --- | --- | --- |
| Unit test service | Kiểm tra quy tắc nghiệp vụ, không phụ thuộc JMS | Không |
| Unit test publisher/listener adapter | Kiểm tra mapping và nhánh xử lý bằng mock khi phù hợp | Không |
| JMS integration test | Kiểm tra ConnectionFactory, JmsTemplate, converter, listener và destination | Có |
| Broker policy test | Kiểm tra redelivery, DLQ, expiry, persistence và acknowledgement | Có |
| End-to-end test | Kiểm tra producer, broker, listener và downstream service cùng hoạt động | Thường có ở pipeline phù hợp |

Không cần khởi động broker cho mọi unit test. Đặt integration test trong nhóm riêng nếu khởi động Docker làm suite chậm; nhưng vẫn chạy chúng thường xuyên trong CI để phát hiện lỗi tích hợp trước khi deploy.

## 13. Checklist hoàn thành

- [ ] Test sử dụng broker container thật và image có version cố định.
- [ ] Testcontainers quản lý vòng đời broker và cung cấp endpoint động.
- [ ] Spring Boot được cấu hình `mode=native`, URL, username và password của container.
- [ ] `JmsTemplate` gửi message qua broker, không phải mock.
- [ ] `@JmsListener` nhận message qua listener container thật.
- [ ] Test xác nhận nội dung payload và timeout rõ ràng.
- [ ] MessageConverter, headers và properties được kiểm tra nếu thuộc hợp đồng.
- [ ] Queue/topic mode và destination được cấu hình nhất quán.
- [ ] Transaction, acknowledgement, redelivery và DLQ được kiểm tra khi ứng dụng phụ thuộc vào chúng.
- [ ] Test cô lập destination và không rò rỉ message giữa các method.
- [ ] Container lifecycle tương thích với Spring context cache.
- [ ] CI có Docker/container runtime và chạy nhóm integration test.

## Tài liệu tham khảo

- [Spring Boot — JMS](https://docs.spring.io/spring-boot/reference/messaging/jms.html): auto-configuration của ConnectionFactory, JmsTemplate, @JmsListener, Artemis và listener transaction.
- [Spring Framework — JMS](https://docs.spring.io/spring-framework/reference/integration/jms.html): JmsTemplate, listener containers, message conversion và transaction support.
- [Spring Guide — Messaging with JMS](https://spring.io/guides/gs/messaging-jms/): ví dụ JmsTemplate gửi message và @JmsListener nhận message.
- [Testcontainers for Java — ActiveMQ and Artemis](https://java.testcontainers.org/modules/activemq/): ArtemisContainer, credentials và dependency module.
- [Testcontainers for Java — JUnit 5](https://java.testcontainers.org/test_framework_integration/junit_5/): @Testcontainers, @Container và vòng đời container.
- [Apache ActiveMQ Artemis — Docker](https://artemis.apache.org/components/artemis/documentation/latest/docker.html): official image, cổng messaging và biến môi trường khởi tạo broker.

