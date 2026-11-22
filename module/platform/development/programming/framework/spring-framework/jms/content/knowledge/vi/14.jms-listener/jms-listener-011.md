# JmsListenerEndpointRegistry để tìm và quản lý container trong Spring JMS

**Chủ đề cha:** `@JmsListener` — Spring Framework / JMS.

**Mục tiêu:** Biết dùng `JmsListenerEndpointRegistry` để **liệt kê những JMS listener endpoints đã đăng ký, tìm đúng `MessageListenerContainer` theo ID, xem trạng thái, tạm dừng/khởi động lại một listener hoặc toàn bộ nhóm, và đăng ký endpoint bằng code khi có nhu cầu**. Nắm được ranh giới giữa *Spring bean*, *listener endpoint*, *listener container*, *destination* và *JMS broker*, để thao tác vận hành không gây mất xử lý hoặc dừng nhầm consumer.

**Môi trường và cách đọc code:** Java 17+, Spring Framework 6.x / Spring Boot 3.x với Jakarta Messaging (`jakarta.jms`). Ví dụ tích hợp dùng Spring Boot 3.5.0 và Apache ActiveMQ Artemis **broker chạy ngoài ứng dụng**; không khẳng định đó là bản Spring Boot mới nhất. Những API minh họa dưới đây có trong Spring Framework 6.2.x, cần kiểm tra lại khi nâng major version.

> **Kết luận quan trọng nhất:** các `MessageListenerContainer` mà hạ tầng `@JmsListener` tạo ra **thường không được đăng ký thành từng bean trong `ApplicationContext`**. Muốn tìm hoặc điều khiển chúng, inject bean **`JmsListenerEndpointRegistry`** và gọi `getListenerContainer(id)`. ID để quản lý không phải tên queue, cũng không phải tên `JmsListenerContainerFactory`.

## 1. Tại sao ứng dụng cần một registry?

Thông thường, code nghiệp vụ chỉ có:

~~~java
@Component
class InvoiceConsumer {

    @JmsListener(
            id = "invoiceCommands",
            destination = "invoice.commands")
    public void handle(String command) {
        System.out.println("Received: " + command);
    }
}
~~~

**Đây là snippet** nằm trong project Spring JMS có import `org.springframework.stereotype.Component` và `org.springframework.jms.annotation.JmsListener`. Một câu hỏi xuất hiện sau khi triển khai: *Listener nào đang chạy? Có thể tạm dừng riêng listener invoice không? Làm sao biết Spring đã phát hiện annotation?*

Spring tạo infrastructure theo chuỗi:

~~~text
ApplicationContext
   ├─ InvoiceConsumer bean
   │     └─ @JmsListener(id="invoiceCommands", destination="invoice.commands")
   │
   ├─ JmsListenerContainerFactory bean
   │     └─ tạo container với các thiết lập transaction/connection/concurrency
   │
   └─ JmsListenerEndpointRegistry bean
         └─ registry["invoiceCommands"]
               └─ MessageListenerContainer instance
                     ├─ JMS Connection / Session / MessageConsumer
                     ├─ consumer threads / listener lifecycle
                     └─ callback → InvoiceConsumer.handle(...)
                                        │
                                        ▼
                                  JMS broker/queue
~~~

Container là đơn vị vận hành listener: nó quản lý nhận message, threading, resources, recovery, transaction/ACK. Registry giữ **danh mục containers tạo cho các endpoints** và điều phối lifecycle. Registry **không lưu nội dung messages** và **không thay thế broker management API**.

Đôi khi ta vẫn có thể khai báo thủ công một `DefaultMessageListenerContainer` như `@Bean`. Bean thủ công như thế **không tự xuất hiện trong registry** chỉ vì nó cùng loại. Đây là khác biệt đáng nhớ khi viết code liệt kê listeners.

## 2. Phân biệt năm tên dễ nhầm

| Thuật ngữ | Ví dụ | Chức năng |
| --- | --- | --- |
| **Listener bean** | `InvoiceConsumer` | Object Spring chứa phương thức nghiệp vụ |
| **Endpoint ID** | `invoiceCommands` | Khóa định danh của một endpoint/container trong registry |
| **Destination** | `invoice.commands` | Tên queue/topic để container tạo JMS consumer |
| **Container factory** | `jmsListenerContainerFactory` | Bean cấu hình dùng để **tạo** container |
| **Listener container** | `DefaultMessageListenerContainer` | Instance sống thực sự, có start/stop và JMS resources |

Ví dụ đầy đủ thuộc tính annotation:

~~~java
@JmsListener(
        id = "invoiceCommands",
        destination = "invoice.commands",
        containerFactory = "criticalJmsFactory",
        selector = "eventType = 'CreateInvoice'")
public void handleInvoice(String payload) {
    // Xử lý payload sau khi listener đã được container dispatch.
}
~~~

Trong đoạn trên:
- `id` là key để dùng `registry.getListenerContainer("invoiceCommands")`.
- `destination` là queue/topic name, **không** phải key cho `getListenerContainer(...)`.
- `containerFactory` trỏ đến bean factory tên `criticalJmsFactory`, không phải một container instance.
- `selector` là biểu thức JMS filter dựa trên header/properties, không tự parse JSON body.

Nếu chỉ ghi `@JmsListener(destination = "invoice.commands")` mà bỏ `id`, framework có thể **tạo endpoint ID tự động**. Bạn vẫn có thể liệt kê IDs, nhưng đừng phụ thuộc ID generated đó cho monitoring và thao tác vận hành ổn định qua các lần rebuild. **Nên đặt một ID duy nhất, có chủ đích** khi cần điều khiển chính xác endpoint.

## 3. Vị trí của registry trong Spring

`JmsListenerEndpointRegistry` nằm trong package:

~~~java
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.listener.MessageListenerContainer;
~~~

Để Spring đăng ký registry và các endpoints dựa trên annotation:

- **Spring Framework thuần:** bật `@EnableJms` trong một `@Configuration`, có `ConnectionFactory` và bean `JmsListenerContainerFactory` phù hợp.
- **Spring Boot 3.x:** với `spring-boot-starter-artemis` hoặc JMS provider starter/client tương thích, Boot có thể tự cấu hình hạ tầng listener khi điều kiện được đáp ứng; thường không cần tự viết `@EnableJms`.
- Listener class phải được Spring quản lý: `@Component`/`@Bean`/component scan phù hợp. Một object được khởi tạo bằng `new` bên ngoài container sẽ không được phát hiện như annotated endpoint.

**Phân biệt inject:** registry là một **Spring bean** nên có thể constructor-inject; `MessageListenerContainer` do registry tạo **không nhất thiết là bean**, nên `@Autowired MessageListenerContainer` thường không tìm được endpoint cụ thể. Đây là thiết kế được Spring Framework mô tả; truy vấn qua registry theo ID là đường được hỗ trợ.

### 3.1. Cấu hình Spring thuần tối thiểu

~~~java
package example.jms;

import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
@EnableJms
public class JmsListenerConfiguration {

    @Bean
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(false);
        factory.setSessionTransacted(true);
        factory.setConcurrency("1-3");
        return factory;
    }
}
~~~

Đây là một class biên dịch được khi có Spring 6.x/Jakarta JMS dependencies và `ConnectionFactory` bean. Nó không tự chạy vì còn cần ứng dụng khởi động `ApplicationContext` và broker thực. Factory mặc định mang tên `jmsListenerContainerFactory`; với listener không chỉ rõ `containerFactory`, Spring tìm default factory tương ứng. Khi endpoints được phát hiện, registry quản lý containers sinh từ factory.

## 4. Bộ API thực sự của JmsListenerEndpointRegistry

Các phương thức quan trọng trong Spring Framework 6.2.x:

| API | Kết quả / ý nghĩa |
| --- | --- |
| `getListenerContainerIds()` | `Set<String>` các **endpoint IDs** được registry quản lý |
| `getListenerContainer(String id)` | `MessageListenerContainer` cho ID, hoặc **`null`** nếu không tìm thấy |
| `getListenerContainers()` | `Collection<MessageListenerContainer>` các containers do registry quản lý |
| `isRunning()` | Trạng thái lifecycle của registry, **true nếu có ít nhất một container đang chạy** |
| `start()` | Gửi lệnh start tới các containers theo lifecycle |
| `stop()` | Dừng các containers do registry quản lý |
| `stop(Runnable callback)` | Dừng theo lifecycle callback được Spring hỗ trợ |
| `getPhase()` | Pha lifecycle dùng để phối hợp startup/shutdown |
| `registerListenerContainer(endpoint, factory)` | Tạo và đăng ký một container cho endpoint được cung cấp |
| `registerListenerContainer(endpoint, factory, startImmediately)` | Như trên, đồng thời quyết định có yêu cầu start ngay hay không |

**Không có `getAllListenerContainers()` và `unregisterListenerContainer(String)` trong bộ API của `JmsListenerEndpointRegistry` ở Spring Framework 6.2.x.** Hai tên dễ bị copy từ **Spring AMQP/Rabbit** hoặc API thuộc phiên bản khác. Kiểm tra **JMS** package và Javadoc thay vì suy luận các registries đều giống nhau.

Các kết quả collection là cấu trúc để quan sát và quản lý, **không phải mutable list để app tự xóa container**. Không cố sửa `getListenerContainerIds()`/`getListenerContainers()` để “gỡ listener” khỏi registry; đó không phải thao tác đăng ký/ngắt đăng ký được bảo đảm.

## 5. Liệt kê endpoint IDs trong ứng dụng đang chạy

Mẫu service Spring có thể tái sử dụng:

~~~java
package example.jms;

import java.util.Set;
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.stereotype.Service;

@Service
public class JmsEndpointCatalog {

    private final JmsListenerEndpointRegistry registry;

    public JmsEndpointCatalog(JmsListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public Set<String> endpointIds() {
        return Set.copyOf(registry.getListenerContainerIds());
    }

    public int endpointCount() {
        return registry.getListenerContainerIds().size();
    }
}
~~~

**Lợi ích:** lấy danh sách endpoint ở runtime thay vì hard-code tất cả vào dashboard. `Set.copyOf` tạo snapshot để code gọi tiếp không phụ thuộc collection live được registry trả về. **Không giả định thứ tự Set là thứ tự đăng ký hay ưu tiên nghiệp vụ**; nếu cần hiển thị ổn định, sort bằng `Comparator.naturalOrder()` hoặc `TreeSet`.

Nếu registry chưa có endpoint, danh sách IDs có thể rỗng. Đây có thể là trạng thái hợp lệ khi app cố tình chưa bật listener hoặc chưa đăng ký endpoints, chứ không tự chứng minh mất kết nối broker.

### 5.1. Logging khi ứng dụng startup

~~~java
@Bean
ApplicationRunner logJmsEndpoints(JmsListenerEndpointRegistry registry) {
    return args -> registry.getListenerContainerIds().stream()
            .sorted()
            .forEach(id -> {
                MessageListenerContainer c =
                        registry.getListenerContainer(id);
                System.out.printf(
                        "JMS_ENDPOINT id=%s registered=%s running=%s%n",
                        id, c != null, c != null && c.isRunning());
            });
}
~~~

Snippet nằm trong class `@Configuration`/`@SpringBootApplication` có imports `@Bean`, `ApplicationRunner`, `JmsListenerEndpointRegistry`, `MessageListenerContainer`. Nó **không bảo đảm** broker đã reachable ngay tại thời điểm log. Container có thể đang khởi động hoặc recovery trong khi `isRunning()` trả true.

## 6. Tìm một container theo ID và kiểm tra null

Đây là thao tác chính của bài:

~~~java
MessageListenerContainer container =
        registry.getListenerContainer("invoiceCommands");

if (container == null) {
    throw new IllegalArgumentException(
            "Unknown JMS listener id: invoiceCommands");
}

System.out.println("listener running = " + container.isRunning());
~~~

`getListenerContainer(...)` **trả `null`** nếu không có key; không phải ngoại lệ “bean not found”. Đừng gọi `container.stop()` trước khi kiểm tra null. Nếu null, chẩn đoán theo thứ tự:

1. `@JmsListener(id="invoiceCommands")` có nằm trong class là Spring bean không?
2. Package đó có được component scan không?
3. Listener annotation infrastructure đã bật chưa?
4. ID có viết đúng chữ hoa/chữ thường, khoảng trắng và giá trị property placeholder không?
5. ID có bị trùng dẫn tới lỗi đăng ký endpoint lúc startup không?
6. Có đang tham chiếu nhầm registry/ApplicationContext trong môi trường test nhiều contexts không?

### 6.1. Không lấy container bằng tên destination

~~~java
// ĐÚNG: id đúng như @JmsListener(id = "invoiceCommands").
registry.getListenerContainer("invoiceCommands");

// THƯỜNG SAI: đây là destination, không phải ID đã đăng ký.
registry.getListenerContainer("invoice.commands");
~~~

Trường hợp trùng ngẫu nhiên chỉ xảy ra nếu bạn **cố tình đặt ID bằng tên destination**; đó không phải một quy tắc tự động của Spring.

## 7. start() và stop() một listener cụ thể

`MessageListenerContainer` là abstraction chung có lifecycle methods:

~~~java
MessageListenerContainer listener =
        registry.getListenerContainer("invoiceCommands");

if (listener == null) {
    throw new IllegalArgumentException("Listener does not exist");
}

listener.stop();            // Dừng riêng endpoint này
boolean afterStop = listener.isRunning();

listener.start();           // Khởi động lại chính endpoint ấy
boolean afterStart = listener.isRunning();
~~~

**Ranh giới tác động:** gọi `listener.stop()` không xóa queue broker, không làm mất bean chứa `@JmsListener` và không xóa registration trong registry. Trong tình huống queue có persistence/retention phù hợp, message có thể tiếp tục tồn tại ở broker trong lúc endpoint dừng, để nhận sau khi start lại. Tuy nhiên **topic non-durable subscriptions có semantics khác**, message có thể bị bỏ lỡ trong thời gian subscription không còn hoạt động.

**Với in-flight message:** container có thể đang xử lý message khi stop được gọi. Thời điểm chờ handler, rollback hoặc commit phụ thuộc implementation, transaction mode, broker và grace period. Không suy luận `stop()` đồng nghĩa toàn bộ message đã hoàn thành business transaction, cũng không gọi stop để hủy tức thì một payment đang thực thi.

### 7.1. start() không có nghĩa broker đang sẵn sàng

`isRunning()==true` thường phản ánh container đã được khởi động ở mặt lifecycle. Một `DefaultMessageListenerContainer` vẫn có thể đang cố reconnect tới broker không reachable. Muốn kết luận “consumer ready”, cần theo dõi connection/authentication, broker-side consumer count, destination permissions và message handling metrics.

### 7.2. Nếu listener đang dừng thì stop lần nữa?

Lifecycle methods được thiết kế để có thể thao tác hợp lý khi đã ở trạng thái đó; tuy nhiên không coi chúng là **API giao dịch nguyên tử** giữa nhiều callers. Nếu nhiều admin requests stop/start đồng thời, có thể xuất hiện race hoặc trạng thái khó hiểu. Dùng một service điều phối, phân quyền và serialization cho các thao tác vận hành.

## 8. Dừng hoặc khởi động toàn bộ registry

~~~java
registry.stop();      // Dừng tất cả listener containers mà registry quản lý.
registry.start();     // Khởi động lại nhóm theo lifecycle.
~~~

Đây là thao tác diện rộng, **khác** `registry.getListenerContainer("invoiceCommands").stop()`:

| Ý định | Cách gọi |
| --- | --- |
| Tạm dừng riêng invoice consumer | Lấy đúng ID rồi gọi `stop()` |
| Khởi động lại invoice consumer | Lấy đúng ID rồi gọi `start()` |
| Dừng toàn bộ endpoints do registry quản lý | `registry.stop()` |
| Khởi động toàn bộ endpoints do registry quản lý | `registry.start()` |

`registry.stop(Runnable callback)` có thể tích hợp với chu trình `SmartLifecycle` của Spring, nơi callback được gọi sau khi các listener containers báo hoàn tất stop. Đây không phải cách đồng bộ “tất cả hóa đơn đã commit”; nó là callback về **lifecycle stop**, khác với business completion.

**Không dùng `registry.stop()` làm lệnh “pause toàn bộ message broker”.** Nó chỉ tác động listener containers thuộc registry **trong ApplicationContext/tiến trình hiện tại**. Các instance service khác, applications khác hoặc consumer tạo thủ công vẫn có thể lấy message bình thường.

### 8.1. Chú ý đặc biệt về registry.isRunning()

Trong Spring Framework 6.2.x, triển khai `JmsListenerEndpointRegistry.isRunning()` trả **true khi tìm thấy ít nhất một container đang running**. Do đó:

~~~java
boolean anyRunning = registry.isRunning();
~~~

**Không được diễn giải** `anyRunning=true` là “tất cả endpoints đều healthy”. Một application có 10 listeners, chỉ 1 chạy, registry vẫn có thể báo true. Ngược lại, muốn biết tất cả endpoints có started hay không, phải kiểm tra **từng container**.

~~~java
boolean allRegisteredRunning =
        !registry.getListenerContainerIds().isEmpty()
        && registry.getListenerContainerIds().stream()
            .map(registry::getListenerContainer)
            .allMatch(c -> c != null && c.isRunning());
~~~

Code này tính **lifecycle running của các endpoints đã đăng ký**, **không phải broker readiness**. Với không có endpoints, ta cố tình trả false để không coi “allMatch trên tập rỗng” là một trạng thái khỏe giả.

## 9. Spring Boot 3.x: demo hoàn chỉnh để tìm, dừng và chạy lại

Mục tiêu của ví dụ là **quan sát sự khác nhau giữa container lifecycle và broker queue**. Một `@JmsListener` có ID xác định, một `ApplicationRunner` tìm container, dừng nó, publish một message vào queue test rồi start lại. Đây là demo chỉ để học, **không áp dụng stop/start vào production queue** chỉ để debug log.

### 9.1. Dependency và phiên bản

Tệp `build.gradle` dùng Java 17 và Spring Boot 3.5.0:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
}
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'jms-endpoint-registry'
~~~

### 9.2. application.yaml

Tệp `src/main/resources/application.yaml`:

~~~yaml
spring:
  artemis:
    mode: native
    broker-url: tcp://localhost:61616
    user: demo
  jms:
    pub-sub-domain: false
    listener:
      auto-startup: true
      min-concurrency: 1
      max-concurrency: 1
~~~

**Điều kiện:** Artemis broker chạy tại URL, có queue `demo.registry.jobs` (hoặc cho phép auto-create), account `demo` có quyền consume/send. Cung cấp password qua biến môi trường `SPRING_ARTEMIS_PASSWORD` hoặc secret store; không commit credentials vào Git. Những thuộc tính trên tác động tới auto-configured listener factory khi điều kiện Boot phù hợp.

### 9.3. Một Java file đầy đủ

`src/main/java/example/jmsregistry/RegistryApplication.java`:

~~~java
package example.jmsregistry;

import java.util.Set;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.listener.MessageListenerContainer;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class RegistryApplication {

    public static void main(String[] args) {
        SpringApplication.run(RegistryApplication.class, args);
    }

    @Bean
    ApplicationRunner demonstrateRegistry(
            JmsListenerEndpointRegistry registry,
            JmsTemplate jmsTemplate) {

        return args -> {
            Set<String> ids = Set.copyOf(
                    registry.getListenerContainerIds());
            System.out.println("REGISTERED_IDS=" + ids);

            MessageListenerContainer listener =
                    registry.getListenerContainer("jobsDemo");

            if (listener == null) {
                throw new IllegalStateException(
                        "Listener jobsDemo was not registered");
            }

            System.out.println(
                    "INITIAL_RUNNING=" + listener.isRunning());

            listener.stop();
            System.out.println(
                    "RUNNING_AFTER_STOP=" + listener.isRunning());

            // Queue test: không có một consumer khác tranh message.
            jmsTemplate.convertAndSend(
                    "demo.registry.jobs", "job-created-42");
            System.out.println("SEND_WHILE_STOPPED_RETURNED");

            listener.start();
            System.out.println(
                    "RUNNING_AFTER_START=" + listener.isRunning());
        };
    }
}

@Component
class DemoJobListener {

    @JmsListener(
            id = "jobsDemo",
            destination = "demo.registry.jobs")
    public void handle(String payload) {
        System.out.println("HANDLER_THREAD="
                + Thread.currentThread().getName()
                + " PAYLOAD=" + payload);
    }
}
~~~

**Vì sao là ví dụ đúng ý:** `jobsDemo` là annotation ID để registry tìm; `demo.registry.jobs` là destination để producer gửi; `MessageListenerContainer` là object có `stop/start/isRunning`. Thread thực thi `ApplicationRunner` không tự biến thành consumer thread. Broker queue (nếu còn message) sẽ được listener nhận sau khi chạy lại.

**Không có việc inject `DemoJobListener` rồi gọi `handle(...)` để thực hiện stop/start.** Gọi handler trực tiếp chỉ gọi Java method, không tạo JMS receive/ACK; phải điều khiển container.

### 9.4. Chạy và diễn giải output

Sau khi thiết lập broker và Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Các dòng chính **có thể** có:

~~~text
REGISTERED_IDS=[jobsDemo]
INITIAL_RUNNING=true
RUNNING_AFTER_STOP=false
SEND_WHILE_STOPPED_RETURNED
RUNNING_AFTER_START=true
HANDLER_THREAD=... PAYLOAD=job-created-42
~~~

**Không coi đây là stdout cố định:** thứ tự dòng `HANDLER_THREAD` có thể xen vào sau khi `listener.start()` được gọi; khi start đã sẵn sàng, listener có thể chạy **trước** log `RUNNING_AFTER_START`. Nếu broker lỗi/auth sai, send có thể ném exception, listener có thể đang recovery; nếu có consumer khác/queue chứa message cũ, dữ liệu nhận cũng khác. `Set<String>` không bảo đảm thứ tự in khi có nhiều IDs. Một queue được broker lưu bền vững sẽ giữ message khi listener stop trong phạm vi TTL/retention, nhưng mode/topic policy có thể khác.

**Demo không chứng minh nghiệp vụ thành công:** handler chỉ in chuỗi, không dùng DB, không có idempotency hoặc outbox. Mỗi lần khởi động sẽ gửi một message, không nên copy `ApplicationRunner` này sang ứng dụng chạy production.

## 10. Các endpoints được đăng ký từ @JmsListener có phải Spring beans không?

Spring Framework nêu rõ: containers tạo cho annotated endpoints được quản lý **bên trong registry**, **không đăng ký từng container dưới dạng bean để autowiring tự động**. Vì thế:

~~~java
// Không nên mong endpoint container có bean name "jobsDemo"
// trong ApplicationContext chỉ vì @JmsListener(id = "jobsDemo").

// Cách ổn định:
MessageListenerContainer listener =
        registry.getListenerContainer("jobsDemo");
~~~

Cần phân biệt ba đối tượng:
- `JmsListenerEndpointRegistry` **là Spring bean**, có thể inject vào controller/service.
- `DefaultJmsListenerContainerFactory` **là Spring bean factory**, chứa cấu hình tạo container.
- `DefaultMessageListenerContainer` **instance do registry tạo** thông thường không phải Spring bean độc lập.

**Ngoại lệ:** nếu bạn tự tạo một bean `DefaultMessageListenerContainer` theo cách thủ công, bean đó có thể được autowire như một Spring bean. Nhưng **không suy ra nó có mặt trong registry**; registry không phải “trình quét mọi bean có type MessageListenerContainer”.

## 11. Trạng thái và khả năng quan sát sâu hơn

`MessageListenerContainer` chung có `isRunning()` và lifecycle. Nếu container thực tế là `DefaultMessageListenerContainer`, có thể lấy một số chỉ số bổ sung:

~~~java
MessageListenerContainer listener =
        registry.getListenerContainer("jobsDemo");

if (listener instanceof DefaultMessageListenerContainer dmlc) {
    int scheduled = dmlc.getScheduledConsumerCount();
    int active = dmlc.getActiveConsumerCount();

    System.out.println("SCHEDULED=" + scheduled);
    System.out.println("ACTIVE=" + active);
    System.out.println("RECOVERING=" + dmlc.isRecovering());
}
~~~

Snippet này cần import `org.springframework.jms.listener.DefaultMessageListenerContainer`. **Không cast mù** vì Spring có nhiều container implementations; ví dụ custom factory có thể tạo `SimpleMessageListenerContainer`.

- `scheduled`: số consumer invoker tasks đang được lên lịch theo container.
- `active`: số consumer invokers active theo nội bộ container; **không phải chính xác số message đang xử lý trong thời điểm quan sát**.
- `isRecovering()`: dấu hiệu Default container đang cố khôi phục JMS resources, không phải một metric end-to-end về business.
- `isRunning()`: trạng thái lifecycle, **không chứng minh** broker connection, queue/selector và handler luôn khỏe.

Nếu một hệ thống muốn biết “thực sự xử lý được message chưa”, cần thêm broker-side connected consumers, queue depth/oldest age, listener metrics, logs lỗi conversion/transaction và business DB outcome.

### 11.1. Bảng diễn giải tình huống thực tế

| `isRunning()` | Broker consumer count | Queue messages | Nhận định hợp lý |
| --- | --- | --- | --- |
| false | 0 cho endpoint này | Có thể tăng | Container dừng ở JVM này; không được coi là queue pause toàn hệ thống |
| true | 0, logs recovery | Có thể tăng | Lifecycle đã start nhưng chưa có consumer kết nối thật |
| true | Có | 0 | Có consumer, chưa có backlog; không biết nghiệp vụ đã xong hay chưa |
| true | Có | Nhiều, oldest age tăng | Có khả năng consumer chậm, nghẽn downstream, selector/routing hoặc thiếu concurrency |
| true | Có | DLQ tăng | Message lỗi lâu dài, redelivery/rejection policy cần xem |
| false | Có consumer khác | Vẫn có delivery | Các replica/service khác còn đang nhận; stop local không dừng toàn cluster |

**Không dùng `registry.isRunning()` làm health probe duy nhất:** nó chỉ cần ít nhất một endpoint running để true, và running không bao gồm broker/business readiness.

## 12. Một service quản lý một endpoint an toàn hơn controller gọi registry trực tiếp

Ở production, nên gom logic quản lý vào service với **allowlist**, authorization, audit log và kiểm soát race. Ví dụ service Java 17 dưới đây chỉ thao tác trên một endpoint được xác định:

~~~java
package example.jmsregistry;

import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.listener.MessageListenerContainer;
import org.springframework.stereotype.Service;

@Service
public class JmsListenerControlService {

    private static final String MANAGED_ID = "jobsDemo";

    private final JmsListenerEndpointRegistry registry;

    public JmsListenerControlService(
            JmsListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public synchronized boolean stopLocalListener() {
        MessageListenerContainer container = requireContainer();
        if (container.isRunning()) {
            container.stop();
        }
        return container.isRunning();
    }

    public synchronized boolean startLocalListener() {
        MessageListenerContainer container = requireContainer();
        if (!container.isRunning()) {
            container.start();
        }
        return container.isRunning();
    }

    public synchronized boolean isLocalListenerRunning() {
        return requireContainer().isRunning();
    }

    private MessageListenerContainer requireContainer() {
        MessageListenerContainer container =
                registry.getListenerContainer(MANAGED_ID);
        if (container == null) {
            throw new IllegalStateException(
                    "Unknown JMS endpoint: " + MANAGED_ID);
        }
        return container;
    }
}
~~~

Đây là class Spring hợp lệ nếu nằm trong component scan và có registry bean. `synchronized` chỉ tuần tự hóa calls **trên cùng service instance**, **không** điều phối nhiều JVM/replicas, không thay thế security và không loại trừ can thiệp lifecycle từ chỗ khác.

**Không tự mở public HTTP endpoint** như `POST /jms/stop?listenerId=...` không auth. Một người dùng bên ngoài có thể dừng xử lý mọi queue, gây SLA outage. Nếu cần API vận hành, giới hạn ID, yêu cầu role, bảo vệ CSRF/phân quyền phù hợp, ghi audit, đặt timeout và chỉ cho phép trong mạng quản trị. Với thay đổi production, phải có runbook và quy trình xác nhận tác động đến in-flight messages.

### 12.1. Stop là một “pause intake” mang tính cục bộ

Một listener đang stop có thể không nhận message mới. Nhưng:
- Các consumer khác trên **cùng queue** vẫn có thể nhận.
- Broker có thể tiếp tục lưu message đến; queue backlog và TTL vẫn vận hành.
- Topic non-durable subscription khi offline có thể **bỏ lỡ** message.
- Có thể còn in-flight message đang được commit/rollback theo transaction state.

Nếu muốn **pause thực sự trên toàn cluster**, cần một control plane/orchestrator điều phối tất cả instances, hoặc broker administrative control theo policy; registry của một JVM không thể làm điều đó một mình.

## 13. Quản lý startup và autoStartup

Khi Spring context refresh, registry tham gia lifecycle như một `SmartLifecycle` component. Mỗi container có thể có `autoStartup` và `phase`:

~~~java
@Bean
DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
        ConnectionFactory connectionFactory) {
    var factory = new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setAutoStartup(false);
    factory.setSessionTransacted(true);
    return factory;
}
~~~

Đây là snippet Spring `@Configuration`; cần imports `jakarta.jms.ConnectionFactory`, `org.springframework.context.annotation.Bean` và `org.springframework.jms.config.DefaultJmsListenerContainerFactory`. Với `setAutoStartup(false)`, listeners tạo bởi factory sẽ **không tự start khi context startup**; một service/operator có thể gọi `registry.getListenerContainer(id).start()` sau khi dependency/broker sẵn sàng.

**Quan trọng:** `autoStartup=false` chỉ điều khiển **startup tự động**, không có nghĩa cấm gọi `start()` thủ công. Sau khi context đã refresh, `registry.start()` có thể chủ động start các containers trong registry, **kể cả endpoint vốn để autoStartup=false** trong một số triển khai như Spring 6.2.x. Vì vậy không dùng `registry.start()` bừa bãi khi chỉ muốn mở một listener.

Boot có thể cấu hình `spring.jms.listener.auto-startup=false` cho default listener factory (nếu app chưa tự thay factory). Khi tạo nhiều factories, điều kiện auto-startup có thể khác nhau giữa endpoints; phải kiểm tra từng container thay vì đoán từ một property global.

### 13.1. Phase và thứ tự shutdown

`SmartLifecycle.getPhase()` cho biết phase tương đối để Spring phối hợp start/stop. Phase lớn thường start muộn hơn, stop sớm hơn phase nhỏ trong lifecycle processor thông thường. Không tự chỉnh phase chỉ để thay thế chuẩn bị backend connectivity; broker có thể unavailable ngay cả khi các beans đã start đúng thứ tự.

Khi app dừng theo SIGTERM/Kubernetes, lifecycle processor gọi stop/destroy theo cơ chế Spring, nhưng grace period có hạn. Nếu một handler đang gọi DB/HTTP quá lâu, orchestrator có thể kill tiến trình trước khi hoàn tất. Cần idempotency, transaction timeout và recovery phù hợp.

## 14. Đăng ký endpoint bằng code: dùng registrar trước, registry khi chạy

Không phải mọi listener đều có annotation. Spring hỗ trợ `JmsListenerEndpoint` và `JmsListenerConfigurer` để đăng ký bằng code.

### 14.1. Cấu hình static/programmatic lúc khởi động

~~~java
package example.jmsregistry;

import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListenerConfigurer;
import org.springframework.jms.config.JmsListenerEndpointRegistrar;
import org.springframework.jms.config.SimpleJmsListenerEndpoint;

@Configuration
@EnableJms
public class ExtraEndpointConfiguration
        implements JmsListenerConfigurer {

    @Override
    public void configureJmsListeners(
            JmsListenerEndpointRegistrar registrar) {

        var endpoint = new SimpleJmsListenerEndpoint();
        endpoint.setId("auditEvents");
        endpoint.setDestination("audit.events");
        endpoint.setMessageListener(message ->
                System.out.println("Received JMS audit event"));

        registrar.registerEndpoint(endpoint);
    }
}
~~~

Đây là một class Spring Framework 6.x biên dịch được nếu đã có JMS infrastructure và default `JmsListenerContainerFactory`, broker/destination hợp lệ. Dù không có `@JmsListener` trên method audit, endpoint `auditEvents` vẫn được đăng ký qua registrar, tạo container và xuất hiện trong registry.

**Lý do dùng registrar:** thực hiện registration trong pha khởi tạo khi Spring đang chuẩn bị endpoints, thay vì cố tạo/khởi động container thủ công trước context refresh.

### 14.2. Đăng ký một endpoint khi ứng dụng đã chạy

Nếu thật sự cần listener được tạo theo cấu hình runtime, registry có API:

~~~java
SimpleJmsListenerEndpoint endpoint =
        new SimpleJmsListenerEndpoint();
endpoint.setId("dynamicAudit");
endpoint.setDestination("audit.dynamic");
endpoint.setMessageListener(message ->
        System.out.println("Dynamic audit event received"));

registry.registerListenerContainer(
        endpoint, listenerFactory, true);
~~~

Đoạn snippet này yêu cầu:
- `registry` là `JmsListenerEndpointRegistry` đã inject.
- `listenerFactory` là `JmsListenerContainerFactory<?>` phù hợp provider/destination/transaction đã cấu hình.
- Được gọi **sau context refresh** nếu kỳ vọng `startImmediately=true` có hiệu lực ngay.
- Một unique ID không trùng endpoint đã có; ID trùng có thể ném `IllegalStateException`.
- Hệ thống kiểm soát ai được gọi registration, vì listener mới có thể tạo connection/session/consumer và tiêu thụ message ngay.

Có thể inject factory như sau:

~~~java
@Bean
ApplicationRunner registerDynamicAudit(
        JmsListenerEndpointRegistry registry,
        @Qualifier("jmsListenerContainerFactory")
        JmsListenerContainerFactory<?> listenerFactory) {

    return args -> {
        var endpoint = new SimpleJmsListenerEndpoint();
        endpoint.setId("dynamicAudit");
        endpoint.setDestination("audit.dynamic");
        endpoint.setMessageListener(message ->
                System.out.println("Received audit.dynamic"));
        registry.registerListenerContainer(
                endpoint, listenerFactory, true);
    };
}
~~~

Snippet nằm trong class `@Configuration` có imports `org.springframework.boot.ApplicationRunner`, `org.springframework.context.annotation.Bean`, `org.springframework.beans.factory.annotation.Qualifier`, `org.springframework.jms.config.JmsListenerContainerFactory`, `org.springframework.jms.config.SimpleJmsListenerEndpoint`, `org.springframework.jms.config.JmsListenerEndpointRegistry`. Nó cần broker/queue và không được trùng ID với endpoint đã tồn tại. `ApplicationRunner` chạy sau refresh nên phù hợp minh họa registration sau startup; trong môi trường thật cần xử lý lỗi registration và chính sách tự khôi phục sau restart.

### 14.3. Vì sao runtime registration không nên dùng để thay “pause”?

Đăng ký tạo **endpoint/container mới**, còn pause/resume tác động container **đang tồn tại**. Nếu mỗi lần tạm dừng/mở lại bạn lại `registerListenerContainer` với một ID mới, application sẽ tích lũy consumers, tăng session/connection và có thể xử lý cùng queue song song ngoài dự kiến. Muốn tạm dừng hoặc mở lại, dùng `container.stop/start`.

**Giới hạn API:** trong Spring JMS 6.2.x, registry không cung cấp một lệnh `unregisterListenerContainer(String)` tương đương với API quen thuộc ở Spring Rabbit. Stop không xóa registration. Nếu ứng dụng cần tạo/hủy tùy ý hàng ngàn subscriptions, hãy thiết kế vòng đời và phương án khôi phục riêng thay vì cho rằng registry là một CRUD store cho endpoints.

## 15. Runtime concurrency: registry quản lý container, không thay factory

`DefaultMessageListenerContainer` có thể có:

~~~java
MessageListenerContainer listener =
        registry.getListenerContainer("invoiceCommands");

if (listener instanceof DefaultMessageListenerContainer dmlc) {
    System.out.println(
            "Core consumers = " + dmlc.getConcurrentConsumers());
    System.out.println(
            "Max consumers = " + dmlc.getMaxConcurrentConsumers());
    System.out.println(
            "Scheduled = " + dmlc.getScheduledConsumerCount());
    System.out.println(
            "Active = " + dmlc.getActiveConsumerCount());
}
~~~

Đây là snippet; import `org.springframework.jms.listener.DefaultMessageListenerContainer`. Nếu factory tạo `SimpleMessageListenerContainer` thì cast không đúng. Nếu cần thay concurrency lúc runtime và implementation hỗ trợ, có thể dùng setters trên concrete container **sau khi đánh giá ảnh hưởng**; đó không phải khả năng của interface `MessageListenerContainer` chung.

**Khi nào không nên tăng concurrency:** yêu cầu xử lý đúng thứ tự message trên một queue, downstream DB pool nhỏ, topic subscription có thể tạo duplicate semantics, hoặc broker đã có nhiều consumer từ nhiều replicas. Một registry có ba endpoints mỗi endpoint max 5 consumers không phải tổng 5; trên một replica có thể lên tới 15 invokers trước khi nhân với replica count.

**Chú ý:** `DefaultMessageListenerContainer.getActiveConsumerCount()` có thể bao gồm invokers đang chờ `receive(timeout)`; không tự suy ra số business handlers đang xử lý cùng lúc.

## 16. Registry và Spring Boot: factory override có thể làm hành vi đổi

Với Spring Boot 3.x, JMS starter và provider phù hợp, Boot thường tự cấu hình default `JmsListenerContainerFactory`. Nếu ứng dụng khai báo một bean factory cùng tên, Boot có thể không tạo default factory như trước. Các lựa chọn như `MessageConverter`, `DestinationResolver`, `sessionTransacted`, native ConnectionFactory và concurrency cần được giữ rõ ràng.

Khi cần factory mới nhưng vẫn muốn kế thừa cấu hình mặc định của Boot 3.5.x, dùng configurer:

~~~java
@Configuration(proxyBeanMethods = false)
class CustomJmsFactoryConfiguration {

    @Bean
    DefaultJmsListenerContainerFactory criticalQueueFactory(
            DefaultJmsListenerContainerFactoryConfigurer configurer,
            ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        configurer.configure(factory,
                ConnectionFactoryUnwrapper.unwrapCaching(
                        connectionFactory));
        factory.setConcurrency("2-5");
        factory.setSessionTransacted(true);
        return factory;
    }
}
~~~

Các imports:
- `jakarta.jms.ConnectionFactory`.
- `org.springframework.context.annotation.Configuration`, `Bean`.
- `org.springframework.jms.config.DefaultJmsListenerContainerFactory`.
- `org.springframework.boot.autoconfigure.jms.DefaultJmsListenerContainerFactoryConfigurer`.
- `org.springframework.boot.jms.ConnectionFactoryUnwrapper`.

Ở annotation, chọn bean rõ:

~~~java
@JmsListener(
        id = "criticalInvoices",
        destination = "critical.invoice.queue",
        containerFactory = "criticalQueueFactory")
public void process(String body) {
    // Xử lý nghiệp vụ.
}
~~~

**Registry sẽ chứa ID `criticalInvoices`**, không phải tên factory `criticalQueueFactory`. Một factory có thể tạo **nhiều containers** cho nhiều annotated endpoints. Nếu đổi factory config sau khi containers đã được tạo, đừng mặc định containers hiện tại sẽ được tái cấu hình toàn bộ; kiểm tra behavior và xây kế hoạch restart an toàn.

## 17. Transaction, ACK và lỗi handler khi stop/start

Registry điều khiển **lifecycle của container**; nó **không trực tiếp thay** JMS acknowledgment mode hoặc transaction manager của container.

- Với `sessionTransacted=true`, listener handler thành công thì container có thể commit JMS receive; exception phù hợp làm rollback/redelivery theo provider policy.
- Với `AUTO_ACKNOWLEDGE` trên `DefaultMessageListenerContainer`, ACK có thể xảy ra **trước khi handler chạy**, nên exception không đảm bảo broker redelivery.
- Với DB transaction riêng, lỗi giữa **DB commit** và **JMS commit** vẫn có thể gây duplicate message. Cần `eventId` ổn định và consumer idempotent.
- Khi dừng container lúc có message in-flight, phải xem transaction completion/rollback, retry policy, DLQ, thời gian chờ stop và graceful shutdown.
- Khi restart, có thể nhận message cũ, message mới hoặc bản redelivery; thứ tự phụ thuộc queue/topic, concurrency và broker.

**Tình huống nguy hiểm:** dùng `stop()` để “hủy nghiệp vụ đang xử lý”, sau đó cho client gửi cùng command với event ID mới. Nếu handler cũ đã commit database hoặc payment nhưng JMS ACK chưa thành công, việc gửi mới có thể tạo double charge. Stop/start chỉ quản lý tiếp nhận, không thay business idempotency/reconciliation.

## 18. Multi-replica: registry là cục bộ cho ApplicationContext

Một service triển khai nhiều pods:

~~~text
Pod A                       Pod B                       Pod C
 └─ Registry A                └─ Registry B               └─ Registry C
     └─ jobsDemo container       └─ jobsDemo container       └─ jobsDemo container
            │                          │                          │
            └──────────────────────────┼──────────────────────────┘
                                       ▼
                                  JMS broker queue
~~~

`Registry A.stop()` **không** dừng `Registry B` và `Registry C`. Hơn nữa, một application có thể có nhiều ApplicationContext trong test hoặc framework setup; inject nhầm context sẽ khiến registry liệt kê endpoint khác kỳ vọng.

Nếu cần “pause consumption toàn hệ thống”:
1. Định nghĩa phạm vi rõ: một endpoint, một replica, một deployment hay toàn broker address.
2. Dùng control plane có auth/audit để thực hiện nhất quán, hoặc broker administrative API nếu phù hợp.
3. Quan sát consumer counts trên broker sau lệnh, không chỉ một Java boolean.
4. Xử lý in-flight messages và deadline; rollback/redelivery theo policy.
5. Khi resume, có thể gặp backlog lớn và burst load; giới hạn concurrency/backpressure.
6. Đảm bảo operational action có owner, thời điểm, lý do và phương án rollback.

Một endpoint ID **chỉ định danh container bên trong một registry/context**, không phải global identifier duy nhất giữa nhiều JVM.

## 19. Health, metrics và logging có ý nghĩa

Đo ít nhất ba tầng:

| Tầng | Metric/trạng thái | Ý nghĩa |
| --- | --- | --- |
| Registry | IDs được đăng ký, `getListenerContainer(id)!=null` | Endpoint infrastructure đã tồn tại |
| Container | `isRunning()`, scheduled/active invokers, `isRecovering()` | Lifecycle/consumer invokers của JVM này |
| Broker | Connected consumers, queue depth, in-flight, oldest age, DLQ | Giao nhận/routing thực trên broker |
| Business | Success/failure, DB commit, retries/idempotency | Công việc nghiệp vụ thực sự hoàn tất |

Một log quản trị nên có `endpointId`, `applicationInstanceId`, `action` (STOP/START), người thao tác, timestamp UTC, old/new lifecycle state và correlation ID. Với message processing, log `eventId` và `JMSMessageID` theo chính sách bảo vệ dữ liệu; không in username/password/PII nhạy cảm.

**Đừng dùng registry làm message inventory.** Registry không biết queue chứa bao nhiêu message, deadline TTL, offset, số event đã xử lý hay DLQ details. Broker console, metrics và dữ liệu nghiệp vụ mới cung cấp bức tranh đầy đủ.

### Health aggregation: phân biệt ANY với ALL

~~~java
Set<String> ids = Set.copyOf(
        registry.getListenerContainerIds());

boolean anyRunning = ids.stream()
        .map(registry::getListenerContainer)
        .anyMatch(c -> c != null && c.isRunning());

boolean allRunning = !ids.isEmpty()
        && ids.stream()
            .map(registry::getListenerContainer)
            .allMatch(c -> c != null && c.isRunning());
~~~

`anyRunning` phù hợp nghĩa **có ít nhất một endpoint running**. `allRunning` có thể dùng để đánh giá **start state của toàn bộ endpoints đã đăng ký**, nhưng nếu có listener cố ý đặt `autoStartup=false` hoặc stop theo lịch, dùng allRunning làm readiness sẽ báo giả. Readiness phải dựa trên **các endpoints bắt buộc phục vụ tại thời điểm đó** và broker health, không chỉ all/any boolean.

## 20. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Cách xác minh |
| --- | --- | --- |
| Inject registry thất bại | Chưa bật `@EnableJms` hoặc Boot JMS infrastructure không được kích hoạt | Classpath, condition report, annotation config |
| `getListenerContainerIds()` rỗng | Không có endpoints, component scan sai, annotation support tắt, đăng ký muộn | Kiểm tra bean listener, package scan, context |
| `getListenerContainer("myId")==null` | ID sai/không đặt, dùng tên queue thay ID, context khác | So sánh `@JmsListener(id=...)` và IDs thực |
| App startup lỗi duplicate endpoint ID | Hai endpoints có ID trùng | Đặt ID duy nhất cho từng annotation/registration |
| `isRunning()==true` nhưng không nhận | Broker down/recovery, auth, queue/topic, selector, conversion | Logs recovery, broker consumer count, metrics |
| `registry.isRunning()==true` nhưng endpoint X dừng | Registry trả true khi **có ít nhất một** container running | Kiểm tra theo từng ID |
| Gọi `registry.stop()` làm mọi endpoint im lặng | Đây là stop **toàn registry** | Dùng `getListenerContainer(id).stop()` |
| Một pod stop nhưng queue vẫn bị consume | Replicas/consumers khác còn chạy | Broker consumer list, toàn cluster |
| Message mất khi stop topic | Non-durable subscription offline | Durable/shared subscription + TTL/retention |
| Message giao lại sau resume | In-flight rollback, JMS transaction chưa commit | Redelivery count, broker logs, consumer idempotency |
| `getActiveConsumerCount()` không bằng số handlers | Active invokers có thể đang chờ receive | Tracing handler, broker in-flight metrics |
| Custom factory khiến listener mất transaction | Không dùng Boot configurer hoặc quên `sessionTransacted` | Inspect factory/container runtime và fault test |
| Runtime registration ID mới liên tục tăng | Tạo endpoint thay vì start/stop cái cũ | Giữ ID ổn định và quản lý registration lifecycle |
| Thấy API `unregisterListenerContainer` nhưng compile lỗi | Nhầm **RabbitListenerEndpointRegistry** với **JmsListenerEndpointRegistry** | Xác minh imports, Spring Framework JMS Javadoc |
| Registry đã start nhưng `JmsTemplate` send lỗi | Producer và listener dùng connection config khác hoặc broker lỗi | Kiểm tra cả hai factories/client logs |
| Stop chậm/hang khi shutdown | Handler in-flight, network timeout, transaction commit/recovery | Thread dumps, timeout, grace period |

Đọc log khởi động/condition report trước khi thay cấu hình bừa bãi. Một annotation class không nằm trong Spring component scan sẽ không được đăng ký; việc sửa broker URL sẽ không giải quyết lỗi ấy.

## 21. Kiểm thử bằng hành vi thay vì một dòng trạng thái

**Bài 1 — Danh sách IDs:** tạo một listener với `id="jobsDemo"` và một không đặt ID. In `getListenerContainerIds()`; xác định ID ổn định và ID generated.

**Bài 2 — Tìm đúng container:** thử `getListenerContainer("jobsDemo")`, `getListenerContainer("demo.registry.jobs")` và một ID không tồn tại. Giải thích kết quả `null`.

**Bài 3 — Lifecycle một endpoint:** tạo hai listeners trên hai queues. Stop riêng listener A; gửi message vào cả hai; xác nhận B vẫn nhận trong JVM, A chỉ nhận lại khi start (nếu broker policy giữ message).

**Bài 4 — Registry-wide stop:** gọi `registry.stop()` trong môi trường test; xác nhận cả hai endpoints dừng. So sánh với `listener.stop()`; không chạy bài này trên production.

**Bài 5 — ANY vs ALL:** dừng một trong hai listeners, so sánh `registry.isRunning()` với từng `container.isRunning()`. Giải thích vì sao registry có thể true.

**Bài 6 — Consumer runtime type:** cast qua `instanceof DefaultMessageListenerContainer` rồi log scheduled/active count và recovering; so sánh với số connected consumers ở broker.

**Bài 7 — Broker outage:** tắt Artemis test, quan sát container còn running nhưng `isRecovering()`/logs thay đổi; khởi động broker, kiểm tra recovery và delivery.

**Bài 8 — Auto startup:** dùng `spring.jms.listener.auto-startup=false` với default factory, quan sát container tồn tại nhưng chưa running. Start đúng ID; không gọi toàn registry khi còn endpoints cần ở trạng thái disabled.

**Bài 9 — Programmatic endpoint:** đăng ký `SimpleJmsListenerEndpoint` bằng `JmsListenerConfigurer` lúc startup; xác nhận ID mới trong registry.

**Bài 10 — Runtime registration:** dùng `registerListenerContainer(endpoint,factory,true)` sau context refresh; gửi message và quan sát; thử ID trùng trong môi trường test và giải thích exception.

**Bài 11 — Transaction:** bật local `sessionTransacted=true`, cho listener ném lỗi; xác minh rollback/redelivery hoặc DLQ theo provider policy. Stop/start không thay chính sách ACK.

**Bài 12 — Multi-replica:** chạy hai instances cùng queue và cùng listener ID. Stop một instance, xem consumer khác còn nhận; giải thích tại sao ID không là global control-plane key.

**Bài 13 — Topic:** thử một non-durable topic subscriber stop/start, quan sát khả năng bỏ lỡ event; không mặc định queue semantics đúng cho topic.

**Bài 14 — Graceful shutdown:** tạo handler xử lý lâu, stop rồi tắt JVM, ghi thời gian stop, in-flight, DB commit và redelivery sau restart.

**Bài 15 — Security:** mô phỏng một route quản trị có allowlist và audit; xác minh user không có quyền không thể start/stop bất kỳ listener nào.

### Checklist tự đánh giá

- [ ] Phân biệt **endpoint ID**, destination, factory bean và container instance.
- [ ] Biết `JmsListenerEndpointRegistry` là Spring bean, còn containers tạo bởi annotation thường **không** là bean riêng.
- [ ] Biết `getListenerContainerIds()`, `getListenerContainers()` và `getListenerContainer(id)` với nhánh `null`.
- [ ] Biết stop/start **một container** và stop/start **toàn registry**.
- [ ] Không diễn giải `registry.isRunning()` thành “mọi endpoints healthy”.
- [ ] Biết chỉ số scheduled/active/recovering của `DefaultMessageListenerContainer` không phải business result.
- [ ] Biết ID phải duy nhất trong registry và không dựa vào generated ID cho quản trị quan trọng.
- [ ] Biết đăng ký endpoint bằng `JmsListenerConfigurer`/`SimpleJmsListenerEndpoint` hoặc runtime `registerListenerContainer`.
- [ ] Không copy nhầm `unregisterListenerContainer` của Rabbit sang JMS.
- [ ] Hiểu `stop/start` là điều khiển **local intake**, không dừng broker/queue hoặc mọi replicas.
- [ ] Có cơ chế auth/audit khi đưa lifecycle control ra management API.
- [ ] Hiểu transaction/ACK, in-flight và idempotency khi stop/start/shutdown.
- [ ] Đã kiểm chứng bằng broker test, logs và metrics thay vì dựa trên một boolean.

**Câu hỏi kết thúc:** “Ứng dụng có `@JmsListener(id="payments", destination="payment.commands")`. Làm sao chỉ dừng consumer này mà không dừng mọi listener?” — Inject `JmsListenerEndpointRegistry`, gọi `getListenerContainer("payments")`, kiểm tra khác `null`, sau đó gọi `stop()` trên **container được trả về**. Không truyền tên queue, không gọi `registry.stop()`; và phải biết còn replicas khác có thể đang consume.

## 22. Tài liệu tham khảo chính thức

1. [Spring Framework Reference — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html): `@JmsListener`, container không phải bean độc lập, registry và đăng ký endpoint programmatic.
2. [Spring Framework 6.2 — JmsListenerEndpointRegistry Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/config/JmsListenerEndpointRegistry.html): chữ ký `getListenerContainerIds`/`getListenerContainer`/`getListenerContainers`, start/stop và register.
3. [Spring Framework 6.2 — JmsListenerEndpointRegistrar Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/config/JmsListenerEndpointRegistrar.html): đăng ký endpoint trong giai đoạn annotation infrastructure setup.
4. [Spring Framework 6.2 — SimpleJmsListenerEndpoint Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/config/SimpleJmsListenerEndpoint.html): thiết lập ID, destination và `MessageListener` trực tiếp.
5. [Spring Framework — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): listener container, concurrency, session transactions, resource management.
6. [Spring Framework 6.2 — DefaultMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html): trạng thái invoker, recovery và lifecycle.
7. [Spring Boot 3.5 — JMS](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html): Artemis starter, auto-configuration và default listener factory.
8. [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): `spring.jms.listener.*` và `spring.artemis.*`.
9. [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): JMS consumer/connection/session, ACK, transaction và redelivery.

**Kết luận:** `JmsListenerEndpointRegistry` là **điểm truy cập và điều phối vòng đời** cho các containers tạo từ `@JmsListener`. Dùng **ID ổn định** để tìm container, thao tác **đúng phạm vi** với start/stop, và kết hợp registry state với broker metrics và business outcome. Điều khiển lifecycle không thay thế quản trị broker hay cơ chế đảm bảo xử lý nghiệp vụ.