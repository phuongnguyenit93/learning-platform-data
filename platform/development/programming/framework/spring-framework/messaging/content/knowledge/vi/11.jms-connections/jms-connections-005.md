# Phân biệt bộ nhớ đệm của Spring với pool của nhà cung cấp trong JMS

Khi một ứng dụng Spring gửi hoặc nhận message qua JMS, việc tạo `Connection`, `Session`, `MessageProducer` và `MessageConsumer` liên tục có thể tốn thời gian và tài nguyên trên broker. Hai cách thường dùng để tái sử dụng các tài nguyên này là:

- **Spring cache:** dùng `CachingConnectionFactory` để giữ một connection dùng chung và cache các session, producer, consumer theo chính sách của Spring.
- **Provider/resource pool:** dùng một connection factory có pool để cho nhiều caller mượn và trả connection/session, thường có giới hạn số lượng và chính sách chờ khi pool đầy.

Cả hai đều giúp giảm chi phí tạo tài nguyên JMS, nhưng chúng giải quyết bài toán ở hai tầng khác nhau. Cache của Spring tập trung vào tái sử dụng các handle JMS trong ứng dụng; pool tập trung vào quản lý số lượng connection/session được cấp phát đồng thời và vòng đời mượn-trả.

## 1. Các tài nguyên JMS cần phân biệt

Một client JMS thường làm việc với các tài nguyên sau:

| Tài nguyên | Vai trò | Chi phí khi tạo lại |
| --- | --- | --- |
| `Connection` | Kết nối client với JMS provider/broker | Có thể bao gồm socket, handshake, authentication và tài nguyên broker |
| `Session` | Ngữ cảnh tạo producer/consumer, gửi và nhận message, transaction/acknowledgement | Tạo lại thường tốn tài nguyên và có thể ảnh hưởng throughput |
| `MessageProducer` | Gửi message đến destination | Có thể chứa cấu hình delivery mode, destination và trạng thái gửi |
| `MessageConsumer` | Nhận message từ destination hoặc subscription | Có thể giữ đăng ký consumer, selector và trạng thái subscription |

Trong JMS, `Session` không được thiết kế để nhiều thread sử dụng đồng thời. Mỗi luồng xử lý nên dùng session riêng hoặc session được cấp riêng từ container/pool. Một connection có thể quản lý nhiều session, nhưng không nên dùng chung một session giữa các luồng cùng lúc.

`ConnectionFactory` là điểm tạo connection. Spring có thể bọc một provider `ConnectionFactory` bằng `CachingConnectionFactory`; một thư viện pool cũng có thể bọc provider factory và vẫn triển khai cùng interface JMS `ConnectionFactory`.

## 2. CachingConnectionFactory của Spring hoạt động thế nào?

`org.springframework.jms.connection.CachingConnectionFactory` kế thừa `SingleConnectionFactory`. Nó giữ một connection dùng chung đến provider và bổ sung cache cho:

- `Session`, phân loại theo acknowledgement/transaction mode.
- `MessageProducer`, theo session và destination.
- `MessageConsumer`, theo session, destination, selector và các thuộc tính liên quan.

Sơ đồ:

```text
JmsTemplate / Spring JMS client
             |
             v
  CachingConnectionFactory
   - one shared Connection
   - Session cache
   - Producer / Consumer cache
             |
             v
  Provider ConnectionFactory
             |
             v
          Broker
```

### Connection dùng chung

Vì kế thừa `SingleConnectionFactory`, Spring cache không tạo một connection vật lý riêng cho mỗi lần gọi `createConnection()`. Các caller nhận proxy dùng chung cho connection được quản lý bởi factory. Connection vật lý được giữ lại và tái sử dụng cho đến khi factory reset/destroy hoặc phải phục hồi sau lỗi.

Điều này giúp giảm số lần mở connection đến broker. Tuy nhiên, bản thân `CachingConnectionFactory` không phải pool nhiều connection để tăng số lượng connection vật lý cho nhiều caller.

### Session cache

Cấu hình quan trọng nhất là `setSessionCacheSize(int)`:

```java
CachingConnectionFactory cache =
        new CachingConnectionFactory(providerConnectionFactory);

cache.setSessionCacheSize(10);
```

Giá trị mặc định là `1` cho mỗi loại session acknowledgement mode. Các mode được cache riêng, ví dụ:

- `AUTO_ACKNOWLEDGE`
- `CLIENT_ACKNOWLEDGE`
- `DUPS_OK_ACKNOWLEDGE`
- Session transacted

Vì vậy, nếu ứng dụng sử dụng đủ bốn nhóm mode, tổng số session được cache có thể lên đến bốn lần `sessionCacheSize`. Giá trị này là giới hạn cache session được giữ lại sau khi caller đóng handle, không phải giới hạn số session đang hoạt động đồng thời. Nếu cache đã đủ chỗ, session trả về thêm sẽ được đóng thay vì giữ lại.

Khi caller gọi `Session.close()` trên proxy do Spring cung cấp, session thật có thể được trả về cache để tái sử dụng. Vì vậy, code dùng JMS API trực tiếp phải đóng session rõ ràng. Nếu không đóng, Spring không thể thu hồi session handle để tái sử dụng.

`JmsTemplate` quản lý vòng đời resource trong các thao tác gửi/nhận và đóng handle sau khi hoàn tất; khi dùng `CachingConnectionFactory`, các lệnh close được proxy chuyển thành thao tác trả tài nguyên về cache.

### Producer và consumer cache

Trong Spring Framework 7.0.10, các mặc định của `CachingConnectionFactory` là:

| Thuộc tính | Mặc định |
| --- | --- |
| `sessionCacheSize` | `1` cho mỗi acknowledgement mode |
| `cacheProducers` | `true` |
| `cacheConsumers` | `true` |
| `reconnectOnException` | `true` |

Có thể điều chỉnh:

```java
cache.setCacheProducers(true);
cache.setCacheConsumers(false);
```

Producer được cache theo destination và session. Consumer được cache theo destination, selector và các thuộc tính subscription liên quan. Producer/consumer của temporary queue và temporary topic không được cache.

Consumer caching cần được cân nhắc kỹ. Consumer lấy từ session đã cache có thể vẫn còn tồn tại vật lý sau khi code gọi close logic; chúng được đóng khi session tương ứng bị loại khỏi cache. Với durable subscriber, việc đóng session logic có thể đóng subscription; việc đăng ký lại durable consumer trên cùng cached session handle có những giới hạn. Nếu không cần consumer cache, có thể đặt `cacheConsumers=false`.

### Khi nào nên dùng Spring cache?

Phù hợp khi:

- Ứng dụng dùng `JmsTemplate` với một provider connection factory thông thường.
- Muốn giảm chi phí tạo connection/session/producer lặp lại.
- Số lượng connection vật lý không cần tăng theo số caller.
- Muốn dùng một cấu hình cache thống nhất ở tầng Spring.

## 3. Pool ở tầng provider hoặc thư viện pooling hoạt động thế nào?

Một connection pool quản lý tập hợp connection vật lý đến provider. Caller mượn connection khi cần, tạo hoặc mượn session, rồi trả các handle về pool khi gọi close. Pool tái sử dụng tài nguyên cho caller tiếp theo.

Một ví dụ phổ biến là **MessagingHub Pooled JMS**, thư viện cung cấp `JmsPoolConnectionFactory`. Nó bọc một provider `ConnectionFactory` và triển khai lại interface JMS `ConnectionFactory`.

Sơ đồ:

```text
JmsTemplate / JMS client
             |
             v
    JmsPoolConnectionFactory
       - Connection pool
       - Session pool per connection
       - Max/idle/timeout limits
             |
             v
  Provider ConnectionFactory
             |
             v
          Broker
```

### Connection pool

Các tùy chọn quan trọng của `JmsPoolConnectionFactory` gồm:

- `maxConnections`: số connection tối đa trong pool.
- `connectionIdleTimeout`: thời gian connection không được mượn có thể nằm idle trước khi bị loại bỏ.
- `connectionCheckInterval`: chu kỳ kiểm tra connection hết hạn nếu được bật.

Trong MessagingHub Pooled JMS, mặc định `maxConnections` là `1`. Muốn cho phép nhiều connection vật lý được mượn đồng thời, cần cấu hình số lớn hơn, ví dụ `8`.

### Session pool và backpressure

Pool còn giới hạn số session có thể được mượn trên mỗi connection:

- `maxSessionsPerConnection`: số session tối đa trên mỗi connection.
- `maxIdleSessionsPerConnection`: số session idle tối đa được giữ lại trên mỗi connection.
- `blockIfSessionPoolIsFull`: khi hết session, caller chờ hay nhận lỗi.
- `blockIfSessionPoolIsFullTimeout`: giới hạn thời gian chờ session khả dụng.

Với MessagingHub Pooled JMS 3.1.7, mặc định `maxSessionsPerConnection` là `500`; `blockIfSessionPoolIsFull` mặc định là `true`, và timeout mặc định là `-1` (chờ không giới hạn). Trong production, nên đặt timeout hữu hạn để pool cạn tài nguyên không giữ thread vô thời hạn.

Ví dụ cấu hình:

```java
import jakarta.jms.ConnectionFactory;
import org.messaginghub.pooled.jms.JmsPoolConnectionFactory;

JmsPoolConnectionFactory pool = new JmsPoolConnectionFactory();
pool.setConnectionFactory(providerConnectionFactory);
pool.setMaxConnections(8);
pool.setMaxSessionsPerConnection(20);
pool.setMaxIdleSessionsPerConnection(10);
pool.setConnectionIdleTimeout(30_000);
pool.setBlockIfSessionPoolIsFull(true);
pool.setBlockIfSessionPoolIsFullTimeout(2_000);
```

Các con số trên chỉ là ví dụ. Hãy chọn giới hạn theo concurrency của producer/consumer, giới hạn connection/session của broker và mức tài nguyên mà ứng dụng được phép sử dụng.

Khi caller đóng connection/session wrapper, pool trả tài nguyên về pool để caller khác mượn lại. Khi ứng dụng dừng, phải dừng/đóng pool để giải phóng các connection vật lý mà pool đang quản lý.

### Khi nào nên dùng provider pool?

Phù hợp khi:

- Ứng dụng có nhiều luồng hoặc nhiều client đồng thời cần connection/session riêng.
- Cần giới hạn số connection/session để bảo vệ broker.
- Muốn có backpressure rõ ràng khi tài nguyên đã được mượn hết.
- Provider hoặc thư viện pooling cung cấp chính sách idle timeout, eviction, health check và giới hạn resource.

## 4. So sánh trực tiếp

| Tiêu chí | Spring `CachingConnectionFactory` | Provider/resource pool |
| --- | --- | --- |
| Tầng quản lý | Spring Framework | Provider hoặc thư viện pool bọc provider factory |
| Connection vật lý | Một connection dùng chung | Một hoặc nhiều connection theo cấu hình |
| Session | Cache theo acknowledgement mode | Mượn/trả session trong pool của từng connection |
| Producer | Có thể cache theo session/destination | Tùy thư viện/provider; thường được quản lý theo session |
| Consumer | Có thể cache theo session và selector | Tùy thư viện/provider; cần kiểm tra lifecycle subscription |
| Giới hạn session | Giới hạn số session idle được giữ trong cache; session hoạt động vẫn có thể được tạo thêm | Có thể giới hạn số session được mượn trên mỗi connection |
| Khi hết chỗ | Session trả về cache vượt mức sẽ được đóng | Có thể block, timeout hoặc ném lỗi khi pool đầy |
| Mục tiêu chính | Giảm việc tạo lại resource trong Spring | Quản lý concurrency và tổng số resource được cấp phát |
| Cấu hình tiêu biểu | `sessionCacheSize`, `cacheProducers`, `cacheConsumers` | `maxConnections`, `maxSessionsPerConnection`, idle timeout, block timeout |

Một điểm dễ nhầm: `sessionCacheSize` của Spring là kích thước cache session được giữ lại sau khi đóng handle. Nó không tương đương với `maxSessionsPerConnection` của pool, vốn giới hạn số session được mượn/được tạo trên một connection.

## 5. Cấu hình Spring cache

Có thể đăng ký `CachingConnectionFactory` như một Spring bean:

```java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.connection.CachingConnectionFactory;

@Configuration
public class JmsCacheConfiguration {

    @Bean
    CachingConnectionFactory cachingConnectionFactory(
            ConnectionFactory providerConnectionFactory) {

        CachingConnectionFactory cache =
                new CachingConnectionFactory(providerConnectionFactory);

        cache.setSessionCacheSize(10);
        cache.setCacheProducers(true);

        // Tắt nếu không muốn giữ consumer handle trong session cache.
        cache.setCacheConsumers(false);

        return cache;
    }
}
```

Sau đó inject bean này vào `JmsTemplate` hoặc các thành phần Spring JMS cần dùng connection factory:

```java
@Bean
JmsTemplate jmsTemplate(CachingConnectionFactory cachingConnectionFactory) {
    return new JmsTemplate(cachingConnectionFactory);
}
```

Nếu dùng cache cho producer workload, `cacheProducers=true` giúp tái sử dụng producer theo session/destination. Nếu ứng dụng cần nhiều acknowledgement mode, hãy chọn `sessionCacheSize` dựa trên concurrency thực tế và số mode đang sử dụng.

Không giữ session hoặc producer proxy quá lâu sau khi đóng logical handle. Mục tiêu là để Spring nhận lại resource và có thể dùng lại cho thao tác tiếp theo.

## 6. Cấu hình pool ở tầng provider

Ví dụ dùng MessagingHub Pooled JMS. Provider connection factory được tạo từ cấu hình riêng của broker và inject vào bean pool:

```java
import jakarta.jms.ConnectionFactory;
import org.messaginghub.pooled.jms.JmsPoolConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class JmsPoolConfiguration {

    @Bean(destroyMethod = "stop")
    JmsPoolConnectionFactory pooledConnectionFactory(
            ConnectionFactory providerConnectionFactory) {

        JmsPoolConnectionFactory pool = new JmsPoolConnectionFactory();
        pool.setConnectionFactory(providerConnectionFactory);

        pool.setMaxConnections(8);
        pool.setMaxSessionsPerConnection(20);
        pool.setMaxIdleSessionsPerConnection(10);
        pool.setConnectionIdleTimeout(30_000);

        pool.setBlockIfSessionPoolIsFull(true);
        pool.setBlockIfSessionPoolIsFullTimeout(2_000);

        return pool;
    }
}
```

Inject pool vào `JmsTemplate` như một `ConnectionFactory` bình thường:

```java
@Bean
JmsTemplate jmsTemplate(JmsPoolConnectionFactory pooledConnectionFactory) {
    return new JmsTemplate(pooledConnectionFactory);
}
```

`destroyMethod = "stop"` bảo đảm pool được dừng khi Spring context đóng. Tên phương thức shutdown có thể khác ở thư viện pool khác; hãy dùng lifecycle API của implementation đang chọn.

## 7. Có nên bọc pool bằng CachingConnectionFactory không?

Không nên tự động chồng hai lớp này lên nhau. Cần hiểu thứ tự wrapper và tài nguyên nào đang được quản lý ở mỗi tầng.

Ví dụ:

```text
JmsTemplate
    |
    v
CachingConnectionFactory
    |
    v
JmsPoolConnectionFactory
    |
    v
Provider ConnectionFactory
```

Trong cấu trúc này, `CachingConnectionFactory` giữ một shared connection được mượn từ pool và giữ nó trong suốt vòng đời của cache. Các caller của Spring dùng chung connection đó. Pool bên dưới vì vậy không thể phân phối nhiều connection vật lý cho từng caller như khi được dùng trực tiếp; phần lớn lợi ích mở rộng connection của pool có thể bị che khuất. Spring cache cũng giữ session riêng, nên session pool phía dưới có thể không được tận dụng như dự kiến.

Đảo thứ tự wrapper cũng không tự tạo ra nhiều connection vật lý nếu lớp bên trong vẫn là `SingleConnectionFactory` dùng chung một connection. Hai lớp cache/pool còn có thể làm cho việc quan sát số resource đang active, idle hoặc được đóng trở nên khó hơn.

Chọn một chiến lược chính:

- Dùng `CachingConnectionFactory` khi muốn cache resource theo cách Spring quản lý và mô hình một connection dùng chung đáp ứng tải.
- Dùng provider/resource pool trực tiếp khi cần giới hạn và cấp phát nhiều connection/session đồng thời.
- Chỉ kết hợp hai lớp nếu đã kiểm tra rõ vòng đời `close()`, số connection thực tế, session cache ở từng tầng và hành vi khi reconnect.

## 8. Lưu ý với listener container và @JmsListener

`DefaultMessageListenerContainer` quản lý vòng đời connection, session và consumer của listener. Container có cơ chế cache level riêng, ví dụ cache connection, session hoặc consumer. Khi dùng listener container, thường nên để container tự quản lý cache theo lifecycle của nó.

Spring lưu ý rằng dùng `CachingConnectionFactory` cùng listener container có một số hạn chế:

- Dừng rồi khởi động lại listener container có thể gặp vấn đề nếu connection được cache bên ngoài container.
- Dynamic scaling và các provider hint có thể khiến message được chuyển đến consumer đã được cache nhưng không còn gắn với task hiện tại của container.
- Consumer caching có thể làm phức tạp việc đăng ký lại durable subscription.

Với `@JmsListener`, hãy cấu hình `DefaultJmsListenerContainerFactory` và các thuộc tính concurrency/cache/transaction phù hợp. Nếu listener container đã quản lý session và consumer cache, tránh thêm một lớp consumer cache bên ngoài khi chưa có lý do rõ ràng.

Ví dụ cấu hình listener container:

```java
@Bean
DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
        ConnectionFactory connectionFactory) {

    DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();

    factory.setConnectionFactory(connectionFactory);
    factory.setConcurrency("3-10");
    factory.setSessionTransacted(true);

    return factory;
}
```

`sessionTransacted=true` là một lựa chọn phổ biến khi cần rollback việc nhận message nếu listener xử lý thất bại. Caching và pooling chỉ tối ưu việc dùng resource; chúng không thay thế transaction, acknowledgement, redelivery hoặc idempotency.

## 9. Kiểm thử cấu hình bằng Java 17+

Ví dụ sau kiểm tra các giá trị cấu hình của Spring cache và MessagingHub pool. Nó không cần kết nối broker vì chỉ tạo hai wrapper và đọc các thuộc tính cấu hình; việc gửi/nhận message thật cần provider `ConnectionFactory` hợp lệ.

Tạo file `src/main/java/JmsResourceReuseDemo.java`:

```java
import org.messaginghub.pooled.jms.JmsPoolConnectionFactory;
import org.springframework.jms.connection.CachingConnectionFactory;

public class JmsResourceReuseDemo {

    public static void main(String[] args) {
        CachingConnectionFactory cache = new CachingConnectionFactory();

        System.out.println("spring.sessionCacheSize.default: "
                + cache.getSessionCacheSize());
        System.out.println("spring.cacheProducers.default: "
                + cache.isCacheProducers());
        System.out.println("spring.cacheConsumers.default: "
                + cache.isCacheConsumers());

        cache.setSessionCacheSize(10);
        cache.setCacheConsumers(false);

        System.out.println("spring.sessionCacheSize.configured: "
                + cache.getSessionCacheSize());
        System.out.println("spring.cacheConsumers.configured: "
                + cache.isCacheConsumers());

        JmsPoolConnectionFactory pool = new JmsPoolConnectionFactory();
        pool.setMaxConnections(8);
        pool.setMaxSessionsPerConnection(20);
        pool.setMaxIdleSessionsPerConnection(10);
        pool.setConnectionIdleTimeout(30_000);
        pool.setBlockIfSessionPoolIsFull(true);
        pool.setBlockIfSessionPoolIsFullTimeout(2_000);

        System.out.println("providerPool.maxConnections: "
                + pool.getMaxConnections());
        System.out.println("providerPool.maxSessionsPerConnection: "
                + pool.getMaxSessionsPerConnection());
        System.out.println("providerPool.maxIdleSessionsPerConnection: "
                + pool.getMaxIdleSessionsPerConnection());
        System.out.println("providerPool.connectionIdleTimeoutMs: "
                + pool.getConnectionIdleTimeout());
        System.out.println("providerPool.blockIfSessionPoolIsFull: "
                + pool.isBlockIfSessionPoolIsFull());
        System.out.println("providerPool.blockIfSessionPoolIsFullTimeoutMs: "
                + pool.getBlockIfSessionPoolIsFullTimeout());
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
    <artifactId>jms-resource-reuse-demo</artifactId>
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
            <groupId>org.messaginghub</groupId>
            <artifactId>pooled-jms</artifactId>
            <version>3.1.7</version>
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
                    <mainClass>JmsResourceReuseDemo</mainClass>
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
spring.sessionCacheSize.default: 1
spring.cacheProducers.default: true
spring.cacheConsumers.default: true
spring.sessionCacheSize.configured: 10
spring.cacheConsumers.configured: false
providerPool.maxConnections: 8
providerPool.maxSessionsPerConnection: 20
providerPool.maxIdleSessionsPerConnection: 10
providerPool.connectionIdleTimeoutMs: 30000
providerPool.blockIfSessionPoolIsFull: true
providerPool.blockIfSessionPoolIsFullTimeoutMs: 2000
```

Ví dụ xác nhận cấu hình wrapper và các giá trị mặc định. Để kiểm tra hiệu năng hoặc số connection vật lý được tạo, cần integration test với broker thật và đo connection/session active, idle, thời gian mượn resource cùng throughput.

## 10. Chọn giải pháp theo tình huống

| Tình huống | Lựa chọn gợi ý | Lý do |
| --- | --- | --- |
| Ứng dụng gửi message qua `JmsTemplate`, concurrency vừa phải | `CachingConnectionFactory` | Giảm chi phí tạo connection/session/producer |
| Nhiều producer/consumer đồng thời, cần nhiều connection vật lý | Provider/resource pool | Cho phép cấp phát nhiều connection theo giới hạn |
| Muốn bảo vệ broker khỏi quá nhiều session | Pool có `maxSessionsPerConnection` | Giới hạn số session được mượn |
| Listener dùng `DefaultMessageListenerContainer` | Container tự quản lý cache level | Resource lifecycle gắn với listener task/concurrency |
| Provider đã có pool chính thức | Dùng pool của provider nếu đáp ứng yêu cầu | Tránh tạo thêm tầng quản lý trùng lặp |
| Chỉ cần giảm việc tạo producer | Spring cache hoặc producer cache của pool | Chọn theo nơi đang quản lý session |

Không có một con số cache/pool đúng cho mọi ứng dụng. Hãy bắt đầu từ concurrency thực tế, số connection/session broker cho phép và cách container quản lý listener. Sau đó đo throughput, latency, số resource active/idle, thời gian chờ pool và tỷ lệ timeout.

## 11. Lỗi thường gặp

1. **Coi `CachingConnectionFactory` là pool nhiều connection.** Nó kế thừa `SingleConnectionFactory` và dùng một connection chia sẻ.
2. **Coi `sessionCacheSize` là giới hạn số session hoạt động.** Đây là giới hạn cache session giữ lại theo từng acknowledgement mode.
3. **Không đóng session khi dùng JMS API trực tiếp.** Session không được trả về cache nếu caller không đóng logical handle.
4. **Để `cacheConsumers=true` mà không xem xét durable subscription.** Consumer có thể còn tồn tại đến khi session bị loại khỏi cache.
5. **Cấu hình pool nhưng quên giới hạn số connection/session.** Pool không tự động bảo vệ broker nếu các giới hạn không được đặt đúng.
6. **Để pool block vô thời hạn.** Nếu session pool đầy, thread có thể chờ mãi; đặt timeout và xử lý tình huống hết resource.
7. **Bọc CachingConnectionFactory và pool theo thói quen.** Một lớp có thể giữ shared connection hoặc session lâu đến mức lớp kia không tận dụng được pool.
8. **Dùng consumer cache bên ngoài listener container mà không kiểm tra lifecycle.** Có thể gây vấn đề khi restart, scale hoặc đăng ký lại durable subscription.
9. **Cho rằng cache/pool cung cấp exactly-once delivery.** Chúng chỉ quản lý resource; transaction, acknowledgement, redelivery và idempotency vẫn cần thiết.
10. **Đo hiệu năng chỉ bằng số lần gọi createConnection.** Hãy đo connection vật lý, session active/idle, thời gian lấy resource, throughput và latency ở broker thật.

## 12. Checklist triển khai

- Xác định bottleneck là chi phí tạo resource hay thiếu capacity/concurrency.
- Xác định số connection vật lý cần thiết và giới hạn broker.
- Nếu dùng Spring cache, cấu hình `sessionCacheSize`, producer/consumer cache và đóng session đúng cách.
- Nếu dùng pool, đặt `maxConnections`, `maxSessionsPerConnection`, idle timeout và timeout khi pool đầy.
- Kiểm tra lifecycle của consumer, durable subscription và listener container.
- Tránh chồng nhiều lớp cache/pool nếu chưa đo và hiểu rõ vòng đời close/return.
- Dùng transaction/acknowledgement phù hợp; thiết kế consumer idempotent cho redelivery.
- Đo và theo dõi số resource active/idle, wait time, pool exhaustion và lỗi kết nối.
- Kiểm thử với đúng broker/provider sẽ dùng trong production.

## 13. Tài liệu tham khảo

- [Spring Framework – CachingConnectionFactory Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/connection/CachingConnectionFactory.html)
- [Spring Framework – Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html)
- [Spring Framework – DefaultMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html)
- [MessagingHub Pooled JMS – Configuration](https://github.com/messaginghub/pooled-jms/blob/main/pooled-jms-docs/Configuration.md)
- [MessagingHub Pooled JMS – JmsPoolConnectionFactory source](https://github.com/messaginghub/pooled-jms/blob/main/pooled-jms/src/main/java/org/messaginghub/pooled/jms/JmsPoolConnectionFactory.java)
