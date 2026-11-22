# Nhiều @JmsListener trên một phương thức và annotation @JmsListeners

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao một phương thức Java có thể mang nhiều annotation @JmsListener.
- Hiểu @JmsListener là repeatable annotation và @JmsListeners là annotation container.
- Phân biệt cách khai báo lặp trực tiếp với cách viết tường minh @JmsListeners.
- Biết mỗi khai báo listener tạo một endpoint riêng và được quản lý bởi listener container.
- Cấu hình destination, id, selector, concurrency và containerFactory riêng cho từng endpoint.
- Hiểu cách một phương thức dùng chung nhận Message từ nhiều Queue hoặc Topic.
- Tránh lỗi về thread safety, durable subscription, thứ tự xử lý và chuyển đổi payload.
- Theo dõi, dừng và khởi động endpoint thông qua JmsListenerEndpointRegistry.

## 1. Bài toán: nhiều destination, một phương thức xử lý

Một ứng dụng có thể nhận cùng một loại nghiệp vụ từ nhiều destination JMS. Ví dụ:

- Queue orders.priority nhận đơn hàng ưu tiên.
- Queue orders.standard nhận đơn hàng thông thường.
- Topic orders.events phát các sự kiện đơn hàng.
- Một destination khác được dùng trong môi trường hoặc tenant riêng.

Nếu logic nghiệp vụ giống nhau, ta có thể muốn nhiều destination gọi cùng một phương thức. Spring hỗ trợ điều đó bằng cách cho phép khai báo @JmsListener nhiều lần trên cùng một method.

~~~java
@JmsListener(destination = "orders.priority")
@JmsListener(destination = "orders.standard")
public void handleOrder(String orderId) {
    process(orderId);
}
~~~

Hai annotation mô tả hai listener endpoint khác nhau. Mỗi endpoint có destination và cấu hình riêng, nhưng đều gọi phương thức handleOrder khi nhận được Message phù hợp.

~~~mermaid
flowchart TB
    A["Queue orders.priority"]
    B["Queue orders.standard"]
    C["Listener endpoint 1"]
    D["Listener endpoint 2"]
    E["Cùng phương thức handleOrder(String)"]
    F["Logic nghiệp vụ process(orderId)"]

    A --> C --> E
    B --> D --> E
    E --> F
~~~

Cách này giúp tái sử dụng logic xử lý. Nó không gộp nhiều destination thành một Queue và cũng không biến nhiều endpoint thành một subscription duy nhất.

## 2. @JmsListener là repeatable annotation

Trong Java 8 trở lên, annotation có thể được đánh dấu là repeatable bằng meta-annotation @Repeatable. Spring khai báo @JmsListener theo cách này:

~~~java
@Repeatable(JmsListeners.class)
public @interface JmsListener {
    // Các thuộc tính cấu hình endpoint
}
~~~

Vì vậy, một method có thể khai báo nhiều @JmsListener trực tiếp:

~~~java
@JmsListener(destination = "orders.priority")
@JmsListener(destination = "orders.standard")
public void handleOrder(String orderId) {
    // Xử lý đơn hàng
}
~~~

Khi biên dịch, Java sử dụng annotation container để lưu nhiều annotation cùng loại. Trong trường hợp này, container là @JmsListeners.

Spring đọc các khai báo lặp và đăng ký từng listener endpoint. Mỗi khai báo có thể đại diện cho một destination và cấu hình riêng.

Các package cần biết:

- @JmsListener: org.springframework.jms.annotation.JmsListener.
- @JmsListeners: org.springframework.jms.annotation.JmsListeners.
- @EnableJms: org.springframework.jms.annotation.EnableJms.

Đây là API của Spring JMS, không phải annotation của Spring Messaging nói chung.

## 3. @JmsListeners là annotation container

@JmsListeners là annotation container dùng để nhóm nhiều @JmsListener. Nó có phần tử value chứa mảng các annotation @JmsListener.

Có thể viết tường minh như sau:

~~~java
@JmsListeners({
    @JmsListener(
            id = "priorityOrders",
            destination = "orders.priority"
    ),
    @JmsListener(
            id = "standardOrders",
            destination = "orders.standard"
    )
})
public void handleOrder(String orderId) {
    process(orderId);
}
~~~

Cách viết này tương đương về ý nghĩa với việc đặt hai @JmsListener trực tiếp trên method:

~~~java
@JmsListener(
        id = "priorityOrders",
        destination = "orders.priority"
)
@JmsListener(
        id = "standardOrders",
        destination = "orders.standard"
)
public void handleOrder(String orderId) {
    process(orderId);
}
~~~

Trong code Java hiện đại, khai báo lặp trực tiếp thường dễ đọc hơn. Cách viết @JmsListeners tường minh hữu ích khi muốn thể hiện rõ container annotation hoặc khi tạo annotation tổng hợp (composed annotation).

**Điểm cần nhớ:** @JmsListeners chỉ gom các khai báo annotation. Nó không phải một listener container dùng chung cho mọi destination. Spring vẫn xử lý từng @JmsListener bên trong để đăng ký các endpoint tương ứng.

Không cần đặt cả hai kiểu khai báo trên cùng một method. Chọn một trong hai cách để tránh khai báo trùng.

## 4. Spring đăng ký endpoint như thế nào?

@JmsListener không trực tiếp mở Connection hay tự nhận Message. Spring sử dụng annotation processor và listener container factory để tạo hạ tầng nhận.

Luồng khởi tạo khái niệm:

~~~mermaid
flowchart TD
    A["Application context khởi động"]
    B["@EnableJms bật annotation support"]
    C["JmsListenerAnnotationBeanPostProcessor"]
    D["Phát hiện các @JmsListener"]
    E["Tạo endpoint cho từng annotation"]
    F["Chọn JmsListenerContainerFactory"]
    G["Tạo listener container"]
    H["Container đăng ký consumer với JMS provider"]

    A --> B --> C --> D --> E --> F --> G --> H
~~~

Một endpoint mô tả cách nhận Message từ một destination. Listener container chịu trách nhiệm kết nối tới JMS provider, tạo Session và Consumer, quản lý thread, transaction và gọi phương thức được đánh dấu.

Spring cung cấp JmsListenerEndpointRegistry để quản lý các listener container được tạo bởi annotation infrastructure. Các container này không được đăng ký như bean độc lập thông thường, nhưng có thể được truy xuất qua registry bằng ID endpoint.

### 4.1. Bật annotation support

Thêm @EnableJms vào một class cấu hình:

~~~java
@Configuration
@EnableJms
public class JmsConfiguration {
}
~~~

Nếu không bật annotation support, Spring không đăng ký các method có @JmsListener thành endpoint.

### 4.2. Listener container factory mặc định

Theo mặc định, Spring tìm bean có tên jmsListenerContainerFactory để tạo listener container:

~~~java
@Bean
public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
        ConnectionFactory connectionFactory) {

    DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();

    factory.setConnectionFactory(connectionFactory);
    factory.setSessionTransacted(true);
    factory.setConcurrency("2-5");

    return factory;
}
~~~

Nếu không chỉ định containerFactory trên annotation, endpoint sử dụng factory mặc định này. Có thể khai báo factory khác và chọn riêng cho từng @JmsListener.

## 5. Mỗi @JmsListener có cấu hình riêng

Một ưu điểm quan trọng của repeatable annotation là từng khai báo có thể mang cấu hình khác nhau.

Các thuộc tính thường dùng:

| Thuộc tính | Ý nghĩa |
|---|---|
| destination | Tên Queue hoặc Topic mà endpoint nhận |
| id | ID duy nhất của listener container trong registry |
| containerFactory | Tên bean JmsListenerContainerFactory dùng cho endpoint |
| selector | JMS message selector để lọc Message |
| concurrency | Giới hạn số consumer đồng thời của endpoint |
| subscription | Tên durable subscription khi nhận Topic |

Ví dụ:

~~~java
@JmsListener(
        id = "priorityOrders",
        destination = "orders.in",
        selector = "priority >= 5",
        concurrency = "2-4",
        containerFactory = "fastListenerFactory"
)
@JmsListener(
        id = "standardOrders",
        destination = "orders.in",
        selector = "priority < 5",
        concurrency = "1",
        containerFactory = "standardListenerFactory"
)
public void handleOrder(String orderId) {
    process(orderId);
}
~~~

Hai endpoint cùng đọc orders.in nhưng áp dụng selector và concurrency khác nhau. Message được phân loại theo JMS properties phù hợp với selector.

Nếu nhiều selector có thể cùng khớp, hãy hiểu semantics của các consumer và destination. Với Queue, các consumer cạnh tranh nhận Message; một Message không được broadcast cho tất cả consumer của Queue. Với Topic, các subscription có semantics publish-subscribe riêng.

### 5.1. ID phải rõ ràng và duy nhất

ID định danh container của endpoint. Nếu bỏ trống, Spring tự tạo ID. Với nhiều @JmsListener trên cùng method, nên khai báo ID riêng để quản lý dễ hơn:

~~~java
@JmsListener(id = "priorityOrders", destination = "orders.priority")
@JmsListener(id = "standardOrders", destination = "orders.standard")
public void handleOrder(String orderId) {
    process(orderId);
}
~~~

Có thể truy xuất container:

~~~java
MessageListenerContainer container =
        registry.getListenerContainer("priorityOrders");
~~~

Sau đó gọi start(), stop() hoặc kiểm tra trạng thái theo nhu cầu vận hành. Registry cũng hữu ích khi cần quan sát các endpoint đã được đăng ký.

Không dùng cùng một ID cho nhiều annotation. ID trùng khiến việc đăng ký và quản lý container trở nên mơ hồ hoặc thất bại.

### 5.2. Chọn containerFactory theo endpoint

Mỗi annotation có thể chỉ định containerFactory khác nhau:

~~~java
@JmsListener(
        id = "queueOrders",
        destination = "orders.in",
        containerFactory = "queueListenerFactory"
)
@JmsListener(
        id = "topicEvents",
        destination = "orders.events",
        containerFactory = "topicListenerFactory"
)
public void handle(String payload) {
    process(payload);
}
~~~

Cách này hữu ích khi Queue và Topic cần cấu hình pubSubDomain khác nhau, hoặc khi endpoint có yêu cầu khác nhau về transaction, concurrency, error handler, converter và recovery.

Một factory có thể dùng chung cho nhiều endpoint nếu chúng có cùng chính sách. Không cần tạo factory mới cho từng annotation nếu cấu hình không khác nhau.

## 6. Một phương thức dùng chung nhận payload như thế nào?

Các endpoint trên cùng method đều dùng cùng chữ ký phương thức. Spring chuyển JMS Message thành tham số Java theo converter và cơ chế argument resolution của listener adapter.

Ví dụ:

~~~java
@JmsListener(destination = "orders.priority")
@JmsListener(destination = "orders.standard")
public void handleOrder(String orderId) {
    process(orderId);
}
~~~

Với cấu hình converter mặc định, TextMessage thường được chuyển thành String. Nếu hai destination gửi các kiểu Message khác nhau, cần bảo đảm method signature và converter có thể xử lý cả hai.

Các kiểu tham số thường được hỗ trợ gồm:

- Payload Java như String hoặc DTO.
- jakarta.jms.Message hoặc subclass như TextMessage.
- jakarta.jms.Session khi cần truy cập JMS API.
- org.springframework.messaging.Message để nhận payload cùng headers.
- Tham số có @Header để lấy một header cụ thể.
- Tham số Map có @Headers để nhận tập headers.

Ví dụ đọc thêm metadata:

~~~java
@JmsListener(destination = "orders.priority")
@JmsListener(destination = "orders.standard")
public void handleOrder(
        String orderId,
        @Header("eventType") String eventType) {

    process(orderId, eventType);
}
~~~

Cả hai destination phải gửi metadata eventType tương thích. Nếu một destination không có header bắt buộc, việc bind tham số có thể thất bại; có thể dùng required=false hoặc giá trị mặc định nếu nghiệp vụ cho phép.

### 6.1. Dùng raw JMS Message khi cấu trúc không đồng nhất

Nếu các destination gửi nhiều loại JMS Message hoặc cần kiểm tra properties, có thể nhận raw Message:

~~~java
@JmsListener(destination = "orders.priority")
@JmsListener(destination = "orders.standard")
public void handleMessage(jakarta.jms.Message message) {
    // Kiểm tra kiểu Message và đọc dữ liệu tương ứng.
}
~~~

Cách này cho phép xử lý khác nhau theo TextMessage, BytesMessage, MapMessage hoặc metadata của JMS. Đổi lại, method phải tự kiểm tra kiểu và xử lý JMSException.

Nếu chỉ dùng chung một DTO, nên giữ chữ ký payload rõ ràng để tránh việc chuyển đổi và kiểm tra kiểu thủ công.

## 7. Queue và Topic khi có nhiều listener endpoint

Ý nghĩa của việc lặp @JmsListener phụ thuộc loại destination.

### 7.1. Nhiều endpoint đọc cùng một Queue

Ví dụ:

~~~java
@JmsListener(destination = "orders.in")
@JmsListener(destination = "orders.in")
public void handleOrder(String orderId) {
    process(orderId);
}
~~~

Mỗi annotation tạo một endpoint riêng. Nếu cả hai endpoint cùng đọc một Queue, chúng tạo các consumer cạnh tranh trên Queue đó. Theo mô hình point-to-point, một Message được giao cho một consumer nhận được nó, không phải tự động gọi method hai lần cho cùng một Message.

Tuy nhiên, nếu cả hai endpoint đều có selector phù hợp, cả hai có thể cạnh tranh nhận các Message thỏa điều kiện. Hãy tránh khai báo trùng nếu không có chủ đích tăng số consumer.

### 7.2. Nhiều endpoint nhận cùng một Topic

Topic dùng mô hình publish-subscribe. Các subscription độc lập có thể nhận bản sao của cùng một publication.

Nếu nhiều @JmsListener đăng ký cùng Topic với subscription riêng, một publication có thể được chuyển tới từng subscription. Đây là hành vi khác Queue và có thể khiến cùng logic method được gọi nhiều lần cho cùng event.

Không tăng concurrency của Topic một cách máy móc. Cấu hình nhiều consumer trên cùng Topic có thể dẫn đến cùng một publication được xử lý đồng thời nhiều lần tùy kiểu subscription và JMS provider.

### 7.3. Durable subscription và tên subscription

Thuộc tính subscription dùng để đặt tên durable subscription. Durable subscription cho phép broker giữ Message theo chính sách subscription khi subscriber tạm thời offline.

Javadoc Spring ghi nhận tên subscription mặc định có thể được tạo từ tên đầy đủ của listener method. Khi nhiều @JmsListener trên cùng một method cùng sử dụng durable Topic, hãy khai báo subscription name riêng cho từng endpoint để tránh trùng danh tính subscription.

Ngoài tên subscription, durable subscriber còn phụ thuộc client ID, cấu hình container và khả năng của JMS provider. Hãy kiểm tra cấu hình client identity và durable/shared subscription của broker đang dùng.

## 8. Concurrency và thread safety của method dùng chung

Một method có nhiều @JmsListener có thể được gọi từ nhiều listener container. Mỗi endpoint có thể có concurrency riêng.

Ví dụ:

~~~java
@JmsListener(
        destination = "orders.priority",
        concurrency = "3"
)
@JmsListener(
        destination = "orders.standard",
        concurrency = "2"
)
public void handleOrder(String orderId) {
    process(orderId);
}
~~~

Tổng số consumer có thể lớn hơn concurrency của một endpoint. Trong ví dụ, mỗi endpoint có số consumer riêng theo cấu hình, và cả hai đều gọi cùng một method trên cùng listener bean.

Đây là điểm dễ bị bỏ sót: đặt concurrency=1 cho từng endpoint không có nghĩa toàn bộ method chỉ chạy một thread tại một thời điểm. Hai endpoint khác nhau vẫn có thể gọi method đồng thời.

Vì vậy:

- Ưu tiên listener stateless.
- Dùng biến cục bộ cho dữ liệu của từng lần xử lý.
- Nếu cần chia sẻ counter hoặc cache, dùng cấu trúc thread-safe.
- Không giữ một JMS Session hoặc MessageConsumer trong field để nhiều lần gọi cùng sử dụng.
- Bảo vệ các thao tác cập nhật cùng một entity nghiệp vụ bằng transaction hoặc cơ chế đồng bộ thích hợp.
- Không giả định thứ tự xử lý toàn cục giữa các destination.

Nếu nghiệp vụ yêu cầu tuần tự hóa tất cả đơn hàng từ nhiều destination, hãy dùng một cơ chế điều phối rõ ràng, chẳng hạn một worker tuần tự, partition theo khóa hoặc hàng đợi hợp nhất. Nhiều @JmsListener không tự tạo bảo đảm thứ tự chung.

## 9. Transaction và xử lý lỗi

Mỗi endpoint có listener container và session riêng theo cấu hình. Transaction, acknowledgement và redelivery được áp dụng theo container factory của endpoint đó.

Ví dụ:

~~~java
factory.setSessionTransacted(true);
~~~

Khi dùng sessionTransacted=true, listener xử lý Message trong JMS local transaction. Nếu method hoàn tất bình thường, container commit. Nếu method ném exception, transaction có thể rollback và broker giao lại Message theo redelivery policy.

Nếu một method được gọi từ nhiều endpoint, mỗi lần gọi vẫn thuộc transaction của endpoint đã nhận Message. Một lần xử lý thành công trên destination thứ nhất không làm commit hoặc rollback transaction của endpoint thứ hai.

Cần chú ý:

- AUTO_ACKNOWLEDGE mặc định không cung cấp bảo đảm redelivery đáng tin cậy cho mọi trường hợp lỗi.
- Cấu hình transaction cho từng factory phù hợp với yêu cầu nghiệp vụ.
- JMS local transaction không tự bao gồm transaction database.
- Nếu có side effect ở database hoặc API ngoài, cần idempotency và duplicate detection.
- Cấu hình maximum redelivery và dead-letter policy ở broker để tránh poison message lặp vô hạn.

Khi nhiều endpoint gọi chung method, log nên có destination, message ID, correlation ID hoặc event type để xác định endpoint nào đã kích hoạt lần xử lý.

## 10. Reply từ method dùng chung

Listener method có thể trả về một giá trị khác void. Spring có thể chuyển giá trị đó thành JMS response và gửi về destination được chỉ định trong JMSReplyTo của request. Nếu request không có JMSReplyTo, có thể cấu hình destination mặc định bằng @SendTo.

Ví dụ:

~~~java
@JmsListener(destination = "orders.priority")
@JmsListener(destination = "orders.standard")
@SendTo("orders.status")
public OrderStatus handleOrder(Order order) {
    return process(order);
}
~~~

Trong ví dụ, hai endpoint dùng chung chính sách reply destination orders.status.

Nếu mỗi endpoint cần gửi reply tới một destination khác nhau, một @SendTo cố định trên method có thể không đủ. Hãy dùng JmsResponse để chọn destination theo từng request hoặc tách thành các method riêng khi logic phản hồi khác nhau.

Không phải mọi event một chiều đều cần return value. Nếu producer không chờ response, dùng method void sẽ làm ý định rõ ràng hơn.

## 11. Khi nào dùng @JmsListeners tường minh?

Khai báo lặp trực tiếp là cách thông dụng:

~~~java
@JmsListener(destination = "orders.priority")
@JmsListener(destination = "orders.standard")
public void handleOrder(String orderId) {
    process(orderId);
}
~~~

Container annotation có thể được viết tường minh:

~~~java
@JmsListeners({
    @JmsListener(destination = "orders.priority"),
    @JmsListener(destination = "orders.standard")
})
public void handleOrder(String orderId) {
    process(orderId);
}
~~~

Nên dùng khai báo lặp trực tiếp khi:

- Code chạy trên Java 8 trở lên.
- Muốn đọc nhanh các destination cùng gọi một method.
- Mỗi annotation có cấu hình đơn giản.

Có thể dùng @JmsListeners tường minh khi:

- Muốn thể hiện rõ annotation container trong code hoặc tài liệu.
- Đang tạo annotation tổng hợp dùng lại ở nhiều nơi.
- Cần nhóm các annotation con thành một khai báo duy nhất theo quy ước codebase.

Cả hai cách đều dựa trên cùng cơ chế repeatable annotation của Java và được Spring xử lý thành các listener endpoint riêng.

## 12. Khi danh sách destination chỉ biết lúc chạy

Repeatable annotation phù hợp khi danh sách destination có thể khai báo tĩnh trong source code. Nếu danh sách destination được tải từ database, cấu hình tenant hoặc registry lúc ứng dụng khởi động, không thể viết số lượng annotation tùy ý tại compile time.

Trong trường hợp đó, có thể đăng ký endpoint bằng JmsListenerConfigurer và JmsListenerEndpointRegistrar:

~~~java
@Configuration
@EnableJms
public class DynamicJmsConfiguration implements JmsListenerConfigurer {

    @Override
    public void configureJmsListeners(
            JmsListenerEndpointRegistrar registrar) {

        SimpleJmsListenerEndpoint endpoint =
                new SimpleJmsListenerEndpoint();

        endpoint.setId("dynamicOrders");
        endpoint.setDestination("orders.dynamic");
        endpoint.setMessageListener(message -> {
            // Xử lý JMS Message
        });

        registrar.registerEndpoint(endpoint);
    }
}
~~~

Có thể lặp qua danh sách cấu hình để đăng ký nhiều endpoint. Đây là cách phù hợp hơn cho số lượng destination thay đổi theo cấu hình runtime.

Đừng cố tạo annotation bằng reflection sau khi application context đã hoàn tất khởi tạo rồi kỳ vọng Spring tự động đăng ký lại endpoint. Hãy dùng API đăng ký endpoint chính thức.

## 13. Ví dụ Java 17 chạy được với hai @JmsListener trên một method

Ví dụ sau dùng Spring Framework 6.2.19 và Apache ActiveMQ Classic 6.1.6. Broker được chạy embedded trong cùng JVM qua BrokerService và VM transport. Hai Queue được gửi tới cùng một method listener.

### 13.1. Cấu hình Maven

Tạo file pom.xml:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>repeatable-jms-listener-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework</groupId>
                <artifactId>spring-framework-bom</artifactId>
                <version>6.2.19</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jms</artifactId>
        </dependency>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>activemq-broker</artifactId>
            <version>6.1.6</version>
        </dependency>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>activemq-client</artifactId>
            <version>6.1.6</version>
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
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 13.2. Cấu hình Spring JMS

Tạo file src/main/java/demo/JmsDemoConfiguration.java:

~~~java
package demo;

import jakarta.jms.ConnectionFactory;

import org.apache.activemq.ActiveMQConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;

@Configuration
@EnableJms
public class JmsDemoConfiguration {

    @Bean
    public ConnectionFactory connectionFactory() {
        return new ActiveMQConnectionFactory(
                "vm://repeatable-listener-demo?create=false"
        );
    }

    @Bean
    public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        factory.setConcurrency("1");

        return factory;
    }

    @Bean
    public JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
        return new JmsTemplate(connectionFactory);
    }

    @Bean
    public SharedOrderListener sharedOrderListener() {
        return new SharedOrderListener();
    }
}
~~~

### 13.3. Listener dùng chung

Tạo file src/main/java/demo/SharedOrderListener.java:

~~~java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.jms.annotation.JmsListener;

public class SharedOrderListener {

    private final AtomicInteger priorityCount = new AtomicInteger();
    private final AtomicInteger standardCount = new AtomicInteger();
    private final CountDownLatch received = new CountDownLatch(2);

    @JmsListener(
            id = "priorityOrders",
            destination = "orders.priority",
            containerFactory = "jmsListenerContainerFactory",
            concurrency = "1"
    )
    @JmsListener(
            id = "standardOrders",
            destination = "orders.standard",
            containerFactory = "jmsListenerContainerFactory",
            concurrency = "1"
    )
    public void handleOrder(String payload) {
        if (payload.startsWith("priority:")) {
            priorityCount.incrementAndGet();
        }
        else if (payload.startsWith("standard:")) {
            standardCount.incrementAndGet();
        }
        else {
            throw new IllegalArgumentException(
                    "Unsupported order payload: " + payload
            );
        }

        received.countDown();
    }

    public boolean awaitMessages(long timeout, TimeUnit unit)
            throws InterruptedException {
        return received.await(timeout, unit);
    }

    public int getPriorityCount() {
        return priorityCount.get();
    }

    public int getStandardCount() {
        return standardCount.get();
    }
}
~~~

### 13.4. Khởi chạy broker và gửi hai Message

Tạo file src/main/java/demo/RepeatableJmsListenerDemo.java:

~~~java
package demo;

import java.util.concurrent.TimeUnit;

import org.apache.activemq.broker.BrokerService;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.jms.core.JmsTemplate;

public class RepeatableJmsListenerDemo {

    public static void main(String[] args) throws Exception {
        BrokerService broker = new BrokerService();
        broker.setBrokerName("repeatable-listener-demo");
        broker.setPersistent(false);
        broker.setUseJmx(false);

        broker.start();
        broker.waitUntilStarted();

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             JmsDemoConfiguration.class
                     )) {

            JmsTemplate template = context.getBean(JmsTemplate.class);
            SharedOrderListener listener =
                    context.getBean(SharedOrderListener.class);

            template.convertAndSend(
                    "orders.priority",
                    "priority:PO-158"
            );

            template.convertAndSend(
                    "orders.standard",
                    "standard:SO-158"
            );

            if (!listener.awaitMessages(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Listener did not receive both messages"
                );
            }

            System.out.println(
                    "priority.received=" + listener.getPriorityCount()
            );
            System.out.println(
                    "standard.received=" + listener.getStandardCount()
            );
        }
        finally {
            broker.stop();
            broker.waitUntilStopped();
        }
    }
}
~~~

Chạy từ thư mục chứa pom.xml:

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=demo.RepeatableJmsListenerDemo
~~~

Các dòng do chương trình in ra, không tính log nội bộ của broker hoặc framework:

~~~text
priority.received=1
standard.received=1
~~~

### 13.5. Phân tích kết quả

JmsDemoConfiguration bật @EnableJms và cung cấp một DefaultJmsListenerContainerFactory. Spring phát hiện hai @JmsListener trên cùng method handleOrder và đăng ký hai endpoint:

- priorityOrders nhận từ Queue orders.priority.
- standardOrders nhận từ Queue orders.standard.

Hai endpoint dùng chung listener bean SharedOrderListener nhưng có container riêng. JmsTemplate gửi hai TextMessage với payload khác nhau. Container tương ứng nhận từng Message và gọi cùng method handleOrder.

Method phân biệt loại payload bằng tiền tố priority: hoặc standard:. AtomicInteger giúp cập nhật counter an toàn khi hai endpoint gọi method từ các thread khác nhau. CountDownLatch giúp chương trình chính đợi tới khi cả hai Message được xử lý rồi mới in kết quả.

Ví dụ chứng minh hai destination có thể dùng chung một method. Nó không có nghĩa hai Message được xử lý trên cùng một thread hoặc theo một thứ tự toàn cục.

## 14. Kiểm thử và quan sát nhiều endpoint

Khi có nhiều @JmsListener trên một method, nên kiểm thử từng endpoint độc lập và kiểm thử trường hợp chúng chạy đồng thời.

Các điểm nên xác nhận:

1. Mỗi destination đều được đăng ký đúng.
2. Mỗi endpoint có ID duy nhất.
3. Message từ destination thứ nhất và thứ hai đều gọi đúng method.
4. Selector của từng endpoint lọc đúng Message.
5. Converter xử lý được payload của tất cả destination.
6. Concurrency không gây race condition trong listener bean.
7. Transaction và redelivery hoạt động đúng với từng endpoint.
8. Durable subscription không trùng tên hoặc client identity.
9. Reply được gửi về destination mong đợi nếu method có return value.
10. Registry có thể truy xuất và quản lý từng container bằng ID.

Có thể dùng JmsListenerEndpointRegistry để kiểm tra trạng thái:

~~~java
MessageListenerContainer priorityContainer =
        registry.getListenerContainer("priorityOrders");

MessageListenerContainer standardContainer =
        registry.getListenerContainer("standardOrders");
~~~

Hai container có thể được start hoặc stop riêng. Điều này hữu ích khi cần tạm dừng một luồng nhận trong lúc bảo trì destination hoặc thay đổi cấu hình.

Nên log endpoint ID hoặc destination cùng message ID/correlation ID để truy vết. Nếu chỉ log tên method, sẽ khó phân biệt Message đến từ endpoint nào khi nhiều annotation gọi cùng một method.

## 15. Lỗi thường gặp

1. **Nghĩ @JmsListeners là một listener container chung:** đây là annotation container; Spring xử lý từng @JmsListener bên trong thành endpoint riêng.
2. **Dùng @JmsListener nhiều lần nhưng quên @EnableJms:** annotation infrastructure chưa được bật.
3. **Không có default container factory:** nếu annotation không chỉ định containerFactory, Spring cần factory mặc định tên jmsListenerContainerFactory hoặc cấu hình default khác.
4. **Dùng ID trùng nhau:** mỗi endpoint cần ID duy nhất để registry quản lý chính xác.
5. **Cho rằng concurrency=1 bảo đảm method không chạy song song:** nhiều endpoint vẫn có thể gọi cùng method đồng thời.
6. **Dùng field mutable không thread-safe:** shared listener bean có thể được gọi từ nhiều container và consumer thread.
7. **Giả định Queue broadcast cho mọi listener:** Queue dùng mô hình competing consumers; một Message được một consumer nhận.
8. **Giả định Topic giống Queue:** các subscription độc lập có thể nhận bản sao của cùng publication.
9. **Dùng chung durable subscription name:** các endpoint durable cần danh tính subscription phù hợp và không xung đột.
10. **Dùng cùng method cho payload không tương thích:** converter hoặc argument binding có thể lỗi khi một destination gửi kiểu Message khác.
11. **Không phân biệt containerFactory:** endpoint Queue và Topic có thể cần factory với pubSubDomain hoặc transaction khác nhau.
12. **Đặt @SendTo cố định nhưng mong reply destination khác nhau:** dùng JmsResponse hoặc tách method khi reply destination phụ thuộc endpoint.
13. **Kỳ vọng thứ tự xử lý chung giữa nhiều destination:** mỗi endpoint và consumer có lịch thực thi riêng.
14. **Dùng annotation cho danh sách destination chỉ biết lúc chạy:** dùng JmsListenerConfigurer và JmsListenerEndpointRegistrar.
15. **Không theo dõi endpoint riêng:** khi có lỗi, cần ID/destination để xác định container nào gặp vấn đề.

## 16. Câu hỏi tự kiểm tra

1. Vì sao @JmsListener có thể xuất hiện nhiều lần trên cùng một method?
2. @Repeatable(JmsListeners.class) có ý nghĩa gì?
3. Java xử lý các annotation lặp thông qua annotation container nào?
4. @JmsListeners có trực tiếp tạo một listener container duy nhất không?
5. Mỗi khai báo @JmsListener có thể cấu hình những thuộc tính riêng nào?
6. Vai trò của @EnableJms là gì?
7. Nếu không chỉ định containerFactory, Spring tìm bean mặc định tên gì?
8. JmsListenerEndpointRegistry dùng để quản lý thành phần nào?
9. Vì sao mỗi endpoint nên có ID riêng?
10. Hai @JmsListener cùng đọc một Queue có tạo broadcast không?
11. Điều gì khác khi nhiều endpoint đăng ký cùng một Topic?
12. Vì sao durable subscription cần tên riêng khi nhiều annotation dùng chung method?
13. Concurrency=1 trên từng endpoint có bảo đảm method chỉ chạy một thread không?
14. Khi nào nên dùng @JmsListeners tường minh thay vì annotation lặp trực tiếp?
15. Khi danh sách destination chỉ biết lúc runtime, API nào phù hợp hơn?
16. Nếu method trả về object, Spring có thể gửi reply tới đâu?
17. Làm thế nào để kiểm thử rằng cả hai endpoint đều gọi đúng method?

## 17. Kết luận

@JmsListener là repeatable annotation, cho phép một method nhận Message từ nhiều JMS destination. Java lưu các khai báo lặp thông qua container annotation @JmsListeners; ứng dụng cũng có thể khai báo container này tường minh.

Spring xử lý từng @JmsListener thành một listener endpoint riêng và tạo listener container tương ứng. Mỗi endpoint có thể có destination, ID, selector, concurrency, subscription và containerFactory riêng, trong khi cùng gọi một method nghiệp vụ.

Khi thiết kế, cần phân biệt Queue với Topic, quản lý ID và durable subscription, bảo đảm method thread-safe và cấu hình transaction phù hợp. Nếu danh sách destination chỉ biết khi chạy, hãy dùng API đăng ký endpoint thay vì cố tạo annotation động.

## Tài liệu tham khảo chính thức

- Spring Framework 6.2 — Annotation-driven Listener Endpoints: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html
- Spring Framework 6.2 — Receiving a Message: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html
- Spring Framework 6.2 — Using Spring JMS: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html
- JmsListener API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/annotation/JmsListener.html
- JmsListeners API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/annotation/JmsListeners.html
- EnableJms API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/annotation/EnableJms.html
- JmsListenerEndpointRegistry API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/config/JmsListenerEndpointRegistry.html
- Jakarta Messaging specification: https://jakarta.ee/specifications/messaging/
- Apache ActiveMQ Classic: https://activemq.apache.org/components/classic/
