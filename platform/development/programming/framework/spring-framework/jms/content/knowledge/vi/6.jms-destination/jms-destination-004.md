# JndiDestinationResolver và tra cứu đối tượng quản trị

## Mục tiêu học tập

Khi tích hợp JMS với một application server, doanh nghiệp thường không muốn mã Java tự quyết định Queue hoặc Topic vật lý cho từng môi trường. Quản trị viên có thể công bố các tài nguyên JMS dưới **tên JNDI** ổn định, còn ứng dụng chỉ biết tên logic đó. Trong Spring JMS, `JndiDestinationResolver` là cầu nối giữa tên logic và đối tượng `jakarta.jms.Destination`.

Sau bài này, bạn có thể:

- Giải thích **JMS administered objects**, sự khác nhau giữa tên **JNDI**, tên Queue/Topic thực tế trên broker và địa chỉ kết nối.
- Hiểu khi nào `JndiDestinationResolver` tra cứu `Queue`/`Topic`, khi nào dùng cache, và cơ chế fallback sang dynamic destination.
- Cấu hình `JndiDestinationResolver` với `JmsTemplate` và `@JmsListener`; hiểu vì sao hai phía phải được cấu hình phù hợp.
- Dùng JNDI của application server (`java:comp/env/...`) hoặc JNDI client-side của Apache ActiveMQ Artemis để thực hành.
- Chẩn đoán lỗi thiếu binding, nhầm Queue/Topic, cache cũ, sai nhà cung cấp và lỗi kết nối broker mà không nhầm các nguyên nhân với nhau.

Bài dùng **Spring Framework 6.x / Spring Boot 3.5.x, Java 17+ và Jakarta Messaging 3.x**. Trong các phiên bản Spring/JMS đời cũ, API có thể nằm trong `javax.jms`; Java JNDI vẫn dùng package `javax.naming`, **kể cả khi JMS đã chuyển sang `jakarta.jms`**.

## 1. JNDI và JMS administered objects là gì?

### 1.1. JNDI không phải Queue broker

**JNDI** (*Java Naming and Directory Interface*) là cơ chế tra cứu tài nguyên Java từ một ngữ cảnh đặt tên (`Context`). Ứng dụng gọi `lookup("jms/Orders")` và nhận một đối tượng đã được đăng ký dưới tên đó. Trong JMS, các đối tượng thường được quản trị và cung cấp qua JNDI gồm:

| Loại administered object | Kiểu Java | Chức năng |
| --- | --- | --- |
| Connection factory | `jakarta.jms.ConnectionFactory` | Chứa cấu hình để tạo kết nối JMS tới provider/broker. |
| Queue | `jakarta.jms.Queue` | Biểu diễn đích point-to-point. |
| Topic | `jakarta.jms.Topic` | Biểu diễn đích publish/subscribe. |

**Không đánh đồng ba lớp tên:**

```text
Tên ứng dụng gửi:           "jms/Orders"
              |
              | JndiDestinationResolver
              v
JNDI lookup("jms/Orders") -> jakarta.jms.Queue
              |
              | JMS provider biết queueName
              v
Queue trên broker:          "orders.queue"
```

- `jms/Orders` là **tên binding trong JNDI** để ứng dụng tra cứu. Nó không bắt buộc trùng Queue vật lý.
- `orders.queue` là **tên Queue phía broker** mà đối tượng JMS trỏ đến trong cấu hình minh họa.
- `tcp://localhost:61616` là **địa chỉ kết nối tới broker**, không phải tên Destination.
- `ConnectionFactory` biết cách kết nối; `Destination` biểu diễn nơi gửi/nhận. Spring cần cả hai.

Ví dụ nếu một môi trường khác dùng Queue vật lý `orders.production`, quản trị viên có thể đổi binding của `jms/Orders` sang Queue mới mà code service vẫn gọi cùng tên. Việc đổi mapping thực tế có thể cần xóa cache hoặc khởi động lại ứng dụng, tùy provider và thiết lập resolver.

### 1.2. “Administered” nghĩa là ai quản lý?

Trong môi trường Jakarta EE hoặc ứng dụng có resource adapter, application server có thể tạo/công bố ConnectionFactory, Queue và Topic trong naming context. Mã nghiệp vụ không cần tự tạo từng đối tượng qua `session.createQueue(...)`.

Tuy nhiên **JNDI không nhất thiết là một JNDI server độc lập**. Apache ActiveMQ Artemis cung cấp một **client-side JNDI implementation**: dựa vào các property `queue.*` / `topic.*`, client tự khởi tạo đối tượng Java `Queue` / `Topic` cho lookup. **Artemis broker không chạy JNDI server và binding client-side không tự tạo một Queue vật lý trên broker.** Broker phải có address/queue phù hợp hoặc hỗ trợ auto-create theo policy.

Vì vậy hãy phân biệt:

1. **Administered object trong JNDI:** lớp cấu hình/đại diện phía client hoặc application server.
2. **Tài nguyên broker thực tế:** Queue, Topic/address, routing, quyền truy cập, persistence, dead-letter policy và các giới hạn.
3. **JMS connection/session:** tài nguyên runtime được tạo để gửi/nhận sau khi đã biết factory và destination.

Tra cứu JNDI thành công chứng minh binding tồn tại và trả đối tượng phù hợp; nó **chưa chứng minh broker đang online, user có quyền, Queue vật lý tồn tại hoặc message đã được xử lý**.

## 2. Spring chuyển tên destination thành đối tượng như thế nào?

Trong Spring JMS, `org.springframework.jms.support.destination.DestinationResolver` có phương thức trọng tâm:

```java
Destination resolveDestinationName(
        Session session,
        String destinationName,
        boolean pubSubDomain) throws JMSException;
```

Đây là chữ ký API để giải thích cơ chế, không phải chương trình Java độc lập. `destinationName` là chuỗi từ `JmsTemplate` hoặc listener container; `pubSubDomain=false` nghĩa là mong đợi Queue, `true` nghĩa là mong đợi Topic.

### 2.1. DynamicDestinationResolver — mặc định phổ biến

`DynamicDestinationResolver` là resolver mặc định của `JmsTemplate` khi không cấu hình khác. Nó sử dụng JMS `Session` để tạo đối tượng biểu diễn destination bằng tên được truyền vào: `session.createQueue(name)` hoặc `session.createTopic(name)`. Nó không bắt buộc phải tra JNDI.

Ví dụ:

```java
jmsTemplate.convertAndSend("orders.queue", "order-123");
```

Nếu template dùng resolver mặc định và `pubSubDomain=false`, chuỗi `orders.queue` sẽ được hiểu như tên Queue. **Việc gọi `createQueue` không bảo đảm broker tạo Queue vật lý**; kết quả phụ thuộc broker/provider.

### 2.2. JndiDestinationResolver — tra cứu đối tượng đã công bố

`org.springframework.jms.support.destination.JndiDestinationResolver` được dùng khi chuỗi của ứng dụng là **tên JNDI**, không phải tên Queue/Topic vật lý.

```java
JndiDestinationResolver resolver = new JndiDestinationResolver();
resolver.setCache(true);
resolver.setFallbackToDynamicDestination(false);

jmsTemplate.setDestinationResolver(resolver);
jmsTemplate.convertAndSend("jms/Orders", "order-123");
```

Đoạn này là **mã minh họa bên trong cấu hình Spring đã có biến `jmsTemplate` và một JNDI context**; không chạy độc lập. Khi gửi, Spring yêu cầu resolver tra `jms/Orders` và nhận một `Queue`, rồi dùng Queue ấy làm đích của producer.

Quy trình khái niệm:

```text
JmsTemplate.convertAndSend("jms/Orders", payload)
    |
    v
JndiDestinationResolver.resolveDestinationName(
        session, "jms/Orders", false)
    |
    +-- cache có binding? --> dùng đối tượng đã cache
    |
    +-- chưa có --> tra cứu JNDI "jms/Orders"
                         |
                         +-- tìm thấy Queue --> kiểm tra đúng kiểu --> cache --> trả Queue
                         |
                         +-- không tìm thấy --> fallback được bật?
                                                   |
                                                   +-- không: báo lỗi
                                                   +-- có: DynamicDestinationResolver
```

Trong quá trình tra cứu, resolver kiểm tra kiểu destination theo Queue/Topic mà bên gọi yêu cầu. Một tên JNDI trả về `Topic` nhưng template đang dùng Queue có thể dẫn đến lỗi **mismatch domain**, không nên sửa bằng cách đổi tên tùy tiện.

## 3. Các thiết lập quan trọng của JndiDestinationResolver

| Thiết lập | Giá trị mặc định ở Spring Framework 6.x | Ý nghĩa |
| --- | --- | --- |
| `setCache(true/false)` | `true` | Cache `Destination` đã lookup theo tên để tránh tra JNDI mỗi lần. |
| `setFallbackToDynamicDestination(true/false)` | `false` | Nếu lookup JNDI thất bại, có dùng resolver động để tạo đối tượng destination không? |
| `setResourceRef(true/false)` | `false` | Với resource reference của application server, bổ sung `java:comp/env/` cho tên tương đối khi cần. |
| `setJndiEnvironment(Properties)` | Không chỉ định môi trường riêng | Cấp các tham số `InitialContext` cho JNDI provider cụ thể. |
| `setJndiTemplate(JndiTemplate)` | Dùng hành vi JNDI thông thường | Tùy biến cách lookup hoặc dùng JNDI template đã được cấu hình. |
| `setDynamicDestinationResolver(...)` | `DynamicDestinationResolver` chuẩn | Thay chiến lược fallback khi bật fallback. |

### 3.1. Cache là cache đối tượng Destination, không phải cache message

Khi `cache=true`, lần lookup đầu tiên của `jms/Orders` lấy `Destination` từ JNDI và những lần sau thường dùng lại đối tượng đã lưu. Cache này **không chứa message, không đồng nghĩa cache connection/session và không bảo đảm broker Queue được duy trì**.

Nếu admin rebind tên `jms/Orders` sang một đối tượng Queue mới trong khi ứng dụng vẫn chạy, cache có thể giữ đối tượng cũ. Có thể dùng:

```java
resolver.removeFromCache("jms/Orders"); // Loại một binding.
resolver.clearCache();                  // Loại toàn bộ binding.
```

Hai lời gọi trên là **snippet thao tác vận hành** trên bean resolver đã tồn tại. Chỉ xóa cache khi có lý do; với thay đổi broker/routing quan trọng, test cả việc reconnect và dừng nhận trước khi thay vì giả định cache clear là đủ.

Có thể tắt cache bằng `setCache(false)` nếu cần re-lookup mỗi thao tác, nhưng tăng chi phí JNDI và phụ thuộc availability của naming provider. Với một số listener, lookup được thực hiện lúc container khởi động/tạo consumer; đổi cache không đảm bảo listener đang chạy tự chuyển sang destination mới ngay lập tức.

**Bẫy:** cache của `JndiDestinationResolver` dùng khóa theo **tên**, không tách độc lập Queue/Topic. Tránh dùng chung một tên JNDI cho cả Queue lẫn Topic khi bật cache.

### 3.2. Fallback mặc định là false — nên giữ nghiêm ngặt khi cần admin quản trị

`setFallbackToDynamicDestination(false)` khiến tên JNDI sai được phát hiện thay vì âm thầm tạo đối tượng theo chính chuỗi đó.

Giả sử code gọi sai `jms/Ordres` thay vì `jms/Orders`:

- **Fallback=false:** lookup thất bại; ứng dụng thấy lỗi cấu hình/binding.
- **Fallback=true:** resolver có thể gọi `session.createQueue("jms/Ordres")`. Tùy broker, nó có thể trỏ tới Queue sai hoặc được auto-create, khiến lỗi khó phát hiện.
- Fallback bật **không có nghĩa** provider cam kết Queue vật lý sẽ tự tạo hay message sẽ được giao tới đúng nghiệp vụ.

Khi hệ thống yêu cầu tài nguyên do admin chuẩn bị và có naming policy rõ ràng, cấu hình **fail fast theo thiết kế** sẽ giúp phát hiện typo, quyền và mapping sai.

### 3.3. Tên tài nguyên kiểu java:comp/env

Trong application server, tên được công bố có thể là:

```text
java:comp/env/jms/Orders
java:comp/env/jms/BillingTopic
```

Với `resolver.setResourceRef(true)`, gọi tên tương đối `jms/Orders` có thể được Spring chuẩn hóa thành `java:comp/env/jms/Orders`. Nếu chuỗi đã có scheme, ví dụ `java:comp/env/jms/Orders`, Spring không tự thêm prefix lần nữa. **Giá trị mặc định của `resourceRef` là `false`**, phù hợp khi nhà cung cấp JNDI không sử dụng namespace này.

Không tự đổi mọi deployment thành `resourceRef=true`: Artemis client-side JNDI trong ví dụ bên dưới dùng alias `jms/Orders`, không dùng naming context `java:comp/env/`.

## 4. Ví dụ đầy đủ: tra cứu Queue bằng JNDI trong Spring Boot

Ví dụ này dùng **Java 17+, Spring Boot 3.5.8, Artemis Jakarta JMS client**. Mục đích là kiểm chứng rằng mã publisher và consumer đều dùng tên JNDI `jms/Orders` trong khi Queue thực tế được cấu hình là `orders.queue`.

### 4.1. Điều kiện để chạy

- Có Java 17+ và Maven.
- Có Apache ActiveMQ Artemis broker sẵn sàng tại `tcp://localhost:61616` hoặc một endpoint tương ứng.
- Có tài khoản JMS được phép gửi/nhận. Cung cấp `JMS_USERNAME` và `JMS_PASSWORD` qua environment; không viết secret vào source.
- Broker có Queue `orders.queue`, hoặc đã bật auto-create phù hợp. **`jndi.properties` chỉ cấu hình đối tượng Queue phía client**, không thay thế việc cấu hình broker.
- Không chạy đồng thời nhiều ứng dụng khác tranh nhận cùng Queue nếu muốn dễ đối chiếu log trong thực hành.

**`pom.xml`**

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
    <artifactId>jndi-destination-demo</artifactId>
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

`spring-boot-starter-artemis` mang `spring-jms` và Artemis Jakarta client theo dependency management phù hợp Spring Boot. Vì ví dụ khởi tạo connection factory gốc bằng code, không cần đặt `spring.artemis.*` đồng thời; các cấu hình riêng của ví dụ dùng namespace `app.jms.*` để tránh hiểu nhầm rằng Spring Boot sẽ tự áp dụng chúng.

### 4.2. Khai báo binding JNDI

**`src/main/resources/jndi.properties`**

```properties
java.naming.factory.initial=org.apache.activemq.artemis.jndi.ActiveMQInitialContextFactory

# Phần sau "queue." là tên JNDI; giá trị bên phải là Queue trên broker:
queue.jms/Orders=orders.queue

# Ví dụ thêm Topic để thấy cách đặt tên; bài chạy chỉ dùng Queue:
topic.jms/OrderEvents=orders.events
```

Artemis cung cấp `ActiveMQInitialContextFactory` trong client JNDI. Khi `InitialContext` được tạo, nó tìm cấu hình JNDI trên classpath, đăng ký alias `jms/Orders` để lookup ra một JMS `Queue` trỏ tới `orders.queue`. Đối với Topic, `topic.jms/OrderEvents=orders.events` là mapping độc lập.

**Quan trọng về phiên bản:** mã Java dùng `jakarta.jms.*`, nên phải dùng Artemis **Jakarta client** tương thích (starter Boot ở trên đã quản lý phụ thuộc). Đừng trộn artifact JMS `javax.jms` cũ với kiểu `jakarta.jms.Queue` và mong việc cast thành công.

**`src/main/resources/application.properties`**

```properties
app.jms.broker-url=${JMS_BROKER_URL:tcp://localhost:61616}
app.jms.username=${JMS_USERNAME}
app.jms.password=${JMS_PASSWORD}
```

File này tạo ba property do **ứng dụng** định nghĩa để cấp thông tin cho provider connection factory. Bạn phải truyền username/password hợp lệ trước khi khởi động; placeholder không có default để tránh tự sử dụng credentials nhầm môi trường.

### 4.3. Kết nối một JndiDestinationResolver tới cả sender và listener

**`src/main/java/example/jndi/JmsConfiguration.java`**

```java
package example.jndi;

import jakarta.jms.ConnectionFactory;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.destination.JndiDestinationResolver;

@Configuration(proxyBeanMethods = false)
@EnableJms
public class JmsConfiguration {

    @Bean(destroyMethod = "close")
    ActiveMQConnectionFactory connectionFactory(
            @Value("${app.jms.broker-url}") String url,
            @Value("${app.jms.username}") String username,
            @Value("${app.jms.password}") String password) {

        return new ActiveMQConnectionFactory(url, username, password);
    }

    @Bean
    JndiDestinationResolver jndiDestinationResolver() {
        var resolver = new JndiDestinationResolver();
        resolver.setResourceRef(false); // JNDI client-side alias; không thêm java:comp/env/
        resolver.setCache(true);
        resolver.setFallbackToDynamicDestination(false);
        return resolver;
    }

    @Bean
    JmsTemplate jmsTemplate(ConnectionFactory connectionFactory,
                            JndiDestinationResolver resolver) {
        var template = new JmsTemplate(connectionFactory);
        template.setDestinationResolver(resolver);
        template.setPubSubDomain(false); // Mong đợi Queue.
        return template;
    }

    @Bean(name = "jmsListenerContainerFactory")
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory,
            JndiDestinationResolver resolver) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setDestinationResolver(resolver);
        factory.setPubSubDomain(false);
        factory.setSessionTransacted(true);
        factory.setConcurrency("1-2");
        return factory;
    }
}
```

**Giải thích chi tiết:**

1. `connectionFactory()` tạo Artemis implementation dùng địa chỉ broker và credentials. Spring quản lý bean này và gọi `close()` khi application context dừng. Việc tạo bean chưa đảm bảo đã mở một connection TCP.
2. `jndiDestinationResolver()` khởi tạo resolver singleton. Vì `jndi.properties` có trên classpath, JNDI provider được tìm bằng `InitialContext` mặc định; không cần truyền thủ công `Properties` vào bean trong ví dụ này.
3. `setResourceRef(false)` giữ nguyên alias `jms/Orders`; **không** ghép `java:comp/env/`.
4. `setFallbackToDynamicDestination(false)` buộc phải có alias JNDI đúng. Nếu thiếu `queue.jms/Orders`, lỗi được bộc lộ khi resolve.
5. `JmsTemplate` sẽ dịch tên `"jms/Orders"` qua resolver. Nếu quên `template.setDestinationResolver(resolver)`, template mặc định giải tên theo cơ chế dynamic và có thể nhắm sai Queue.
6. **Listener không kế thừa resolver từ JmsTemplate.** Vì `@JmsListener` sử dụng listener container riêng, cần `factory.setDestinationResolver(resolver)`. Nếu quên, listener có thể coi `"jms/Orders"` là tên Queue broker thay vì lookup JNDI.
7. `@EnableJms` bật infrastructure `@JmsListener`. Bean có tên `jmsListenerContainerFactory` được tìm theo convention khi endpoint không khai báo `containerFactory`.
8. `setSessionTransacted(true)` tạo local JMS transaction ở phía consumer. Nếu listener xử lý thành công, container commit; nếu exception thoát ra ngoài, container rollback và broker có thể redeliver. Transaction JMS **không tự atomic** với transaction database.
9. `setConcurrency("1-2")` minh họa một đến hai consumer, nên message processing có thể chạy song song. Dự án đòi hỏi thứ tự xử lý nghiêm ngặt có thể chọn concurrency bằng 1 hoặc áp dụng partition/grouping theo business key.

Trong Spring Boot, việc bạn tự tạo bean `ConnectionFactory` hoặc `JmsTemplate` có thể làm phần auto-configuration tương ứng **back off**. Đó là hành vi thông thường để tránh sinh bean trùng; đừng tạo thêm factory/template cùng vai trò nếu chưa xác định rõ bean nào sẽ được inject.

### 4.4. Publisher và consumer dùng tên JNDI

**`src/main/java/example/jndi/JndiOrderApplication.java`**

```java
package example.jndi;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class JndiOrderApplication {

    private static final String ORDER_DESTINATION = "jms/Orders";

    public static void main(String[] args) {
        SpringApplication.run(JndiOrderApplication.class, args);
    }

    @Bean
    ApplicationRunner samplePublisher(JmsTemplate template) {
        return args -> {
            template.convertAndSend(ORDER_DESTINATION, "order-001");
            System.out.println("sent=order-001");
        };
    }

    @Component
    static class OrderReceiver {
        @JmsListener(destination = ORDER_DESTINATION)
        public void receive(String body) {
            System.out.println("received=" + body);
        }
    }
}
```

`@SpringBootApplication` đặt ở package `example.jndi` để Spring quét được cả `JmsConfiguration` và `OrderReceiver`. `ApplicationRunner` gửi một message sau khi context đã được khởi tạo. Listener dùng cùng tên JNDI logic. Producer và consumer không cần hardcode `orders.queue` trong Java.

**Luồng xử lý mong đợi:**

```text
ApplicationRunner
   -> JmsTemplate.convertAndSend("jms/Orders", "order-001")
       -> JndiDestinationResolver
          -> JNDI lookup("jms/Orders")
          -> Queue trỏ đến "orders.queue"
       -> JMS producer gửi tới broker
   -> in "sent=order-001"

@JmsListener(destination="jms/Orders")
   -> DefaultJmsListenerContainerFactory
      -> cùng JndiDestinationResolver
      -> Queue trỏ đến "orders.queue"
   -> nhận TextMessage từ broker
   -> in "received=order-001"
```

Lưu ý: **JNDI alias được giải quyết phía client trước khi JMS gửi/nhận**. Sau bước resolve, broker nhìn thấy routing/destination theo implementation JMS, không nhất thiết có khái niệm tên JNDI `jms/Orders`.

### 4.5. Lệnh chạy và stdout

Ví dụ sử dụng PowerShell (Windows):

```powershell
$env:JMS_BROKER_URL = "tcp://localhost:61616"
$env:JMS_USERNAME = "dev-user"
$env:JMS_PASSWORD = "dev-password"

mvn spring-boot:run
```

Thay `dev-user` / `dev-password` bằng tài khoản mà broker thực tế cung cấp. Trên shell POSIX:

```bash
JMS_BROKER_URL=tcp://localhost:61616 \
JMS_USERNAME=dev-user \
JMS_PASSWORD=dev-password \
mvn spring-boot:run
```

Nếu broker hoạt động, có quyền với Queue và không có consumer khác nhận message trước, trong log sẽ thấy **hai dòng do ứng dụng chủ động in**:

```text
sent=order-001
received=order-001
```

Thứ tự hai dòng **không cố định**, vì listener xử lý trên thread khác và có thể nhận message trước khi publisher in xong. Ứng dụng còn có log khởi động Spring/JMS. Mỗi lần khởi động lại, `ApplicationRunner` tạo thêm một message cùng payload `order-001`; đó là message mới, không phải bằng chứng broker redeliver. Nếu một process khác cùng nhận Queue, dòng `received=...` có thể xuất hiện ở process đó thay vì tại ứng dụng này.

**Nếu không có broker:** code có thể biên dịch nhưng gửi/nhận không thành công; đây là integration example, cần broker thực tế. Không khẳng định một lần gọi `convertAndSend` thành công đảm bảo xử lý nghiệp vụ đúng một lần trong mọi lỗi mạng/transaction.

## 5. Tra cứu JNDI trực tiếp: đối chiếu với resolver

Khi cần kiểm tra wiring, có thể sử dụng API Java JNDI nguyên bản:

```java
import javax.naming.Context;
import javax.naming.InitialContext;
import javax.naming.NamingException;
import jakarta.jms.Queue;

public final class JndiQueueProbe {
    public static void main(String[] args) throws NamingException {
        Context context = new InitialContext();
        try {
            Queue queue = (Queue) context.lookup("jms/Orders");
            System.out.println("queue=" + queue.getQueueName());
        } catch (jakarta.jms.JMSException ex) {
            throw new IllegalStateException("Cannot read JMS queue name", ex);
        } finally {
            context.close();
        }
    }
}
```

Đây là **class Java độc lập về logic** nhưng cần đúng `jakarta.jms-api`, Artemis Jakarta client và `jndi.properties` trên runtime classpath; không thể chỉ dùng JDK trống để chạy. Bạn có thể đặt class vào cùng Maven project của mục 4, nhưng nó không phải `main` mặc định của Spring Boot. Với cấu hình `queue.jms/Orders=orders.queue`, output kỳ vọng (khi provider JNDI trả đúng kiểu Queue):

```text
queue=orders.queue
```

Ở mức Spring, `JndiTemplate` thay thế một phần boilerplate của `InitialContext`:

```java
import jakarta.jms.Queue;
import org.springframework.jndi.JndiTemplate;

// Ví dụ bên trong một bean/service đã có JndiTemplate.
Queue queue = jndiTemplate.lookup("jms/Orders", Queue.class);
String actualQueueName = queue.getQueueName();
```

Đoạn này là **snippet**, cần xử lý `NamingException` và `JMSException` theo chữ ký method thực tế. `JndiTemplate` là helper tổng quát cho mọi loại đối tượng JNDI. `JndiDestinationResolver` chuyên nhận chuỗi destination name theo hợp đồng của **Spring JMS** và trả `Destination` phù hợp, nên là lựa chọn tự nhiên cho `JmsTemplate` và listener container.

### 5.1. Tra cứu ConnectionFactory như administered object

Không chỉ Destination, application server cũng có thể công bố `ConnectionFactory`, ví dụ:

```text
java:comp/env/jms/ConnectionFactory
```

Khi đó cấu hình Spring có thể tra cứu factory thay vì tự new class provider:

```java
@Bean
jakarta.jms.ConnectionFactory connectionFactory(
        org.springframework.jndi.JndiTemplate jndi) throws javax.naming.NamingException {

    return jndi.lookup(
            "java:comp/env/jms/ConnectionFactory",
            jakarta.jms.ConnectionFactory.class);
}
```

Đây là **snippet thay thế** cho `connectionFactory()` trong mục 4, không được thêm đồng thời cả hai bean trùng tên. Khi application server cung cấp factory, hãy để **container sở hữu lifecycle của tài nguyên do nó quản lý**; không mặc định gọi `close()` trên singleton factory lookup. Các connection/session do application code tự tạo vẫn cần giải phóng theo API/quy ước tương ứng.

Cần tách hai việc: **lookup ConnectionFactory** là một cấu hình cấp kết nối; **lookup Destination bằng `JndiDestinationResolver`** là cấu hình tên điểm gửi/nhận. Ứng dụng có thể dùng JNDI cho một trong hai hoặc cả hai.

## 6. Cấu hình trong Jakarta EE / application server

Phần lớn hệ thống triển khai Spring vào application server không tạo một `ActiveMQInitialContextFactory` client-side như ví dụ Artemis. Thay vào đó, server đưa các resource vào **environment naming context (ENC)** của ứng dụng, ví dụ `java:comp/env/jms/Orders`, `java:comp/env/jms/ConnectionFactory`.

**Ví dụ JavaConfig dành cho môi trường đó (thay thế cấu hình JNDI mục 4):**

```java
@Bean
org.springframework.jms.support.destination.JndiDestinationResolver destinationResolver() {
    var resolver =
            new org.springframework.jms.support.destination.JndiDestinationResolver();
    resolver.setResourceRef(true);
    resolver.setCache(true);
    resolver.setFallbackToDynamicDestination(false);
    return resolver;
}
```

Khi service gọi `"jms/Orders"`, Spring có thể tra `java:comp/env/jms/Orders`. Đối tượng thực tế do server cấp phát và ánh xạ; file resource binding, quyền và tên phụ thuộc WildFly/Payara/TomEE hoặc container đang dùng. Một resource reference có tên tương đối `jms/Orders` trong ứng dụng thường được server map tới tài nguyên JMS mà admin đã provision.

Nếu tổ chức dùng **JNDI provider từ xa**, cấu hình `InitialContext` thường cần property provider-specific như factory class, provider URL và phương thức xác thực JNDI (khác với xác thực JMS broker):

```java
Properties env = new Properties();
env.put(javax.naming.Context.INITIAL_CONTEXT_FACTORY,
        "com.example.naming.CustomInitialContextFactory");
env.put(javax.naming.Context.PROVIDER_URL, "iiop://naming.example:2809");

JndiDestinationResolver resolver = new JndiDestinationResolver();
resolver.setJndiEnvironment(env);
resolver.setResourceRef(false);
```

Đây là **pseudo-configuration minh họa**, `com.example...` không phải provider có thật và không phải chương trình chạy độc lập. Phải thay factory class, URL, bảo mật bằng tham số chính thức của môi trường của bạn; không copy các placeholder đó vào production. Không đưa JNDI credentials bí mật vào source, đặc biệt khi naming service nằm trên mạng.

## 7. Queue và Topic: tên JNDI không quyết định mô hình message

Giả sử có hai binding:

```properties
queue.jms/Orders=orders.queue
topic.jms/OrderEvents=orders.events
```

Ở client:

- `jms/Orders` được lookup thành `jakarta.jms.Queue`.
- `jms/OrderEvents` được lookup thành `jakarta.jms.Topic`.

Với `JmsTemplate` được cấu hình `setPubSubDomain(false)`, ta gửi vào Queue bằng:

```java
queueTemplate.convertAndSend("jms/Orders", "order-created");
```

Để gửi tới Topic, cần template/endpoint phù hợp `pubSubDomain=true`:

```java
JmsTemplate topicTemplate = new JmsTemplate(connectionFactory);
topicTemplate.setDestinationResolver(jndiDestinationResolver);
topicTemplate.setPubSubDomain(true);
topicTemplate.convertAndSend("jms/OrderEvents", "order-created");
```

Hai đoạn là **snippet trong code đã có các bean tương ứng**, không phải file độc lập. Đừng tạo một singleton `JmsTemplate` rồi liên tục chuyển `pubSubDomain` theo request của các thread khác. Hãy đăng ký **hai bean được cấu hình cố định** khi cần cả Queue và Topic.

Nếu một template đang yêu cầu Queue mà JNDI trả Topic, `JndiDestinationResolver` sẽ kiểm tra sự phù hợp kiểu destination và có thể báo lỗi. Bật `fallbackToDynamicDestination` không phải cách sửa mapping kiểu này: phải khai báo đúng binding và domain của client.

Đối với `@JmsListener` cần cấu hình listener container riêng nếu lắng nghe Topic, và chọn subscription mode (durable/non-durable/shared) theo nghiệp vụ. Chỉ đổi một tên JNDI không tự quyết định semantics của việc broadcast đến nhiều subscriber.

## 8. Vì sao JndiDestinationResolver hữu ích?

Không phải mọi ứng dụng JMS đều cần JNDI. Khi dùng nhiều môi trường hoặc application server, JNDI giúp **tách tên logic trong code khỏi cấu hình provider**.

| Tiêu chí | `DynamicDestinationResolver` | `JndiDestinationResolver` |
| --- | --- | --- |
| Đầu vào `"orders.queue"` | Được hiểu là tên destination provider theo Queue/Topic hiện tại | Được hiểu là tên JNDI cần lookup |
| Phụ thuộc JNDI registry | Không | Có |
| Quản trị mapping bên ngoài code | Thường qua cấu hình string hoặc convention của app | Qua binding JNDI do provider/server/admin quản lý |
| Không tìm thấy tên | Provider có thể tạo destination object; broker policy quyết định hành vi thực tế | Mặc định lỗi lookup; có thể bật fallback |
| Caching resolved Destination | Không có cơ chế cache JNDI tương tự | Có; mặc định `cache=true` |
| Phù hợp | Ứng dụng nhỏ, tên Queue được cấu hình trực tiếp | Jakarta EE, môi trường nhiều profile, tài nguyên JMS do admin cung cấp |

**Tình huống thực tế:** Một service order cần gửi thông điệp đến Queue của đối tác. Trong test, JNDI binding `jms/Orders` trỏ tới `integration-test.orders`; trong production, nó trỏ tới `partner.orders.production`. Service vẫn gọi `jmsTemplate.convertAndSend("jms/Orders", order)`. Việc chuyển môi trường nằm ở cấu hình naming/broker và release process, không bắt service thay string hoặc biên dịch lại.

**Giới hạn:** Nếu code phụ thuộc một naming provider cụ thể, cách cấu hình context và quyền truy cập JNDI vẫn có thể khác nhau giữa các môi trường. JNDI không xóa hoàn toàn phụ thuộc vendor; nó cho một interface lookup thống nhất để cô lập phần đó.

## 9. Cache, reconnect và thay đổi binding trong môi trường chạy thật

Một luồng xử lý cần phân biệt **ba loại cache/vòng đời**:

1. **Destination cache:** `JndiDestinationResolver` giữ đối tượng `Destination` theo JNDI alias.
2. **JMS connection/session cache hoặc pool:** do `CachingConnectionFactory`, provider pool hoặc application server điều khiển. Đây là tài nguyên network/transaction, **khác Destination cache**.
3. **Listener container lifecycle:** listener khởi tạo consumer, recover connection và có thể lookup lại destination khi restart. Nó không tự đồng bộ mọi thay đổi JNDI theo thời gian thực.

Vì vậy, khi admin rebind `jms/Orders`:
- Cần quyết định **khi nào** producer/consumer được phép chuyển sang Queue mới để không mất message đang xử lý.
- Tắt cache hoặc `clearCache()` có thể giúp lần lookup sau lấy binding mới, nhưng **listener hiện hữu** có thể vẫn giữ consumer với destination cũ tới khi container tái tạo nó.
- Nếu Queue cũ/broker cũ còn message, cần kế hoạch drain/retire; đổi binding không di chuyển message đã tồn tại từ broker này sang broker khác.
- Mất broker không có nghĩa JNDI alias sai. Một `Queue` lookup được vẫn có thể không dùng được vì network, thiếu permission hoặc broker đã gỡ Queue.

Không tự xóa cache trong mọi lần gửi để “đảm bảo cập nhật”: điều đó triệt tiêu lợi ích cache, làm mỗi request phụ thuộc vào naming provider và có thể tăng độ trễ.

## 10. Lỗi phổ biến và cách chẩn đoán

| Biểu hiện | Khả năng cao | Cách xác minh / sửa |
| --- | --- | --- |
| `NoInitialContextException` hoặc không có initial factory | Thiếu `jndi.properties` hoặc cấu hình `java.naming.factory.initial` | Kiểm tra resource trên runtime classpath, tên class và dependency provider. |
| `ClassNotFoundException` của Artemis JNDI factory | Thiếu Artemis client hoặc trộn Jakarta/JMS cũ | Dùng đúng Jakarta client/BOM, xem dependency tree. |
| `NameNotFoundException` khi lookup `jms/Orders` | Không có alias JNDI, sai namespace hoặc resourceRef | Đọc cấu hình binding chính xác, phân biệt `jms/Orders` với `java:comp/env/jms/Orders`. |
| Lookup ra sai type | Bind Topic nhưng service mong Queue (hoặc ngược lại) | Kiểm tra type `Queue`/`Topic` và `pubSubDomain`. |
| Publisher gửi thành công nhưng listener không nhận | Hai phía dùng resolver khác nhau, Queue khác, consumer khác đang tranh nhận | Kiểm tra cả `JmsTemplate` lẫn `jmsListenerContainerFactory`; xem Queue thực tế và broker metrics. |
| `JNDI lookup` thành công nhưng gửi thất bại | Broker offline, sai URL, xác thực/quyền, thiếu Queue vật lý | Test broker và quyền gửi/nhận độc lập với việc lookup JNDI. |
| Message đi vào Queue tên `jms/Orders` thay vì `orders.queue` | Dùng resolver mặc định dynamic hoặc bật fallback che lỗi | Gắn đúng `JndiDestinationResolver`, tắt fallback và kiểm tra binding. |
| Vừa đổi JNDI alias nhưng app vẫn dùng Queue cũ | Destination cache / listener đang giữ consumer cũ | Dùng `removeFromCache` / `clearCache` hợp lý; lên lịch restart/rebind listener theo vận hành. |
| `javax.jms.Queue` không cast được thành `jakarta.jms.Queue` | Lệch major JMS API/provider | Đồng bộ Spring Framework 6.x với Jakarta JMS 3.x/Artemis Jakarta client. |
| Listener báo retry liên tục khi startup | JNDI resolution hoặc broker không sẵn sàng | Kiểm tra exception gốc, logging listener container, tên Queue, kết nối và quyền. |
| Khi bật fallback thì “hết lỗi” nhưng message mất | Fallback tạo đối tượng trỏ tới tên mới ngoài dự kiến | Khôi phục binding chuẩn; kiểm tra queue address/routing thực tế, DLQ và policy auto-create. |

### Quy trình chẩn đoán có thứ tự

1. **Kiểm tra tên:** code dùng `jms/Orders` hay `orders.queue`? Quyết định đây là tên JNDI hay tên Queue broker.
2. **Tra cứu độc lập:** với đúng JNDI provider, gọi `InitialContext.lookup("jms/Orders")`; xác định class thực tế của object và `Queue.getQueueName()`.
3. **Kiểm tra domain:** nếu mong Queue, object phải là `Queue` và phía template/listener đặt `pubSubDomain=false`.
4. **Kiểm tra wiring:** cả sender và consumer có thực sự dùng cùng `JndiDestinationResolver` hoặc đúng các resolver tương ứng không?
5. **Kiểm tra broker:** kết nối, address/queue tồn tại, quyền send/consume, routing, backlog, consumer count và in-flight messages.
6. **Kiểm tra cache và lifecycle:** nếu binding mới thay đổi, quan sát resolver cache, listener restart và policy rollout.
7. **Kiểm tra transaction:** với listener transacted, message có thể redeliver khi callback ném lỗi. Đừng coi log xử lý hai lần là bằng chứng có hai Queue.
8. **Kiểm tra phân tách môi trường:** test và production có thể dùng cùng alias nhưng mapping tới Queue khác; nhìn vào mapping được triển khai thực tế trước khi gửi lại message.

## 11. Lưu ý về bảo mật, testing và vận hành

### Không coi JNDI là một cơ chế bảo mật

Tên JNDI có thể trừu tượng hóa tài nguyên, nhưng quyền thật nằm ở **naming provider** và **JMS broker/application server**. Người dùng có quyền lookup Queue chưa chắc có quyền gửi hoặc nhận. Ngược lại, một alias sai có thể làm message đi tới đích không mong muốn khi bật fallback.

- Đừng nhúng JNDI/JMS passwords vào source, file commit hoặc log. Dùng secret store/environment/server resource binding.
- Nếu JNDI provider ở xa, xác thực, bảo mật kết nối/TLS và chính sách tin cậy classloading phải tuân theo hướng dẫn provider; tránh kết nối naming server không tin cậy.
- Phân quyền gửi/nhận và quyền quản trị Queue theo từng service; kiểm thử các lỗi permission với account giống production.
- Dùng tên JNDI riêng, dễ audit cho Queue/Topic, không dùng chung một tên cho hai loại destination nếu bật cache.
- Đo latency lookup, cache hit, lỗi naming, broker availability, pending/in-flight, redelivery và DLQ tách biệt để không chẩn đoán sai tầng.

### Một bộ kiểm thử thực tế

| Bài test | Kỳ vọng |
| --- | --- |
| Lookup binding hợp lệ `jms/Orders` | Trả đúng `Queue`, `getQueueName()` khớp Queue đã cấu hình. |
| Lookup sai `jms/Orderz`, fallback tắt | Báo lỗi resolution, không âm thầm tạo Queue mới. |
| Bind `jms/Orders` thành `Topic` nhưng caller yêu cầu Queue | Phát hiện type mismatch. |
| Gửi qua template và nhận qua listener cùng resolver | Message đi tới Queue thực tế, listener xử lý được khi broker/permissions đúng. |
| Chỉ cấu hình resolver ở template | Kiểm tra listener bị resolution sai để thấy necessity cấu hình cả hai. |
| Rebind alias trong khi `cache=true` | Tái tạo điều kiện cache cũ; verify clear/restart phù hợp. |
| Broker offline, JNDI alias còn | Lookup có thể vẫn thành công nhưng gửi/nhận thất bại; log phân biệt naming vs transport. |
| Retry/redelivery khi listener throw | Hiểu JMS transaction và idempotency; không đánh đồng lỗi naming. |

Trong unit test, có thể thay `JndiTemplate` bằng implementation giả lập trả `Queue`/`Topic` để kiểm tra resolution và type. Integration test với broker thực mới chứng minh đường đi message, quyền và transaction. Không viết bài test phụ thuộc vào một thư mục JNDI server “ngầm có” trong Spring Boot: khi chạy standalone, bạn phải cung cấp naming implementation như Artemis client-side hoặc một provider khác.

## 12. Các câu hỏi tự kiểm tra

**1.** Ứng dụng gọi `convertAndSend("jms/Orders", payload)`, broker có nhất thiết biết tên `jms/Orders`?

**Không.** Resolver tra alias thành `Queue`; broker làm việc với destination/routing do provider biểu diễn, ở ví dụ là `orders.queue`.

**2.** Vì sao có binding `queue.jms/Orders=orders.queue` vẫn có thể gửi thất bại?

Vì binding phía client không cam kết broker đang chạy, Queue vật lý đã được provision, quyền send và kết nối hợp lệ.

**3.** Vì sao `@JmsListener(destination="jms/Orders")` không tự sử dụng resolver đã set trên `JmsTemplate`?

Vì listener có container factory và luồng tạo consumer riêng. Cần gắn resolver ở `DefaultJmsListenerContainerFactory` tương ứng.

**4.** `fallbackToDynamicDestination=true` có thể che lỗi gì?

Có thể che typo/missing JNDI binding bằng cách tạo destination object từ chuỗi sai, đôi khi khiến message đi vào Queue ngoài dự kiến.

**5.** Đặt `cache=false` có tự chuyển toàn bộ listener đang chạy sang Queue mới sau khi rebind không?

**Không chắc.** Nó ảnh hưởng lần resolution tiếp theo. Consumer đang mở có thể cần tái tạo, restart hoặc coordination riêng.

**6.** `jakarta.jms` chuyển namespace thì JNDI có thành `jakarta.naming` không?

**Không.** Java JNDI vẫn là `javax.naming`, trong khi đối tượng JMS được lookup dùng `jakarta.jms.Queue` / `jakarta.jms.Topic` trong Spring 6.x.

## Kết luận

`JndiDestinationResolver` giúp Spring JMS hiểu **tên destination như một binding JNDI** để lấy đối tượng `Queue` hoặc `Topic` đã được công bố. Nó hữu ích khi application server hoặc tổ chức quản trị JMS destination bên ngoài code và muốn cùng một tên logic trỏ đến tài nguyên khác nhau theo môi trường.

Để đúng trong ứng dụng thực, hãy cấu hình resolver cho **cả JmsTemplate và listener container**, chọn namespace JNDI đúng, giữ fallback nghiêm ngặt nếu tài nguyên được quản trị trước, hiểu cache và phân biệt thành công của lookup với kết nối/định tuyến/transaction. Với Artemis standalone, JNDI là cơ chế **phía client**; cấu hình alias không thay thế việc provision Queue trên broker.

## Tài liệu tham khảo

- Spring Framework — Using JMS, `DestinationResolver` và JNDI: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html
- Spring Framework — Annotation-driven JMS listener, cấu hình `setDestinationResolver`: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html
- Spring Framework — `JndiDestinationResolver` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/support/destination/JndiDestinationResolver.html
- Spring Framework — `JndiLocatorSupport` và `resourceRef`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jndi/JndiLocatorSupport.html
- Apache ActiveMQ Artemis — Using JMS / JNDI / administered objects: https://artemis.apache.org/components/artemis/documentation/latest/using-jms
- Apache ActiveMQ Artemis — Client classpath, Jakarta Messaging: https://artemis.apache.org/components/artemis/documentation/latest/client-classpath
- Jakarta Messaging 3.1 — Specification: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Oracle Java — Naming and Directory Interface (JNDI) API: https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/package-summary.html