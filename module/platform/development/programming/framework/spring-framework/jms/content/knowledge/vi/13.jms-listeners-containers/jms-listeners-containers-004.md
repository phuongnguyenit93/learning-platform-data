# Container quản lý consumer, luồng và tài nguyên trong Spring JMS

**Chủ đề cha:** Listener và container — Spring Framework / JMS.

**Mục tiêu:** Khi nhìn thấy `@JmsListener`, giải thích được **ai tạo `MessageConsumer`, ai giữ `Session` và `Connection`, thread nào gọi xử lý message, ai chịu trách nhiệm khởi động/dừng/phục hồi**, cũng như tác động của concurrency, cache, transaction và broker failure. Bài tập trung vào **JMS Message Listener Container** của Spring, không đánh đồng với container servlet, Docker/Kubernetes hay message broker.

**Môi trường:** Java 17+, Spring Framework 6.x / Spring Boot 3.x, Jakarta Messaging (`jakarta.jms`); ví dụ kết nối Apache ActiveMQ Artemis broker bên ngoài. Các mặc định được ghi rõ phạm vi phiên bản và có thể đổi khi nâng Spring/provider. Đặc biệt, **container quản lý tài nguyên cho một listener không có nghĩa broker và business DB được Spring tự tạo**.

## 1. Mô hình tổng quát: @JmsListener chỉ là đầu vào cấu hình

`@JmsListener` thường được đặt trên một **Spring-managed bean**. Nó không tự là một thread hay một consumer. Khi Spring xử lý annotation, hệ thống endpoint tạo một **listener container** thông qua `JmsListenerContainerFactory`. Container mới chịu trách nhiệm vận hành consumer.

~~~text
                          Spring ApplicationContext
                                   │
                   phát hiện @JmsListener trên bean
                                   │
                                   ▼
                   JmsListenerEndpointRegistry
                                   │
                                   ▼
                   JmsListenerContainerFactory
                                   │ tạo / cấu hình
                                   ▼
                     MessageListenerContainer
                           │       │       │
                           │       │       └── lifecycle: start/stop/recover
                           │       └────────── TaskExecutor / consumer threads
                           └────────────────── JMS resources
                                                 │
                   ┌─────────────────────────────┼──────────────────────┐
                   ▼                             ▼                      ▼
           JMS Connection                 JMS Session            MessageConsumer
                   │                             │                      │
                   └─────────────────────────────┴──────────────────────┘
                                                 │
                                                 ▼
                                         JMS broker / queue
                                                 │
                                                 ▼
                                 @JmsListener method trong Spring bean
~~~

**Phân biệt cấp sở hữu:**

- **JMS provider/broker:** thực sự lưu, định tuyến và giao message; có quyền quyết định prefetch/credit, expiry, DLQ, redelivery, ACL và HA theo cấu hình.
- **Spring ConnectionFactory bean:** cung cấp khả năng mở JMS `Connection`; chính factory không nhất thiết mở kết nối khi Spring khởi động.
- **Listener container:** chủ động tạo/giữ/đóng connection, session và consumer theo chính sách, chạy vòng nhận và điều phối callback, quản lý recovery.
- **Spring listener bean:** chứa logic nghiệp vụ, converter/validator và transaction DB cần thiết; **không** nên tự đóng tài nguyên JMS mà container đang dùng.

Không cần ứng dụng tự gọi `new MessageConsumer(...)` hoặc `new Thread(...)` cho từng message chỉ để dùng `@JmsListener`. Lợi ích của container là **quyền sở hữu tài nguyên được tập trung và lifecycle nhất quán**.

## 2. Tại sao cần container thay vì tự viết một vòng receive?

Một worker viết tay ở tầng JMS có thể trông đơn giản:

~~~java
while (running) {
    Message m = consumer.receive(1_000L);
    if (m != null) {
        process(m);
    }
}
~~~

Nhưng ứng dụng phải quyết định: ai tạo `Connection`/`Session`/`MessageConsumer`, ai gọi `connection.start()`, làm sao phản ứng với broker restart, dừng thread không leak, rollback khi listener ném lỗi, tăng số consumer, đo lag và quản lý shutdown. Nếu có mười queue hoặc nhiều replica, độ phức tạp nhân lên nhanh.

`DefaultMessageListenerContainer` của Spring cung cấp một **vòng receive do framework quản lý**. Nó lấy JMS resources từ factory, lập consumer tasks, gọi listener, xử lý acknowledgment/transaction theo cấu hình và cố gắng phục hồi khi broker mất kết nối. Ứng dụng vẫn chịu trách nhiệm **business retry/idempotency và hạ tầng broker**, nhưng không phải tự lắp vòng life cycle.

**Giới hạn:** container không hứa message được xử lý “exactly once” ở DB, không vô hiệu hóa luật session threading của JMS, không tự quản lý SQL transaction của mọi dependency, không tạo một worker vô hạn không tốn tài nguyên.

## 3. Ba cấp tài nguyên JMS: Connection, Session, MessageConsumer

| Resource | Chức năng | Mối quan hệ với container |
| --- | --- | --- |
| `ConnectionFactory` | Factory/provider client để mở connection | Container được inject; có thể là native factory, cached wrapper hoặc pool tùy cấu hình |
| `Connection` | Kênh logic tới broker, có thể hỗ trợ nhiều session | Container mở/quản lý kết nối, start/stop/re-establish; **không bắt buộc mỗi consumer một physical connection** |
| `Session` | Ngữ cảnh làm việc JMS, tạo consumer và điều khiển local JMS transaction/ack | Mỗi consumer/invoker thường sử dụng session riêng; **không chia sẻ một session giữa các thread đồng thời** |
| `MessageConsumer` | Subscription/consumer cụ thể ở một queue/topic/selector | Container tạo, giữ hoặc tạo lại tùy cache level và recovery |
| `TaskExecutor` | Hạ tầng thực thi các consumer invoker tasks | Lập lịch và chạy những tác vụ có thể chờ lâu ở `receive()` |
| `@JmsListener` bean | Hàm xử lý nghiệp vụ | Được gọi khi container giao một message; method có thể chạy đồng thời nếu cấu hình nhiều consumer |

Một `Connection` có thể được chia sẻ giữa nhiều `Session`, nhưng một `Session` classic JMS tuân theo mô hình **single-threaded context**. Container thường cung cấp một session cho **một consumer task đang xử lý tại một thời điểm**. Đừng nhầm thứ tự:

~~~text
1 Connection  ──► nhiều Sessions
Session A     ──► consumer A ──► listener invocation trên worker A
Session B     ──► consumer B ──► listener invocation trên worker B
Session C     ──► consumer C ──► listener invocation trên worker C
~~~

Số **listener methods**, **concurrent consumers**, **JMS sessions**, **physical connections** và **OS threads** là các đại lượng **khác nhau**. Thông thường mỗi consumer task dùng một session/consumer, nhưng provider pooling và cache level có thể làm thay đổi số resources nhìn thấy trong broker console.

## 4. Hai listener container chuẩn của Spring

Spring JMS cung cấp hai triển khai phổ biến:

| Đặc điểm | `SimpleMessageListenerContainer` | `DefaultMessageListenerContainer` |
| --- | --- | --- |
| Cách nhận | Đăng ký callback bằng `MessageConsumer.setMessageListener(...)` | Chạy vòng `MessageConsumer.receive(...)` trong consumer invoker tasks |
| Số consumers | Tạo số cố định khi startup | Có core consumers và có thể tăng tới max theo tải |
| Listener callbacks | JMS provider điều phối callback | Spring `TaskExecutor` chạy invoker và gọi listener |
| Recovery/lifecycle | Cơ chế đơn giản hơn, phụ thuộc provider nhiều hơn | Có logic tự phục hồi, stop/restart và thay đổi cấu hình runtime |
| Local JMS transaction | Có thể bật `sessionTransacted=true` | Có thể bật `sessionTransacted=true` |
| External/JTA transaction manager | Không hỗ trợ participation như Default | Hỗ trợ cấu hình `PlatformTransactionManager` phù hợp |
| Khả năng thay đổi concurrency | Cố định về cơ bản | Có cấu hình core/max và dynamic scaling |
| Khi nên cân nhắc | Tích hợp JMS đơn giản, điều kiện provider cụ thể | Thường là lựa chọn mặc định cho Spring workloads cần recovery và kiểm soát resources |

**Đừng hiểu chữ “Simple” là ít thread nên hiệu năng chắc chắn tốt hơn.** `SimpleMessageListenerContainer` để JMS provider thực thi callback; nó không đồng nghĩa mọi listener chạy trên thread gọi cấu hình. Ngược lại, `DefaultMessageListenerContainer` mặc dù dùng vòng synchronous `receive` bên trong vẫn **asynchronous đối với code publisher và HTTP threads**, vì container thực thi invoker tasks riêng.

Với `@JmsListener` được tạo từ `DefaultJmsListenerContainerFactory`, runtime container thường là `DefaultMessageListenerContainer`. Những ứng dụng tự viết factory riêng có thể chọn triển khai khác; phải xác định **class thực tại runtime** khi chẩn đoán.

## 5. Vòng đời của một container: từ ApplicationContext tới shutdown

Một chu trình cơ bản của `DefaultMessageListenerContainer`:

~~~text
[Configuration / bean definitions]
           │
           ▼
[@EnableJms hoặc Boot auto-config tạo annotation infrastructure]
           │
           ▼
[Endpoint được đăng ký; factory tạo listener container]
           │
           ▼
[Context refresh / autoStartup]
           │
           ▼
[Container start]
  ├─ lấy ConnectionFactory
  ├─ thiết lập shared/dedicated connection theo cache policy
  ├─ lên lịch consumer invoker tasks
  ├─ tạo Session + MessageConsumer cho invoker
  ├─ nhận message và dispatch tới listener
  └─ lặp receive, transaction/ACK theo cấu hình
           │
           ├── broker error → recovery/backoff → tạo lại resources
           │
           ├── stop → dừng nhận mới theo lifecycle, xử lý in-flight
           │
           └── context close / destroy → đóng consumer/session/connection,
                                         dừng worker tasks phù hợp
~~~

**Không giả định `@Bean` được tạo là broker đã kết nối.** Connection setup có thể diễn ra bất đồng bộ. Container có thể đang `isRunning()==true` nhưng không có consumer thực sự connected do broker down hoặc đang recovery. Phải kết hợp trạng thái runtime, log recovery và broker-side consumer count.

Spring listener containers triển khai lifecycle integration, thường thuộc `SmartLifecycle`. `autoStartup` quyết định có start khi context khởi động; `phase` giúp điều phối thứ tự start/stop tương đối giữa các lifecycle beans. Khi shutdown, phải xét message đang xử lý và deadline tổng của orchestrator, không chỉ nhìn dòng “container stop called”.

## 6. @JmsListener + JmsListenerContainerFactory: một annotation tạo ra những gì?

Spring Framework thuần có thể bật annotation support và khai báo factory:

~~~java
package example.listener;

import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
@EnableJms
public class ListenerConfiguration {

    @Bean
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(false); // queue
        factory.setSessionTransacted(true);
        factory.setConcurrency("2-4");
        factory.setReceiveTimeout(1_000L);
        factory.setRecoveryInterval(5_000L);
        return factory;
    }
}
~~~

Đây là **một class Java 17 biên dịch được** trong ứng dụng Spring Framework 6.x có `jakarta.jms.ConnectionFactory` bean/provider, `spring-jms` và cấu hình container. Class **không có `main`**: để chạy phải khởi tạo ApplicationContext/scan và có broker. `@EnableJms` đăng ký cơ chế phát hiện `@JmsListener`. Factory tên `jmsListenerContainerFactory` là tên mặc định mà annotation infrastructure sẽ tìm khi endpoint không chỉ rõ factory.

Ý nghĩa của từng dòng:

- `setConnectionFactory`: chọn provider và hạ tầng kết nối.
- `setPubSubDomain(false)`: tên destination được hiểu theo queue; với topic cần chính sách riêng.
- `setSessionTransacted(true)`: mỗi listener invocation dùng local JMS transaction (nếu provider hỗ trợ); handler exception phù hợp dẫn tới rollback/redelivery.
- `setConcurrency("2-4")`: duy trì số consumer core và có thể scale tới max theo tải, **không tạo một shared session đồng thời cho bốn threads**.
- `setReceiveTimeout(1_000L)`: mỗi lần invoker receive có cửa sổ chờ khoảng một giây; **đây không phải SLA xử lý nghiệp vụ**.
- `setRecoveryInterval(5_000L)`: khoảng chờ giữa các lần recovery connection theo cấu hình; **không phải thời gian retry một poison message**.

Nếu dùng **Spring Boot 3.x** với JMS starter, thường không cần tự khai báo toàn bộ class trên: Boot tạo `ConnectionFactory`, template và default listener factory theo điều kiện. Tuy nhiên, khi ứng dụng tự tạo một bean `jmsListenerContainerFactory`, bạn có thể **thay thế phần cấu hình mặc định** của Boot; transaction, converter, destination resolver và caching semantics phải được giữ rõ ràng.

## 7. Bean nghiệp vụ không phải nơi tạo consumer

Ví dụ listener trong một Spring-managed component:

~~~java
package example.listener;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class InvoiceWorker {

    @JmsListener(destination = "invoice.commands")
    public void onMessage(String content) {
        System.out.println("Thread=" + Thread.currentThread().getName()
                + " payload=" + content);
    }
}
~~~

Ở đây, `InvoiceWorker` chỉ chứa handler. Annotation không tự gọi `connection.createSession`. Spring tạo endpoint container, container thiết lập consumer tương ứng, nhận message và gọi `onMessage` từ worker thread đã chọn.

**Các điều kiện phải đủ:**
1. `InvoiceWorker` phải thực sự là Spring bean (được component scan hoặc `@Bean`); một instance tạo bởi `new InvoiceWorker()` bên ngoài Spring sẽ không được Spring listener infrastructure đăng ký.
2. Annotation support đã bật: `@EnableJms` trong Spring thuần, hoặc Boot đã auto-configure phần này.
3. Có `JmsListenerContainerFactory` thích hợp và `ConnectionFactory` trỏ đúng broker.
4. Queue `invoice.commands` tồn tại hoặc broker cho phép provisioning theo chính sách; credential có quyền consume.
5. Listener container đang chạy, đã kết nối broker, có message routing đúng.

Method `onMessage(String)` trong ví dụ chỉ chạy khi có message được chuyển thành String phù hợp; `MessageConverter` và listener adapter quyết định conversion. Nếu message là binary/JSON POJO mà converter không hiểu, listener có thể lỗi **trước hoặc trong dispatch**.

## 8. Spring Boot 3.x: ví dụ chạy được, quan sát thread và consumer count

Ví dụ này dùng **Java 17**, **Spring Boot 3.5.0** (một release có thật, không khẳng định là bản mới nhất) và Artemis broker **chạy bên ngoài ứng dụng**. Mục tiêu là chứng minh container được tự tạo, có endpoint ID để quản lý và listener chạy trên threads riêng.

### 8.1. Tệp build.gradle

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
rootProject.name = 'jms-container-resources'
~~~

### 8.2. Tệp application.yaml

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
      min-concurrency: 2
      max-concurrency: 4
      receive-timeout: 1s
~~~

Đặt password qua `SPRING_ARTEMIS_PASSWORD` hoặc secret store, không commit password trong Git. Broker phải có endpoint, user và queue `demo.listener.jobs` được tạo hoặc cho phép auto-create. Các giá trị `spring.jms.listener.*` điều khiển factory được Boot auto-configure khi điều kiện phù hợp; nếu tự tạo một factory khác không dùng Boot configurer, properties này **không tự chắc chắn được áp dụng**.

### 8.3. Java đầy đủ trong một tệp

`src/main/java/example/jmscontainer/ContainerResourcesApplication.java`:

~~~java
package example.jmscontainer;

import java.util.UUID;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.listener.DefaultMessageListenerContainer;
import org.springframework.jms.listener.MessageListenerContainer;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class ContainerResourcesApplication {

    public static void main(String[] args) {
        SpringApplication.run(ContainerResourcesApplication.class, args);
    }

    @Bean
    ApplicationRunner publishAndInspect(
            JmsTemplate jmsTemplate,
            JmsListenerEndpointRegistry registry) {

        return args -> {
            MessageListenerContainer container =
                    registry.getListenerContainer("demoJobsListener");

            if (container == null) {
                throw new IllegalStateException(
                        "Listener endpoint not registered");
            }

            System.out.println("LISTENER_RUNNING=" + container.isRunning());

            if (container instanceof DefaultMessageListenerContainer dmlc) {
                System.out.println("SCHEDULED_CONSUMERS="
                        + dmlc.getScheduledConsumerCount());
                System.out.println("ACTIVE_CONSUMERS="
                        + dmlc.getActiveConsumerCount());
            }

            for (int i = 1; i <= 4; i++) {
                String eventId = UUID.randomUUID().toString();
                String body = "job-" + i;

                jmsTemplate.convertAndSend(
                        "demo.listener.jobs",
                        body,
                        message -> {
                            message.setStringProperty("eventId", eventId);
                            return message;
                        });
            }
            System.out.println("PUBLISHER_SENT_FOUR_MESSAGES");
        };
    }
}

@Component
class JobsListener {

    @JmsListener(
            id = "demoJobsListener",
            destination = "demo.listener.jobs")
    public void onMessage(Message message) throws JMSException {

        String eventId = message.getStringProperty("eventId");
        String body = message instanceof TextMessage text
                ? text.getText() : "<non-text-message>";

        System.out.println(
                "CONSUMED thread=" + Thread.currentThread().getName()
                        + " eventId=" + eventId
                        + " body=" + body);
    }
}
~~~

**Tại sao ví dụ chạy được:** `spring-boot-starter-artemis` đem Spring JMS và Artemis Jakarta client phù hợp; Boot khi có hạ tầng JMS sẽ tự tạo `ConnectionFactory`, `JmsTemplate`, default `JmsListenerContainerFactory` và phát hiện `@JmsListener`. `@Component` đăng ký listener; `@JmsListener(id=...)` đặt ID để registry tra cứu. `ApplicationRunner` được gọi trong quá trình startup sau khi ApplicationContext được refresh. Consumer threads và publisher không phải cùng một method call stack.

### 8.4. Chạy và quan sát

Với Gradle wrapper và broker test hoạt động:

~~~bash
./gradlew bootRun
~~~

Các dòng dưới đây chỉ là **một tập hợp log có thể xuất hiện**, không phải stdout cố định:

~~~text
LISTENER_RUNNING=true
SCHEDULED_CONSUMERS=2
ACTIVE_CONSUMERS=2
PUBLISHER_SENT_FOUR_MESSAGES
CONSUMED thread=DefaultMessageListenerContainer-... eventId=... body=job-1
CONSUMED thread=DefaultMessageListenerContainer-... eventId=... body=job-2
CONSUMED thread=DefaultMessageListenerContainer-... eventId=... body=job-3
CONSUMED thread=DefaultMessageListenerContainer-... eventId=... body=job-4
~~~

**Không cam kết các con số hoặc thứ tự:** container khởi động và kết nối bất đồng bộ; scheduled/active counts có thể khác ở đúng thời điểm đọc. Hai consumers core không đồng nghĩa mỗi message một thread mới; thread có thể được tái sử dụng. Trong queue nhiều consumer, `job-2` có thể được xử lý trước `job-1`. Listener có thể nhận trong khi publisher vẫn đang gửi, nên log `CONSUMED` có thể xuất hiện **trước** `PUBLISHER_SENT_FOUR_MESSAGES`. Nếu broker không kết nối, mất quyền, thiếu queue hoặc nhận lỗi, ví dụ có thể không có log consume và cần xem log provider.

**Không phải ví dụ lưu trạng thái nghiệp vụ:** handler chỉ log; không có DB commit, idempotency, retry business hoặc DLQ tests. Mỗi lần restart, runner gửi thêm bốn message với ID mới. Không dùng startup runner để publish event nghiệp vụ thật khi chưa có transaction/outbox.

## 9. Tại sao factory và container là hai đối tượng khác nhau?

Một `DefaultJmsListenerContainerFactory` là **bản thiết kế cấu hình** để tạo ra các `DefaultMessageListenerContainer`. Nó **không** có nghĩa chỉ có một consumer trên toàn ứng dụng.

Giả sử có hai method:

~~~java
@JmsListener(id = "billing", destination = "billing.queue")
public void bill(String body) {
    handleBilling(body);
}

@JmsListener(id = "shipping", destination = "shipping.queue")
public void ship(String body) {
    handleShipping(body);
}
~~~

Đây là **snippets**, với `handleBilling` và `handleShipping` là nghiệp vụ do ứng dụng định nghĩa. Mỗi endpoint được factory tạo **container riêng**. Hai containers cùng sử dụng cấu hình nền của factory nhưng có resources/lifecycle và destination riêng.

~~~text
DefaultJmsListenerContainerFactory
          │
          ├──► billing container  ──► Sessions/Consumers ở billing.queue
          │
          └──► shipping container ──► Sessions/Consumers ở shipping.queue
~~~

Nếu cấu hình `concurrency=3-5` cho **mỗi container**, và có ba endpoints, về lý thuyết có thể có tới 15 consumer tasks, không phải tổng 5 cho toàn ứng dụng. Kế hoạch capacity phải tính **số endpoints × consumers mỗi endpoint × số replicas**, cộng giới hạn broker, session, DB connection pool và downstream API. Đây là lý do không thể chỉ nhìn giá trị `max-concurrency` mà kết luận hệ thống an toàn.

## 10. Concurrency trong DefaultMessageListenerContainer

Hai tham số quan trọng:

- `concurrentConsumers`: số consumer invokers cơ bản/container giữ (mặc định là 1).
- `maxConcurrentConsumers`: giới hạn trên (mặc định 1). Chỉ khi max cao hơn core container mới có thể **scale up/down** trong khoảng đó.

Có thể cấu hình bằng chuỗi:

~~~java
factory.setConcurrency("2-5");
~~~

hoặc bằng Boot properties:

~~~yaml
spring:
  jms:
    listener:
      min-concurrency: 2
      max-concurrency: 5
~~~

Ý nghĩa thực tế: container duy trì core 2 consumers, và **có thể** tạo đến 5 invokers nếu nhận thấy tải phù hợp. Không có bảo đảm sẽ luôn đạt max chỉ vì queue depth tăng: broker credit/prefetch, task executor saturation, CPU, DB và các giới hạn khác đều tác động.

**Với queue**, tăng concurrency có thể giúp throughput, nhưng thông thường **không còn thứ tự xử lý tuyệt đối** vì các consumer chạy song song. Với **topic dạng subscription thông thường**, không tùy ý tăng consumer count: bạn có thể tạo nhiều subscriptions nhận cùng một event, dẫn tới xử lý trùng theo thiết kế pub/sub. Muốn parallel processing trên topic, cần nghiên cứu shared/durable subscription hỗ trợ bởi JMS 2.0+/provider.

### 10.1. Thread và message không phải ánh xạ một-một

~~~text
Consumer invoker A (thread A)
    receive M1 → handle M1 → receive M3 → handle M3 → ...

Consumer invoker B (thread B)
    receive M2 → handle M2 → receive M4 → handle M4 → ...
~~~

Một thread có thể xử lý **nhiều message nối tiếp**; nếu handler mất 5 giây, consumer đó có thể không nhận message tiếp theo trong khi đang chạy code xử lý. Tăng concurrency không làm một single message tự phân chia thành nhiều phần xử lý song song.

### 10.2. Số scheduled không phải số active

`DefaultMessageListenerContainer` có thể cung cấp:

~~~java
int scheduled = container.getScheduledConsumerCount();
int active = container.getActiveConsumerCount();
int min = container.getConcurrentConsumers();
int max = container.getMaxConcurrentConsumers();
~~~

Snippet này giả định `container` là `DefaultMessageListenerContainer`. Scheduled là số tasks đã được lên lịch; active là số đang hoạt động theo định nghĩa container, và chúng có thể khác nhau. **Đừng coi active là số message đang được xử lý tại đúng thời điểm**; một active invoker có thể đang chờ `receive(timeout)`. Cần thêm số in-flight ở broker và handler metrics.

### 10.3. Bẫy khi chọn max quá lớn

Nếu có 8 replicas, 4 endpoints và `maxConcurrency=10`, trần dự kiến có thể là **320 consumer invoker tasks** (8 × 4 × 10) nếu mọi endpoint cấu hình như vậy. Broker, JVM, DB pool và external APIs có thể không chịu nổi. Đây là số tính theo **cấu hình capacity giả định**, không phải con số broker đang có.

Khi mở rộng, dùng load test, giới hạn downstream concurrency, queue depth/age, p95/p99 processing latency và mức sử dụng connection pool để chọn core/max. Đừng chỉ tăng số consumer vì thấy backlog.

## 11. TaskExecutor: ai sở hữu thread nhận message?

Với `DefaultMessageListenerContainer`, Spring lên lịch các invoker thông qua `TaskExecutor`. Nếu không cung cấp executor riêng, container tạo executor mặc định (trong Spring 6.x thường là `SimpleAsyncTaskExecutor`) để chạy các tasks theo `concurrentConsumers`/max. Những tasks có thể tồn tại lâu để lặp `receive`.

~~~text
TaskExecutor
 ├─ invoker #1  ──► session #1 + consumer #1 ──► listener handler
 ├─ invoker #2  ──► session #2 + consumer #2 ──► listener handler
 └─ invoker #3  ──► session #3 + consumer #3 ──► listener handler
~~~

**Nếu dùng thread pool tùy chỉnh**, nhớ rằng consumer invokers **có thể giữ threads trong thời gian dài**, không giống một HTTP task xử lý vài mili-giây rồi nhả slot. Một pool có 4 threads được chia cho 5 listener containers có thể gây **starvation**: tasks mới không có thread chạy, dù JVM còn CPU. Khi pool báo full, inspect cả số invokers đang giữ threads lẫn các tasks đang chờ trong executor queue.

### 11.1. Không tự tạo new Thread trong @JmsListener để “tăng tốc”

~~~java
@JmsListener(destination = "jobs.queue")
public void onMessage(String payload) {
    new Thread(() -> doWork(payload)).start();
}
~~~

Đây là **anti-pattern minh họa**, `doWork` là business code giả định. Listener trả về trước khi background thread hoàn tất. Nếu container đang transacted, JMS transaction có thể **commit ngay sau khi method return**, còn business thread bên ngoài thất bại thì broker không tự redeliver message. Thread mới cũng không tự kế thừa transaction/thread context mà Spring quản lý.

Nếu thật sự cần phân tách công việc, hãy có một cơ chế **handoff bền vững** và outcome protocol rõ ràng, hoặc sử dụng một thiết kế listener phù hợp. Đừng biến method return thành ACK sớm chỉ vì khởi chạy một task bất đồng bộ.

### 11.2. Java 21 virtual threads là tùy chọn riêng

Một số phiên bản Spring Framework 6.2+ hỗ trợ cấu hình virtual threads trong `DefaultMessageListenerContainer` (Java 21+). Bài này dùng Java 17, nên không bật tùy chọn đó. Dù virtual threads giảm chi phí chờ ở JVM, JMS sessions/consumers, broker quota, downstream DB connections vẫn là **tài nguyên hữu hạn**; không có phép nhân throughput miễn phí.

## 12. Container cache khác với ConnectionFactory cache và pool

Dễ nhầm giữa ba lớp tài nguyên:

1. **Cache của chính `DefaultMessageListenerContainer`:** giữ `Connection`, `Session`, `MessageConsumer` giữa các vòng receive theo `cacheLevel`; có thể tạo lại khi lỗi.
2. **`CachingConnectionFactory` của Spring:** wrapper của provider factory, có thể cache connection/session/producer/consumer; thường có ích với `JmsTemplate` gửi nhiều request ngắn.
3. **JMS connection pool** (ví dụ `pooled-jms`): có thể quản lý nhiều physical connections, max connections, borrowing và resource limits; không tương đương một session cache.

Một bảng chi tiết về `cacheLevel` của `DefaultMessageListenerContainer`:

| Mức | Giữ lại resources giữa các vòng nhận | Khi nào cân nhắc |
| --- | --- | --- |
| `CACHE_NONE` | Không cố giữ các JMS handles | Tương thích với một số container/JTA providers cần lấy resources mới khi transaction bắt đầu |
| `CACHE_CONNECTION` | Giữ connection, lấy lại session/consumer khi cần | Khi cần giảm chi phí connection nhưng không cache hết |
| `CACHE_SESSION` | Giữ connection + session, lấy lại consumer | Khi consumer không nên được cache quá lâu |
| `CACHE_CONSUMER` | Giữ connection + session + consumer | Môi trường JMS native dùng local transactions; ít overhead per receive |
| `CACHE_AUTO` | Chọn theo transaction management strategy | Default; **không** có nghĩa mãi mãi một mức cố định |

Trong môi trường thông thường **không có external transaction manager**, `CACHE_AUTO` hiệu quả tương đương `CACHE_CONSUMER`. Khi cấu hình external transaction manager, default có thể dùng `CACHE_NONE` để các resources mới được enlist đúng vào JTA/XA transaction. Thay cache level mà không hiểu XA enlistment có thể làm transaction **không bao trùm đúng JMS receive**.

### 12.1. Vì sao Boot tránh đưa caching wrapper trực tiếp cho listener?

Spring Boot 3.x thường bọc native JMS `ConnectionFactory` bằng `CachingConnectionFactory` cho đường `JmsTemplate`. Nhưng listener container thường nên dùng **native ConnectionFactory** để quản lý recovery/connection/session của chính nó. Auto-configuration của Boot có cơ chế `ConnectionFactoryUnwrapper.unwrapCaching(...)` để lấy native factory từ wrapper mà Boot đã tạo (khi phù hợp).

**Cảnh báo:** cơ chế unwrap của Boot chỉ nhận diện một số wrapper cụ thể; nếu bạn tự lồng nhiều lớp custom proxy/pool, đừng giả định container luôn tự lấy được native factory. Kiểm tra runtime bean graph.

### 12.2. Khi tự tạo factory trong Boot, nên kế thừa configurer

Snippet Boot 3.5.x:

~~~java
@Configuration(proxyBeanMethods = false)
class CustomJmsContainers {

    @Bean
    DefaultJmsListenerContainerFactory priorityJobsFactory(
            DefaultJmsListenerContainerFactoryConfigurer configurer,
            ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        configurer.configure(
                factory,
                ConnectionFactoryUnwrapper.unwrapCaching(connectionFactory));

        // Chỉ override phần cần khác default của Boot.
        factory.setConcurrency("2-4");
        factory.setSessionTransacted(true);
        return factory;
    }
}
~~~

Imports:
- `jakarta.jms.ConnectionFactory`.
- `org.springframework.context.annotation.Configuration` và `Bean`.
- `org.springframework.jms.config.DefaultJmsListenerContainerFactory`.
- `org.springframework.boot.autoconfigure.jms.DefaultJmsListenerContainerFactoryConfigurer`.
- `org.springframework.boot.jms.ConnectionFactoryUnwrapper`.

Snippet cần được đặt trong ứng dụng Spring Boot 3.5.x có provider client; nó **không** phải chương trình chạy độc lập. Với bean tên `priorityJobsFactory`, dùng:

~~~java
@JmsListener(
        destination = "priority.jobs",
        containerFactory = "priorityJobsFactory")
public void handlePriorityJob(String body) {
    processPriority(body);
}
~~~

`processPriority` là nghiệp vụ tự triển khai. Factory **tên riêng** không tự thay default factory cho mọi endpoint; `containerFactory` trong annotation chọn đúng bean. Dùng `DefaultJmsListenerContainerFactoryConfigurer` giúp giữ các lựa chọn cấu hình Boot đang áp dụng, tránh vô tình mất transaction/message converter/destination resolver khi tạo factory mới.

## 13. Recovery và reconnect: container phục hồi cái gì?

Khi broker ngắt kết nối, `DefaultMessageListenerContainer` có logic phục hồi: nhận exception, chờ interval/backoff, tạo/đăng ký lại JMS resources theo cấu hình rồi tiếp tục receive. Ở Spring Framework 6.x, `DEFAULT_RECOVERY_INTERVAL` là **5.000 ms** nếu không tùy biến.

~~~text
RUNNING / receiving
     │
     ▼
Broker network outage
     │
     ▼
receive / setup failure
     │
     ▼
Container recovering
  ├─ đóng/refresh stale resources
  ├─ chờ recoveryInterval hoặc BackOff
  └─ thử lại connection / destination / consumer
     ├─ thành công → RUNNING / receiving
     └─ thất bại  → tiếp tục theo backoff policy
~~~

**Recovery của connection không phải retry nghiệp vụ.** Broker có thể đã giao message rồi consumer chết trước JMS commit; sau reconnect, message có thể được redeliver theo provider policy. Container không tự tạo unique index hay idempotency key trong database.

**Không nhầm hai loại chờ:**
- `receiveTimeout`: thời gian một vòng invoker chờ **message**.
- `recoveryInterval` / `BackOff`: thời gian chờ **trước lần thử khôi phục connection/resources tiếp theo**.

Cấu hình phù hợp nên dựa trên SLA, broker failover và tải. Recovery interval quá thấp trên hàng trăm replicas có thể gây **thundering herd** khi broker vừa quay lại. Dùng backoff/jitter hoặc cơ chế hỗ trợ của provider phù hợp; không retry nóng vô hạn.

### 13.1. Có thể kiểm tra container đang recovery không?

~~~java
if (container instanceof DefaultMessageListenerContainer dmlc) {
    System.out.println("recovering=" + dmlc.isRecovering());
}
~~~

Snippet này giả định `container` loại `MessageListenerContainer` lấy từ registry. `isRecovering()` là một chỉ báo hữu ích, nhưng cần kết hợp với metrics broker-side connections, consumer count, queue age và logs; không dùng một boolean làm toàn bộ health check.

### 13.2. Lỗi ở handler khác với lỗi ở transport

| Tình huống | Bên chịu trách nhiệm chính |
| --- | --- |
| Broker refused connection / auth fail | Provider/config + container recovery |
| Network mất giữa receive và commit | JMS transaction/rollback + broker redelivery policy |
| JSON converter không đọc được payload | Consumer contract, error classification, DLQ |
| Handler ném exception vì DB timeout | Business retry policy, JMS rollback/delivery |
| Handler ghi DB xong nhưng JMS commit fail | Consumer idempotency + reconciliation |
| Message bị TTL expiry | Broker expiry policy, application outcome monitoring |

Một `ErrorHandler` trên listener container có thể nhận thông báo exception; nó **không thay thế** transaction rollback, DLQ routing hoặc retry logic. Khi xử lý exception trong handler, tránh nuốt lỗi rồi return success nếu nghiệp vụ chưa commit — container có thể ACK/commit JMS receive và message không được phát lại.

## 14. Acknowledgment và transaction thuộc trách nhiệm cấu hình container

Listener nhận một message rồi ném exception **không bảo đảm redelivery** nếu container đang ở `AUTO_ACKNOWLEDGE` không transacted. Với `DefaultMessageListenerContainer`, AUTO_ACK thông thường được thực hiện **trước listener execution**, nên exception từ listener không kéo theo broker redelivery theo cách nhiều người tưởng.

| Mode | Điều bạn cần biết |
| --- | --- |
| `AUTO_ACKNOWLEDGE` | Thao tác ACK có thể xảy ra trước listener trong Default container; không phù hợp workload cần đảm bảo xử lý trước ACK |
| `CLIENT_ACKNOWLEDGE` | Container chủ động quản lý ACK theo semantics session; không đồng nhất với DB commit |
| `DUPS_OK_ACKNOWLEDGE` | Có thể trì hoãn ACK; khả năng nhận lại/trùng cần được chấp nhận |
| `sessionTransacted=true` | Local JMS receive transaction; handler thành công sẽ JMS commit, lỗi phù hợp rollback |
| External/JTA transaction manager | Có thể bao trùm JMS + resource XA tương thích nhưng đòi hạ tầng/provider/cấu hình riêng |

Spring Framework thường khuyến nghị **transacted sessions** khi cần reliable message processing. Spring Boot 3.x default listener factory do Boot auto-configure được cấu hình **transactional**: nếu có JTA manager phù hợp thì liên kết JTA; nếu không thì `sessionTransacted=true`. Nếu bạn tạo custom factory và không dùng configurer, default transaction có thể khác; phải kiểm thử **bean thực đang được endpoint sử dụng**.

**Quan trọng:** local JMS transaction không tự bao gồm PostgreSQL/MySQL. Nếu handler commit DB trước rồi JMS commit lỗi, broker có thể redeliver; cần stable `eventId` và idempotency bằng DB unique constraint/inbox trong một DB transaction. `JMSMessageID` do provider cấp có thể đổi nếu producer gửi lại cùng business event như message mới.

## 15. Stop, start và shutdown: không chỉ là một cờ running

`JmsListenerEndpointRegistry` cho phép truy container của endpoint theo ID:

~~~java
MessageListenerContainer c =
        registry.getListenerContainer("demoJobsListener");

if (c != null) {
    System.out.println(c.isRunning());
    c.stop();   // Dừng nhận theo lifecycle.
    // Sau khi đã chuẩn bị điều kiện mở lại và muốn nhận tiếp:
    c.start();
}
~~~

Đây là snippet dành cho công cụ vận hành/test, không đặt trong listener handler đang xử lý message. `stop()` không có nghĩa message đã hoàn tất hay tài nguyên được destroy vĩnh viễn; container có thể start lại. `destroy()/ApplicationContext.close()` mới là thao tác chấm dứt vòng đời, giải phóng consumer/session/connection theo hạ tầng. Đừng dùng `stop/start` để làm “pause queue” ở mọi replica nếu bạn chưa điều phối các consumer khác.

### 15.1. In-flight messages trong quá trình shutdown

Trong shutdown có ba nhóm:

1. Message vẫn **nằm ở broker** (chưa dispatch): không bị xử lý bởi container đã stop; kết quả sau restart tùy queue/topic/subscription/TTL.
2. Message **đã giao nhưng chưa commit/ACK**: có thể redeliver sau broker/consumer recovery.
3. Message **đã commit JMS**: broker coi là tiêu thụ xong; business side effect bên ngoài JMS có thể cần reconciliation nếu có failure window.

Khi orchestrator gửi SIGTERM hoặc dừng service, hãy:
- Chặn thêm traffic/điều chỉnh readiness khi phù hợp.
- Cho container có cơ hội dừng nhận mới, để handler in-flight kết thúc trong **grace period** có giới hạn.
- Đặt timeouts cho DB/HTTP calls; đừng để handler treo vô hạn.
- Đảm bảo JMS/DB transaction boundaries rõ; idempotency bảo vệ khi tiến trình chết đột ngột.
- Đo duration shutdown và so với Kubernetes terminationGracePeriodSeconds hoặc deadline của runtime.

**Không khẳng định** “stop luôn đợi tất cả business hoàn tất” trong mọi cấu hình. Một handler có thể bị kill khi grace period hết, network I/O có thể treo, và behavior cụ thể phụ thuộc container/provider settings.

## 16. Lifecycle registry và cách kiểm tra trạng thái endpoint

Các containers được tạo bởi `@JmsListener` **không nhất thiết là bean độc lập trong ApplicationContext**. Spring tập trung quản lý qua `JmsListenerEndpointRegistry`.

~~~java
Set<String> ids = registry.getListenerContainerIds();
for (String id : ids) {
    MessageListenerContainer listener =
            registry.getListenerContainer(id);
    System.out.println(id + " running="
            + (listener != null && listener.isRunning()));
}
~~~

Đây là snippet; imports `java.util.Set`, `JmsListenerEndpointRegistry` và `MessageListenerContainer`, biến `registry` được inject vào Spring bean. Nếu cần can thiệp một endpoint, **đặt `id` tường minh trong annotation**, tránh dựa vào ID sinh ngẫu nhiên/thứ tự đăng ký.

Một container có thể **RUNNING nhưng broker unreachable** trong quá trình recovery. Ngoài `isRunning()`, nên kiểm tra `isRecovering()` ở Default container, số scheduled/active consumer tasks, broker consumer count, oldest message age, DLQ, số lần listener nhận và result của business DB.

**Không hiểu sai tên registry:** nó quản lý *listener container instances*, không chứa toàn bộ JMS connection pools, broker addresses hoặc dữ liệu message. Những thứ đó phải theo dõi ở hạ tầng tương ứng.

## 17. Queue, topic và ordering khi tăng số consumer

### 17.1. Queue

Với queue `jobs.queue`, nhiều consumers có thể cạnh tranh nhận message, thường giúp throughput. Broker quyết định dispatch và prefetch/credit; các listener xử lý song song có thể hoàn tất **khác thứ tự enqueue**.

~~~text
Queue: M1, M2, M3, M4
    │      │
    ▼      ▼
Consumer A   Consumer B
  M1 xử lý 5s   M2 xử lý 100ms
  M3 ...        M4 ...

Kết quả xử lý: M2 có thể commit trước M1.
~~~

Nếu cần ordering theo aggregate `orderId`, dùng partition/grouping phù hợp broker, giảm concurrency cho luồng nhạy cảm hoặc thiết kế xử lý event version. Chỉ tăng consumer count không thể vừa tăng parallelism vô hạn vừa giữ strict total order.

### 17.2. Topic

Topic là pub/sub: nhiều subscriptions có thể nhận mỗi event của topic. Tăng số consumers không đúng cách có thể **nhân số callback nhận cùng message**. Durable subscription, shared subscription, client ID, subscription name và broker routing phải phù hợp loại topology muốn dùng.

**Không áp dụng nguyên xi công thức “2-4 consumers để tăng throughput” của queue cho topic.** Với nhiều replicas topic, hãy thiết kế shared durable/non-durable subscription theo provider/JMS API hoặc chọn queue cho competing consumers. `pubSubDomain=true` chỉ xác định topic destination; nó **không tự thiết lập durable/shared semantics**.

## 18. Multi-endpoint và multi-broker: ai chọn ConnectionFactory?

Ứng dụng có thể có:

~~~text
billingFactory         → billingBrokerCF      → billing.queue
auditFactory           → auditBrokerCF        → audit.topic
notificationFactory    → notificationBrokerCF → notify.queue
~~~

Một `@JmsListener(containerFactory="billingFactory")` chọn factory đã được ứng dụng định nghĩa. Với nhiều `ConnectionFactory`, dùng `@Qualifier`, bean names và `@Primary` cẩn thận; Boot không tự suy ra destination nào thuộc broker nào. Mỗi factory/container có lifecycle và recovery riêng, có thể cùng hoặc khác broker.

Không nhầm annotation ID với destination name:
- `id="billingListener"`: ID trong `JmsListenerEndpointRegistry` để quan sát và quản lý endpoint.
- `destination="billing.queue"`: địa chỉ logic để tạo consumer.
- `containerFactory="billingFactory"`: tên bean factory tạo container.

Một method có thể được đăng ký cho nhiều destinations bằng nhiều `@JmsListener` (annotation repeatable); lúc đó có nhiều endpoints/containers, nên tổng consumers có thể tăng.

### Khi có selector

Selector lọc theo JMS header/property, không parse trực tiếp JSON body. Một endpoint tạo consumer với selector có thể không nhận message không khớp dù queue chứa nhiều item; cần xem property types. Với nhiều selectors, broker dispatch/fairness/prefetch có thể khác nhau, nên sizing phải dựa trên kết quả vận hành.

## 19. Observability: giám sát tài nguyên theo đúng lớp

| Lớp | Dấu hiệu/metric nên theo dõi | Không được suy ra |
| --- | --- | --- |
| Spring registry | Endpoint IDs, `isRunning`, startup state | Broker chắc chắn connected |
| Default container | Scheduled/active consumer count, `isRecovering`, received/error logs | Số message business đã commit |
| TaskExecutor/JVM | Thread count/state, queue executor, CPU/memory | Cứ nhiều thread là throughput cao |
| Connection/provider | Physical connections, sessions, consumers, reconnects, auth errors | Mỗi session = một TCP connection |
| Broker | Queue depth, in-flight, oldest message age, DLQ/expiry, dispatch | Queue depth 0 = business success |
| Handler | Started/succeeded/failed, processing latency, retries | Handler return = DB commit trong mọi transaction |
| Business store | Commit count, idempotency conflicts, invariant errors | JMS commit đã xảy ra nếu DB commit độc lập |

Một dashboard tốt cần **cùng eventId/operationId** ở producer, broker/consumer logs và business DB; thêm `JMSMessageID` và `JMSXDeliveryCount` để truy một message cụ thể. Không ghi token/password hoặc thông tin nhạy cảm ra log.

Khi broker lỗi, hãy kiểm tra theo thứ tự:
1. `ConnectionFactory` thực tế đến broker nào, credentials/ACL đúng không?
2. Endpoint container có được đăng ký và started không?
3. `isRecovering`, logs recovery và broker-side connections/consumers ra sao?
4. Destination là queue/topic nào, selector/filter nào, backlog/in-flight ra sao?
5. Handler có ném exception, converter fail, transaction rollback hay DLQ?
6. DB outcome cuối có được commit không?

Không suy diễn một dấu hiệu đơn lẻ thành toàn bộ kết quả.

## 20. Những anti-pattern cần tránh

1. **“Có `@JmsListener` nghĩa là có một consumer trong JVM”** — sai; số consumers do factory/concurrency quyết định.
2. **“Container tự tạo một thread mới cho mỗi message”** — không; invoker tasks xử lý nhiều message nối tiếp.
3. **“Một consumer đồng nghĩa một physical TCP connection”** — không; connection có thể chứa nhiều sessions.
4. **“Tăng `max-concurrency` luôn làm throughput tăng”** — không; có thể nghẽn broker, DB hoặc API bên ngoài.
5. **“Topic càng nhiều consumers càng nhanh”** — không; có thể là các subscriptions nhận lặp cùng event.
6. **“Gọi `new InvoiceWorker()` thì annotation tự chạy”** — không, object phải được Spring quản lý.
7. **“Factory và container là một bean duy nhất”** — không; một factory có thể tạo nhiều containers.
8. **“Container RUNNING chứng minh broker connected”** — không khi đang recovery.
9. **“Spring Boot cache wrapper nên gắn vào mọi listener”** — thường nên dùng native CF cho listener để container tự recovery.
10. **“`CACHE_CONSUMER` và connection pool là cùng một thứ”** — không; phạm vi/cache semantics khác nhau.
11. **“Tự tạo thread trong listener giúp ACK an toàn hơn”** — ngược lại, listener có thể return/ACK trước business result.
12. **“Exception listener luôn làm broker retry”** — phụ thuộc ACK/transaction mode và DLQ policy.
13. **“`sessionTransacted=true` tự gộp SQL commit”** — không với local JMS transaction.
14. **“`@JmsListener` tự biến payload thành JSON POJO”** — phụ thuộc MessageConverter/schema.
15. **“Stop container là xóa queue”** — không, queue là tài nguyên broker độc lập.
16. **“shutdownNow/cancel hủy ngay mọi JDBC/JMS/HTTP I/O”** — không có bảo đảm chung.
17. **“Recovery interval = độ trễ redelivery của poison message”** — không; recovery connection và broker delivery policy khác nhau.
18. **“Một `max-concurrency=10` áp dụng toàn ứng dụng”** — nó thường áp dụng **mỗi listener endpoint/container**.
19. **“AUTO_ACK mặc định chắc chắn an toàn”** — không; với Default container có thể ACK trước listener execution.
20. **“Message listener làm xong nghĩa là publisher đã nhận business result”** — không; outcome protocol là tầng riêng.

## 21. Bài tập kiểm chứng theo thứ tự

**Bài 1 — Chứng minh container tồn tại:** tạo Spring Boot project có Artemis starter, một `@JmsListener(id="jobs")`, inject `JmsListenerEndpointRegistry`, in IDs và `isRunning`. Không dùng `new Thread`.

**Bài 2 — Nhìn actual class:** lấy endpoint từ registry, in `getClass().getName()`; giải thích khác nhau giữa factory type, container type và listener bean type.

**Bài 3 — Thread ownership:** in `Thread.currentThread().getName()` trong publisher và listener. Gửi nhiều messages, quan sát listener chạy trên consumer thread khác publisher.

**Bài 4 — Min/max consumers:** cấu hình `min-concurrency=1` và `max-concurrency=5`, tạo backlog test, quan sát `getScheduledConsumerCount()` và `getActiveConsumerCount()` theo thời gian; không mặc định luôn lên tới 5.

**Bài 5 — Thứ tự queue:** gửi M1–M10 với sequence; so sánh concurrency 1 và 3. Quan sát processing/completion order thực tế, không kết luận dựa trên một lần chạy.

**Bài 6 — Broker outage:** tắt broker test, xem container recovery/log/backoff; bật lại, kiểm tra consumer registration và message tiếp tục được nhận. Không thử trên môi trường production.

**Bài 7 — Cache level:** thử `CACHE_CONSUMER` với local JMS transaction và `CACHE_NONE` trong setup test; đo resource churn và so sánh. Không áp dụng cache tùy tiện khi có JTA/XA.

**Bài 8 — Native và cached factory:** kiểm tra bean `ConnectionFactory` của Boot (wrapper), listener thực dùng native CF như thế nào và khi nào `ConnectionFactoryUnwrapper` có hiệu lực.

**Bài 9 — Multi-endpoint capacity:** tạo hai endpoints mỗi cái `concurrency=2-4`; dự báo tổng invoker tasks tối đa là 8 cho một replica, rồi xác minh bằng metrics thay vì giả định physical connections cũng là 8.

**Bài 10 — Exception/transaction:** listener có `sessionTransacted=true`, cố throw trước business commit; xem rollback/redelivery hoặc DLQ theo broker. So sánh với AUTO_ACK trên Default container để hiểu vì sao behavior khác nhau.

**Bài 11 — DB commit rồi JMS commit lỗi:** fault injection đúng cửa sổ, xác minh event ID/unique constraint chặn duplicate business state khi broker redeliver.

**Bài 12 — Graceful shutdown:** cho handler mất 3–5 giây, stop context trong lúc xử lý; quan sát in-flight, thời gian stop, JMS rollback/commit và recovery sau restart.

**Bài 13 — Topic:** thử topic với hai subscription độc lập và queue với hai competing consumers. Giải thích vì sao “nhận trùng” có thể là đúng pub/sub semantics.

**Bài 14 — Custom TaskExecutor:** cấu hình executor capacity thấp hơn số invoker tasks, đo executor queue/pending tasks; giải thích starvation, không vội đổ lỗi broker.

**Bài 15 — Bad payload:** gửi một message converter không hiểu, xem error logs, handler có được gọi hay không, broker redelivery và DLQ policy.

### Checklist trước khi hoàn thành bài

- [ ] Phân biệt `@JmsListener`, `JmsListenerContainerFactory` và `MessageListenerContainer`.
- [ ] Giải thích được ConnectionFactory, Connection, Session, MessageConsumer và TaskExecutor thuộc về ai.
- [ ] Biết container giữ lifecycle/recovery, listener bean giữ business logic.
- [ ] Phân biệt `SimpleMessageListenerContainer` và `DefaultMessageListenerContainer`.
- [ ] Biết dùng `@EnableJms` ở Spring thuần, Boot 3.x tự cấu hình khi đủ điều kiện.
- [ ] Hiểu `concurrentConsumers`/`maxConcurrentConsumers` và ảnh hưởng ordering.
- [ ] Không coi consumer count là physical connection count.
- [ ] Phân biệt cacheLevel của container, CachingConnectionFactory và connection pool.
- [ ] Nắm tác động của `sessionTransacted`, AUTO_ACK và local DB commit gap.
- [ ] Biết dùng `JmsListenerEndpointRegistry` để quản lý/quan sát endpoint.
- [ ] Tách recovery connection khỏi retry nghiệp vụ và DLQ.
- [ ] Kiểm chứng được shutdown, broker restart và idempotency bằng fault injection.
- [ ] Không tự cấp thread tùy tiện bên trong listener để đẩy công việc chưa commit sang background.

## 22. Tài liệu chính thức và phạm vi áp dụng

1. [Spring Framework — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): so sánh hai containers, transaction và caching.
2. [Spring Framework — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html): `@EnableJms`, `@JmsListener`, factory, registry và cấu hình concurrency.
3. [Spring Framework 6.2 — DefaultMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html): vòng receive, TaskExecutor, cache levels, recovery, scheduled/active consumer count.
4. [Spring Framework 6.2 — DefaultJmsListenerContainerFactory Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html): các setter được factory ánh xạ sang container.
5. [Spring Framework — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html): listener containers và khả năng phục hồi, acknowledgment.
6. [Spring Boot 3.5 — JMS](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html): Artemis auto-configuration, cached/native factory và listener transaction defaults.
7. [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): `spring.jms.listener.min-concurrency`, `max-concurrency`, `receive-timeout` và `auto-startup`.
8. [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): JMS `Connection`/`Session`/`MessageConsumer`, threading, transaction và redelivery.
9. [Spring Guide — Messaging with JMS](https://spring.io/guides/gs/messaging-jms/): ví dụ ứng dụng Spring Boot phát và nhận message.

**Kết luận:** listener container của Spring là **đơn vị vận hành consumer**, không chỉ một annotation tiện dụng. Container quản lý cách nhận, luồng, JMS resources, scaling, phục hồi và shutdown; ứng dụng vẫn phải quản lý business transaction, idempotency và bằng chứng kết quả. Để debug hoặc scale đúng, xác định **container thực tế, ConnectionFactory thực tế, concurrency thực tế và broker state thực tế** thay vì suy luận từ tên method.