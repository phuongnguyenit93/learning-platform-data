# Đích mặc định và phân giải tên đích bằng DestinationResolver trong Spring Messaging

## 1. Destination trong mô hình gửi và nhận

Trong Spring Messaging, một message được gửi tới một **destination**. Destination là đối tượng đích mà template sử dụng để gửi, nhận hoặc trao đổi request-reply. Kiểu dữ liệu của destination phụ thuộc implementation: với GenericMessagingTemplate, destination là MessageChannel; với template tích hợp JMS, destination có thể là đối tượng JMS Destination.

Spring tách hai cách chỉ định đích:

1. **Truyền destination trực tiếp:** caller đã có đối tượng đích và truyền nó vào phương thức send/convertAndSend.
2. **Truyền tên destination:** caller đưa một String name; template dùng DestinationResolver để tìm đối tượng đích tương ứng.

Ngoài ra, template có thể được cấu hình một **default destination** để những phương thức không nhận tham số destination biết phải gửi hoặc nhận ở đâu.

Ba khái niệm cần phân biệt:

- **Default destination:** đối tượng đích mặc định được template lưu sẵn.
- **Destination name:** chuỗi tên mà caller truyền vào, ví dụ "ordersChannel".
- **DestinationResolver<D>:** chiến lược chuyển String name thành một đối tượng destination kiểu D.

Default destination và DestinationResolver giải quyết hai nhu cầu khác nhau. Default destination phục vụ lời gọi không nêu đích; resolver phục vụ lời gọi có tên đích.

## 2. Default destination trong MessageSendingOperations

Spring định nghĩa MessageSendingOperations<D> cho các thao tác gửi message. Các phương thức có thể nhận destination trực tiếp hoặc dùng destination mặc định:

~~~java
template.send(destination, message);
template.send(message);

template.convertAndSend(destination, payload);
template.convertAndSend(payload);
~~~

Những phương thức có tham số destination sử dụng đối tượng được truyền vào. Những phương thức không có tham số destination sử dụng default destination đã cấu hình trên template.

Lớp cơ sở AbstractMessageSendingTemplate<D> cung cấp:

- setDefaultDestination(D destination): đặt destination mặc định.
- getDefaultDestination(): lấy destination đang cấu hình.
- getRequiredDefaultDestination(): lấy destination bắt buộc; nếu chưa có sẽ ném IllegalStateException.

Ví dụ khái niệm:

~~~java
template.setDefaultDestination(ordersChannel);

// Gửi trực tiếp tới destination mặc định.
template.convertAndSend("order-created");

// Gửi tới destination khác được chỉ định rõ.
template.convertAndSend(paymentsChannel, "payment-request");
~~~

Nếu chưa cấu hình default destination mà gọi phương thức không có tham số destination, template sẽ báo lỗi vì không biết gửi tới đâu. Không nên dựa vào một destination ngầm định không được khai báo trong cấu hình.

### 2.1. Default destination của GenericMessagingTemplate

GenericMessagingTemplate kế thừa AbstractDestinationResolvingMessagingTemplate<MessageChannel>. Vì kiểu D của template là MessageChannel, default destination của nó là **một MessageChannel instance**, không phải tên channel dạng String.

~~~java
MessageChannel ordersChannel = ...;

GenericMessagingTemplate template = new GenericMessagingTemplate();
template.setDefaultDestination(ordersChannel);

template.convertAndSend("order-created");
~~~

Ở đây, "order-created" là payload. Template gửi payload vào MessageChannel đã được cấu hình làm default destination.

Nếu muốn chỉ định channel bằng tên bean, dùng overload nhận String name:

~~~java
template.convertAndSend("ordersChannel", "order-created");
~~~

Phương thức này đi qua DestinationResolver; nó không đọc default destination để thay thế cho việc phân giải tên.

## 3. DestinationResolver<D> là gì?

DestinationResolver<D> là functional interface trong package org.springframework.messaging.core. Nó định nghĩa một phương thức:

~~~java
D resolveDestination(String name);
~~~

Nhiệm vụ của resolver là chuyển một tên String thành đối tượng destination thực tế kiểu D. Với GenericMessagingTemplate, D là MessageChannel.

Ví dụ ánh xạ đơn giản:

~~~java
DestinationResolver<MessageChannel> resolver = name -> {
    if ("orders".equals(name)) {
        return ordersChannel;
    }
    throw new DestinationResolutionException(
        "Unknown destination: " + name
    );
};
~~~

Một resolver phải trả về destination khác null. Nếu tên không tồn tại hoặc không thể phân giải, implementation nên ném DestinationResolutionException với thông tin đủ để chẩn đoán.

Resolver không tự định nghĩa cách gửi message. Nó chỉ giải quyết tên thành đối tượng đích; template tiếp tục gọi send/receive trên destination đã phân giải.

### 3.1. AbstractDestinationResolvingMessagingTemplate

AbstractDestinationResolvingMessagingTemplate<D> mở rộng AbstractMessagingTemplate<D> và bổ sung các thao tác dùng tên destination dạng String, ví dụ:

~~~java
template.send("orders", message);
template.convertAndSend("orders", payload);
template.receive("orders");
template.sendAndReceive("orders", requestMessage);
~~~

Template phải được cấu hình DestinationResolver bằng setDestinationResolver(...). Nếu chưa có resolver, những phương thức cần phân giải tên sẽ ném IllegalArgumentException. Nếu resolver không tìm thấy tên, lỗi phân giải thường được biểu diễn bằng DestinationResolutionException.

Lớp này không tự cung cấp resolver mặc định. Implementation cụ thể hoặc cấu hình ứng dụng phải cung cấp chiến lược phù hợp.

## 4. GenericMessagingTemplate và BeanFactoryMessageChannelDestinationResolver

GenericMessagingTemplate là template tổng quát để gửi, nhận và request-reply qua MessageChannel. Nó hỗ trợ cả destination object và destination name.

GenericMessagingTemplate triển khai BeanFactoryAware. Khi được Spring quản lý và nhận BeanFactory, phương thức setBeanFactory(...) cấu hình BeanFactoryMessageChannelDestinationResolver làm resolver.

BeanFactoryMessageChannelDestinationResolver diễn giải destination name như **tên bean của một MessageChannel** và tra cứu bean đó trong BeanFactory.

Ví dụ Spring configuration:

~~~java
@Configuration
class MessagingConfig {

    @Bean
    MessageChannel ordersChannel() {
        return new ExecutorSubscribableChannel();
    }

    @Bean
    GenericMessagingTemplate messagingTemplate(
            ConfigurableListableBeanFactory beanFactory,
            MessageChannel ordersChannel) {

        GenericMessagingTemplate template = new GenericMessagingTemplate();
        template.setBeanFactory(beanFactory);
        template.setDefaultDestination(ordersChannel);
        return template;
    }
}
~~~

Với cấu hình này:

- Gọi template.convertAndSend("ordersChannel", payload) sẽ tra cứu bean MessageChannel có tên ordersChannel.
- Gọi template.convertAndSend(payload) sẽ gửi tới instance ordersChannel đã đặt làm default destination.
- Gọi template.convertAndSend(otherChannel, payload) sẽ gửi trực tiếp tới channel được truyền vào.

Tên bean phải đúng và bean phải là một MessageChannel có thể sử dụng. Resolver này là cơ chế tra cứu bean trong BeanFactory; nó không tự tạo một channel mới chỉ vì có tên chưa tồn tại.

### 4.1. Khởi tạo template thủ công

Nếu tự tạo GenericMessagingTemplate bằng new và không có Spring container gọi setBeanFactory, resolver sẽ chưa được cấu hình tự động.

Có thể thiết lập resolver trực tiếp:

~~~java
DefaultListableBeanFactory beanFactory = new DefaultListableBeanFactory();

beanFactory.registerSingleton("ordersChannel", ordersChannel);

GenericMessagingTemplate template = new GenericMessagingTemplate();
template.setDestinationResolver(
    new BeanFactoryMessageChannelDestinationResolver(beanFactory)
);
~~~

Hoặc gọi template.setBeanFactory(beanFactory), vì GenericMessagingTemplate tự tạo BeanFactoryMessageChannelDestinationResolver khi nhận BeanFactory.

Cần phân biệt hai việc:

- setDefaultDestination(ordersChannel): cấu hình đích mặc định dưới dạng đối tượng.
- setDestinationResolver(...): cấu hình cách tìm destination từ String name.

Có thể cấu hình cả hai trên cùng một template.

## 5. Viết custom DestinationResolver

Khi destination không phải bean trong BeanFactory, có thể viết resolver theo quy tắc của ứng dụng. Ví dụ, ánh xạ alias tới channel qua Map:

~~~java
Map<String, MessageChannel> channels = Map.of(
    "orders", ordersChannel,
    "payments", paymentsChannel
);

DestinationResolver<MessageChannel> resolver = name -> {
    MessageChannel channel = channels.get(name);

    if (channel == null) {
        throw new DestinationResolutionException(
            "Destination not found: " + name
        );
    }

    return channel;
};

GenericMessagingTemplate template = new GenericMessagingTemplate();
template.setDestinationResolver(resolver);

template.convertAndSend("orders", "order-created");
template.convertAndSend("payments", "payment-request");
~~~

Resolver có thể dùng một registry, cấu hình tenant, metadata hoặc dịch vụ tra cứu khác. Tuy nhiên, không nên cho phép một chuỗi destination do client tự gửi quyết định tùy ý channel nội bộ. Hãy xác thực tên, kiểm tra quyền truy cập và giới hạn danh sách destination có thể dùng.

### 5.1. Phân biệt tên hợp lệ và lỗi phân giải

Nên định nghĩa hành vi rõ ràng khi không tìm thấy destination:

~~~java
DestinationResolver<MessageChannel> resolver = name -> {
    MessageChannel channel = channels.get(name);

    if (channel == null) {
        throw new DestinationResolutionException(
            "Unknown messaging destination: " + name
        );
    }

    return channel;
};
~~~

Không trả null để biểu diễn tên không hợp lệ. Theo contract của DestinationResolver, kết quả phân giải phải là một destination thực tế, khác null. Lỗi nên nêu tên logic đang tìm để log và xử lý cấu hình dễ hơn, nhưng tránh đưa thông tin bí mật vào thông báo lỗi.

## 6. Cache kết quả phân giải

Nếu quá trình phân giải tốn chi phí, ví dụ phải tra cứu registry bên ngoài, có thể dùng CachingDestinationResolverProxy<D>. Class này bọc một DestinationResolver khác và cache những kết quả resolveDestination(name) thành công.

~~~java
DestinationResolver<MessageChannel> targetResolver = name -> {
    // Tra cứu từ registry hoặc hệ thống cấu hình.
    return channelRegistry.lookup(name);
};

CachingDestinationResolverProxy<MessageChannel> cachedResolver =
    new CachingDestinationResolverProxy<>(targetResolver);

GenericMessagingTemplate template = new GenericMessagingTemplate();
template.setDestinationResolver(cachedResolver);
~~~

Caching hữu ích khi kết quả phân giải ổn định và lookup đắt đỏ. Nếu mapping thay đổi thường xuyên, cache có thể giữ tham chiếu cũ; cần thiết kế vòng đời cache, khả năng invalidation và thời điểm cập nhật resolver phù hợp. Không dùng cache như cách che giấu lỗi cấu hình hoặc destination đã bị thu hồi.

## 7. Luồng xử lý khi gửi tới tên destination

Khi gọi:

~~~java
template.convertAndSend("orders", payload);
~~~

Luồng khái quát:

1. Template nhận String destinationName là "orders".
2. Template gọi DestinationResolver.resolveDestination("orders").
3. Resolver trả về một destination, ví dụ ordersChannel.
4. Template chuyển payload thành Message bằng MessageConverter.
5. Template gửi Message tới destination đã phân giải.

Nếu resolver chưa được cấu hình, lời gọi dùng tên không thể tiếp tục. Nếu tên không tồn tại, resolver ném DestinationResolutionException. Nếu phân giải thành công nhưng channel từ chối hoặc không thể gửi, lỗi phát sinh ở bước gửi sẽ thuộc nhóm lỗi messaging/delivery tương ứng.

Điểm quan trọng: resolver chỉ quyết định **destination object nào tương ứng với tên**. Nó không quyết định payload chuyển đổi ra sao, consumer nào xử lý message hay message có được lưu bền vững hay không.

## 8. Ví dụ Java 17+ chạy độc lập

Ví dụ sau minh họa đồng thời ba trường hợp: phân giải tên bean, gửi tới default destination và sử dụng custom resolver. Channel dùng ExecutorSubscribableChannel với dispatch đồng bộ theo cấu hình mặc định.

**Cấu trúc dự án**

~~~text
destination-resolver-demo/
  pom.xml
  src/
    main/
      java/
        demo/
          DestinationResolverDemo.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>destination-resolver-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>6.2.18</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-beans</artifactId>
            <version>6.2.18</version>
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
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/DestinationResolverDemo.java**

~~~java
package demo;

import org.springframework.beans.factory.support.DefaultListableBeanFactory;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.SubscribableChannel;
import org.springframework.messaging.core.DestinationResolutionException;
import org.springframework.messaging.core.DestinationResolver;
import org.springframework.messaging.core.GenericMessagingTemplate;
import org.springframework.messaging.support.ExecutorSubscribableChannel;

public class DestinationResolverDemo {

    public static void main(String[] args) {
        SubscribableChannel ordersChannel = new ExecutorSubscribableChannel();
        ordersChannel.subscribe(message ->
            System.out.println("received=" + message.getPayload())
        );

        DefaultListableBeanFactory beanFactory = new DefaultListableBeanFactory();
        beanFactory.registerSingleton("ordersChannel", ordersChannel);

        GenericMessagingTemplate template = new GenericMessagingTemplate();
        template.setBeanFactory(beanFactory);
        template.setDefaultDestination((MessageChannel) ordersChannel);

        template.convertAndSend("ordersChannel", "by-name");
        template.convertAndSend("default-destination");

        DestinationResolver<MessageChannel> customResolver = name -> {
            if ("orders".equals(name)) {
                return ordersChannel;
            }

            throw new DestinationResolutionException(
                "Unknown destination: " + name
            );
        };

        GenericMessagingTemplate customTemplate = new GenericMessagingTemplate();
        customTemplate.setDestinationResolver(customResolver);
        customTemplate.setDefaultDestination((MessageChannel) ordersChannel);

        customTemplate.convertAndSend("orders", "custom");

        try {
            customTemplate.convertAndSend("missing", "not-sent");
        }
        catch (DestinationResolutionException ex) {
            System.out.println("missingDestination=failed");
        }
    }
}
~~~

Chạy từ thư mục destination-resolver-demo:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.DestinationResolverDemo
~~~

**stdout**

~~~text
received=by-name
received=default-destination
received=custom
missingDestination=failed
~~~

Giải thích:

- Lần gửi đầu tiên phân giải tên bean ordersChannel bằng BeanFactoryMessageChannelDestinationResolver.
- Lần thứ hai không truyền tên destination nên template dùng default destination.
- customTemplate dùng resolver tự định nghĩa, ánh xạ alias orders.
- Tên missing gây DestinationResolutionException và message không được gửi.

## 9. Lỗi thường gặp

1. **Nhầm default destination với destination name:** default destination là đối tượng D; với GenericMessagingTemplate, đó là MessageChannel. Tên String cần resolver.
2. **Quên cấu hình default destination:** phương thức send/convertAndSend không có tham số đích sẽ thất bại nếu default chưa được đặt.
3. **Quên cấu hình resolver:** phương thức nhận String destinationName cần resolver. GenericMessagingTemplate được Spring quản lý nhận resolver qua BeanFactoryAware; khởi tạo thủ công cần cấu hình rõ.
4. **Đăng ký sai bean name:** BeanFactoryMessageChannelDestinationResolver tra cứu đúng tên bean MessageChannel. Sai tên hoặc sai kiểu sẽ không phân giải được.
5. **Cho rằng resolver tự tạo channel:** resolver có thể tra cứu hoặc ánh xạ theo implementation. BeanFactoryMessageChannelDestinationResolver tra cứu bean đã đăng ký.
6. **Trả về null:** contract yêu cầu destination khác null. Hãy ném DestinationResolutionException khi không tìm thấy.
7. **Dùng default destination làm fallback cho mọi tên sai:** lời gọi có tên đi qua resolver. Tên sai cần được báo lỗi; không tự gửi sang default vì có thể làm sai luồng nghiệp vụ.
8. **Không kiểm soát destination do client cung cấp:** tên đích có thể ảnh hưởng routing. Xác thực và phân quyền trước khi phân giải.
9. **Cache mapping động mà không invalidation:** CachingDestinationResolverProxy phù hợp khi kết quả ổn định; nếu registry thay đổi, cache có thể giữ destination cũ.
10. **Nhầm resolver trong Spring Messaging với resolver trong Spring JMS:** package và generic type khác nhau. Hãy kiểm tra import để dùng đúng abstraction cho loại destination đang làm việc.

## 10. Khi nào dùng từng cách?

| Nhu cầu | Cách dùng |
|---|---|
| Ứng dụng luôn gửi tới một channel chính | setDefaultDestination(channel) |
| Caller biết sẵn channel object | send(channel, message) hoặc convertAndSend(channel, payload) |
| Caller chỉ biết tên bean channel | GenericMessagingTemplate + BeanFactoryMessageChannelDestinationResolver |
| Cần alias hoặc quy tắc định tuyến riêng | Custom DestinationResolver<MessageChannel> |
| Tra cứu destination tốn chi phí, kết quả ổn định | CachingDestinationResolverProxy |
| Cần gửi tới tên destination không có resolver mặc định | Cấu hình setDestinationResolver(...) trước khi gọi |

## 11. Kết luận

Default destination giúp template gửi hoặc nhận khi caller không chỉ định đích. DestinationResolver cho phép caller dùng tên String và để template tìm đối tượng destination tương ứng. Trong GenericMessagingTemplate, destination là MessageChannel; BeanFactoryMessageChannelDestinationResolver tra cứu channel theo tên bean trong BeanFactory.

Hãy cấu hình default destination cho luồng gửi mặc định, cấu hình resolver cho các lời gọi theo tên và xử lý rõ lỗi không phân giải được. Nếu destination thay đổi theo tenant, quyền hoặc dữ liệu client gửi lên, cần xác thực tên trước khi sử dụng để tránh gửi nhầm hoặc mở đường truy cập channel không được phép.

## 12. Tài liệu tham khảo

- [MessageSendingOperations — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/core/MessageSendingOperations.html)
- [AbstractMessageSendingTemplate — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/core/AbstractMessageSendingTemplate.html)
- [DestinationResolver — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/core/DestinationResolver.html)
- [AbstractDestinationResolvingMessagingTemplate — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/core/AbstractDestinationResolvingMessagingTemplate.html)
- [GenericMessagingTemplate — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/core/GenericMessagingTemplate.html)
- [BeanFactoryMessageChannelDestinationResolver — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/core/BeanFactoryMessageChannelDestinationResolver.html)
- [CachingDestinationResolverProxy — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/core/CachingDestinationResolverProxy.html)