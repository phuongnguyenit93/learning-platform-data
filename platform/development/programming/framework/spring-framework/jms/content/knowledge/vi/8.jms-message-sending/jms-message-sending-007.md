# Gửi nhiều thao tác qua SessionCallback trong Spring JMS

## 1. Mục tiêu và tình huống sử dụng

Trong nhiều ứng dụng, một yêu cầu nghiệp vụ không chỉ phát một JMS message. Ví dụ khi đơn hàng được tiếp nhận, service cần gửi **message nghiệp vụ** đến Queue xử lý đơn và **message audit** đến Queue theo dõi. Nếu mỗi thao tác viết bằng một lệnh `jmsTemplate.convertAndSend(...)` riêng, cách viết đơn giản nhưng bạn chưa thể hiện rõ rằng chúng phải dùng **cùng một JMS `Session`** hoặc phải **commit/rollback cùng nhau**.

Spring JMS cung cấp `org.springframework.jms.core.SessionCallback<T>`. Khi gọi `JmsTemplate.execute(SessionCallback<T>)`, Spring cho callback mượn một `jakarta.jms.Session` để thực hiện nhiều thao tác: tạo các `Message`, tạo `MessageProducer`, gửi đến một hoặc nhiều `Destination`, thiết lập header/property, rồi trả về kết quả.

Điểm cần nắm chắc:

> **Nhiều thao tác chung `Session` không đồng nghĩa với một giao dịch nguyên tử.** `SessionCallback` là API thao tác theo phạm vi session; để gửi “tất cả cùng thành công hoặc tất cả rollback”, phải thiết lập **JMS transaction boundary** thích hợp, ví dụ `JmsTransactionManager` kết hợp `TransactionTemplate` hoặc `@Transactional`.

Sau bài này, bạn sẽ:
- Hiểu chữ ký, vòng đời, ownership và cách dùng `SessionCallback<T>`.
- Gửi nhiều `TextMessage` trong một callback; gửi nhiều Queue hoặc cùng một Queue.
- Phân biệt việc tái sử dụng session với transaction/atomicity, JMS batching và hành vi thứ tự message.
- Xây dựng ví dụ Java 17+ / Spring Boot / Apache ActiveMQ Artemis có commit JMS rõ ràng.
- Biết khi nào ưu tiên `ProducerCallback`, `MessageCreator` hoặc nhiều lần `convertAndSend`; tránh lỗi tài nguyên và transaction.

Các ví dụ dùng **Jakarta Messaging** (`jakarta.jms.*`) và **Spring Framework 6.x** (qua Spring Boot 3.5.x). Dự án Spring cũ dùng `javax.jms` cần bộ dependency tương thích riêng; không trộn hai namespace.

## 2. SessionCallback là gì?

`SessionCallback<T>` là functional interface trong package `org.springframework.jms.core`. Về bản chất, nó có một phương thức:

```java
@FunctionalInterface
public interface SessionCallback<T> {
    T doInJms(jakarta.jms.Session session)
            throws jakarta.jms.JMSException;
}
```

Đây là **chữ ký minh họa**, không phải code bạn cần khai báo lại vì Spring đã cung cấp interface. `T` là loại kết quả callback trả về. Callback có thể trả một số nguyên, một đối tượng kết quả hoặc `null` nếu không cần giá trị.

Phía ứng dụng gọi:

```java
T result = jmsTemplate.execute(
        (SessionCallback<T>) session -> {
            // Thực hiện các JMS operation trong cùng session.
            return resultValue;
        });
```

Đoạn trên chỉ minh họa hình dạng callback (biến `jmsTemplate`, `resultValue` và kiểu `T` cần tồn tại trong ngữ cảnh sử dụng).

### JmsTemplate làm gì trước và sau callback?

```text
Service
   |
   +--> JmsTemplate.execute(SessionCallback)
              |
              +--> Tìm Session đã gắn với Spring transaction (nếu có)
              |    hoặc mở/lấy Connection + Session phù hợp
              |
              +--> gọi doInJms(session)
              |      |
              |      +--> createQueue / createTopic
              |      +--> createTextMessage / set properties
              |      +--> createProducer / send 1
              |      +--> send 2 / ... / send n
              |      +--> callback trả về T
              |
              +--> dọn/trả resource do template quản lý
              +--> dịch checked JMSException thành Spring JmsException
   |
   +--> sử dụng kết quả T
```

`JmsTemplate` điều phối acquisition/release của connection và session. Nếu đang có `JmsTransactionManager` quản lý transaction, nó sử dụng session ràng buộc với thread và **transaction manager** sẽ commit/rollback đúng thời điểm. Khi không có transaction, template quản lý vòng đời session như một thao tác độc lập.

**Quan trọng:** `execute(SessionCallback)` thông thường dành cho thao tác gửi nên **không cần `Connection.start()`**. Overload `execute(SessionCallback, boolean startConnection)` cho phép kích hoạt delivery nếu thực sự dùng session để nhận. Đối với nhận message thường xuyên, ưu tiên `@JmsListener`; nhận đồng bộ đơn giản có thể dùng `JmsTemplate.receive(...)`.

### Ai sở hữu resource?

| Đối tượng | Ai tạo/sở hữu? | Quy tắc trong callback |
| --- | --- | --- |
| `Connection` và `Session` được template cấp | Spring/template hoặc transaction manager | Không `close()` session; không giữ reference sau khi callback kết thúc. |
| `MessageProducer` do callback gọi `session.createProducer(...)` | Chính callback | Đóng bằng `try-with-resources`/`finally`. |
| `Message` do `session.createTextMessage(...)` | Tạo trong session | Dùng trong scope gửi; không phải tài nguyên cần `close`. |
| `Destination` do `session.createQueue(...)` | Đối tượng đại diện Queue/Topic do provider tạo | Thông thường không có `close`; Queue vật lý trên broker là chuyện khác. |
| Transaction được mở bằng `JmsTransactionManager` | Spring transaction manager | Không gọi `session.commit()`/`rollback()` thủ công trong callback đang tham gia transaction. |

`Session` không phải đối tượng chia sẻ an toàn cho nhiều thread tùy ý. **Không** thực hiện `parallelStream`, `CompletableFuture.runAsync` hay tách thread để dùng cùng một `Session` được truyền vào callback.

## 3. Ví dụ nhỏ nhất: gửi hai message trong một lần execute

Giả sử `JmsTemplate` đã được cấu hình với `ConnectionFactory` tới broker và Queue có tên `orders.queue`.

```java
import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.core.SessionCallback;

public final class TwoMessages {
    private final JmsTemplate template;

    public TwoMessages(JmsTemplate template) {
        this.template = template;
    }

    public int publish(String orderId) {
        Integer count = template.execute((SessionCallback<Integer>) session -> {
            Queue queue = session.createQueue("orders.queue");

            try (MessageProducer producer = session.createProducer(queue)) {
                var placed = session.createTextMessage("placed:" + orderId);
                placed.setStringProperty("orderId", orderId);
                producer.send(placed);

                var confirmed = session.createTextMessage("confirmed:" + orderId);
                confirmed.setStringProperty("orderId", orderId);
                producer.send(confirmed);
            }
            return 2;
        });

        return java.util.Objects.requireNonNull(count);
    }
}
```

Đây là **class dùng trong ứng dụng đã có `JmsTemplate` và JMS broker**, chưa phải chương trình có `main()`. Hai lệnh `producer.send(...)` nằm trong **cùng callback, cùng JMS Session, cùng producer và cùng Queue**. Kết quả `2` biểu thị **số lần gửi đã được callback thực hiện mà không ném exception**, không phải số lần consumer xử lý thành công.

Tại sao dùng `try-with-resources`? Vì callback **tự tạo** producer bằng `session.createProducer`, nên chính callback đóng nó. Đóng producer **không đóng session**; session thuộc lifecycle của `JmsTemplate`.

### Trường hợp đổi sang hai Queue

Trong một `SessionCallback`, bạn có thể tạo hai Destination từ cùng session rồi gửi mỗi message đến nơi phù hợp:

```java
Integer count = jmsTemplate.execute((SessionCallback<Integer>) session -> {
    Queue orders = session.createQueue("orders.queue");
    Queue audit = session.createQueue("audit.queue");

    try (var orderProducer = session.createProducer(orders);
         var auditProducer = session.createProducer(audit)) {

        orderProducer.send(session.createTextMessage("order-created"));
        auditProducer.send(session.createTextMessage("order-audited"));
    }
    return 2;
});
```

Đây là snippet trong service có bean `jmsTemplate` và import `SessionCallback`, `Queue`; không phải file Java độc lập. Nó minh họa rằng **một session có thể sử dụng nhiều producer và nhiều destination**.

**Không suy luận rằng hai send là atomic chỉ vì chúng chung session:** nếu session không transacted, lệnh thứ nhất có thể đã gửi thành công, rồi lệnh thứ hai thất bại. Khi cần một transaction JMS bao trọn cả hai, sử dụng cấu hình ở mục 5.

## 4. So sánh với cách gửi thông thường

```java
jmsTemplate.convertAndSend("orders.queue", "order-created");
jmsTemplate.convertAndSend("audit.queue", "order-audited");
```

Đây là hai invocation riêng biệt. Nếu không có Spring transaction bao ngoài, chúng có thể dùng các session/transaction logic riêng, và sự thành công của lần thứ nhất không phụ thuộc lần thứ hai. Gọn hơn callback, nhưng không thể truy cập trực tiếp một session xuyên qua cả hai lệnh chỉ bằng cách viết chúng liền nhau.

`SessionCallback` có ích khi:
1. Muốn thao tác **trực tiếp** bằng Jakarta Messaging API và lặp nhiều `send` trên cùng một session.
2. Muốn reuse một hoặc vài `MessageProducer` trong phạm vi ngắn, không tạo producer cho từng lần gửi.
3. Muốn tạo nhiều kiểu message/header/property khác nhau hoặc gửi đến nhiều Queue/Topic với cùng một session.
4. Muốn trả kết quả tổng hợp (số message đã chuẩn bị/gửi, ID đã tạo, thông tin điều khiển) từ callback.
5. Muốn kiểm soát chính xác ranh giới resource và kết hợp session đó với một **transaction JMS đang được quản lý**.

**Điều `SessionCallback` không tự làm:** nó không phải một API batch gửi message đặc biệt trên broker, không bảo đảm một network round-trip duy nhất, không giảm mọi overhead, và không tự tạo transaction. Gửi `n` message thường vẫn là `n` thao tác gửi JMS; broker/provider có thể tối ưu nội bộ theo cấu hình, nhưng muốn chứng minh hiệu năng phải đo.

## 5. Ví dụ Spring Boot hoàn chỉnh với một JMS transaction

Để gửi hai message cùng commit/rollback, ví dụ dùng:

- Java 17+.
- Spring Boot **3.5.8**, tương thích Spring Framework 6.x và Jakarta Messaging.
- Apache ActiveMQ Artemis client qua `spring-boot-starter-artemis`.
- `JmsTransactionManager` quản lý **local JMS transaction**.
- `TransactionTemplate` tạo transaction boundary bằng lập trình; cách này cho ví dụ đơn giản vì không phụ thuộc việc gọi qua proxy của `@Transactional`.
- `JmsTemplate.execute(SessionCallback<Integer>)` gửi lần lượt hai message trong cùng JMS session gắn với transaction.

**Điều kiện để chạy:** một Artemis broker bên ngoài đang lắng nghe `tcp://localhost:61616`, credentials hợp lệ và Queue `demo.orders`, `demo.audit` đã tồn tại hoặc broker cho phép auto-create theo chính sách. Maven chỉ khởi động ứng dụng client; nó **không** tự khởi động broker.

### 5.1. Cấu trúc dự án

```text
session-callback-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── example/
        │       └── jms/
        │           ├── SessionCallbackApplication.java
        │           ├── JmsTransactionConfiguration.java
        │           └── MultiSendService.java
        └── resources/
            └── application.properties
```

### 5.2. pom.xml

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
    <artifactId>session-callback-demo</artifactId>
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

`spring-boot-starter-artemis` mang Spring JMS và Jakarta-compatible Artemis client theo dependency management của Spring Boot. Không thêm thư viện JMS 1.x sử dụng `javax.jms` vào cùng ứng dụng; việc trộn namespace dễ gây lỗi compile hoặc `ClassCastException`.

### 5.3. application.properties

```properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=${JMS_USERNAME}
spring.artemis.password=${JMS_PASSWORD}

# Publisher đang dùng Queue, không phải Topic:
spring.jms.pub-sub-domain=false

# Giá trị minh họa: cache session có thể giảm chi phí khi tải cao.
spring.jms.cache.session-cache-size=5
```

Các biến `JMS_USERNAME` và `JMS_PASSWORD` phải được cung cấp từ môi trường trước khi chạy và phải khớp account của broker. Đừng commit mật khẩu thật vào source. Nếu broker dùng TLS, HA hoặc failover, hãy cấu hình URL/transport theo tài liệu Artemis thay vì mặc định copy URL nội bộ trên.

**Lưu ý:** cấu hình cache của Spring Boot không phải một connection pool tự động cho nhiều socket. `CachingConnectionFactory` có thể giữ connection/session ở tầng Spring; không gán nhầm “5 session cache” thành “5 JMS connection”.

### 5.4. Cấu hình JmsTransactionManager và TransactionTemplate

**`src/main/java/example/jms/JmsTransactionConfiguration.java`**

```java
package example.jms;

import jakarta.jms.ConnectionFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.connection.JmsTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@Configuration(proxyBeanMethods = false)
public class JmsTransactionConfiguration {

    @Bean(name = "jmsTransactionManager")
    JmsTransactionManager jmsTransactionManager(ConnectionFactory connectionFactory) {
        return new JmsTransactionManager(connectionFactory);
    }

    @Bean(name = "jmsBatchTransactionTemplate")
    TransactionTemplate jmsBatchTransactionTemplate(
            @Qualifier("jmsTransactionManager") JmsTransactionManager manager) {
        return new TransactionTemplate(manager);
    }
}
```

`JmsTransactionManager` quản lý một `ConnectionFactory`. Trong ví dụ có một factory Spring Boot auto-configure; template gửi và transaction manager cùng sử dụng bean đó. **Nếu ứng dụng có nhiều ConnectionFactory**, phải xác minh template và manager cùng trỏ tới **đúng cùng một bean/wrapper**, không chỉ là hai factory khác nhau cùng kết nối một broker.

Khi transaction bắt đầu, manager lấy/bind `Connection` và `Session` cho thread hiện tại. `JmsTemplate` nhận ra session được ràng buộc và dùng session đó trong callback. Khi `TransactionTemplate` kết thúc thành công, manager commit JMS transaction. Khi callback ném exception, manager rollback.

### 5.5. Service thực hiện hai thao tác gửi

**`src/main/java/example/jms/MultiSendService.java`**

```java
package example.jms;

import java.util.Objects;

import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.core.SessionCallback;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class MultiSendService {

    private final JmsTemplate jmsTemplate;
    private final TransactionTemplate transactionTemplate;

    public MultiSendService(
            JmsTemplate jmsTemplate,
            @Qualifier("jmsBatchTransactionTemplate")
            TransactionTemplate transactionTemplate) {
        this.jmsTemplate = jmsTemplate;
        this.transactionTemplate = transactionTemplate;
    }

    public int publishOrder(String orderId) {
        Integer published = transactionTemplate.execute(status ->
            jmsTemplate.execute((SessionCallback<Integer>) session -> {
                Queue orderQueue = session.createQueue("demo.orders");
                Queue auditQueue = session.createQueue("demo.audit");

                try (MessageProducer orderProducer =
                             session.createProducer(orderQueue);
                     MessageProducer auditProducer =
                             session.createProducer(auditQueue)) {

                    TextMessage order = session.createTextMessage(
                            "order-created:" + orderId);
                    order.setStringProperty("orderId", orderId);
                    orderProducer.send(order);

                    TextMessage audit = session.createTextMessage(
                            "audit-created:" + orderId);
                    audit.setStringProperty("orderId", orderId);
                    auditProducer.send(audit);
                }
                return 2;
            })
        );

        return Objects.requireNonNull(published, "Transaction returned null");
    }
}
```

**Đọc từ ngoài vào trong:**

1. `transactionTemplate.execute(...)` mở một JMS transaction thông qua `JmsTransactionManager`.
2. `jmsTemplate.execute(SessionCallback<Integer>)` nhận session gắn với transaction hiện tại.
3. Callback tạo hai đối tượng `Queue` và hai `MessageProducer` từ **cùng session**.
4. Từng message có body khác nhau nhưng cùng property nghiệp vụ `orderId`. Tránh dùng lại một `TextMessage` rồi sửa nội dung khi gửi sang Queue thứ hai; tách thông điệp giúp log/trace rõ ràng.
5. `producer.send` được gọi hai lần. Callback chủ động đóng **hai producer mà mình tạo** nhờ `try-with-resources`. **Không** đóng session mà template đã cấp.
6. Callback trả về `Integer 2`; giá trị này được trả tiếp qua `TransactionTemplate`.
7. Khi callback và transaction body kết thúc bình thường, `JmsTransactionManager` commit. Chỉ sau khi `transactionTemplate.execute` trả về, `publishOrder` mới trả lại `2`.
8. Nếu một trong hai send hoặc commit thất bại, exception được đẩy ra ngoài; transaction rollback nếu còn có thể rollback. Trong tình huống mất kết nối đúng lúc commit, trạng thái broker có thể **mơ hồ** với client, nên nghiệp vụ vẫn cần idempotency.

**Tại sao không gọi `session.commit()` trong service?** Vì session thuộc một transaction **do Spring quản lý**. Commit/rollback thủ công bên trong callback có thể phá hỏng ranh giới transaction, đặc biệt khi các operation khác vẫn cần tham gia.

### 5.6. Main và ApplicationRunner

**`src/main/java/example/jms/SessionCallbackApplication.java`**

```java
package example.jms;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class SessionCallbackApplication {

    public static void main(String[] args) {
        SpringApplication.run(SessionCallbackApplication.class, args);
    }

    @Bean
    ApplicationRunner sendOnStartup(MultiSendService service) {
        return args -> {
            int count = service.publishOrder("demo-001");
            System.out.println("committedJmsMessages=" + count);
        };
    }
}
```

Cả ba Java class cùng package `example.jms` để Spring component scan tìm được `@Configuration` và `@Service`. `ApplicationRunner` gọi service bean **qua Spring container**, nhưng ví dụ sử dụng `TransactionTemplate` nên không phụ thuộc vào AOP proxy cho transaction.

Với broker đang chạy, hai Queue hợp lệ, tài khoản đúng và transaction commit thành công, dòng do **ứng dụng chủ động in** là:

```text
committedJmsMessages=2
```

Các log khởi động Spring Boot hoặc Artemis client vẫn xuất hiện. Chương trình **không in nội dung nhận từ consumer**, vì ví dụ tập trung ở producer; để xác nhận Queue đã nhận message, xem broker console/metrics hoặc viết consumer integration test riêng. Chạy lại ứng dụng sẽ gửi thêm hai message mới có cùng payload, không phải là cơ chế gửi exactly-once.

### 5.7. Cách chạy

Trên PowerShell:

```powershell
$env:JMS_USERNAME = "dev-user"
$env:JMS_PASSWORD = "dev-password"
mvn spring-boot:run
```

Trên shell POSIX:

```bash
JMS_USERNAME=dev-user JMS_PASSWORD=dev-password mvn spring-boot:run
```

Điều chỉnh account theo broker đang sử dụng. Nếu broker không cho auto-create Queue, provision trước `demo.orders` và `demo.audit` theo routing ANYCAST của Artemis. Nếu broker ở máy khác, thay `spring.artemis.broker-url` bằng endpoint phù hợp. Khi thiếu broker/credentials hoặc Queue không tồn tại, chương trình có thể compile thành công nhưng không gửi được; đừng nhầm lỗi integration với lỗi Java syntax.

Để build mà không chạy:

```bash
mvn -q -DskipTests package
```

Chạy với broker mới là bài test integration thật. Không khẳng định đã kiểm thử runtime trong môi trường không cung cấp broker.

## 6. Điều cốt lõi: SessionCallback không tự bảo đảm commit

Đây là phần quan trọng nhất khi gửi nhiều thao tác.

### 6.1. Session dùng chung nhưng không transaction

Giả sử template mặc định không bật `sessionTransacted`, và không có Spring/JTA transaction đang mở:

```java
jmsTemplate.execute((SessionCallback<Void>) session -> {
    Queue first = session.createQueue("demo.orders");
    Queue second = session.createQueue("demo.audit");

    try (var p1 = session.createProducer(first);
         var p2 = session.createProducer(second)) {
        p1.send(session.createTextMessage("order-1"));
        p2.send(session.createTextMessage("audit-1"));
    }
    return null;
});
```

Nếu `p1.send` thành công nhưng `p2.send` ném lỗi, callback và template sẽ báo exception; **message thứ nhất có thể đã được provider chấp nhận**. Dù hai thao tác chung session, không có local transaction để rollback cả hai.

### 6.2. JmsTemplate.setSessionTransacted(true) và một bẫy quan trọng

`JmsTemplate` có thể cấu hình `setSessionTransacted(true)` để tạo session transacted trong môi trường unmanaged. Nhưng **không suy ra rằng `execute(SessionCallback)` tự gọi `session.commit()` sau callback**.

Trong Spring Framework 6.x, `JmsTemplate.execute(SessionCallback)` tổ chức lấy session → gọi callback → release session. Nó **không có lời gọi commit chung ở cuối callback** như một số convenience method gửi/nhận có logic commit riêng. Nếu tự tạo local transacted session và callback chỉ gọi `producer.send(...)` rồi thoát mà **không có transaction manager và không commit**, đóng session có thể rollback các send chưa commit.

Do đó không nên “khắc phục atomicity” bằng cách bật `sessionTransacted=true` rồi giữ nguyên callback mà không quyết định ai commit.

### 6.3. Ba mô hình rõ ràng

| Mô hình | Điều kiện | Ai quyết định commit? | Độ nguyên tử của hai send |
| --- | --- | --- | --- |
| `SessionCallback` trên session thường | Không transaction, ví dụ mặc định | Không có transaction chung | Không bảo đảm all-or-nothing. |
| Callback dùng local transacted session **unmanaged** | `sessionTransacted=true` và callback tự điều khiển | Code phải `session.commit()`/`rollback()` thích hợp | Có local JMS transaction nếu provider hỗ trợ. |
| `SessionCallback` tham gia `JmsTransactionManager` | Transaction boundary `TransactionTemplate` hoặc `@Transactional` | Spring transaction manager | Các send trong cùng JMS transaction commit/rollback cùng nhau. |

**Không dùng đồng thời hai người điều khiển commit.** Trong ví dụ mục 5, manager đã quản lý transaction nên callback không tự commit/rollback.

### 6.4. Ví dụ local transaction thủ công — chỉ khi không có manager

Khi chạy code độc lập, chưa dùng `JmsTransactionManager`/JTA, và chủ đích muốn một transaction **mà callback tự commit**, có thể dùng một template riêng:

```java
JmsTemplate localTemplate = new JmsTemplate(connectionFactory);
localTemplate.setSessionTransacted(true);

localTemplate.execute((SessionCallback<Void>) session -> {
    try {
        Queue queue = session.createQueue("demo.orders");
        try (var producer = session.createProducer(queue)) {
            producer.send(session.createTextMessage("first"));
            producer.send(session.createTextMessage("second"));
        }

        session.commit(); // Chỉ trong local session tự quản lý.
        return null;
    } catch (jakarta.jms.JMSException | RuntimeException ex) {
        try {
            session.rollback();
        } catch (jakarta.jms.JMSException rollbackFailure) {
            ex.addSuppressed(rollbackFailure);
        }
        throw ex;
    }
});
```

Đây là **snippet** giả định biến `connectionFactory`, import `JmsTemplate`/`SessionCallback` và broker đã sẵn sàng. Nó không được đặt trong một Spring/JTA transaction có sẵn. Lỗi phát sinh trong `close()` sau khi commit cũng cần được log/giám sát; nếu commit ném lỗi do mất kết nối, client không luôn biết broker đã commit chưa. Trong Spring service, **nên ưu tiên manager-managed boundary ở mục 5** vì rõ ownership và dễ kết hợp nhiều lời gọi template.

### 6.5. @Transactional là lựa chọn khác cho cùng mục tiêu

Bạn có thể thay `TransactionTemplate` bằng `@Transactional` nếu ứng dụng đã có hỗ trợ AOP/proxy đúng cách:

```java
import org.springframework.transaction.annotation.Transactional;
import org.springframework.jms.core.SessionCallback;

@Transactional(transactionManager = "jmsTransactionManager")
public int publishWithAnnotation(String id) {
    Integer count = jmsTemplate.execute((SessionCallback<Integer>) session -> {
        try (var producer =
                     session.createProducer(session.createQueue("demo.orders"))) {
            producer.send(session.createTextMessage("event-1:" + id));
            producer.send(session.createTextMessage("event-2:" + id));
        }
        return 2;
    });
    return java.util.Objects.requireNonNull(count);
}
```

Đây là **method minh họa bổ sung** bên trong Spring-managed service đã có `jmsTemplate`, không phải file Java độc lập. Cần `@EnableTransactionManagement` hoặc hạ tầng transaction management tương ứng, và lời gọi phải đi **qua Spring proxy**. Nếu một method trong cùng class gọi `this.publishWithAnnotation(...)` theo proxy-based AOP mặc định, lời gọi nội bộ đó không tạo transaction advice. Đừng thêm cả hai kiểu transaction boundary chồng nhau chỉ để “chắc ăn”.

Khi dùng local transaction của `JmsTransactionManager`, JDBC/database **không tự động** cùng atomic. Nếu yêu cầu vừa lưu DB vừa gửi JMS đáng tin cậy, cân nhắc transactional outbox hoặc XA/JTA được cấu hình thực sự, không chỉ thêm `@Transactional`.

## 7. So sánh SessionCallback và ProducerCallback

Ngoài `SessionCallback<T>`, `JmsTemplate` còn cung cấp `ProducerCallback<T>`:

```java
Integer count = jmsTemplate.execute(
        "demo.orders",
        (session, producer) -> {
            producer.send(session.createTextMessage("one"));
            producer.send(session.createTextMessage("two"));
            return 2;
        });
```

Trong overload `execute(destinationName, ProducerCallback)`, **JmsTemplate tạo và đóng `MessageProducer`**; callback nhận sẵn session + producer. Điều này giảm boilerplate khi nhiều send cùng một destination.

| Tình huống | Phù hợp hơn |
| --- | --- |
| Gửi một message, không cần thao tác JMS mức thấp | `convertAndSend` hoặc `send(MessageCreator)`. |
| Gửi nhiều message đến **một Queue** bằng cùng producer | `ProducerCallback` có thể ngắn gọn hơn. |
| Gửi nhiều Queue/Topic, tạo nhiều producer, cần session logic riêng | `SessionCallback`. |
| Cần chỉnh headers/properties trên message trước gửi nhưng chỉ một send | `MessageCreator`/`MessagePostProcessor`. |
| Cần nhiều lời gọi template cùng transaction, nhưng không bắt buộc cùng callback | `JmsTransactionManager` + `TransactionTemplate` hoặc `@Transactional`. |

**Cả `ProducerCallback` và `SessionCallback` đều không tự tạo transaction nguyên tử.** Lựa chọn callback là lựa chọn về mức truy cập tài nguyên; transaction boundary là trách nhiệm riêng.

### Sử dụng một producer không gắn destination

Jakarta Messaging cho phép producer **không định danh destination**:

```java
jmsTemplate.execute((SessionCallback<Void>) session -> {
    var firstQueue = session.createQueue("demo.orders");
    var secondQueue = session.createQueue("demo.audit");

    try (var producer = session.createProducer(null)) {
        producer.send(firstQueue, session.createTextMessage("first"));
        producer.send(secondQueue, session.createTextMessage("second"));
    }
    return null;
});
```

Đây là đoạn minh họa dùng `MessageProducer.send(Destination, Message)`: tạo một anonymous producer rồi chọn destination khi gửi. Nó có thể gọn hơn hai producer riêng, nhưng thiết lập QoS và khả năng tối ưu phụ thuộc provider. Với yêu cầu portability hoặc convention rõ ràng, tạo hai producer gắn Queue như ví dụ chính cũng hoàn toàn hợp lệ.

## 8. Header, properties và Quality of Service trong callback

Một lý do quan trọng để dùng `SessionCallback` là bạn có toàn quyền thao tác `Message`:

```java
jmsTemplate.execute((SessionCallback<Void>) session -> {
    Queue queue = session.createQueue("demo.orders");
    try (var producer = session.createProducer(queue)) {
        producer.setDeliveryMode(jakarta.jms.DeliveryMode.PERSISTENT);
        producer.setPriority(4);
        producer.setTimeToLive(60_000L);

        var message = session.createTextMessage("order-created");
        message.setStringProperty("eventType", "ORDER_CREATED");
        message.setStringProperty("orderId", "o-123");
        message.setJMSCorrelationID("corr-o-123");

        producer.send(message);
    }
    return null;
});
```

Đây là snippet có sẵn `jmsTemplate` và import `SessionCallback`, `Queue`. Vì **callback tự gọi `producer.send`**, đừng giả định mọi cấu hình tiện ích của `JmsTemplate` như explicit QoS, delivery delay hay message conversion sẽ tự được áp dụng giống như khi gọi `jmsTemplate.convertAndSend(...)`. Bạn đang sử dụng **JMS API gốc** trong callback; hãy set producer QoS, headers và properties tương ứng khi cần.

Các điểm cẩn trọng:

- `PERSISTENT` là yêu cầu delivery mode JMS, không tự thay thế chính sách broker persistence, replication, HA hay commit.
- `timeToLive` quy định thời gian tồn tại, không phải timeout đợi xác nhận gửi. Khi hết hạn, provider/broker có thể xử lý expiration theo chính sách.
- `priority` gợi ý ưu tiên; thứ tự delivery thực tế còn phụ thuộc provider, concurrent consumer và cấu hình.
- `JMSCorrelationID` giúp liên kết request/reply hoặc trace; nó không tự tạo business idempotency key.
- Thuộc tính JMS do bạn đặt cần tên hợp lệ; các property nghiệp vụ như `eventType`, `orderId` có thể dùng cho selector theo JMS.
- Nếu thao tác với `BytesMessage`/`MapMessage`/`ObjectMessage` thay `TextMessage`, chú ý tương thích serialization và security. Không deserialize object không tin cậy tùy ý.

## 9. Gửi nhiều thao tác có bảo đảm thứ tự không?

**Thứ tự gọi `send`** trong cùng thread/session là thứ tự chương trình thực thi:

```text
producer.send(message-1)
producer.send(message-2)
producer.send(message-3)
```

Tuy vậy **thứ tự xử lý nghiệp vụ ở consumer** không thể suy ra chỉ từ ba dòng code:

- Với **một Queue**, nhiều competing consumer có thể nhận và xử lý song song, nên message thứ hai có thể hoàn tất xử lý trước message thứ nhất.
- Priority, redelivery, expiry và cơ chế provider có thể làm thứ tự delivery thực tế khác kỳ vọng.
- Với hai Queue khác nhau, không có một global ordering giữa hai destination, kể cả khi hai message commit trong cùng JMS transaction.
- Một transaction commit hai send bảo đảm ranh giới commit/rollback JMS, **không** bảo đảm hai consumer downstream cùng xử lý nguyên tử hoặc cùng thời điểm.
- Nếu cần giữ thứ tự theo `orderId`, cân nhắc grouping/partitioning theo key hoặc một consumer cho từng nhóm theo thiết kế broker, đồng thời kiểm tra retry semantics.

Khi business yêu cầu audit chỉ được xử lý sau khi order processing hoàn tất, **gửi order và audit cùng transaction không tự tạo điều kiện phụ thuộc đó**. Bạn có thể cần workflow, message chaining hoặc orchestration riêng, thay vì cố suy ra từ thứ tự send.

## 10. Xử lý lỗi và retry đúng cách

### 10.1. Lỗi giữa hai lần gửi

Giả sử `orderProducer.send(order)` thành công, nhưng `auditProducer.send(audit)` ném `JMSException`:

- Trong session không transacted, order message có thể đã tới broker; không thể dùng `SessionCallback` để quay ngược điều đó.
- Trong `JmsTransactionManager` ở mục 5, checked `JMSException` thoát khỏi callback được Spring chuyển thành họ unchecked `JmsException`. `TransactionTemplate` bắt lỗi, rollback session đang tham gia.
- Nếu đã **commit** rồi mới có exception do các phần việc khác hoặc network bị mất đúng thời điểm trả kết quả, client có thể không chắc transaction đã commit hay chưa. Việc retry có thể phát sinh message lặp ở tầng nghiệp vụ.

**Không nuốt exception chỉ để service trả về 2.** Nếu bạn catch `JMSException` hoặc Spring `JmsException` rồi trả về bình thường trong transaction body, Spring có thể hiểu đó là thành công và commit những send trước đó. Khi muốn rollback, để exception thoát ra hoặc chủ động `status.setRollbackOnly()` trong `TransactionTemplate`.

### 10.2. Retry toàn bộ đơn vị nghiệp vụ, không retry tùy tiện từng send

Nếu muốn “hoặc cả hai message, hoặc không message nào”, logic retry cần bao phủ **toàn bộ transaction**. Đừng làm:

```text
send(order) thành công
send(audit) thất bại
retry send(audit) độc lập
```

trong khi nghiệp vụ kỳ vọng cả hai message gắn chung một sự kiện có trạng thái nhất quán. Thay vào đó:
- Phân biệt lỗi có thể retry (mất kết nối tạm thời) với lỗi cấu hình, quyền, bad payload.
- Đặt giới hạn số lần thử, exponential backoff và cơ chế ngăn retry storm.
- Gắn **eventId/orderId bất biến** vào từng message để consumer có thể idempotent.
- Quan sát DLQ, redelivery và transaction rollback ở broker; bên gửi không thể tự đảm bảo exactly-once processing của consumer.

### 10.3. Không gộp database và JMS một cách ngây thơ

`JmsTransactionManager` là transaction manager **cho JMS resource**. Câu lệnh SQL qua `DataSourceTransactionManager` **không tự nằm chung** một atomic transaction chỉ vì hai thao tác cùng xuất hiện trong method có `@Transactional`.

Ví dụ nguy hiểm:
1. Ghi row order vào database, transaction DB commit.
2. Gửi hai JMS message, JMS commit thất bại.
3. Database đã có order nhưng không có message thông báo.

Hoặc chiều ngược lại: message được commit nhưng DB rollback. Với các hệ thống yêu cầu nhất quán giữa DB và JMS, lựa chọn phổ biến là **transactional outbox** kết hợp publisher idempotent, hoặc JTA/XA khi hạ tầng thực sự hỗ trợ và phù hợp chi phí vận hành.

## 11. Hiệu năng, phạm vi session và giới hạn lô

`SessionCallback` giúp **định nghĩa một phạm vi session rõ ràng**. Dùng hợp lý có thể giảm việc lặp lại tạo/đóng producer hoặc giúp nhóm nhiều send trong một transaction. Nhưng không nên đánh đồng với batch JDBC hay một API gửi 1.000 message trong một network packet.

**Khi gửi một lô lớn:**
- Đặt giới hạn số message/byte cho mỗi transaction. Transaction quá lớn tăng thời gian giữ tài nguyên, memory, latency commit và lượng công việc cần rollback.
- Cân nhắc chia thành các lô có transaction riêng nếu business cho phép; mỗi lô cần ID và retry semantics rõ.
- Không mở producer mới cho từng message khi tất cả gửi cùng Queue trong cùng callback; reuse một producer trong một phạm vi ngắn.
- Khi gửi nhiều Queue, có thể tạo producer gắn từng Queue hoặc producer không định danh; đo trên provider thực.
- Không giữ một `Session` hoặc `MessageProducer` trong singleton service để tái sử dụng xuyên request. Nếu cần optimization giữa nhiều callback, để `ConnectionFactory` cache/pool và Spring lifecycle xử lý.
- `Session` là đối tượng theo thread/context, không chạy parallel Java Stream trong callback trên cùng session.
- Điều chỉnh delivery mode, persistence, message size, session cache và transaction size theo đo lường; không khẳng định callback tự động nhanh hơn nhiều lần `convertAndSend` dưới một transaction dùng chung.

Một ví dụ suy nghĩ về kích thước lô: nếu mỗi transaction chứa hàng trăm sự kiện, rollback vì sự kiện cuối cùng có thể buộc gửi lại cả lô. Phải đánh đổi giữa throughput và phạm vi failure, thay vì chỉ tối đa hóa số lượng message trong một callback.

## 12. Những lỗi phổ biến

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nghĩ `SessionCallback` = transaction | Message 1 đã gửi nhưng message 2 lỗi, không atomic | Khai báo `JmsTransactionManager` và transaction boundary thực sự. |
| Bật `sessionTransacted=true` nhưng callback không commit ở unmanaged session | Pending local transaction rollback khi session đóng | Dùng manager-managed transaction hoặc commit/rollback thủ công đúng scope. |
| Gọi `session.commit()` trong Spring-managed transaction | Phá ranh giới manager, có thể commit sớm | Để manager commit sau transaction body. |
| Gọi `session.close()` trong callback | Template còn cần session, lỗi resource lifecycle | Không đóng session do Spring đưa vào. |
| Không đóng producer do mình tạo | Rò rỉ resource phía provider | `try-with-resources` cho `MessageProducer` tự tạo. |
| Dùng chung `Session` trên nhiều thread | Vi phạm quy tắc concurrency của JMS | Chạy tuần tự trong callback; để mỗi thread có session riêng. |
| Gọi `jmsTemplate.send(...)` lồng bên trong callback với suy nghĩ dùng chính session đang có | Có thể tạo/tham gia resource theo logic khác, khó dự đoán khi không có tx | Dùng trực tiếp `session` hoặc định rõ Spring transaction bên ngoài. |
| Catch rồi bỏ qua `JmsException` | Transaction manager thấy callback bình thường và commit một phần | Propagate exception hoặc mark rollback-only. |
| Dùng `@Transactional` qua self-invocation | Annotation không được proxy áp dụng | Gọi qua Spring bean/proxy hoặc dùng `TransactionTemplate`. |
| Nghĩ hai Queue commit cùng nhau thì hai consumer xử lý cùng nhau | Consumer xử lý độc lập, thứ tự/ack khác nhau | Thiết kế workflow và idempotency downstream. |
| Tăng batch vô hạn | Transaction quá lớn, rollback tốn kém | Chia lô theo SLA và giới hạn provider. |
| Không phân biệt Queue/Topic, domain và destination | Message đi sai nơi hoặc provider báo lỗi | Resolve destination đúng theo JMS provider, kiểm tra `pubSubDomain` nếu dùng tên qua template. |

## 13. Kiểm thử và quan sát

Một cách kiểm thử đầy đủ nên tách **unit test callback**, **integration với broker** và **kiểm thử lỗi transaction**.

### 13.1. Kiểm thử đường đi thành công

- Khởi động một Artemis test broker phù hợp, provision `demo.orders` và `demo.audit`.
- Gọi `publishOrder("case-001")` đúng một lần.
- Kiểm tra mỗi Queue có một message mới với body tương ứng và property `orderId=case-001`; nếu có consumer khác, kiểm tra bằng test consumer/record thay vì chỉ nhìn Queue depth.
- Kết quả `committedJmsMessages=2` phải xuất hiện **sau khi** transaction manager trả về bình thường.
- Dùng eventId duy nhất mỗi test để phân biệt message của lần chạy trước.

### 13.2. Kiểm thử rollback

Chủ động làm message thứ hai gây lỗi trước commit, ví dụ trong môi trường test dùng broker policy từ chối gửi tới `demo.audit` hoặc một cấu hình provider cho phép mô phỏng lỗi. Kỳ vọng:
- Service báo exception.
- Transaction rollback nếu không xảy ra lỗi mơ hồ ở commit.
- Broker không hiển thị message **mới commit** từ transaction đó.
- Log ghi rõ orderId, loại lỗi, destination, transaction rollback — không log password.

**Không** giả lập bằng cách ném exception sau khi `TransactionTemplate` đã hoàn thành và commit, vì lúc đó rollback không thể thu hồi message đã gửi.

### 13.3. Kiểm thử retry và broker restart

- Dừng broker khi gửi, quan sát thông báo lỗi và chính sách reconnect.
- Cho broker chạy lại; thử gửi lại **cùng eventId** để kiểm tra consumer idempotency.
- Thử mất kết nối đúng giai đoạn commit nếu môi trường kiểm thử hỗ trợ fault injection; không gán chắc chắn trạng thái commit chỉ từ một lỗi timeout.
- Đo số connection/session/producer ở broker sau nhiều lượt gửi, bảo đảm không tăng vô hạn do resource leak.

### 13.4. Những chỉ số cần theo dõi

- Số lần gọi `publishOrder` thành công/thất bại, latency toàn transaction.
- Số lần JMS commit/rollback, lý do rollback, lỗi kết nối và timeout.
- Backlog, in-flight, consumer count, redelivery và DLQ cho mỗi Queue.
- Số message gửi trung bình mỗi transaction; kích thước message/transaction.
- Số message nghiệp vụ trùng eventId hoặc số lần consumer idempotency bỏ qua duplicate.

**Lưu ý:** counters của publisher thường đo thao tác client, không thể tự chứng minh tất cả consumer đã xử lý xong; cần metrics/tracing downstream.

## 14. Checklist trước khi dùng trong production

- Xác định rõ mục tiêu là **chia sẻ session** hay **gửi nguyên tử**. Với nguyên tử, cấu hình transaction manager/boundary tường minh.
- Dùng cùng `ConnectionFactory` cho template và `JmsTransactionManager`, đặc biệt nếu có wrapper cache/pool.
- Gửi tất cả operation mong muốn từ **cùng session**; giữ callback ngắn, tuần tự và giới hạn lô.
- Đóng producer do callback tạo; không đóng session/template-managed connection và không lưu session ra ngoài callback.
- Để checked `JMSException` chuyển thành Spring `JmsException` hoặc propagate lỗi; không nuốt lỗi trong transaction.
- Nếu sử dụng `@Transactional`, xác minh proxy invocation và đúng tên transaction manager.
- Đặt orderId/eventId để trace/idempotency; cân nhắc outbox nếu có transaction database liên quan.
- Thử kiểm tra quyền send đến mọi Queue và policy tồn tại destination trước khi deploy.
- Không cam kết global processing order chỉ vì gửi trong cùng callback.
- Benchmark với broker thực trước khi kết luận callback/batch mang lại throughput tốt hơn.

## 15. Câu hỏi tự kiểm tra

**1.** Vì sao hai lệnh `producer.send(...)` trong một `SessionCallback` không tự động all-or-nothing?

Vì cùng một `Session` chỉ nói về phạm vi tài nguyên. Atomicity yêu cầu session transacted và một biên commit/rollback rõ ràng.

**2.** Trong callback, phải đóng `MessageProducer` hay `Session`?

Đóng producer do callback tự tạo. Không đóng session do `JmsTemplate` cung cấp.

**3.** Nếu dùng `JmsTransactionManager`, lúc nào transaction commit?

Khi Spring transaction boundary (ví dụ `TransactionTemplate.execute`) kết thúc thành công, **sau** callback đã trả về.

**4.** `JmsTemplate.setSessionTransacted(true)` có đủ để `execute(SessionCallback)` tự commit không?

Không nên giả định như vậy. Với local transacted session unmanaged, cần commit/rollback đúng chỗ; tốt hơn dùng transaction manager tường minh trong service Spring.

**5.** Khi nào `ProducerCallback` tiện hơn `SessionCallback`?

Khi cần gửi nhiều message đến một destination và muốn template tạo/đóng producer giúp mình.

**6.** Nếu JMS transaction commit hai message vào hai Queue, liệu hai consumer có luôn xử lý đồng thời, đúng một lần và theo thứ tự không?

Không. Atomicity của publish khác với concurrency, processing order và idempotency phía consumer.

## Kết luận

`JmsTemplate.execute(SessionCallback<T>)` là cách đúng khi cần thực hiện **nhiều thao tác JMS trên cùng một `Session`** mà vẫn để Spring quản lý acquisition/release của session và connection. Bạn có thể tạo nhiều message, nhiều producer, gửi đến một hoặc nhiều Queue/Topic, gắn property/header và trả về kết quả tổng hợp.

Đối với yêu cầu “hoặc tất cả message được gửi, hoặc không message nào”, hãy đặt callback **bên trong một JMS transaction** được quản lý bởi `JmsTransactionManager`/`TransactionTemplate` hoặc `@Transactional` được cấu hình chuẩn. Không coi cùng session là cùng transaction; không tự commit khi Spring đang sở hữu transaction; không nhầm nguyên tử lúc publish với xử lý exactly-once ở downstream.

## Tài liệu tham khảo

- Spring Framework — Sending a Message, `SessionCallback` và `ProducerCallback`: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/sending.html
- Spring Framework — Using JMS và transaction management: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html
- Spring Framework — `JmsTemplate` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/core/JmsTemplate.html
- Spring Framework — `SessionCallback` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/core/SessionCallback.html
- Spring Framework — `JmsTransactionManager` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/connection/JmsTransactionManager.html
- Spring Framework — TransactionTemplate: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
- Spring Boot 3.5 — JMS / ActiveMQ Artemis: https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html
- Jakarta Messaging 3.1 — specification: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Jakarta Messaging 3.1 — `MessageProducer` API: https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageproducer