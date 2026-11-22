# autoStartup, phase và thứ tự bắt đầu hoặc dừng với @JmsListener (Spring JMS)

## 1. Bài toán: ứng dụng khởi động không có nghĩa consumer phải nhận ngay

Một dịch vụ Spring Boot có hai hoạt động: khởi tạo tài nguyên phục vụ xử lý đơn hàng và tiêu thụ sự kiện JMS từ queue `orders.in`. Nếu listener nhận message khi nguồn dữ liệu hoặc dependency chưa sẵn sàng, xử lý có thể thất bại ngay trong quá trình deploy. Ngược lại, khi shutdown, nếu nguồn dữ liệu bị đóng trước nhưng listener vẫn đang xử lý thì message đang chạy có thể bị lỗi hoặc phải redeliver.

Chúng ta cần kiểm soát ba quyết định khác nhau:

1. **`autoStartup`:** listener container có tự bắt đầu hoạt động khi Spring `ApplicationContext` refresh hay không?
2. **`phase`:** khi các đối tượng `SmartLifecycle` tự khởi động/dừng trong cùng context, thành phần nào được **yêu cầu start trước**, thành phần nào được **yêu cầu stop trước**?
3. **Điều khiển runtime:** khi đã khởi động ứng dụng, ai được phép gọi `start()`/`stop()` đối với một listener cụ thể, và chuyện gì xảy ra với message đang xử lý?

Ví dụ đích đến:

```text
                   KHI KHỞI ĐỘNG
Spring tạo beans / endpoint / listener container
                       |
                       v
          Kiểm tra autoStartup
                       |
                +------+------+
                |             |
               true          false
                |             |
                v             v
       lifecycle start    giữ container
       theo phase         ở trạng thái chưa chạy
                |             |
                v             v
       nhận message      chờ explicit start()
                |
                v
       @JmsListener xử lý

                   KHI SHUTDOWN
Spring yêu cầu stop các SmartLifecycle:
phase cao trước -> phase thấp sau
          |
listener ngừng nhận/drain theo khả năng & cấu hình
          |
dependency cần dùng có thể dừng sau listener
```

**Trọng tâm:** trong Spring JMS 6.x, `@JmsListener` **không khai báo trực tiếp** thuộc tính `autoStartup` hoặc `phase`. Hai thiết lập này thuộc **listener container** hoặc **`JmsListenerContainerFactory`**, rồi được điều phối bởi `JmsListenerEndpointRegistry` và Spring lifecycle processor.

## 2. Phân biệt annotation, factory, container và registry

Nhìn vào một endpoint:

```java
@JmsListener(
        id = "ordersWorker",
        destination = "orders.in",
        containerFactory = "controlledJmsListenerFactory")
public void consume(String body) {
    orderService.process(body);
}
```

Đây là **đoạn method minh họa** trong Spring bean đã được quản lý; `orderService` được inject, không phải chương trình Java độc lập.

| Thành phần | Vai trò lifecycle |
| --- | --- |
| `@JmsListener` | Khai báo endpoint, `id`, `destination`, `containerFactory`, `selector`, `concurrency`... |
| `DefaultJmsListenerContainerFactory` | Tạo `DefaultMessageListenerContainer` cho endpoint; có `setAutoStartup(boolean)` và `setPhase(int)` |
| `DefaultMessageListenerContainer` | Thực tế sở hữu consumer/session, điều khiển `start()`, `stop()`, trạng thái `isRunning()` |
| `JmsListenerEndpointRegistry` | Đăng ký/tra cứu/quản lý tập listener containers do `@JmsListener` tạo; bản thân cũng tham gia `SmartLifecycle` |
| `DefaultLifecycleProcessor` của Spring | Điều phối start/stop các lifecycle components theo `phase` trong một `ApplicationContext` |
| Broker JMS | Giữ và phân phối message; broker không biết bean lifecycle phase của Spring |

Một phương thức như:

```java
@JmsListener(
        destination = "orders.in",
        autoStartup = "false", // SAI: không phải thuộc tính @JmsListener ở Spring JMS 6.2.
        phase = 100)           // SAI: không phải thuộc tính @JmsListener.
public void consume(String body) {}
```

là **phản ví dụ cố ý**, **không biên dịch**. Không sao chép cách cấu hình lifecycle trong `@KafkaListener` sang `@JmsListener` rồi cho rằng hai annotation có cùng tập thuộc tính.

Cấu hình đúng của Spring JMS sẽ đặt hai giá trị đó vào `DefaultJmsListenerContainerFactory`:

```java
DefaultJmsListenerContainerFactory factory =
        new DefaultJmsListenerContainerFactory();
factory.setConnectionFactory(connectionFactory);
factory.setAutoStartup(false);
factory.setPhase(100);
```

Đoạn này giả định có biến `jakarta.jms.ConnectionFactory connectionFactory` trong một method cấu hình. Nó chỉ minh họa các setter, chưa tạo đầy đủ Spring context.

## 3. autoStartup: tạo endpoint khác với bắt đầu tiêu thụ

`DefaultMessageListenerContainer` kế thừa khả năng `setAutoStartup(boolean)` từ `AbstractJmsListeningContainer`:

- **`true`**, giá trị mặc định của container: container được phép tự khởi động trong lifecycle refresh theo cơ chế registry/context.
- **`false`:** container vẫn được tạo, đăng ký và có cấu hình destination/handler, nhưng không tự nhận message chỉ vì ứng dụng vừa refresh. Nó có thể được bắt đầu bằng một lời gọi `start()` tường minh.

Đây là hai trạng thái khác nhau:

| Trạng thái | `@JmsListener` endpoint tồn tại? | Container chạy? | Consumer nhận message? |
| --- | --- | --- | --- |
| Đã đăng ký, `autoStartup=false`, chưa `start` | Có | Chưa chạy | Không, đối với container đó |
| Đã gọi `start()` thành công ở cấp lifecycle | Có | `isRunning()` có thể thành `true` | Có thể bắt đầu nhận nếu kết nối/broker/selector hợp lệ |
| Đã gọi `stop()` và kết thúc dừng | Có | `false` | Container ấy không còn tiếp tục nhận |
| Ứng dụng khác vẫn có consumer trên cùng queue | Không liên quan | Tùy ứng dụng khác | Các consumer khác vẫn có thể nhận |

**Đừng nhầm `autoStartup=false` với “vô hiệu hóa annotation”.** Spring vẫn phát hiện endpoint; bean listener và các dependency vẫn phải khởi tạo đúng. Nó cũng **không** tạm dừng toàn bộ queue ở broker, không stop những consumer từ instance khác, không ngăn producer gửi message.

### 3.1. Khi nào nên tắt autoStartup?

Các ví dụ hợp lý:

- Chỉ cho phép tiêu thụ sau khi một bước readiness hoặc migration thực tế thành công.
- Cần tách deployment ứng dụng khỏi thời điểm bật consumer (cutover/blue-green).
- Dịch vụ được khởi động trước nhưng chỉ consume trong một cửa sổ vận hành được phê duyệt.
- Cần vận hành dry-run kiểm tra kết nối/configuration rồi mới bật nhận thực tế.
- Trong môi trường demo, muốn gửi nhiều message vào queue trước khi chủ động start listener.

`autoStartup=false` **không tự thực hiện readiness check**; application phải thiết kế ai kiểm tra và ai gọi `start`.

### 3.2. Spring Boot: property toàn cục so với factory tự tạo

Khi sử dụng **default listener factory do Spring Boot tự cấu hình**, Spring Boot 3.4 hỗ trợ:

```yaml
spring:
  jms:
    listener:
      auto-startup: false
```

Đó là cấu hình `spring.jms.listener.auto-startup`, mặc định `true`. Nó ảnh hưởng cấu hình factory mặc định do Boot cung cấp (và những factory được tạo qua Boot configurer theo cách phù hợp).

Nếu ứng dụng **tự tạo** bean `DefaultJmsListenerContainerFactory` mà không dùng Boot `DefaultJmsListenerContainerFactoryConfigurer`, đừng giả định property đó tự đổi factory của mình. Hãy đặt trực tiếp `factory.setAutoStartup(false)` hoặc để Boot configurer cấu hình factory rồi override giá trị có chủ ý.

Không có property Spring Boot phổ quát tên `spring.jms.listener.phase` trong bộ thuộc tính chuẩn 3.4. Nếu muốn chọn phase bằng YAML trong một custom factory, đó là **property do ứng dụng tự định nghĩa**, ví dụ `app.jms.listener-phase`.

## 4. phase: thứ tự start ngược với thứ tự stop

`DefaultMessageListenerContainer` thực thi `SmartLifecycle` thông qua các lớp cha. Quy tắc trong Spring `SmartLifecycle` rất rõ:

- Khi context startup, thành phần phase **nhỏ hơn được start trước** thành phần phase lớn hơn.
- Khi context shutdown, thành phần phase **lớn hơn được stop trước** thành phần phase nhỏ hơn.
- Các thành phần có **cùng phase** không được hứa có thứ tự riêng bên trong phase.
- `SmartLifecycle.DEFAULT_PHASE` là `Integer.MAX_VALUE`. `AbstractJmsListeningContainer` mặc định dùng phase này, nghĩa là thường start khá muộn và stop khá sớm so với các bean lifecycle ở phase thấp hơn.
- `Lifecycle` thường (không phải `SmartLifecycle`) được Spring lifecycle processor coi như phase 0 nếu không có quy tắc đặc biệt.
- Quan hệ bean `depends-on` tường minh có thể ưu tiên hơn phase theo đặc tả `SmartLifecycle`. Tuy nhiên các listener containers do registry tạo **không đơn giản là bean cùng tên endpoint**, nên không thể chỉ gắn `@DependsOn` lên method listener để ép trình tự start của từng container.

Ví dụ:

| Thành phần | Phase | Start | Stop |
| --- | ---: | --- | --- |
| Bộ chuẩn bị dependency (SmartLifecycle) | `0` | Trước | Sau |
| Registry chứa JMS listeners | `100` | Sau dependency | Trước dependency |

Timeline:

```text
START:
  phase 0:   prerequisite.start() kết thúc
                         |
  phase 100: registry/JMS listener containers start
                         |
             các consumer mới bắt đầu nhận khi provider sẵn sàng

STOP:
  phase 100: registry/JMS listener containers stop
                         |
  phase 0:   prerequisite.stop()
```

Đây là **thứ tự yêu cầu lifecycle**. Nó **không phải** lời hứa rằng consumer đã kết nối broker ngay khi `start()` trả về, rằng dependency đã khỏe nếu `start()` tự chạy nền rồi trả về, hoặc rằng mọi tác vụ nghiệp vụ đã hoàn thành vào một deadline cố định.

### 4.1. phase không phải delay, priority hay thứ tự message

`setPhase(100)` **không** có nghĩa chờ 100 giây, giữ 100 message, có 100 thread, hay message có JMS priority 100.

Các khái niệm cần phân biệt:

- `phase`: thứ tự start/stop giữa Spring lifecycle components.
- `autoStartup`: tự start khi context refresh hay chờ lệnh.
- `concurrency`: số concurrent consumers được container dùng.
- `receiveTimeout`: thời gian chờ một lần nhận trong container dùng receive loop.
- `JMSPriority`: mức ưu tiên 0–9 của **message**, do JMS provider xử lý theo policy.
- `JMS transaction/acknowledgment`: xác nhận/rollback xử lý JMS theo cấu hình.

### 4.2. Một lưu ý quan trọng: registry có phase chung

Với `@JmsListener`, mỗi method annotated được đăng ký thành một container dưới sự quản lý của `JmsListenerEndpointRegistry`. Registry chính là thành phần tham gia `SmartLifecycle` của Spring context.

Trong implementation Spring JMS 6.2, registry thống nhất phase dựa trên containers mà nó tạo; nếu các factory tạo ra containers với **những custom phase xung đột**, registry có thể báo lỗi phase mismatch. Vì thế **không nên** cấu hình endpoint A phase 10 và endpoint B phase 20 bằng hai factories rồi dựa vào đó để buộc A start trước B trong cùng registry.

Nếu cần trình tự cụ thể giữa **hai endpoint trong cùng registry**, hãy sử dụng điều phối bằng **ID + explicit start/stop** và điều kiện sẵn sàng thực tế (hoặc thiết kế chúng ở các lifecycle/context độc lập phù hợp), chứ không nhầm phase của registry thành scheduler riêng cho từng annotated method.

**Kết luận:** `phase` thường hữu ích nhất để đặt **cả nhóm listener JMS** sau một prerequisite chung khi startup và trước prerequisite ấy khi shutdown.

## 5. Ví dụ Java 17 độc lập: tự tính thứ tự phase

Trước khi tích hợp Spring, ta có thể mô phỏng quy tắc sắp xếp bằng Java 17 thuần. File `PhaseOrderDemo.java`:

```java
import java.util.Comparator;
import java.util.List;

public class PhaseOrderDemo {
    record Unit(String name, int phase) {}

    public static void main(String[] args) {
        List<Unit> units = List.of(
                new Unit("jms-registry", 100),
                new Unit("datastore", 0));

        units.stream()
                .sorted(Comparator.comparingInt(Unit::phase))
                .forEach(unit -> System.out.println(
                        "START " + unit.name() + " phase=" + unit.phase()));

        units.stream()
                .sorted(Comparator.comparingInt(Unit::phase).reversed())
                .forEach(unit -> System.out.println(
                        "STOP " + unit.name() + " phase=" + unit.phase()));
    }
}
```

Chạy:

```bash
javac PhaseOrderDemo.java
java PhaseOrderDemo
```

Stdout chính xác:

```text
START datastore phase=0
START jms-registry phase=100
STOP jms-registry phase=100
STOP datastore phase=0
```

Chương trình này **chỉ mô phỏng quy tắc phase bằng cách sort**; không có Spring, JMS, listener registry hoặc broker. Trong Spring thực, lifecycle processor xử lý thêm phụ thuộc bean, autoStartup, callback shutdown và timeout; không dùng chương trình demo để tuyên bố đã kiểm thử lifecycle framework.

## 6. Dự án Spring Boot 3.x/Java 17+: listener khởi động thủ công

Ví dụ dùng Spring Boot 3.4.x, Java 17+, ActiveMQ Artemis và `jakarta.jms`. Điểm chính: ứng dụng có `@JmsListener` nhưng **không tự consume khi context startup**. Chỉ khi bật profile demo quản trị hoặc gọi `start()` rõ ràng, container mới bắt đầu hoạt động.

Yêu cầu môi trường:

- JDK 17+ và Gradle tương thích với Spring Boot 3.4.x.
- Broker Artemis đã chạy tại `tcp://localhost:61616` hoặc URL do bạn cung cấp.
- Queue `orders.lifecycle` tồn tại (hoặc broker cho phép auto-create theo policy).
- Tài khoản broker có quyền gửi/nhận phù hợp.
- Không chạy consumer bên ngoài cùng queue khi muốn quan sát demo theo một consumer.

### 6.1. Cấu trúc tệp

```text
jms-lifecycle-demo/
  settings.gradle
  build.gradle
  src/main/resources/application.yml
  src/main/java/demo/lifecycle/LifecycleApplication.java
  src/main/java/demo/lifecycle/JmsLifecycleConfiguration.java
  src/main/java/demo/lifecycle/OrdersListener.java
  src/main/java/demo/lifecycle/ManualStartAfterReady.java
  src/main/java/demo/lifecycle/PublishDemoRunner.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'jms-lifecycle-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.13'
    id 'io.spring.dependency-management' version '1.1.7'
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
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Ví dụ này cố định phiên bản để tránh thay đổi hành vi do nâng major version. Nếu project thực tế đã có Spring Boot plugin hoặc BOM, hãy dùng dependency management hiện có; không trộn nhiều version Spring Framework khác nhau.

### 6.2. application.yml

File `src/main/resources/application.yml`:

```yaml
spring:
  artemis:
    mode: native
    broker-url: "${JMS_BROKER_URL:tcp://localhost:61616}"
    user: "${JMS_USER}"
    password: "${JMS_PASSWORD}"
  lifecycle:
    timeout-per-shutdown-phase: 20s

app:
  jms:
    queue: "${JMS_ORDERS_QUEUE:orders.lifecycle}"
    auto-start: "${JMS_AUTO_START:false}"
    listener-phase: "${JMS_LISTENER_PHASE:100}"
```

Giải thích:

- `spring.artemis.*` là cấu hình kết nối JMS của Spring Boot.
- `spring.lifecycle.timeout-per-shutdown-phase` là giới hạn thời gian mà lifecycle processor dành cho **một phase shutdown**, ở đây chọn 20 giây để minh họa. Nó không bảo đảm một business transaction chậm sẽ luôn kết thúc sạch trong thời hạn này.
- `app.jms.auto-start` và `app.jms.listener-phase` là **hai property tùy biến** của ví dụ; không phải tên property mặc định của Spring Boot.
- Giá trị `auto-start=false` và `listener-phase=100` được inject vào factory trong bước tiếp theo. Thay chúng bằng biến môi trường khi chạy nhiều chế độ.
- Dùng secrets thật qua hệ thống quản lý credentials, không commit password vào repository.

### 6.3. Spring Boot application

File `src/main/java/demo/lifecycle/LifecycleApplication.java`:

```java
package demo.lifecycle;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.jms.annotation.EnableJms;

@SpringBootApplication
@EnableJms
public class LifecycleApplication {
    public static void main(String[] args) {
        SpringApplication.run(LifecycleApplication.class, args);
    }
}
```

`@EnableJms` bật phát hiện annotation-driven JMS endpoints. Với Spring Boot đã cấu hình JMS, quá trình này thường cũng được auto-configuration hỗ trợ; khai báo tường minh ở đây nhằm giải thích cách đăng ký listener trong một project khép kín.

### 6.4. Factory thiết lập autoStartup và phase

File `src/main/java/demo/lifecycle/JmsLifecycleConfiguration.java`:

```java
package demo.lifecycle;

import jakarta.jms.ConnectionFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration(proxyBeanMethods = false)
public class JmsLifecycleConfiguration {

    @Bean("controlledJmsListenerFactory")
    public DefaultJmsListenerContainerFactory controlledJmsListenerFactory(
            ConnectionFactory connectionFactory,
            @Value("${app.jms.auto-start:false}") boolean autoStart,
            @Value("${app.jms.listener-phase:100}") int phase) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        factory.setConcurrency("1");
        factory.setAutoStartup(autoStart);
        factory.setPhase(phase);
        return factory;
    }
}
```

Phân tích các lựa chọn:

1. `DefaultJmsListenerContainerFactory` tạo listener container cho endpoint tham chiếu đến factory này.
2. `setAutoStartup(false)`: trong demo mặc định, container **không tự bắt đầu** khi refresh context.
3. `setPhase(100)`: nếu lifecycle auto-start được bật, nhóm listener tham gia thứ tự phase 100 tương đối với các `SmartLifecycle` khác. Khi start thủ công, phase **không** tự gây trì hoãn theo đồng hồ.
4. `setConcurrency("1")`: giới hạn một consumer trong **container của endpoint**, không giới hạn tổng các replica đang chạy ở nhiều JVM.
5. `setSessionTransacted(true)`: dùng local JMS session transaction; khi handler ném exception ra container, container có thể rollback để provider redeliver theo chính sách. Điều này không làm transaction JMS và database bên ngoài trở thành atomic.

Ví dụ có một factory cho một endpoint để tránh xung đột phase. Nếu dùng nhiều factory và nhiều endpoint trong cùng registry, cần kiểm tra chúng có lifecycle phase tương thích.

### 6.5. Method @JmsListener có ID cố định

File `src/main/java/demo/lifecycle/OrdersListener.java`:

```java
package demo.lifecycle;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrdersListener {

    @JmsListener(
            id = "ordersWorker",
            destination = "${app.jms.queue}",
            containerFactory = "controlledJmsListenerFactory")
    public void onOrder(String payload) {
        if (payload == null || payload.isBlank()) {
            throw new IllegalArgumentException("Empty order event");
        }
        System.out.println("RECEIVED " + payload);
    }
}
```

`id = "ordersWorker"` là khóa dùng bởi `JmsListenerEndpointRegistry.getListenerContainer("ordersWorker")`. Nếu không đặt `id`, Spring tự sinh ID, khiến code quản trị khó tham chiếu ổn định qua triển khai.

**Cẩn thận:** việc `@JmsListener` được đăng ký và class `OrdersListener` đã tồn tại **không chứng minh** consumer đã chạy khi `autoStartup=false`. Đó là mục tiêu của ví dụ.

### 6.6. Chỉ bật listener sau ApplicationReadyEvent trong profile demo

File `src/main/java/demo/lifecycle/ManualStartAfterReady.java`:

```java
package demo.lifecycle;

import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.annotation.Profile;
import org.springframework.context.event.EventListener;
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.listener.MessageListenerContainer;
import org.springframework.stereotype.Component;

@Component
@Profile("manual-demo")
public class ManualStartAfterReady {

    private final JmsListenerEndpointRegistry registry;

    public ManualStartAfterReady(JmsListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void startAfterReady() {
        MessageListenerContainer container =
                registry.getListenerContainer("ordersWorker");

        if (container == null) {
            throw new IllegalStateException(
                    "JMS endpoint ordersWorker is not registered");
        }

        if (!container.isRunning()) {
            container.start();
            System.out.println("MANUAL_START_CALLED");
        }
    }
}
```

Ở đây profile `manual-demo` là **chủ ý bật start khi ApplicationReadyEvent xảy ra**. `ApplicationReadyEvent` chỉ nói Spring Boot startup đã đi đến mốc ứng dụng sẵn sàng; **không chứng minh** database/remote service/broker có đáp ứng dependency readiness theo nghiệp vụ. Nếu production cần một điều kiện thật như migration hoàn tất hoặc dịch vụ downstream đạt health-check, phải kiểm tra điều kiện đó **trước `container.start()`**, hoặc không bật profile/không gửi lệnh start cho tới khi có bằng chứng.

Gọi `container.start()` có thể tạo và khởi chạy consumer tasks, nhưng một lần gọi thành công không chứng minh broker đã sẵn sàng nhận/dispatch tại thời điểm đó. `isRunning()` là **lifecycle state**, không phải chỉ số queue lag bằng 0 hay consumer đã xử lý xong.

### 6.7. Producer thử nghiệm

File `src/main/java/demo/lifecycle/PublishDemoRunner.java`:

```java
package demo.lifecycle;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Profile;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@Component
@Profile("publish-demo")
public class PublishDemoRunner implements ApplicationRunner {

    private final JmsTemplate template;
    private final String destination;

    public PublishDemoRunner(
            JmsTemplate template,
            @Value("${app.jms.queue}") String destination) {
        this.template = template;
        this.destination = destination;
    }

    @Override
    public void run(ApplicationArguments args) {
        template.convertAndSend(
                destination, "OrderCreated:ORDER-1001");
        System.out.println("PUBLISH_FINISHED");
    }
}
```

Profile `publish-demo` gửi **một message mỗi lần khởi động**. Vì mặc định của ví dụ là `auto-start=false` và không có profile `manual-demo`, chính process gửi này **không tự consume** message. Broker phải có queue và chấp nhận message; đây không phải giả định về việc consumer có chạy hay không ở process khác.

### 6.8. Chạy và quan sát

Đặt `JMS_USER` và `JMS_PASSWORD` của broker trong môi trường, sau đó dùng Gradle wrapper đã được tạo cho project (hoặc tạo wrapper bằng Gradle phù hợp):

```bash
# 1. Gửi message, không chủ động khởi động listener trong process này.
./gradlew bootRun --args='--spring.profiles.active=publish-demo'

# 2. Dừng process thử nghiệm trên, rồi chạy một process có profile manual-demo.
./gradlew bootRun --args='--spring.profiles.active=manual-demo'
```

Trên Windows dùng `gradlew.bat` thay cho `./gradlew`. Ví dụ có thể được chạy từ IDE với đúng profile, JDK, broker và credentials tương ứng.

Nếu kết nối broker/queue ổn, process publish có thể in:

```text
PUBLISH_FINISHED
```

Process `manual-demo` có thể in:

```text
MANUAL_START_CALLED
RECEIVED OrderCreated:ORDER-1001
```

Đây chỉ là **các dòng ứng dụng có thể xuất hiện**; Spring Boot còn in log khác, kết nối broker và xử lý bất đồng bộ không có lịch tuyệt đối. Hai dòng trong `manual-demo` không phải một hợp đồng ordering với mọi broker/version; thread listener có thể chạy gần như ngay sau `start()` và log `RECEIVED` có thể xuất hiện trước `MANUAL_START_CALLED`. Nếu queue đã được consumer khác lấy mất, có thể chỉ thấy `MANUAL_START_CALLED`. Nếu broker chưa sẵn sàng, container có thể ở trạng thái đang retry kết nối.

**Không dùng profile `publish-demo` và `manual-demo` trong production** nếu không muốn mỗi lần khởi động tự gửi dữ liệu hoặc tự bật nhận một cách khó kiểm soát.

## 7. Ví dụ thêm: SmartLifecycle prerequisite phase 0

Để minh họa phase giữa listener registry và một thành phần lifecycle khác, bổ sung một bean chỉ dùng khi chạy profile `phase-demo`.

File `src/main/java/demo/lifecycle/PrerequisiteLifecycle.java`:

```java
package demo.lifecycle;

import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("phase-demo")
public class PrerequisiteLifecycle implements SmartLifecycle {
    private volatile boolean running;

    @Override
    public void start() {
        // Demo: phase 0 giả lập rằng prerequisite đã khởi động.
        // Production phải kiểm tra readiness thật trước khi trả về.
        System.out.println("PREREQUISITE_START phase=0");
        running = true;
    }

    @Override
    public void stop() {
        System.out.println("PREREQUISITE_STOP phase=0");
        running = false;
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }

    @Override
    public int getPhase() {
        return 0;
    }
}
```

`SmartLifecycle.stop(Runnable)` có default implementation gọi `stop()` rồi thông báo callback; với service thực có shutdown bất đồng bộ, có thể cần implement `stop(Runnable)` đúng cách để lifecycle processor chờ cho tới khi đã dừng. Không được quên gọi callback khi hoàn tất.

Để chạy scenario phase, phải **bật auto-start thực sự**, khác scenario manual:

```bash
JMS_AUTO_START=true ./gradlew bootRun --args='--spring.profiles.active=phase-demo'
```

Lệnh shell theo cú pháp Unix. Với PowerShell, có thể đặt biến môi trường trước bằng `$env:JMS_AUTO_START="true"` rồi chạy `gradlew.bat`; trên Windows không dùng cú pháp gán biến ở đầu dòng như Bash.

Khi context startup, lifecycle processor yêu cầu `PrerequisiteLifecycle` phase 0 start trước nhóm listener phase 100. Khi context shutdown chuẩn, nhóm listener phase 100 được yêu cầu stop trước khi `PrerequisiteLifecycle` phase 0 stop. Không có giả định rằng stdout của mọi JMS thread luôn có thứ tự cố định trong lúc broker nhận message.

**Điều kiện quyết định:** nếu một dependency có startup bất đồng bộ nhưng `start()` trả về trước khi dependency thực sự ready, phase 0 vẫn có thể kết thúc trước readiness thật. Khi đó phase 100 **không** tự đợi health check; cần readiness gate riêng.

### 7.1. Khi muốn chọn phase, hỏi điều gì?

Ví dụ:

- “Listener phải chỉ bắt đầu sau khi dữ liệu reference cache hoàn tất?” → chuẩn bị cache/validate thành công ở component phase thấp, rồi start listener phase cao, hoặc manual start sau readiness.
- “Listener phải dừng trước khi database pool bị đóng?” → yêu cầu phase listener cao hơn component lifecycle quản lý dependency (đồng thời kiểm tra cơ chế shutdown của bean thực tế).
- “Listener A phải start trước Listener B nhưng cả hai dùng cùng `@JmsListener` registry?” → không dùng hai custom phase khác nhau một cách tùy tiện; registry có group-phase constraints. Dùng explicit orchestration theo ID hoặc tách lifecycle kiến trúc.
- “Chỉ muốn đợi 10 giây rồi mở consumer?” → phase **không** cung cấp delay thời gian; dùng một điều kiện/scheduler điều phối rõ ràng, không gán phase 10.

## 8. Quản lý listener cụ thể bằng JmsListenerEndpointRegistry

`JmsListenerEndpointRegistry` quản lý các listener containers tạo bởi `@JmsListener`. Khi endpoint có `id` cố định, có thể lấy đúng container để điều khiển.

Ví dụ class **service có API nội bộ**, không phải HTTP endpoint:

```java
package demo.lifecycle;

import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.listener.MessageListenerContainer;
import org.springframework.stereotype.Service;

@Service
public class OrdersConsumerControl {

    private final JmsListenerEndpointRegistry registry;

    public OrdersConsumerControl(JmsListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    private MessageListenerContainer getContainer() {
        MessageListenerContainer container =
                registry.getListenerContainer("ordersWorker");
        if (container == null) {
            throw new IllegalStateException(
                    "Listener ordersWorker does not exist");
        }
        return container;
    }

    public void start() {
        getContainer().start();
    }

    public void stop() {
        getContainer().stop();
    }

    public boolean isRunning() {
        return getContainer().isRunning();
    }

    public int phase() {
        return getContainer().getPhase();
    }

    public boolean isAutoStartup() {
        return getContainer().isAutoStartup();
    }
}
```

Các method `start/stop` trên đây được dùng khi một **operator flow đã được bảo vệ, xác thực và có quyền** quyết định bật/tắt consumer; không tự lộ chúng thành HTTP API công khai không kiểm soát.

- Gọi `getListenerContainer("ordersWorker")` để không ảnh hưởng endpoint khác.
- Gọi `registry.start()` sẽ là **lệnh start cho tập containers được registry quản lý**, không phải chỉ riêng endpoint `ordersWorker`. Sau khi context đã refresh, start tường minh có thể khởi động cả những container `autoStartup=false`.
- Gọi `registry.stop()` tương tự tác động nhiều containers.
- `isRunning() == true` chỉ là trạng thái lifecycle tại thời điểm đọc; không đồng nghĩa đang có message in-flight, đã kết nối broker khỏe, hay backlog bằng 0.
- `container.start()`/`stop()` có thể được gọi ở runtime, nhưng không nên spam lệnh qua nhiều thread/operator vì sẽ khó kiểm soát in-flight và trạng thái cuối.

### 8.1. Bật lại sau khi dừng

Mô hình có thể là:

```text
Registered, autoStartup=false
       |
  operator.start()
       v
    Running ---- operator.stop() ----> Stopped
       ^                                  |
       |------------ operator.start() ----|
```

Đây là sơ đồ lifecycle ở cấp ứng dụng. Container có thể phải kết nối lại broker và tạo consumer khi bật lại; stop không xóa queue hoặc mọi message chưa xử lý. Message vẫn có thể còn trên broker để được xử lý tiếp, tùy delivery/expiration/transaction/provider policy.

### 8.2. Khi listener được đăng ký động sau context refresh

`autoStartup` chủ yếu quyết định **tự khởi động trong quá trình refresh context**. Với endpoint được đăng ký động sau thời điểm context đã refresh, hành vi start còn phụ thuộc cách gọi `JmsListenerEndpointRegistry.registerListenerContainer(...)` và cờ start-immediately; implementation có thể cố ý start ngay theo hợp đồng lifecycle. Vì vậy cần test trường hợp **dynamic registration** của version Spring đang dùng thay vì mặc định suy rằng mọi container `autoStartup=false` sẽ đứng yên trong mọi luồng đăng ký muộn.

Ví dụ trong bài dùng annotation endpoints được phát hiện ở startup thông thường, không minh họa dynamic registration.

## 9. Shutdown: dừng nhận khác với hoàn tất mọi tác vụ đang chạy

Khi có tín hiệu shutdown, Spring dùng lifecycle processor điều phối `stop(Runnable)` cho `SmartLifecycle` theo **phase giảm dần**. Với listener phase 100 và prerequisite phase 0, listener được yêu cầu dừng trước, sau đó dependency được dừng.

Nhưng vẫn cần phân biệt:

1. **Ngừng lấy message mới:** listener container dừng tạo hoạt động nhận tiếp theo trong phạm vi chính nó.
2. **Xử lý message đang chạy:** các consumer tasks có thể đang thực hiện business logic.
3. **JMS ACK/commit/rollback:** transaction có thể chưa kết thúc; nếu thất bại, message có thể redeliver.
4. **Dọn tài nguyên JMS:** session/consumer/connection cần được đóng theo lifecycle provider.
5. **Dừng dependency:** database pool hoặc external resource không nên bị ngắt trước khi handler cần dùng đã xong, trong phạm vi shutdown policy.

Vì vậy, **phase là thứ tự gọi stop**, không phải phép màu bảo đảm tất cả in-flight đã commit trước khi phần khác bị đóng. Cần cấu hình và kiểm chứng shutdown timeouts/cancellation phù hợp.

Ví dụ property:

```yaml
spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
```

Trong Spring Boot 3.4, property này đặt thời gian chờ cho mỗi shutdown phase. Giá trị 20 giây là tùy chọn minh họa, không phải lời hứa rằng một message xử lý 60 giây sẽ được hoàn tất trong 20 giây. Khi hết thời gian, lifecycle processor có thể tiếp tục với phase tiếp theo dù thành phần nào đó chưa dừng sạch.

### 9.1. Chuyện gì xảy ra với message chưa xử lý xong?

Phụ thuộc cấu hình:

- **Local JMS transaction:** một message đang xử lý chưa commit có thể rollback/redeliver nếu connection/session đóng hoặc lỗi ở ranh giới xử lý.
- **AUTO_ACKNOWLEDGE không transacted:** tùy container/provider, ACK có thể xảy ra **trước** body listener, nên exception hoặc shutdown có thể không làm message được gửi lại như bạn kỳ vọng.
- **Business database transaction:** một transaction DB có thể đã commit nhưng transaction JMS chưa commit; redelivery gây duplicate nếu thiếu idempotency.
- **Consumer khác trên queue:** ngay khi listener này dừng, consumer ở JVM khác có thể tiếp tục tiêu thụ; stop một endpoint không phải “đóng queue”.

Thiết kế ít nhất:

- Handler có timeout và cơ chế idempotency.
- Transaction/ack mode rõ ràng, định nghĩa retry và DLQ.
- Shutdown period đủ cho workload điển hình, nhưng vẫn có kế hoạch khi quá hạn.
- Metrics cho in-flight, queue age, redelivery và DLQ.
- Kịch bản restart sau khi kill process và broker reconnect.
- Không dùng `System.exit(0)` như cách “graceful stop listener”.

### 9.2. Thứ tự trong một phase không cố định

Nếu cả hai component có phase 100:

```text
phase=100: component A, component B
START: không nên yêu cầu A luôn start trước B
STOP:  không nên yêu cầu B luôn stop trước A
```

Spring có thể xử lý các lifecycle components cùng phase mà không hứa thứ tự ổn định. Cần chọn **phases khác nhau cho các lifecycle groups hợp lệ** hoặc quan hệ dependency thực sự, không dựa vào thứ tự đăng ký bean, tên method, thứ tự classpath hay thứ tự xuất hiện trong log.

Đối với **các endpoint cùng `JmsListenerEndpointRegistry`**, đừng cố vượt giới hạn group-phase bằng cách dựng factories xung đột phase; dùng explicit startup control hoặc tách cấu trúc khi thật sự cần ordering.

## 10. Kịch bản vận hành thực tế

### Kịch bản A — chỉ bật consumer sau migration

1. Deploy code có listener factory `autoStartup=false`.
2. Ứng dụng tạo Spring context và đăng ký listener, nhưng consumer ấy chưa nhận message.
3. Chạy migration hoặc kiểm tra phiên bản schema, access policy, dependency readiness.
4. Khi điều kiện **đã thực sự đạt**, operator/initializer gọi `getListenerContainer(id).start()`.
5. Theo dõi connection, consumer count, backlog và lỗi handler; rollback nếu có vấn đề.

Không dùng `ApplicationReadyEvent` như bằng chứng tự động rằng migration ngoài Spring đã hoàn tất.

### Kịch bản B — blue/green cutover

1. Blue đang consume queue; green deploy với `autoStartup=false`.
2. Xác minh green kết nối/config hợp lệ bằng các probe không tác động việc consume production.
3. Dừng listener blue và kiểm tra in-flight/transaction theo policy.
4. Bật green và quan sát backlog/redelivery/DLQ.
5. Giữ eventId/idempotency vì cutover vẫn có thể gặp duplicate hoặc message không chắc outcome.

Đừng mặc định stop một endpoint sẽ ngừng tất cả consumer blue ở mọi replica. Cần điều phối trên từng instance hoặc orchestration cấp dịch vụ.

### Kịch bản C — shutdown đúng thứ tự khi listener phụ thuộc cache

Một component `SmartLifecycle` chịu trách nhiệm cache có phase `0`; nhóm listener phase `100`. Khi startup, cache start trước, listener start sau. Khi shutdown, listener stop trước, cache stop sau.

Nếu cache startup thực sự async, cần cache chỉ đánh dấu ready sau khi load xong và sử dụng cơ chế kiểm tra/gating. Chỉ cấu hình phase không thay thế điều kiện readiness.

### Kịch bản D — tạm dừng xử lý vì downstream quá tải

Có thể gọi `container.stop()` trên endpoint cụ thể, giảm concurrency, hoặc áp dụng policy backpressure khác. Sau khi downstream phục hồi, gọi `start()`. Đừng dùng busy restart mỗi giây; mỗi lần dừng/bật có thể tạo/đóng consumer và tác động redelivery.

Nếu backlog lớn, start lại đột ngột có thể gây “thundering herd” khi nhiều replica cùng nhận. Hãy tính concurrency và hạn mức downstream.

## 11. Kiểm thử lifecycle: đừng chỉ đọc log

### 11.1. Unit-level kiểm tra phase rule

`PhaseOrderDemo` ở mục 5 đã cho kết quả Java 17 độc lập, nhưng test ấy **không kiểm tra Spring**. Với ứng dụng Spring, cần xác minh trạng thái registry/containers.

### 11.2. Integration test cần context và JMS provider phù hợp

Kiểm thử với broker thử nghiệm (embedded hoặc Testcontainers/Artemis setup tương thích), dùng endpoint ID `ordersWorker` và thiết lập `auto-start=false`:

| Bước | Kiểm tra | Kết luận mong đợi |
| --- | --- | --- |
| Context khởi tạo | `registry.getListenerContainer("ordersWorker") != null` | Endpoint đã được đăng ký |
| Chưa gọi `start()` | `container.isAutoStartup() == false`; `!container.isRunning()` | Container không tự chạy trong scenario bình thường |
| Gửi một message | Không thấy handler chạy trong thời gian quan sát có giới hạn, và queue vẫn có message nếu không có consumer khác | Container chưa consume |
| Gọi `container.start()` | `isRunning()` chuyển trạng thái; sau đó handler nhận message khi broker sẵn sàng | Manual start hoạt động |
| Gọi `container.stop()` | Sau khi stop ổn định, không nhận message mới qua container đó | Manual stop hoạt động |
| Khởi động lại | `container.start()` tiếp tục nhận | Restart runtime hoạt động |
| Shutdown context | Component phase cao bị stop trước phase thấp, theo tracer/lifecycle callbacks | Phase ordering đúng với cấu hình |
| Handler đang chạy khi stop | Ghi nhận in-flight, transaction outcome và redelivery | Không giả định “stop” đồng nghĩa commit |
| Broker down trước start | Container có thể retry/recover theo policy, `isRunning` không đủ chứng minh broker ready | Lifecycle state khác broker health |

Không dựa chỉ vào thứ tự `println` giữa nhiều threads. Dùng `CountDownLatch`, trạng thái registry, broker queue metrics và timeout điều kiện. Với phase ordering, dùng test lifecycle components có recorder thread-safe, không lấy thứ tự xử lý message làm bằng chứng cho thứ tự start của bean.

### 11.3. Mẫu test cấu hình bằng Spring context (phác thảo)

Trong một integration test đã khởi động context với property `app.jms.auto-start=false` và hạ tầng JMS phù hợp:

```java
@Autowired
JmsListenerEndpointRegistry registry;

@Test
void endpointIsRegisteredButNotStarted() {
    MessageListenerContainer container =
            registry.getListenerContainer("ordersWorker");

    assertNotNull(container);
    assertFalse(container.isAutoStartup());
    assertFalse(container.isRunning());
    assertEquals(100, container.getPhase());
}
```

Đây là **phác thảo các field/method trong một JUnit/Spring test class**, không phải một file Java độc lập. Cần import `@Autowired`, `@Test`, `MessageListenerContainer`, `JmsListenerEndpointRegistry` và assertions từ JUnit Jupiter. Kết quả `!isRunning()` chỉ đúng nếu test **không bật** profile/manual controller hoặc thực hiện start ở bước khác; trong môi trường có parallel integration tests, phải cô lập Spring context và endpoint registry.

Đặc biệt, test này không kiểm tra broker đã giao message hay local transaction đã rollback. Việc xác minh API configuration phải được bổ sung bằng integration test theo broker thực.

## 12. Troubleshooting

| Hiện tượng | Nguyên nhân đáng kiểm tra | Hướng xử lý |
| --- | --- | --- |
| `@JmsListener` có annotation nhưng không nhận message sau boot | `autoStartup=false` ở factory/default property, container chưa start | Tra registry ID, `isAutoStartup`, `isRunning`; gọi start khi được phép |
| Cố viết `autoStartup`/`phase` ngay trên `@JmsListener` | Sao chép từ cơ chế khác như Kafka | Đặt trên `JmsListenerContainerFactory`/container |
| Đổi `spring.jms.listener.auto-startup` nhưng endpoint không đổi | App dùng custom factory, không nhận Boot default configurer | Cấu hình trực tiếp custom factory hoặc dùng Boot configurer |
| Factory A phase 10, factory B phase 20 gây startup failure | Registry JMS có thể yêu cầu custom phases thống nhất | Dùng một phase registry/group; điều phối endpoint bằng ID |
| Phase cao nhưng listener vẫn nhận trước dependency sẵn sàng | Dependency `start()` trả sớm dù task async chưa ready | Readiness gate thực, manual start sau health/migration |
| Gọi `registry.start()` và nhiều listener cùng bật | Registry quản lý toàn bộ endpoints | Dùng `getListenerContainer(id).start()` nếu chỉ bật một |
| `container.start()` trả về, không có message | Broker offline, queue sai, selector, ACL, connection retry, queue rỗng | Kiểm tra broker health, container logs, metrics, destination |
| `container.isRunning() == true` nhưng lag lớn | Running không đồng nghĩa xử lý đủ nhanh | Quan sát queue age, throughput, consumer count, lỗi |
| Gọi `stop()` nhưng log xử lý vẫn xuất hiện | In-flight work/threads đang hoàn tất hoặc replica khác consume | Kiểm tra shutdown drain, transactions, tất cả instances |
| Dừng listener trước, DB đã ngừng rồi | Phase không đúng hoặc dependency không tham gia lifecycle như mong đợi | Xác định thực tế lifecycle bean/phase, quan hệ dependency |
| Dùng phase 100 để “chờ 100 giây” | Phase là thứ tự, không phải thời gian | Scheduler/gating theo thời điểm thực tế |
| Dừng/bật nhiều lần gây duplicate event | Transaction outcome không chắc, retry/redelivery | Idempotency, eventId, retry/DLQ phù hợp |
| Endpoint ID không tìm thấy | Bean chưa scan, factory lỗi, ID sai, context khác | Kiểm tra `@EnableJms`, component scan, registry ID |
| Khi deploy không có traffic nhưng broker vẫn hoạt động | Listener của instance này bị stop, message chờ hoặc consumer khác nhận | Xem trạng thái toàn hệ thống, không chỉ một JVM |

## 13. Quy tắc ra quyết định

Khi thiết kế một `@JmsListener` mới, hãy tự trả lời:

1. **Consumer nên nhận ngay khi ứng dụng startup?** Nếu có, giữ `autoStartup=true` trừ khi có ràng buộc riêng; nếu không, đặt `false` và chỉ rõ ai gọi start.
2. **Có dependency lifecycle cần start trước và stop sau?** Dùng phase hợp lý giữa các `SmartLifecycle` groups. Đừng gán phase khác nhau tùy tiện cho endpoints cùng registry.
3. **Có điều kiện readiness ngoài Spring context?** Dùng health-check/gate hoặc manual start; phase một mình không đủ.
4. **Có cần pause một endpoint mà không ảnh hưởng endpoint khác?** Dùng endpoint ID và `JmsListenerEndpointRegistry.getListenerContainer(id)`.
5. **Shutdown phải giữ consistency ra sao?** Chốt JMS transaction/ack, in-flight policy, idempotency, drain/timeout, retry và DLQ.
6. **Chạy nhiều instance cùng queue?** Phải điều phối mỗi instance; một lời gọi `stop` cục bộ không kiểm soát tất cả consumers.

**Ghi nhớ:** `autoStartup` quyết định *có tự khởi động hay không*, `phase` quyết định *thứ tự tương đối giữa lifecycle groups khi Spring start/stop*, còn `JmsListenerEndpointRegistry` cho phép *bật/tắt và quan sát runtime*. Ba cơ chế này **không** thay thế readiness kiểm chứng thực tế, graceful shutdown được thiết kế đúng, hoặc bảo đảm xử lý message của hệ thống nghiệp vụ.

### Tài liệu tham khảo

- Spring Framework 6.2 API — `JmsListener` (danh sách thuộc tính; không có `autoStartup`/`phase`): https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/annotation/JmsListener.html
- Spring Framework 6.2 API — `DefaultJmsListenerContainerFactory` và `AbstractJmsListenerContainerFactory`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html
- Spring Framework 6.2 API — `AbstractJmsListeningContainer` (`setAutoStartup`, `setPhase`, `isRunning`): https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/AbstractJmsListeningContainer.html
- Spring Framework 6.2 API — `JmsListenerEndpointRegistry` (`getListenerContainer`, `start`, `stop` và phase): https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/config/JmsListenerEndpointRegistry.html
- Spring Framework 6.2 API — `SmartLifecycle` (phase thấp start trước, phase cao stop trước): https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/SmartLifecycle.html
- Spring Boot 3.4 — Common Application Properties (`spring.jms.listener.auto-startup` và `spring.lifecycle.timeout-per-shutdown-phase`): https://docs.spring.io/spring-boot/3.4/appendix/application-properties/index.html
- Spring Boot 3.4 — JMS auto-configuration và Artemis: https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html
- Spring Framework source — `JmsListenerEndpointRegistry` (registry group phase và start-if-necessary): https://github.com/spring-projects/spring-framework/blob/main/spring-jms/src/main/java/org/springframework/jms/config/JmsListenerEndpointRegistry.java
