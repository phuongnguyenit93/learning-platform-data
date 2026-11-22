# Phân biệt vòng đời bean nghiệp vụ với vòng đời listener container trong Spring JMS

## 1. Vấn đề cần hiểu

Một method gắn `@JmsListener` không đồng nghĩa bản thân đối tượng Java chứa method đó là JMS consumer hoặc chịu trách nhiệm mở/đóng connection. Trong Spring JMS có **hai vòng đời có liên quan nhưng không đồng nhất**:

- **Spring business bean lifecycle**: khởi tạo đối tượng, inject dependencies, chạy `@PostConstruct`, phục vụ các lời gọi nghiệp vụ, sau cùng chạy `@PreDestroy` khi ApplicationContext hủy bean.
- **JMS listener container lifecycle**: đăng ký endpoint, tạo/quản lý Connection/Session/MessageConsumer, start nhận message, điều phối listener threads, xử lý transaction/recovery, stop rồi giải phóng tài nguyên.

**Tình huống quan trọng:** một `OrderBusinessService` có thể đã được Spring khởi tạo hoàn toàn trong khi JMS listener container vẫn **stopped**. Khi gọi `container.start()`, Spring chỉ bắt đầu hoạt động nhận message; bean không bị xây dựng lại. Khi gọi `container.stop()`, bean vẫn tồn tại và có thể được caller khác gọi; `@PreDestroy` chưa được thực hiện.

Sau bài học, bạn sẽ biết cách:

1. Giải thích vai trò `@Component`, `@Service`, `@PostConstruct`/`@PreDestroy` đối lập với `@JmsListener`/`MessageListenerContainer`.
2. Phân biệt listener endpoint registration, container startup, broker connectivity, handler execution và business commit.
3. Dùng `@EnableJms`, `JmsListenerContainerFactory`, `JmsListenerEndpointRegistry`, `SmartLifecycle`.
4. Cấu hình `autoStartup`, `phase`, start/stop/pause/resume từng listener theo ID.
5. Thiết kế readiness, graceful shutdown, transaction, recovery và thread safety.
6. Chạy ví dụ **Java 17+, Spring Boot 3.5.x và ActiveMQ Artemis embedded** chứng minh hai vòng đời khác nhau.

## 2. Hai đối tượng, hai trách nhiệm

| Góc nhìn | Bean nghiệp vụ Spring | Spring JMS listener container |
| --- | --- | --- |
| Đại diện | Service/handler chịu trách nhiệm business logic. | Hạ tầng nhận message và gọi handler. |
| Người tạo | `BeanFactory`/`ApplicationContext` thông qua component scan hoặc `@Bean`. | Spring JMS annotation infrastructure qua `JmsListenerContainerFactory` hoặc do ứng dụng khai báo thủ công. |
| Khởi tạo | Constructor, dependency injection, bean post-processing, `@PostConstruct`. | Endpoint/factory config, JMS resources, khởi tạo listening infrastructure. |
| Start | Không có start bắt buộc cho POJO service thông thường. | `start()`, auto-startup, `SmartLifecycle`. |
| Khi broker mất kết nối | Bean vẫn có thể tồn tại. | Container có thể recovery/reconnect hoặc báo lỗi. |
| Stop | Không tự bị destroy vì listener dừng. | `stop()` dừng/giảm tiếp nhận theo implementation. |
| Restart | Không bắt buộc constructor/`@PostConstruct` chạy lại. | `start()` lại, có thể tạo lại JMS consumer resources. |
| Shutdown | `@PreDestroy`/destroy callbacks khi context đóng. | Dừng lifecycle và giải phóng Connection/Session/Consumer. |
| Đồng thời | Singleton method có thể được nhiều thread gọi. | Concurrency, task executor, session/consumer threads. |

Điểm cốt lõi: **Bean trả lời “xử lý message như thế nào?”; container trả lời “ai nhận message, lúc nào và bằng tài nguyên JMS nào?”**. Một method business không tự mở JMS connection chỉ vì có annotation.

~~~mermaid
flowchart TD
  A["ApplicationContext"] --> B["OrderBusinessService bean"]
  A --> C["OrderListener bean @JmsListener"]
  A --> D["JmsListenerEndpointRegistry"]
  D --> E["MessageListenerContainer"]
  E --> F["Connection / Session / MessageConsumer"]
  F <--> G[("Broker Queue")]
  E --> C
  C --> B
~~~

`jakarta.jms.MessageListener` là **callback contract** JMS, khác với `org.springframework.jms.listener.MessageListenerContainer` là **lifecycle infrastructure**. Spring có thể tạo listener adapter để gọi method annotated trên bean.

## 3. Spring tạo endpoint như thế nào?

Với `@JmsListener`:

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    private final OrderService orderService;

    public OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @JmsListener(id = "ordersListener", destination = "orders.commands")
    public void receive(String orderId) {
        orderService.handle(orderId);
    }
}
~~~

Đoạn trên là **fragment gồm một class Spring-managed**; `OrderService` là dependency ứng dụng cần định nghĩa. Khi bật hạ tầng JMS:

1. Spring tạo bean `OrderListener` và inject `OrderService`.
2. `JmsListenerAnnotationBeanPostProcessor` phát hiện method annotated.
3. Method trở thành listener endpoint; `JmsListenerContainerFactory` tạo container/adapter tương ứng.
4. `JmsListenerEndpointRegistry` quản lý container của annotation endpoint.
5. Nếu cấu hình `autoStartup=true`, Spring lifecycle processor yêu cầu container start trong quá trình context refresh.
6. Container nhận message và dispatch tới method của bean; bean business thực hiện xử lý.

**Một chi tiết dễ sai:** container do annotation infrastructure tạo **không phải Spring bean độc lập có thể autowire trực tiếp**. Để lấy nó, dùng `registry.getListenerContainer("ordersListener")`. Trường hợp ứng dụng **tự khai báo** `DefaultMessageListenerContainer` bằng `@Bean` là một trường hợp khác: container đó thực sự là bean.

`@JmsListener(id=...)` đặt **ID container/endpoint**, không phải tên của queue, bean hay class. ID ổn định giúp kiểm soát và giám sát từng listener. Nếu bỏ `id`, Spring có thể sinh ID; khi cần quản trị runtime, nên khai báo ID tường minh.

### 3.1. Một method có thể có nhiều endpoint

`@JmsListener` là repeatable; một method có thể đăng ký nhiều endpoints. Một bean không đồng nghĩa chỉ một container. Ngược lại, một container cũng có thể có nhiều JMS consumers theo concurrency. Khi giám sát đừng nhầm:

- Số Spring business beans.
- Số endpoint containers.
- Số JMS consumers/sessions.
- Số message handler invocations.

Các con số này độc lập về khái niệm.

### 3.2. @EnableJms làm gì?

Trong Spring Framework thuần, `@EnableJms` bật infrastructure phát hiện `@JmsListener` và đăng ký endpoints. Cần `ConnectionFactory` và một `JmsListenerContainerFactory`, mặc định tìm bean tên `jmsListenerContainerFactory` nếu endpoint không chỉ rõ factory. Spring Boot có thể auto-configure các thành phần này khi JMS dependencies hiện diện.

**`@EnableJms` không tương đương `container.start()`**, cũng không chứng minh broker kết nối được. Nếu method annotated không được scan hoặc profile/conditional không active, endpoint **không tồn tại**, khác với endpoint **có nhưng đang stopped**.

## 4. Timeline giữa hai vòng đời

| Giai đoạn | Business bean | Listener container |
| --- | --- | --- |
| Context tạo bean definitions | Chưa có instance. | Chưa có container cho annotated method. |
| Instantiate/inject | Constructor/injection. | Listener processor phát hiện metadata của endpoint. |
| Bean initialization | `@PostConstruct` và init callbacks. | Factory/registry chuẩn bị endpoint và container. |
| Context lifecycle start | Bean vẫn sẵn sàng gọi method. | Những container auto-startup được yêu cầu `start()`. |
| Ứng dụng chạy | Methods xử lý nghiệp vụ, có thể dùng DB/API. | JMS consumers nhận, convert/dispatch, quản lý transaction. |
| Gọi `stop()` | Bean **không tự bị hủy**. | Container dừng nhận theo cơ chế của nó. |
| Gọi `start()` tiếp | `@PostConstruct` **không chạy lại** vì stop/start container. | Container tiếp tục bắt đầu lắng nghe. |
| ApplicationContext close | `@PreDestroy`/destroy callbacks (shutdown bình thường). | Containers dừng theo phases và destroy JMS resources. |

~~~mermaid
flowchart LR
  B0["Bean chưa tạo"] --> B1["Bean init @PostConstruct"]
  B1 --> B2["Bean hoạt động"]
  B2 --> B3["Bean destroy @PreDestroy"]
  C0["Endpoint/container registered"] --> C1["Container stopped"]
  C1 --> C2["Container running"]
  C2 --> C1
  C1 --> C3["Container destroyed"]
  C2 --> C3
~~~

Hai dòng là **hai state machines riêng**. Container có thể cycling stopped/running nhiều lần trong một vòng đời singleton bean. Nếu bean scope tùy biến hoặc context refresh, hành vi có thể khác, nhưng **container restart đơn thuần không tạo lại singleton**.

### 4.1. @PostConstruct không phải “listener started”

`@PostConstruct` thuộc **bean lifecycle**; chạy trong initialization. Nó phù hợp để kiểm tra cấu hình, thiết lập state nội bộ hoặc resource do **chính bean sở hữu**. Không nên tự tạo vòng lặp `receive()`, block vô hạn chờ broker hoặc gọi `registry.start()` trước khi annotation endpoints được đăng ký.

Ngược lại, container `start()` có thể xảy ra **sau** khi bean initialized, dùng tài nguyên của broker. Một bean sẵn sàng về cấu trúc **chưa đủ** chứng minh DB migration hoặc upstream API đã sẵn sàng cho processing.

### 4.2. ApplicationRunner không phải startup gate mặc định

Trong Spring Boot, `ApplicationRunner`/`CommandLineRunner` chạy sau context refresh. Spring sẽ có cơ hội start `SmartLifecycle` auto-startup **trước khi runner được gọi**; `ApplicationReadyEvent` được phát sau runners. Vì vậy listener auto-startup có thể đã nhận message trước khi app báo ready.

Nếu cần đợi initialization riêng của hệ thống, **tắt autoStartup rồi chủ động start** từ coordinator/runner khi điều kiện ready đã thỏa. Đừng chỉ thêm một `ApplicationReadyEvent` listener và mặc nhiên tin rằng JMS chưa được giao trước event đó.

## 5. SmartLifecycle và các trạng thái runtime

Spring JMS `MessageListenerContainer` triển khai `SmartLifecycle` với API:

| API | Ý nghĩa |
| --- | --- |
| `isAutoStartup()` | Container có tự start theo Spring lifecycle không? |
| `getPhase()` | Thứ tự start/stop so với các lifecycle components khác. |
| `start()` | Yêu cầu container bắt đầu hoạt động. |
| `stop()` | Yêu cầu dừng hoạt động của container. |
| `stop(Runnable callback)` | Dừng và gọi callback sau khi stop hoàn tất theo hợp đồng implementation. |
| `isRunning()` | Trạng thái lifecycle running, **không đồng nghĩa broker khỏe**. |

**Lifecycle phase:** start từ **phase thấp đến cao**; stop theo **phase cao đến thấp**. Với mặc định phổ biến của JMS container, start muộn và stop sớm giúp dependencies sẵn sàng trước khi nhận message và có cơ hội còn sống khi handler hoàn tất lúc shutdown. Tuy nhiên các phases thực tế phải kiểm chứng ở ứng dụng có nhiều custom factories/components.

Ví dụ, một bean cấu hình cache cũng có thể triển khai `SmartLifecycle` và có phase thấp hơn listener. Trong trường hợp đó, start cache trước; stop listener trước cache. **Phase không thay cho dependency injection hay readiness check** đối với hệ thống bên ngoài.

### 5.1. isRunning khác isConnected

`container.isRunning()==true` chỉ mô tả container đã được yêu cầu chạy/đang ở lifecycle state running. Nó **không tự bảo đảm**:

- Broker hiện kết nối thành công.
- JMS consumer đang active trên broker.
- Listener không lỗi business hoặc converter.
- Queue có message đang được xử lý.
- Database transaction đã commit.
- Event không bị rollback/redelivery.

`DefaultMessageListenerContainer` có recovery/backoff khi broker tạm mất kết nối; trong thời gian đó container có thể báo running nhưng vẫn chưa nhận message. Để biết sức khỏe, cần thêm broker metrics, logs recovery, consumer count và thời điểm xử lý thành công cuối cùng.

## 6. Ví dụ chạy được: Java 17 + Spring Boot + Artemis embedded

Demo sau chứng minh bằng output rằng bean nghiệp vụ **đã initialized trong khi listener chưa start**; sau khi gọi `start()`, handler xử lý; sau khi `stop()`, bean **vẫn tồn tại**; chỉ khi đóng ApplicationContext, `@PreDestroy` mới chạy.

Yêu cầu **JDK 17+**, Maven, Spring Boot **3.5.7** và Artemis embedded. Demo sử dụng `CountDownLatch`/callback stop thay vì sleep tùy ý, và chỉ gửi một message để output dễ kiểm chứng.

### 6.1. Cấu trúc

~~~text
jms-lifecycle-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/jmslifecycle/
    │   ├── JmsLifecycleApplication.java
    │   ├── OrderBusinessService.java
    │   └── OrderMessageListener.java
    └── resources/
        └── application.properties
~~~

### 6.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>jms-lifecycle-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-artemis</artifactId>
        </dependency>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>artemis-jakarta-server</artifactId>
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

Spring Boot parent quản lý các dependency versions. `spring-boot-starter-artemis` cung cấp JMS integration/client; `artemis-jakarta-server` cho phép tạo broker embedded.

### 6.3. application.properties

~~~properties
spring.artemis.mode=embedded
spring.artemis.embedded.queues=demo.lifecycle
spring.artemis.embedded.persistent=false
spring.jms.pub-sub-domain=false
spring.jms.listener.auto-startup=false
spring.lifecycle.timeout-per-shutdown-phase=20s
spring.main.web-application-type=none
spring.main.banner-mode=off
~~~

**Chìa khóa:** `spring.jms.listener.auto-startup=false` không xóa bean, không bỏ đăng ký endpoint mà chỉ tắt auto-start của listener container do Boot cấu hình. Queue `demo.lifecycle` vẫn tồn tại trong broker embedded nên producer có thể gửi trước khi listener bắt đầu nhận.

`persistent=false` chỉ dành cho demo; không dùng cấu hình này để kết luận queue giữ message qua restart. `timeout-per-shutdown-phase` điều chỉnh khoảng chờ lifecycle trong shutdown bình thường, không bảo đảm mọi tác vụ sẽ hoàn tất nếu process bị kill.

### 6.4. OrderBusinessService.java

~~~java
package com.example.jmslifecycle;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;

import org.springframework.stereotype.Service;

@Service
public class OrderBusinessService {

    private final CountDownLatch processed = new CountDownLatch(1);
    private volatile boolean initialized;

    @PostConstruct
    public void initialize() {
        initialized = true;
        System.out.println("BUSINESS_POST_CONSTRUCT");
    }

    public void process(String orderId) {
        if (!initialized) {
            throw new IllegalStateException("Business service not ready");
        }
        System.out.println("BUSINESS_HANDLE=" + orderId);
        processed.countDown();
    }

    public boolean awaitProcessed(long timeout, TimeUnit unit)
            throws InterruptedException {
        return processed.await(timeout, unit);
    }

    public boolean isInitialized() {
        return initialized;
    }

    @PreDestroy
    public void destroy() {
        initialized = false;
        System.out.println("BUSINESS_PRE_DESTROY");
    }
}
~~~

`@PostConstruct` chạy khi Spring initialize bean. Method `process` có thể được gọi cho mỗi message; `@PreDestroy` chạy khi Spring context hủy bean. `CountDownLatch` chỉ phục vụ demo một message; đừng dùng latch đếm một lần làm state xử lý dài hạn cho production.

### 6.5. OrderMessageListener.java

~~~java
package com.example.jmslifecycle;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderMessageListener {

    private final OrderBusinessService business;

    public OrderMessageListener(OrderBusinessService business) {
        this.business = business;
    }

    @JmsListener(
            id = "orderLifecycleListener",
            destination = "demo.lifecycle")
    public void onMessage(String body) {
        business.process(body);
    }
}
~~~

Bean listener chỉ chuyển giao message tới `OrderBusinessService`. Container có ID `orderLifecycleListener` được registry quản lý riêng. Đặt logic nghiệp vụ trong service giúp test độc lập khỏi JMS và cho phép áp dụng DB transaction qua Spring proxy một cách rõ ràng.

### 6.6. JmsLifecycleApplication.java

~~~java
package com.example.jmslifecycle;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.listener.MessageListenerContainer;

@SpringBootApplication
@EnableJms
public class JmsLifecycleApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(
                             JmsLifecycleApplication.class, args)) {
            // Runner đã chạy khi SpringApplication.run trả về.
            // Đóng context sau demo để quan sát @PreDestroy.
        }
    }

    @Bean
    ApplicationRunner demonstrateLifecycle(
            OrderBusinessService business,
            JmsTemplate template,
            JmsListenerEndpointRegistry registry) {

        return args -> {
            MessageListenerContainer container =
                    registry.getListenerContainer("orderLifecycleListener");

            if (container == null) {
                throw new IllegalStateException("Endpoint not registered");
            }

            System.out.println(
                    "BUSINESS_INITIALIZED=" + business.isInitialized());
            System.out.println(
                    "LISTENER_RUNNING_BEFORE=" + container.isRunning());

            if (container.isRunning()) {
                throw new IllegalStateException(
                        "Expected auto-startup=false");
            }

            template.convertAndSend("demo.lifecycle", "ORDER-160");
            System.out.println("MESSAGE_SENT_WHILE_STOPPED");

            container.start();

            if (!business.awaitProcessed(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Listener did not handle message in 10 seconds");
            }

            CountDownLatch stopped = new CountDownLatch(1);
            container.stop(stopped::countDown);

            if (!stopped.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Listener stop did not finish in 10 seconds");
            }

            System.out.println(
                    "LISTENER_RUNNING_AFTER_STOP=" + container.isRunning());
            System.out.println(
                    "BUSINESS_INITIALIZED_AFTER_STOP="
                            + business.isInitialized());
        };
    }
}
~~~

**Giải thích từng bước:**

1. Spring Boot tạo singleton `OrderBusinessService`, chạy `@PostConstruct`. Nó còn được inject vào listener và ApplicationRunner.
2. `@EnableJms` bật annotation endpoint infrastructure (Spring Boot JMS auto-configuration cũng có thể hỗ trợ bước này).
3. Property `auto-startup=false` đảm bảo container đã đăng ký nhưng chưa tự start ở giai đoạn context refresh thông thường.
4. Runner lấy đúng container bằng `registry.getListenerContainer("orderLifecycleListener")`, không tìm bean theo tên class.
5. `BUSINESS_INITIALIZED=true` và `LISTENER_RUNNING_BEFORE=false` minh họa **hai trạng thái độc lập**.
6. Producer `JmsTemplate` gửi message vào broker khi listener còn stopped; message có thể được queue giữ lại cho consumer tương lai theo broker policy.
7. `container.start()` cho phép listener nhận; `CountDownLatch` được release khi business method đã được gọi.
8. `container.stop(stopped::countDown)` và `stopped.await` đợi quá trình dừng. Với `DefaultMessageListenerContainer`, callback báo khi listener processing đã thực sự dừng.
9. Sau stop, business bean vẫn initialized; gọi stop **không chạy `@PreDestroy`**.
10. Khối `try-with-resources` trong main đóng Spring context; `@PreDestroy` được gọi khi bean destruction diễn ra.

**Lưu ý:** handler latch được nhả trước khi callback handler hoàn toàn kết thúc; demo dùng stop callback để không coi mỗi lần latch release là bằng chứng transaction JMS đã commit. Không giả định chỉ bằng output này đã có bảo đảm exactly-once processing.

### 6.7. Chạy và quan sát

Trong thư mục dự án:

~~~bash
mvn spring-boot:run
~~~

Các dòng do mã ứng dụng in (không tính log Maven/Spring/Artemis), trong điều kiện broker embedded khởi động thành công và Queue chưa có competing consumers:

~~~text
BUSINESS_POST_CONSTRUCT
BUSINESS_INITIALIZED=true
LISTENER_RUNNING_BEFORE=false
MESSAGE_SENT_WHILE_STOPPED
BUSINESS_HANDLE=ORDER-160
LISTENER_RUNNING_AFTER_STOP=false
BUSINESS_INITIALIZED_AFTER_STOP=true
BUSINESS_PRE_DESTROY
~~~

Đây là **output kỳ vọng**, không phải kết quả đã chạy/biên dịch trên máy. Nếu listener không nhận message trong 10 giây hoặc không dừng trong 10 giây, demo ném exception có ý nghĩa để phát hiện lỗi thay vì im lặng. Trên broker production có backlog, TTL, các consumer khác hoặc connection issue, hành vi thời gian có thể khác.

### 6.8. Thí nghiệm để hiểu sâu

- Đổi `spring.jms.listener.auto-startup=false` thành `true`: container có thể đã running trước khi Runner bắt đầu, làm assert chủ động báo lỗi.
- Bỏ `container.start()`: bean vẫn initialized nhưng message không được **listener này** xử lý. Khi không có consumer cạnh tranh, nó có thể chờ trên Queue.
- Gọi `container.stop()` xong lại `start()`: container có thể nhận message tiếp, nhưng `@PostConstruct` không chạy lại; để test message thứ hai cần latch/counter mới vì demo latch một lần.
- Gỡ `@JmsListener` hoặc dùng `@Profile` không active: `registry.getListenerContainer(...)` trả null, khác với container tồn tại nhưng stopped.
- Đóng context sớm trong lúc handler còn chạy: phải xét transaction/ack và shutdown budget; không suy diễn mọi message đã xử lý xong.

## 7. Điều khiển runtime bằng JmsListenerEndpointRegistry

Với nhiều listeners, định danh từng endpoint:

~~~java
@Component
public class PaymentListener {

    @JmsListener(
            id = "paymentCommandsListener",
            destination = "payments.commands")
    public void onPayment(String payload) {
        // Delegate vào service nghiệp vụ.
    }
}
~~~

Trong một coordinator/operator component có quyền:

~~~java
// Fragment: registry là JmsListenerEndpointRegistry được inject.
org.springframework.jms.listener.MessageListenerContainer container =
        registry.getListenerContainer("paymentCommandsListener");

if (container == null) {
    throw new IllegalArgumentException("Unknown endpoint ID");
}

if (!container.isRunning()) {
    container.start();
}

// Khi cần tạm dừng đúng endpoint:
container.stop();
~~~

`registry.getListenerContainerIds()` liệt kê IDs; `getListenerContainers()` trả collection containers; `getListenerContainer(id)` trả một container hoặc null nếu endpoint không tồn tại.

**Phân biệt các lệnh:**

| API | Phạm vi |
| --- | --- |
| `registry.start()` | Yêu cầu start các containers do registry quản lý; khi gọi thủ công sau context refresh, có thể start cả container cấu hình autoStartup=false. |
| `registry.stop()` | Stop các containers do registry quản lý, không chỉ một Queue. |
| `container.start()` | Start riêng container được chọn theo ID. |
| `container.stop()` | Stop riêng container được chọn. |
| `container.isRunning()` | Trạng thái lifecycle của container cụ thể. |

`registry.isRunning()` không chứng minh **mọi** endpoint healthy/running. Với nhiều containers, hãy kiểm tra từng container và broker-level consumer count/queue age. Không expose một endpoint HTTP public cho phép ai cũng gọi `registry.stop()`: có thể ngừng toàn bộ pipelines. Điều khiển này cần RBAC, audit, feature policy và synchronization khi có nhiều operator/automation.

### 7.1. Bean container do annotation khác bean container khai báo thủ công

~~~java
@Bean
DefaultMessageListenerContainer manuallyManagedContainer(
        jakarta.jms.ConnectionFactory factory,
        jakarta.jms.MessageListener listener) {
    DefaultMessageListenerContainer container =
            new DefaultMessageListenerContainer();
    container.setConnectionFactory(factory);
    container.setDestinationName("orders.commands");
    container.setMessageListener(listener);
    return container;
}
~~~

Đây là **fragment bean factory** cần import Spring JMS và đảm bảo `MessageListener` có bean phù hợp. Container này được đăng ký trực tiếp trong Spring context và có thể autowire; lifecycle do Spring quản lý như bean SmartLifecycle. Nó **không phải container được registry tự tạo cho `@JmsListener`**, trừ khi bạn chủ động kết nối chúng bằng cơ chế riêng. Đừng vừa khai báo container thủ công vừa tạo annotation endpoint trùng destination mà không hiểu competing consumers.

## 8. Cấu hình autoStartup: Boot, factory và endpoint

### 8.1. Spring Boot property

~~~properties
spring.jms.listener.auto-startup=false
~~~

Property này áp dụng cho **listener container factory do Boot tự cấu hình**. Bean business vẫn tạo; annotated endpoints vẫn được đăng ký. Nếu ứng dụng có custom factory mà không dùng Boot configurer, phải set chính sách tương ứng trên factory đó.

### 8.2. Custom factory (giữ Boot defaults)

~~~java
// Fragment trong @Configuration; cần import Bean,
// DefaultJmsListenerContainerFactory và ConnectionFactory.
@Bean
DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
        jakarta.jms.ConnectionFactory connectionFactory,
        org.springframework.boot.autoconfigure.jms
                .DefaultJmsListenerContainerFactoryConfigurer configurer) {

    DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();
    configurer.configure(factory, connectionFactory);

    factory.setAutoStartup(false);
    factory.setConcurrency("2-4");
    factory.setSessionTransacted(true);
    return factory;
}
~~~

`DefaultJmsListenerContainerFactoryConfigurer` là helper Spring Boot để cấu hình factory theo properties/defaults của Boot; các setter sau đó tùy biến thêm. Fragment này **thay thế factory mặc định** nếu đặt tên `jmsListenerContainerFactory`; đừng copy vào demo đồng thời với các cấu hình mâu thuẫn mà không hiểu bean selection.

### 8.3. Mỗi endpoint dùng factory riêng

~~~java
@JmsListener(
        id = "priorityListener",
        destination = "orders.priority",
        containerFactory = "priorityJmsListenerContainerFactory")
public void onPriority(String body) {
    // Handler.
}
~~~

`@JmsListener` có thuộc tính `containerFactory` nhưng **không có thuộc tính `autoStartup` riêng được định nghĩa như một field của annotation** trong Spring JMS 6.x. Muốn hai endpoints có auto-start policy khác nhau, dùng hai factories tương ứng hoặc quản lý riêng bằng registry.

Không hiểu `autoStartup=false` là vĩnh viễn vô hiệu hóa listener: gọi `start()` hợp lệ vẫn có thể bắt đầu nhận.

## 9. Readiness: ngăn nhận message quá sớm

Một service có thể cần hoàn tất database migration, nạp cache, lấy credentials, kiểm tra feature flag hoặc thông tin định tuyến trước khi xử lý. Nếu listener auto-start trước khi những bước này xong, message có thể bị fail/retry dù bean business đã được tạo.

Cách có kiểm soát:

1. Đặt listener `autoStartup=false` từ đầu.
2. Để Spring tạo mọi business beans và đăng ký endpoint.
3. Sau context refresh, một startup coordinator kiểm tra tiêu chí ready với timeout.
4. Khi đủ điều kiện, lấy container theo ID và gọi `start()`.
5. Ghi log/metrics thời điểm chuyển trạng thái.
6. Khi điều kiện ready biến mất, đưa hệ thống vào chính sách pause/retry được thỏa thuận; không thay thế broker failure/recovery bằng context refresh vô cớ.

~~~java
// Fragment: registry và readinessService thuộc coordinator đã được inject.
MessageListenerContainer listener =
        registry.getListenerContainer("orderLifecycleListener");

if (listener == null) {
    throw new IllegalStateException("Listener not registered");
}

if (readinessService.isReadyForOrders()) {
    listener.start();
}
~~~

`readinessService.isReadyForOrders()` là **method ứng dụng**, không phải API Spring chuẩn. Khi điều kiện không thỏa, cần hiển thị alert và cơ chế retry/resume của coordinator; không âm thầm để Queue tích backlog vô hạn.

**Lưu ý:** Spring Boot `ApplicationReadyEvent` xuất hiện sau runners, nhưng nếu container auto-start, nó có thể đã nhận message **trước** event. Kubernetes/Actuator readiness dùng để kiểm soát traffic HTTP, không mặc định stop JMS listener; muốn dùng chung business readiness phải cấu hình phối hợp rõ.

## 10. Graceful shutdown: dừng container rồi hủy beans

Khi Spring ApplicationContext đóng bình thường, lifecycle processor dừng các `SmartLifecycle` theo **phase giảm dần**, rồi Spring thực hiện destruction callbacks. Đây là lý do phải tách container stop khỏi business bean destroy.

Timeline mong muốn:

~~~text
10:00:00  Listener nhận message M1, mở JMS transaction.
10:00:02  Ứng dụng nhận tín hiệu shutdown bình thường.
10:00:02  Lifecycle processor yêu cầu listener stop.
10:00:03  Handler M1 hoàn thành và transaction/ack được giải quyết.
10:00:03+ Stop callback báo container dừng.
10:00:04  Spring tiếp tục destruction callbacks của beans.
~~~

Timeline chỉ mang tính **minh họa**. Với provider, prefetch, concurrency và thời gian xử lý khác nhau, stop có thể mất lâu hơn; nếu process bị SIGKILL, `@PreDestroy` có thể không chạy và message có thể được redeliver.

### 10.1. stop(Runnable) cho shutdown có kiểm soát

~~~java
// Fragment có MessageListenerContainer container.
java.util.concurrent.CountDownLatch stopped =
        new java.util.concurrent.CountDownLatch(1);

container.stop(stopped::countDown);

if (!stopped.await(30, java.util.concurrent.TimeUnit.SECONDS)) {
    throw new IllegalStateException("Timed out stopping listener");
}
~~~

Với `DefaultMessageListenerContainer`, Javadoc cho biết callback stop được gọi khi listener processing thực sự dừng. **Không gọi `start()` đồng thời trong lúc đợi stop callback**; callback có thể không bao giờ được gọi nếu một start mới chen vào. Nếu gọi `stop(callback)` nhiều lần trước khi dừng, callback sau có thể thay thế callback trước theo implementation — cần serialize operational commands.

Cấu hình Boot:

~~~properties
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Đây là ngân sách cho một phase shutdown, **không bảo đảm** mọi handler được phép chạy 20 giây chính xác, không bảo đảm DB/JMS commit trong mọi lỗi và không thay thế deadline của Kubernetes.

### 10.2. Bean @PreDestroy nên làm gì?

`@PreDestroy` của business bean hợp lý cho **resource do bean đó sở hữu** (flush buffer, đóng scheduler hoặc file do nó tạo theo cách an toàn). **Đừng đóng JMS Connection/Session/Consumer thuộc quyền listener container** trong `OrderBusinessService.@PreDestroy`; Spring JMS container sẽ quản lý tài nguyên của chính nó.

Ngược lại, container `stop()` không phải lệnh destroy hết business dependencies. Tách ownership tránh double-close, race và callback cố dùng một dependency đã hủy.

## 11. Recovery: broker down không đồng nghĩa bean bị destroy

`DefaultMessageListenerContainer` có cơ chế cố gắng hồi phục khi JMS broker tạm không sẵn sàng. Bean business vẫn sống; container có thể duy trì trạng thái running nhưng chưa có connection/consumer khỏe trong một khoảng retry/backoff.

~~~text
Business bean:         initialized ---------------- initialized
Container lifecycle:   running --------------------- running
Broker availability:   UP ------- DOWN ---- retry --- UP
Message processing:    yes ------ none ------------- yes
~~~

Các quan sát nên tách:

- `registry.getListenerContainer(id)!=null`: endpoint đã được đăng ký.
- `container.isRunning()`: container lifecycle đã start.
- Broker consumer count/connection health: JMS resources hoạt động.
- Queue depth, oldest-message age, DLQ/redelivery: luồng đang tiến triển hay kẹt.
- Last-successful-process timestamp và business error rate: handler thực tế xử lý thành công.

Đừng tự chạy `new OrderBusinessService()` hay `ApplicationContext.refresh()` mỗi lần broker reconnect: đó là nhầm **lifecycle hạ tầng JMS** với **bean lifecycle**.

### 11.1. DefaultMessageListenerContainer và SimpleMessageListenerContainer

| Tiêu chí | DefaultMessageListenerContainer | SimpleMessageListenerContainer |
| --- | --- | --- |
| Nhận message | Chủ động polling/dispatch trong consumer tasks. | Dùng `MessageConsumer.setMessageListener` để provider callback. |
| Scale concurrency | Hỗ trợ điều chỉnh trong khoảng cấu hình. | Số consumer cơ bản cố định. |
| Broker recovery | Có recovery/backoff, cấu hình được. | Đơn giản, thiếu một số khả năng thích ứng/recovery của DMLC. |
| External/JTA transactions | Có thể cấu hình tham gia XA/JTA khi hạ tầng phù hợp. | Không hỗ trợ tương đương các external transaction modes. |
| Vòng đời | `SmartLifecycle` start/stop. | `SmartLifecycle` start/stop. |

Trong nhiều cấu hình Spring Boot, factory mặc định tạo `DefaultMessageListenerContainer`, nhưng nếu ứng dụng tự thay factory, phải kiểm tra implementation thật. Không áp dụng các khẳng định về callback stop/recovery của DMLC cho mọi provider hoặc custom container.

## 12. Transaction và acknowledgment vẫn là trách nhiệm riêng

Dừng container không tự quyết định xử lý message đang in-flight đã thành công hay thất bại. Điều này phụ thuộc JMS Session mode, transaction manager và provider:

- `AUTO_ACKNOWLEDGE` có các giới hạn reliability khi listener ném exception tùy container/provider.
- `CLIENT_ACKNOWLEDGE` có cơ chế xác nhận theo JMS Session; không phải mỗi lần business method in log là message đã ack.
- `sessionTransacted=true` giúp container dùng JMS local transaction, commit/rollback trong phạm vi session khi xử lý thành công/thất bại.
- `JtaTransactionManager` có thể điều phối XA resources khi cấu hình đúng; **không được bật tự động** chỉ vì có `@Transactional`.
- Business `@Transactional` với DB manager **không mặc nhiên** kết hợp DB và JMS thành một giao dịch nguyên tử.

Ví dụ service được gọi qua Spring proxy:

~~~java
@Service
public class PaymentService {

    @Transactional
    public void persistPayment(String eventId, String paymentId) {
        // DB operation và idempotency constraint.
    }
}

@Component
public class PaymentListener {

    private final PaymentService service;

    public PaymentListener(PaymentService service) {
        this.service = service;
    }

    @JmsListener(destination = "payments.events")
    public void handle(String jsonBody) {
        // Parse/validate message và gọi service.persistPayment(...).
    }
}
~~~

Đây là **hai fragments**, không phải các file có thể compile/chạy độc lập: cần package/import, repository logic, transaction manager và broker. Mục đích là tách JMS callback adapter khỏi business transaction proxy. Tránh **self-invocation** làm `@Transactional` không được áp dụng như mong đợi.

Nếu app crash giữa DB commit và JMS ack, message có thể redeliver; business method cần **idempotency** với `eventId`/unique key hoặc inbox pattern. `container.stop()` cũng không có nghĩa đã ack tất cả message sẵn có trong Queue.

## 13. Concurrency: không có một bean mới cho mỗi message

Với `@JmsListener(concurrency = "3-10")` hoặc factory `setConcurrency("3-10")`, container có thể tạo nhiều JMS consumer tasks và gọi **cùng một singleton listener/service** từ nhiều threads.

~~~java
@Service
public class UnsafeStats {

    private int handled;

    public void count() {
        handled++; // Không thread-safe khi nhiều listener threads cùng gọi.
    }
}
~~~

Đây là **phản ví dụ**. Một singleton business bean không tự nhân bản theo số message hoặc consumer threads. Trong production, dùng thread-safe counters/metrics, database transactional writes và tránh shared mutable state không được bảo vệ.

**Quan trọng:** `@PostConstruct` vẫn thường chỉ chạy một lần cho một singleton instance, dù handler được gọi hàng nghìn lần. Lần khởi động lại JMS consumer thread sau broker reconnect cũng không phải lý do gọi lại constructor bean.

Nếu dùng prototype/custom-scoped bean, cần thiết kế scope và injection rõ; Spring JMS không tự cung cấp “một business bean mới cho mỗi message” theo mặc định. Tránh lưu `ThreadLocal` mà không cleanup trong worker pools; tracing/request context có thể rò giữa messages.

## 14. Khi nào cần start/stop và khi nào không?

**Hợp lý:**

- Tạm pause một Queue khi downstream maintenance có kế hoạch.
- Chờ database migration hoặc config chuẩn bị xong trước khi bắt đầu consume.
- Enable/disable một nhóm listeners theo feature flag có giám sát.
- Quản lý graceful shutdown/in-flight processing trong rollout.
- Ngắt một consumer lỗi để điều tra mà không phải hủy business service bean.

**Không hợp lý:**

- Start/stop container cho **mỗi message** (chi phí tạo/đóng resources, rủi ro race).
- Gọi `registry.stop()` chỉ muốn dừng một listener; nó có thể dừng tất cả.
- Tự gọi `@PostConstruct` để “restart bean”, hoặc coi nó là listener start callback.
- Tạo listener container thủ công bên trong business handler mỗi khi gặp lỗi.
- Dùng pause thay cho retry/backoff/idempotency lâu dài.
- Dựa vào stop để bảo đảm Queue không còn message, hoặc Topic non-durable giữ toàn bộ event khi offline.

**Topic cần lưu ý:** với non-durable subscription, việc dừng consumer/subscription có thể khiến các message publish trong thời gian offline không được giữ lại. Durable subscription/retention còn phụ thuộc broker policy. Với Queue, message chưa xử lý thường còn chờ, nhưng vẫn chịu TTL, expiry, DLQ và capacity limits. Đừng áp một kết luận đơn giản cho mọi destination.

## 15. Kiểm thử hai vòng đời

### 15.1. Unit test business bean

Với `OrderBusinessService`:

- Kiểm tra logic xử lý và validation riêng, không cần broker.
- Nếu tự `new` một bean ngoài Spring, `@PostConstruct` **không tự chạy**; callback do Spring quản lý. Có thể tạo test fixture tương ứng hoặc test qua Spring context.
- Đừng mock `JmsListenerEndpointRegistry` chỉ để unit test domain logic thuần.

### 15.2. Integration test có broker

Một bài integration test tốt:

1. Bật `spring.jms.listener.auto-startup=false`.
2. Inject business service + registry; assert service initialized, endpoint tồn tại, container stopped.
3. Send một message vào Queue riêng của test.
4. Kiểm tra handler chưa được gọi khi listener chưa start theo khoảng thời gian có kiểm soát.
5. Start listener; dùng latch/polling với timeout để đợi handler thật.
6. Stop listener bằng `stop(Runnable)` và đợi callback.
7. Assert business bean vẫn là **cùng instance** nếu scope singleton.
8. Restart, gửi message thứ hai; assert không chạy `@PostConstruct` lần hai.
9. Đóng ApplicationContext; assert destroy callback khi shutdown bình thường.
10. Bổ sung test broker disconnect, transaction rollback, in-flight stop và redelivery riêng.

Dùng Queue test **không có competing consumers**; nếu message bị worker khác lấy, test dễ thất thường. Đừng dùng `Thread.sleep(10)` như bằng chứng chắc chắn cho lifecycle ordering.

### 15.3. Assertions nên tách

| Assertion | Chứng minh |
| --- | --- |
| Bean có trong context, init flag true. | Bean initialized. |
| Registry trả container với ID đúng. | Endpoint đã đăng ký. |
| `container.isRunning()==false` trước start. | Container không auto-start trong config test. |
| Handler latch được nhả sau start. | Method handler đã được gọi. |
| Stop callback hoàn thành. | Container dừng theo hợp đồng callback. |
| Bean vẫn initialized sau stop. | Stop container không destroy business bean. |
| `@PreDestroy` khi close context. | Bean destruction khác listener stop. |
| Broker consumer count và log. | Có thông tin bổ sung về JMS connectivity. |

Không trộn “handler đã chạy” và “business commit thành công” vào cùng assertion; transaction phải được verify độc lập.

## 16. Bảng lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `@PostConstruct` chạy nhưng không nhận JMS | Auto-startup false, broker offline, sai Queue, thiếu quyền. | Registry, container isRunning, broker logs. |
| Listener nhận message trước ApplicationRunner | SmartLifecycle auto-start trong context refresh. | Cấu hình autoStartup; dùng ready gate có kiểm soát. |
| `getListenerContainer(id)==null` | ID sai, `@JmsListener` chưa được scan/enable, profile inactive. | Annotation ID, registry IDs, factory config. |
| Stop listener nhưng bean không chạy `@PreDestroy` | Stop chỉ điều khiển container. | Close ApplicationContext nếu muốn destroy bean. |
| Start listener nhưng constructor không chạy lại | Singleton bean đã tồn tại. | Đây là hành vi đúng của Spring bean lifecycle. |
| Container running nhưng broker không có consumer | Broker connectivity/recovery/authorization. | Consumer count, recovery logs, queue depth. |
| Thay Boot property không tác dụng | Custom factory không nhận Boot configurer hoặc endpoint chọn factory khác. | Bean factory name, `containerFactory` trong annotation. |
| Một bean bị race khi xử lý nhiều message | Container concurrency >1, mutable shared fields. | Thread-safety, transaction boundaries. |
| Có duplicate side effect sau restart | Ack/commit JMS không đồng bộ với DB. | Idempotency/outbox/inbox/transactions. |
| Shutdown timeout | Handler lâu, prefetch, receive timeout, resource cleanup. | SmartLifecycle phase, stop callback, logs. |
| `registry.stop()` khiến nhiều Queue ngừng | Đã stop tất cả registry-managed containers. | Điều khiển theo ID, không stop toàn registry. |
| Broker reconnect liên tục tạo bean mới | Code tự refresh context sai lớp trách nhiệm. | Để DMLC recovery, đừng recreate bean. |
| Context đóng nhưng vẫn xử lý message | In-flight/async tasks chưa drain hoặc lifecycle shutdown sai. | Callback stop, task executor, termination deadline. |
| Queue vẫn tăng sau pause | Producers vẫn gửi khi listener dừng. | Backlog, TTL/expiry, producer rate. |
| Topic mất messages khi listener stop | Non-durable subscription semantics. | Chọn durable subscription khi phù hợp. |

## 17. Nguyên tắc thiết kế production

1. **Tách JMS adapter và business service** khi logic phức tạp: listener chỉ parse/validate/dispatch, service nắm domain transaction.
2. **Khởi tạo bean độc lập với JMS reception**: đừng đặt vòng lặp receive hoặc long-blocking broker calls trong `@PostConstruct`.
3. **Cấu hình autoStartup theo yêu cầu readiness**: dùng manual start khi cần điều kiện phụ thuộc đặc biệt.
4. **Dùng ID ổn định cho mỗi endpoint**: quản lý qua registry và giám sát theo destination.
5. **Điều khiển start/stop có RBAC và audit**, tránh public control không được bảo vệ.
6. **Tôn trọng SmartLifecycle phase** trong startup/shutdown; không giả định bean init callbacks thay thế phase ordering.
7. **Xử lý in-flight với timeout** và idempotency; không mong crash luôn gọi `@PreDestroy`.
8. **Không dùng isRunning như health đầy đủ**: cần broker metrics, last success, exception rate và backlog.
9. **Giữ handler thread-safe** khi listener concurrency tăng; business bean singleton không tự được copy.
10. **Test cả paused và running states**, transaction/recovery, concurrency, Topic durable semantics khi áp dụng.

## 18. Câu hỏi ôn tập

1. `@JmsListener` có khiến Spring tạo business bean mới cho từng message? **Không**, container gọi method của bean theo scope hiện tại.
2. Bean initialized có đồng nghĩa listener running? **Không.**
3. `container.stop()` có chạy `@PreDestroy`? **Không**, bean chỉ bị hủy theo ApplicationContext/bean lifecycle.
4. Gọi `container.start()` sau stop có chạy lại `@PostConstruct`? **Không**, nếu singleton bean/context vẫn tồn tại.
5. `JmsListenerEndpointRegistry` quản lý những gì? **Các listener containers của annotation endpoints** và lifecycle chúng.
6. Vì sao không tự động `@Autowired MessageListenerContainer` để lấy endpoint annotated? **Container registry-managed không phải bean độc lập theo mặc định**.
7. `spring.jms.listener.auto-startup=false` ảnh hưởng gì? **Ngăn container tự start, không ngăn bean init/endpoint registration**.
8. `isRunning()==true` có bảo đảm broker reachable? **Không**, DMLC có thể đang recovery.
9. Lifecycle phase start/stop theo thứ tự nào? **Start phase tăng dần; shutdown phase giảm dần**.
10. Listener có thể nhận trước `ApplicationReadyEvent` không? **Có**, nếu auto-startup bật.
11. `stop(Runnable)` có lợi ích gì? **Biết khi listener processing đã dừng theo implementation**, để phối hợp shutdown.
12. Concurrency 5 có nghĩa 5 bản sao business bean? **Không**, thường nhiều thread cùng gọi một singleton.
13. Handler exception có tự destroy Spring bean không? **Không**; nó đi vào transaction/error handling của container.
14. Broker down có phải chạy lại `@PostConstruct`? **Không**; hạ tầng container/recovery chịu trách nhiệm.
15. Pause Queue listener có cấm producer tiếp tục gửi? **Không**; Queue/backlog vẫn chịu broker policies.
16. DB `@Transactional` có tự kết hợp JMS transaction không? **Không**, cần transaction design rõ.
17. Muốn pause riêng payment listener có nên `registry.stop()`? **Không**, dùng `getListenerContainer(id).stop()`.
18. Khi app bị SIGKILL, `@PreDestroy` có bảo đảm chạy? **Không**.
19. Mỗi listener được đăng ký nhưng never started có thể nhận message không? **Không từ chính listener đó**.
20. Mục tiêu của business service với listener container là gì? **Tách “xử lý gì” khỏi “nhận/dispatch khi nào”**.

## 19. Tài liệu chính thức

- [Spring Framework 6.2 — Annotation-driven JMS listener endpoints](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html): annotation, endpoint registration, `@EnableJms`, factory và registry.
- [Spring Framework 6.2 — Using Spring JMS](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html): listener POJO, Simple/Default MessageListenerContainer.
- [Spring Framework — JmsListenerEndpointRegistry API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/config/JmsListenerEndpointRegistry.html): `getListenerContainer`, start, stop, lifecycle.
- [Spring Framework — @JmsListener API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/annotation/JmsListener.html): `id`, `destination`, `containerFactory`, concurrency.
- [Spring Framework — DefaultMessageListenerContainer API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html): recovery và `stop(Runnable)`.
- [Spring Framework — SmartLifecycle API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/SmartLifecycle.html): phase, auto-startup, callback stop.
- [Spring Boot 3.5 — JMS/Artemis](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html): JMS integration/embedded Artemis.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): `spring.jms.listener.auto-startup` và related settings.
- [Spring Boot 3.5 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.5/reference/web/graceful-shutdown.html): `spring.lifecycle.timeout-per-shutdown-phase`.
- [Spring Boot 3.5 — DefaultJmsListenerContainerFactoryConfigurer API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/jms/DefaultJmsListenerContainerFactoryConfigurer.html): custom factory giữ Boot defaults.

**Ghi nhớ:** Spring bean nghiệp vụ trải qua **create → inject → initialize (`@PostConstruct`) → serve → destroy (`@PreDestroy`)**; listener container trải qua **register/init → start → receive/dispatch → stop/restart → destroy**. Hai vòng đời phối hợp qua Spring context nhưng không phải cùng một đối tượng. Hãy dùng `JmsListenerEndpointRegistry` để điều khiển container theo ID, `SmartLifecycle`/autoStartup/phase để điều phối, và transaction/idempotency/monitoring cho phần reliability.
