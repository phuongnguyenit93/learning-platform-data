# Trách nhiệm xác nhận và giao dịch của listener container trong Spring JMS

## 1. Bài toán: ai quyết định một message đã xử lý xong?

Một ứng dụng **Spring Framework JMS** thường dùng `@JmsListener` để nhận message bất đồng bộ:

```java
@JmsListener(destination = "orders.in")
public void handle(String orderId) {
    processOrder(orderId);
}
```

Ví dụ trên mới diễn tả **logic nghiệp vụ**. Một câu hỏi quan trọng hơn là: khi nào message được **acknowledge (xác nhận)** để broker biết có thể xem lần giao đó là hoàn tất? Nếu `processOrder` ném exception, message có được gửi lại (redelivery) không? Nếu method vừa cập nhật database vừa gửi response JMS, các thao tác có commit cùng nhau không?

Đó là trách nhiệm của **message listener container**, không phải chỉ của annotation `@JmsListener`. Trong Spring, container:

1. Mở/lấy kết nối qua `jakarta.jms.ConnectionFactory`, tạo hoặc lấy `Session` và `MessageConsumer`.
2. Nhận message từ Queue/Topic theo cấu hình destination, selector, concurrency và subscription.
3. Gọi listener hoặc adapter xử lý `@JmsListener`.
4. Quyết định **acknowledge, commit hoặc rollback/recover**, dựa trên loại container, session acknowledge mode và transaction manager.
5. Quản lý vòng đời consumer, lỗi kết nối, shutdown, recovery và việc khởi tạo lại tài nguyên.

```text
              JMS Broker
                  |
                  | dispatch một JMS Message
                  v
       Message Listener Container
       | ConnectionFactory/Session
       | acknowledgement/transaction
       | exception/recovery
       v
       @JmsListener handler
          |              |
          | thành công    | ném exception
          v              v
    commit / ACK      rollback/recover?
          |              |
          v              v
    hoàn tất lượt     broker có thể
       giao           redeliver theo policy
```

**Không nhầm “method đã chạy” với “broker đã xác nhận”, và không nhầm “broker đã xác nhận” với “database đã commit”.** Ba mốc này chỉ trùng nhau khi có thiết kế giao dịch nhất quán.

## 2. Bốn khái niệm cần phân biệt

| Khái niệm | Ai chủ yếu phụ trách? | Ý nghĩa |
| --- | --- | --- |
| **Delivery** | JMS provider/broker và consumer | Message được giao đến một consumer/session. |
| **Acknowledgment (ACK)** | JMS Session + listener container theo mode | Xác nhận việc nhận/hoàn tất lần giao trong chế độ không transacted. |
| **JMS transaction** | Locally transacted Session hoặc transaction manager | Nhóm các thao tác JMS có commit/rollback. |
| **Business transaction** | Service, database, hệ thống ngoài | Cập nhật trạng thái nghiệp vụ, có thể hoàn toàn độc lập với JMS. |

Ví dụ xử lý một đơn hàng:

```text
T0   Broker giao ORDER-42 cho container
T1   Listener đọc nội dung và bắt đầu xử lý
T2   UPDATE orders SET status='PAID' ...
T3   Database COMMIT
T4   Container/JMS COMMIT hoặc ACK
```

Nếu JVM chết giữa **T3** và **T4**, DB đã đổi nhưng JMS có thể giao lại message vì chưa thấy commit/ACK. Nếu handler không idempotent, order có thể bị xử lý hoặc trừ tiền hai lần. **Đây không phải bug của riêng Spring**; đó là cửa sổ bất nhất giữa hai tài nguyên độc lập.

Ngược lại, trong `AUTO_ACKNOWLEDGE` của một số container, ACK có thể xảy ra **trước** khi code xử lý; nếu code thất bại sau đó, message có thể không được giao lại.

## 3. Tách trách nhiệm của listener và container

### 3.1. Listener chịu trách nhiệm phần nào?

Một method `@JmsListener` nên chịu trách nhiệm:

- Kiểm tra schema/message type và dữ liệu nghiệp vụ.
- Thực hiện thao tác nghiệp vụ theo cơ chế idempotent.
- Phân loại lỗi tạm thời và lỗi vĩnh viễn.
- **Để exception đi ra** khi thực sự muốn container coi lượt xử lý là thất bại và tiến hành rollback/recovery theo cấu hình.
- Ghi log/metrics dựa trên business event ID và các header như `JMSMessageID`, `JMSRedelivered` (tránh log dữ liệu nhạy cảm).

### 3.2. Container chịu trách nhiệm phần nào?

Container thực thi:

- Tạo `MessageConsumer`, chọn Queue/Topic, message selector và receive loop.
- Thiết lập `sessionTransacted`, `sessionAcknowledgeMode`, transaction manager.
- Gọi `commit()` hoặc `rollback()` cho locally transacted Session khi phù hợp.
- Gọi ACK/recover trong các mode non-transacted theo contract cụ thể.
- Quản lý concurrency, error handler, resource caching và broker recovery.
- Điều phối việc gửi **auto-reply** trong cùng Session khi adapter hỗ trợ.

**Một listener method không có thuộc tính `acknowledgment` trên `@JmsListener`** để đổi mode cho từng lời gọi. Hãy cấu hình `JmsListenerContainerFactory` (hoặc chính listener container) rồi chọn factory bằng `containerFactory = "beanName"`.

## 4. Các chế độ acknowledgment theo Jakarta Messaging

Jakarta Messaging định nghĩa các hằng số trong `jakarta.jms.Session`:

```java
Session.AUTO_ACKNOWLEDGE
Session.CLIENT_ACKNOWLEDGE
Session.DUPS_OK_ACKNOWLEDGE
Session.SESSION_TRANSACTED
```

Tuy nhiên, **`SESSION_TRANSACTED` không phải lựa chọn thay thế đơn giản cho acknowledge mode của một session non-transacted**. Trong Spring, khi muốn giao dịch local JMS, dùng `setSessionTransacted(true)`.

| Cấu hình Spring container | Khi nào ACK/commit? | Listener ném exception | Độ tin cậy thường gặp |
| --- | --- | --- | --- |
| `AUTO_ACKNOWLEDGE`, `sessionTransacted=false` | Phụ thuộc container; xem mục 5. | Không bảo đảm redelivery trên exception của người dùng. | Dễ mất message trong thời điểm lỗi. |
| `DUPS_OK_ACKNOWLEDGE`, non-transacted | ACK trì hoãn/lazy. | Không bảo đảm redelivery khi handler ném exception. | Có thể có bản giao lặp; không phù hợp nếu cần rollback chắc chắn. |
| `CLIENT_ACKNOWLEDGE`, non-transacted | Spring container thường ACK sau khi listener thành công. | **Best-effort redelivery** nếu listener lỗi; phụ thuộc recovery/provider. | Tốt hơn auto ACK trong một số tình huống nhưng không atomic với send khác. |
| **`sessionTransacted=true`** | Container commit JMS transaction khi listener thành công. | Container rollback JMS transaction khi listener thất bại, broker có thể giao lại theo policy. | Lựa chọn ưu tiên để xử lý Queue tin cậy bằng local JMS transaction. |
| External transaction manager | Coordinator quyết định commit/rollback. | Rollback transaction nếu quy tắc tương ứng được kích hoạt. | Có thể phối hợp nhiều tài nguyên khi thiết lập JTA/XA đúng. |

Không suy luận từ mode rằng hệ thống đã có **exactly-once processing**. Redelivery, duplicate, transaction boundary, DLQ và idempotency vẫn phải được thiết kế và kiểm thử.

### 4.1. AUTO_ACKNOWLEDGE

`AUTO_ACKNOWLEDGE` là kiểu dùng khi không bật transaction và không cấu hình mode khác. Nhưng **thời điểm ACK cụ thể khác nhau theo container**:

- `DefaultMessageListenerContainer`: message được JMS acknowledge ở giai đoạn receive, về thực chất **trước** khi listener xử lý. Một exception của listener không giúp lấy lại message đã ACK.
- `SimpleMessageListenerContainer`: provider thực hiện callback `MessageListener` và tự ACK **sau** khi callback hoàn tất; Spring container xử lý exception của listener, nên exception do code ném thường không đi nguyên vẹn đến provider để yêu cầu redelivery.

Vì vậy **không dùng `AUTO_ACKNOWLEDGE` chỉ vì muốn “tự động retry khi listener lỗi”**. Điều đó không đúng với contract của Spring containers.

### 4.2. DUPS_OK_ACKNOWLEDGE

JMS có thể trì hoãn ACK để tối ưu throughput. Lỗi JVM hoặc sự cố kết nối quanh mốc ACK có thể dẫn đến giao lại; nhưng **lỗi nghiệp vụ do listener ném không phải cơ chế rollback đáng tin** trong mode này.

Tên `DUPS_OK` không có nghĩa broker cố tình gửi hai lần mọi message; nó chỉ cho phép kiểu ACK lazy mà duplicate delivery có thể xảy ra. Handler vẫn nên idempotent.

### 4.3. CLIENT_ACKNOWLEDGE

Trong JMS API thuần, `Message.acknowledge()` được gọi bởi client khi muốn ACK. Một điểm rất dễ nhầm: **acknowledge một message trong cùng Session thường xác nhận tất cả message đã được Session tiêu thụ**, không đơn thuần một message tùy chọn theo ý người gọi.

Ở Spring listener container, `CLIENT_ACKNOWLEDGE` **không đồng nghĩa bạn phải tự gọi `message.acknowledge()` trong từng `@JmsListener`**: container thường tự ACK sau khi listener thành công. Khi lỗi, Spring có thể gọi recovery nên redelivery thuộc loại **best effort**, không phải thay thế cho transacted session.

Spring Framework 6.2 còn có `setAcknowledgeAfterListener(...)` để điều chỉnh một số client/vendor-specific acknowledgment modes. Đây là cấu hình nâng cao, không phải công tắc nên vô hiệu hóa tùy tiện; nếu cần mode vendor-specific kiểu individual ACK, phải kiểm tra contract và phiên bản Spring cụ thể.

### 4.4. Session transacted

Khi `sessionTransacted=true`, commit/rollback điều khiển cả **nhận message** và các thao tác **gửi bằng chính JMS Session đó**. Acknowledge mode thông thường không còn là công tắc quyết định thời điểm xác nhận. Vòng đời phổ biến:

```text
receive(message)
    |
    +-- begin local JMS transaction
    |
    +-- invoke listener
            |
            +-- OK  --> Session.commit() --> xác nhận receive
            |
            +-- ERROR --> Session.rollback() --> có thể redeliver
```

Sơ đồ là mô hình khái niệm; trong triển khai cụ thể, `Session` được tạo transacted và một transaction session gắn với lượt xử lý. Không cần ứng dụng tự gọi `session.commit()` trong listener: **container làm việc đó**.

## 5. DefaultMessageListenerContainer và SimpleMessageListenerContainer khác nhau

Spring Framework JMS có hai listener container phổ biến:

### 5.1. DefaultMessageListenerContainer (DMLC)

`org.springframework.jms.listener.DefaultMessageListenerContainer`:

- Thường được dùng cho `@JmsListener` thông qua `DefaultJmsListenerContainerFactory`.
- Sử dụng một vòng `MessageConsumer.receive()` nội bộ, cho phép quản lý receive/commit/rollback một cách chủ động.
- Có thể thay đổi số consumer theo `concurrency`, quản lý cache và tự phục hồi sau lỗi kết nối.
- Hỗ trợ **external transaction manager**, bao gồm JTA/XA khi broker/factory và coordinator được cấu hình đúng.
- Với non-transacted `AUTO_ACKNOWLEDGE`, message có thể được ACK **trước khi listener chạy**, nên Spring khuyến nghị local transaction hoặc transaction manager cho nhu cầu tin cậy.

### 5.2. SimpleMessageListenerContainer (SMLC)

`org.springframework.jms.listener.SimpleMessageListenerContainer`:

- Đăng ký listener qua JMS `MessageConsumer.setMessageListener(...)`.
- Thường tạo số Session và consumer cố định từ lúc start.
- Hỗ trợ local JMS transaction bằng `sessionTransacted=true` nhưng **không** tham gia external transaction manager theo cách DMLC hỗ trợ.
- Với `AUTO_ACKNOWLEDGE`, provider ACK sau callback, nhưng exception từ code listener do Spring xử lý nên không bảo đảm redelivery theo exception nghiệp vụ.
- Phù hợp khi muốn mô hình callback đơn giản và environment thích hợp; không nên dùng để kỳ vọng external XA.

### Bảng quyết định

| Tiêu chí | DMLC | SMLC |
| --- | --- | --- |
| Cơ chế nhận | Polling `receive()` có quản lý | JMS listener callback |
| Concurrency | Có khả năng thích nghi | Thường fixed |
| Local session transacted | Có | Có |
| External transaction/JTA | Có | Không |
| `AUTO_ACKNOWLEDGE` | ACK trước xử lý | ACK sau callback, exception từ app vẫn không đảm bảo redelivery |
| Phục hồi kết nối/scale | Nhiều tùy chọn | Đơn giản hơn |
| Lựa chọn thường gặp cho `@JmsListener` | **DMLC** | Khi có yêu cầu đặc biệt |

**Không có kết luận “container nào tự đảm bảo exactly-once”.** Loại container chỉ là một phần của cấu hình delivery semantics.

## 6. Lựa chọn mặc định an toàn: locally transacted JMS Session

Đối với Queue xử lý đơn hàng hoặc tác vụ quan trọng, `sessionTransacted=true` thường là lựa chọn đơn giản và hiệu quả trước khi cân nhắc XA.

Sự kiện bình thường:

```text
Broker --> receive ORDER-100
         --> listener xử lý thành công
         --> container commit JMS Session
         --> broker đánh dấu lượt nhận thành công
```

Sự kiện có lỗi:

```text
Broker --> receive ORDER-101
         --> listener ném IllegalStateException
         --> container rollback JMS Session
         --> broker đánh dấu cần redelivery
         --> có thể dispatch ORDER-101 lần nữa
```

**Redelivery không bắt buộc lập tức**: broker có thể đặt delay, giới hạn số lần thử, đưa message vào DLQ sau nhiều lần lỗi, hoặc áp policy riêng. Không nên khẳng định mọi broker sẽ gọi handler đúng hai lần khi code thất bại lần đầu.

### Điểm khác biệt so với một transaction database

Local JMS transaction chỉ điều khiển các hoạt động trên JMS Session của nó. Chẳng hạn:

```text
DB INSERT thành công + DB COMMIT
         |
         v
JMS Session.commit() thất bại
         |
         v
Message được redeliver; DB có thể đã lưu dữ liệu
```

Nếu handler tạo hóa đơn mỗi lần nhận mà không kiểm tra event ID, bạn có thể tạo **hai hóa đơn**. Cần idempotent consumer, unique constraint hoặc inbox table, không chỉ bật `sessionTransacted`.

## 7. Cấu hình thuần Spring Framework 6

Trong Spring Framework đã có `jakarta.jms.ConnectionFactory`, dùng `DefaultJmsListenerContainerFactory` để tạo container có transaction:

```java
package demo.jms;

import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration(proxyBeanMethods = false)
public class ListenerConfig {

    @Bean("txListenerFactory")
    public DefaultJmsListenerContainerFactory txListenerFactory(
            ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        factory.setConcurrency("1");
        return factory;
    }
}
```

Đây là **class cấu hình biên dịch được**, nhưng ứng dụng phải có bean `ConnectionFactory` hợp lệ và JMS infrastructure để đăng ký `@JmsListener`.

Listener chọn factory:

```java
@Component
public class OrderListener {

    @JmsListener(
        destination = "orders.in",
        containerFactory = "txListenerFactory"
    )
    public void onOrder(String orderId) {
        service.process(orderId);
    }
}
```

Đoạn listener trên **chỉ minh họa cấu trúc**: cần import `@Component`, `@JmsListener` và cung cấp field/service `service` thật. Không đưa class này vào chương trình nếu chưa khai báo dependency.

**Giải thích:** `@JmsListener` chọn `txListenerFactory`; factory tạo DMLC có Session transacted. Khi listener hoàn tất bình thường, container commit. Khi exception thoát ra, container rollback rồi provider có thể redeliver. `setConcurrency("1")` hữu ích cho thí nghiệm dễ quan sát; production có thể điều chỉnh theo Queue load và yêu cầu về ordering.

Không cần dùng `setSessionAcknowledgeMode(Session.CLIENT_ACKNOWLEDGE)` song song với `setSessionTransacted(true)` để “tăng gấp đôi bảo đảm”; trong session transacted, commit/rollback mới là cơ chế trung tâm.

## 8. Spring Boot: phải phân biệt auto-configured factory và custom factory

Trong **Spring Boot 3.x**, nếu JMS infrastructure có sẵn và bạn **không khai báo factory tùy chỉnh**, Boot tạo một default `JmsListenerContainerFactory` phù hợp. Theo hướng dẫn chính thức, **factory mặc định của Spring Boot có transaction**:

- Nếu có `JtaTransactionManager` thích hợp, Boot có thể gắn nó vào listener container.
- Nếu không có JTA manager, Boot thường bật **`sessionTransacted=true`**.
- Spring Boot starter/provider cấu hình `ConnectionFactory` để kết nối broker.

Đây là **khác biệt quan trọng**: trong Spring Framework, một `new DefaultJmsListenerContainerFactory()` trần **không tự động thừa hưởng** tất cả lựa chọn transaction của Spring Boot. Vì vậy, khi tự khai báo bean, hãy quyết định rõ điều bạn cần.

### 8.1. Giữ các mặc định Boot bằng Configurer

Dùng `org.springframework.boot.autoconfigure.jms.DefaultJmsListenerContainerFactoryConfigurer` với Boot 3:

```java
@Bean("txListenerFactory")
DefaultJmsListenerContainerFactory txListenerFactory(
        ConnectionFactory connectionFactory,
        DefaultJmsListenerContainerFactoryConfigurer configurer) {

    var factory = new DefaultJmsListenerContainerFactory();
    configurer.configure(
            factory,
            ConnectionFactoryUnwrapper.unwrapCaching(connectionFactory)
    );
    factory.setSessionTransacted(true);
    factory.setConcurrency("1");
    return factory;
}
```

Snippet này nằm **trong class `@Configuration`**, cần import `@Bean`, `ConnectionFactory`, `DefaultJmsListenerContainerFactory`, `DefaultJmsListenerContainerFactoryConfigurer`, `org.springframework.boot.jms.ConnectionFactoryUnwrapper`. `unwrapCaching` giúp listener container nhận native factory khi cần tự quản lý connection/recovery thay vì dùng factory cache wrapper do Boot thêm vào.

**Chú ý về external JTA:** đoạn này đặt `sessionTransacted=true` để minh họa local transaction khi không có external TM. Nếu ứng dụng thật dùng JTA/XA, phải để transaction manager/container tham gia đúng cơ chế được hỗ trợ; không sao chép một cấu hình local-tx rồi cho rằng nó đã tạo XA.

### 8.2. Cấu hình Boot bằng application.yml

Ví dụ hạ tầng Artemis local:

```yaml
spring:
  artemis:
    mode: native
    broker-url: tcp://localhost:61616
    user: demo
    password: demo
  jms:
    pub-sub-domain: false
    listener:
      concurrency: 1
      max-concurrency: 1
```

Các giá trị trên điều khiển broker connection, Queue domain và concurrency cho **factory được Boot cấu hình**. Chúng **không** thay thế việc xác định `sessionTransacted` của một custom factory tự tạo. Khi dùng Boot phiên bản khác, cần kiểm tra tên property theo bản đó (một số tên cấu hình session thay đổi giữa các nhánh Boot).

**Đừng nhầm:**

- `spring.jms.template.session.transacted`: liên quan session của **`JmsTemplate`**.
- `spring.jms.listener.session.transacted`: liên quan cấu hình session cho **listener container** ở những bản Boot hỗ trợ tên này.
- `spring.jms.listener.session.acknowledge-mode`: liên quan acknowledge mode non-transacted.
- `@Transactional`: tạo/join Spring transaction dựa vào transaction manager được chọn; **không tự cấu hình listener container làm XA**.

Với bài thực hành này, ta dùng **factory riêng, bật transaction tường minh** để tránh phụ thuộc vào các giá trị mặc định không hiển thị.

## 9. Demo đầy đủ: listener lỗi một lần, container rollback và nhận lại

Ví dụ sau dùng **Java 17, Spring Boot 3.3.13, Gradle 8.x và Apache ActiveMQ Artemis bên ngoài ứng dụng**. Mục tiêu minh họa chính xác trách nhiệm của container:

1. Producer gửi một `TextMessage("ORDER-001")`.
2. Listener nhận lần đầu, chủ động ném `IllegalStateException` để giả lập lỗi nghiệp vụ tạm thời.
3. `DefaultMessageListenerContainer` với `sessionTransacted=true` rollback JMS transaction.
4. Broker có thể gửi lại message theo redelivery policy.
5. Khi listener thành công ở lần sau, container commit.

Ví dụ **không** dùng DB nên chỉ kiểm tra transaction **JMS**, không khẳng định atomicity giữa DB và broker.

### 9.1. Broker thử nghiệm

Nếu đã có Docker, có thể chạy Artemis:

```bash
docker run --detach --rm --name artemis-container-tx -p 61616:61616 -e ARTEMIS_USER=demo -e ARTEMIS_PASSWORD=demo apache/artemis:latest-alpine
```

Đợi broker sẵn sàng rồi kiểm tra `docker logs artemis-container-tx`. Broker cần có Queue `demo.tx.orders` hoặc bật policy auto-create; user phải có quyền send/consume. Với môi trường production, phải provision Queue, bảo vệ credentials/TLS và thiết lập redelivery/DLQ phù hợp.

Sau buổi học, dừng broker:

```bash
docker stop artemis-container-tx
```

### 9.2. Cấu trúc file

```text
listener-transaction-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── resources/
    │   └── application.yml
    └── java/demo/jms/
        ├── ListenerTransactionApplication.java
        ├── ListenerTransactionConfig.java
        └── RetryOnceListener.java
```

`settings.gradle`:

```groovy
rootProject.name = 'listener-transaction-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
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
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
```

`src/main/resources/application.yml`:

```yaml
spring:
  artemis:
    mode: native
    broker-url: tcp://localhost:61616
    user: demo
    password: demo
  jms:
    pub-sub-domain: false
    listener:
      concurrency: 1
      max-concurrency: 1
```

Chương trình demo tự cấu hình một listener factory có transaction; các property về concurrency trong YAML chủ yếu giữ bộ cấu hình mặc định của Boot nhất quán. Nếu bạn dùng custom factory không đi qua Boot configurer, cần đặt concurrency trực tiếp trên factory như ví dụ tiếp theo.

### 9.3. Lớp ứng dụng: gửi một request

`src/main/java/demo/jms/ListenerTransactionApplication.java`:

```java
package demo.jms;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
@EnableJms
public class ListenerTransactionApplication {

    public static void main(String[] args) {
        SpringApplication.run(ListenerTransactionApplication.class, args);
    }

    @Bean
    ApplicationRunner sendTestMessage(JmsTemplate jmsTemplate) {
        return args -> {
            jmsTemplate.convertAndSend(
                    "demo.tx.orders", "ORDER-001");
            System.out.println("SENT ORDER-001");
        };
    }
}
```

Lệnh gửi thực thi khi context đã khởi động, nhưng listener chạy trên thread riêng nên log `SENT` có thể xuất hiện trước hoặc sau log nhận. Không coi thứ tự giữa hai thread là một bảo đảm nghiệp vụ.

### 9.4. Factory: chịu trách nhiệm transaction

`src/main/java/demo/jms/ListenerTransactionConfig.java`:

```java
package demo.jms;

import jakarta.jms.ConnectionFactory;

import org.springframework.boot.autoconfigure.jms.DefaultJmsListenerContainerFactoryConfigurer;
import org.springframework.boot.jms.ConnectionFactoryUnwrapper;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration(proxyBeanMethods = false)
public class ListenerTransactionConfig {

    @Bean("txListenerFactory")
    public DefaultJmsListenerContainerFactory txListenerFactory(
            ConnectionFactory connectionFactory,
            DefaultJmsListenerContainerFactoryConfigurer configurer) {

        var factory = new DefaultJmsListenerContainerFactory();
        configurer.configure(
                factory,
                ConnectionFactoryUnwrapper.unwrapCaching(connectionFactory)
        );

        // Chủ động cho phép container quản lý local JMS transaction.
        factory.setSessionTransacted(true);
        factory.setConcurrency("1");
        return factory;
    }
}
```

`configurer.configure` mang các mặc định của Spring Boot 3.x sang factory riêng. `factory.setSessionTransacted(true)` được đặt tường minh sau đó cho mục tiêu demo; `setConcurrency("1")` giữ một consumer để quan sát retry đơn giản. Không khai báo `JtaTransactionManager` trong demo này.

### 9.5. Listener: một lần lỗi, lần sau xử lý thành công

`src/main/java/demo/jms/RetryOnceListener.java`:

```java
package demo.jms;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class RetryOnceListener {

    private final AtomicInteger attempts = new AtomicInteger();

    @JmsListener(
            destination = "demo.tx.orders",
            containerFactory = "txListenerFactory"
    )
    public void onOrder(String payload) {
        int attempt = attempts.incrementAndGet();
        System.out.println("ATTEMPT " + attempt + " " + payload);

        if (attempt == 1) {
            throw new IllegalStateException("Transient demo failure");
        }

        System.out.println("PROCESSED " + payload);
    }
}
```

Chương trình chủ động ném **runtime exception** ở lần gọi đầu; vì exception thoát khỏi handler, container nhận biết lượt xử lý thất bại và rollback Session. Ở lần giao sau, counter tăng lên 2, method hoàn tất bình thường và container commit.

**Cảnh báo:** counter `AtomicInteger` là trạng thái **trong RAM của bean**, không phải công cụ deduplication production. Nếu JVM restart hoặc có nhiều instance/consumer, counter reset hoặc chia ra nhiều bản. Demo chỉ nhằm minh họa được ranh giới transaction.

### 9.6. Chạy và giải thích output

Với Java 17+, Gradle tương thích và broker sạch:

```bash
gradle bootRun
```

Nếu đã có Gradle Wrapper, dùng `./gradlew bootRun` trên Linux/macOS hoặc `gradlew.bat bootRun` trên Windows.

Với một message mới, broker hỗ trợ JMS local transaction và policy redelivery cho phép gửi lại, những dòng **do code demo in** có thể là:

```text
SENT ORDER-001
ATTEMPT 1 ORDER-001
ATTEMPT 2 ORDER-001
PROCESSED ORDER-001
```

Thứ tự dòng `SENT` có thể khác; Spring cũng log exception từ lần đầu và broker có thể trì hoãn lần redelivery. Các dòng trên là **kỳ vọng có điều kiện**, không phải stdout đã đo từ một lần chạy trong lúc biên soạn.

Điều cần thấy:

- `ATTEMPT 1`: listener đã **nhận và thực thi** nhưng chưa đồng nghĩa JMS commit.
- Exception: container rollback, do đó message **có thể** được giao lại.
- `ATTEMPT 2` rồi `PROCESSED`: handler hoàn thành.
- Container commit JMS transaction sau khi listener trả về bình thường; code không gọi `Message.acknowledge()` hoặc `Session.commit()`.

Nếu Queue còn backlog từ lần chạy trước, có listener cạnh tranh, broker giới hạn redelivery hoặc cấu hình DLQ, số lần gọi và thứ tự có thể khác. Hãy khởi tạo Queue/broker thử nghiệm sạch để dễ đối chiếu.

## 10. Vì sao không bắt exception rồi im lặng?

Sai lầm điển hình:

```java
@JmsListener(destination = "orders.in")
public void unsafeHandle(String text) {
    try {
        persistOrder(text);
    } catch (RuntimeException ex) {
        logger.error("Persist failed", ex);
        // Không ném lại; method trở về bình thường.
    }
}
```

Đây là **snippet minh họa trong bean có `logger` và `persistOrder` thật**, không phải một chương trình Java độc lập.

Với container transacted, khi method trả về bình thường, container **có lý do coi việc xử lý thành công** và commit JMS Session, mặc dù DB đã lỗi. Kết quả có thể là **message mất khỏi Queue nhưng dữ liệu nghiệp vụ chưa được lưu**.

Một cách an toàn hơn với lỗi tạm thời:

```java
@JmsListener(destination = "orders.in")
public void handle(String text) {
    try {
        persistOrder(text);
    } catch (TransientBusinessException ex) {
        logger.warn("Temporary failure; request rollback", ex);
        throw ex;
    }
}
```

Snippet này cần class exception và service phù hợp. `TransientBusinessException` nên kế thừa `RuntimeException`, hoặc ném lại một runtime exception đã chọn. Để exception tới container cho phép rollback, nhưng **rollback chỉ xảy ra khi transaction/ACK configuration thực sự hỗ trợ**.

### Nếu lỗi là vĩnh viễn thì sao?

Ví dụ schema message không hợp lệ hoặc phiên bản event không được hỗ trợ. Ném exception mãi có thể tạo **poison-message loop**. Cần chính sách:

1. Giới hạn số lần redelivery ở broker.
2. Có dead-letter address/Queue (DLQ), lưu lý do lỗi để phân tích.
3. Quarantine hoặc đánh dấu loại event không thể xử lý.
4. Sau khi sửa dữ liệu/ứng dụng mới cho phép replay có kiểm soát.
5. Không nuốt exception chỉ để tránh log mà bỏ message không có dấu vết.

“Lỗi vĩnh viễn” và “lỗi tạm thời” là **phân loại nghiệp vụ**, không phải một thuộc tính mà Spring listener container tự suy ra hoàn toàn từ loại exception.

## 11. ErrorHandler, JMS ExceptionListener và trách nhiệm rollback

Spring JMS có hai nhóm hook dễ nhầm:

- `ErrorHandler`: nhận exception phát sinh trong **xử lý listener**; thường dùng để log, đo metrics, cảnh báo.
- JMS `ExceptionListener`: nhận thông báo lỗi kết nối/provider theo cơ chế JMS; không đồng nghĩa thất bại của mọi message handler.

Ví dụ:

```java
factory.setErrorHandler(ex -> {
    System.err.println("Listener processing error: " + ex.getMessage());
});
```

Đây là snippet trong method cấu hình factory. `ErrorHandler` không thay thế việc có `sessionTransacted` hoặc transaction manager. Trong Spring containers, exception của listener thường **được container giữ lại và xử lý nội bộ** chứ không trực tiếp ném nguyên vẹn lên provider; container tự quyết định commit/rollback theo cấu hình.

**Đừng hiểu rằng chỉ cần cài ErrorHandler là broker chắc chắn redeliver.** Muốn retry trên failure, cần session transacted hoặc cơ chế acknowledgment/recovery phù hợp, cộng broker redelivery policy.

### Throw exception trong ErrorHandler có giúp rollback?

Không dùng hành vi ném lỗi của `ErrorHandler` như một “nút rollback”. Container đã có luồng xử lý exception và transaction riêng; ErrorHandler chủ yếu là observer. Giữ handler ổn định, không làm I/O chặn lâu hoặc làm mất nguyên nhân gốc. Quyết định rollback nên xuất phát từ lỗi trong listener và cấu hình transaction.

### Có thể thử log `JMSRedelivered`

Trong listener nhận raw message:

```java
@JmsListener(
    destination = "orders.in",
    containerFactory = "txListenerFactory")
public void handleRaw(jakarta.jms.TextMessage msg)
        throws jakarta.jms.JMSException {

    boolean redelivered = msg.getJMSRedelivered();
    String body = msg.getText();
    System.out.println("redelivered=" + redelivered + "; body=" + body);
}
```

Đây là method minh họa của một bean Spring, **không thêm nó vào cùng Queue demo ở mục 9** vì sẽ xuất hiện consumer cạnh tranh. `JMSRedelivered` giúp quan sát việc gửi lại nhưng không phải business event ID ổn định để khử trùng lặp. Một số broker cũng hỗ trợ `JMSXDeliveryCount`; kiểm tra sự tồn tại và chính sách provider khi sử dụng.

## 12. Local JMS transaction khác JmsTransactionManager thế nào?

Có hai khái niệm liên quan nhưng không giống nhau:

### Container tự dùng local JMS Session transaction

Khi `factory.setSessionTransacted(true)`, container tạo/nhận locally transacted `Session`, gọi listener, rồi tự commit hoặc rollback. Đây là cấu hình thường đủ cho một consumer xử lý một Queue và một số thao tác gửi trong cùng Session.

### Spring `JmsTransactionManager`

`org.springframework.jms.connection.JmsTransactionManager` là một `PlatformTransactionManager` điều phối **JMS local transaction cho một `ConnectionFactory`**, gắn Session phù hợp vào thread để các thao tác Spring JMS có thể cùng tham gia.

Ví dụ cấu hình một transaction manager cho các service JMS:

```java
@Bean("jmsTransactionManager")
JmsTransactionManager jmsTransactionManager(
        ConnectionFactory connectionFactory) {
    return new JmsTransactionManager(connectionFactory);
}
```

Snippet nằm trong class `@Configuration`; cần import `JmsTransactionManager`, `ConnectionFactory` và `@Bean`.

Nếu code được chạy dưới `@Transactional("jmsTransactionManager")` qua proxy Spring, những thao tác JMS phù hợp dùng cùng factory có thể cùng tham gia giao dịch JMS đó. Nhưng **`JmsTransactionManager` không tạo distributed transaction với một database chỉ vì DB cũng có bean DataSource**.

Trong bài toán listener, thường **không cần** vừa bật local transaction ở container vừa tự tạo `JmsTransactionManager` riêng chỉ để “commit hai lần”. Hãy xác định một chiến lược transaction nhất quán và test thật trước khi ghép nhiều tầng.

## 13. Database @Transactional và JMS transaction: ranh giới quan trọng

Ví dụ một listener làm hai việc:

```text
JMS receive ORDER-101
   |
   v
@Transactional("jdbcTransactionManager")
cập nhật bảng orders
   |
   v
DB transaction commit
   |
   v
JMS container commit Session
```

Trong một số cấu hình Spring Boot, ứng dụng có thể dùng một database transaction bên trong một JMS-local transacted listener. Điều đó tạo **hai local transactions được đồng bộ theo thứ tự phù hợp**, nhưng **không phải 2-phase commit XA**. Crash giữa hai commit vẫn có thể gây giao lại message với DB đã cập nhật.

### Một ví dụ idempotent bằng khóa sự kiện

Sử dụng business event ID `eventId` trong JMS property hoặc payload, không dùng `JMSMessageID` làm duy nhất nguồn kiểm soát nghiệp vụ nếu có bước tái phát event.

Thiết kế bảng:

```sql
CREATE TABLE processed_messages (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

Trong transaction DB:

```text
BEGIN
  INSERT INTO processed_messages(consumer_name, event_id, ...)
  Nếu duplicate key -> đã xử lý, bỏ qua side effect
  Nếu insert thành công -> cập nhật bảng orders
COMMIT
```

Đây là **pseudocode nghiệp vụ**, không phải SQL hoàn chỉnh dùng nguyên cho mọi database. Hãy dùng cú pháp insert/duplicate handling phù hợp DB, đồng thời đảm bảo insert dedupe và cập nhật nghiệp vụ thuộc **cùng database transaction**.

Kịch bản quan trọng:

1. Lần đầu listener cập nhật DB xong.
2. JMS commit thất bại do mất kết nối.
3. Broker redeliver event.
4. Lần hai kiểm tra bảng `processed_messages`, thấy event đã xử lý, **không lặp side effect**, và cho container hoàn tất JMS transaction.

Mẫu này thường được gọi là **idempotent consumer / inbox pattern**.

### Transactional outbox khi còn phải phát sự kiện mới

Nếu listener vừa ghi DB vừa phát event sang broker khác, một local JMS transaction không tự bao gồm broker khác. Transactional outbox lưu event cần phát trong DB transaction, rồi một publisher chuyên trách gửi từ outbox. Kết hợp inbox/deduplication ở consumer downstream để xử lý khả năng phát lại.

Chọn XA khi thật sự cần atomicity giữa nhiều tài nguyên đã được XA coordinator quản lý, không chọn vì tưởng nó là một option `@Transactional` đơn giản.

## 14. Khi cần external JTA/XA

`DefaultMessageListenerContainer` có thể sử dụng một `PlatformTransactionManager` ngoài qua `setTransactionManager`. Với Jakarta EE hoặc hệ thống có coordinator, thường dùng **`JtaTransactionManager`** để tham gia XA.

Mô hình:

```text
            JTA Transaction Coordinator
                   /           \
                  /             \
       XA-aware JMS factory    XA DataSource
               |                  |
       consume / ACK           UPDATE DB
               |                  |
               +---- 2PC ---------+
                  commit / rollback
```

Điều kiện để thực sự có một transaction chung:

- Broker hỗ trợ XA và `ConnectionFactory` XA-capable được đăng ký với coordinator.
- DataSource cũng là XA-capable/enlisted trong cùng JTA transaction.
- `DefaultMessageListenerContainer` sử dụng JTA transaction manager đúng instance.
- Message receive và thao tác DB thực sự nằm trong cùng transactional boundary, không mở kết nối độc lập bên ngoài.
- Coordinator lưu transaction log và có cơ chế recovery cho in-doubt transactions.

Đoạn cấu hình khái niệm:

```java
factory.setTransactionManager(jtaTransactionManager);
```

Chỉ riêng dòng trên **chưa đủ** để có XA. `jtaTransactionManager` phải là bean thật, broker/DB phải XA-aware và được enlist đúng. Không đưa một `DataSourceTransactionManager` bất kỳ vào listener rồi gọi đó là distributed transaction.

**Chi phí XA:** transaction logging, coordinated recovery, thêm round trips và độ phức tạp vận hành. Với nhiều workload, local JMS transaction + idempotency hoặc inbox/outbox dễ triển khai và tối ưu hơn.

## 15. Gửi response trong cùng transaction của container

Một listener có thể tạo **response JMS** sau khi xử lý request. Nếu gửi qua chính **JMS Session mà container cấp**, các thao tác receive và reply-send có thể cùng một local JMS transaction.

Ví dụ với `SessionAwareMessageListener` (mô hình Java interface của Spring):

```java
public final class RespondingListener
        implements SessionAwareMessageListener<TextMessage> {

    @Override
    public void onMessage(TextMessage request, Session session)
            throws JMSException {

        Destination replyTo = request.getJMSReplyTo();
        if (replyTo == null) {
            throw new IllegalArgumentException(
                    "Request must provide JMSReplyTo");
        }

        try (MessageProducer producer =
                     session.createProducer(replyTo)) {
            TextMessage response =
                    session.createTextMessage("ACK:" + request.getText());
            producer.send(response);
        }
    }
}
```

Đây là **một class minh họa** cần các import `jakarta.jms.TextMessage`, `jakarta.jms.Session`, `jakarta.jms.Destination`, `jakarta.jms.MessageProducer`, `jakarta.jms.JMSException` và `org.springframework.jms.listener.SessionAwareMessageListener`. Nếu provider không hỗ trợ `MessageProducer` trong try-with-resources theo phiên bản API bạn dùng, thay bằng `try/finally` và `producer.close()` đúng contract. **Không** dán class này vào demo mục 9 vì ví dụ đó chỉ dùng `@JmsListener` và một destination khác.

Khi container dùng local Session transaction, **cả receive và gửi reply bằng Session đó** có thể cùng commit/rollback. Nếu exception ném sau khi `producer.send` nhưng trước commit, container rollback transaction; reply chưa được committed sẽ không trở thành response đã xác nhận.

### Còn @JmsListener trả về String thì sao?

Spring listener adapter có thể tự gửi reply khi method trả về giá trị và có `JMSReplyTo`, `@SendTo` hoặc `JmsResponse` hợp lệ. Khi adapter gửi reply dùng listener Session của container, message reply có thể thuộc cùng transaction JMS của lần receive.

Nhưng nếu handler **tự inject một `JmsTemplate` khác**, gắn vào ConnectionFactory khác hoặc tự tạo Session riêng, đừng mặc định lệnh gửi đó tham gia transaction của container. Cần kiểm tra factory, session exposure, transaction synchronization và integration test.

## 16. Concurrency, redelivery, DLQ và vòng đời container

### 16.1. Tăng concurrency không đồng nghĩa tăng exactly-once

Đối với Queue, có nhiều consumer chạy song song sẽ tăng throughput nhưng:

- Thứ tự xử lý log có thể khác thứ tự message được gửi.
- Message rollback có thể được giao cho **consumer khác**, không nhất thiết handler instance ban đầu.
- Trạng thái trong RAM của listener (như `AtomicInteger` trong demo) không thể dùng làm dedupe toàn hệ thống.
- Nếu cần thứ tự theo một order ID, nên xem xét partition/routing, single-active-consumer hoặc chính sách group của broker.

### 16.2. Retry không phải chỉ là một thuộc tính của Spring

Khi container rollback, provider quyết định khi nào và bao nhiêu lần redeliver theo policy được cấu hình. Các yếu tố thường cần xem:

- Redelivery delay/backoff.
- Giới hạn số lần giao lại (max delivery attempts).
- Dead-letter Queue/address.
- JMS header `JMSRedelivered` hoặc property `JMSXDeliveryCount` nếu broker có.
- Quota, prefetch, connection recovery và shutdown.

Spring có thể khôi phục connection/consumer khi broker tạm mất kết nối, nhưng **đó không đồng nghĩa tự động quyết định giới hạn retry nghiệp vụ của từng message**. Chính sách redelivery và DLQ thuộc contract broker cùng quy tắc xử lý của ứng dụng.

### 16.3. Shutdown, in-flight messages và transaction

Khi ứng dụng dừng, listener container cần chờ hoặc xử lý các receive/tasks đang chạy. Nếu bị kill bất ngờ khi transaction chưa commit, JMS broker có thể redeliver. Nếu dùng `AUTO_ACKNOWLEDGE` trước xử lý, không thể giả định message cũng được cứu theo cách đó.

Theo dõi:

- Số consumer đang chạy.
- Số message đang xử lý, tuổi message và Queue depth.
- Số rollback, redelivery, DLQ và lỗi conversion.
- Thời gian xử lý listener, DB transaction và JMS commit.
- Số message thiếu/duplicated business event ID.

**Không** sửa consumer count hoặc cache tùy tiện chỉ để che lấp lỗi giao dịch; cần kiểm tra acknowledgment/transaction trước.

## 17. Bảng xử lý sự cố

| Triệu chứng | Nguyên nhân có thể | Kiểm tra/sửa |
| --- | --- | --- |
| Listener ném exception nhưng message không được nhận lại | Non-transacted `AUTO_ACKNOWLEDGE`, hoặc broker policy/consumer khác. | Kiểm tra đúng factory, `sessionTransacted`, mode, Queue depth và DLQ. |
| `AUTO_ACKNOWLEDGE` mất message khi xử lý lỗi | DMLC đã ACK trước listener chạy. | Bật local transaction hoặc external transaction đúng cách. |
| `@JmsListener` chưa bật transaction dù Boot thường transacted | Custom factory tạo trần mà không dùng configurer. | Cấu hình tường minh `setSessionTransacted(true)` hoặc Boot configurer. |
| Code bắt exception rồi không ném lại | Container thấy listener hoàn thành bình thường. | Chỉ bắt khi đã xử lý thành công; nếu cần retry thì rethrow. |
| Một event làm side effect hai lần | JMS redelivery sau DB commit, retry producer hoặc nhiều consumer. | Business event ID, unique constraint, idempotent inbox. |
| Listener bị lặp mãi trên poison message | Broker redelivery không có giới hạn hoặc chưa có DLQ. | Thiết lập max attempts/backoff/DLQ và quy trình replay. |
| Có ErrorHandler nhưng không rollback | ErrorHandler không tự bật JMS transaction. | Kiểm tra transaction manager/Session, lỗi có thoát khỏi listener không. |
| `Message.acknowledge()` làm message khác biến mất | CLIENT_ACK thường ACK các message đã tiêu thụ trong cùng Session. | Để Spring quản lý ACK hoặc thiết kế Session/individual mode đúng chuẩn. |
| DB rollback nhưng JMS đã ACK | DB và JMS là hai resource độc lập; mode/transaction chưa đồng bộ. | Rà transaction boundary, dùng locally transacted Session + DB tx hoặc XA. |
| JMS rollback nhưng DB đã commit | Crash giữa hai commit local. | Idempotency, inbox, outbox hoặc XA nếu cần. |
| Reply được gửi nhưng không thể rollback cùng request | Reply gửi qua factory/Session khác. | Dùng đúng Session transaction hoặc thiết kế outbox. |
| `@Transactional` không hoạt động như kỳ vọng | Proxy không áp dụng, chọn sai transaction manager, self-invocation. | Kiểm tra proxy/bean, manager được chọn và test rollback DB thật. |
| Chuyển từ SMLC sang DMLC thay đổi hành vi ACK | Cơ chế callback khác polling. | Test lại `AUTO_ACKNOWLEDGE`, exception và shutdown. |
| Nhiều consumer xử lý đảo thứ tự | Concurrency, retry, requeue. | Thiết kế ordering/grouping hoặc giảm concurrency ở nhánh cần thứ tự. |
| Broker mất kết nối, listener ngưng | Recovery/backoff hoặc credentials/ACL, factory caching. | Kiểm tra log container, ConnectionFactory và broker. |

### Quy trình chẩn đoán ngắn

1. Xác định **đúng listener container factory** mà `@JmsListener` đang dùng.
2. Xác định container là DMLC hay SMLC; đọc `sessionTransacted`, `sessionAcknowledgeMode`, external `transactionManager`.
3. Kiểm tra exception có thực sự **thoát ra khỏi handler** không.
4. Xem broker: message đã ACK/commit hay đang unacknowledged, redelivered, expired hoặc vào DLQ.
5. Nếu có DB, vẽ timeline **DB commit ↔ JMS commit**, xác định cửa sổ duplicate hoặc loss.
6. Kiểm tra transaction manager mà `@Transactional` sử dụng và proxy có hiệu lực.
7. Thử lại trên Queue sạch, một consumer, lỗi được tiêm một lần, rồi tăng concurrency và kiểm tra shutdown/recovery.

## 18. Kiểm thử và bài tập tự luyện

### 18.1. Unit test cấu hình

Có thể unit test factory bean qua Spring context để xác nhận tên bean và cấu hình `sessionTransacted`. Đừng giả định mock `JmsTemplate` hoặc mock listener container tự tạo JMS transaction; mock chỉ giúp kiểm tra lời gọi cấu hình.

Test quan trọng hơn là **integration test với broker thật**:

1. Gửi một message, handler thành công, xác nhận message không được giao lại sau commit.
2. Tiêm lỗi trước side effect, xác nhận container rollback và broker redeliver theo policy.
3. Ghi DB rồi tiêm lỗi sau DB commit nhưng trước JMS commit; xác nhận handler idempotent khi redeliver.
4. Thử một message không hợp lệ liên tục; kiểm tra giới hạn attempts, DLQ, metrics.
5. Thử shutdown bất ngờ lúc handler đang chạy, kiểm tra khả năng redelivery/duplicate.
6. Thử riêng `AUTO_ACKNOWLEDGE` và `sessionTransacted=true`; ghi nhận khác biệt.
7. Kiểm tra phản hồi gửi bằng **cùng Session** có rollback cùng request; nếu gửi qua factory khác thì ghi nhận transaction boundary riêng.
8. Tăng concurrency và chắc chắn handler thread-safe, deduplication không phụ thuộc một counter trong RAM.

Không viết test kiểu “chờ đúng 100 ms” hay “luôn redeliver ngay trong 1 giây”: provider/backoff/network có độ trễ. Dùng polling có timeout tổng đủ hợp lý, assertion theo business event ID và quan sát broker state.

### 18.2. Câu hỏi và đáp án

**Câu 1.** Một `DefaultMessageListenerContainer` dùng `AUTO_ACKNOWLEDGE` và listener ném `IllegalStateException`. Message có chắc được redeliver không?

**Đáp án:** Không. DMLC non-transacted auto ACK có thể xác nhận message **trước khi gọi listener**; exception sau đó không tạo rollback của message đã ACK.

**Câu 2.** Bật `sessionTransacted=true`, listener nhận message rồi ném exception. Ai gọi `rollback()`?

**Đáp án:** **Listener container** quản lý locally transacted Session và rollback khi lỗi thoát ra. Listener không cần tự gọi `session.rollback()`.

**Câu 3.** Một service dùng `@Transactional` với DB. Có phải transaction đó tự động làm JMS receive và DB commit cùng một XA transaction?

**Đáp án:** Không. Cần JTA/XA coordinator và XA-aware resources được enlist đúng. Hai local transactions chỉ đồng bộ theo thiết kế vẫn có khoảng thời gian bất nhất.

**Câu 4.** `CLIENT_ACKNOWLEDGE` có nghĩa method `@JmsListener` bắt buộc phải gọi `message.acknowledge()` không?

**Đáp án:** Không. Spring container thường ACK sau khi listener thành công; cần hiểu mode/container cụ thể. Tự ACK có thể ảnh hưởng nhiều message trên cùng Session.

**Câu 5.** Listener bắt exception, log rồi return bình thường. Dù container transacted, message có thể bị commit không?

**Đáp án:** Có. Container nhìn thấy handler hoàn tất; nếu không có tín hiệu thất bại thì có thể commit JMS transaction.

**Câu 6.** Vì sao local JMS transaction + DB transaction cần business event ID?

**Đáp án:** Crash sau DB commit nhưng trước JMS commit có thể khiến message redeliver; event ID giúp phát hiện đã xử lý và tránh side effect trùng.

**Câu 7.** Spring Boot 3 tạo default factory có transaction, vậy `new DefaultJmsListenerContainerFactory()` của ứng dụng có tự transacted giống hệt không?

**Đáp án:** Không. Custom bean phải cấu hình rõ hoặc dùng `DefaultJmsListenerContainerFactoryConfigurer` để kế thừa lựa chọn Boot phù hợp.

**Câu 8.** Khi listener gửi reply bằng cùng `Session` với receive và Session là locally transacted, rollback có thể hủy cả reply chưa commit không?

**Đáp án:** Có, nếu cả hai thao tác thuộc **đúng một JMS Session transaction**. Nếu reply dùng Session hoặc broker khác, cần đánh giá giao dịch riêng.

**Câu 9.** `DUPS_OK_ACKNOWLEDGE` có thể dùng để bảo đảm rollback khi listener ném exception không?

**Đáp án:** Không. Đây là ACK lazy, không phải replacement tin cậy cho `sessionTransacted=true`.

### 18.3. Bài tập

**Bài A.** Chạy demo mục 9 trên một Queue sạch. Ghi nhận output, số lần nhận và trạng thái Queue. Sau đó bỏ dòng `factory.setSessionTransacted(true)` **chỉ trong môi trường thử nghiệm không có transaction manager**. Dự đoán và quan sát sự khác biệt; tuyệt đối không suy từ kết quả một lần rằng provider khác sẽ giống hệt.

**Bài B.** Thêm một bảng `processed_messages` với khóa duy nhất `eventId`. Cố ý để JMS redeliver sau lần xử lý đầu, kiểm tra side effect nghiệp vụ chỉ thực hiện một lần.

**Bài C.** Cấu hình redelivery tối đa theo tài liệu broker rồi gửi một message luôn ném exception. Kiểm tra DLQ, retry count và cảnh báo vận hành.

**Bài D.** Tạo request-reply trong cùng Session transaction và tiêm lỗi trước commit. Kiểm tra response chưa được committed rồi chỉ xuất hiện ở lần xử lý thành công.

## 19. Tài liệu chính thức

- [Spring Framework 6.2 — Receiving a Message / Processing Messages Within Transactions](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html)
- [Spring Framework 6.2 — Using Spring JMS / Simple vs Default Listener Container](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html)
- [Spring Framework 6.2 — AbstractMessageListenerContainer: acknowledgment modes](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/listener/AbstractMessageListenerContainer.html)
- [Spring Framework 6.2 — DefaultMessageListenerContainer](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html)
- [Spring Framework 6.2 — SimpleMessageListenerContainer](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/listener/SimpleMessageListenerContainer.html)
- [Spring Framework 6.2 — AbstractPollingMessageListenerContainer: external transaction manager](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/listener/AbstractPollingMessageListenerContainer.html)
- [Spring Boot 3 — JMS listener auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/messaging/jms.html)
- [Spring Boot — Messaging with JMS](https://spring.io/guides/gs/messaging-jms/)
- [Jakarta Messaging 3.1 — Session, acknowledgment, transaction semantics](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)
- [Apache ActiveMQ Artemis — broker, addresses, DLQ/redelivery](https://artemis.apache.org/components/artemis/documentation/latest/)

**Kết luận:** Listener là nơi thực hiện nghiệp vụ, còn **listener container quản lý Session, ACK, commit/rollback và xử lý exception**. Để tránh mất message trong xử lý Queue quan trọng, nên hiểu rõ DMLC/SMLC và cấu hình **`sessionTransacted=true`** hoặc external transaction manager phù hợp. Tuy vậy, **JMS commit không tự đồng nghĩa DB commit**: muốn xử lý an toàn khi có redelivery, cần idempotency, quy tắc retry/DLQ và kiểm thử transaction boundary thực tế.
