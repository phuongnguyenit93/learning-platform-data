# concurrentConsumers và maxConcurrentConsumers trong Spring JMS DefaultMessageListenerContainer

## 1. Vì sao cần hai tham số concurrency?

Khi một ứng dụng Spring JMS tiêu thụ Queue, thông điệp có thể đến chậm vào ban đêm nhưng tăng đột biến lúc cao điểm. Nếu chỉ có **một consumer**, tất cả message được xử lý gần như tuần tự; một callback xử lý lâu sẽ làm các message khác chờ. Nếu cố định **nhiều consumer** mọi lúc, ứng dụng tốn connection/session, consumer và thread ngay cả khi Queue trống.

`org.springframework.jms.listener.DefaultMessageListenerContainer` (gọi tắt **DMLC**) giải quyết sự đánh đổi này bằng hai giới hạn:

- **`concurrentConsumers`**: số consumer lõi/tối thiểu được lên lịch duy trì.
- **`maxConcurrentConsumers`**: mức trần số consumer container có thể mở rộng tới **khi tăng tải**.

Hai tham số mô tả **độ song song ở tầng JMS consumer của một listener container**, không phải số message trong một lô, số Queue, thread HTTP, số connection TCP chắc chắn, số replica Kubernetes hay mức đảm bảo "chính xác N tác vụ chạy cùng lúc".

Bài học giúp bạn:

1. Phân biệt `concurrentConsumers` và `maxConcurrentConsumers`, giá trị mặc định và phạm vi hiệu lực.
2. Hiểu cơ chế DMLC gọi `MessageConsumer.receive()`, lên lịch consumer dư khi Queue bận và thu hẹp khi nhàn rỗi.
3. Cấu hình bằng JavaConfig, `setConcurrency("2-5")`, Spring Boot properties và `@JmsListener(concurrency = "...")`.
4. Chạy ví dụ Java 17+ / Spring Boot 3.5.8 / Apache ActiveMQ Artemis với Queue và listener có nhiều worker.
5. Kiểm tra số consumer **được cấu hình** khác với số **đã lên lịch/đang hoạt động** qua registry.
6. Điều chỉnh scaling, prefetch, receive timeout, transaction, thread executor và tránh lỗi thứ tự xử lý.
7. Thiết kế test/tuning dựa trên backlog, throughput, latency và tài nguyên thực tế.

Bài dựa vào **Spring Framework 6.2.x** và **Jakarta Messaging 3.x** (`jakarta.jms.*`). Một số tham số có cùng tên trên phiên bản khác, nhưng hành vi cụ thể của idle scaling có thể thay đổi; luôn đọc Javadoc đúng phiên bản ứng dụng.

## 2. DefaultMessageListenerContainer vận hành thế nào?

DMLC là listener container thường dùng của Spring JMS. Khác với chương trình tự gọi `jmsTemplate.receive(...)`, DMLC tạo và quản lý các **listener invoker tasks**. Mỗi invoker hoạt động có thể giữ `Session` và `MessageConsumer` riêng, lặp các lần `receive` rồi gọi business listener.

```text
                 Spring ApplicationContext
                           |
                  DefaultMessageListenerContainer
                           |
               +-----------+-----------+
               |           |           |
          Invoker #1    Invoker #2   Invoker #3 ... #N
               |           |           |
           Session 1   Session 2    Session 3
               |           |           |
           Consumer 1  Consumer 2   Consumer 3
               \           |           /
                \          |          /
                   JMS Queue trên broker
                           |
                    MessageListener
                  (@JmsListener/POJO)
```

Ở mức khái niệm:

1. Khi container start, nó chuẩn bị ít nhất số consumer lõi theo cấu hình.
2. Một invoker chờ một message từ `MessageConsumer.receive(...)` trong khoảng `receiveTimeout`.
3. Nếu có message, invoker gọi listener tương ứng, hoàn tất acknowledge/transaction theo container.
4. Nếu có nhiều message và các invoker hiện tại đều bận, DMLC **có thể** lên lịch invoker/consumer bổ sung, không vượt trần `maxConcurrentConsumers`.
5. Khi Queue bớt tải, các consumer **dư trên mức lõi** có thể trở nên idle và được thu hồi theo các điều kiện timeout/idle-task.
6. Consumer lõi được giữ để duy trì khả năng nhận, trừ lúc container stop/shutdown/recovery.

Tăng consumer có ý nghĩa nhất với **Queue có competing consumers**. Với Topic thông thường, tạo nhiều consumer trên cùng Topic có thể khiến **mỗi subscription nhận cùng một publication**, gây xử lý lặp ngay trong một instance. Hãy xem mục 10 trước khi tăng concurrency cho Topic.

### 2.1. Một consumer không nhất thiết bằng một thread vật lý vĩnh viễn

Trong cấu hình mặc định, DMLC dùng một `TaskExecutor` để chạy listener invokers; một invoker có thể sử dụng thread để chờ receive và xử lý callback. Nhưng:
- Một task được **lên lịch** không phải lúc nào cũng đang **chạy** (executor có thể bị nghẽn).
- Một consumer đang **active** không có nghĩa đang **xử lý message hữu ích**; nó có thể đang chờ `receive`.
- Session/consumer có thể được tái sử dụng hoặc tạo lại theo cache level, transaction manager, lỗi broker.
- Java 21+ và Spring Framework 6.2 cho phép chọn virtual threads cho default executor qua `setVirtualThreads(true)`; **ví dụ Java 17 của bài không dùng tính năng này**.

Vì vậy việc nhìn vào số thread của JVM hoặc Queue depth không đủ để khẳng định số consumer đang nhận.

## 3. concurrentConsumers: mức lõi duy trì

DMLC khai báo:

```java
container.setConcurrentConsumers(2);
```

Ý nghĩa: container sẽ cố duy trì **hai consumer lõi được lên lịch** khi hoạt động bình thường. Giá trị mặc định của DMLC là **1**.

Các đặc điểm:

- Phải là số nguyên **lớn hơn hoặc bằng 1**.
- Tăng từ 1 lên 2 làm tăng khả năng hai message khác nhau trong Queue được xử lý cùng lúc, nếu broker có đủ message/permission/resource.
- Đặt 4 nghĩa là có mức lõi 4, **không** bảo đảm có bốn message đang được xử lý mọi thời điểm.
- Khi Queue rỗng, các consumer lõi vẫn có thể tiếp tục chờ receive.
- Tăng mức lõi ảnh hưởng cả tài nguyên lúc nhàn rỗi: session, consumer registrations, thread tasks, bộ nhớ/prefetch theo broker.
- Với một Queue ít message và yêu cầu thứ tự, giữ `concurrentConsumers=1` thường hợp lý.

**Bẫy quan trọng:** khi gọi `setConcurrentConsumers(4)` trong lúc max cũ là 1, Spring sẽ tự bảo đảm max **không nhỏ hơn core**. Muốn tạo dải 4..8, hãy đặt cả hai giá trị, không chỉ thay core rồi mặc định hệ thống có khả năng scale vô hạn.

`getConcurrentConsumers()` trả **cấu hình hiện hành**, không phải số consumer đang active. Để quan sát runtime, dùng `getScheduledConsumerCount()` và `getActiveConsumerCount()`.

## 4. maxConcurrentConsumers: trần mở rộng theo tải

DMLC khai báo:

```java
container.setMaxConcurrentConsumers(6);
```

Ý nghĩa: khi tải tăng, DMLC **có thể mở thêm consumer**, từ mức lõi đến tối đa **6 consumer** cho **container này**; mặc định max cũng là **1**. Nếu max bằng core, **không có khoảng mở rộng động**.

Ví dụ:

```java
container.setConcurrentConsumers(2);
container.setMaxConcurrentConsumers(6);
```

Ở idle, mục tiêu là duy trì 2 consumer lõi. Khi số message đến và thời gian xử lý cao khiến các invoker bận, container có thể tăng 3, 4, 5, 6 consumer. Khi hết tải, các invoker dư có thể dừng; còn 2 lõi tiếp tục chờ.

**Không hiểu sai:**

- `maxConcurrentConsumers=6` **không có nghĩa lúc startup tạo ngay 6 consumer**.
- `maxConcurrentConsumers=6` **không có nghĩa luôn xử lý 6 message song song**.
- Nó **không tự khởi động thêm 6 replica**, không tạo 6 Queue và không cam kết 6 TCP connections (connection có thể chia sẻ).
- Nó là giới hạn cho **một instance của một listener container**, không phải trần toàn bộ cluster.
- Nó là **trần cấu hình**, không phải “target CPU utilization” hay auto-scaler theo độ dài Queue một cách trực tiếp.

### 4.1. Giá trị mặc định

| Tham số của DMLC | Mặc định | Ý nghĩa |
| --- | ---: | --- |
| `concurrentConsumers` | 1 | Số consumer lõi được giữ. |
| `maxConcurrentConsumers` | 1 | Trần consumer; khi cả hai bằng 1 không có mở rộng động. |
| `receiveTimeout` | 1.000 ms | Thời gian một lời gọi nhận chờ message, ảnh hưởng cách xác định idle. |
| `idleConsumerLimit` | 1 | Giới hạn số consumer đang idle cho phép trước khi tạo thêm invoker. |
| `idleTaskExecutionLimit` | 1 | Số lần thực thi task được đánh dấu idle trước khi consumer dư có thể dừng. |

Trên Spring Framework 6.2 với executor mặc định, `idleReceivesPerTaskLimit` hiệu lực thường **10 lần receive trả null liên tiếp** đối với consumer dư. Với `receiveTimeout=1s` và điều kiện khác bình thường, việc thu hẹp có thể xảy ra sau khoảng 10 giây idle, **không phải SLA cố định 10 giây**. Khi sử dụng `SchedulingTaskExecutor` ưu tiên task ngắn, `maxMessagesPerTask` có default/nhịp reschedule khác. Các con số về idle scaling là đặc điểm implementation, không phải cam kết cứng bất chấp môi trường.

## 5. Các cách khai báo concurrency — và bẫy cú pháp

### 5.1. Gọi hai setter trên DefaultMessageListenerContainer

```java
DefaultMessageListenerContainer container =
        new DefaultMessageListenerContainer();

container.setConcurrentConsumers(2);
container.setMaxConcurrentConsumers(5);
```

Đây là snippet trong JavaConfig đã có các tham số khác như `ConnectionFactory`, destination và `MessageListener`. Không thể chạy độc lập chỉ bằng hai setter.

### 5.2. Dùng một chuỗi setConcurrency

Spring hỗ trợ:

```java
container.setConcurrency("2-5"); // core=2, max=5.
container.setConcurrency("5");   // core=1, max=5.
```

**Đặc biệt:** chuỗi một số `"5"` với DMLC được hiểu là **giới hạn trên 5, core 1**, **không phải cố định 5 consumer**. Muốn **cố định 5**, đặt cả core và max bằng 5:

```java
container.setConcurrency("5-5");
```

Bảng ý nghĩa:

| Cấu hình | Core | Max | Hành vi |
| --- | ---: | ---: | --- |
| Không cấu hình | 1 | 1 | Một consumer lõi, không scale lên. |
| `"1-1"` | 1 | 1 | Tương đương mặc định. |
| `"2-5"` | 2 | 5 | Giữ khoảng hai core, có thể mở thêm tới năm. |
| `"1-8"` | 1 | 8 | Tiết kiệm idle resource nhưng có thể tăng chậm khi có burst. |
| `"5"` | 1 | 5 | **Một core**, trần năm. |
| `"5-5"` | 5 | 5 | Năm consumer cố định theo cấu hình lõi/trần. |

`setConcurrency` và các setter yêu cầu giá trị hợp lệ. Tránh số không, số âm, cú pháp `"two-five"`, khoảng trắng không theo format hoặc dải ngược `"5-2"`; hãy validate config ở startup thay vì chấp nhận một cấu hình trái ý nghĩa. Implementation có thể chuẩn hóa max không thấp hơn core, nhưng đó không phải lý do cố tình viết dải đảo.

### 5.3. Set trên DefaultJmsListenerContainerFactory

Với `@JmsListener`, container được tạo bởi factory nên thường cấu hình ở đây:

```java
@Bean(name = "jmsListenerContainerFactory")
DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
        ConnectionFactory connectionFactory) {

    var factory = new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setConcurrency("2-5");
    factory.setSessionTransacted(true);
    return factory;
}
```

Đây là snippet cần import `jakarta.jms.ConnectionFactory`, `org.springframework.jms.config.DefaultJmsListenerContainerFactory` và `@Bean` trong class cấu hình. Factory sẽ truyền các tùy chọn sang từng `DefaultMessageListenerContainer` được tạo. Thay đổi factory sau khi container đã chạy **không mặc định tái cấu hình toàn bộ container hiện có**.

### 5.4. Override riêng từng @JmsListener

Nếu tất cả listener dùng factory mặc định `"2-5"`, nhưng một Queue cần ít consumer hơn:

```java
@JmsListener(
        id = "paymentsListener",
        destination = "payments.queue",
        concurrency = "1-2")
public void onPayment(String body) {
    // Xử lý thanh toán.
}
```

Đây là snippet trong Spring bean đã bật `@EnableJms`. Thuộc tính `concurrency` của endpoint **override giá trị trên factory** nếu container hỗ trợ. Đừng nhầm `concurrency="2"` là chắc chắn hai consumer cố định: với DMLC, chỉ một số đơn được hiểu là core 1, max 2; muốn cố định 2 dùng `"2-2"`.

### 5.5. Spring Boot properties

Nếu bạn **dùng factory được Spring Boot tự cấu hình** (không tự thay bằng bean thủ công), Spring Boot 3.5 cung cấp:

```properties
spring.jms.listener.min-concurrency=2
spring.jms.listener.max-concurrency=5
```

Ở lớp abstraction của Boot, `min-concurrency` tương ứng mức tối thiểu/cốt lõi; `max-concurrency` là mức tối đa. Property cũ `spring.jms.listener.concurrency` đã được đánh dấu deprecated từ Boot 3.2; ưu tiên `min-concurrency` thay vì copy cấu hình lỗi thời.

**Điểm tích hợp:** khi bạn tự định nghĩa bean `jmsListenerContainerFactory` với `new DefaultJmsListenerContainerFactory()`, Boot có thể back off không tạo factory mặc định, và hai property trên **không tự động gắn vào bean tự viết**. Bạn phải tự gọi `setConcurrency("2-5")` hoặc dùng `DefaultJmsListenerContainerFactoryConfigurer` để áp lại cấu hình Boot trước khi override phần mong muốn.

Ví dụ dùng configurer, **thay thế** ví dụ tạo factory thuần ở trên:

```java
@Bean(name = "jmsListenerContainerFactory")
DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
        ConnectionFactory connectionFactory,
        DefaultJmsListenerContainerFactoryConfigurer bootConfigurer) {

    var factory = new DefaultJmsListenerContainerFactory();
    bootConfigurer.configure(
            factory,
            ConnectionFactoryUnwrapper.unwrapCaching(connectionFactory));

    // Những thiết lập đặc thù ứng dụng có thể override ở đây.
    factory.setSessionTransacted(true);
    return factory;
}
```

Đây là snippet dành cho Spring Boot 3.5 có imports `org.springframework.boot.autoconfigure.jms.DefaultJmsListenerContainerFactoryConfigurer` và `org.springframework.boot.jms.ConnectionFactoryUnwrapper`, không phải Java file độc lập. Khi dùng, lựa chọn unwrap/caching/transaction manager phải phù hợp Spring Boot/provider. Ví dụ full project ở mục 7 dùng cách **cấu hình thủ công tường minh**, nên không đặt min/max bằng property Boot để tránh nguồn cấu hình cạnh tranh.

## 6. Cơ chế mở rộng: tăng chậm, thu hồi theo idle

Hãy xét `concurrentConsumers=2`, `maxConcurrentConsumers=5`:

```text
Thời điểm       Tải Queue                  Consumer theo kỳ vọng
--------        ---------                  -----------------------
08:00           Queue trống                ~2 (core)
09:00           Vừa có vài message        2 (thường đủ)
09:05           Backlog tăng, listener bận  2 -> 3 -> 4 -> 5 (có thể)
09:10           Nhiều message liên tục      <=5
09:30           Queue hết tải              5 -> 4 -> 3 -> 2 (theo idle)
10:00           Queue trống                ~2 (core)
```

Đây là **timeline minh họa**, không phải một biểu đồ số đo cố định của Spring. Không thể hứa 5 consumer sẽ được mở đúng sau 3 message hoặc sau 1 giây. Điều kiện lên lịch mới phụ thuộc trạng thái invoker, khả năng TaskExecutor cấp thread, có idle consumer không, tần suất `receive` trả message và việc broker chuyển message tới consumer nào.

### 6.1. idleConsumerLimit

`setIdleConsumerLimit(int)` đặt giới hạn số consumer đang idle được phép khi cân nhắc tạo invoker mới. Mặc định **1**, nghĩa là container không mở thêm khi đã có consumer idle thích hợp. Nâng lên một giá trị lớn hơn có thể làm hệ thống **scale up tích cực hơn**, nhưng tốn thêm consumer/thread khi tải không đủ.

```java
container.setIdleConsumerLimit(2);
```

Đây là snippet cấu hình DMLC trong bean phù hợp; không phải công tắc “luôn có hai consumer idle”. Nó chỉ ảnh hưởng điều kiện scheduler, không nâng max nếu `maxConcurrentConsumers` vẫn là 1.

### 6.2. idleTaskExecutionLimit

`setIdleTaskExecutionLimit(int)` nói sau bao nhiêu task execution được đánh dấu idle, consumer dư có thể được dừng. Mặc định **1**. Core consumers vẫn được giữ trong điều kiện bình thường.

```java
container.setIdleTaskExecutionLimit(3);
```

Nâng giới hạn có thể giảm dao động tăng/giảm invoker khi tải có các khoảng trống ngắn, đổi lại giữ resource lâu hơn. Khái niệm *task execution* không giống một message và không nhất thiết giống một lần `receive`.

### 6.3. idleReceivesPerTaskLimit của Spring 6.2

`setIdleReceivesPerTaskLimit(int)` quyết định sau bao nhiêu **lần receive không lấy được message (`null`)** một consumer dư được đánh dấu idle trong một task. Với executor mặc định của Spring 6.2, mặc định hiệu lực thường là **10 lần receive null**. DMLC dùng thêm `idleTaskExecutionLimit` để quyết định có thu hồi invoker dư hay không.

```java
container.setIdleReceivesPerTaskLimit(20);
container.setReceiveTimeout(1_000L);
```

Mô hình đơn giản: nếu Queue thật sự idle và receive lần nào cũng chờ khoảng 1 giây rồi trả null, 20 lần tương ứng khoảng 20 giây **trong điều kiện lý tưởng**. Không coi đây là SLA cứng vì thread scheduling, broker, task executor và policy khác có thể thay đổi hành vi.

Nếu đặt receive timeout rất lớn, DMLC có thể mất thời gian để phát hiện idle/scale down. Nếu đặt rất nhỏ và tăng số consumer mạnh, Queue trống có thể gây nhiều lần receive/poll hơn, tăng chi phí nền.

### 6.4. maxMessagesPerTask, TaskExecutor và virtual threads

`maxMessagesPerTask` đếm **số lần thử nhận**, kể cả lần timeout không có message, không đơn thuần là số message xử lý thành công. Với default TaskExecutor thông thường, giá trị mặc định có thể là **-1 (không giới hạn)** và một task tồn tại dài; với executor kiểu `SchedulingTaskExecutor` thích task ngắn, default có thể là **10 lần nhận** để task được reschedule thường xuyên.

Vì vậy điều chỉnh chỉ một biến idle có thể không đủ; cần nhìn cả bộ:
- `concurrentConsumers` / `maxConcurrentConsumers`.
- `receiveTimeout`.
- `idleConsumerLimit`.
- `idleTaskExecutionLimit`.
- `idleReceivesPerTaskLimit`.
- `maxMessagesPerTask`.
- `TaskExecutor` và khả năng cấp worker threads.

Nếu gắn một fixed thread pool có kích thước **nhỏ hơn max consumer**, dù max là 10, các invoker chưa chắc chạy đồng thời được. Với Java 21+ và Spring Framework 6.2, có thể cân nhắc virtual threads (`setVirtualThreads(true)` với default executor) để giảm chi phí khi các invoker chờ I/O; **virtual threads không làm broker hoặc database nhanh hơn** và ví dụ Java 17 ở đây không bật.

## 7. Ví dụ Spring Boot hoàn chỉnh: core 2, max 5

Ta tạo một application có **một Queue**, một `@JmsListener` và factory tạo `DefaultMessageListenerContainer`. Code gửi **12 message**; listener giả lập mỗi công việc mất khoảng 400 ms để có cơ hội nhìn thấy nhiều worker hoạt động.

**Điều kiện để chạy:**
- Java 17+, Maven.
- Apache ActiveMQ Artemis broker ngoài ứng dụng ở `tcp://localhost:61616` hoặc endpoint khác do bạn truyền.
- Tài khoản có quyền send/consume.
- Queue `demo.concurrent.queue` đã được provision với routing thích hợp hoặc broker cho auto-create.
- Queue demo ban đầu sạch và không có consumer khác nếu muốn kiểm tra đúng 12 callback.

Không có broker thì vẫn có thể build project, nhưng không kiểm chứng được concurrency thực tế.

### 7.1. Cấu trúc dự án

```text
jms-concurrency-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── example/
        │       └── jms/
        │           ├── ConcurrencyDemoApplication.java
        │           ├── JmsListenerConfig.java
        │           └── WorkMessageListener.java
        └── resources/
            └── application.properties
```

### 7.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.8</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>jms-concurrency-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-artemis</artifactId>
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
```

Starter Artemis mang Spring JMS và Jakarta-compatible Artemis client theo dependency management của Boot. Không ghép `javax.jms-api` đời cũ với Spring Framework 6.x (`jakarta.jms.*`).

### 7.3. application.properties

```properties
spring.artemis.mode=native
spring.artemis.broker-url=${JMS_BROKER_URL:tcp://localhost:61616}
spring.artemis.user=${JMS_USERNAME}
spring.artemis.password=${JMS_PASSWORD}

spring.jms.pub-sub-domain=false

# Demo không dùng thêm CachingConnectionFactory bên ngoài DMLC.
spring.jms.cache.enabled=false
```

**Lưu ý:** Application dùng một `DefaultJmsListenerContainerFactory` **tự khai báo**, nên min/max concurrency nằm trong JavaConfig bên dưới. Không đặt `spring.jms.listener.min-concurrency` / `max-concurrency` trong cùng demo rồi kỳ vọng chúng tự override factory thủ công.

`spring.jms.cache.enabled=false` giúp listener container có thể tự quản lý caching/refresh/recovery của connection/session/consumer mà không trộn thêm cache wrapper bên ngoài trong demo. Khi vận hành thực, bạn có thể dùng factory/pool cho producer riêng và chọn level cache phù hợp listener; không có một lựa chọn luôn tối ưu cho mọi provider.

### 7.4. Cấu hình listener container factory

**`src/main/java/example/jms/JmsListenerConfig.java`**

```java
package example.jms;

import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration(proxyBeanMethods = false)
@EnableJms
public class JmsListenerConfig {

    @Bean(name = "jmsListenerContainerFactory")
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(false);
        factory.setConcurrency("2-5");
        factory.setSessionTransacted(true);
        factory.setReceiveTimeout(1_000L);
        return factory;
    }
}
```

`factory.setConcurrency("2-5")` là cách ngắn gọn tương đương **`concurrentConsumers=2` và `maxConcurrentConsumers=5`** cho DMLC do factory sinh ra. Code không cần tự `new DefaultMessageListenerContainer` hoặc `start()`; Spring container lifecycle thực hiện.

`setSessionTransacted(true)` đặt **local JMS transaction** cho mỗi callback: thành công thì container commit, exception thoát khỏi listener thì rollback, broker có thể redeliver theo policy. Giao dịch này không tự bao trùm SQL hoặc HTTP.

`setReceiveTimeout(1_000L)` minh họa timeout 1 giây của lần thử `MessageConsumer.receive` trong DMLC, **không phải deadline xử lý business message** và không quyết định một message phải hoàn tất trong 1 giây. Việc đổi timeout ảnh hưởng idle/scaling và vòng poll.

### 7.5. Listener xử lý công việc giả lập

**`src/main/java/example/jms/WorkMessageListener.java`**

```java
package example.jms;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class WorkMessageListener {

    private final CountDownLatch callbacks = new CountDownLatch(12);
    private final AtomicInteger processedCallbacks = new AtomicInteger();

    @JmsListener(
            id = "workListener",
            destination = "demo.concurrent.queue",
            containerFactory = "jmsListenerContainerFactory")
    public void handle(String body) throws InterruptedException {

        String worker = Thread.currentThread().getName();
        System.out.println("received=" + body + " worker=" + worker);

        // Giả lập logic mất 400ms, không làm CPU-heavy.
        Thread.sleep(400L);

        processedCallbacks.incrementAndGet();
        callbacks.countDown();
    }

    public boolean awaitAll(long timeout, TimeUnit unit)
            throws InterruptedException {
        return callbacks.await(timeout, unit);
    }

    public int callbackCount() {
        return processedCallbacks.get();
    }
}
```

Ở đây `@JmsListener` dùng message converter mặc định để nhận body `TextMessage` dạng `String`. Vì có nhiều consumer, **cùng một Spring bean `WorkMessageListener` có thể được gọi song song trên nhiều thread**. Do đó counter dùng `AtomicInteger`, latch dùng `CountDownLatch`.

**Không lấy thứ tự dòng log làm thứ tự xử lý.** Message `task-7` có thể hoàn tất trước `task-6` vì các worker khác nhau. `Thread.sleep(400)` chỉ giả lập công việc; production phải đo latency của xử lý DB/HTTP thật và có timeout, retry phù hợp.

**Chú ý transaction:** counter/latch được cập nhật **trước khi DMLC commit JMS transaction** (commit xảy ra sau khi method trả về). Vì vậy đếm 12 callback không tự chứng minh 12 JMS commit chắc chắn. Counter RAM cũng không được rollback khi JMS transaction rollback; production cần metric và state bền vững.

### 7.6. Main + theo dõi concurrency qua endpoint registry

**`src/main/java/example/jms/ConcurrencyDemoApplication.java`**

```java
package example.jms;

import java.util.concurrent.TimeUnit;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.listener.DefaultMessageListenerContainer;
import org.springframework.jms.listener.MessageListenerContainer;

@SpringBootApplication
public class ConcurrencyDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConcurrencyDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner runDemo(
            JmsTemplate jmsTemplate,
            WorkMessageListener listener,
            JmsListenerEndpointRegistry registry) {

        return args -> {
            MessageListenerContainer base =
                    registry.getListenerContainer("workListener");

            if (!(base instanceof DefaultMessageListenerContainer dmlc)) {
                throw new IllegalStateException(
                        "Expected DefaultMessageListenerContainer");
            }

            System.out.printf(
                    "configuredCore=%d configuredMax=%d%n",
                    dmlc.getConcurrentConsumers(),
                    dmlc.getMaxConcurrentConsumers());

            for (int index = 1; index <= 12; index++) {
                jmsTemplate.convertAndSend(
                        "demo.concurrent.queue", "task-" + index);
            }

            boolean allCallbacks =
                    listener.awaitAll(30, TimeUnit.SECONDS);

            System.out.println("callbacksObserved=" + allCallbacks);
            System.out.println("callbackCount=" + listener.callbackCount());

            // Một snapshot, không hứa lúc nào cũng bằng max.
            System.out.printf(
                    "scheduledSnapshot=%d activeSnapshot=%d%n",
                    dmlc.getScheduledConsumerCount(),
                    dmlc.getActiveConsumerCount());

            if (!allCallbacks) {
                throw new IllegalStateException(
                        "Not all callbacks ran within 30 seconds");
            }
        };
    }
}
```

**Đây là một Java Spring Boot project chạy được về mặt code khi các dependency và broker phù hợp.** Tên package nhất quán `example.jms`, `@SpringBootApplication` quét listener và configuration. `@EnableJms` trong `JmsListenerConfig` bật annotation infrastructure, registry quản lý container được tạo từ factory.

Hai getter đầu là **giá trị cấu hình**; hai getter `getScheduledConsumerCount()` và `getActiveConsumerCount()` là **snapshot động**. Nếu snapshot được in sau khi 12 callback đã chạy, DMLC có thể đang giữ vài consumer dư hoặc bắt đầu scale down; không có một cặp số snapshot cố định để hardcode trong test.

### 7.7. Chạy project

PowerShell:

```powershell
$env:JMS_BROKER_URL = "tcp://localhost:61616"
$env:JMS_USERNAME = "dev-user"
$env:JMS_PASSWORD = "dev-password"
mvn spring-boot:run
```

Shell POSIX:

```bash
JMS_BROKER_URL=tcp://localhost:61616 \
JMS_USERNAME=dev-user \
JMS_PASSWORD=dev-password \
mvn spring-boot:run
```

Đổi `dev-user`/`dev-password` sang tài khoản Artemis thật. Nếu Queue không tồn tại và auto-create bị tắt, hãy provision `demo.concurrent.queue` trên broker. Nếu broker chưa chạy hoặc quyền không đủ, ứng dụng có thể build nhưng gửi/nhận sẽ thất bại.

Build không kết nối broker:

```bash
mvn -q -DskipTests package
```

**Output minh họa (trích các dòng ứng dụng in, không bao gồm Spring/Artemis log):**

```text
configuredCore=2 configuredMax=5
received=task-1 worker=...
received=task-2 worker=...
received=task-3 worker=...
... (các task khác, thứ tự thread không cố định)
callbacksObserved=true
callbackCount=12
scheduledSnapshot=... activeSnapshot=...
```

`...` ở đây là **ký hiệu output thay đổi theo thời điểm chạy**, không phải chuỗi mà code bắt buộc in ra. Nếu cần test chính xác, chỉ assert phần cấu hình `configuredCore=2 configuredMax=5`, và trong môi trường Queue cô lập, số callback thành công đúng 12. Không assert số thread được cấp bằng 5 hoặc log luôn theo thứ tự 1..12.

Trong ví dụ, ứng dụng vẫn chạy vì listener container còn hoạt động sau `ApplicationRunner`. Dừng bằng Ctrl+C. Muốn quan sát autoscale rõ hơn, gửi một số lượng message lớn hơn và theo dõi snapshot trong lúc listener đang chạy (qua metrics/JMX hoặc endpoint vận hành), thay vì chỉ in một lần cuối.

## 8. Cấu hình trực tiếp DefaultMessageListenerContainer bằng @Bean

Nếu bạn không dùng `@JmsListener` mà có một bean `MessageListener` thuần, có thể cấu hình **trực tiếp** container:

```java
@Bean
DefaultMessageListenerContainer directContainer(
        ConnectionFactory connectionFactory,
        MessageListener listener) {

    var container = new DefaultMessageListenerContainer();
    container.setConnectionFactory(connectionFactory);
    container.setDestinationName("jobs.queue");
    container.setMessageListener(listener);
    container.setPubSubDomain(false);
    container.setConcurrentConsumers(2);
    container.setMaxConcurrentConsumers(5);
    container.setSessionTransacted(true);
    return container;
}
```

**Đây là snippet thay thế** cho annotation container, không phải một phần bắt buộc thêm vào full project. Cần import `jakarta.jms.ConnectionFactory`, `jakarta.jms.MessageListener`, `org.springframework.jms.listener.DefaultMessageListenerContainer`, `org.springframework.context.annotation.Bean`. Nếu thêm cùng Queue với listener annotation ở mục 7, bạn tạo **hai nhóm competing consumers** thay vì thay đổi nhóm cũ.

Các giá trị min/max là **của đúng bean container** đó. Nếu bạn khai báo ba bean DMLC, mỗi bean có trần năm, tổng số consumer tiềm năng có thể lên đến 15 trong cùng JVM (tùy broker/TaskExecutor), không phải năm chia sẻ toàn ứng dụng.

Đừng chủ động gọi `container.start()` trong method `@Bean` chỉ để “chắc chắn đang nhận”: hãy để Spring lifecycle gọi. Tương tự, khi bean dừng, Spring sẽ xử lý shutdown phù hợp.

## 9. Queue, Topic và sự thật về thứ tự message

### 9.1. Queue có competing consumers

Với Queue `orders.queue`, ba consumer có thể nhận các message khác nhau:

```text
Queue: [M1] [M2] [M3] [M4] [M5] ...
             |     |     |
          Consumer A  B    C
          xử lý 500ms 100ms 300ms
```

Do thời gian xử lý khác nhau, **B có thể hoàn tất message sau của A trước A**, dù broker phân phối theo một thứ tự hợp lý. Khi concurrency tăng:
- Throughput thường tăng nếu callback bị chặn I/O và backend còn dư năng lực.
- Thứ tự **xử lý hoàn tất** không được bảo đảm giống thứ tự gửi.
- Các message cùng business key có thể được xử lý song song nếu không có grouping.
- Rollback, redelivery, priority, expiration và broker prefetch có thể làm phân phối thực tế khó suy từ thứ tự producer gửi.

Nếu yêu cầu business là **cập nhật trạng thái một đơn hàng theo thứ tự**, cần quyết định partition/message group theo `orderId`, tuần tự hóa theo key hoặc giữ một consumer cho luồng bắt buộc FIFO. Artemis có khả năng message grouping theo provider; nên xem đúng tài liệu Artemis và kiểm tra cluster/routing của bạn trước khi dựa vào grouping.

### 9.2. Topic có thể xử lý trùng publication

Đối với Topic JMS thông thường, mỗi subscription có thể nhận một bản message. Nếu đặt nhiều consumer không chia sẻ subscription một cách đúng đắn, bạn có thể nhận **cùng publication nhiều lần** trong một node. Spring DMLC Javadoc cảnh báo **không tăng concurrent consumers cho Topic** trừ khi có cấu hình vendor/shared-subscription phù hợp.

Vì vậy:
- **Queue:** có thể dùng `concurrentConsumers > 1` để xử lý công việc theo competing-consumer pattern.
- **Topic non-shared:** thông thường giữ `1` consumer trên một subscription.
- **Topic shared/durable:** cần thiết kế subscription name/client ID/shared semantics đúng Jakarta Messaging/provider rồi mới cân nhắc concurrency.

Không lấy giá trị `"2-5"` đã phù hợp Queue rồi copy sang Topic production một cách máy móc.

### 9.3. Concurrency không thể thay thế idempotency

Giả sử DB commit xong nhưng transaction nhận JMS rollback do lỗi mạng. Broker có thể redeliver cùng business event. Một consumer khác trong nhóm có thể nhận lại event ấy. Nếu handler không idempotent, việc tăng concurrency làm tác dụng phụ trùng càng khó phát hiện.

Hãy dùng business `eventId`/inbox/dedup logic với unique constraint và kiểm soát transaction DB. `JMSMessageID` hữu ích cho tracing nhưng không luôn là khóa business tốt nhất khi publisher có thể gửi lại cùng event qua message mới.

## 10. Transaction, acknowledge và tác động của concurrency

### 10.1. Local JMS transaction trong container

`factory.setSessionTransacted(true)` làm mỗi listener execution trong DMLC dùng một JMS local transaction. Khi callback kết thúc bình thường, container commit việc nhận. Khi callback ném exception tới container, nó rollback, và broker có thể redeliver theo policy.

Với concurrency 2..5, **mỗi consumer/session** có transaction riêng; không có một “global transaction” bao tất cả message đang được các consumer xử lý đồng thời. Nếu message A thành công, transaction của A có thể commit dù message B của consumer khác thất bại.

### 10.2. AUTO_ACKNOWLEDGE có rủi ro khi callback lỗi

Spring DMLC Javadoc lưu ý trong `AUTO_ACKNOWLEDGE`, acknowledgement có thể diễn ra **trước** khi listener chạy. Nếu callback sau đó ném exception, bạn không nhất thiết nhận được redelivery đáng tin cậy. Với Queue công việc quan trọng, `sessionTransacted=true` thường là lựa chọn phù hợp hơn (cần kiểm tra broker policy, DLQ và business semantics).

### 10.3. Một Spring JMS transaction không atomic với database

`sessionTransacted=true` chỉ là **local JMS transaction**. Nó không tự đưa câu lệnh SQL vào cùng một atomic commit. Dưới load cao, nhiều consumer có thể cùng ghi database:
- Tăng `maxConcurrentConsumers` có thể tạo áp lực lên JDBC connection pool.
- Lock contention và deadlock DB có thể tăng.
- Retry/redelivery có thể phát sinh nhiều lần gọi DB cho cùng event.
- Nếu transaction DB commit nhưng JMS commit lỗi, duplicate vẫn có thể xuất hiện.

Với hệ thống có DB, cần idempotent consumer/inbox, connection pool capacity, lock policy và transaction boundaries rõ ràng. Nếu cần giao dịch phân tán, xem xét JTA/XA thật sự hoặc thiết kế outbox/inbox thay vì mặc định thêm `@Transactional`.

### 10.4. Ngưỡng retry và dead-letter queue

Khi một message thất bại và bị rollback liên tục:
- Broker có thể redeliver theo delay/backoff.
- Khi vượt `max-delivery-attempts` hoặc policy tương đương, nó có thể chuyển sang DLQ.
- Một poison message được retry nhanh có thể giữ bận consumer, làm throughput thực giảm dù max cao.

Đặt số lần redelivery, delay, DLQ và alert theo nghiệp vụ; không đơn giản tăng concurrency để che lỗi poison message.

## 11. Quan sát cấu hình và thực tế bằng getter

DMLC có các phương thức:

```java
int core = container.getConcurrentConsumers();
int max = container.getMaxConcurrentConsumers();

int scheduled = container.getScheduledConsumerCount();
int active = container.getActiveConsumerCount();

boolean running = container.isRunning();
```

Đây là **snippet** khi `container` là `DefaultMessageListenerContainer` và đã được cấu hình/khởi động thích hợp.

Phân biệt bốn số:

| Getter | Trả về | Dùng để |
| --- | --- | --- |
| `getConcurrentConsumers()` | Số consumer lõi cấu hình | Xác nhận min/core đã được áp dụng. |
| `getMaxConcurrentConsumers()` | Trần consumer cấu hình | Xác nhận upper limit của container. |
| `getScheduledConsumerCount()` | Consumer invokers đang được lên lịch | Quan sát mức mở rộng thực ở một thời điểm. |
| `getActiveConsumerCount()` | Consumer invokers đang active | Phát hiện chênh giữa scheduled và thực thi (ví dụ executor thiếu thread). |

Nếu `scheduled=5`, `active=3`, không nhất thiết hai consumer đã chết: có thể chúng **được lên lịch nhưng chưa chạy** hoặc đang trong trạng thái chuyển đổi. Cần đối chiếu logs, executor, broker consumer count và sampling qua thời gian.

**Đừng coi `active` là “số message đang xử lý”**. Một invoker có thể active nhưng đang đợi `receive` hết timeout khi Queue trống. Muốn đo số business callbacks đang chạy, tạo gauge riêng: tăng khi vào listener và giảm trong `finally`; cùng lúc đo processing latency và callback exception.

### 11.1. Lấy container từ @JmsListener endpoint registry

`@JmsListener(id = "workListener", ...)` cho phép tra cứu:

```java
MessageListenerContainer base =
        registry.getListenerContainer("workListener");

if (base instanceof DefaultMessageListenerContainer dmlc) {
    System.out.printf(
            "core=%d max=%d scheduled=%d active=%d%n",
            dmlc.getConcurrentConsumers(),
            dmlc.getMaxConcurrentConsumers(),
            dmlc.getScheduledConsumerCount(),
            dmlc.getActiveConsumerCount());
}
```

Đây là snippet bên trong Spring bean có `JmsListenerEndpointRegistry registry`. Endpoint container do registry quản lý không nhất thiết là một Spring bean có thể `@Autowired` trực tiếp theo cùng ID.

### 11.2. Theo dõi từ broker và hệ thống

Spring runtime metrics chỉ là một nửa. Theo dõi thêm:
- Queue messages ready/pending và in-flight/delivering.
- Consumer count thực trên broker, phân bố theo connection/node.
- Incoming/enqueue và outgoing/dequeue rate, độ trễ message chờ.
- Redelivery count, DLQ count, expired message count.
- CPU/memory của JVM, số task executor threads và GC.
- DB pool active/waiting, HTTP client pool, downstream latency/error rate.
- Business callback gauge, duration (p50/p95/p99), retry và idempotency hit rate.

Chính xác nhất là xem các thông số **cùng trục thời gian**. Max đạt 5 nhưng backlog không giảm có thể do DB bottleneck chứ không phải thiếu JMS consumer.

## 12. Một công thức định hướng trước khi tăng concurrency

Giả sử mỗi callback thực hiện một tác vụ độc lập có thời gian trung bình **200 ms**, và không có giới hạn CPU/DB/broker:

- Một consumer xử lý lý tưởng khoảng `1 / 0,2 = 5 message/giây`.
- Bốn consumer xử lý lý tưởng khoảng `4 / 0,2 = 20 message/giây`.
- Nhưng đây là **xấp xỉ trần lý tưởng**, không phải lời cam kết. Thực tế có network, polling, transaction commit, prefetch, locking và load skew.

Để chọn mức core/max, hãy đo:

```text
arrival rate             = messages vào mỗi giây
average processing time  = thời gian xử lý mỗi message (giây)
required concurrency     ≈ arrival rate x processing time
```

Ví dụ dòng vào trung bình 12 message/giây và mỗi message mất 0,25 giây: khoảng `12 × 0,25 = 3` callback song song mới đủ bắt kịp **trong lý tưởng**. Nên có thêm headroom cho p95/p99, burst và biến động downstream, nhưng cũng phải giới hạn theo DB connection pool và sức chịu đựng của hệ thống.

**Không lấy công thức lý tưởng để mặc định đặt max=100.** Nếu service DB chỉ chịu 10 query song song, max 100 có thể khiến queue/threading phức tạp hơn và giảm throughput vì contention.

### 12.1. Tuning theo workload

| Workload | Cách bắt đầu | Vì sao |
| --- | --- | --- |
| Queue rất ít message, cần FIFO business | `1-1` | Đơn giản, ít resource, giảm nguy cơ chạy song song. |
| Queue đều đặn, xử lý độc lập | `2-4` | Có core đủ tải thường, max cho burst. |
| Queue thỉnh thoảng có burst lớn | `1-6` | Idle resource thấp; scale up từ từ khi cần. |
| Consumer chủ yếu chờ HTTP/DB và downstream còn dư | Core/max cao hơn sau khi đo | I/O wait có thể che giấu bằng concurrency. |
| Consumer CPU-heavy | Giới hạn theo CPU cores/thực nghiệm | Quá nhiều threads gây context switching/GC. |
| Topic subscription không chia sẻ | Thường `1-1` | Tránh nhận trùng publication. |

Bảng là **điểm khởi đầu để benchmark**, không phải công thức cố định; cần kiểm chứng p95 latency, broker throughput, DB load và retry policy.

## 13. Prefetch, broker và cạnh tranh giữa consumer

Có trường hợp đã đặt core 2/max 5, broker có hàng nghìn message, nhưng CPU chỉ bận ở một vài consumer. Nguyên nhân có thể là provider **prefetch** một lượng message lớn vào từng consumer khiến phân phối không đều.

Ví dụ minh họa:

```text
Broker Queue có 100 message
     |
     +-- Consumer A prefetch nhiều message, đang xử lý tuần tự
     +-- Consumer B nhận ít message
     +-- Consumer C mới được tạo, chưa có message
```

Lúc này tăng max không chắc giảm độ trễ. Cần:
- Xem Artemis consumer window/flow control và routing settings; đừng dùng tên property của ActiveMQ Classic như thể Artemis giống hệt.
- Kiểm tra số message broker báo **in delivery** so với **ready**.
- Đo tốc độ xử lý của từng consumer, uneven partitions và poison messages.
- Điều chỉnh prefetch/window size một cách có kiểm chứng, tránh thay ngẫu nhiên.
- Kiểm tra quyền send/consume, queue binding, selector và bất kỳ filter nào.

**Đừng suy từ Queue depth một mình:** 100 message ready khác với 100 message đã dispatch đến một consumer nhưng chưa commit.

### 13.1. Nhiều replica nhân tổng số consumer

Nếu mỗi instance có `concurrentConsumers=2`, `maxConcurrentConsumers=5` và bạn chạy **4 replicas**, sức chứa cấu hình lý thuyết có thể là:

```text
Per replica: 2 ... 5 consumers
4 replicas : 8 ... 20 consumers (tổng cấu hình)
```

Đây là lý do phải phối hợp JMS concurrency với **horizontal pod autoscaling**. Nếu mỗi replica tăng max khi backlog tăng, rồi autoscaler tăng số replica, tổng consumer có thể vượt khả năng chịu tải của database/broker. Theo dõi tổng consumer count và downstream budgets.

## 14. Những lỗi phổ biến và hướng chẩn đoán

| Triệu chứng / hiểu nhầm | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Đặt `maxConcurrentConsumers=5` nhưng luôn thấy 1 | Core mặc định 1, tải chưa đủ, còn invoker idle, executor thiếu thread hoặc broker prefetch lệch | Tạo tải đủ dài, đo scheduled/active và broker; kiểm tra TaskExecutor/idle settings. |
| Đặt `setConcurrency("5")` mà muốn cố định 5 | Với DMLC, `"5"` là min 1/max 5 | Dùng `"5-5"` hoặc set cả hai setter bằng 5. |
| Tăng `concurrentConsumers` mà thứ tự xử lý thay đổi | Nhiều consumer chạy callback song song | Giữ 1 nếu cần FIFO, hoặc thiết kế grouping/partition theo business key. |
| Tăng max khiến message bị xử lý trùng trên Topic | Topic non-shared có nhiều subscription độc lập | Giữ concurrency 1 hoặc cấu hình shared subscription đúng. |
| Backlog cao nhưng `active < scheduled` | Executor thiếu worker threads, task chưa chạy hoặc trạng thái chuyển tiếp | Kiểm tra thread pool, blocking tasks, container lifecycle. |
| `active=5` nhưng throughput thấp | Active không có nghĩa đang làm business work; DB/HTTP chậm, broker không giao đủ message | Đo actual in-flight callbacks, database pool, queue ready/delivering, errors. |
| Trên Boot đã set min/max nhưng getter vẫn 1/1 | Factory tự tạo bỏ qua Boot properties hoặc endpoint override | Kiểm tra bean factory, `@JmsListener(concurrency)` và Boot configurer. |
| Consumer tăng/giảm liên tục | Idle thresholds/receiveTimeout không phù hợp tải burst | Tuning `idleTaskExecutionLimit`, `idleReceivesPerTaskLimit`, `idleConsumerLimit`, receive timeout. |
| Rất nhiều thread chờ `receive` khi Queue rỗng | Core đặt quá cao, executor giữ thread lâu | Hạ core, cân nhắc cấu hình scale linh hoạt. |
| DMLC không nhận sau broker restart | Connection factory cache/recovery/credentials hoặc broker unavailable | Kiểm tra recovery/backoff, cache level, broker health và permissions. |
| Callback ném exception nhưng message không retry | AUTO_ACKNOWLEDGE hoặc exception bị catch rồi bỏ qua | Dùng transacted session đúng và propagate failure; kiểm tra redelivery/DLQ. |
| DB liên tục timeout khi tăng max | JDBC pool/locks/HTTP connection pool bị quá tải | Giới hạn max theo downstream và dùng backpressure. |
| Cấu hình 5 mỗi pod nhưng cluster có 30 consumer | Có 6 replicas hoặc nhiều containers | Tổng hợp theo instance và endpoint, đặt giới hạn cluster. |
| `maxConcurrentConsumers < concurrentConsumers` | Config không nhất quán; implementation có thể clamp max lên | Validate `1 <= core <= max` rõ ở startup. |
| Dùng `@Async` để tăng listener concurrency | Nhầm callback executor của business với JMS consumer | Tuning DMLC consumers; `@Async` không thay thế transaction/ack semantics. |
| Bảo rằng `receiveTimeout=1s` nên callback tối đa 1s | Timeout chỉ áp dụng cho lời gọi đợi message | Đo business processing latency và áp timeout riêng cho I/O downstream. |

## 15. Kiểm thử concurrency và scaling

### 15.1. Kiểm thử giá trị cấu hình

Không cần broker để unit test việc thiết lập hai setter của DMLC:

```java
DefaultMessageListenerContainer container =
        new DefaultMessageListenerContainer();
container.setConcurrency("2-5");

assertEquals(2, container.getConcurrentConsumers());
assertEquals(5, container.getMaxConcurrentConsumers());
```

Đây là **snippet trong JUnit test** có Spring JMS trên classpath và import `assertEquals`, không phải class test độc lập. Nó xác minh parsing/config, **không** kiểm chứng DMLC đã mở năm consumer với broker.

### 15.2. Test bình thường khi Queue trống

- Khởi động Spring context với core 2/max 5.
- Tách riêng Queue test, chắc rằng chưa có producer.
- Quan sát scheduled/active ổn định gần core khi container đã start; phụ thuộc executor/connection health.
- Xác minh không có busy polling/connection leak; snapshot thay đổi ngắn hạn có thể xảy ra.
- Không assert cứng “sau 100 ms phải đúng 2 active” vì startup/recovery phụ thuộc broker.

### 15.3. Test khi backlog tăng

- Gửi đủ nhiều message có ID riêng, mỗi callback xử lý mất thời gian đo được.
- Theo dõi active/scheduled count theo chu kỳ, cùng Queue ready/delivering.
- Đảm bảo max không bị vượt trong điều kiện bình thường.
- Kiểm tra giảm backlog và throughput thực; không chỉ đếm số lần logger in tên thread.
- Nếu không scale up, kiểm tra một consumer idle, provider prefetch, executor capacity, selector, lock và callback timing.

### 15.4. Test scale down

- Dừng producer sau giai đoạn tải lớn.
- Chờ callback và commit hoàn tất; đo thời gian invoker dư được thu hồi.
- Đối chiếu `receiveTimeout`, idle receives/task execution, tránh khẳng định thu hồi ngay.
- Kiểm tra core consumers tiếp tục hoạt động sẵn sàng sau khi queue về trạng thái idle.
- Chạy lại một burst mới để xem chi phí startup consumer có gây latency bất thường hay không.

### 15.5. Test lỗi khi concurrency lớn

- Cho listener ném exception ở một event đã chọn; session transacted phải rollback, broker redeliver theo policy.
- Kiểm tra side effects được dedup nếu event xuất hiện ở consumer khác sau rollback.
- Giảm broker availability hoặc revoke quyền, quan sát recovery thay vì crash âm thầm.
- Giữ concurrency 2..5 và đo connection/session/consumer resources khi recover.
- Kiểm tra rolling deploy hai replicas không tạo quá nhiều in-flight work.

### 15.6. Performance benchmark

Thiết lập tải từng mức `1-1`, `2-4`, `2-8`, `4-8` với **cùng message size**, **cùng broker**, **cùng downstream**. Ghi nhận:
- Enqueue/dequeue rate, backlog, end-to-end completion latency.
- Processing p95/p99, transaction rollback, retry/DLQ.
- CPU/memory/threads và DB/HTTP pool saturation.
- Consumer count active/scheduled trên từng replica.
- Thời gian scale up/scale down và thông lượng sau đợt burst.

Chỉ chọn cấu hình cao hơn khi **mức cải thiện đủ bù chi phí và rủi ro**. Nếu throughput không cải thiện mà DB errors tăng, max lớn hơn không giúp.

## 16. Câu hỏi tự kiểm tra

**1.** `concurrentConsumers=2`, `maxConcurrentConsumers=5` có tạo ngay 5 consumer khi startup không?

Không. Core mục tiêu là 2; DMLC **có thể** mở thêm tới 5 tùy tải và điều kiện scheduling.

**2.** `setConcurrency("5")` có nghĩa đúng 5 consumer cố định không?

Không. Với DMLC Spring 6.x, đó là **core 1, max 5**. Muốn cố định 5, dùng `"5-5"`.

**3.** `getMaxConcurrentConsumers()=8` nhưng `getActiveConsumerCount()=3` có chứng minh cấu hình lỗi không?

Không. Max là trần cấu hình, active là snapshot phụ thuộc tải, executor, Queue và lifecycle.

**4.** Vì sao không tăng consumer cho Topic như Queue?

Với Topic non-shared, nhiều subscriptions có thể nhận cùng publication, tạo xử lý lặp. Chỉ tăng sau khi thiết kế shared subscription/vendor semantics rõ ràng.

**5.** Có bảo đảm message `M1` sẽ hoàn tất trước `M2` khi concurrency=4 không?

Không. Nhiều session/consumer xử lý độc lập nên thứ tự hoàn tất có thể khác thứ tự gửi; cần grouping/ordering policy nếu nghiệp vụ yêu cầu.

**6.** `receiveTimeout=1_000` có làm callback luôn xong dưới 1 giây không?

Không. Nó chỉ giới hạn thời gian chờ trong một lần `receive` của DMLC, không phải timeout business logic.

**7.** Nếu dùng 4 pod, mỗi pod max 5, tổng trần lý thuyết là bao nhiêu consumer?

Khoảng **20 consumer cho endpoint đó** nếu tất cả pod đều scale tối đa và không có khác biệt cấu hình, chưa kể listener containers khác.

**8.** Vì sao listener transacted vẫn cần idempotency?

Vì DB/HTTP có thể thành công nhưng JMS commit lỗi, message được redeliver; hoặc publisher phát lại event dưới một JMSMessageID khác.

**9.** Spring Boot properties min/max có luôn áp vào bean `DefaultJmsListenerContainerFactory` tự tạo không?

Không. Khi tự tạo factory, phải cấu hình thủ công hoặc dùng Boot `DefaultJmsListenerContainerFactoryConfigurer`.

**10.** Nếu throughput giảm sau khi tăng max từ 5 lên 20, nên làm gì?

Đo DB/HTTP pool, broker prefetch, CPU, rollback/DLQ và context switching; hạ max hoặc cải thiện bottleneck thay vì tiếp tục tăng.

## 17. Checklist production

- Xác nhận loại destination: Queue competing consumers hay Topic subscription; **không copy concurrency của Queue sang Topic**.
- Xác định số core để xử lý tải thường và max để xử lý burst, không lấy max làm số consumer “luôn có”.
- Với DMLC, nhớ `"5"` nghĩa **1..5**, còn `"5-5"` nghĩa cố định năm.
- Kiểm tra factory/annotation/Boot properties để biết **nguồn cấu hình cuối cùng** đã áp vào endpoint.
- Giữ bean listener thread-safe; tránh counter/caches mutable không đồng bộ.
- Không dựa vào ordering toàn cục khi có nhiều consumer; thiết kế grouping/partition nếu cần.
- Dùng local JMS transaction và propagate exception đúng, cấu hình retry/DLQ và xử lý poison message.
- Đảm bảo business handler idempotent khi thao tác DB/HTTP.
- Giới hạn tổng consumer theo số replicas và số listener containers, tránh vượt tài nguyên broker/downstream.
- Theo dõi `getScheduledConsumerCount`, `getActiveConsumerCount`, broker metrics, callback in-flight và thread/DB pool.
- Tuning idle settings cùng `receiveTimeout` và `TaskExecutor` sau khi đã có dữ liệu đo.
- Kiểm thử khi queue rỗng, burst, scale down, retry, broker restart, rolling deployment.
- Không tự thay đổi concurrency liên tục trong mỗi request; thay đổi runtime bằng quy trình vận hành có audit, canary và quan sát hiệu năng.

## Kết luận

Trong Spring JMS **`DefaultMessageListenerContainer`**, **`concurrentConsumers` xác định số consumer lõi**, còn **`maxConcurrentConsumers` giới hạn số consumer mà container có thể mở thêm khi tải tăng**. Mặc định cả hai là **1**, nên không có dynamic scaling. Cấu hình `setConcurrency("2-5")` cho phép giữ tối thiểu khoảng hai consumer và mở rộng tới năm; `setConcurrency("5")` tương ứng min 1/max 5, **không phải cố định năm**.

Con số cấu hình khác số consumer chạy thực tế. Hãy kiểm tra `getScheduledConsumerCount()`, `getActiveConsumerCount()` và metrics broker/downstream trước khi điều chỉnh. Tăng concurrency hữu ích cho Queue có công việc độc lập, nhưng có thể phá thứ tự hoàn tất, tăng tải DB, tạo redelivery và lãng phí tài nguyên; với Topic thông thường, tránh mở nhiều consumer nếu chưa có shared-subscription semantics đúng. Một cấu hình production tốt phải kết hợp **transaction, idempotency, giới hạn tài nguyên và benchmark**, chứ không chỉ nâng trần lên thật cao.

## Tài liệu tham khảo

- Spring Framework 6.2 — `DefaultMessageListenerContainer` Javadoc, `setConcurrentConsumers`, `setMaxConcurrentConsumers`, `setConcurrency`, scaling/idle settings, getters: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html
- Spring Framework 6.2 — `DefaultJmsListenerContainerFactory` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html
- Spring Framework 6.2 — Annotation-driven JMS endpoints, `@JmsListener`, factory concurrency: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html
- Spring Framework 6.2 — Using Spring JMS / listener containers: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html
- Spring Framework 6.2 — Receiving a Message / listener transactions: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html
- Spring Boot 3.5 — JMS/Artemis messaging: https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html
- Spring Boot 3.5 — Application properties `spring.jms.listener.min-concurrency` và `max-concurrency`: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/
- Spring Boot 3.5 — JMS How-to / DefaultJmsListenerContainerFactoryConfigurer: https://docs.spring.io/spring-boot/3.5/how-to/messaging.html
- Jakarta Messaging 3.1 — specification, consumer/session transaction và Queue/Topic: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Apache ActiveMQ Artemis — Using JMS, queue routing/grouping: https://artemis.apache.org/components/artemis/documentation/latest/using-jms