# MessageListenerAdapter cho đối tượng Java thông thường trong Spring JMS

## 1. Mục tiêu: biến một POJO thành JMS message listener

Trong Spring JMS, listener không nhất thiết phải là class triển khai trực tiếp `jakarta.jms.MessageListener`. Nhiều hệ thống đã có sẵn lớp Java nhận một chuỗi, byte array hoặc object nghiệp vụ, ví dụ:

~~~java
public class OrderHandler {
    public void handleMessage(String orderText) {
        System.out.println("ORDER=" + orderText);
    }
}
~~~

Đây là **POJO (Plain Old Java Object)**: không implements JMS interface, không cần import `jakarta.jms.*`, không biết broker, connection, session hay acknowledge mode. Nhưng một JMS provider vốn giao callback bằng `MessageListener.onMessage(Message)`, nghĩa là cần một thành phần ở giữa để đổi JMS message thành tham số cho method của POJO.

Spring Framework cung cấp **`org.springframework.jms.listener.adapter.MessageListenerAdapter`** để làm cầu nối:

~~~text
Artemis / JMS Broker
         |
         | Jakarta JMS Message
         v
DefaultMessageListenerContainer
         |
         | invokes listener
         v
MessageListenerAdapter
         |
         | MessageConverter:
         | TextMessage -> String
         | BytesMessage -> byte[]
         | MapMessage -> Map
         | ObjectMessage -> Serializable (cần thận trọng)
         |
         | tìm method trên delegate và gọi qua reflection
         v
POJO OrderHandler
         |
         +-- handleMessage(String body)
         +-- hoặc tên method do bạn cấu hình
~~~

**Phạm vi của adapter:** nó chuyển kiểu dữ liệu và điều phối lời gọi vào object Java thông thường. Nó **không** tự kết nối broker, tạo thread consumer, bảo đảm transaction hoặc lưu trạng thái xử lý. Những việc đó thuộc `ConnectionFactory`, listener container, provider và code nghiệp vụ.

Sau bài này bạn có thể:

1. Giải thích vai trò delegate, listener adapter, converter và container.
2. Cấu hình method mặc định `handleMessage` hoặc đổi tên bằng `setDefaultListenerMethod`.
3. Đọc body tự động thành String/byte[]/Map hoặc tắt converter để nhận raw JMS `Message`.
4. Biết khi nào adapter tự gửi reply từ giá trị trả về.
5. Tự viết ứng dụng Java 17/Spring Boot/Artemis gửi một TextMessage và gọi POJO.
6. Hiểu lỗi method không khớp, message conversion, transaction/ACK và kiểm thử.

## 2. MessageListenerAdapter hoạt động như thế nào?

Theo Spring Framework, `MessageListenerAdapter` triển khai các giao diện listener cần thiết để đứng ở vị trí một JMS message listener, trong đó có `jakarta.jms.MessageListener` và `org.springframework.jms.listener.SessionAwareMessageListener`. Nó giữ một **delegate** — object thật chứa logic xử lý.

~~~java
OrderHandler handler = new OrderHandler();
MessageListenerAdapter adapter =
        new MessageListenerAdapter(handler);
~~~

Khi container nhận message, nó gọi adapter. Adapter thường thực hiện:

1. Nhận `jakarta.jms.Message` từ listener container.
2. Dùng `MessageConverter` (mặc định là `SimpleMessageConverter`) để lấy nội dung body thành Java value.
3. Xác định tên method của delegate; mặc định **`handleMessage`**.
4. Gọi method phù hợp qua reflection với **một tham số** là Java value đã trích xuất.
5. Nếu method trả giá trị khác null, adapter có thể tạo và gửi **reply JMS** theo điều kiện cấu hình.
6. Nếu delegate ném exception, container áp dụng error handling/transaction/ACK riêng.

Ví dụ message đến là `TextMessage` chứa `"ORDER|O-42"`. Converter mặc định lấy `String` và adapter tìm method:

~~~java
public void handleMessage(String text)
~~~

Nó **không** tìm một method tùy ý theo tên `onMessage` nếu bạn chưa cấu hình tên đó.

### 2.1. POJO độc lập JMS đến mức nào?

Với method `handleMessage(String)`, lớp nghiệp vụ không dùng một import JMS nào. Nhưng bean adapter, converter, container và configuration **vẫn phụ thuộc Spring JMS**. Nếu muốn đổi broker/provider, POJO thường ít phải thay đổi; nếu chuyển hẳn sang Kafka thì cần adapter tương ứng hoặc một cổng nghiệp vụ riêng.

Đừng nhầm “POJO không implements JMS MessageListener” với “toàn ứng dụng không phụ thuộc JMS”. Ranh giới kiến trúc đúng là POJO chỉ thực thi nghiệp vụ; hạ tầng giải quyết transport.

## 3. Ba đối tượng cần phân biệt

| Thành phần | Kiểu/đối tượng | Công việc |
| --- | --- | --- |
| **Delegate** | `OrderHandler` POJO | Method như `handleMessage(String)` hoặc `onOrder(String)` |
| **Adapter** | `MessageListenerAdapter` | Convert JMS message và gọi delegate qua reflection |
| **Container** | `DefaultMessageListenerContainer` / `SimpleMessageListenerContainer` | Quản lý connection/session/consumer, nhận message, ACK, transaction và lifecycle |

Một bean `MessageListenerAdapter` **đứng riêng** trong Spring context chưa đủ để broker giao message. Cần đăng ký adapter với một listener container:

~~~java
DefaultMessageListenerContainer container =
        new DefaultMessageListenerContainer();
container.setConnectionFactory(connectionFactory);
container.setDestinationName("orders.in");
container.setMessageListener(adapter);
~~~

Đây là **snippet cấu hình**, cần có biến `connectionFactory` và `adapter` phù hợp. Với một Spring bean container hoàn chỉnh, Spring sẽ quản lý `afterPropertiesSet`, startup, shutdown và resource cleanup.

### 3.1. DefaultMessageListenerContainer hay SimpleMessageListenerContainer?

- `DefaultMessageListenerContainer`: mô hình polling qua JMS receive bên trong container, hỗ trợ recovery, điều chỉnh concurrent consumer và transaction behavior linh hoạt. Thường là lựa chọn tốt cho ứng dụng Spring có yêu cầu vận hành.
- `SimpleMessageListenerContainer`: ít cơ chế hơn, đăng ký `MessageListener` trực tiếp với JMS provider, phù hợp một số trường hợp đơn giản. Nó có các giới hạn riêng về transaction/container.
- Hai loại đều có thể dùng adapter làm message listener; **adapter không tự quyết định** nên chọn container nào.

Chỉ gọi `adapter.onMessage(...)` trực tiếp trong unit test không có nghĩa container đã hoạt động hoặc broker có thể kết nối.

## 4. Method mặc định handleMessage và cách đổi tên

### 4.1. Không cấu hình thêm: mặc định handleMessage

POJO:

~~~java
public class PlainOrderHandler {
    public void handleMessage(String orderText) {
        System.out.println("ORDER=" + orderText);
    }
}
~~~

Adapter:

~~~java
MessageListenerAdapter adapter =
        new MessageListenerAdapter(new PlainOrderHandler());
~~~

Spring mặc định tìm method có tên **`handleMessage`**. Nếu TextMessage được chuyển thành String, signature phù hợp là `handleMessage(String)`.

### 4.2. Đổi sang tên phù hợp nghiệp vụ

POJO legacy có thể đã có:

~~~java
public class LegacyOrderProcessor {
    public void processOrder(String payload) {
        System.out.println("PROCESS=" + payload);
    }
}
~~~

Cấu hình:

~~~java
MessageListenerAdapter adapter =
        new MessageListenerAdapter(new LegacyOrderProcessor());
adapter.setDefaultListenerMethod("processOrder");
~~~

Không cần đổi tên method trong code legacy. Nếu đổi thành `processOrder` nhưng quên gọi `setDefaultListenerMethod`, adapter vẫn tìm `handleMessage` và sẽ báo lỗi khi message tới.

### 4.3. Method có một tham số và overload

Một delegate có thể khai báo:

~~~java
public void handleMessage(String text) { /* ... */ }
public void handleMessage(byte[] bytes) { /* ... */ }
public void handleMessage(java.util.Map<?, ?> map) { /* ... */ }
~~~

`SimpleMessageConverter` chuyển từng loại JMS body thành Java value; adapter dựa trên tên method và kiểu tham số phù hợp để invoke. Nếu có overload mơ hồ hoặc conversion không trả kiểu mong đợi, có thể gặp lỗi reflection/method resolution.

**Không nên** dùng nhiều overload thiếu rõ ràng chỉ để bắt đủ loại message. Với hệ thống có message schema nghiêm ngặt, việc chuẩn hóa converter và một method nghiệp vụ cụ thể thường dễ bảo trì hơn.

## 5. MessageConverter mặc định chuyển các kiểu body nào?

`MessageListenerAdapter` mặc định sử dụng **`SimpleMessageConverter`** của Spring JMS. Với các message điển hình:

| JMS message đến | Giá trị truyền vào POJO |
| --- | --- |
| `TextMessage` | `String` |
| `BytesMessage` | `byte[]` |
| `MapMessage` | `java.util.Map` |
| `ObjectMessage` | Object Serializable được deserialize theo provider |
| `StreamMessage` hoặc kiểu khác | Tùy hỗ trợ của converter; có thể không chuyển được |

Ví dụ:

~~~text
Broker gửi TextMessage(body="ORDER|O-42")
    -> SimpleMessageConverter
    -> String "ORDER|O-42"
    -> handler.processOrder(String)
~~~

Nếu broker gửi BytesMessage JSON UTF-8 mà handler chỉ có `processOrder(String)`, adapter **không tự decode byte[] thành String** theo quy tắc mặc định. Kết quả có thể là method không tìm được hoặc lỗi conversion/argument. Khi yêu cầu JSON/DTO, cần chọn converter nhất quán trên cả producer và consumer.

### 5.1. Đừng giả định POJO JSON tự thành DTO

Nhận một TextMessage có body:

~~~json
{"orderId":"O-42","amountVnd":125000}
~~~

không tự khiến `SimpleMessageConverter` tạo một `OrderCreated` record. Mặc định nó trả **String** JSON. Để dùng method `handleMessage(OrderCreated event)` cần một `MessageConverter` JSON được cấu hình và đủ type information.

Spring có `MappingJackson2MessageConverter` dùng Jackson. Khi thiết kế:

- Cần thống nhất `MessageType.TEXT` hoặc `MessageType.BYTES`.
- Cần type ID property/mapping nếu converter phải suy ra Java type từ message.
- Hai phía cần dùng schema và converter tương thích.
- Lỗi parsing/schema/DTO xảy ra **trước** khi delegate method được gọi.
- Không mở rộng tự do các class mà message bên ngoài có thể yêu cầu deserialize.

### 5.2. Thận trọng với ObjectMessage

`ObjectMessage` có thể kéo theo Java native serialization/deserialization; đó không phải định dạng JSON độc lập ngôn ngữ. Với message từ nguồn không tin cậy, deserialization có nguy cơ bảo mật đáng kể. Ưu tiên TextMessage JSON hoặc BytesMessage với schema rõ, allowlist type và kiểm thử dữ liệu.

## 6. Tắt MessageConverter để nhận raw JMS Message

Một số delegate cần truy cập `JMSCorrelationID`, `JMSReplyTo`, `JMSType`, properties hoặc một kiểu raw body cụ thể. Khi đó adapter có thể tắt automatic extraction:

~~~java
import jakarta.jms.TextMessage;

public class RawTextHandler {
    public void receive(TextMessage message) throws Exception {
        String body = message.getText();
        String correlation = message.getJMSCorrelationID();
        System.out.println("BODY=" + body + ", CORR=" + correlation);
    }
}
~~~

Cấu hình:

~~~java
MessageListenerAdapter adapter =
        new MessageListenerAdapter(new RawTextHandler());
adapter.setDefaultListenerMethod("receive");
adapter.setMessageConverter(null);
~~~

Khi converter là `null`, adapter không trích xuất String body mà truyền raw JMS `Message` để method phù hợp nhận. Với ví dụ này, delegate **không còn độc lập JMS** vì method nhận `TextMessage`.

Các chú ý quan trọng:

1. Raw `Message` có thể là `TextMessage`, `BytesMessage` hoặc kiểu khác; dùng kiểu tham số phù hợp và không ép kiểu khi chưa xác minh.
2. Đọc JMS headers/properties có thể ném `JMSException`.
3. Nếu producer đổi body type từ TextMessage sang BytesMessage, method `receive(TextMessage)` không còn nhận hợp lệ.
4. Không đặt converter `null` chỉ để giải quyết lỗi JSON parsing; nó bỏ bước conversion, còn nhu cầu xử lý JSON vẫn phải có.
5. Nếu nghiệp vụ cần cùng lúc payload và metadata, có thể thiết kế một application DTO/envelope riêng được dựng ở adapter hạ tầng thay vì ép domain method nhận JMS raw API.

## 7. Khi method trả về giá trị: adapter có thể gửi JMS reply

Đây là một tính năng dễ bị bỏ sót. `MessageListenerAdapter` không chỉ convert request và gọi delegate. Nếu method trả giá trị **khác null**, adapter có thể tạo response JMS message và gửi vào destination trả lời.

Ví dụ delegate:

~~~java
public class PricingHandler {
    public String handleMessage(String request) {
        return "PRICE_OK:" + request;
    }
}
~~~

Nếu request đến có `JMSReplyTo` hợp lệ, adapter chạy theo đường `SessionAwareMessageListener` của Spring container có thể chuyển String thành TextMessage và gửi tới reply destination.

~~~text
Requestor
   |
   | TextMessage("PRICE:SKU-42", JMSReplyTo=temp.reply)
   v
Queue pricing.requests
   |
   v
DefaultMessageListenerContainer
   |
   v
MessageListenerAdapter
   |
   v
PricingHandler.handleMessage(String)
   |
   +-- returns "PRICE_OK:PRICE:SKU-42"
   |
   v
Adapter creates TextMessage reply
   |
   v
temp.reply queue
~~~

Nếu request không có `JMSReplyTo`, có thể cấu hình fallback:

~~~java
adapter.setDefaultResponseQueueName("pricing.replies");
~~~

**Giới hạn quan trọng:** Javadoc của Spring ghi rõ khả năng gửi response tự động được hỗ trợ khi dùng entry point **`SessionAwareMessageListener.onMessage(Message, Session)`** (điển hình qua Spring listener container). Nếu chỉ invoke adapter qua JMS `MessageListener.onMessage(Message)` theo đường không có session, việc tạo response **không được hỗ trợ** như cùng luồng session-aware.

Nếu delegate trả non-null nhưng không có reply destination hợp lệ, không coi đó là kết quả “không sao” mặc định. Cần xác minh behavior/error handling theo adapter và cấu hình. Với consumer chỉ xử lý event, nên dùng **`void` method** để không yêu cầu reply ngoài ý muốn.

### 7.1. Reply không bằng transaction nghiệp vụ

Một response message được gửi không tự chứng minh database transaction và JMS ACK đã commit cùng nhau. Cần kiểm tra session transacted/external transaction manager và chính sách request/reply của broker. Nếu handler gửi reply nhưng session rollback, response có thể bị rollback cùng transaction khi thực sự dùng chung session; không nên suy diễn khi dùng resource khác.

### 7.2. Không tự cho rằng result String là response HTTP

Giá trị return của POJO qua adapter là kết quả cho **JMS** theo cấu hình reply; không phải HTTP response hay một Java return value được caller producer đồng bộ nhìn thấy. Nếu cần request/reply, producer cũng phải dùng pattern phù hợp với `JMSReplyTo`, correlation và receive timeout.

## 8. Bài thực hành đầy đủ: POJO nhận TextMessage qua MessageListenerAdapter

Mục tiêu: dùng Spring Boot 3.x, Java 17, Apache Artemis. Producer gửi một String, listener container nhận, adapter tự đổi TextMessage thành String và gọi **method `onOrder(String)`** của một POJO. Không dùng `@JmsListener` trên POJO.

### 8.1. Khởi động Artemis local

Máy có Docker, chạy broker demo:

~~~bash
docker run --detach --rm --name artemis-adapter-demo -p 127.0.0.1:61616:61616 -p 127.0.0.1:8161:8161 -e ARTEMIS_USER=demo -e ARTEMIS_PASSWORD=demo apache/artemis:latest
~~~

Chờ broker sẵn sàng, xem:

~~~bash
docker logs artemis-adapter-demo
~~~

Đây là cấu hình học tập. `demo/demo` không được dùng trên production. Nếu broker tắt auto-create Queue, tạo sẵn `orders.adapter.demo` và cấp quyền send/consume cho tài khoản dịch vụ.

### 8.2. Cấu trúc dự án

~~~text
jms-pojo-adapter/
  settings.gradle
  build.gradle
  src/main/resources/application.properties
  src/main/java/demo/jms/
    PojoAdapterApplication.java
    OrderMessageHandler.java
    JmsListenerConfiguration.java
  src/test/java/demo/jms/
    OrderMessageAdapterTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'jms-pojo-adapter'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'demo'
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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Version được cố định để mô tả project thống nhất, không hàm ý Spring Boot 3.3.0 là phiên bản mới nhất. Khi triển khai thực tế, dùng bản maintenance/security tương thích. Vì dùng Spring Boot 3/Framework 6, mọi JMS type phải thuộc package **`jakarta.jms`**, không phải `javax.jms`.

`src/main/resources/application.properties`:

~~~properties
spring.main.web-application-type=none
spring.artemis.mode=native
spring.artemis.broker-url=${JMS_BROKER_URL:tcp://localhost:61616}
spring.artemis.user=${JMS_BROKER_USER:demo}
spring.artemis.password=${JMS_BROKER_PASSWORD:demo}
spring.jms.pub-sub-domain=false
spring.jms.cache.enabled=false
~~~

Bản lưu dùng property placeholder chuẩn của Spring: ví dụ `$` + `{JMS_BROKER_URL:tcp://localhost:61616}`. Default demo chỉ dành cho lab; production cần secret management. `spring.jms.cache.enabled=false` giữ factory trong ví dụ đơn giản là factory gốc để container độc lập quản lý JMS connection. Trong hệ thống production, cấu hình cache/pool cần được thiết kế theo workload, không mặc định copy tùy chọn này.

### 8.3. Lớp POJO xử lý nghiệp vụ

`src/main/java/demo/jms/OrderMessageHandler.java`:

~~~java
package demo.jms;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Component;

@Component
public class OrderMessageHandler {

    private final CountDownLatch received = new CountDownLatch(1);
    private volatile String lastBody;

    // POJO method: không có JMS Message hoặc Session.
    public void onOrder(String body) {
        if (body == null || !body.startsWith("ORDER|")) {
            throw new IllegalArgumentException("Invalid order message");
        }

        lastBody = body;
        System.out.println("POJO_RECEIVED=" + body);
        received.countDown();
    }

    public boolean await(long timeout, TimeUnit unit)
            throws InterruptedException {
        return received.await(timeout, unit);
    }

    public String lastBody() {
        return lastBody;
    }
}
~~~

POJO vẫn là một class Java bình thường có thể khởi tạo bằng `new` trong unit test. `@Component` chỉ giúp Spring quản lý bean; nó **không phải listener annotation**. Method `onOrder` là public, chỉ nhận `String` và trả `void` nên adapter không cần xử lý reply.

`CountDownLatch` dùng để quan sát một message trong demo, **không phải cơ chế ACK**, không chứng minh broker transaction đã commit. Khi làm production, thay logic in log/latch bằng nghiệp vụ có validation, idempotency và transaction phù hợp.

### 8.4. Bean MessageListenerAdapter và listener container

`src/main/java/demo/jms/JmsListenerConfiguration.java`:

~~~java
package demo.jms;

import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.listener.DefaultMessageListenerContainer;
import org.springframework.jms.listener.adapter.MessageListenerAdapter;

@Configuration
public class JmsListenerConfiguration {

    @Bean
    MessageListenerAdapter orderMessageAdapter(
            OrderMessageHandler handler) {
        MessageListenerAdapter adapter =
                new MessageListenerAdapter(handler);

        // POJO method không mang tên mặc định handleMessage.
        adapter.setDefaultListenerMethod("onOrder");
        return adapter;
    }

    @Bean
    DefaultMessageListenerContainer orderListenerContainer(
            ConnectionFactory connectionFactory,
            MessageListenerAdapter orderMessageAdapter) {

        DefaultMessageListenerContainer container =
                new DefaultMessageListenerContainer();

        container.setConnectionFactory(connectionFactory);
        container.setDestinationName("orders.adapter.demo");
        container.setMessageListener(orderMessageAdapter);
        container.setConcurrentConsumers(1);

        // Để lỗi từ POJO có thể rollback JMS session.
        container.setSessionTransacted(true);
        return container;
    }
}
~~~

Đây là chỗ **wiring thực sự**:

1. Bean `OrderMessageHandler` chứa logic.
2. Bean `MessageListenerAdapter` bao bọc delegate và biết method `onOrder`.
3. Bean `DefaultMessageListenerContainer` giữ connection factory, Queue name, adapter và transaction policy.
4. Khi Spring tạo context, container bean được quản lý lifecycle; nó sẽ khởi động nhận message khi sẵn sàng.
5. Với session transacted, lỗi delegate xảy ra trước commit có thể khiến JMS transaction rollback và message được redeliver theo broker policy.

**Không cần `@EnableJms` trong ví dụ này**, vì không dùng các endpoint `@JmsListener`. Đây là listener container được đăng ký bằng tay dưới dạng Spring bean. `@EnableJms` có nhiệm vụ bật xử lý annotation listener, không làm thay đổi bản chất của adapter đã được đăng ký trực tiếp.

### 8.5. Main class và producer demo

`src/main/java/demo/jms/PojoAdapterApplication.java`:

~~~java
package demo.jms;

import java.util.concurrent.TimeUnit;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class PojoAdapterApplication {

    public static void main(String[] args) {
        SpringApplication.run(PojoAdapterApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(JmsTemplate jmsTemplate,
                           OrderMessageHandler handler) {
        return args -> {
            jmsTemplate.convertAndSend(
                    "orders.adapter.demo", "ORDER|O-42");

            // Chứng minh handler thực sự được gọi trong lab.
            boolean invoked = handler.await(10, TimeUnit.SECONDS);
            System.out.println("HANDLER_INVOKED=" + invoked);
        };
    }
}
~~~

Producer `convertAndSend` nhận String; với `SimpleMessageConverter` thông dụng, String được tạo thành JMS `TextMessage`. Container nhận TextMessage và adapter chuyển thành Java String cho `OrderMessageHandler.onOrder`.

Trên broker không có consumer khác và với cấu hình đã hợp lệ, kỳ vọng stdout của **chính code demo**:

~~~text
POJO_RECEIVED=ORDER|O-42
HANDLER_INVOKED=true
~~~

Các log Spring/Artemis và Gradle có thể xen kẽ. `HANDLER_INVOKED=true` chỉ cho biết method POJO đã chạy đến `CountDownLatch.countDown()`; không chứng minh DB nghiệp vụ đã commit hoặc JMS ACK đã được broker xác nhận. Nếu broker chưa sẵn sàng, credential/ACL sai hoặc có consumer khác cùng Queue lấy message, demo có thể không tạo đúng hai dòng.

### 8.6. Chạy

Với JDK 17+, Gradle tương thích và broker đang hoạt động:

~~~bash
gradle test
gradle bootRun
~~~

Trên repository có Gradle wrapper, có thể chạy `./gradlew test` và `./gradlew bootRun` trên Bash hoặc `.\gradlew.bat` trên Windows.

Kết thúc broker demo:

~~~bash
docker stop artemis-adapter-demo
~~~

## 9. Unit test cho chính adapter, không cần broker

Một unit test có thể dùng Mockito để tạo `TextMessage` giả, đưa nó vào `MessageListenerAdapter.onMessage(Message, Session)` và xác minh POJO được gọi đúng. Điều này giúp kiểm tra default converter + reflection dispatch mà không cần start Artemis.

`src/test/java/demo/jms/OrderMessageAdapterTest.java`:

~~~java
package demo.jms;

import jakarta.jms.TextMessage;
import org.junit.jupiter.api.Test;
import org.springframework.jms.listener.adapter.MessageListenerAdapter;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class OrderMessageAdapterTest {

    @Test
    void convertsTextMessageAndInvokesPojo() throws Exception {
        OrderMessageHandler handler = new OrderMessageHandler();

        MessageListenerAdapter adapter =
                new MessageListenerAdapter(handler);
        adapter.setDefaultListenerMethod("onOrder");

        TextMessage message = mock(TextMessage.class);
        when(message.getText()).thenReturn("ORDER|O-42");

        // Session bằng null chỉ phù hợp test void delegate:
        // không có automatic response cần được gửi.
        adapter.onMessage(message, null);

        assertEquals("ORDER|O-42", handler.lastBody());
    }
}
~~~

Test này chứng minh một `TextMessage` có body String được adapter chuyển và gọi đúng method `onOrder`; nó không chứng minh đã tạo broker connection, Queue có tồn tại, ACL hoạt động, hoặc session commit. Những điểm đó cần **integration test** chạy với broker thật.

### 9.1. Test trực tiếp POJO độc lập framework

Bởi vì POJO không nhận JMS type, bạn cũng có thể test:

~~~java
OrderMessageHandler handler = new OrderMessageHandler();
handler.onOrder("ORDER|O-42");
assertEquals("ORDER|O-42", handler.lastBody());
~~~

Đây là snippet nằm trong test method, cần import `assertEquals`. Nó cô lập logic validation/business khỏi adapter. Nên có **cả test POJO** và **test adapter**, nhưng tránh dựa vào mock-only test để khẳng định message đã được giao thực tế.

## 10. Khi nào dùng MessageListenerAdapter, khi nào dùng @JmsListener?

Spring hiện đại thường dùng `@JmsListener`:

~~~java
@Component
public class AnnotatedOrderListener {

    @JmsListener(destination = "orders.in")
    public void onOrder(String payload) {
        System.out.println(payload);
    }
}
~~~

Đây là **một phương án riêng**, không thêm vào cùng Queue với demo nếu không muốn competing consumers. Cần import `org.springframework.stereotype.Component` và `org.springframework.jms.annotation.JmsListener` trong class thực tế.

So sánh:

| Khía cạnh | MessageListenerAdapter | @JmsListener |
| --- | --- | --- |
| Cách khai báo | Bean adapter + container hoặc listener endpoint | Annotation trên method |
| POJO không phụ thuộc Spring JMS? | Có thể, nếu delegate không dùng JMS types và không chứa JMS annotations | Method chứa Spring JMS annotation |
| Mặc định method | `handleMessage`, đổi bằng `setDefaultListenerMethod` | Method có annotation |
| Conversion | `MessageConverter` của adapter | Conversion/argument resolution của listener infrastructure |
| Reply | Giá trị return qua SessionAware entry point và reply destination | Có cơ chế reply riêng của annotation/handler |
| Legacy POJO | Rất phù hợp khi không muốn sửa class | Cần sửa class hoặc viết wrapper annotated method |
| Boilerplate cấu hình | Nhiều hơn | Ít hơn trong ứng dụng Spring Boot |
| Kiểm soát container | Khai báo bean và cài đặt thủ công | Có thể cấu hình listener factory và annotation |
| Phù hợp dự án mới | Khi cần dùng POJO có sẵn/contract riêng | Thường là phương án thuận tiện |

**Khi nên dùng adapter:** tái sử dụng class legacy không có annotation, giữ service tách biệt transport, wiring listener theo configuration, hoặc cần chọn delegate/method linh hoạt.

**Khi nên dùng @JmsListener:** xây ứng dụng Spring mới, dễ đọc endpoint, cần argument binding/validation/annotation tiện lợi và muốn Boot quản lý phần lớn wiring.

Không có lựa chọn “luôn nhanh hơn” từ việc adapter dùng reflection: hiệu năng tổng thường bị chi phối bởi broker, network, deserialize, DB và nghiệp vụ. Benchmark nếu nó là yêu cầu thực tế.

## 11. MappingJackson2MessageConverter và nhận DTO thay String

Trong ví dụ chạy, adapter mặc định nhận String từ TextMessage. Nếu message body là JSON và delegate muốn nhận record:

~~~java
public record OrderCreated(
        String eventId,
        String orderId,
        long amountVnd) {
}
~~~

Bạn phải cấu hình JSON converter phù hợp với message format và type metadata, thay vì giả định chỉ cần đổi method:

~~~java
public void onOrder(OrderCreated event) {
    // Xử lý event được converter deserialize.
}
~~~

Đoạn cấu hình tham khảo (không tự thêm vào project demo String ở mục 8):

~~~java
import java.util.Map;
import org.springframework.jms.support.converter.MappingJackson2MessageConverter;
import org.springframework.jms.support.converter.MessageType;

MappingJackson2MessageConverter converter =
        new MappingJackson2MessageConverter();

converter.setTargetType(MessageType.TEXT);
converter.setTypeIdPropertyName("_type");
converter.setTypeIdMappings(
        Map.of("order-created.v1", OrderCreated.class));

adapter.setMessageConverter(converter);
~~~

Đây là **snippet trong một method cấu hình đã có biến adapter**; import đầy đủ `OrderCreated` nếu ở package khác. Producer cũng phải sử dụng converter tương thích và gắn type ID property `_type` theo hợp đồng. Một default JSON converter không tự khiến mọi kiểu DTO có thể deserialize an toàn mà không có type ID và schema mapping phù hợp.

Javadoc Spring nêu converter Jackson mặc định tạo BytesMessage nếu chưa chuyển sang `MessageType.TEXT`. Producer và consumer phải thống nhất TextMessage/BytesMessage, encoding, schema version và loại object được phép.

**Lựa chọn kiến trúc:** có thể để adapter chỉ nhận String JSON rồi gọi service parser riêng, hoặc cấu hình converter để method nhận DTO. Cách đầu explicit, dễ quan sát; cách sau gọn hơn nhưng phụ thuộc cấu hình converter. Chọn dựa trên contract và test, không dựa vào số dòng code.

## 12. Lỗi thường gặp khi cấu hình MessageListenerAdapter

| Biểu hiện | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Broker có message nhưng POJO không chạy | Chưa đăng ký adapter với listener container hoặc sai destination | Kiểm tra `setMessageListener`, `setDestinationName`, container startup |
| Có `NoSuchMethodException` / lỗi reflection | Delegate không có `handleMessage` mặc định | Đặt `setDefaultListenerMethod("onOrder")` hoặc đổi tên method |
| Method có tên đúng nhưng không gọi được | Parameter type không khớp converted body | Xem loại JMS message và converter |
| Handler nhận `byte[]` thay vì String | Producer gửi BytesMessage và default converter trả bytes | Thống nhất body contract hoặc dùng converter JSON |
| Handler muốn raw TextMessage nhưng chỉ nhận String | Chưa tắt conversion | `adapter.setMessageConverter(null)`, đổi signature |
| Handler nhận DTO thất bại | Thiếu JSON converter/type ID/schema mapping | Cấu hình converter hai chiều và kiểm thử |
| Handler trả String nhưng reply không tới | Không có `JMSReplyTo`/default response destination hoặc dùng entry point không session-aware | Đối chiếu request/reply contract và container |
| Message bị xử lý lại | Exception, rollback, redelivery | Thiết kế idempotency, retry/DLQ và transaction |
| Method bị invoke nhưng data sai | Conversion/schema hoặc property/body không nhất quán | Log metadata an toàn, test byte/JSON encoding |
| Nhiều instance tranh nhau nhận | Queue competing consumers | Điều chỉnh concurrency/partition/Queue thiết kế |
| Container restart không hồi phục | Connection factory caching quá mức hoặc provider recovery config sai | Kiểm tra factory lifecycle và DMLC recovery policy |
| Runtime `javax.jms`/`jakarta.jms` mismatch | Client/provider cũ không tương thích Spring Boot 3 | Dùng thư viện Jakarta JMS tương thích |

### 12.1. Sai tên method cần được phát hiện trước khi production

Adapter tìm method bằng reflection. Java compiler không thể bảo đảm string `"onOrder"` thực sự tồn tại sau refactor nếu chỉ dùng cấu hình string. Với code mới, dùng unit test gọi adapter và kiểm tra branch conversion. Không chỉ kiểm tra Spring context có bean adapter.

### 12.2. Lỗi xảy ra lúc xử lý, không phải lúc đăng ký bean

Một adapter bean có thể khởi tạo bình thường nhưng đến lúc message đầu tiên tới mới phát hiện no matching method hoặc lỗi conversion. Vì vậy health check chỉ kiểm tra connection không đủ; integration test phải **thực sự gửi và nhận** ít nhất một message đúng type.

### 12.3. Không swallow exception từ delegate

Nếu POJO thất bại nhưng adapter/container không quan sát được exception, message có thể được ACK như đã xử lý. Đừng catch rồi chỉ log:

~~~java
// Mẫu không nên dùng nếu nghiệp vụ cần retry:
try {
    processBusiness(payload);
} catch (Exception failure) {
    logger.error("Failed", failure);
    // Không throw lại => container có thể coi là thành công!
}
~~~

Giữ exception hoặc chuyển sang outcome thất bại theo transaction policy đã chọn, có DLQ/idempotency phù hợp. Nếu cần retry bên trong handler, phải giới hạn attempts/backoff và tránh khiến một transaction giữ tài nguyên lâu.

## 13. Transaction, ACK, redelivery và reply

### 13.1. Container quyết định mốc ACK

MessageListenerAdapter không tự quyết định rằng message sẽ ACK trước hay sau khi POJO chạy. Chính `DefaultMessageListenerContainer` và `Session` định nghĩa behavior.

- Với `AUTO_ACKNOWLEDGE` mặc định trên `DefaultMessageListenerContainer`, Spring docs cảnh báo ACK có thể được thực hiện **trước khi listener thực thi**, nên lỗi handler không bảo đảm redelivery.
- Với `sessionTransacted=true`, container dùng local JMS transaction; method thành công có thể dẫn tới commit, exception có thể gây rollback và redelivery theo provider policy.
- Nếu dùng external transaction manager/XA, cần cấu hình đúng transaction boundaries, resource enlistment và recovery.

**Đừng coi việc gọi `CountDownLatch.countDown()` trong ví dụ là ACK.** Nó chỉ chứng minh Java handler đến được một vị trí trong code, không chứng minh commit của transaction với broker.

### 13.2. Response cùng session khi được hỗ trợ

Adapter trả một non-null value và có `JMSReplyTo`/default response destination có thể gửi reply bằng session được container cung cấp. Với session transacted, nhận request và gửi reply có thể cùng thuộc transaction JMS cục bộ. Nhưng database nghiệp vụ là một resource khác; không giả định JMS+DB atomic chỉ bằng `@Transactional` hoặc `setSessionTransacted(true)`.

### 13.3. Redelivery và idempotency

Khi listener ném exception và session rollback, broker có thể gửi lại message. Một sự kiện nghiệp vụ có thể xuất hiện nhiều lần bởi retry producer, broker redelivery hoặc sự cố sau khi DB commit nhưng trước JMS ACK. Consumer cần business event ID, lưu trạng thái xử lý bền vững và cơ chế loại bỏ tác dụng phụ lặp.

Một contract tốt cho event nên có:

~~~text
eventId = stable identifier qua các lần retry
eventType = order.created.v1
schemaVersion = 1
payload = dữ liệu nghiệp vụ
~~~

Đừng dùng `JMSMessageID` làm khóa duy nhất cho mọi lần republish cùng sự kiện: một JMS message mới có thể có message ID khác. Nếu dùng DLQ, cần policy cho malformed payload và exception không phục hồi, tránh retry vô hạn gây tắc Queue.

## 14. Caching, concurrency và vòng đời

### 14.1. Container dùng connection/session thế nào?

`DefaultMessageListenerContainer` tự quản lý connection/session/consumer và có chiến lược cache phù hợp. Spring Boot có thể bọc native factory bằng `CachingConnectionFactory` cho `JmsTemplate`; tuy nhiên DMLC cần cân nhắc sử dụng factory native để tránh resource ownership và recovery không rõ. Trong sample đã tắt Boot JMS cache để giữ đường đi đơn giản.

Trong production:

- Một factory dùng cho publisher có thể được cache/pool hợp lý.
- Listener container nên có quyền quản lý connection lifecycle và recover.
- Không tăng `concurrentConsumers` mà không đo broker resource, business thread safety và ordering.
- Với Queue, nhiều consumer chia message; với Topic, subscription semantics khác.
- Dùng resource metrics thay vì suy luận số broker connection từ số bean listener.

### 14.2. Thread safety của delegate

POJO thường là Spring singleton; nhiều container threads có thể gọi cùng delegate **đồng thời** khi tăng concurrency. Không lưu trạng thái message hiện tại trong mutable field nếu không được đồng bộ phù hợp.

Ví dụ không an toàn:

~~~java
private String currentOrder;

public void onOrder(String body) {
    currentOrder = body;
    // Thread khác có thể ghi currentOrder trước khi dùng.
}
~~~

Thay bằng biến local hoặc thiết kế stateless:

~~~java
public void onOrder(String body) {
    String currentOrder = body;
    processBusiness(currentOrder);
}
~~~

Đây là snippet minh họa trong một class đã có `processBusiness`. Phần ứng dụng thử nghiệm có `lastBody` và latch chỉ để quan sát **một message**; không copy state này như cách xử lý đa luồng production.

## 15. Đưa POJO legacy vào hệ thống mà không chỉnh code cũ

Giả sử một thư viện nội bộ có:

~~~java
public final class LegacyInvoiceService {
    public void acceptInvoice(String invoiceJson) {
        // Parse JSON, validate, ghi nghiệp vụ.
    }
}
~~~

Không thêm `@JmsListener` vào lớp này. Tại module integration với broker:

~~~java
@Bean
MessageListenerAdapter invoiceAdapter(
        LegacyInvoiceService service) {
    MessageListenerAdapter adapter =
            new MessageListenerAdapter(service);
    adapter.setDefaultListenerMethod("acceptInvoice");
    return adapter;
}
~~~

Sau đó khai báo listener container với `setMessageListener(invoiceAdapter)` như project mẫu. Nếu POJO cũ không phải Spring bean, có thể tạo một `@Bean LegacyInvoiceService` hoặc nhận instance từ factory hiện có.

Ưu điểm:

- Không thêm phụ thuộc JMS/Spring lên thư viện nghiệp vụ.
- Không sửa ký tên method legacy.
- Test POJO độc lập, test adapter dispatch riêng.
- Hạ tầng broker có thể thay đổi mà method nghiệp vụ vẫn nhận String JSON.

Giới hạn: adapter gọi thông qua reflection theo tên method là string, nên việc đổi chữ ký method phải có test kiểm chứng. Nếu POJO cần nhiều metadata, hãy dùng envelope/application DTO hoặc adapter tùy biến thay vì ép framework transport vào domain.

## 16. Bộ kiểm thử đề xuất

| Mức test | Điều cần kiểm chứng | Cần broker? |
| --- | --- | --- |
| POJO unit test | Validation, business transformations, lỗi nghiệp vụ | Không |
| Adapter unit test | Converter + dispatch đúng method/type | Không |
| Spring context test | Bean adapter/container/wiring không bị thiếu | Có thể không, nếu ngăn auto-start container |
| Integration test Artemis | Queue nhận, adapter gọi POJO, transaction/ACK/retry đúng | Có |
| End-to-end test | Database commit, idempotency, DLQ, reply tới requestor | Có, cùng DB/dịch vụ liên quan |

Các tình huống nên test:

1. TextMessage bình thường gọi `onOrder(String)`.
2. BytesMessage vào handler String tạo lỗi contract rõ ràng.
3. Đổi `setDefaultListenerMethod` sang tên không tồn tại gây lỗi có thể phát hiện.
4. Handler ném exception khi payload invalid và kiểm tra rollback/redelivery đúng policy.
5. Có `JMSReplyTo` với delegate trả String: response được tạo ở đường session-aware.
6. Không có `JMSReplyTo`, không đặt default reply: behavior được quan sát đúng theo adapter/container.
7. Hai consumer cạnh tranh một Queue: message đi tới một consumer theo JMS Queue semantics.
8. Nhiều message đồng thời: delegate không có mutable shared state gây race.
9. Broker restart giữa receive/ACK: ghi lại retry/redelivery và idempotency.
10. Không gửi credentials hoặc payload nhạy cảm vào log từ adapter/handler.

## 17. Câu hỏi tự kiểm tra

**1.** Vì sao một `OrderHandler.handleMessage(String)` không cần implements `MessageListener`?

Vì `MessageListenerAdapter` đứng giữa container và POJO, lấy JMS message, chuyển body thành Java String rồi gọi method.

**2.** Method mặc định Spring tìm trên delegate tên gì?

`handleMessage`. Nếu method nghiệp vụ tên `processOrder` thì dùng `setDefaultListenerMethod("processOrder")`.

**3.** Bean `MessageListenerAdapter` riêng có tự kết nối Queue không?

Không. Cần listener container được đăng ký với ConnectionFactory, destination và adapter.

**4.** TextMessage thường được converter mặc định chuyển thành kiểu gì?

`String`. BytesMessage thường được chuyển thành `byte[]`, MapMessage thành `Map`.

**5.** Muốn delegate nhận `TextMessage` raw thay vì `String` thì làm sao?

Đặt `adapter.setMessageConverter(null)` và khai báo method nhận `TextMessage` (hoặc `Message`) phù hợp.

**6.** Một handler có `String handleMessage(String)` trả kết quả khác null có luôn gửi JMS reply không?

Không. Cần đường `SessionAwareMessageListener` qua container và destination reply hợp lệ (`JMSReplyTo` hoặc default response destination).

**7.** Có nên dùng `@JmsListener` trên cùng Queue song song với adapter demo không?

Nếu muốn kết quả demo xác định, không: hai consumer có thể cạnh tranh và message bị listener khác nhận.

**8.** Nếu POJO method ném exception, message có nhất định được giao lại không?

Không trong mọi acknowledge mode; cần cấu hình transaction/ACK của container. `sessionTransacted=true` là lựa chọn giúp rollback/redelivery theo chính sách broker.

**9.** Unit test gọi `adapter.onMessage(mockTextMessage, null)` chứng minh điều gì?

Chứng minh đường converter/dispatch vào POJO trong JVM; không chứng minh broker đã giao hoặc ACK thành công.

**10.** Khi nào MessageListenerAdapter hữu ích hơn `@JmsListener`?

Khi đã có POJO legacy, muốn không thêm annotation/JMS dependency vào lớp đó, hoặc muốn wiring delegate theo configuration.

## 18. Tài liệu chính thức

- Spring Framework 6.1 — `MessageListenerAdapter` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/jms/listener/adapter/MessageListenerAdapter.html
- Spring Framework — MessageListenerAdapter / receiving JMS: https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html
- Spring Framework — Using Spring JMS, listener containers: https://docs.spring.io/spring-framework/reference/integration/jms/using.html
- Spring Framework 6.1 — `DefaultMessageListenerContainer` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html
- Spring Framework 6.1 — `SimpleMessageConverter` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/jms/support/converter/SimpleMessageConverter.html
- Spring Framework — `@JmsListener` reference: https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html
- Spring Boot — JMS and ActiveMQ Artemis: https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html
- Jakarta Messaging 3.1 Specification: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html

**Ghi nhớ:** `MessageListenerAdapter` biến **method của POJO thành một JMS listener endpoint** thông qua converter và reflection. Container mới là thành phần quản lý connection, lifecycle và transaction. Dùng adapter khi cần tận dụng Java object có sẵn, cấu hình đúng method/converter và kiểm thử cả dispatch lẫn broker thực tế.
