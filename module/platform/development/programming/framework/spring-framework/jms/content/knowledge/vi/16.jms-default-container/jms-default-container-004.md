# Cấu hình concurrency bằng giá trị hoặc khoảng trong DefaultMessageListenerContainer

**Chủ đề cha:** Default container — Spring Framework / JMS.

**Mục tiêu bài học:** Cấu hình chính xác số consumer đồng thời cho `DefaultMessageListenerContainer` bằng chuỗi **một giá trị** hoặc **một khoảng**, qua factory, `@JmsListener`, Spring Boot properties hoặc API Java; biết đọc trạng thái thực tế, giải thích dynamic scaling và chọn min/max phù hợp với queue, topic, thứ tự xử lý, transaction, tài nguyên và số replica.

**Phạm vi phiên bản:** Java 17+, Spring Framework 6.2.x, Spring Boot 3.5.x, Jakarta Messaging (`jakarta.jms`), broker JMS tương thích như Apache ActiveMQ Artemis. Hành vi parser của Default container được đối chiếu với Javadoc chính thức; **không** suy diễn quy tắc này cho mọi messaging framework hay Spring Rabbit/AMQP.

> **Điều cần ghi nhớ nhất:** Với **`DefaultMessageListenerContainer`**, `setConcurrency("5")` là **min = 1, max = 5**, không phải năm consumer cố định. `setConcurrency("5-5")` mới có **min = 5, max = 5**. `"2-5"` nghĩa là giữ hai consumer lõi và có thể mở rộng tới năm. Cách hiểu này cũng áp dụng khi `DefaultJmsListenerContainerFactory` và `@JmsListener(concurrency=...)` chuyển cấu hình xuống Default container.

## 1. Concurrent consumers thực chất là gì?

Spring `DefaultMessageListenerContainer` chạy các tác vụ gọi `MessageConsumer.receive()` để nhận message từ broker và gọi handler. Mỗi consumer invoker thường gắn với một JMS `Session` và `MessageConsumer`, được lập lịch trên một worker thread từ `TaskExecutor`. Invoker xử lý một message, hoàn tất xử lý/transaction phù hợp, rồi nhận message tiếp theo.

~~~text
JMS queue: orders.jobs
    │
    ├── Message A ──► Invoker 1 / JMS Session 1 ──► @JmsListener handler
    ├── Message B ──► Invoker 2 / JMS Session 2 ──► @JmsListener handler
    ├── Message C ──► Invoker 3 / JMS Session 3 ──► @JmsListener handler
    └── Message D ──► Chờ điều kiện dispatch và consumer rảnh
~~~

Concurrency ở đây là **số JMS consumer invokers được phép chạy đồng thời trong một listener container**, không phải số message đang nằm trong queue, số HTTP requests, số CPU cores, số producer, hay số TCP connections. Một `Connection` có thể có nhiều `Session`. Một invoker có thể xử lý nhiều messages theo thời gian, không phải mỗi message tạo một thread mới.

Với queue có hai consumers, hai messages có thể được xử lý đồng thời. Nhưng hai consumers cũng có thể cùng chờ `receive(timeout)`; khi đó họ **active** theo container mà chưa thực hiện business logic. Vì vậy, không dùng `getActiveConsumerCount()` làm số message handlers đang bận tại một thời điểm.

## 2. Hai số gốc: concurrentConsumers và maxConcurrentConsumers

| Thuộc tính | Ý nghĩa | Mặc định trong Default container |
| --- | --- | --- |
| `concurrentConsumers` | Mức **core/tối thiểu** container cố duy trì khi hoạt động | 1 |
| `maxConcurrentConsumers` | Mức **tối đa** container có thể tạo khi tải tăng | 1 |

Với `min=2, max=5`:

~~~text
Consumer invoker 1  CORE ── được duy trì
Consumer invoker 2  CORE ── được duy trì
Consumer invoker 3  EXTRA ─ có thể được tạo khi nhiều message
Consumer invoker 4  EXTRA ─ có thể được tạo khi tải vẫn lớn
Consumer invoker 5  EXTRA ─ giới hạn trên
                  tải giảm / idle
                  └─ các EXTRA có thể dừng, CORE được duy trì
~~~

Có thể cấu hình trực tiếp bằng Java:

~~~java
DefaultMessageListenerContainer container =
        new DefaultMessageListenerContainer();

container.setConcurrentConsumers(2);
container.setMaxConcurrentConsumers(5);
~~~

Đây chỉ là **snippet cấu hình**; để chạy cần `ConnectionFactory`, destination, listener, lifecycle và broker. Hai tham số phải là số nguyên dương. Hãy tự áp dụng rule `1 ≤ min ≤ max`; đừng phụ thuộc vào hành vi clamp/normalize của setter khi nhập nhầm max thấp hơn min.

Một consumer lõi được “duy trì” theo chính sách lifecycle, **không** đồng nghĩa broker chắc chắn có một connected consumer nếu network đang down, credentials lỗi, hoặc executor không cấp được thread.

## 3. Cú pháp một giá trị và khoảng: bảng bắt buộc nhớ

`DefaultMessageListenerContainer.setConcurrency(String)` hỗ trợ:
- `"N"`: **giới hạn trên N**, giữ min bằng `1`.
- `"MIN-MAX"`: đặt rõ cả core min và upper max.

| Cấu hình chuỗi | Min/core | Max | Cách hiểu đúng |
| --- | ---: | ---: | --- |
| Không cấu hình | 1 | 1 | Một consumer |
| `"1"` | 1 | 1 | Một consumer cố định |
| `"4"` | 1 | 4 | **Co giãn 1 đến 4** |
| `"4-4"` | 4 | 4 | **Cố định 4** |
| `"2-5"` | 2 | 5 | Hai core, có thể lên năm |
| `"1-8"` | 1 | 8 | Ít resources lúc rảnh, có thể tăng tới tám |
| `"5-10"` | 5 | 10 | Năm core, trần mười |
| `"8-8"` | 8 | 8 | Cố định tám |

~~~java
container.setConcurrency("4");   // min = 1, max = 4
container.setConcurrency("4-4"); // min = 4, max = 4
container.setConcurrency("2-4"); // min = 2, max = 4
~~~

Vì vậy câu “`concurrency="4"` tạo ra bốn workers” là **sai** với Default container. Muốn bốn consumers lõi ngay khi startup, dùng `"4-4"`. Muốn bắt đầu với một rồi scale đến bốn, dùng `"1-4"` hoặc `"4"`.

### Dữ liệu không hợp lệ và bẫy parser

- `"0"` hoặc `"0-5"` không hợp lệ vì không thể có 0 core consumer trong cấu hình này.
- `"auto"`, `"2..5"`, `"two-five"` không phải cú pháp `setConcurrency(String)`.
- `"5-2"` ngược ý định min/max; Spring 6.2 có thể normalize max lên min thay vì luôn throw. Không dùng trường hợp đó làm cấu hình có chủ đích.
- Tránh whitespace bất thường như `"2 - 5"`: parser không được cam kết sẽ trim mọi đoạn trước khi chuyển sang integer.
- Đây là chuỗi do API parse, không phải phép trừ số học.

**Điểm khác framework:** trong Spring Rabbit/AMQP, các listener containers có API và cách phân tích single integer riêng. Không copy nguyên kết luận “`N` nghĩa min1/maxN” cho những class không phải Spring JMS `DefaultMessageListenerContainer`.

## 4. Dùng Java setters để diễn đạt cố định hoặc co giãn

Một số fixed:

~~~java
container.setConcurrentConsumers(3);
container.setMaxConcurrentConsumers(3);
// Tương đương setConcurrency("3-3").
~~~

Một khoảng elastic:

~~~java
container.setConcurrentConsumers(2);
container.setMaxConcurrentConsumers(6);
// Tương đương setConcurrency("2-6").
~~~

**Vì sao có cả hai API?** Code cấu hình có thể có input số nguyên riêng từ config service, còn annotation/factory dùng một chuỗi ngắn để tiện thiết lập. Cả hai tạo ra cặp min/max cho cùng container. Khi code hoàn chỉnh, ưu tiên một nguồn cấu hình rõ ràng thay vì đặt chuỗi rồi gọi setters chồng chéo ở nhiều nơi.

Giá trị `maxConcurrentConsumers` là **giới hạn cấu hình**, không phải số consumer tức thì sau setter. Container phải có tải, quyền cấp thread và broker dispatch phù hợp mới có thể scale. Ngược lại, khi muốn fixed số lượng, đặt min=max; khi không có broker, ngay cả fixed container cũng có thể đang recovery.

## 5. Cấu hình tại DefaultJmsListenerContainerFactory trong Spring Framework thuần

Một cách sử dụng phổ biến là khai báo factory bean:

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
            ConnectionFactory cf) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(cf);
        factory.setPubSubDomain(false);
        factory.setConcurrency("2-5");
        factory.setReceiveTimeout(1_000L);
        factory.setSessionTransacted(true);
        return factory;
    }
}
~~~

Class Java 17 trên biên dịch được trong project Spring Framework 6.x với `spring-jms`, Jakarta JMS API và `ConnectionFactory` bean từ provider. **Không có `main` độc lập**, phải có Spring ApplicationContext, broker và listener bean.

`@EnableJms` kích hoạt xử lý `@JmsListener`; factory mang tên mặc định `jmsListenerContainerFactory`. Khi Spring phát hiện một annotated endpoint dùng factory đó, nó tạo **một DefaultMessageListenerContainer cho endpoint** và áp dụng cặp concurrency 2..5. Nếu có bốn endpoints cùng dùng factory, mỗi endpoint có range riêng, **không phải bốn endpoints dùng chung max5**.

~~~text
Factory concurrency = 2-5
  ├─ Orders container:    min2..max5
  ├─ Billing container:   min2..max5
  ├─ Shipping container:  min2..max5
  └─ Audit container:     min2..max5
Tối đa theo cấu hình = 4 × 5 = 20 invoker tasks / replica
~~~

Các container đã được tạo không nhất thiết tự cập nhật khi thay đổi bean factory ở runtime. Nếu muốn thay mức đang chạy, làm ở concrete container/registry với runbook hoặc cập nhật cấu hình và redeploy.

## 6. Annotation @JmsListener có thể override factory

Spring hỗ trợ cấu hình cho **mỗi listener endpoint** thông qua `@JmsListener(concurrency = "...")`:

~~~java
@Component
class OrderListeners {

    @JmsListener(
            id = "regularOrders",
            destination = "orders.regular",
            concurrency = "1-3")
    public void regular(String body) {
        processRegular(body);
    }

    @JmsListener(
            id = "criticalOrders",
            destination = "orders.critical",
            concurrency = "4-4")
    public void critical(String body) {
        processCritical(body);
    }
}
~~~

Đoạn này là snippet trong Spring bean; cần import `@Component`, `@JmsListener` và tự implement `processRegular`, `processCritical`. Nếu factory có `"2-5"` thì:
- `regularOrders` dùng **min1/max3** theo annotation.
- `criticalOrders` dùng **min4/max4** theo annotation.
- Listener thứ ba không đặt thuộc tính concurrency sẽ dùng cấu hình factory.

Javadoc `@JmsListener` nói rõ thuộc tính này **override concurrency của container factory**. Nó không override toàn bộ cấu hình connection/transaction/converter; những thuộc tính đó vẫn từ factory hoặc endpoint config.

~~~java
@JmsListener(
        id = "wrongFixedAssumption",
        destination = "demo.jobs",
        concurrency = "4")  // MIN=1, MAX=4, không cố định 4.
public void handle(String body) {
    process(body);
}
~~~

Nếu cần chính xác bốn core consumers, sửa `concurrency="4-4"`. Không đặt min quá lớn chỉ để “có nhiều threads”: với queue ít dữ liệu, consumers dư vẫn chiếm resources.

## 7. Spring Boot 3.5: min-concurrency và max-concurrency trong YAML

Spring Boot cung cấp hai properties cho default JMS listener factory:

~~~yaml
spring:
  jms:
    listener:
      min-concurrency: 2
      max-concurrency: 5
      receive-timeout: 1s
~~~

Trong auto-configuration chuẩn của Boot 3.5, config này thể hiện **min2/max5**. Đây là cách viết bằng hai giá trị riêng, không phải truyền nguyên chuỗi `"2-5"`.

**Điểm đặc biệt:** Boot 3.5 property metadata quy định khi chỉ có `min-concurrency` mà **không có `max-concurrency`**, min được dùng làm max. Ví dụ:

~~~yaml
spring:
  jms:
    listener:
      min-concurrency: 4
~~~

Khi default listener factory của Boot được sử dụng, đây là cấu hình **fixed min4/max4**. Nó **khác** truyền `"4"` cho `DefaultMessageListenerContainer.setConcurrency(String)`, khi đó min1/max4. Tránh nhầm hai lớp API.

| Ý định | Spring factory hoặc annotation | Spring Boot properties |
| --- | --- | --- |
| Cố định 1 | `"1"` hoặc `"1-1"` | `min-concurrency: 1`, không đặt max |
| Cố định 3 | `"3-3"` | `min-concurrency: 3`, không đặt max |
| Co giãn 1..3 | `"3"` hoặc `"1-3"` | `min-concurrency: 1` và `max-concurrency: 3` |
| Co giãn 2..5 | `"2-5"` | `min-concurrency: 2` và `max-concurrency: 5` |
| Cố định 5 | `"5-5"` | `min-concurrency: 5` và `max-concurrency: 5` |

Nếu Boot factory mặc định dùng 2..5 nhưng annotation ghi `concurrency="1-8"`, listener đó áp dụng **1..8** theo annotation. YAML không phải một *global max* được áp dụng cứng cho toàn bộ app.

**Khi Boot properties không có tác dụng:** ứng dụng tự khai báo một `DefaultJmsListenerContainerFactory` khác, nhưng không gọi `DefaultJmsListenerContainerFactoryConfigurer`, có thể bỏ qua properties Boot. Hãy kiểm tra factory mà từng endpoint thực sự sử dụng.

## 8. Tạo một factory riêng trong Boot mà vẫn giữ cấu hình của Boot

Nếu ứng dụng cần một factory riêng cho các queue quan trọng, có thể tận dụng Boot configurer:

~~~java
@Configuration(proxyBeanMethods = false)
class CriticalQueueConfiguration {

    @Bean
    DefaultJmsListenerContainerFactory criticalQueueFactory(
            DefaultJmsListenerContainerFactoryConfigurer configurer,
            ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        configurer.configure(
                factory,
                ConnectionFactoryUnwrapper.unwrapCaching(connectionFactory));

        factory.setConcurrency("3-6");
        factory.setSessionTransacted(true);
        return factory;
    }
}
~~~

Imports: `jakarta.jms.ConnectionFactory`, `org.springframework.context.annotation.Configuration`, `@Bean`, `org.springframework.jms.config.DefaultJmsListenerContainerFactory`, `org.springframework.boot.autoconfigure.jms.DefaultJmsListenerContainerFactoryConfigurer` và `org.springframework.boot.jms.ConnectionFactoryUnwrapper`.

Đây là snippet trong project Spring Boot 3.5, không phải class standalone. `Configurer` giúp giữ config mặc định hữu ích của Boot (converter, transaction settings, resource handling…) trước khi bạn override `concurrency`. `ConnectionFactoryUnwrapper.unwrapCaching` lấy native factory từ wrapper cache trong những trường hợp được hỗ trợ; đây là lựa chọn được Spring Boot hướng dẫn cho listener containers để recovery do container tự quản lý.

Listener lựa chọn bean factory bằng tên:

~~~java
@JmsListener(
        id = "criticalInvoices",
        destination = "critical.invoices",
        containerFactory = "criticalQueueFactory")
public void handle(String payload) {
    processInvoice(payload);
}
~~~

Nếu đặt tiếp `concurrency="2-2"` trên annotation này, annotation sẽ override `"3-6"` của factory cho endpoint, không phải đồng thời tạo 3–6 và 2–2 consumers. `containerFactory` là bean name, `id` là endpoint ID trong registry và `destination` là queue/topic broker.

## 9. Ví dụ Java 17 + Spring Boot: quan sát fixed và elastic

Bài thực hành có hai queues:
- `demo.fixed.jobs`: listener `fixedJobs` với `concurrency="3-3"`.
- `demo.elastic.jobs`: listener `elasticJobs` với `concurrency="2-5"`.

Ứng dụng gửi 12 messages vào mỗi queue và đọc config từ `JmsListenerEndpointRegistry`. Mục tiêu **đọc được min/max thật**, không giả định elastic luôn chạm 5 hoặc fixed luôn có đủ connected consumers khi broker down.

**Điều kiện chạy:** Java 17+, Spring Boot 3.5.0, Gradle phù hợp, broker Apache ActiveMQ Artemis đang chạy tại `tcp://localhost:61616`, user có quyền send/consume, hai queues tồn tại hoặc broker cho phép auto-create. Bài dùng bản phát hành có thật làm mốc API, không khẳng định là bản Boot mới nhất.

### 9.1. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '1.0.0'

repositories { mavenCentral() }

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
rootProject.name = 'jms-concurrency'
~~~

### 9.2. application.yaml

~~~yaml
spring:
  artemis:
    mode: native
    broker-url: tcp://localhost:61616
    user: demo
  jms:
    pub-sub-domain: false
    listener:
      min-concurrency: 1
      max-concurrency: 3
      receive-timeout: 1s
~~~

Đặt mật khẩu qua biến môi trường `SPRING_ARTEMIS_PASSWORD` hoặc secret manager. Không hard-code credentials trong Git. YAML mặc định 1..3 chỉ áp dụng với endpoints không override concurrency; hai endpoints Java bên dưới override để thể hiện fixed và elastic.

### 9.3. Java application đầy đủ

`src/main/java/example/jmsconcurrency/JmsConcurrencyApplication.java`:

~~~java
package example.jmsconcurrency;

import java.util.List;

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
public class JmsConcurrencyApplication {

    public static void main(String[] args) {
        SpringApplication.run(JmsConcurrencyApplication.class, args);
    }

    @Bean
    ApplicationRunner demonstrate(
            JmsTemplate template,
            JmsListenerEndpointRegistry registry) {

        return args -> {
            for (String id : List.of("fixedJobs", "elasticJobs")) {
                MessageListenerContainer container =
                        registry.getListenerContainer(id);

                if (!(container instanceof
                        DefaultMessageListenerContainer dmlc)) {
                    throw new IllegalStateException(
                            "Expected Default container for " + id);
                }

                System.out.printf(
                        "CONFIG %s min=%d max=%d scheduled=%d active=%d%n",
                        id,
                        dmlc.getConcurrentConsumers(),
                        dmlc.getMaxConcurrentConsumers(),
                        dmlc.getScheduledConsumerCount(),
                        dmlc.getActiveConsumerCount());
            }

            for (int i = 1; i <= 12; i++) {
                template.convertAndSend("demo.fixed.jobs", "fixed-" + i);
                template.convertAndSend("demo.elastic.jobs", "elastic-" + i);
            }
            System.out.println("SENT_24_MESSAGES");
        };
    }
}

@Component
class DemoJobsListeners {

    @JmsListener(
            id = "fixedJobs",
            destination = "demo.fixed.jobs",
            concurrency = "3-3")
    public void fixed(String payload) {
        handle("FIXED", payload);
    }

    @JmsListener(
            id = "elasticJobs",
            destination = "demo.elastic.jobs",
            concurrency = "2-5")
    public void elastic(String payload) {
        handle("ELASTIC", payload);
    }

    private void handle(String kind, String payload) {
        try {
            Thread.sleep(250L);
            System.out.printf(
                    "%s thread=%s payload=%s%n",
                    kind, Thread.currentThread().getName(), payload);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Handler interrupted", ex);
        }
    }
}
~~~

### 9.4. Chạy và quan sát

Với Gradle wrapper và broker test đã hoạt động:

~~~bash
./gradlew bootRun
~~~

Một số log có thể xuất hiện:

~~~text
CONFIG fixedJobs min=3 max=3 scheduled=3 active=3
CONFIG elasticJobs min=2 max=5 scheduled=2 active=2
ELASTIC thread=... payload=elastic-1
FIXED thread=... payload=fixed-1
SENT_24_MESSAGES
~~~

**Đây không phải stdout được bảo đảm.** Scheduled/active có thể khác ở đúng thời điểm đo vì container startup/recovery bất đồng bộ. Consumers có thể xử lý messages ngay trong lúc `ApplicationRunner` đang gửi. Queue có nhiều consumers nên thứ tự handle/commit không cố định; `elastic-4` có thể chạy trước `elastic-3`. Với thời gian xử lý 250ms, container cũng không nhất thiết scale từ 2 lên 5 vì backlog có thể hết quá nhanh hoặc broker prefetch phân phối khác nhau.

**Ví dụ không có DB nghiệp vụ**, chỉ in log; không chứng minh exactly-once processing, không nên dùng startup runner để phát messages production. Mỗi lần restart, runner gửi thêm messages test.

## 10. Phải đo cả min/max và số invokers đang chạy

`DefaultMessageListenerContainer` có các getters:

~~~java
int min = dmlc.getConcurrentConsumers();
int max = dmlc.getMaxConcurrentConsumers();
int scheduled = dmlc.getScheduledConsumerCount();
int active = dmlc.getActiveConsumerCount();
~~~

| Getter | Điều nó cung cấp |
| --- | --- |
| `getConcurrentConsumers()` | Mức core min **đã cấu hình** |
| `getMaxConcurrentConsumers()` | Mức max **đã cấu hình** |
| `getScheduledConsumerCount()` | Số consumer invoker tasks được schedule |
| `getActiveConsumerCount()` | Số invokers đang active theo lifecycle container |

**Active không phải số handler đang thực thi nghiệp vụ ngay lúc đó**: một active invoker có thể đang chờ `receive(timeout)`. Scheduled không nhất thiết là số broker-connected consumers khi connection failed hoặc executor saturated. Chỉ nhìn `max=10` cũng không chứng minh lúc này có 10 consumers.

Đọc qua registry theo ID:

~~~java
MessageListenerContainer container =
        registry.getListenerContainer("elasticJobs");

if (container instanceof DefaultMessageListenerContainer dmlc) {
    System.out.printf(
            "min=%d max=%d scheduled=%d active=%d%n",
            dmlc.getConcurrentConsumers(),
            dmlc.getMaxConcurrentConsumers(),
            dmlc.getScheduledConsumerCount(),
            dmlc.getActiveConsumerCount());
}
~~~

`registry` là Spring bean `JmsListenerEndpointRegistry` đã inject. Nó tìm container được tạo từ endpoint có `id` phù hợp; **không** tìm theo queue name. Dùng `instanceof` thay vì ép kiểu mù, vì một factory khác có thể tạo `SimpleMessageListenerContainer`.

## 11. Cơ chế scale up/down không đơn giản là queue depth vượt một ngưỡng

Default container không mặc định vận hành theo công thức “queue depth > 100 thì tăng 1 consumer”. Nó quan sát hoạt động receive, invokers bận/rảnh, số dư được phép schedule và tài nguyên executor. Min consumers được giữ; surplus consumers có thể được tạo khi tải tăng và dừng khi không còn việc.

~~~text
min=2, max=5

t0: queue rỗng              [core A, core B]
t1: có backlog              [core A bận, core B bận]
t2: còn nhiều message       [core A, core B, extra C] (có thể)
t3: tải tiếp tục            [core A, B, C, extra D, extra E] (có thể)
t4: queue rỗng trở lại      [surplus C/D/E idle]
t5: qua ngưỡng idle         [core A, core B]
~~~

**Thứ tự và thời điểm này chỉ minh họa.** Việc chạm max phụ thuộc `TaskExecutor`, thời gian xử lý message, broker credit/prefetch, selector, timeout và các giới hạn idle. Không bắt buộc “queue depth tăng ⇒ active ngay lập tức bằng max”.

Nếu một consumer prefetch quá nhiều messages vào client, các consumers mới có thể còn idle dù broker queue hiển thị ít message. Nếu database chậm, mở thêm consumers có thể làm DB connection pool bị tranh chấp nặng hơn thay vì tăng throughput.

## 12. Receive timeout và giới hạn idle làm thay đổi nhịp co giãn

| Thiết lập | Vai trò |
| --- | --- |
| `setReceiveTimeout(long)` | Thời gian một lần consumer invoker chờ message, Default container thường 1000ms |
| `setIdleConsumerLimit(int)` | Số idle consumers cho phép khi quyết định schedule thêm (default 1) |
| `setIdleTaskExecutionLimit(int)` | Giới hạn số task executions idle trước khi surplus consumer được thu hồi (default 1) |
| `setIdleReceivesPerTaskLimit(int)` | Số lần receive liên tiếp trả null để đánh dấu task idle |
| `setMaxMessagesPerTask(int)` | Số receive **attempts** tối đa trong một task, có thể gồm những lần nhận null |
| `setTaskExecutor(Executor)` | Nơi schedule các invoker tasks, ảnh hưởng pool capacity và task lifetime |

**Phân biệt hai đếm:** `maxMessagesPerTask` không chỉ là số messages đã xử lý thành công; có thể tính cả receive attempts hết timeout. `idleTaskExecutionLimit` đếm task executions idle, khác `idleReceivesPerTaskLimit` đếm số receive null liên tiếp.

Trong Spring Framework 6.2, với default/non-pooling executor, `idleReceivesPerTaskLimit` hiệu lực mặc định là 10 cho surplus consumers. Nếu mỗi `receive` chờ tối đa một giây thì một surplus consumer có thể được thu hồi sau khoảng 10 lần rỗng, tức khoảng 10 giây trong trường hợp lý tưởng. **Đây không phải SLA thời gian cố định**, và core consumers vẫn được duy trì theo min.

Với `SchedulingTaskExecutor` ưu tiên short-lived tasks, `maxMessagesPerTask` có thể mặc định 10; tasks được chia/re-schedule khác default executor. Chỉ nên chỉnh các giới hạn idle khi load test cho thấy ramp-up chậm hoặc scale-up/down quá thường xuyên, không vì “đã đặt range nên phải tùy chỉnh mọi property”.

## 13. TaskExecutor: cấu hình max không bảo đảm có đủ threads

Một `DefaultMessageListenerContainer` chạy invoker tasks qua Spring `TaskExecutor`. Nếu dùng default executor, thường là `SimpleAsyncTaskExecutor`. Khi dùng custom bounded executor, những invokers có thể chiếm threads lâu dài vì mỗi task lặp receive.

~~~text
Custom executor có 3 threads:
Thread #1: core invoker A → receive → handler → receive ...
Thread #2: core invoker B → receive → handler → receive ...
Thread #3: extra invoker C → receive → handler → receive ...
Task D và E: phải chờ executor slot dù container max=5
~~~

**Mất scale chưa chắc do JMS setting:** nếu executor pool nhỏ hoặc chia chung với nhiều endpoints, scheduled invokers có thể không được cấp threads. Đo executor active count/queue length, broker consumer count, handler duration và idle count trước khi kết luận `setConcurrency` không hoạt động.

Cũng không nên cho mọi endpoints dùng chung một bounded pool có kích thước ít hơn tổng core consumers. Invoker core có thể giữ threads rất lâu và gây starvation cho endpoints còn lại.

### Virtual threads

Spring Framework 6.2+ hỗ trợ virtual threads trên Java 21+ với default executor trong những điều kiện phù hợp, nhưng **bài minh họa Java 17** không bật. Virtual threads giảm chi phí chờ ở JVM chứ không biến broker JMS sessions, prefetch memory, database connections hoặc API rate limits thành vô hạn.

## 14. Fixed và elastic: chọn khi nào?

| Tiêu chí | Fixed `"4-4"` | Elastic `"1-4"` / `"4"` |
| --- | --- | --- |
| Core consumers | 4 | 1 |
| Max consumers | 4 | 4 |
| Footprint khi queue rỗng | Thường lớn hơn | Thường nhỏ hơn |
| Khả năng phản hồi burst ngay lập tức | Core đã có sẵn | Phải schedule thêm invokers |
| Số invokers thay đổi theo tải | Không do min/max | Có thể tăng/giảm |
| Dự đoán resource budget | Dễ hơn | Cần quan sát dynamic scaling |
| Phù hợp | Tải nền ổn định, latency nhạy cảm | Tải bursty, muốn ít resource lúc rảnh |
| Rủi ro mất ordering khi >1 | Có | Có khi scale lên 2+ |

Nếu queue nhỏ và có yêu cầu ordering, `"1-1"` có thể hợp lý. Nếu queue luôn backlog và downstream đủ capacity, fixed `"4-4"` có thể tốt hơn về latency khởi động. Nếu queue rảnh nhiều giờ rồi có burst ngắn, `"1-4"` giảm idle cost nhưng cần kiểm tra ramp-up.

**Không suy ra fixed nghĩa không có retry.** Container/recovery/broker có thể redeliver dù chỉ một consumer; idempotency vẫn cần cho nghiệp vụ quan trọng.

## 15. Tăng concurrency có thể làm mất thứ tự xử lý

~~~text
Broker dispatch: M1, M2, M3
Consumer A nhận M1 → xử lý 2 giây ─────────────► DB COMMIT
Consumer B nhận M2 → xử lý 100ms ─► DB COMMIT
Consumer C nhận M3 → xử lý 300ms ───► DB COMMIT

Thứ tự business commit có thể là M2, M3, M1.
~~~

Với nhiều consumers trên queue, processing order và completion order có thể khác enqueue order, ngay cả khi broker dispatch theo thứ tự. Nếu workflow yêu cầu đúng thứ tự state của cùng `orderId`, cân nhắc:
- Một consumer nếu cần strict total ordering và chấp nhận hạn chế throughput.
- Message grouping theo `JMSXGroupID` nếu broker hỗ trợ và đã kiểm thử failover.
- Partition theo aggregate key, event version, optimistic locking hoặc state machine.
- Idempotent handling để đối phó redelivery/duplicate publish.

**Một range `"1-5"` có thể tạm thời xử lý đúng thứ tự lúc chỉ có một consumer, rồi phá thứ tự khi tăng lên năm.** Đừng dùng trạng thái min=1 như lời hứa ordering xuyên mọi mức tải.

## 16. Topic không giống queue khi tăng consumer count

Spring Default container Javadoc cảnh báo: khi destination là **topic** với subscriptions JMS thông thường, tăng số consumers có thể tạo nhiều subscriptions độc lập cùng nhận **bản sao của một event**, không phải chia tải như competing queue consumers.

~~~text
Topic: audit.events
   │
   ├─ Consumer/subscription A nhận Event X
   ├─ Consumer/subscription B nhận Event X
   └─ Consumer/subscription C nhận Event X
       → có thể ba callback cho cùng Event X
~~~

Với topic non-shared thông thường, thường giữ `concurrency="1-1"` trừ khi có thiết kế shared/durable subscription được JMS provider hỗ trợ và đã kiểm chứng. `pubSubDomain=true` chỉ làm destination thuộc loại topic; nó **không tự cấu hình shared subscription hoặc durable identity** cho mọi consumer.

Trên queue, nhiều consumers cạnh tranh nhận message, và broker dispatch một message cho một consumer trong một lần delivery. Trên topic, nhiều subscriptions nhận event theo pub/sub semantics. Tăng concurrency vô tội vạ trên topic có thể bị hiểu nhầm thành duplicate business processing.

## 17. Số sessions, connections và downstream capacity

Khi tăng `maxConcurrentConsumers`, một container có thể cần thêm JMS `Session`, `MessageConsumer` và tasks. Nhưng một JMS `Connection` có thể chứa nhiều sessions; **không** kết luận max5 đồng nghĩa năm physical TCP connections.

Tài nguyên cần cân nhắc:
- Broker max consumers/addresses, memory và prefetch/credit.
- Container cache level: `CACHE_NONE`, `CACHE_CONNECTION`, `CACHE_SESSION`, `CACHE_CONSUMER`, `CACHE_AUTO`.
- `TaskExecutor` threads và queue.
- DB pool size, SQL locks, transactions, external API rate limits.
- Payload size, serialization/deserialization và thời gian handler.
- Số endpoints, số replicas, failover/recovery sau outage.

Với native/local JMS, Default container có thể cache sessions/consumers. Khi dùng external transaction manager/JTA, default auto cache có thể giảm để resources được enlist đúng. Không chỉnh cache level tùy tiện chỉ để đạt max consumer nhanh hơn.

Trong Spring Boot, listener container thường nên dùng native `ConnectionFactory` được unwrap khỏi wrapper caching của template, để container quản lý recovery. Đừng dùng `CachingConnectionFactory` trực tiếp trong mọi listener mà không hiểu giới hạn lifecycle và scaling.

## 18. Transaction và acknowledgment không do concurrency quyết định

Tăng min/max không tự làm consumer đáng tin hơn:

- Với `AUTO_ACKNOWLEDGE` trên `DefaultMessageListenerContainer`, acknowledgment có thể xảy ra **trước** khi listener handler chạy; lỗi xử lý có thể không làm redelivery.
- Với `sessionTransacted=true`, mỗi receive/handler được bao quanh bởi local JMS transaction; handler exception phù hợp dẫn tới rollback/redelivery theo broker policy.
- Local JMS transaction **không tự bao gồm SQL database** hoặc một HTTP payment API.
- Nhiều invokers có thể xử lý những message khác nhau đồng thời; mỗi JMS Session tuân theo quy tắc context một luồng.

~~~java
@Bean
DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
        ConnectionFactory connectionFactory) {

    var factory = new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setConcurrency("2-5");
    factory.setSessionTransacted(true);
    return factory;
}
~~~

Đây là snippet cấu hình Spring cần imports và bean `ConnectionFactory` tương thích. Nếu handler commit DB rồi tiến trình chết trước JMS commit, broker có thể redeliver. Với concurrency lớn, race trên cùng business key trở nên dễ thấy hơn. Dùng stable `eventId`, unique constraints/inbox trong cùng DB transaction, và idempotency với side effects bên ngoài.

Không spawn raw `new Thread` trong listener rồi return ngay khi việc nghiệp vụ chưa hoàn thành nếu còn trông đợi JMS transaction bảo vệ nó. Listener return có thể làm JMS commit trước business effect của background thread.

## 19. Multi-replica: max của một container không phải global max

Ví dụ bốn replicas, mỗi replica có ba endpoints, mỗi endpoint min2/max6:

~~~text
Số core invoker tasks theo cấu hình:  4 × 3 × 2 = 24
Số tối đa theo cấu hình:              4 × 3 × 6 = 72
~~~

Đây là **số lý thuyết về invokers**, không đo actual broker connections hoặc throughput. Nếu mọi worker gọi DB, mỗi replica cần resource budget phù hợp. Nâng max ở tất cả replicas cùng lúc có thể gây thundering herd khi broker phục hồi hoặc queue backlog tăng.

Nếu một external API cho phép toàn hệ thống chỉ tối đa mười calls đồng thời, `concurrency="1-10"` **ở mỗi replica** không tạo global cap mười. Bạn cần limiter/distributed coordination thích hợp hoặc giới hạn ở hệ thống đích.

### Ước lượng throughput với giả định rõ

Nếu trung bình mỗi handler tốn 200ms và có năm consumers thật sự bận liên tục, throughput lý tưởng xấp xỉ:

\[
\frac{5\text{ consumers}}{0.2\text{ s/message}} = 25\text{ messages/s}
\]

Con số **25 msg/s chỉ là mô hình**, không tính SQL lock, broker latency, serialization, retry, tail latency, prefetch hoặc CPU contention. Để sizing production, đo p95/p99 processing duration, oldest message age, error rate và DB pool saturation; không dùng một phép chia làm benchmark.

## 20. Runtime tuning: thay trên đúng container, có giám sát

Các setters `setConcurrentConsumers`/`setMaxConcurrentConsumers` của Default container có thể được thay ở runtime trong Spring 6.2, nhưng cần lấy **instance container thật**:

~~~java
MessageListenerContainer container =
        registry.getListenerContainer("elasticJobs");

if (container instanceof DefaultMessageListenerContainer dmlc) {
    dmlc.setConcurrentConsumers(2);
    dmlc.setMaxConcurrentConsumers(6);
}
~~~

`registry` là Spring bean `JmsListenerEndpointRegistry`, không phải broker API. Không sửa `DefaultJmsListenerContainerFactory` rồi mặc định mọi containers đã tạo được update ngay.

Trước runtime change:
1. Kiểm tra đúng endpoint ID, queue/topic và runtime implementation.
2. Xác nhận quyền/admin approval, audit log và cơ chế rollback.
3. Đặt min/max trong resource budget của JVM/broker/DB và tổng replicas.
4. Quan sát actual scheduled/active counts, handler latency và queue age trong vài chu kỳ.
5. Hiểu thay đổi không nhất thiết tức thì; scale-down cần idle events.
6. Ghi thay đổi vào config bền vững khi phù hợp; runtime setters có thể mất sau restart.

Không mở public HTTP endpoint cho phép bất kỳ ai đổi `maxConcurrentConsumers` lên hàng nghìn.

## 21. Troubleshooting theo triệu chứng

| Triệu chứng | Khả năng nguyên nhân | Hành động kiểm tra |
| --- | --- | --- |
| Đặt `"5"` mà startup chỉ thấy 1 consumer | `"5"` là min1/max5 | Đọc `getConcurrentConsumers()` và `getMaxConcurrentConsumers()` |
| Muốn fixed 5 nhưng count lúc rảnh giảm | Dùng `"5"` thay cho `"5-5"` | Sửa định dạng fixed |
| `"2-6"` nhưng active chỉ 2 | Tải thấp, broker không dispatch, executor thiếu threads | Broker consumer count, scheduled/active, executor queue |
| Backlog tăng mà scale không đạt max | Prefetch/credit, handler nhanh/chậm, resource saturation | Queue age, in-flight và consumer metrics |
| YAML min4 không max mà fixed4 | Boot min-only dùng min làm max | Đọc Boot properties và factory runtime |
| Annotation muốn max8 nhưng YAML max5 | Annotation override factory cho endpoint | Inspect `@JmsListener(concurrency)` và actual container |
| Thấy 20 consumers dù max5 | Nhiều endpoints/replicas cùng queue | Đếm theo từng container và cluster |
| Business completion out of order | Consumers xử lý song song | Chọn grouping/ordering invariant |
| Topic nhận event trùng | Nhiều subscriptions thay vì competing consumers | Kiểm tra topic topology/shared subscription |
| Handler lỗi nhưng broker không redeliver | AUTO_ACK/transaction config | Test rollback, DLQ, session transacted |
| DB pool cạn sau tăng max | Concurrency vượt downstream capacity | Đo DB connections, locks, handler latency |
| Max8 mà throughput không tăng | CPU/DB/broker bottleneck | Profile trước khi tiếp tục tăng |
| Scheduled nhiều, active ít | Executor saturation hoặc invokers chưa ready | Thread dump, executor metrics, broker connection |
| Stop chậm khi max lớn | Invokers blocked/handler I/O/transaction | Receive timeout, shutdown grace, logs |

Tránh thay min/max, receiveTimeout, prefetch, DB pool và executor cùng lúc; sẽ rất khó xác định nguyên nhân cải thiện hoặc suy giảm.

## 22. Bài thực hành và checklist

**Bài 1 — Giải mã chuỗi:** trên Default container test, đặt `"1"`, `"3"`, `"3-3"`, `"2-5"`. In hai getters min/max và đối chiếu bảng ở mục 3.

**Bài 2 — Chứng minh fixed:** đặt `"4-4"` cho một queue test, quan sát core invokers khi queue rỗng. Tắt broker để thấy cấu hình min không bảo đảm broker-connected consumers mọi lúc.

**Bài 3 — Elastic burst:** đặt `"1-5"`, gửi đủ backlog và cho handler mất 300ms; đo scheduled/active theo thời gian, không tự kỳ vọng max5 luôn xuất hiện.

**Bài 4 — Boot min-only:** dùng `min-concurrency: 3` không có max và so với `factory.setConcurrency("3")`. Nêu sự khác nhau về min/max.

**Bài 5 — Annotation override:** factory `"2-5"`, endpoint A dùng default, endpoint B có `concurrency="1-8"`; đọc actual config của cả hai qua registry.

**Bài 6 — TaskExecutor:** dùng bounded pool nhỏ hơn tổng core consumers trong test; giải thích vì sao một số invokers scheduled nhưng không chạy.

**Bài 7 — Queue ordering:** gửi messages có sequence, so sánh một consumer và bốn consumers. Đo business completion order, không chỉ send order.

**Bài 8 — Topic:** thử topic non-shared với ba consumers, quan sát duplicates và giải thích khác competing queue consumers.

**Bài 9 — Transacted listener:** cho handler throw exception, quan sát redelivery/DLQ theo policy; chứng minh concurrency và transaction là hai vấn đề khác nhau.

**Bài 10 — Replicas:** chạy hai replicas có max4 trên cùng queue; kiểm kê tổng broker consumers, nhận diện vì sao không phải global cap4.

**Bài 11 — DB bottleneck:** tăng max khi DB pool nhỏ, đo thread waiting/SQL locks; tìm điểm throughput bão hòa.

**Bài 12 — Idle shrink:** tạo burst rồi rút tải, đo khi nào extra invokers rút về core. Liên hệ receiveTimeout, idleReceivesPerTaskLimit và maxMessagesPerTask.

**Bài 13 — Graceful shutdown:** dừng app giữa xử lý, đo in-flight, rollback/commit và idempotency sau restart.

**Bài 14 — Capacity planning:** ba replicas, năm endpoints, mỗi max6 thì trần theo cấu hình là **90 invoker tasks**. Không suy ra có 90 TCP connections.

**Checklist tự đánh giá:**
- [ ] Tôi nhớ **`"N" = min1/maxN`**, **`"N-N" = fixed N`** trong Default container.
- [ ] Tôi phân biệt min/max config với scheduled/active runtime.
- [ ] Tôi biết cấu hình Java factory, annotation và Boot YAML, cùng thứ tự ưu tiên.
- [ ] Tôi không nhầm Boot min-only với chuỗi `setConcurrency("N")`.
- [ ] Tôi hiểu queue ordering và topic subscription bị tác động khi concurrency >1.
- [ ] Tôi tính đúng số consumers tối đa qua nhiều endpoints và replicas.
- [ ] Tôi không đồng nhất consumers, sessions, threads và physical connections.
- [ ] Tôi quan sát TaskExecutor, broker credit/prefetch, receive timeout và idle limits.
- [ ] Tôi không coi concurrency là giải pháp transaction/ACK/idempotency.
- [ ] Tôi chạy benchmark có kiểm chứng thay vì luôn đặt max càng lớn càng tốt.

**Câu hỏi chốt:** “`concurrency="5"` có giống `concurrency="5-5"` không?” — **Không.** Với Spring JMS `DefaultMessageListenerContainer`, dạng đầu là một **giới hạn tối đa** với min1; dạng sau là **năm consumers cố định**. Chọn rõ theo yêu cầu về thời gian phản hồi và tài nguyên.

## Tài liệu tham khảo chính thức

1. [Spring Framework 6.2 — DefaultMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html): `setConcurrency(String)`, min/max, scaling, idle limits, thread executor, ordering/topic.
2. [Spring Framework 6.2 — @JmsListener Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/annotation/JmsListener.html): `concurrency` có dạng `"N"` hoặc `"MIN-MAX"`, ghi đè factory cho endpoint.
3. [Spring Framework — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html): ví dụ `setConcurrency("3-10")` với Default factory.
4. [Spring Framework 6.2 — DefaultJmsListenerContainerFactory Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html): cách tạo container và cấu hình concurrency.
5. [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): `spring.jms.listener.min-concurrency`, `max-concurrency`, receive timeout.
6. [Spring Boot 3.5 — JMS Reference](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html): JMS auto-configuration, Artemis và listener transactions.
7. [Spring Boot 3.5 — Messaging How-to](https://docs.spring.io/spring-boot/3.5/how-to/messaging.html): `DefaultJmsListenerContainerFactoryConfigurer` và native ConnectionFactory.
8. [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): `Session`, `MessageConsumer`, queue/topic, ACK, transaction và delivery.

**Kết luận:** hãy chọn min/max dựa trên **ý định rõ ràng**, dùng `"N-N"` khi cần fixed và `"MIN-MAX"` khi cần co giãn. Kiểm chứng cấu hình bằng getters của container thực tế, rồi kiểm chứng hiệu quả bằng queue age, handler latency, executor và DB pool — không chỉ nhìn giá trị max.