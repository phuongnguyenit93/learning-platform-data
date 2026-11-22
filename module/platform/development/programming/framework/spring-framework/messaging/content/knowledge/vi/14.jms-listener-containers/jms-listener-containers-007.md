# Các mức cache và ảnh hưởng tới tài nguyên JMS trong Spring

Trong Spring JMS, `DefaultMessageListenerContainer` quản lý việc nhận message, tạo listener thread và sử dụng các tài nguyên JMS như `Connection`, `Session` và `MessageConsumer`. Mỗi lần tạo rồi đóng các tài nguyên này đều có chi phí ở client và có thể tạo thêm công việc cho broker.

Thuộc tính `cacheLevel` quyết định container giữ lại những tài nguyên nào để tái sử dụng giữa các lần nhận message. Chọn mức cache phù hợp giúp giảm chi phí tạo resource, đồng thời giữ đúng hành vi transaction và subscription của provider.

Các mức cache được định nghĩa trên `DefaultMessageListenerContainer`:

| Hằng số | Giá trị | Tài nguyên được cache |
| --- | ---: | --- |
| `CACHE_NONE` | 0 | Không cache resource JMS |
| `CACHE_CONNECTION` | 1 | Cache connection dùng chung |
| `CACHE_SESSION` | 2 | Cache connection và session của listener invoker |
| `CACHE_CONSUMER` | 3 | Cache connection, session và consumer của listener invoker |
| `CACHE_AUTO` | 4 | Để Spring chọn mức phù hợp theo transaction manager |

`CACHE_AUTO` là chế độ tự chọn, không phải một tầng resource nằm sau `CACHE_CONSUMER`. Đây cũng là giá trị mặc định của container.

## 1. Các tài nguyên mà listener container quản lý

Một listener container thường thực hiện chuỗi thao tác:

```text
ConnectionFactory
       |
       v
   Connection
       |
       v
    Session
       |
       v
 MessageConsumer
       |
       v
 receive() -> MessageListener
```

- **Connection:** kết nối client tới JMS provider/broker.
- **Session:** ngữ cảnh tạo consumer, nhận message và quản lý acknowledgement/transaction. Một session không được dùng đồng thời bởi nhiều thread.
- **MessageConsumer:** đăng ký nhận message từ queue hoặc topic, có thể đi kèm selector và thông tin subscription.
- **Listener invoker:** tác vụ/thread do `DefaultMessageListenerContainer` quản lý để gọi `receive()` và dispatch message tới listener.

Mỗi listener invoker cần session riêng để xử lý an toàn. Khi tăng concurrency, số session và consumer đang hoạt động thường tăng theo số invoker.

## 2. Ý nghĩa của từng mức cache

Các mức cache là các bước tích lũy: mức cao hơn giữ lại thêm resource ở mức thấp hơn.

### CACHE_NONE — không giữ lại resource

`CACHE_NONE` có giá trị `0`. Container không cache connection, session hoặc consumer. Khi nhận message, container lấy các resource cần thiết; sau lần nhận, chúng được đóng và lần tiếp theo phải lấy lại.

Theo tài liệu Spring, khi không bật cache, một connection và một session mới được tạo cho mỗi lần nhận message. Consumer cũng được tạo lại theo vòng đời lần nhận.

Ưu điểm:

- Tài nguyên được lấy mới trong từng transaction, phù hợp với một số môi trường XA/Jakarta EE.
- Vòng đời resource đơn giản, ít giữ consumer hoặc session lâu dài.
- Hữu ích khi provider yêu cầu handle mới để enlist vào transaction.

Đổi lại, tạo và đóng connection/session/consumer liên tục làm tăng overhead, độ trễ và số thao tác với broker. Với tải cao hoặc subscription không durable, khoảng trống giữa các lần đăng ký consumer có thể làm ứng dụng bỏ lỡ message.

### CACHE_CONNECTION — giữ connection dùng chung

`CACHE_CONNECTION` có giá trị `1`. Container giữ lại connection dùng chung trong vòng đời listener container. Session và consumer vẫn được tạo lại cho từng lần nhận.

Mức này giảm chi phí mở connection tới broker nhưng vẫn có chi phí tạo session và consumer. Nó có thể hữu ích khi provider tạo connection đắt, nhưng transaction hoặc môi trường triển khai chưa cho phép cache session.

Không nên mặc định chọn mức này chỉ vì nó có số lượng resource cache thấp. Hãy kiểm tra liệu connection dùng chung có phù hợp với provider, transaction manager và chính sách concurrency của ứng dụng hay không.

### CACHE_SESSION — giữ connection và session

`CACHE_SESSION` có giá trị `2`. Container giữ connection và session của từng listener invoker. Consumer được tạo khi cần nhận rồi đóng sau lần nhận.

Mức này tránh tạo lại session cho mỗi message. Nó phù hợp khi session creation có chi phí đáng kể nhưng consumer cần được tạo mới để đáp ứng yêu cầu transaction, selector hoặc subscription của provider.

Vì mỗi invoker có session riêng, tăng số consumer đồng thời cũng làm tăng số session được giữ lại. Không chia sẻ cùng một session cho nhiều listener thread.

### CACHE_CONSUMER — giữ connection, session và consumer

`CACHE_CONSUMER` có giá trị `3`. Container giữ connection dùng chung, session của từng listener invoker và consumer tương ứng trong suốt thời gian invoker hoạt động. Consumer được tái sử dụng giữa các lần gọi `receive()`.

Đây là mức cache đầy đủ nhất. Nó giảm mạnh việc tạo và đăng ký lại consumer, đồng thời duy trì đăng ký với destination ổn định trong suốt vòng đời listener task.

Ưu điểm:

- Giảm việc tạo consumer lặp lại.
- Giảm thao tác đăng ký/hủy đăng ký với broker.
- Phù hợp với listener chạy liên tục trên queue.
- Là mức mặc định hiệu lực khi không có external transaction manager và `cacheLevel=CACHE_AUTO`.

Nhược điểm là consumer và subscription được giữ lâu hơn. Khi thay đổi selector, destination hoặc cấu hình subscription, cần quản lý việc dừng và khởi động lại container phù hợp. Khi tăng concurrency, mỗi invoker có thể giữ thêm một session và consumer.

Trong `DefaultMessageListenerContainer`, chỉ `CACHE_CONSUMER` duy trì một đăng ký consumer cố định. Các mức thấp hơn có thể tạo lại consumer trong các lần thực thi invoker.

## 3. CACHE_AUTO và ảnh hưởng của transaction manager

Mặc định, `DefaultMessageListenerContainer` có:

```java
container.setCacheLevel(DefaultMessageListenerContainer.CACHE_AUTO);
```

Spring phân giải `CACHE_AUTO` trong quá trình `initialize()`:

| Cấu hình transaction | Mức cache hiệu lực |
| --- | --- |
| Không cấu hình external `PlatformTransactionManager` | `CACHE_CONSUMER` |
| Có external `PlatformTransactionManager` | `CACHE_NONE` |

Điều kiện được xét là sự hiện diện của transaction manager trên container. Việc phân giải diễn ra khi container khởi tạo. Vì vậy, trước `initialize()`, `getCacheLevel()` có thể trả về `CACHE_AUTO` (4); sau khởi tạo, nó trả về mức hiệu lực (3 hoặc 0).

### Vì sao external transaction manager mặc định dùng CACHE_NONE?

Trong môi trường Jakarta EE/XA, một số application server chỉ enlist JMS resource vào transaction nếu `Connection` và `Session` được lấy mới trong phạm vi transaction. Nếu container giữ session hoặc consumer qua nhiều transaction, provider có thể không đăng ký resource đúng cách với XA coordinator.

Vì lý do tương thích đó, Spring mặc định lấy mới resource khi có external transaction manager. Tuy nhiên, quy tắc này phụ thuộc provider và application server. Một số môi trường cho phép cache connection hoặc session trong XA. Khi đã xác minh chính sách của server, có thể đặt tường minh `CACHE_CONNECTION` hoặc `CACHE_SESSION` nếu phù hợp.

Không nên tự tăng mức cache trong môi trường XA chỉ để cải thiện throughput mà chưa kiểm tra khả năng enlist resource của provider.

### Local JMS transaction và external transaction khác nhau

`sessionTransacted=true` bật transaction cục bộ trên JMS session. Nó không đồng nghĩa với việc cấu hình external `PlatformTransactionManager`.

Nếu chỉ dùng local JMS transaction và không đặt external transaction manager, `CACHE_AUTO` vẫn phân giải thành `CACHE_CONSUMER`. Mỗi listener invoker có session riêng và container có thể giữ consumer để tái sử dụng.

Khi cần kết hợp nhận message với cập nhật database trong một XA transaction, cấu hình external `JtaTransactionManager` cùng JMS `ConnectionFactory` có hỗ trợ XA. Khi đó `CACHE_AUTO` mặc định thành `CACHE_NONE` để lấy resource mới theo transaction.

Với nhiều ứng dụng, local JMS transaction cùng xử lý idempotent có thể hiệu quả hơn XA toàn bộ. Đổi lại, khi JVM dừng bất ngờ, ứng dụng cần chấp nhận khả năng xử lý lặp và có cơ chế chống trùng phù hợp.

## 4. Cache level tác động tới tài nguyên như thế nào?

Giả sử container có 4 listener invoker đang hoạt động:

| Mức cache | Connection | Session | Consumer |
| --- | --- | --- | --- |
| `CACHE_NONE` | Tạo lại theo lần nhận | Tạo lại theo lần nhận | Tạo lại theo lần nhận |
| `CACHE_CONNECTION` | Connection dùng chung được giữ lại | Tạo lại theo lần nhận | Tạo lại theo lần nhận |
| `CACHE_SESSION` | Connection dùng chung được giữ lại | Một session được giữ cho mỗi invoker | Tạo lại theo lần nhận |
| `CACHE_CONSUMER` | Connection dùng chung được giữ lại | Một session được giữ cho mỗi invoker | Một consumer được giữ cho mỗi invoker |

Bảng mô tả cách quản lý resource của container; số lượng thực tế còn phụ thuộc concurrency, quá trình recovery, transaction và provider.

Với `CACHE_CONSUMER`, 4 invoker thường giữ 4 session và 4 consumer. Khi `maxConcurrentConsumers` cho phép scale lên 10, container có thể cần tới 10 session và 10 consumer tương ứng. Connection được chia sẻ theo cơ chế của container.

Điều này cho thấy cache level và concurrency phải được thiết kế cùng nhau. Tăng cache level giúp giảm chi phí tạo resource, nhưng tăng concurrency cũng làm tăng số resource được giữ đồng thời.

## 5. Ảnh hưởng đến throughput và subscription

### Chi phí tạo resource

Tạo connection thường đắt hơn tạo session; tạo consumer cũng có chi phí đăng ký với broker. Giữ lại resource thường giúp giảm latency và tăng throughput khi listener nhận message liên tục.

- `CACHE_NONE`: chi phí tạo resource cao nhất, nhưng phù hợp với yêu cầu lấy resource mới trong mỗi transaction.
- `CACHE_CONNECTION`: giảm chi phí connection.
- `CACHE_SESSION`: giảm thêm chi phí session.
- `CACHE_CONSUMER`: giảm cả chi phí đăng ký consumer, thường phù hợp với listener chạy lâu dài.

Không nên suy luận rằng mức cache cao nhất luôn nhanh nhất trong mọi hệ thống. Provider có thể giới hạn consumer, session hoặc connection; giữ quá nhiều resource có thể làm broker cạn tài nguyên hoặc tăng thời gian recovery.

### Queue và topic

Với queue, nhiều consumer thường cạnh tranh nhận message từ cùng queue. Tăng concurrency có thể tăng throughput nếu broker và xử lý phía sau đủ năng lực.

Với topic, mỗi subscription độc lập có thể nhận một bản sao của publication. Nếu tạo nhiều consumer/subscription trên cùng topic trong một node, ứng dụng có thể nhận cùng publication nhiều lần. Vì vậy, dynamic scaling thường phù hợp với queue hơn topic; topic thường giữ concurrency mặc định một consumer trừ khi thiết kế subscription yêu cầu khác.

### Non-durable subscription và CACHE_NONE

Khi không cache, container liên tục đóng và tạo consumer. Với tải cao và non-durable subscription, message được publish trong khoảng thời gian subscription chưa đăng ký có thể bị bỏ lỡ. Đây là lý do Spring khuyến nghị chọn cache level phù hợp khi dùng listener container ở tải lớn.

Với durable subscription, provider lưu message theo chính sách durable subscription khi subscriber offline, nhưng vẫn phải kiểm tra client ID, subscription name, provider semantics và thời điểm đăng ký lại.

## 6. Cấu hình cache level

Có hai cách đặt mức cache.

### Dùng hằng số

```java
import org.springframework.jms.listener.DefaultMessageListenerContainer;

DefaultMessageListenerContainer container =
        new DefaultMessageListenerContainer();

container.setCacheLevel(
        DefaultMessageListenerContainer.CACHE_CONSUMER);
```

Cách này giúp compiler kiểm tra tên hằng số và dễ đọc khi cấu hình bằng Java.

### Dùng tên hằng số

```java
container.setCacheLevelName("CACHE_SESSION");
```

`setCacheLevelName` nhận tên một trong các hằng số `CACHE_NONE`, `CACHE_CONNECTION`, `CACHE_SESSION`, `CACHE_CONSUMER` hoặc `CACHE_AUTO`. Tên không hợp lệ sẽ gây `IllegalArgumentException`.

### Cấu hình một listener container trong Spring

Ví dụ dưới đây chọn `CACHE_CONSUMER` cho queue có xử lý local transaction:

```java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.MessageListener;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.listener.DefaultMessageListenerContainer;

@Configuration
public class OrdersListenerConfiguration {

    @Bean
    DefaultMessageListenerContainer ordersListenerContainer(
            ConnectionFactory connectionFactory,
            MessageListener ordersListener) {

        DefaultMessageListenerContainer container =
                new DefaultMessageListenerContainer();

        container.setConnectionFactory(connectionFactory);
        container.setDestinationName("orders");
        container.setMessageListener(ordersListener);

        container.setCacheLevel(
                DefaultMessageListenerContainer.CACHE_CONSUMER);

        container.setSessionTransacted(true);
        container.setConcurrency("2-8");

        return container;
    }
}
```

Trong ví dụ, container bắt đầu với hai listener invoker và có thể tăng tối đa tám khi tải tăng. Mỗi invoker có session và consumer được giữ lại. Local JMS transaction giúp rollback việc nhận message khi listener ném exception.

Cấu hình này giả định destination là queue. Nếu dùng topic, hãy xem xét semantics của subscription trước khi tăng concurrency.

## 7. Tương tác với CachingConnectionFactory

`DefaultMessageListenerContainer` có cơ chế cache resource riêng. Spring thường khuyến nghị để listener container quản lý cache theo lifecycle của nó.

`CachingConnectionFactory` cũng cache session, producer và consumer. Nếu bọc connection factory bằng lớp này rồi đồng thời bật cache consumer/session ở listener container, hai tầng có thể cùng giữ resource. Điều đó làm lifecycle và việc giải phóng resource khó dự đoán hơn.

Spring ghi nhận một số hạn chế khi dùng `CachingConnectionFactory` với listener container:

- Dừng rồi khởi động lại container chỉ hoạt động đúng với connection được cache độc lập bên trong container, không phải connection được cache bên ngoài.
- Khi dynamic scaling kết hợp với các provider hint như `maxMessagesPerTask`, cached consumer có thể tiếp tục nhận message dù không còn gắn với listener container hiện tại.
- Consumer cache và durable subscription có thể làm phức tạp việc đóng, đăng ký lại hoặc thay đổi subscription.

Nếu ứng dụng đã dùng `CachingConnectionFactory`, hãy kiểm tra kỹ thứ tự wrapper, cache level, stop/start và dynamic scaling bằng integration test với broker thật. Không thêm một tầng cache khác chỉ vì muốn tăng tốc; trước hết hãy xác định resource nào đang được tạo lại và tầng nào nên quản lý lifecycle đó.

## 8. Phân biệt DefaultMessageListenerContainer và SimpleMessageListenerContainer

Hai container tiêu chuẩn của Spring có cách quản lý listener khác nhau:

| Đặc điểm | `DefaultMessageListenerContainer` | `SimpleMessageListenerContainer` |
| --- | --- | --- |
| Cách nhận | Vòng lặp `MessageConsumer.receive()` | Đăng ký listener bằng `setMessageListener()` |
| Cache level | Có `CACHE_NONE` đến `CACHE_AUTO` | Không có thuộc tính cache level tương ứng |
| Dynamic concurrency | Có thể scale theo tải | Số consumer cố định khi khởi động |
| External transaction manager | Có hỗ trợ | Không hỗ trợ |
| Recovery | Có cơ chế recovery khi broker lỗi | Dựa nhiều hơn vào callback/recovery của provider |

Bài này tập trung vào `DefaultMessageListenerContainer`, vì các hằng số `CACHE_NONE`, `CACHE_CONNECTION`, `CACHE_SESSION`, `CACHE_CONSUMER` và `CACHE_AUTO` thuộc class này.

## 9. Ví dụ Java 17+: kiểm tra mức cache và CACHE_AUTO

Ví dụ sau xác nhận các giá trị cache và cách `CACHE_AUTO` được phân giải khi container khởi tạo. Nó dùng executor không thực thi task và connection factory giả để chỉ kiểm tra cấu hình. Không có listener thread hoặc kết nối broker nào được khởi chạy.

Tạo file `src/main/java/ListenerCacheLevelDemo.java`:

```java
import java.lang.reflect.Proxy;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.MessageListener;

import org.springframework.jms.listener.DefaultMessageListenerContainer;
import org.springframework.transaction.PlatformTransactionManager;

public class ListenerCacheLevelDemo {

    private static ConnectionFactory unusedConnectionFactory() {
        return (ConnectionFactory) Proxy.newProxyInstance(
                ConnectionFactory.class.getClassLoader(),
                new Class<?>[] { ConnectionFactory.class },
                (proxy, method, args) -> null);
    }

    private static PlatformTransactionManager transactionManagerMarker() {
        return (PlatformTransactionManager) Proxy.newProxyInstance(
                PlatformTransactionManager.class.getClassLoader(),
                new Class<?>[] { PlatformTransactionManager.class },
                (proxy, method, args) -> null);
    }

    private static DefaultMessageListenerContainer container(
            PlatformTransactionManager transactionManager) {

        DefaultMessageListenerContainer container =
                new DefaultMessageListenerContainer();

        container.setConnectionFactory(unusedConnectionFactory());
        container.setTaskExecutor(task -> { });
        container.setDestinationName("orders");
        container.setMessageListener((MessageListener) message -> { });

        if (transactionManager != null) {
            container.setTransactionManager(transactionManager);
        }

        return container;
    }

    private static void print(
            String label, DefaultMessageListenerContainer container) {
        System.out.println(label + " cacheLevel=" + container.getCacheLevel());
    }

    public static void main(String[] args) {
        // Không có external transaction manager.
        DefaultMessageListenerContainer local = container(null);
        print("local.beforeInitialize", local);
        local.initialize();
        print("local.afterInitialize", local);
        local.shutdown();

        // Có external transaction manager.
        DefaultMessageListenerContainer external =
                container(transactionManagerMarker());
        print("external.beforeInitialize", external);
        external.initialize();
        print("external.afterInitialize", external);
        external.shutdown();

        // Đặt mức cache tường minh bằng tên hằng số.
        DefaultMessageListenerContainer explicit = container(null);
        explicit.setCacheLevelName("CACHE_SESSION");
        print("explicit.CACHE_SESSION", explicit);
    }
}
```

Tạo `pom.xml` ở thư mục gốc:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>listener-cache-level-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jms</artifactId>
            <version>7.0.10</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>7.0.10</version>
        </dependency>
        <dependency>
            <groupId>jakarta.jms</groupId>
            <artifactId>jakarta.jms-api</artifactId>
            <version>3.1.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>ListenerCacheLevelDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Chạy từ thư mục chứa `pom.xml`:

```bash
mvn -q clean compile exec:java
```

Kết quả stdout:

```text
local.beforeInitialize cacheLevel=4
local.afterInitialize cacheLevel=3
external.beforeInitialize cacheLevel=4
external.afterInitialize cacheLevel=0
explicit.CACHE_SESSION cacheLevel=2
```

Ý nghĩa:

- Trước khi khởi tạo, cả hai container đều giữ giá trị cấu hình `CACHE_AUTO=4`.
- Container không có external transaction manager được phân giải thành `CACHE_CONSUMER=3`.
- Container có external transaction manager được phân giải thành `CACHE_NONE=0`.
- `setCacheLevelName("CACHE_SESSION")` đặt mức tường minh thành `2`.

Hai proxy trong ví dụ chỉ là marker để kiểm tra nhánh cấu hình. Executor không chạy task và connection factory không kết nối broker. Trong ứng dụng thực tế, hãy inject `ConnectionFactory` và transaction manager thật; không dùng executor rỗng.

## 10. Cách chọn mức cache trong thực tế

| Tình huống | Điểm bắt đầu |
| --- | --- |
| Local JMS transaction, listener nhận message liên tục | `CACHE_CONSUMER` hoặc `CACHE_AUTO` |
| External XA transaction, provider yêu cầu resource mới | `CACHE_NONE` hoặc `CACHE_AUTO` |
| External transaction nhưng provider cho phép giữ connection | Đánh giá `CACHE_CONNECTION` |
| External transaction cho phép giữ cả session | Đánh giá `CACHE_SESSION` sau khi kiểm tra XA enlistment |
| Provider tạo consumer rất tốn kém và không có ràng buộc XA | `CACHE_CONSUMER` |
| Cần kiểm tra hành vi tạo resource mới cho mỗi lần nhận | `CACHE_NONE` |

Không chọn mức cache chỉ dựa vào benchmark throughput. Cần kiểm tra thêm tính đúng đắn của transaction, khả năng phục hồi, subscription và giới hạn resource của broker.

## 11. Lỗi thường gặp

1. **Đọc `getCacheLevel()` trước khi initialize rồi nghĩ AUTO đã được phân giải.** Trước khởi tạo, giá trị vẫn có thể là `CACHE_AUTO`.
2. **Cho rằng `CACHE_NONE` chỉ bỏ cache consumer.** Nó không cache connection, session và consumer; mỗi lần nhận phải lấy resource mới.
3. **Dùng `CACHE_CONSUMER` với external XA mà không kiểm tra provider.** Một số application server yêu cầu connection/session mới để enlist transaction.
4. **Cho rằng `sessionTransacted=true` làm AUTO chuyển thành CACHE_NONE.** AUTO kiểm tra external transaction manager; local JMS transaction không tự làm thay đổi lựa chọn này.
5. **Dùng `CACHE_NONE` cho tải cao với non-durable subscription.** Việc liên tục tạo lại consumer có thể tạo khoảng trống nhận message.
6. **Tăng cache level mà không xem concurrency.** Mỗi invoker có thể giữ session và consumer, làm số resource tăng theo số listener đồng thời.
7. **Scale nhiều consumer trên topic như queue.** Nhiều subscription có thể khiến cùng publication được nhận nhiều lần trên cùng node.
8. **Chồng `CachingConnectionFactory` với cache của listener container mà không kiểm tra lifecycle.** Stop/start, dynamic scaling và consumer registration có thể gặp vấn đề.
9. **Dùng cache để thay thế transaction.** Cache chỉ tái sử dụng resource; acknowledgement, rollback, redelivery và idempotency vẫn cần cấu hình riêng.
10. **Không đo resource ở broker.** Getter của container cho biết mức cache được cấu hình, không cho biết broker đang có bao nhiêu session hoặc consumer active.

## 12. Checklist trước khi triển khai

- Xác định container đang dùng là `DefaultMessageListenerContainer`.
- Xác định có external transaction manager hay chỉ local JMS transaction.
- Kiểm tra provider/application server có yêu cầu resource mới cho XA enlistment không.
- Chọn mức cache rõ ràng hoặc dùng `CACHE_AUTO` khi mặc định theo transaction phù hợp.
- Tính số session và consumer theo concurrency tối thiểu/tối đa.
- Kiểm tra queue hay topic và durable hay non-durable subscription.
- Xem xét tác động của `CachingConnectionFactory` nếu đang bọc provider factory.
- Kiểm thử stop/start, broker recovery, dynamic scaling và transaction rollback.
- Theo dõi số connection/session/consumer active, thời gian tạo resource, throughput và lỗi enlistment.
- Giữ listener idempotent nếu hệ thống có thể redeliver message.

## 13. Tài liệu tham khảo

- [Spring Framework – DefaultMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html)
- [Spring Framework – Receiving a Message](https://docs.spring.io/spring-framework/reference/7.0/integration/jms/receiving.html)
- [Spring Framework – Using Spring JMS](https://docs.spring.io/spring-framework/reference/7.0/integration/jms/using.html)
- [Spring Framework – CachingConnectionFactory Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/connection/CachingConnectionFactory.html)
- [Spring Framework – AbstractPollingMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/listener/AbstractPollingMessageListenerContainer.html)
