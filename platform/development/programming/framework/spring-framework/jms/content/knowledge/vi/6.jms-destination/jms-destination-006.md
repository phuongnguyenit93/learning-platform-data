# defaultDestination và defaultDestinationName trong Spring JMS

**Phạm vi:** Spring Framework - jms → Destination.

## 1. Vì sao JmsTemplate cần một destination mặc định?

Trong JMS/Jakarta Messaging, **destination** là nơi producer gửi thông điệp hoặc consumer nhận thông điệp. Destination thường là `Queue` (point-to-point) hoặc `Topic` (publish/subscribe). Spring Framework cung cấp `JmsTemplate` để ứng dụng không phải lặp lại các thao tác mở connection/session, tạo producer và chuyển đổi message.

Nếu một service chủ yếu gửi tới cùng một queue, việc viết lặp lại tên destination:

~~~java
jmsTemplate.convertAndSend("orders.created", "order-101");
jmsTemplate.convertAndSend("orders.created", "order-102");
jmsTemplate.convertAndSend("orders.created", "order-103");
~~~

có thể được thay bằng cấu hình **default destination**:

~~~java
jmsTemplate.setDefaultDestinationName("orders.created");

jmsTemplate.convertAndSend("order-101");
jmsTemplate.convertAndSend("order-102");
jmsTemplate.convertAndSend("order-103");
~~~

Hai đoạn mã giả định `jmsTemplate` đã được tạo từ một `ConnectionFactory` hợp lệ. Đoạn thứ hai hoạt động vì `convertAndSend(Object)` là **overload không có tham số destination**. Spring lấy destination mặc định của chính instance `JmsTemplate` rồi gửi thông điệp đến đó.

Có hai lựa chọn cấu hình:

- **`defaultDestination`:** một đối tượng `jakarta.jms.Destination` đã được provider/application server cung cấp.
- **`defaultDestinationName`:** một chuỗi `String` biểu diễn tên destination; `JmsTemplate` dùng `DestinationResolver` chuyển tên thành object.

Đây là **hai cách biểu diễn một đích mặc định của Spring JmsTemplate**. Chúng không phải hai loại destination của JMS, không tự tạo broker và không quy định queue mà mọi listener trong ứng dụng phải lắng nghe.

## 2. So sánh defaultDestination và defaultDestinationName

| Tiêu chí | `defaultDestination` | `defaultDestinationName` |
| --- | --- | --- |
| Dữ liệu cấu hình | Object `jakarta.jms.Destination` | Tên dạng `String` |
| Setter | `setDefaultDestination(Destination)` | `setDefaultDestinationName(String)` |
| Getter | `getDefaultDestination()` | `getDefaultDestinationName()` |
| Cách xác định đích | Dùng object đã có | Gọi `DestinationResolver` theo tên và session |
| Ví dụ | `Queue`/`Topic` object được inject từ provider hoặc JNDI | `"orders.created"` |
| Đặc điểm | Dùng khi ứng dụng đã có administered destination | Thuận tiện cho application.properties và Java Config |
| Ảnh hưởng tới lời gọi `convertAndSend("payload")` | Có | Có |
| Ảnh hưởng tới `convertAndSend("other.queue", "payload")` | Không | Không |

Luồng xử lý:

~~~text
                 ỨNG DỤNG SPRING
                         |
                 JmsTemplate
                         |
      +------------------+------------------+
      |                                     |
defaultDestination                    defaultDestinationName
 (Destination object)                       (String)
      |                                     |
      |                               DestinationResolver
      |                                     |
      +------------------+------------------+
                         |
                     Destination
                         |
                  JMS Session/Producer
                         |
                    JMS provider
                         |
                   Queue hoặc Topic
~~~

Điểm quan trọng: **default destination chỉ được dùng khi phương thức không được truyền destination riêng**. Nếu hầu hết thao tác đều có destination tường minh, ứng dụng không bắt buộc cấu hình default.

## 3. Những phương thức nào dùng default destination?

Bảng dưới phân biệt overload của `org.springframework.jms.core.JmsTemplate`:

| Phương thức | Nguồn destination |
| --- | --- |
| `convertAndSend(Object message)` | Default đã cấu hình |
| `send(MessageCreator creator)` | Default |
| `convertAndSend(Object message, MessagePostProcessor postProcessor)` | Default |
| `receive()` / `receiveAndConvert()` | Default |
| `receiveSelected(String selector)` | Default, cộng với selector |
| `sendAndReceive(MessageCreator creator)` | Default cho **request** destination |
| `convertAndSend(String destinationName, Object message)` | Tên destination được truyền |
| `convertAndSend(Destination destination, Object message)` | Object destination được truyền |
| `send(String destinationName, MessageCreator creator)` | Tên được truyền |
| `receive(String destinationName)` | Tên được truyền |

Ví dụ:

~~~java
jmsTemplate.setDefaultDestinationName("orders.normal");

// Một đối số: dữ liệu gửi đi là "order-101", đích là orders.normal.
jmsTemplate.convertAndSend("order-101");

// Hai đối số: gửi dữ liệu "order-202" đến orders.priority.
jmsTemplate.convertAndSend("orders.priority", "order-202");
~~~

Đây là **hai message đến hai queue khác nhau**, mặc dù cùng một template. Cấu hình default không khóa `JmsTemplate` vào một destination duy nhất.

Phải đặc biệt chú ý sự khác biệt giữa:

~~~java
jmsTemplate.convertAndSend("orders.created");
jmsTemplate.convertAndSend("orders.created", "hello");
~~~

Dòng đầu coi `"orders.created"` là **payload** và gửi đến **default**. Dòng thứ hai coi `"orders.created"` là **destinationName**, còn `"hello"` mới là payload. Đây là lỗi hiểu nhầm overload có thể khiến message được đưa đến sai queue mà code vẫn biên dịch.

Nếu không có default và gọi một overload không có destination, Spring sẽ báo `IllegalStateException` với thông điệp tương tự:

~~~text
No 'defaultDestination' or 'defaultDestinationName' specified. Check configuration of JmsTemplate.
~~~

Cách sửa là **thiết lập một default** hoặc **chọn overload có destination tường minh**.

## 4. defaultDestinationName: tên String được resolve như thế nào?

### 4.1. Cấu hình bằng Java

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.jms.core.JmsTemplate;

// connectionFactory phải được provider hoặc Spring cung cấp trước.
JmsTemplate template = new JmsTemplate(connectionFactory);
template.setDefaultDestinationName("orders.created");
template.setPubSubDomain(false); // false => queue, là cấu hình mặc định
template.convertAndSend("order-101");
~~~

Đoạn mã này không độc lập vì cần `connectionFactory`, broker và destination tương ứng. `setDefaultDestinationName` không buộc ứng dụng viết ra tên queue ở mọi lần gọi `convertAndSend`.

### 4.2. DestinationResolver là thành phần trung gian

`DestinationResolver` là interface:

~~~java
Destination resolveDestinationName(
        Session session, String destinationName, boolean pubSubDomain
) throws JMSException;
~~~

Spring sử dụng `DynamicDestinationResolver` theo mặc định. Resolver lấy một `Session` và có thể gọi:

~~~java
session.createQueue("orders.created"); // nếu pubSubDomain=false
session.createTopic("orders.events"); // nếu pubSubDomain=true
~~~

Đây là **trích đoạn minh họa** hai trường hợp; code thực tế sẽ chọn một trong hai theo boolean. Với `defaultDestinationName="orders.created"` và `pubSubDomain=false`, Spring resolve thành queue object rồi dùng nó khi gửi/nhận.

**Đừng nhầm resolve object với provision trên broker.** `Session.createQueue(name)` chỉ trả về một đối tượng `Queue` theo giao diện JMS; việc broker có cho phép tạo queue vật lý tự động hay yêu cầu admin tạo sẵn phụ thuộc provider và cấu hình môi trường. Vì vậy một cấu hình mặc định đúng cú pháp vẫn có thể lỗi khi send nếu queue chưa tồn tại hoặc tài khoản không có quyền.

### 4.3. Tên String không đồng nghĩa với JNDI lookup

`DynamicDestinationResolver` **không mặc định** dùng JNDI. Nếu application server cung cấp queue/topic dưới dạng JNDI administered objects, Spring có `JndiDestinationResolver`:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.destination.JndiDestinationResolver;

@Configuration
class JndiJmsConfiguration {

    @Bean
    JmsTemplate jmsTemplate(ConnectionFactory factory) {
        JndiDestinationResolver resolver = new JndiDestinationResolver();
        resolver.setCache(true);

        JmsTemplate template = new JmsTemplate(factory);
        template.setDestinationResolver(resolver);
        template.setDefaultDestinationName("java:comp/env/jms/Orders");
        return template;
    }
}
~~~

Đây là cấu hình có thể biên dịch khi có Spring JMS dependencies, **nhưng chỉ hoạt động** nếu môi trường thực sự có JNDI context và tên `java:comp/env/jms/Orders` tương ứng. Không mặc định mọi JMS provider đều triển khai cấu trúc JNDI này.

### 4.4. pubSubDomain quyết định Queue hay Topic khi giải quyết tên

| `pubSubDomain` | Loại destination khi dùng `DynamicDestinationResolver` | Ý nghĩa |
| --- | --- | --- |
| `false` (mặc định) | `Queue` | Một message được xử lý bởi một consumer cạnh tranh trong mỗi lượt delivery |
| `true` | `Topic` | Mỗi subscription phù hợp có thể nhận bản sao message theo quy tắc publish/subscribe |

Tên `"events"` **tự nó không quyết định** loại destination. Nếu template set `pubSubDomain=true` thì resolver sẽ tạo/resolve object Topic; consumer/listener cũng phải được cấu hình đúng domain và subscription. Việc đổi `pubSubDomain` có thể khiến message chuyển sang một đích có semantics khác, ngay cả khi tên chuỗi không đổi.

Với `Destination` object gán trực tiếp, Spring không dùng boolean này để tự đổi một Queue object thành Topic object. Object đang cung cấp đã biểu diễn một đích cụ thể.

## 5. defaultDestination: đưa trực tiếp một Destination object

Khi ứng dụng có một object `jakarta.jms.Destination`, cấu hình:

~~~java
import jakarta.jms.Destination;
import org.springframework.jms.core.JmsTemplate;

// connectionFactory và ordersQueue là các object đã được cấp trước.
JmsTemplate template = new JmsTemplate(connectionFactory);
template.setDefaultDestination(ordersQueue);
template.convertAndSend("order-101");
~~~

**Đây là trích đoạn minh họa**, `ordersQueue` có kiểu `Destination` do provider/container/lookup tạo trước. Không thể gọi `new Destination()` vì đây là interface.

Một Spring configuration có thể inject administered destination object:

~~~java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.Destination;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;

@Configuration
class ObjectDestinationConfig {

    @Bean("objectBasedJmsTemplate")
    JmsTemplate objectBasedJmsTemplate(
            ConnectionFactory connectionFactory,
            @Qualifier("ordersQueue") Destination ordersQueue) {

        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setDefaultDestination(ordersQueue);
        return template;
    }
}
~~~

Để chạy cấu hình này cần **bean `ordersQueue` có thật** và phải tương thích với `ConnectionFactory`. Ví dụ không tự cung cấp bean ấy vì cách tạo administered destination tùy provider/JNDI. Khi đã có object, Spring dùng trực tiếp thay vì nhận String để resolve theo tên.

**Lưu ý tính di động:** một `Queue` hoặc `Topic` object có thể mang thông tin riêng của provider. Không giả định object của Artemis luôn có thể đem sang IBM MQ hoặc một broker khác mà không chuyển đổi.

### 5.1. Hai setter là hai lựa chọn thay thế

Trong `JmsTemplate`, mặc định có thể được lưu dưới dạng một `Destination` **hoặc** một `String`. Không nên thiết lập cả hai rồi chờ hai cấu hình cùng có hiệu lực.

~~~java
template.setDefaultDestinationName("orders.a");
template.setDefaultDestination(ordersQueue);
~~~

Trong cách triển khai Spring Framework 6.x, setter gọi sau thay biểu diễn default trước. Vì vậy đoạn trên có default hiện tại là `ordersQueue`. Tránh dựa vào thứ tự setter giữa nhiều file cấu hình hoặc nhiều bean post-processor; **chỉ chọn một kiểu duy nhất cho một template**.

Các getter phản ánh kiểu đang lưu:

~~~java
template.getDefaultDestination();     // Destination hoặc null
template.getDefaultDestinationName(); // String hoặc null
~~~

Nếu đặt bằng `setDefaultDestinationName`, `getDefaultDestination()` trả `null` vẫn có thể là hành vi bình thường. Kiểm tra getter phù hợp với cách đã cấu hình.

## 6. Cấu hình Spring Boot với application.properties

Trong Spring Boot 3.x, khi dùng JMS starter và template được auto-configure, property để đặt tên đích mặc định là:

~~~properties
spring.jms.template.default-destination=demo.orders.default
spring.jms.pub-sub-domain=false
~~~

Dù tên property Boot là `default-destination`, giá trị ở đây là **chuỗi tên**, được Spring áp dụng cho cấu hình default destination của template, không phải object `Destination` Java.

| Cấu hình | Có tác dụng gì? |
| --- | --- |
| `spring.jms.template.default-destination=demo.orders.default` | Tên đích dùng khi `JmsTemplate` không nhận destination |
| `spring.jms.pub-sub-domain=false` | Resolve tên như queue (cấu hình mặc định) |
| `spring.jms.pub-sub-domain=true` | Resolve tên như topic |
| `spring.jms.template.receive-timeout=2s` | Giới hạn chờ của thao tác receive đồng bộ |
| `spring.artemis.mode=native` | Kết nối Artemis broker chạy ngoài ứng dụng |
| `@JmsListener(destination="demo.orders.default")` | Đích nhận của **một listener endpoint riêng**, không phụ thuộc default trên template |

Tên property Boot đúng là **`spring.jms.template.default-destination`**. Không tự giả định tồn tại property `spring.jms.template.default-destination-name`.

Nếu bạn tự khai báo `@Bean JmsTemplate`, Boot có thể không tạo bean mặc định và không tự áp dụng các property lên bean custom như bạn kỳ vọng. Lúc này hãy cấu hình rõ trên bean hoặc dùng cơ chế `JmsTemplateConfigurer` phù hợp phiên bản Boot. Một ứng dụng nên có một nguồn cấu hình dễ kiểm tra.

## 7. Ví dụ Java 17+ chạy được: default và explicit destination

Ví dụ này dùng **Spring Boot 3.x**, Java 17+, Artemis JMS client và **một Artemis broker ngoài ứng dụng**. Nó gửi hai message: một dùng default queue, một dùng destination tường minh. Hai `@JmsListener` giúp xác nhận hai message đến đúng nơi.

### 7.1. Chuẩn bị

Tạo dự án Maven trên [Spring Initializr](https://start.spring.io/) với:

- Group: `com.example`; Artifact: `jms-default-demo`; Java: **17+**.
- Dependency: **Spring for Apache ActiveMQ Artemis**, artifact `org.springframework.boot:spring-boot-starter-artemis`.
- Broker Artemis chạy ở `tcp://localhost:61616`, có tài khoản được quyền send/consume.
- Hai queue `demo.orders.default` và `demo.orders.explicit` được provision hoặc được broker tự tạo theo chính sách của nó.

Đặt biến môi trường `ARTEMIS_USER`, `ARTEMIS_PASSWORD`. Tệp `src/main/resources/application.properties`:

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=${ARTEMIS_USER}
spring.artemis.password=${ARTEMIS_PASSWORD}

spring.jms.pub-sub-domain=false
spring.jms.template.default-destination=demo.orders.default
~~~

`mode=native` **không khởi động broker** bên trong ứng dụng. Template sẽ được Boot cấu hình mặc định bằng tên `demo.orders.default` nếu điều kiện auto-configuration JMS được thỏa mãn.

Tệp `src/main/java/com/example/JmsDefaultDestinationApplication.java`:

~~~java
package com.example;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class JmsDefaultDestinationApplication {

    public static void main(String[] args) {
        SpringApplication.run(JmsDefaultDestinationApplication.class, args);
    }

    @Bean
    ApplicationRunner publish(JmsTemplate template) {
        return args -> {
            System.out.println(
                    "DEFAULT=" + template.getDefaultDestinationName());

            // Dùng default destination: demo.orders.default.
            template.convertAndSend("order-101");

            // Truyền destination tường minh: demo.orders.explicit.
            template.convertAndSend(
                    "demo.orders.explicit", "order-202");
        };
    }
}

@Component
class DefaultQueueConsumer {

    @JmsListener(destination = "demo.orders.default")
    public void receive(String payload) {
        System.out.println("DEFAULT_RECEIVED=" + payload);
    }
}

@Component
class ExplicitQueueConsumer {

    @JmsListener(destination = "demo.orders.explicit")
    public void receive(String payload) {
        System.out.println("EXPLICIT_RECEIVED=" + payload);
    }
}
~~~

Các lớp nằm chung một file Java: có đúng **một public class** với tên trùng filename; hai component còn lại là package-private, hợp lệ trong Java. Spring Boot có JMS infrastructure nhờ starter và tự phát hiện `@JmsListener` trong package được component-scan.

### 7.2. Chạy và output

Ở thư mục gốc dự án Maven:

~~~bash
mvn spring-boot:run
~~~

Nếu có Maven Wrapper trên Windows:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Khi broker và các queue/ACL đã chuẩn bị đúng và không có message tồn đọng, các dòng nghiệp vụ tiêu biểu:

~~~text
DEFAULT=demo.orders.default
DEFAULT_RECEIVED=order-101
EXPLICIT_RECEIVED=order-202
~~~

Có thêm startup logs của Spring; hai dòng `*_RECEIVED` có thể xuất hiện theo thứ tự ngược lại vì listeners xử lý bất đồng bộ. Đây là **stdout kỳ vọng khi điều kiện hạ tầng đúng**, không phải kết quả đã chạy thực tế với broker trong môi trường soạn bài.

**Đối chiếu:** `DEFAULT=...` xác nhận tên cấu hình trên `JmsTemplate`; listener thứ nhất nhận message gửi bằng overload một tham số; listener thứ hai nhận message gửi bằng overload hai tham số.

### 7.3. Tại sao default không thay đổi @JmsListener?

`@JmsListener(destination="...")` cấu hình một endpoint nhận message với destination riêng. Default của `JmsTemplate` chỉ được dùng cho thao tác trên **template ấy** mà không chỉ định đích. Listener container là thành phần khác và có cấu hình riêng; nó không mặc nhiên kế thừa default từ `JmsTemplate`.

Để chọn Queue/Topic cho listener, kiểm tra cấu hình listener container hoặc cấu hình Boot tương ứng. Việc đặt default queue trên template không khiến mọi listener tự nhận queue đó.

## 8. Java Config khi không muốn dùng Spring Boot property

Trong Spring Framework thuần hoặc khi chủ động cấu hình bean:

~~~java
package com.example.config;

import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;

@Configuration
public class JmsConfig {

    @Bean
    public JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setPubSubDomain(false);
        template.setDefaultDestinationName("demo.orders.default");
        return template;
    }
}
~~~

**Điều kiện để chạy:** bean `ConnectionFactory` phải tồn tại, thư viện provider phải tương thích với Jakarta JMS và broker có thể truy cập. Trong Spring thuần, nếu muốn listener, còn phải cấu hình `@EnableJms` và listener container factory phù hợp. Trong Spring Boot, không cần khai báo bean riêng nếu auto-configuration đã đáp ứng.

### 8.1. Nhiều template, mỗi template một mặc định

Một ứng dụng có thể có queue nghiệp vụ khác nhau, chẳng hạn:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;

@Configuration
class MultipleJmsTemplates {

    @Bean("orderTemplate")
    JmsTemplate orderTemplate(ConnectionFactory factory) {
        JmsTemplate t = new JmsTemplate(factory);
        t.setDefaultDestinationName("orders.requests");
        return t;
    }

    @Bean("billingTemplate")
    JmsTemplate billingTemplate(ConnectionFactory factory) {
        JmsTemplate t = new JmsTemplate(factory);
        t.setDefaultDestinationName("billing.requests");
        return t;
    }
}
~~~

Trong service, inject đúng template qua `@Qualifier("orderTemplate")` hoặc `@Qualifier("billingTemplate")`. Cấu hình nhiều template có nghĩa cần quản lý tên bean/ưu tiên injection rõ ràng; nếu Spring thấy nhiều bean cùng kiểu mà không có qualifier/primary, nó có thể không biết chọn bean nào.

Với nhiều broker/provider, mỗi template phải gắn với `ConnectionFactory` **đúng hệ thống**, vì default destination không tự đưa message xuyên các broker khác nhau.

## 9. Khi nào nên dùng tên mặc định và khi nào không?

**Nên dùng default destination khi:**

- Một service chủ yếu phát message tới **một queue hoặc topic ổn định**.
- Mỗi môi trường chạy có tên destination khác nhau và tên được đưa vào cấu hình thay vì viết cố định trong business code.
- Muốn giảm mã lặp và đảm bảo nhóm thao tác trong cùng một publisher dùng cùng đích.
- Có kiểm thử xác minh default phù hợp với contract giữa producer/consumer.

**Nên chỉ định destination tường minh khi:**

- Một service gửi nhiều loại message đến các destination khác nhau.
- Đích gửi thay đổi hợp lệ theo message type hoặc tenant.
- Cần nhìn thấy đích gửi ngay ở call site để review/audit dễ hơn.
- Muốn tránh phụ thuộc vào một default chung có thể bị cấu hình sai.
- Viết reusable library, không biết trước đích của ứng dụng tích hợp.

Ví dụ:

~~~java
// Publisher chuyên một queue: dùng default của template.
jmsTemplate.convertAndSend("order-101");

// Service đa chức năng: đích nêu rõ tại nơi gửi.
jmsTemplate.convertAndSend("audit.events", "audit-101");
jmsTemplate.convertAndSend("billing.commands", "invoice-202");
~~~

Đối với hệ thống đa tenant, **không** đặt default tùy theo từng request bằng `setDefaultDestinationName(tenantQueue)` trên một `JmsTemplate` singleton dùng chung. Nhiều thread có thể thay đổi state của cùng bean, dẫn đến gửi nhầm queue. Hãy dùng overload destination tường minh hoặc nhiều template được cấu hình cố định.

### 9.1. Default không quyết định định dạng message

Cả hai thuộc tính chỉ liên quan đến **đích gửi/nhận**. Chúng không thay đổi payload, không bật JSON conversion hay đặt `JMSCorrelationID`. `SimpleMessageConverter` mặc định xử lý `String` dưới dạng `TextMessage`, byte[] dưới dạng `BytesMessage` và các loại tương thích khác theo chính sách converter.

Nếu gửi POJO, hãy kiểm tra `MessageConverter` trước: không thể giả định một POJO bất kỳ tự biến thành JSON chỉ vì đã đặt `defaultDestinationName`. Ví dụ chạy được trong bài dùng `String` để tránh cần thêm JSON converter.

## 10. Mối quan hệ với JMSDestination, JMSReplyTo và sendAndReceive

Đừng nhầm **default của template** với **header của message**:

| Khái niệm | Mục đích |
| --- | --- |
| `JmsTemplate.defaultDestinationName` | Chọn tên destination nếu lời gọi template bỏ qua destination |
| `Message.getJMSDestination()` | Provider ghi destination thực tế của message được gửi |
| `Message.getJMSReplyTo()` | Nơi người gửi muốn nhận phản hồi (có thể null) |
| `Message.getJMSCorrelationID()` | Dữ liệu ứng dụng dùng để liên kết message/reply |
| `@JmsListener(destination = "...")` | Nơi một listener endpoint nhận message |

Khi gọi `jmsTemplate.convertAndSend("hello")`, Spring resolve default trước khi gửi; provider đặt `JMSDestination` theo destination của lần send đó. Default **không tự đặt `JMSReplyTo`** và không làm broker tự tạo reply.

Với `JmsTemplate.sendAndReceive(messageCreator)` (không destination), default được dùng làm đích **request**, còn cơ chế request/reply sử dụng reply destination riêng (thông thường một temporary queue) và thời gian chờ phù hợp. Không gửi reply trở lại default chỉ vì tên cấu hình giống nhau.

## 11. Receive, timeout và lỗi thường gặp

`receive()` và `receiveAndConvert()` của `JmsTemplate` cũng dùng default nếu không có destination. Đây là **nhận đồng bộ**, khác với listener chạy bất đồng bộ. Nếu không có message, nó có thể block lâu tùy timeout.

~~~java
import org.springframework.jms.core.JmsTemplate;

// template có ConnectionFactory và default destination hợp lệ.
jmsTemplate.setReceiveTimeout(2_000);
Object value = jmsTemplate.receiveAndConvert();
System.out.println(value == null ? "NO_MESSAGE" : value);
~~~

Với `receiveTimeout = 2000` ms, nếu hết thời gian chờ và không nhận được message, nó trả `null`. Ví dụ không có stdout cố định khi broker đang có message hoặc nhiều consumer cùng đọc. Trong Boot có thể đặt:

~~~properties
spring.jms.template.receive-timeout=2s
~~~

Bảng chẩn đoán:

| Tình huống | Nguyên nhân khả dĩ | Hướng giải quyết |
| --- | --- | --- |
| Không có default, gọi `convertAndSend(payload)` | Template chưa có default object/name | Đặt một mặc định hoặc gọi overload truyền destination |
| `getDefaultDestination() == null` nhưng gửi được | Đã cấu hình bằng tên String | Xem `getDefaultDestinationName()` |
| Message đi nhầm queue | Dùng sai overload hoặc default trỏ nhầm | Kiểm tra chữ ký hàm, tên default và tên truyền tường minh |
| Template chuyển sang topic | `pubSubDomain=true` | Đồng bộ domain giữa producer, consumer và resolver |
| Không tìm được destination | Sai tên, JNDI lookup fail, queue chưa provision | Kiểm tra resolver, broker resources và ACL |
| Boot property không có tác dụng | Đã tự tạo JmsTemplate bean, override auto config | Cấu hình lại bean custom hoặc dùng Boot configurer |
| Listener không nhận message | `@JmsListener` nghe destination khác, listener chưa chạy | Kiểm tra listener endpoint và broker queue depth |
| `receiveAndConvert()` chờ mãi | Receive timeout không phù hợp, queue rỗng | Cấu hình timeout; với long-running consumer dùng listener |
| Gửi được nhưng lỗi conversion | `MessageConverter` không hỗ trợ payload | Dùng String/byte[] hoặc converter phù hợp |
| Chạy ở dev, lỗi ở prod | Dev auto-create queue nhưng prod cần provision | Quản trị destination trên broker, quyền và naming |
| Nhiều request cùng thay default | Template singleton bị mutate đồng thời | Giữ default immutable sau cấu hình, dùng overload explicit |

Việc tạo được `JmsTemplate` bean không chứng minh broker đã online: client có thể mở kết nối khi gửi/nhận lần đầu. Kiểm tra cả `ConnectionFactory`, host/port, TLS, credentials, quyền queue/topic và network.

## 12. Những ngộ nhận cần tránh

1. **“defaultDestinationName là tên JMS header.”** Không. Nó là cấu hình Spring cho cách chọn destination.
2. **“defaultDestination nhận String.”** Không. Setter này nhận `Destination`; tên String dùng `setDefaultDestinationName`.
3. **“Đã đặt default thì mọi lệnh send đều gửi tới đó.”** Không. Overload có destination tường minh vẫn dùng đích được truyền.
4. **“Một String luôn được lookup qua JNDI.”** Không. Resolver mặc định là `DynamicDestinationResolver`.
5. **“Đặt defaultDestinationName tự tạo queue trên mọi broker.”** Không. Provision vật lý phụ thuộc provider và policy.
6. **“getDefaultDestination trả null là chưa cấu hình.”** Không hẳn. Có thể đang cấu hình dạng String; kiểm tra getter tên.
7. **“spring.jms.template.default-destination là property cấu hình toàn bộ @JmsListener.”** Không. Listener có destination riêng.
8. **“defaultDestinationName quyết định Queue hay Topic theo tên.”** Không. Với dynamic resolver, `pubSubDomain` quyết định domain.
9. **“Chỉ có một JmsTemplate cho cả hệ thống.”** Không. Có thể tạo nhiều template mỗi cái có default riêng, injection cần rõ ràng.
10. **“Muốn gửi động thì đổi default trong từng request.”** Nguy hiểm với singleton dùng đồng thời; nên chỉ định destination khi gọi.
11. **“Đặt default sẽ bật transaction hoặc bảo đảm exactly-once.”** Không. Ack, transaction, retry, redelivery và idempotency là các vấn đề riêng.
12. **“Một tham số String trong convertAndSend(String) là tên queue.”** Sai. Nó là payload; muốn truyền queue name phải dùng overload hai tham số hoặc `send(String, MessageCreator)`.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** `jmsTemplate.setDefaultDestinationName("queue.a")` đã gọi. `jmsTemplate.convertAndSend("hello")` gửi đến đâu?

**Đáp án:** `queue.a`. `"hello"` là payload và được converter chuyển thành JMS message.

**Câu 2.** Cùng template đó gọi `convertAndSend("queue.b", "hello")`. Default có được dùng không?

**Đáp án:** Không. Message đến `queue.b` do overload hai tham số truyền destination tường minh.

**Câu 3.** Khác nhau giữa `defaultDestination` và `defaultDestinationName` là gì?

**Đáp án:** Cái đầu là `Destination` object; cái sau là tên String được `DestinationResolver` chuyển thành object khi thao tác.

**Câu 4.** `DynamicDestinationResolver` mặc định giải quyết tên như loại gì?

**Đáp án:** Queue vì `pubSubDomain=false` theo mặc định. Set true nếu muốn topic, cùng với cấu hình consumer phù hợp.

**Câu 5.** Có thể dùng `defaultDestinationName` để tạo queue vật lý trong broker mà không cần kiểm tra cấu hình provider không?

**Đáp án:** Không. JMS client tạo đối tượng logic; việc broker auto-create/provision là cơ chế riêng.

**Câu 6.** Vì sao template cấu hình String vẫn gửi bình thường khi `getDefaultDestination()` trả null?

**Đáp án:** Vì default hiện đang được biểu diễn bằng `String`; `getDefaultDestinationName()` trả tên đã đặt.

**Câu 7.** Một listener chỉ khai báo `@JmsListener(destination="queue.x")`. Đổi default trên template thành `queue.y` có khiến listener chuyển sang `queue.y` không?

**Đáp án:** Không. Listener container quản lý destination của endpoint độc lập.

**Câu 8.** Ứng dụng gửi tới nhiều queue tùy tenant nên dùng `setDefaultDestinationName` trước mỗi send hay truyền queue vào send?

**Đáp án:** Truyền destination tường minh hoặc dùng template cố định được inject đúng chức năng; tránh mutate singleton đa luồng.

## Tài liệu tham khảo chính thức

- [Spring Framework — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): cách dùng `JmsTemplate`, `DestinationResolver`, `pubSubDomain` và default destination.
- [Spring Framework — Sending a Message](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html): overload `send`/`convertAndSend` có và không có destination.
- [Spring Framework 6.2 — JmsTemplate API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/core/JmsTemplate.html): setter/getter và các thao tác send/receive.
- [Spring Framework — DestinationResolver API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/support/destination/DestinationResolver.html): giao diện phân giải tên destination.
- [Spring Boot 3.5 — Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): thuộc tính `spring.jms.template.default-destination` và `spring.jms.pub-sub-domain`.
- [Spring Boot — JMS](https://docs.spring.io/spring-boot/reference/messaging/jms.html): Artemis native broker, auto-configured ConnectionFactory/JmsTemplate và listener.
- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): Queue, Topic, Destination và ngữ nghĩa JMS message.
