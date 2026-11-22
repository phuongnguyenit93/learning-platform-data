# Tra cứu ConnectionFactory và Destination qua JNDI

## 1. JNDI đứng ở đâu trong kết nối JMS?

JMS cần ít nhất hai tài nguyên để gửi hoặc nhận message:

- `ConnectionFactory`: factory do JMS provider hoặc application server quản lý, dùng để tạo kết nối và phiên JMS.
- `Destination`: đích nhận message, thường là `Queue` hoặc `Topic`, được quản trị viên cấu hình trên broker/application server.

Trong môi trường Jakarta EE, các tài nguyên này thường được khai báo và bind vào JNDI. Ứng dụng tra cứu tên đã được cấu hình để lấy đúng object mà server quản lý. Nhờ đó ứng dụng không phải tự tạo connection factory, ghi cứng địa chỉ broker, tài khoản hoặc cấu hình pool trong mã nguồn.

JNDI (Java Naming and Directory Interface) là API đặt tên và tra cứu object. JNDI không phải message broker, không tạo ra bảo đảm giao nhận JMS và không tự tạo queue/topic trên mọi provider. Nó chỉ trả về object đã được đăng ký trong naming service.

Spring Framework tích hợp JNDI với JMS qua một số thành phần:

- `JndiObjectFactoryBean`: tra cứu một object JNDI và cung cấp object đó như Spring bean.
- `JndiTemplate`: hỗ trợ thao tác JNDI và quản lý vòng đời `Context` trong các lần lookup.
- `JndiDestinationResolver`: chuyển tên destination thành JMS `Destination` bằng cách tra cứu JNDI.
- `JmsTemplate`: gửi và nhận message, sử dụng `ConnectionFactory` và `DestinationResolver` đã cấu hình.

Phân biệt hai thao tác: tra cứu `ConnectionFactory` thường được thực hiện một lần để inject vào `JmsTemplate` hoặc listener container; tra cứu `Destination` có thể thực hiện qua resolver mỗi khi template cần chuyển một tên destination thành object JMS.

## 2. ConnectionFactory và Destination là gì?

### 2.1. ConnectionFactory

`jakarta.jms.ConnectionFactory` là interface chuẩn của Jakarta Messaging. Object thực tế thường do JMS provider hoặc application server cung cấp. Nó có thể chứa cấu hình endpoint, xác thực, pooling, transaction integration và các chính sách kết nối.

Ứng dụng nên lấy factory do môi trường quản lý khi chạy trong application server. Một factory được server quản lý có thể tích hợp với pool, credential mapping và transaction manager. Tự tạo factory riêng trong ứng dụng có thể bỏ qua những cơ chế này hoặc tạo thêm connection không cần thiết.

Spring `JmsTemplate` nhận một `ConnectionFactory` qua constructor hoặc property. Template quản lý việc tạo và giải phóng các JMS resource dùng cho từng thao tác. Trong môi trường server, factory thường đã cung cấp pooling hoặc chia sẻ connection phù hợp; không tự đóng object `ConnectionFactory` sau khi gửi message.

### 2.2. Destination, Queue và Topic

`jakarta.jms.Destination` là abstraction của đích message. Hai kiểu phổ biến là:

- `Queue`: mô hình point-to-point; một message được giao cho một consumer trong nhóm competing consumers theo semantics của provider.
- `Topic`: mô hình publish-subscribe; message có thể được phân phối tới nhiều subscription theo cấu hình và trạng thái subscription.

Destination có thể được tạo động thông qua `Session.createQueue(...)` hoặc `Session.createTopic(...)`, hoặc được quản trị trước trên broker rồi bind vào JNDI. Với destination được quản trị, lookup trả về object do provider tạo và có thể mang theo cấu hình riêng như quyền truy cập, durable subscription, dead-letter policy hoặc giới hạn tài nguyên.

Không nên xem tên JNDI là tên broker queue trong mọi trường hợp. Tên JNDI là bí danh trong naming service; tên vật lý của destination có thể khác và do provider ánh xạ.

## 3. JNDI naming và các namespace thường gặp

JNDI name phụ thuộc môi trường triển khai. Trong Jakarta EE, các namespace thường gặp gồm:

| Namespace | Phạm vi | Ví dụ |
| --- | --- | --- |
| `java:comp/env` | Môi trường của component/module đang chạy | `java:comp/env/jms/AppConnectionFactory` |
| `java:module` | Phạm vi module | `java:module/env/...` hoặc resource binding theo server |
| `java:app` | Phạm vi ứng dụng | `java:app/...` |
| `java:global` | Phạm vi toàn server | `java:global/...` |

Nhiều application server còn có tên JNDI riêng cho resource toàn cục. Các tên như `java:/JmsXA` hoặc `java:jboss/...` là quy ước của một số server, không phải tên portable cho mọi môi trường.

Ví dụ trong bài dùng tên tương đối `jms/AppConnectionFactory` và `jms/Orders` trong component environment. Khi bật `resourceRef=true`, Spring thêm prefix `java:comp/env/` cho tên tương đối. Vì vậy hai tên trên được tra cứu tương ứng như:

~~~text
java:comp/env/jms/AppConnectionFactory
java:comp/env/jms/Orders
~~~

Nếu đã cung cấp tên đầy đủ bắt đầu bằng `java:`, Spring giữ nguyên tên đó. Hãy xác nhận tên resource mà application server thực sự bind và thống nhất tên với cấu hình triển khai.

## 4. Tra cứu ConnectionFactory bằng JndiObjectFactoryBean

`org.springframework.jndi.JndiObjectFactoryBean` là `FactoryBean` dùng để tra cứu object từ JNDI và đưa object được tìm thấy vào Spring container. Các thuộc tính quan trọng:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `jndiName` | Tên object cần tra cứu |
| `expectedType` | Kiểu mong đợi; Spring kiểm tra object lookup có gán được cho kiểu này không |
| `resourceRef` | Tự thêm `java:comp/env/` cho tên tương đối |
| `lookupOnStartup` | Tra cứu khi Spring khởi tạo bean; mặc định là `true` |
| `cache` | Cache object đã tra cứu; mặc định là `true` |
| `proxyInterface` / `proxyInterfaces` | Interface dùng để tạo proxy khi lookup trì hoãn hoặc không cache |

Ví dụ cấu hình XML:

~~~xml
<bean id="jmsConnectionFactory"
      class="org.springframework.jndi.JndiObjectFactoryBean">
    <property name="jndiName" value="jms/AppConnectionFactory"/>
    <property name="resourceRef" value="true"/>
    <property name="expectedType"
              value="jakarta.jms.ConnectionFactory"/>
</bean>
~~~

Spring tra cứu object khi khởi tạo bean theo mặc định và kiểm tra kiểu mong đợi. Các bean cần JMS có thể inject product của `jmsConnectionFactory` như một `ConnectionFactory`.

### 4.1. Lookup lúc khởi động hay lookup trì hoãn?

Mặc định, `lookupOnStartup=true` và `cache=true`. Ứng dụng sẽ thất bại sớm khi resource không tồn tại hoặc sai kiểu. Đây thường là lựa chọn tốt trong production vì lỗi cấu hình được phát hiện ngay lúc khởi động.

Nếu resource chỉ xuất hiện muộn hoặc cần hỗ trợ redeploy resource, có thể đặt `lookupOnStartup=false`. Khi đó phải cấu hình `proxyInterface` hoặc `proxyInterfaces`, vì Spring cần biết interface để tạo proxy trước khi object thật được lookup. `cache=false` khiến object được lookup lại theo mỗi lần truy cập proxy; chỉ dùng khi môi trường thực sự cần hành vi đó.

Lazy lookup không làm resource tự xuất hiện. Nó chỉ trì hoãn thời điểm phát hiện lỗi. Nếu ứng dụng cần JMS ngay khi phục vụ request, trì hoãn lookup có thể khiến lỗi xuất hiện ở request đầu tiên.

## 5. Tra cứu Destination trực tiếp bằng JNDI

Nếu chỉ có một vài destination cố định, có thể khai báo mỗi destination như một Spring bean bằng `JndiObjectFactoryBean`:

~~~xml
<bean id="ordersQueue"
      class="org.springframework.jndi.JndiObjectFactoryBean">
    <property name="jndiName" value="jms/Orders"/>
    <property name="resourceRef" value="true"/>
    <property name="expectedType" value="jakarta.jms.Queue"/>
</bean>

<bean id="billingTopic"
      class="org.springframework.jndi.JndiObjectFactoryBean">
    <property name="jndiName" value="jms/BillingEvents"/>
    <property name="resourceRef" value="true"/>
    <property name="expectedType" value="jakarta.jms.Topic"/>
</bean>
~~~

Bean `ordersQueue` cung cấp một `Queue`; bean `billingTopic` cung cấp một `Topic`. Sau đó có thể inject trực tiếp `Destination`, `Queue` hoặc `Topic` vào component. `JmsTemplate.send(Destination, MessageCreator)` nhận object destination nên không cần tra cứu tên qua `DestinationResolver` ở mỗi lần gửi.

Cách này phù hợp khi số destination ít, tên ổn định và muốn kiểm tra chúng ngay lúc khởi động. Nếu có nhiều destination hoặc muốn truyền tên từ cấu hình nghiệp vụ, dùng `JndiDestinationResolver` thường gọn hơn.

## 6. JndiDestinationResolver và JmsTemplate

`JmsTemplate` nhận tên destination dạng `String` rồi nhờ `DestinationResolver` chuyển tên đó thành object `Destination`. Resolver mặc định là `DynamicDestinationResolver`: nó dùng JMS `Session` để tạo destination động theo tên.

Khi tên destination đã được quản trị và bind trong JNDI, cấu hình `JndiDestinationResolver`. Resolver này:

- Tra cứu destination theo JNDI name.
- Có cache kết quả theo tên; mặc định cache được bật.
- Có thể xóa một mục hoặc toàn bộ cache qua `removeFromCache(...)` và `clearCache()`.
- Mặc định không fallback sang tạo destination động khi lookup thất bại.

Ví dụ cấu hình XML:

~~~xml
<bean id="jndiDestinationResolver"
      class="org.springframework.jms.support.destination.JndiDestinationResolver">
    <property name="resourceRef" value="true"/>
    <property name="cache" value="true"/>
    <property name="fallbackToDynamicDestination" value="false"/>
</bean>

<bean id="jmsTemplate" class="org.springframework.jms.core.JmsTemplate">
    <constructor-arg ref="jmsConnectionFactory"/>
    <property name="destinationResolver" ref="jndiDestinationResolver"/>
</bean>
~~~

Trong code, có thể gửi tới tên tương đối:

~~~java
jmsTemplate.send("jms/Orders", session ->
        session.createTextMessage("OrderPlaced: ORD-2048"));
~~~

Với `resourceRef=true`, resolver tra cứu `java:comp/env/jms/Orders`. Nếu muốn dùng tên đầy đủ, truyền tên đầy đủ tương ứng với binding của server.

### 6.1. Vì sao fallback mặc định nên tắt?

Nếu lookup JNDI thất bại do sai chính tả hoặc thiếu cấu hình, fallback sang `DynamicDestinationResolver` có thể khiến provider tạo destination động thay vì báo lỗi cấu hình. Điều này có thể dẫn đến message được gửi vào một queue/topic khác hoặc một destination ngoài ý muốn.

Chỉ bật `fallbackToDynamicDestination=true` khi hệ thống chủ động cho phép tạo destination động và đã có quy tắc đặt tên, quyền tạo, dọn dẹp và giám sát phù hợp. Với destination do quản trị viên khai báo, giữ fallback tắt để lỗi `NameNotFound` được phát hiện rõ ràng.

### 6.2. Cache destination

Cache giúp giảm số lần lookup và tránh lặp lại công việc naming cho destination ổn định. Nếu provider xóa hoặc thay thế destination, object đã cache có thể không còn hợp lệ. Khi gặp lỗi do destination bị thay đổi, có thể xóa mục tương ứng khỏi cache rồi lookup lại theo chính sách phục hồi.

Không tắt cache chỉ để “luôn lấy mới” nếu chưa hiểu chi phí và vòng đời object của provider. Nếu bật fallback động, cần dùng tên duy nhất giữa queue và topic vì resolver cache theo destination name.

## 7. Cấu hình JNDI environment cho lookup từ xa

Trong application server, JNDI context thường được môi trường cung cấp sẵn. Với standalone application hoặc remote naming service, ứng dụng có thể phải cấu hình môi trường JNDI, ví dụ:

- `java.naming.factory.initial`: tên lớp `InitialContextFactory` của provider.
- `java.naming.provider.url`: địa chỉ naming service.
- `java.naming.security.principal`: principal dùng xác thực.
- `java.naming.security.credentials`: credential tương ứng.

Đây là các thuộc tính chuẩn JNDI, nhưng giá trị cụ thể và thư viện client phụ thuộc provider. Spring cho phép đặt environment thông qua `JndiTemplate` hoặc các thành phần kế thừa `JndiAccessor`, ví dụ `JndiObjectFactoryBean` và `JndiDestinationResolver`.

Không hardcode mật khẩu trong source code, XML được commit hoặc log. Đọc credential từ secret store hoặc cơ chế cấu hình bảo mật của môi trường. Remote JNDI cần TLS, xác thực và quyền lookup theo hướng dẫn của provider; chỉ mở naming port ra mạng không đáng tin cậy khi đã có kiểm soát phù hợp.

Không dùng cấu hình remote JNDI chung chung cho mọi application server. Provider có thể yêu cầu client library, URL, truststore, authentication mechanism và tên resource riêng. Hãy dùng tài liệu đúng phiên bản server/broker.

## 8. JndiTemplate và lookup thủ công

`JndiTemplate` là tiện ích Spring để thực hiện thao tác JNDI mà không phải lặp lại việc tạo và đóng `Context`. Nó phù hợp khi cần lookup có điều kiện hoặc cần viết một adapter nhỏ thay vì khai báo `JndiObjectFactoryBean`.

Ví dụ lookup có kiểm tra kiểu:

~~~java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.Queue;

import org.springframework.jndi.JndiTemplate;

public final class JmsResources {
    private final JndiTemplate jndiTemplate;

    public JmsResources(JndiTemplate jndiTemplate) {
        this.jndiTemplate = jndiTemplate;
    }

    public ConnectionFactory connectionFactory() {
        return this.jndiTemplate.lookup(
                "java:comp/env/jms/AppConnectionFactory",
                ConnectionFactory.class);
    }

    public Queue ordersQueue() {
        return this.jndiTemplate.lookup(
                "java:comp/env/jms/Orders",
                Queue.class);
    }
}
~~~

Lookup có kiểu giúp phát hiện sớm khi object được bind không đúng interface mong đợi. `JndiTemplate` quản lý `Context` phục vụ thao tác lookup; object JMS trả về vẫn do server/provider quản lý. Không đóng `ConnectionFactory` hoặc `Queue` chỉ vì đã hoàn tất lookup.

Trong ứng dụng Spring thông thường, `JndiObjectFactoryBean` tiện hơn vì đưa resource vào dependency injection, hỗ trợ cache và lazy proxy. Dùng `JndiTemplate` khi cần logic tra cứu động hoặc muốn chủ động xử lý nhiều tên theo quy tắc riêng.

## 9. Ví dụ tích hợp: Java 17 + Spring Framework 6.2

Ví dụ dưới đây cấu hình `ConnectionFactory` và destination thông qua JNDI, sau đó gửi text message bằng `JmsTemplate`. Ví dụ cần chạy trong Jakarta EE/application server hoặc môi trường JMS có naming provider đã bind đúng các tên resource. Nó không thể chạy độc lập chỉ bằng Maven vì JNDI context và JMS provider phải do môi trường triển khai cung cấp.

Cấu trúc project:

~~~text
jms-jndi-demo/
  pom.xml
  src/main/java/com/example/messaging/JmsJndiConfiguration.java
  src/main/java/com/example/messaging/OrderSender.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>jms-jndi-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.18</spring.version>
        <jakarta.jms.version>3.1.0</jakarta.jms.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jms</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>jakarta.jms</groupId>
            <artifactId>jakarta.jms-api</artifactId>
            <version>${jakarta.jms.version}</version>
            <scope>provided</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`src/main/java/com/example/messaging/JmsJndiConfiguration.java`:

~~~java
package com.example.messaging;

import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.destination.JndiDestinationResolver;
import org.springframework.jndi.JndiObjectFactoryBean;

@Configuration
public class JmsJndiConfiguration {

    @Bean
    public JndiObjectFactoryBean jmsConnectionFactory() {
        JndiObjectFactoryBean factory = new JndiObjectFactoryBean();
        factory.setJndiName("jms/AppConnectionFactory");
        factory.setResourceRef(true);
        factory.setExpectedType(ConnectionFactory.class);
        return factory;
    }

    @Bean
    public JndiDestinationResolver jndiDestinationResolver() {
        JndiDestinationResolver resolver = new JndiDestinationResolver();
        resolver.setResourceRef(true);
        resolver.setCache(true);
        resolver.setFallbackToDynamicDestination(false);
        return resolver;
    }

    @Bean
    public JmsTemplate jmsTemplate(
            ConnectionFactory jmsConnectionFactory,
            JndiDestinationResolver jndiDestinationResolver) {
        JmsTemplate template = new JmsTemplate(jmsConnectionFactory);
        template.setDestinationResolver(jndiDestinationResolver);
        return template;
    }
}
~~~

`src/main/java/com/example/messaging/OrderSender.java`:

~~~java
package com.example.messaging;

import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@Component
public class OrderSender {
    private final JmsTemplate jmsTemplate;

    public OrderSender(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public void sendOrderPlaced(String orderId) {
        this.jmsTemplate.send("jms/Orders", session -> {
            var message = session.createTextMessage("OrderPlaced: " + orderId);
            message.setStringProperty("eventType", "OrderPlaced");
            return message;
        });
    }
}
~~~

Triển khai cấu hình trong Spring application context và gọi `sendOrderPlaced("ORD-2048")` sau khi server đã bind:

- `jms/AppConnectionFactory` tới một Jakarta JMS `ConnectionFactory`.
- `jms/Orders` tới một JMS `Queue` được quản trị trên provider.

Vì `resourceRef=true`, Spring tra cứu các tên tương ứng dưới `java:comp/env/`. `JmsTemplate` dùng factory đã lookup và `JndiDestinationResolver` tìm queue. `send()` tạo `TextMessage` bằng `Session` do template cung cấp; template quản lý việc sử dụng và giải phóng JMS resource.

Không có stdout cố định cho ví dụ tích hợp này: kết quả phụ thuộc broker, cấu hình acknowledgement và logging của server. Thành công của lời gọi `send()` chỉ phản ánh việc gửi theo semantics của JMS provider; muốn xác nhận consumer đã xử lý, cần quan sát phía consumer hoặc dùng acknowledgement/response phù hợp.

## 10. Vòng đời và quản lý tài nguyên

JNDI lookup và JMS resource có vòng đời khác nhau:

- `Context`: naming context dùng để lookup; `JndiTemplate` quản lý việc tạo và đóng context cho thao tác lookup.
- `ConnectionFactory`: resource do provider/server quản lý; ứng dụng thường giữ reference và inject vào template/container.
- `Destination`: object đại diện đích JMS; không phải connection hay session và thường được cache/reference trong ứng dụng.
- `Connection`, `Session`, `MessageProducer`, `MessageConsumer`: resource giao tiếp JMS; nên để `JmsTemplate` hoặc listener container quản lý vòng đời theo đúng contract.

Không tạo một `Connection`/`Session` dùng chung giữa nhiều thread. JMS `Session` không thread-safe theo contract; để Spring template/container tạo và quản lý session theo thao tác hoặc consumer thread. Không đóng resource do application server quản lý nếu tài liệu provider yêu cầu container sở hữu lifecycle.

Với standalone application, có thể dùng `SingleConnectionFactory` để chia sẻ một connection và tạo session riêng cho từng thao tác, hoặc dùng pool do provider cung cấp. Trong application server, ưu tiên connection factory đã được server quản lý và cấu hình pooling/transaction.

## 11. Lỗi thường gặp và cách chẩn đoán

| Lỗi | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `NoInitialContextException` | Không có JNDI provider/context factory hoặc thiếu cấu hình môi trường | Kiểm tra application server, provider client library và `java.naming.factory.initial` |
| `NameNotFoundException` | Sai tên hoặc resource chưa được bind | Kiểm tra đúng namespace, tên resource và cấu hình deployment |
| `ClassCastException` / sai `expectedType` | Lookup trả về object khác loại mong đợi | Xác nhận resource binding là `ConnectionFactory`, `Queue` hay `Topic` |
| `DestinationResolutionException` | `JndiDestinationResolver` không tìm thấy destination | Kiểm tra tên JNDI, `resourceRef` và binding của provider |
| `JMSException` khi gửi | Broker mất kết nối, quyền gửi bị từ chối hoặc destination không hợp lệ | Kiểm tra provider log, connection factory, quyền và trạng thái broker |
| Gửi thành công nhưng consumer không nhận | Sai queue/topic, subscription, selector, durable subscription hoặc consumer chưa chạy | Kiểm tra destination vật lý, consumer binding và cấu hình subscription |
| Ứng dụng khởi động thất bại | `JndiObjectFactoryBean` lookup ngay lúc startup nhưng resource chưa sẵn sàng | Kiểm tra thứ tự khởi động; chỉ dùng lazy lookup nếu thực sự cần |
| Message đi vào destination ngoài dự kiến | Tên JNDI sai nhưng fallback dynamic được bật | Tắt fallback hoặc xác minh chính sách tạo destination động |

Trong Spring, `JndiObjectFactoryBean` thường chuyển lỗi lookup thành exception lúc khởi tạo bean. `JndiDestinationResolver` ném `DestinationResolutionException` khi không resolve được tên theo cấu hình. Spring JMS cũng chuyển nhiều `jakarta.jms.JMSException` thành exception unchecked trong hệ thống exception của Spring, giúp code ứng dụng xử lý lỗi nhất quán.

Không log password, credential hoặc toàn bộ environment properties. Khi báo lỗi, ghi tên resource đã được chuẩn hóa, loại resource mong đợi, application/server và nguyên nhân gốc; che thông tin nhạy cảm.

## 12. Quyết định giữa JndiObjectFactoryBean và JndiDestinationResolver

| Nhu cầu | Thành phần phù hợp |
| --- | --- |
| Lấy một `ConnectionFactory` làm dependency dùng chung | `JndiObjectFactoryBean` |
| Lấy một Queue/Topic cố định và inject trực tiếp | `JndiObjectFactoryBean` với `expectedType` là `Queue` hoặc `Topic` |
| `JmsTemplate` nhận tên destination ở runtime và cần lookup JNDI | `JndiDestinationResolver` |
| Muốn tạo destination động từ tên qua JMS Session | `DynamicDestinationResolver` |
| Cần fallback từ JNDI sang dynamic destination | `JndiDestinationResolver` với `fallbackToDynamicDestination=true`, sau khi đánh giá rõ chính sách |
| Cần thao tác lookup tùy biến theo điều kiện | `JndiTemplate` hoặc một service lookup riêng |

Không cần tạo một bean cho từng destination nếu số lượng lớn và tên được cung cấp động. Ngược lại, với một tập nhỏ destination cố định, inject trực tiếp giúp phát hiện sai tên ngay khi ứng dụng khởi động và làm dependency rõ ràng.

## 13. Checklist triển khai

1. Application server/JMS provider đã tạo và bind `ConnectionFactory` chưa?
2. Queue/Topic đã được quản trị và bind đúng JNDI name chưa?
3. Tên được dùng là component-relative hay global/provider-specific?
4. `resourceRef` có khớp với cách khai báo tên không?
5. `expectedType` có đúng `ConnectionFactory`, `Queue`, `Topic` hoặc `Destination` không?
6. `lookupOnStartup` và `cache` có phù hợp với vòng đời resource không?
7. `JmsTemplate` đã được gắn đúng `ConnectionFactory` và `DestinationResolver` chưa?
8. Có vô tình bật dynamic fallback khiến lỗi tên bị che đi không?
9. Provider client library và JNDI environment có đúng phiên bản/môi trường không?
10. Credential được quản lý bằng secret/configuration an toàn chưa?
11. Connection/session/pool có được quản lý đúng bởi container hoặc Spring không?
12. Có kiểm thử trường hợp thiếu binding, sai kiểu, broker mất kết nối và destination bị thay thế không?

## 14. Ghi nhớ

JNDI giúp tra cứu các object JMS đã được provider hoặc application server quản trị. `ConnectionFactory` thường được lookup một lần và inject vào `JmsTemplate` hoặc listener container; `Destination` có thể được inject trực tiếp bằng `JndiObjectFactoryBean` hoặc resolve từ tên qua `JndiDestinationResolver`. `resourceRef=true` giúp dùng tên tương đối dưới `java:comp/env/`; tên global và tên riêng của server cần theo đúng môi trường. `JmsTemplate` mặc định dùng `DynamicDestinationResolver`, nên phải cấu hình `JndiDestinationResolver` khi tên destination được quản lý trong JNDI. Fallback dynamic mặc định tắt để lỗi lookup không âm thầm tạo destination khác. Hãy xác minh binding, kiểu resource, cache, security và vòng đời JMS trước khi triển khai.

### Tài liệu tham khảo

- [Spring Framework 6.2 — Using Spring JMS](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html)
- [Spring Framework 6.2 — Sending a Message](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/sending.html)
- [Spring Framework 6.2 — JndiObjectFactoryBean Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jndi/JndiObjectFactoryBean.html)
- [Spring Framework 6.2 — JndiDestinationResolver package documentation](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/jms/support/destination/package-summary.html)
- [Spring Framework 6.2 — JmsTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html)