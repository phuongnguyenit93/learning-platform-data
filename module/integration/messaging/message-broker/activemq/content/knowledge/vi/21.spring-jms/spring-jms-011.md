# Quản lý khởi động, dừng và phục hồi kết nối của listener container

## 1. Ba trạng thái phải theo dõi riêng: lifecycle, kết nối và tiến độ xử lý

Trong Spring JMS, **@JmsListener** không tự sở hữu một vòng lặp đọc message độc lập. Spring đăng ký endpoint và tạo **message listener container**, thường là **DefaultMessageListenerContainer (DMLC)**. Container quản lý việc tạo JMS Connection/Session/Consumer, điều phối luồng nhận, khởi động, dừng và thử khôi phục khi kết nối tới broker lỗi.

Với ActiveMQ Artemis hoặc ActiveMQ Classic, “listener đang chạy” có thể mang ba nghĩa rất khác:

| Khía cạnh | Câu hỏi đúng | Bằng chứng nên kiểm tra |
| --- | --- | --- |
| **Lifecycle** | Container đã được yêu cầu start hay stop? | **isRunning()**, autoStartup, trạng thái trong **JmsListenerEndpointRegistry** |
| **Connectivity** | Container tạo được Connection/Session/Consumer tới broker và đăng ký nhận chưa? | Log recovery/connection, **consumer count** phía broker, lỗi authentication/TLS |
| **Progress** | Consumer có thực sự xử lý và ACK message đúng SLA? | ACK/dequeue rate, backlog age, delivering/in-flight, lỗi handler và downstream |

**isRunning() = true không phải health check cho broker**: DMLC có thể đã được yêu cầu start nhưng đang ở chu kỳ kết nối lại. Ngược lại, một listener bị stop có chủ đích có thể không có consumer trên broker dù ứng dụng HTTP vẫn khỏe.

~~~mermaid
stateDiagram-v2
    [*] --> CREATED
    CREATED --> STOPPED: autoStartup=false
    CREATED --> STARTING: autoStartup=true
    STOPPED --> STARTING: start()
    STARTING --> ACTIVE: đăng ký consumer thành công
    STARTING --> RECOVERING: broker chưa sẵn sàng
    ACTIVE --> RECOVERING: mất kết nối
    RECOVERING --> ACTIVE: tái tạo resources thành công
    RECOVERING --> STOPPED: stop()
    ACTIVE --> STOPPING: stop()
    STOPPING --> STOPPED: ngừng nhận theo lifecycle
    STOPPED --> DESTROYED: application context shutdown
    ACTIVE --> DESTROYED: application context shutdown
~~~

Sơ đồ là **mô hình vận hành**, không phải các giá trị enum chính thức của Spring. **ACTIVE** ở đây là container có consumer dùng được; **isRunning()** chỉ nói tới trạng thái lifecycle và không bảo đảm ACTIVE.

Bài thuộc chương **Spring JMS** của module **INTEGRATION_MESSAGING_MESSAGE_BROKER_ACTIVEMQ**. Trọng tâm là **khởi động, tạm dừng, shutdown và phục hồi kết nối listener container** trên ActiveMQ Classic/Artemis, với Java/Spring Boot và cách kiểm chứng khi broker mất rồi khôi phục.

## 2. Ai sở hữu @JmsListener container?

Luồng tạo một endpoint annotation-based:

~~~mermaid
flowchart TD
    APP["Spring ApplicationContext"] --> EN["@EnableJms / cấu hình JMS"]
    EN --> POST["JmsListenerAnnotationBeanPostProcessor"]
    POST --> REG["JmsListenerEndpointRegistry"]
    REG --> END["Endpoint id=ordersListener"]
    END --> FACTORY["DefaultJmsListenerContainerFactory"]
    FACTORY --> DMLC["DefaultMessageListenerContainer"]
    DMLC --> CF["ConnectionFactory"]
    CF --> BROKER[("Artemis hoặc Classic")]
    DMLC --> HANDLER["@JmsListener method"]
~~~

Với **@JmsListener**:

- **@EnableJms** kích hoạt hạ tầng nhận diện annotation và đăng ký endpoint; Spring Boot có thể tự cấu hình một phần hạ tầng nhưng khai báo tường minh dễ kiểm chứng.
- **DefaultJmsListenerContainerFactory** tạo và cấu hình từng container: connection factory, transaction, concurrency, recovery, auto-start.
- **JmsListenerEndpointRegistry** quản lý container theo **id** của endpoint annotation; không buộc ứng dụng tự tìm một bean DMLC độc lập.
- **DefaultMessageListenerContainer** quản lý consumer tasks và logic khôi phục kết nối/tài nguyên JMS.
- **ConnectionFactory** tạo kết nối; nó không phải registry và không điều khiển start/stop của từng listener.

Container do registry tạo **không nhất thiết là một bean Spring độc lập có tên giống listener id**. Với endpoint từ annotation, truy cập:

~~~java
MessageListenerContainer container =
        registry.getListenerContainer("ordersListener");
~~~

Đừng giả định có thể **@Autowired DefaultMessageListenerContainer ordersListener** chỉ vì đã gắn **@JmsListener(id = "ordersListener")**.

### DMLC và SimpleMessageListenerContainer

| Tiêu chí | DefaultMessageListenerContainer | SimpleMessageListenerContainer |
| --- | --- | --- |
| Mô hình nhận | Receive tasks/consumer do container quản lý | JMS MessageListener bất đồng bộ |
| Concurrency | Có cơ chế số consumer tối thiểu/tối đa theo cấu hình | Cơ chế đơn giản hơn, ít khả năng co giãn |
| Recovery | Có chiến lược recovery và khởi tạo lại resources | Ít tùy chọn phục hồi/tối ưu hơn |
| Phù hợp broker gián đoạn | Thường chọn DMLC | Chỉ chọn khi đã xác nhận yêu cầu |
| Transaction | Hỗ trợ quản lý Session transacted/transaction manager | Tùy chế độ, cấu hình và giới hạn provider |

Với ứng dụng cần **start/stop có kiểm soát và tự phục hồi khi broker gián đoạn**, DMLC là điểm xuất phát thực dụng. Đừng suy từ tên lớp rằng nó tự bảo đảm exactly-once business processing.

## 3. Auto-start, explicit start và thứ tự khởi động

Một listener có thể bắt đầu consume **khi Spring ApplicationContext vẫn đang khởi tạo**, trước khi các dependency nghiệp vụ sẵn sàng. Điều này nguy hiểm nếu callback cần DB/schema, cache cấu hình hoặc downstream API.

Các lựa chọn:

- **autoStartup=true**: container tham gia lifecycle **SmartLifecycle** của Spring, được start tự động khi context refresh.
- **autoStartup=false**: container được tạo/đăng ký nhưng không tự bắt đầu nhận; phải được ứng dụng/operator gọi **start()**.
- **phase** của SmartLifecycle: xác định thứ tự start/stop tương đối. Phase thấp thường start trước, stop sau phase cao; cần kiểm tra dependency đầy đủ.
- **ApplicationReadyEvent**: mốc Spring Boot hoàn tất khởi tạo ứng dụng, **không tự chứng minh broker, DB, downstream đã khỏe**.

Một startup gate phù hợp:

~~~text
Spring beans và ConnectionFactory được tạo
    ↓
Migration/schema/config đã sẵn sàng
    ↓
Downstream readiness/business preconditions đã được xác minh
    ↓
Có chủ đích start ordersListener
    ↓
Broker consumer count > 0 và listener có tiến độ
~~~

Nếu đặt **autoStartup=false** nhưng không có code/operator gọi **start()**, ứng dụng có thể vẫn phục vụ HTTP nhưng không nhận một message nào.

### Stop listener không dừng cả ứng dụng

Một app vừa phục vụ HTTP vừa consume JMS có thể dừng riêng listener để bảo trì downstream. **stop()** ngừng công việc JMS mới theo lifecycle mà không đóng HTTP server hoặc ApplicationContext. Tuy nhiên stop không phải một lệnh rollback tức thì mọi transaction đang in-flight; cần quản lý drain và shutdown như mục 8.


## 4. Cấu hình Spring Boot 3 + Artemis: tắt tự khởi động có chủ đích

Ví dụ nhất quán cho **Spring Boot 3.x / Spring Framework 6.x / Jakarta Messaging / JDK 17+**. Nếu dự án đang dùng Spring Boot 2.x với **javax.jms** hoặc ActiveMQ Classic 5.x, không trộn package import với đoạn này; đối chiếu starter và JMS API tương thích.

### 4.1. Maven

POM minh họa với Spring Boot **3.3.5**; đây là bản chọn để mô tả API, **không phải lời khẳng định đó là release nên dùng trong production**. Khi triển khai, chọn release còn được hỗ trợ bảo mật và tương thích JDK/broker:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>lab.messaging</groupId>
    <artifactId>spring-jms-listener-lifecycle</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-artemis</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
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

**spring-boot-starter-artemis** cung cấp khả năng tạo **Jakarta JMS ConnectionFactory** cho Artemis. Không thêm riêng Classic 5.x **activemq-client** vào demo, tránh hai loại ConnectionFactory và hai JMS namespace cạnh tranh trên classpath.

### 4.2. application.yml

~~~yaml
spring:
  application:
    name: inventory-jms-worker
  artemis:
    mode: native
    broker-url: tcp://127.0.0.1:61617

logging:
  level:
    org.springframework.jms.listener: INFO
~~~

Credential broker không hardcode trong YAML. Khi chạy, cung cấp **SPRING_ARTEMIS_USER** và **SPRING_ARTEMIS_PASSWORD** qua environment/secret manager. URL **61617** chỉ là ví dụ Artemis publish host port riêng khi chạy song song ActiveMQ Classic; nếu Artemis publish 61616 hoặc dùng service DNS trong Docker, chỉnh theo môi trường.

### 4.3. Application và listener factory

Tệp **src/main/java/lab/messaging/InventoryJmsApplication.java**:

~~~java
package lab.messaging;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.jms.annotation.EnableJms;

@SpringBootApplication
@EnableJms
public class InventoryJmsApplication {
    public static void main(String[] args) {
        SpringApplication.run(InventoryJmsApplication.class, args);
    }
}
~~~

Tệp **OrdersListenerConfiguration.java** cùng package:

~~~java
package lab.messaging;

import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
public class OrdersListenerConfiguration {
    @Bean
    public DefaultJmsListenerContainerFactory ordersListenerFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);

        // Không consume chỉ vì context vừa được tạo.
        factory.setAutoStartup(false);

        // DMLC quản lý 2-4 consumers theo nhu cầu.
        factory.setConcurrency("2-4");

        // Listener exception dẫn tới rollback transaction JMS.
        factory.setSessionTransacted(true);

        // Thử khôi phục kết nối/tài nguyên sau lỗi hạ tầng.
        factory.setRecoveryInterval(5_000L);

        // Ghi nhận exception khi xử lý listener;
        // KHÔNG thay thế phần recovery của DMLC.
        factory.setErrorHandler(t ->
                System.err.println("JMS listener error: " + t));

        return factory;
    }
}
~~~

Các cấu hình có phạm vi khác nhau:

| Cấu hình | Điều nó thay đổi | Điều nó không làm |
| --- | --- | --- |
| **setAutoStartup(false)** | Không tự start khi context khởi tạo | Không tự start nếu chẳng ai gọi start |
| **setConcurrency("2-4")** | DMLC quản lý số consumer có thể co giãn | Không giới hạn số request xuống DB/API |
| **setSessionTransacted(true)** | ACK receive thuộc JMS local transaction | Không tạo transaction chung với JDBC/HTTP |
| **setRecoveryInterval(5000L)** | Nhịp thử phục hồi JMS infrastructure khi lỗi | Không phải broker redelivery-delay |
| **setErrorHandler(...)** | Thu nhận lỗi callback của listener | Không phải connection recovery hook |

Trong ví dụ này, **autoStartup=false** đặt trên **factory được annotation lựa chọn**. Nếu bạn có nhiều listener factory, cần kiểm tra **containerFactory** tương ứng thay vì chỉ thay một property mặc định của Boot rồi cho rằng mọi listener đã tạm dừng.

### 4.4. Connection pooling và caching có thể che giấu recovery

DMLC quản lý JMS Connection/Session/Consumer trong quá trình nhận và phục hồi. Có thể kết hợp với managed ConnectionFactory hoặc connection pool được framework hỗ trợ, nhưng cần kiểm tra cache và pool có **giữ connection hỏng** sau failover không.

- Không tự bọc nhiều lớp **CachingConnectionFactory + vendor pool + DMLC caching** khi chưa hiểu ownership.
- Khi dùng **JTA/XA**, chiến lược cache/transaction khác local Session transacted; không suy **setSessionTransacted(true)** biến JDBC + JMS thành một giao dịch.
- ConnectionFactory bean được tạo thành công **không chứng minh broker đang online**. Chỉ có kết nối sử dụng thật và broker consumer registration mới là bằng chứng thêm.

## 5. @JmsListener và điều khiển theo id qua registry

Tệp **OrderPaidListener.java** (cùng package):

~~~java
package lab.messaging;

import jakarta.jms.JMSException;
import jakarta.jms.TextMessage;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderPaidListener {

    @JmsListener(
        id = "ordersListener",
        destination = "orders.in",
        containerFactory = "ordersListenerFactory"
    )
    public void onMessage(TextMessage message) throws JMSException {
        String eventId = message.getStringProperty("eventId");
        if (eventId == null || eventId.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing eventId in JMS properties");
        }

        String text = message.getText();
        System.out.println("Processing " + eventId + ": " + text);

        // LAB: không tạo side effect DB/HTTP.
        // PRODUCTION: gọi service idempotent theo eventId
        // rồi chỉ return bình thường khi side effect đã bền vững.
    }
}
~~~

Do factory đã bật **sessionTransacted=true**, callback **trả về bình thường** cho phép DMLC hoàn tất/commit JMS transaction; **exception thoát khỏi callback** dẫn tới xử lý rollback theo transaction của container. Nếu bạn **catch Exception rồi chỉ log và return**, container có thể coi message là thành công và ACK/commit; đừng nuốt lỗi nghiệp vụ cần retry.

Tệp **OrdersListenerLifecycle.java** (cùng package):

~~~java
package lab.messaging;

import java.util.Objects;

import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.listener.MessageListenerContainer;
import org.springframework.stereotype.Component;

@Component
public class OrdersListenerLifecycle {
    private final JmsListenerEndpointRegistry registry;

    public OrdersListenerLifecycle(
            JmsListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    private MessageListenerContainer listener() {
        return Objects.requireNonNull(
                registry.getListenerContainer("ordersListener"),
                "ordersListener was not registered");
    }

    // Bản demo chọn start sau khi Spring Boot đã ready.
    @EventListener(ApplicationReadyEvent.class)
    public void onReady() {
        startConsumption();
    }

    public void startConsumption() {
        MessageListenerContainer c = listener();
        if (!c.isRunning()) {
            c.start();
            System.out.println("Start requested for ordersListener");
        }
    }

    public void stopForMaintenance() {
        MessageListenerContainer c = listener();
        if (c.isRunning()) {
            c.stop();
            System.out.println("Stop requested for ordersListener");
        }
    }

    public boolean isStartRequested() {
        return listener().isRunning();
    }
}
~~~

**Chú ý thiết kế:** gọi **startConsumption()** ở **ApplicationReadyEvent** là ví dụ khởi động sau khi Spring Boot hoàn tất các runner. Trong production, chỉ làm vậy **sau khi các dependency nghiệp vụ thực sự đạt điều kiện**: DB migrations hoàn tất, secret/cấu hình sẵn sàng, downstream hợp lệ. Nếu việc mở consumer cần operator approve, bỏ **@EventListener** và gọi start qua một bước điều phối **có xác thực, phân quyền và audit**; đừng tạo endpoint HTTP công khai để bất kỳ ai gọi start/stop.

### Khi nào dừng một listener, khi nào dừng cả registry?

~~~java
// Chỉ điều khiển listener có id cụ thể:
registry.getListenerContainer("ordersListener").stop();
registry.getListenerContainer("ordersListener").start();

// Điều khiển toàn bộ các listener container do registry quản lý:
registry.stop();
registry.start();
~~~

Đây là các lời gọi minh họa trong thành phần có reference đến **registry**. Dừng toàn registry có thể ảnh hưởng listener khác, kể cả queue quan trọng khác. Nên dùng id rõ ràng để bảo trì phạm vi nhỏ.

**registry.getListenerContainer(id)** có thể trả về null nếu id bị viết sai, annotation chưa đăng ký hoặc factory/scan cấu hình không đúng. Vì vậy code trên cần null-check hoặc đi qua helper **listener()** như ví dụ.

### Start không phải kết nối đã thành công

Ngay sau **c.start()**, method **c.isRunning()** có thể trả true trong khi DMLC vẫn đang thử tạo Session/Consumer do broker down. Hãy kiểm tra **consumer count** trên queue, log kết nối và tiến độ xử lý thay vì báo readiness thành công chỉ dựa vào isRunning.


## 6. Phục hồi sau khi broker mất kết nối: DMLC làm gì?

Khi Artemis/Classic broker restart, đường truyền TCP bị cắt, broker failover hoặc consumer resource không còn dùng được, **DefaultMessageListenerContainer** có thể đi vào chu trình recovery: thử tạo lại kết nối, session và consumer phù hợp, rồi tiếp tục receive khi broker sẵn sàng.

Mô hình:

~~~mermaid
sequenceDiagram
    autonumber
    participant L as DMLC listener container
    participant CF as ConnectionFactory
    participant B as Artemis broker
    participant OPS as Operations

    L->>CF: Tạo Connection/Session/Consumer
    CF->>B: Connect + subscribe/consume
    B-->>L: Đã đăng ký consumer
    B--xL: Broker restart, mất kết nối
    L->>L: Ghi nhận lỗi hạ tầng, huỷ resources không còn dùng được
    loop Recovery attempt, ví dụ 5 giây mỗi lần
        L->>CF: Thử tạo lại JMS resources
        CF->>B: Reconnect
        alt Broker chưa sẵn sàng
            B--xCF: Connect fail
            L->>OPS: Recovery log/metric
        else Broker đã sẵn sàng
            B-->>L: Consumer registration thành công
        end
    end
    L->>B: Tiếp tục receive
~~~

**setRecoveryInterval(5_000L)** thiết lập khoảng chờ phục hồi kiểu cố định của DMLC, tính bằng mili giây. Nó **không** quy định thời gian chờ trước redelivery một message lỗi nghiệp vụ ở broker. Cũng không có nghĩa mỗi năm giây sẽ có một lần nhận message thành công: một attempt có thể tốn thêm thời gian vì DNS, socket timeout, authentication hoặc provider failover.

### Recoverable và không recoverable phải phân biệt

| Nguyên nhân | DMLC có thể làm gì | Phần operator/ứng dụng phải sửa |
| --- | --- | --- |
| Broker restart có kiểm soát | Thử tạo lại JMS resources và consumer | Đảm bảo broker quay lại với queue, quyền, storage đúng |
| TCP reset/network partition ngắn | Thử recovery hoặc dựa vào provider reconnect | Xác minh DNS, TLS, firewall, idle timeout |
| Artemis/Classic HA failover | Tiếp tục sau khi provider/broker và DMLC phục hồi | Kiểm chứng failover URI/topology và transaction outcome |
| Sai username/password | Có thể lặp lỗi authentication | Sửa credential/secret và bảo đảm factory dùng secret mới |
| Chứng chỉ TLS hết hạn | Recovery liên tục có thể vẫn thất bại | Cập nhật trust/key material và reload theo client |
| Destination bị xóa hoặc không có quyền consume | Có thể connect được nhưng tạo consumer thất bại | Khôi phục queue/subscription và authorization |
| Handler ném IllegalStateException | Session transacted có thể rollback message | Sửa nghiệp vụ, idempotency, bounded retry/DLQ; không phải reconnect loop |
| DB/API phía consumer không sẵn sàng | Broker connection vẫn có thể hoàn toàn khỏe | Throttle, circuit breaker hoặc stop intake theo SLA |

**ErrorHandler không phải recovery manager.** ErrorHandler của listener chủ yếu thu nhận exception từ callback; nó không tự cấp lại chứng chỉ, không tạo DLQ và không khẳng định session hỏng do broker. Ngược lại, lỗi connectivity có thể xuất hiện ở log DMLC/provider ngay cả khi method **@JmsListener** không được gọi lần nào.

### Recovery interval hay BackOff?

DMLC hỗ trợ cơ chế **recoveryInterval** và, trong các Spring Framework release tương thích, cấu hình **BackOff** để điều chỉnh các lần phục hồi. Với bài lab, một interval cố định 5 giây giúp dễ quan sát. Với nhiều replica production, nên có backoff/jitter thích hợp để tránh đồng loạt reconnect khi broker mới quay lại.

Không đặt **recoveryInterval** quá nhỏ đến mức hàng trăm replica mỗi giây đều thử connect, gây auth/log/connection storm. Một interval lớn quá lại kéo dài thời gian phục hồi so với SLO.

### Failover của JMS provider và recovery của Spring là hai tầng

Artemis client hoặc Classic failover transport có thể tự thử reconnect với broker thay thế. DMLC cũng có cơ chế phục hồi khi JMS resources thất bại. Khi phối hợp:

- Provider cần chính sách **connection timeout, topology, failover/retry** rõ ràng.
- DMLC cần chiến lược **recreate/refresh resources** sau lỗi mà provider không che giấu được.
- Không để cả hai tầng giữ tài nguyên lỗi vô hạn mà không phát tín hiệu vận hành.
- **JMS transaction đang chạy** tại lúc kết nối đứt có thể rollback hoặc có kết quả commit không xác định; reconnect không chứng minh message đã được ACK thành công.
- Một consumer được phục hồi có thể nhận **redelivered message**. Vì vậy business handler cần idempotent theo **eventId**, bất kể connection recovery hoạt động tốt.

## 7. Listener transaction, exception và các lần nhận lại sau recovery

Với **setSessionTransacted(true)**, mỗi lần listener xử lý message gắn với một JMS local transaction do DMLC quản lý. Spring hoàn tất transaction JMS khi handler trả về bình thường, còn exception thoát khỏi handler sẽ làm đường xử lý lỗi/rollback kích hoạt theo semantics container.

~~~mermaid
flowchart TD
    M["Broker deliver event E1"] --> H["@JmsListener handler"]
    H --> DB{"Side effect nghiệp vụ"}
    DB -->|Lỗi chưa commit| ERR["Ném exception"]
    ERR --> RB["DMLC rollback JMS transaction"]
    RB --> RETRY["Broker redelivery policy"]
    DB -->|Đã commit/idempotent| ACK["Handler return bình thường"]
    ACK --> COMMIT["DMLC commit JMS session"]
    COMMIT --> X{"Connection mất ngay commit?"}
    X -->|Không| DONE["Broker ACK confirmed"]
    X -->|Có| UNKNOWN["Kết quả ACK có thể UNKNOWN"]
    UNKNOWN --> RETRY
~~~

Nhánh **UNKNOWN** ở đây nói message **có thể** được giao lại, không phải broker chắc chắn sẽ redeliver. Có thể broker đã commit ACK nhưng phản hồi mất. Để không áp dụng side effect hai lần:

~~~text
BEGIN DB TRANSACTION
    INSERT processed_events(consumer_name, event_id)
    IF mới:
        thực hiện side effect trong CÙNG DB transaction
    ELSE:
        bỏ qua side effect
COMMIT DB TRANSACTION

Handler return bình thường
DMLC commit JMS transaction
~~~

Trong một transaction PostgreSQL, dùng unique constraint trên **(consumer_name, event_id)**. Nếu DB commit thành công rồi JMS connection mất trước ACK, lần nhận lại sẽ phát hiện event đã xử lý và chỉ xác nhận JMS.

**Không dùng mỗi JMSRedelivered hoặc JMSMessageID như business idempotency key**: producer retry sau commit outcome UNKNOWN có thể tạo JMS message mới với JMSMessageID khác nhưng mang cùng eventId.

### Vì sao nuốt exception là nguy hiểm?

~~~java
@JmsListener(
    id = "badListener",
    destination = "orders.in",
    containerFactory = "ordersListenerFactory"
)
public void wrong(TextMessage message) {
    try {
        callInventoryApi(message);
    } catch (Exception failure) {
        System.err.println(failure);
        // Sai: return bình thường dù downstream chưa xử lý.
    }
}
~~~

Đây là **minh họa phản ví dụ**, không phải đoạn source để gắn vào lab; callInventoryApi là một thao tác giả định. Với Session transacted, method return bình thường có thể dẫn đến JMS commit và mất cơ hội retry message đó. Phải **throw** lỗi cần retry hoặc dùng cơ chế quyết định hoàn tất có chủ đích.

**Ngược lại, không retry vô hạn mọi lỗi.** Payload thiếu field bắt buộc hoặc contract sai cần được chuyển vào quarantine/DLQ sau số lần thử phù hợp; outage toàn cục của downstream có thể cần **stop intake/circuit breaker** thay vì làm tất cả message hợp lệ hết attempts trong DLQ.

## 8. Dừng có kiểm soát: stop, drain và shutdown khác nhau

Khi rolling deployment, xoay secret, bảo trì DB hoặc broker, mục tiêu là:

1. Ngăn **nhận công việc mới**.
2. Cho các tác vụ đang chạy **cơ hội hoàn tất** trong khoảng shutdown budget.
3. Không ACK message trước khi side effect đã được commit.
4. Giải phóng JMS resources theo lifecycle và để broker có thể redeliver message chưa hoàn tất.

### stop() không phải “drain đã xong”

**MessageListenerContainer.stop()** yêu cầu container ngừng chạy theo cơ chế của implementation. Tuy nhiên callback đang chạy, receive timeout và transaction in-flight có thể khiến việc dừng diễn ra không tức thì. Với các Spring version/container có callback **SmartLifecycle.stop(Runnable)**, cơ chế shutdown callback hữu ích khi phối hợp; đừng dùng một lời gọi stop rồi mặc định mọi handler đã hoàn tất trong một mili giây.

Một tiến trình shutdown:

~~~text
Kubernetes/Operator yêu cầu giảm tải
    ↓
Readiness cho HTTP (nếu có) chuyển NOT_READY theo chính sách
    ↓
Ngừng intake JMS bằng container.stop()
    ↓
Đợi handler hiện có hoàn thành trong shutdown budget
    ↓
Kiểm tra in-flight, commit/rollback, metrics
    ↓
Spring ApplicationContext shutdown; resources được destroy
    ↓
Consumer replica khác có thể nhận lại message chưa ACK
~~~

Khi không còn đủ shutdown budget, application có thể bị kill trước khi ACK. Trong trường hợp đó, **at-least-once/redelivery + idempotency** mới đảm bảo nghiệp vụ không sai. Không hứa graceful shutdown sẽ làm mọi message hoàn tất nếu pod có deadline ngắn hoặc downstream chậm.

### Những khái niệm khác nhau

| Thao tác | Phạm vi | Có thể khởi động lại bằng start()? |
| --- | --- | --- |
| **listenerContainer.stop()** | Ngừng container được chỉ định | Thông thường có, khi context/container còn sống |
| **listenerContainer.start()** | Yêu cầu container tiếp tục consumer lifecycle | Có, nhưng có thể còn đang recovery |
| **registry.stop()** | Tạm dừng nhiều listener container của registry | Thường có, với registry còn tồn tại |
| **context.close()/destroy()** | Kết thúc ApplicationContext và destroy resources | Không dùng start() trên các bean đã bị destroy như một app đang chạy |
| **broker restart** | Hạ tầng JMS, ảnh hưởng mọi client | DMLC có thể recovery nếu vẫn đang được yêu cầu chạy |
| **Spring app restart** | Toàn bộ JVM/context | Tạo bean và container mới theo autoStartup/gate |

**Điểm rủi ro:** stop một listener rồi restart application khi **autoStartup=false** nhưng gate start chưa được gọi sẽ làm consumer tiếp tục offline dù broker khỏe. Runbook phải ghi rõ điều kiện mở intake trở lại.

### Tránh dừng connection factory dùng chung trước listener

Nếu một ConnectionFactory/pool phục vụ nhiều JMS listener và JmsTemplate, việc đóng pool sớm có thể cắt ngang transaction đang xử lý. Với Spring, ưu tiên lifecycle/shutdown ordering do framework quản lý. Nếu có resource manager tự viết, kiểm tra thứ tự **stop listeners → hoàn tất in-flight → close shared connection/pool**; tránh gọi close trực tiếp trên Connection đang do DMLC sở hữu.


## 9. Artemis và Classic: Spring recovery là một tầng, transport là tầng khác

**DefaultMessageListenerContainer** thực hiện consumer lifecycle và thử phục hồi khi JMS infrastructure lỗi. Nhưng **ConnectionFactory/client của broker** quyết định cách tạo connection, socket timeout, xác thực, failover URI/topology và phản ứng với phiên đang bị cắt.

| Vấn đề | Artemis với Jakarta client/Spring Boot 3 | ActiveMQ Classic với client tương thích |
| --- | --- | --- |
| ConnectionFactory | Có thể dùng **spring-boot-starter-artemis** | Chọn Classic client/starter và JMS namespace phù hợp |
| @JmsListener và DMLC | Spring quản lý | Spring quản lý |
| Recovery interval | Cấu hình ở Spring DMLC | Cấu hình ở Spring DMLC |
| Transport reconnect | Artemis client/topology/HA policy | Classic failover transport URI/policy |
| Broker destination | Address + queue, ANYCAST/MULTICAST | Queue/topic và destination policy |
| Commit khi mất đường truyền | Có thể redelivery hoặc kết quả commit chưa rõ | Cùng nhu cầu phòng trùng, không hứa exactly-once |
| Storage sau restart | Persistent + durable queue/subscription + journal | Persistent + durable destination/subscription + persistence adapter |

Classic 5.x có kiểu URI **failover:(tcp://broker-a:61616,tcp://broker-b:61616)** khi dùng đúng Classic client. **Không sao chép URI đó sang Artemis** rồi mặc định hai client diễn giải giống nhau. Artemis dùng cấu hình reconnect/HA riêng, và việc client tự reconnect không loại bỏ khả năng transaction cũ đang có kết quả **UNKNOWN**.

~~~text
ConnectionFactory / broker transport
   → TCP/TLS/authentication, retry/failover

Spring DMLC
   → start/stop, recreate Session/Consumer, recovery

@JmsListener handler
   → parsing, business transaction, idempotency

Broker policy
   → redelivery-delay, DLQ, expiry

Operations
   → queue/storage, secret rotation, alert, SLO
~~~

Nếu handler ném exception vì DB tạm thời quá tải, DMLC không phải một rate limiter DB. Có thể **stop intake có chủ đích**, giảm concurrency hoặc dùng circuit breaker. Khi phục hồi cần điểm **start()** rõ và xác minh consumer thực sự đăng ký ở broker.

## 10. Quan sát: isRunning, consumer count và business progress

### 10.1. Các chỉ số tối thiểu

| Nguồn | Chỉ báo | Cần kết luận gì? |
| --- | --- | --- |
| Spring registry | **getListenerContainerIds()** | Listener annotation-based nào đã đăng ký |
| Spring container | **isRunning()** | Đang được yêu cầu chạy hay đã stop |
| Spring JMS log | Recovery attempts/connection exceptions | Có đang cố tái tạo JMS resources không |
| Broker log | Connection, authentication và consumer registration | Có consumer dùng được đúng destination không |
| Broker management | Consumer count, delivering, pending | Có backlog và có consumer đăng ký không |
| Application metrics | Handler success/error, latency, commit outcome | Công việc có tiến độ hay không |
| Reliability | Oldest message age, redelivery, DLQ | Có message kẹt hay đang retry bất thường không |
| Downstream | Pool saturation, 429/503, timeout | Có bị nghẽn sau consumer không |

Code quan sát các listener trong registry:

~~~java
for (String id : registry.getListenerContainerIds()) {
    MessageListenerContainer container =
            registry.getListenerContainer(id);
    System.out.printf("id=%s, running=%s%n",
            id, container != null && container.isRunning());
}
~~~

**isRunning() chỉ là lifecycle signal**, không đủ cho một quyết định readiness:

~~~text
A. running=false, consumerCount=0
   → stop có chủ đích hoặc chưa gọi start

B. running=true, consumerCount=0
   → có thể recovery, sai credential hoặc queue/binding

C. running=true, consumerCount>0, ACK rate=0
   → có thể queue rỗng HOẶC handler kẹt

D. running=true, consumerCount>0, backlog age giảm
   → có thêm bằng chứng tiến độ
~~~

Với C, phải kiểm tra queue đang có message không. Consumer rảnh vì queue rỗng không phải consumer bị lỗi.

### 10.2. Phân biệt liveness, readiness và JMS consumption

Khi broker down ngắn, JVM có thể vẫn đủ khỏe để chờ DMLC tự recovery. Nếu **liveness probe** phụ thuộc tuyệt đối vào broker, Kubernetes có thể restart pod liên tục, gây nhiều reconnect hơn. Một cách phân tách:

- **Liveness**: tiến trình còn hoạt động, không bị deadlock nghiêm trọng.
- **Readiness**: ứng dụng có nên nhận traffic mới hay không theo policy.
- **JMS consumption**: container có được phép nhận, broker consumer có tồn tại và nghiệp vụ có tiến độ.

**HTTP readiness=false không tự dừng @JmsListener.** Nếu phải ngừng tiêu thụ khi Inventory API down, dùng **container.stop()** hoặc một cơ chế điều tiết intake khác; Kubernetes ngừng route HTTP không có nghĩa JMS broker ngừng dispatch.

### 10.3. Cảnh giác connection pooling

Một probe tự tạo connection có thể thành công trong khi listener vẫn đang hồi phục một Session cũ, hoặc ngược lại. Khi dùng pool/caching, theo dõi **chính listener** qua registry id, broker consumer count, handler progress và logs, không chỉ một ping tới broker.

## 11. Demo gửi trước khi listener start

Tệp **OrdersListenerConfiguration.java** đặt **autoStartup=false** và **OrdersListenerLifecycle.onReady()** chỉ start khi có **ApplicationReadyEvent**. Để quan sát message chờ trước thời điểm Ready, dùng **ApplicationRunner** chỉ bật ở profile demo.

Tệp **DemoPublisher.java** cùng package:

~~~java
package lab.messaging;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.jms.core.JmsTemplate;

@Configuration
@Profile("demo")
public class DemoPublisher {
    @Bean
    ApplicationRunner sendDemoOrder(JmsTemplate jmsTemplate) {
        return args -> jmsTemplate.convertAndSend(
                "orders.in",
                "OrderPaid:ORD-1001",
                message -> {
                    message.setStringProperty(
                            "eventId", "payment-ORD-1001-demo");
                    return message;
                });
    }
}
~~~

**ApplicationRunner** chạy trong startup trước **ApplicationReadyEvent**. Khi autoStartup=false, listener chưa tự nhận chỉ vì runner gửi xong. Sau khi Ready event phát và gate gọi start, listener có thể nhận event đã ở queue.

**Điều kiện:** Broker phải sẵn sàng khi dùng demo profile vì ApplicationRunner trực tiếp gửi message. Nếu broker down khi app start, runner có thể gây startup failure **trước cả ApplicationReadyEvent**; khi thử broker-down-at-start cần chạy **không có demo profile**.

### 11.1. Lệnh khởi động

~~~powershell
$env:SPRING_ARTEMIS_USER = "artemis_app"
$env:SPRING_ARTEMIS_PASSWORD = "<your-artemis-password>"

mvn spring-boot:run "-Dspring-boot.run.profiles=demo"
~~~

Broker Artemis cần có queue ANYCAST **orders.in** hoặc cho phép auto-create, cùng quyền send/consume. Đổi URL trong application.yml nếu broker không publish host port 61617. Đây là lệnh hướng dẫn, **chưa được chạy trong quá trình viết tài liệu**.

Trình tự logic mong đợi:

~~~text
ApplicationRunner gửi OrderPaid
ApplicationReadyEvent được phát
OrdersListenerLifecycle yêu cầu start
Broker đăng ký consumer orders.in
OrderPaidListener nhận message và ghi log
DMLC commit JMS khi callback trả về bình thường
~~~

Log thực tế giữa các thread có thể xen nhau; không kiểm tra chỉ bằng thứ tự dòng console. **Demo handler chỉ log, không có side effect**; ở production phải thay bằng service idempotent theo eventId.


## 12. Lab broker outage: stop, recovery và restart

Thử nghiệm trên **broker lab và queue riêng**, không cắt kết nối production. Nếu Docker Compose định nghĩa Artemis service là **artemis**, có thể dùng:

~~~powershell
docker compose stop artemis
docker compose start artemis
~~~

Thay tên service theo môi trường. **Không dùng docker compose down -v** trong phép thử persistence/recovery: lệnh này có thể xóa volume làm mất dữ liệu.

### A. Broker down sau khi listener start

1. Khởi động Spring Boot, xác minh **ordersListener** đã start và broker consumer count của **orders.in** lớn hơn 0.
2. Stop Artemis. Quan sát log DMLC/provider: connection failure và các recovery attempts.
3. **isRunning() có thể vẫn true** trong lúc broker đã offline. Đây là trạng thái container được yêu cầu chạy, không phải dấu hiệu consumer đang connected.
4. Start lại Artemis với queue/storage cũ. Chờ DMLC tái tạo consumer; kiểm tra consumer count và message flow.
5. Gửi message mới với **eventId riêng**, xác minh handler tiếp tục nhận và commit. Message chưa ACK trước outage có thể redeliver.

**PASS** khi listener khôi phục mà không cần restart JVM, broker có consumer thực, message được xử lý đúng và không ACK sai. Không PASS nếu chỉ thấy **isRunning=true**.

### B. Broker down trước khi Spring Boot start

1. Stop broker.
2. Start ứng dụng **không bật profile demo**, vì ApplicationRunner gửi JMS có thể làm startup thất bại khi broker offline.
3. Quan sát context có tạo thành công hay không; hành vi phụ thuộc ConnectionFactory, fail-fast policy và các startup beans khác.
4. Nếu ứng dụng khởi tạo được, gate sẽ gọi start; DMLC có thể vào vòng recovery cho đến khi broker quay lại.
5. Start broker, kiểm tra consumer registration và một event test được ACK.

**Không cam kết mọi cấu hình Boot đều start được khi broker down.** Nếu app lỗi trước ApplicationReadyEvent, kiểm tra các bean có kết nối sớm, authentication/TLS, ApplicationRunner, migration, và connection factory/provider; không đổ lỗi cho DMLC khi chưa có bằng chứng.

### C. Stop listener mà không dừng broker

Trong thành phần quản trị nội bộ có xác thực/ủy quyền:

~~~java
lifecycle.stopForMaintenance();
// Khi downstream sẵn sàng:
lifecycle.startConsumption();
~~~

Khi stop, producer vẫn có thể gửi vào durable queue; backlog có thể tăng. Sau start, consumer tiếp tục nhận. Đừng gọi stop/start liên tục như một vòng reconnect thủ công; DMLC đã có recovery loop cho lỗi hạ tầng.

### D. Mất connection ngay lúc JMS commit

Nếu DB đã commit side effect nhưng phản hồi **JMS commit** thất lạc, broker có thể đã ACK hoặc chưa. Consumer sau recovery **có thể** nhận lại message. Inbox/idempotency theo eventId bảo vệ kết quả. Cắt TCP ở thời điểm bất kỳ không bảo đảm luôn tái hiện được nhánh mất phản hồi commit; cần fault injection/tracing phù hợp.

| Mốc | isRunning | Consumer tại broker | Bằng chứng chính |
| --- | --- | --- | --- |
| autoStartup=false, chưa start | false | 0 | Không consume |
| Đã gọi start, broker online | true | Có consumer | Xử lý và ACK có tiến độ |
| Broker offline | Có thể true | Không còn consumer hoạt động | Log recovery, không ACK sai |
| Broker trở lại | true | Đăng ký lại | Message mới/cũ đủ điều kiện được nhận |
| Operator stop | false sau khi ngừng | Giảm về 0 theo lifecycle | Không nhận thêm việc mới |
| App context destroyed | Không còn container sống | Không có consumer của JVM | Unacked có thể được redeliver |

Các trạng thái trong bảng mang ý nghĩa vận hành; Spring không cung cấp một enum mang đúng các từ mô tả này. Với concurrency > 1, consumer count có thể dao động trong lúc recovery, cần quan sát theo cửa sổ thời gian.

## 13. Chẩn đoán lifecycle và recovery theo triệu chứng

| Triệu chứng | Nguyên nhân hay gặp | Bước kiểm tra |
| --- | --- | --- |
| App khỏe nhưng queue không giảm | autoStartup=false, gate chưa start | Registry ids, isRunning, ApplicationReadyEvent |
| Gọi start nhưng consumer count=0 | Recovery, sai URL/queue, auth, TLS | DMLC logs và broker management |
| Registry không tìm thấy listener id | Annotation không scan hoặc id khác | @EnableJms, component scan, getListenerContainerIds() |
| Broker đã lên nhưng listener chưa về | Provider/connection cache lỗi, retry timeout | Recovery logs, pool, TCP/auth, consumer registration |
| Handler lỗi mà message biến mất | Catch/log exception rồi return | Session transacted, exception path |
| Message bị áp dụng nghiệp vụ hai lần | JMS ACK outcome không chắc chắn | Inbox/unique key theo eventId |
| Stop app mất lâu | Handler đang chờ DB/HTTP, receive timeout | In-flight, thread dump, shutdown budget |
| Pod restart liên tục khi broker offline | Liveness bị buộc vào broker | Tách liveness và readiness |
| Pause một queue làm dừng nhiều queue | Gọi registry.stop() toàn cục | Dùng getListenerContainer(id).stop() |
| Credential đã đổi nhưng vẫn auth fail | Factory giữ secret cũ | Reload/recreate factory/session có kiểm soát |
| Consumer tăng tải sau reconnect | Backlog burst, concurrency quá lớn | Quota downstream, rate limiting, consumer settings |

DMLC nên tự recovery với lỗi kết nối **có thể hồi phục**, nhưng retry không thể sửa cấu hình sai vĩnh viễn như user không có quyền, password đã hết hạn hoặc chứng chỉ TLS không tin cậy. Cần cảnh báo khi recovery vượt ngưỡng SLO, xác định nguyên nhân và sửa cấu hình; restart pod liên tục không giúp nếu secret/authorization chưa thay đổi.

Nếu có nhiều listener như **ordersListener**, **paymentsListener**, **auditListener**, nên đặt id và container factory rõ ràng, điều khiển từng nhóm theo dependency. SmartLifecycle phase giúp sắp xếp thứ tự start/stop tương đối, nhưng không thay kiểm tra readiness của DB/API ở ngoài JVM.

## 14. Checklist nghiệm thu trước production

| Câu hỏi | Điều phải chứng minh |
| --- | --- |
| Ai tạo listener container? | @JmsListener, endpoint registry và factory đúng |
| Listener được start khi nào? | autoStartup/explicit gate có định nghĩa và có trigger |
| Có nhầm running với connected? | Kiểm tra broker consumer count và progress |
| Broker restart có tự phục hồi không? | DMLC khôi phục Session/Consumer trong lab |
| Retry recovery có phù hợp? | Interval/backoff có giới hạn storm và có alert |
| Failover transport đúng provider? | Artemis/Classic client/URI/namespace không bị trộn |
| ErrorHandler có thay reconnect không? | Không; phân biệt callback error với connection error |
| Handler exception làm gì? | Rollback JMS khi transacted; không nuốt lỗi |
| Nếu DB commit nhưng JMS ACK UNKNOWN? | Idempotency theo eventId, redelivery an toàn |
| Stop có mất message không? | ACK sau side effect, queue bền và retry phù hợp |
| Shutdown có drain được không? | Budget/timeout và in-flight được kiểm tra |
| Liveness và readiness tách nhau không? | Broker offline ngắn không tạo restart loop vô ích |
| Khi start/recovery có giám sát? | Registry state + broker consumers + ACK/backlog/logs |
| Ai được start/stop trong production? | Operator/admin có xác thực, phân quyền, audit |

**Kết luận:** quản lý listener container trong Spring JMS là quản lý **một tiến trình tiêu thụ có vòng đời riêng**, không chỉ khởi tạo ConnectionFactory. **autoStartup, start và stop** điều khiển lúc listener được phép nhận; **DefaultMessageListenerContainer recovery** giúp tái tạo connection/session/consumer khi broker gián đoạn; còn **transaction, idempotency và shutdown policy** bảo vệ nghiệp vụ khi sự cố xảy ra giữa lúc xử lý. Trên ActiveMQ Artemis và Classic, nghiệm thu phải dựa trên **consumer thực sự được đăng ký, tiến độ nhận/ACK và side effect chính xác**, không chỉ nhìn **isRunning() trả true**.
