# BeanFactoryMessageChannelDestinationResolver và tên bean kênh

## 1. Bài toán phân giải tên channel

Trong Spring Messaging, publisher thường gửi message qua một đối tượng MessageChannel. Khi đã có channel, publisher có thể gọi send trực tiếp. Nhưng một số API gửi message nhận vào một chuỗi destination name thay vì một đối tượng channel. Khi đó cần một cơ chế chuyển tên thành channel tương ứng.

DestinationResolver<D> là strategy có nhiệm vụ phân giải tên String thành một destination có kiểu D. Với destination kiểu MessageChannel, Spring cung cấp BeanFactoryMessageChannelDestinationResolver.

Resolver này hiểu tên destination chính là tên bean của một MessageChannel trong Spring BeanFactory. Ví dụ, nếu ứng dụng khai báo bean tên ordersChannel, resolver có thể tìm bean đó và trả về đối tượng MessageChannel tương ứng.

Resolver chỉ tra cứu bean đã đăng ký. Nó không tự tạo channel, đăng ký handler, lưu message hay kết nối đến broker bên ngoài.

## 2. Hợp đồng và cách hoạt động

BeanFactoryMessageChannelDestinationResolver thuộc package org.springframework.messaging.core của module spring-messaging. Lớp triển khai:

- DestinationResolver<MessageChannel>: nhận tên destination và trả về MessageChannel.
- BeanFactoryAware: nhận BeanFactory sở hữu resolver thông qua callback setBeanFactory.

Phương thức chính:

~~~java
MessageChannel resolveDestination(String name);
~~~

Khi phân giải, resolver tra cứu bean theo tên và yêu cầu kiểu MessageChannel. Về bản chất, thao tác lookup tương đương:

~~~java
beanFactory.getBean(name, MessageChannel.class);
~~~

Tên truyền vào có thể là bean name hoặc alias đã đăng ký trong BeanFactory. Bean được tìm thấy phải tương thích với MessageChannel.

### 2.1. Hai constructor

Lớp cung cấp hai cách khởi tạo:

| Constructor | Mục đích |
| --- | --- |
| BeanFactoryMessageChannelDestinationResolver() | Dùng khi resolver là Spring bean và được container inject BeanFactory |
| BeanFactoryMessageChannelDestinationResolver(beanFactory) | Dùng khi tự tạo resolver trong code và muốn truyền BeanFactory ngay lúc khởi tạo |

Ví dụ tạo resolver thủ công:

~~~java
BeanFactoryMessageChannelDestinationResolver resolver =
    new BeanFactoryMessageChannelDestinationResolver(beanFactory);

MessageChannel channel = resolver.resolveDestination("ordersChannel");
~~~

Nếu dùng constructor không tham số nhưng tự khởi tạo resolver bằng toán tử new, cần gọi setBeanFactory trước khi resolveDestination. Nếu BeanFactory chưa được cấu hình, resolver báo IllegalStateException vì không thể thực hiện lookup.

### 2.2. Xử lý lỗi phân giải

Có hai nhóm lỗi cần phân biệt:

- **Chưa cấu hình BeanFactory**: resolver kiểm tra trạng thái và ném IllegalStateException với thông báo không có BeanFactory được cấu hình.
- **Lookup thất bại**: nếu BeanFactory không tìm thấy tên bean hoặc bean không đúng kiểu MessageChannel, BeansException được bắt và bọc trong DestinationResolutionException. Exception gốc được giữ làm cause.

Nhờ vậy, code gọi có thể bắt DestinationResolutionException để xử lý lỗi destination thống nhất, đồng thời vẫn kiểm tra cause để tìm nguyên nhân cụ thể.

Không nên bắt lỗi rồi âm thầm bỏ qua. Một tên bean sai có thể khiến message không được gửi đến đúng luồng xử lý nghiệp vụ.

## 3. Đặt tên cho MessageChannel bean

Tên bean mặc định thường lấy từ tên phương thức @Bean. Ví dụ:

~~~java
@Configuration
public class MessagingConfiguration {

    @Bean
    public MessageChannel ordersChannel() {
        return new ExecutorSubscribableChannel();
    }
}
~~~

Tên bean trong ví dụ là ordersChannel. Có thể phân giải bằng:

~~~java
MessageChannel channel = resolver.resolveDestination("ordersChannel");
~~~

Nếu muốn tên bean không phụ thuộc tên phương thức Java, khai báo tên tường minh:

~~~java
@Bean(name = "ordersChannel")
public MessageChannel orderEventsChannel() {
    return new ExecutorSubscribableChannel();
}
~~~

Tên bean vẫn là ordersChannel dù phương thức Java được đặt là orderEventsChannel.

Một bean có thể có nhiều tên thông qua alias:

~~~java
@Bean(name = {"ordersChannel", "orderEvents"})
public MessageChannel orderEventsChannel() {
    return new ExecutorSubscribableChannel();
}
~~~

Trong trường hợp này, ordersChannel là tên bean chính và orderEvents là alias. BeanFactory có thể dùng cả hai tên để tra cứu cùng một bean.

Khi đổi tên bean, hãy cập nhật mọi nơi truyền destination name hoặc giữ alias tương thích. Nếu tên được viết rải rác trong nhiều service, có thể gom chúng thành hằng số để tránh lỗi chính tả và giảm chi phí refactor.

## 4. Luồng phân giải destination

~~~mermaid
flowchart TD
    P[Publisher gọi template với destination name] --> T[GenericMessagingTemplate]
    T --> R[BeanFactoryMessageChannelDestinationResolver]
    R --> F[BeanFactory tra cứu tên và kiểu MessageChannel]
    F -->|Tìm thấy| C[MessageChannel bean]
    F -->|Không tìm thấy hoặc sai kiểu| E[DestinationResolutionException]
    C --> S[channel.send(message)]
~~~

Quy trình:

1. Publisher gọi API gửi theo tên, ví dụ convertAndSend với destination name ordersChannel.
2. GenericMessagingTemplate yêu cầu DestinationResolver phân giải tên.
3. BeanFactoryMessageChannelDestinationResolver gọi BeanFactory để lấy bean có tên đó và kiểu MessageChannel.
4. Nếu lookup thành công, template gửi message qua channel được trả về.
5. Nếu lookup thất bại, resolver ném DestinationResolutionException.

Resolver không quyết định channel dispatch message theo cách nào. Việc đó thuộc implementation cụ thể, chẳng hạn ExecutorSubscribableChannel hoặc channel của Spring Integration.

## 5. Tích hợp với GenericMessagingTemplate

GenericMessagingTemplate là messaging template làm việc với MessageChannel và cung cấp API gửi/nhận theo destination name. Lớp này triển khai BeanFactoryAware.

Khi GenericMessagingTemplate được Spring quản lý, container gọi setBeanFactory. Implementation của template tạo BeanFactoryMessageChannelDestinationResolver từ BeanFactory được cung cấp. Do đó, ứng dụng có thể gọi API theo tên bean mà không cần tự tạo resolver cho từng lần gửi.

Ví dụ cấu hình:

~~~java
@Configuration
public class MessagingConfiguration {

    @Bean
    public MessageChannel ordersChannel() {
        return new ExecutorSubscribableChannel();
    }

    @Bean
    public GenericMessagingTemplate messagingTemplate() {
        return new GenericMessagingTemplate();
    }
}
~~~

Sau khi context được khởi tạo, gửi message bằng tên bean:

~~~java
messagingTemplate.convertAndSend("ordersChannel", "order-88");
~~~

Template phân giải ordersChannel thành MessageChannel bean, chuyển payload thành Message bằng MessageConverter, rồi gọi send trên channel đó.

### 5.1. Tạo template ngoài Spring container

Nếu tự tạo GenericMessagingTemplate bằng toán tử new, Spring container không tự gọi BeanFactoryAware. Cần cấu hình resolver thủ công:

~~~java
GenericMessagingTemplate template = new GenericMessagingTemplate();

template.setDestinationResolver(
    new BeanFactoryMessageChannelDestinationResolver(beanFactory)
);

template.convertAndSend("ordersChannel", "order-88");
~~~

Cũng có thể gọi setBeanFactory(beanFactory) trên template vì nó triển khai BeanFactoryAware. Cách cấu hình tường minh hữu ích khi muốn thay strategy phân giải mặc định hoặc dùng resolver tùy chỉnh.

## 6. Ví dụ hoàn chỉnh với Java 17+

Ví dụ sau tạo channel bean tên ordersChannel, đăng ký handler và gửi message thông qua GenericMessagingTemplate. Publisher chỉ truyền tên bean; resolver tìm channel trong Spring context.

Cấu trúc dự án:

~~~text
bean-channel-resolver-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── BeanChannelResolverDemo.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>bean-channel-resolver-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>7.0.10</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>7.0.10</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>BeanChannelResolverDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/BeanChannelResolverDemo.java**

~~~java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.SubscribableChannel;
import org.springframework.messaging.core.GenericMessagingTemplate;
import org.springframework.messaging.support.ExecutorSubscribableChannel;

@Configuration
class MessagingConfiguration {

    @Bean
    public SubscribableChannel ordersChannel() {
        return new ExecutorSubscribableChannel();
    }

    @Bean
    public GenericMessagingTemplate messagingTemplate() {
        return new GenericMessagingTemplate();
    }
}

public class BeanChannelResolverDemo {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(MessagingConfiguration.class)) {

            SubscribableChannel channel =
                context.getBean("ordersChannel", SubscribableChannel.class);

            channel.subscribe(message ->
                System.out.println("received=" + message.getPayload())
            );

            GenericMessagingTemplate template =
                context.getBean(GenericMessagingTemplate.class);

            template.convertAndSend("ordersChannel", "order-88");

            MessageChannel resolved =
                context.getBeanFactory().getBean("ordersChannel", MessageChannel.class);

            System.out.println("resolvedType=" + resolved.getClass().getSimpleName());
        }
    }
}
~~~

Chạy tại thư mục chứa pom.xml:

~~~bash
mvn -q clean compile exec:java
~~~

Stdout dự kiến:

~~~text
received=order-88
resolvedType=ExecutorSubscribableChannel
~~~

GenericMessagingTemplate là Spring bean nên BeanFactoryAware được container gọi tự động. Khi convertAndSend nhận destination name ordersChannel, resolver tra cứu bean đó với kiểu MessageChannel. Handler được đăng ký trên cùng channel và nhận payload order-88.

Biến resolved chỉ minh họa lookup trực tiếp bằng BeanFactory. Publisher trong ứng dụng thường không cần tự tra cứu bean nếu đã gửi qua template có destination resolver.

## 7. Phân biệt tên bean và destination của broker

Tên bean MessageChannel và destination của một broker là hai khái niệm khác nhau:

| Chuỗi | Ý nghĩa |
| --- | --- |
| ordersChannel | Tên bean MessageChannel trong Spring BeanFactory |
| orderEvents | Có thể là alias của bean MessageChannel nếu đã khai báo |
| /topic/orders | Thường là destination của STOMP broker |
| queue.orders | Có thể là destination theo quy ước của broker hoặc ứng dụng |

BeanFactoryMessageChannelDestinationResolver không kết nối đến RabbitMQ, ActiveMQ hoặc STOMP broker để tìm destination. Nó chỉ tra cứu MessageChannel bean trong BeanFactory được cấu hình.

Nếu cần gửi đến destination của broker bên ngoài, hãy dùng template hoặc integration adapter phù hợp với giao thức đó. Không truyền một STOMP destination như /topic/orders vào resolver với kỳ vọng nó tự tìm thấy broker destination.

## 8. Lỗi thường gặp

| Biểu hiện | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy channel bean | Destination name không trùng tên bean hoặc alias | Kiểm tra tên @Bean và chuỗi truyền vào template |
| Bean tồn tại nhưng resolver báo lỗi | Bean không triển khai MessageChannel | Khai báo bean đúng kiểu hoặc sửa destination name |
| No BeanFactory configured | Resolver tự tạo nhưng chưa được inject BeanFactory | Dùng constructor nhận BeanFactory hoặc gọi setBeanFactory |
| DestinationResolutionException | BeanFactory lookup thất bại hoặc bean không thể phân giải | Kiểm tra exception gốc trong cause |
| Gửi đến /topic/orders nhưng không có bean tương ứng | Nhầm tên bean với STOMP destination | Dùng template và broker phù hợp với giao thức |
| Đổi tên phương thức @Bean làm hỏng việc gửi | Tên bean mặc định thay đổi theo tên phương thức | Đặt tên bean tường minh hoặc duy trì alias |
| Có nhiều channel và chọn nhầm | Tên bean không mô tả rõ mục đích | Dùng tên channel thể hiện luồng nghiệp vụ |

## 9. Checklist triển khai

- [ ] Khai báo MessageChannel dưới dạng Spring bean.
- [ ] Chọn tên bean ổn định và thể hiện mục đích của channel.
- [ ] Dùng đúng bean name hoặc alias khi gọi API gửi theo destination name.
- [ ] Để Spring quản lý GenericMessagingTemplate nếu muốn BeanFactory được inject tự động.
- [ ] Nếu tự tạo resolver, truyền BeanFactory vào constructor hoặc gọi setBeanFactory.
- [ ] Xử lý DestinationResolutionException khi tên không hợp lệ hoặc bean sai kiểu.
- [ ] Phân biệt tên bean MessageChannel với destination của STOMP, JMS hoặc broker khác.
- [ ] Không giả định resolver tự tạo channel, đăng ký handler hoặc lưu message bền vững.

## 10. Tài liệu tham khảo

- [Spring Framework API — BeanFactoryMessageChannelDestinationResolver](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/core/BeanFactoryMessageChannelDestinationResolver.html)
- [Spring Framework API — DestinationResolver](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/core/DestinationResolver.html)
- [Spring Framework API — GenericMessagingTemplate](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/core/GenericMessagingTemplate.html)
- [Spring Framework API — DestinationResolutionException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/core/DestinationResolutionException.html)
- [Spring Framework API — MessageChannel](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageChannel.html)
