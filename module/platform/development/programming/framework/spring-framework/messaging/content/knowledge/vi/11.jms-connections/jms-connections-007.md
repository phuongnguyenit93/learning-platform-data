# DestinationResolver, DynamicDestinationResolver và JndiDestinationResolver

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao Spring JMS cần một cơ chế chuyển tên destination thành đối tượng JMS Destination.
- Mô tả hợp đồng DestinationResolver và cách JmsTemplate sử dụng resolver.
- Phân biệt DynamicDestinationResolver với JndiDestinationResolver.
- Chọn đúng Queue hoặc Topic thông qua pubSubDomain.
- Cấu hình JNDI environment, cache và fallback sang dynamic destination.
- Hiểu giới hạn của việc tạo dynamic destination và sự khác nhau giữa destination thường với temporary destination.
- Nhận diện lỗi do sai tên JNDI, sai loại Queue/Topic, cache cũ hoặc khác biệt giữa các JMS provider.
- Viết cấu hình và kiểm thử resolver mà không nhầm DestinationResolver của Spring JMS với interface cùng tên trong Spring Messaging.

## 1. Vì sao phải phân giải destination?

JMS gửi và nhận thông điệp thông qua một đối tượng Destination. Trong thực tế, code nghiệp vụ thường chỉ biết tên logic như:

- `orders.in`: queue nhận lệnh tạo đơn hàng.
- `orders.events`: topic phát sự kiện đơn hàng.
- `tenant.42.notifications`: destination theo tenant được xác định lúc chạy.
- `java:comp/env/jms/OrdersQueue`: tên JNDI của một destination do môi trường quản trị cung cấp.

Một API như JmsTemplate có thể nhận tên destination dưới dạng String. Nhưng JMS provider cần đối tượng Queue hoặc Topic thực tế để tạo MessageProducer hoặc MessageConsumer. Spring cần chuyển tên String thành đối tượng Destination trước khi thực hiện thao tác JMS.

Đó là trách nhiệm của DestinationResolver.

~~~mermaid
flowchart LR
    A["Tên destination<br/>String"]
    B["DestinationResolver"]
    C["JMS Destination"]
    D["JmsTemplate"]
    E["JMS provider"]

    A --> B --> C
    D --> B
    C --> D
    D --> E
~~~

Resolver giúp tách cách đặt tên destination khỏi code gửi/nhận. Ứng dụng có thể đổi từ cách phân giải động sang JNDI bằng cấu hình mà không phải thay mọi lời gọi nghiệp vụ.

## 2. DestinationResolver thuộc Spring JMS

Interface cần dùng nằm trong package:

~~~java
org.springframework.jms.support.destination.DestinationResolver
~~~

Đây là strategy interface của module Spring JMS, thuộc artifact `spring-jms`. Nó có một phương thức:

~~~java
Destination resolveDestinationName(
        Session session,
        String destinationName,
        boolean pubSubDomain
) throws JMSException;
~~~

Ý nghĩa các tham số:

- **session:** JMS Session hiện tại mà thao tác gửi/nhận đang sử dụng. Resolver kiểu dynamic cần Session để gọi API tạo hoặc lấy Queue/Topic.
- **destinationName:** tên logic của destination cần phân giải.
- **pubSubDomain:** `false` nghĩa là Point-to-Point, resolver cần Queue; `true` nghĩa là Publish/Subscribe, resolver cần Topic.

Kết quả là một đối tượng `jakarta.jms.Destination`, thường là Queue hoặc Topic. Nếu phân giải thất bại, resolver có thể ném JMSException hoặc DestinationResolutionException.

DestinationResolver là functional interface. Về lý thuyết, ứng dụng có thể viết resolver bằng lambda. Tuy nhiên, trong phần lớn ứng dụng, DynamicDestinationResolver hoặc JndiDestinationResolver đã đáp ứng nhu cầu phổ biến.

**Chú ý package:** Spring còn có interface tên DestinationResolver trong `org.springframework.messaging.core` dành cho một abstraction messaging khác. Bài này nói về `org.springframework.jms.support.destination.DestinationResolver`, dùng với Jakarta JMS, Session và JmsTemplate. Khi import, hãy kiểm tra package để tránh dùng nhầm hai interface cùng tên.

## 3. JmsTemplate sử dụng DestinationResolver như thế nào?

JmsTemplate cho phép gọi các phương thức dùng tên destination:

~~~java
jmsTemplate.convertAndSend("orders.in", payload);
~~~

Trong lời gọi này, JmsTemplate cần một DestinationResolver để chuyển `orders.in` thành đối tượng Queue hoặc Topic. Resolver được cấu hình trên JmsDestinationAccessor, lớp cha của JmsTemplate.

Các API chính:

~~~java
jmsTemplate.setDestinationResolver(destinationResolver);
DestinationResolver resolver = jmsTemplate.getDestinationResolver();
~~~

Trong Spring Framework 6.2, JmsTemplate mặc định dùng DynamicDestinationResolver. Có thể thay bằng JndiDestinationResolver hoặc một implementation do ứng dụng tự viết.

Nếu truyền thẳng đối tượng Destination vào overload tương ứng, ứng dụng đã có sẵn destination và không cần phân giải tên cho thao tác đó:

~~~java
jmsTemplate.convertAndSend(queueObject, payload);
~~~

Nếu dùng overload nhận String, resolver sẽ tham gia.

### 3.1. Queue và Topic được chọn bằng pubSubDomain

JmsTemplate có thuộc tính `pubSubDomain`:

~~~java
jmsTemplate.setPubSubDomain(false); // Queue, mặc định
jmsTemplate.setPubSubDomain(true);  // Topic
~~~

Mặc định là `false`, tức Point-to-Point domain và Queue. Thuộc tính này đặc biệt quan trọng khi resolver phải tạo dynamic destination, vì nó quyết định gọi API tạo Queue hay Topic.

Ví dụ:

~~~java
// Resolver nhận pubSubDomain=false và phân giải thành Queue.
queueTemplate.convertAndSend("orders.in", payload);

// Resolver nhận pubSubDomain=true và phân giải thành Topic.
topicTemplate.convertAndSend("orders.events", event);
~~~

Một JmsTemplate có một giá trị pubSubDomain tại một thời điểm. Nếu ứng dụng gửi cả Queue lẫn Topic bằng tên String, cách rõ ràng là cấu hình hai template riêng cho hai domain. Nếu đã có đối tượng Queue/Topic, có thể dùng overload nhận Destination để chỉ rõ loại đích.

Không nên giả định resolver có thể suy ra Queue hay Topic từ hậu tố tên như `.queue` hoặc `.topic`. Quyết định domain được truyền qua tham số pubSubDomain hoặc đến từ chính Destination object.

## 4. DynamicDestinationResolver

DynamicDestinationResolver là implementation cơ bản của DestinationResolver. Nó dùng JMS Session hiện tại để phân giải tên thành dynamic destination:

- Khi `pubSubDomain=false`, gọi `Session.createQueue(destinationName)`.
- Khi `pubSubDomain=true`, gọi `Session.createTopic(destinationName)`.

Ví dụ:

~~~java
DynamicDestinationResolver resolver = new DynamicDestinationResolver();

Destination queue = resolver.resolveDestinationName(
        session, "orders.in", false
);

Destination topic = resolver.resolveDestinationName(
        session, "orders.events", true
);
~~~

### 4.1. Dynamic destination có nghĩa gì?

Dynamic destination là destination được ứng dụng tham chiếu bằng tên được biết lúc chạy, thay vì phải lấy sẵn đối tượng Destination đã được bind trong JNDI.

Điểm quan trọng là JMS specification không chuẩn hóa cách tạo physical destination động. Các JMS provider thường hỗ trợ việc gọi createQueue/createTopic để tạo đối tượng destination theo tên, nhưng hành vi cụ thể phụ thuộc provider:

- Có provider chỉ trả về một đối tượng đại diện cho destination có tên đó.
- Có provider tự tạo physical queue/topic nếu destination chưa tồn tại.
- Có provider yêu cầu destination đã được quản trị viên tạo trước.
- Các thuộc tính đặc thù như durability, retention, partition hoặc policy có thể phải cấu hình bằng công cụ/API riêng của provider.

Do đó, gọi DynamicDestinationResolver không bảo đảm broker sẽ tự tạo một queue/topic vật lý mới. Hãy kiểm tra tài liệu provider đang dùng và chính sách quản trị destination.

### 4.2. Dynamic destination không phải temporary destination

Hai khái niệm này khác nhau:

| Loại | Cách tạo | Vòng đời |
|---|---|---|
| Dynamic destination | Phân giải tên bằng createQueue/createTopic theo provider | Tên do ứng dụng quy ước; vòng đời vật lý phụ thuộc provider |
| TemporaryQueue/TemporaryTopic | Gọi Session.createTemporaryQueue/createTemporaryTopic | Thường gắn với Connection tạo ra nó và bị xóa khi connection đóng |
| JNDI destination | Lookup đối tượng đã được bind trong naming service | Vòng đời do môi trường/provider quản trị |

DynamicDestinationResolver không gọi createTemporaryQueue hoặc createTemporaryTopic. Không dùng resolver này nếu mục tiêu là tạo destination tạm chỉ dành cho một request-reply session.

### 4.3. Khi nào dùng DynamicDestinationResolver?

Dùng resolver mặc định này khi:

- Destination name được xác định lúc chạy theo quy ước đã thống nhất.
- JMS provider hỗ trợ cách phân giải dynamic destination tương ứng.
- Ứng dụng không cần lookup destination từ JNDI.
- Mô hình Queue/Topic được cấu hình rõ bằng pubSubDomain.

Nó đơn giản và không cần cấu hình JNDI. Nhưng nếu hệ thống yêu cầu quản trị destination tập trung, quyền truy cập, policy hoặc thuộc tính provider cụ thể, hãy cân nhắc JNDI hoặc một resolver chuyên biệt.

## 5. JndiDestinationResolver

JndiDestinationResolver là implementation DestinationResolver sử dụng JNDI. Thay vì gọi Session.createQueue/createTopic để phân giải tên, nó hiểu destinationName là tên cần lookup trong JNDI.

Ví dụ tên JNDI thường có dạng:

~~~text
java:comp/env/jms/OrdersQueue
java:comp/env/jms/OrderEventsTopic
~~~

Tên thực tế phụ thuộc application server, JMS provider và cấu hình naming context.

Resolver thực hiện các công việc chính:

1. Dùng JNDI environment/JndiTemplate được cấu hình để lookup tên.
2. Lấy đối tượng Destination đã được bind trong naming service.
3. Kiểm tra loại destination có phù hợp với domain mong đợi hay không.
4. Có thể cache kết quả để dùng lại.
5. Nếu được bật, có thể fallback sang một DynamicDestinationResolver khi lookup JNDI thất bại.

JNDI lookup không tự tạo binding. Queue hoặc Topic phải được provision và bind trong môi trường JMS/JNDI trước, trừ khi ứng dụng bật fallback dynamic và provider hỗ trợ việc đó.

### 5.1. Fallback sang dynamic destination

Mặc định, `fallbackToDynamicDestination=false`. Nếu JNDI lookup không tìm thấy destination, resolver báo lỗi phân giải.

Có thể bật fallback:

~~~java
JndiDestinationResolver resolver = new JndiDestinationResolver();
resolver.setFallbackToDynamicDestination(true);
resolver.setDynamicDestinationResolver(
        new DynamicDestinationResolver()
);
~~~

Khi bật, quy trình là:

~~~mermaid
flowchart TD
    A["Nhận destinationName"]
    B["Lookup JNDI"]
    C{"Tìm thấy Destination?"}
    D["Kiểm tra loại Queue/Topic"]
    E["Trả về Destination"]
    F{"Fallback dynamic bật?"}
    G["DynamicDestinationResolver"]
    H["Ném lỗi phân giải"]

    A --> B --> C
    C -->|Có| D --> E
    C -->|Không| F
    F -->|Có| G --> E
    F -->|Không| H
~~~

Fallback phù hợp khi ứng dụng có một nhóm destination được quản trị trong JNDI và một số destination động theo tenant hoặc quy ước nghiệp vụ. Chỉ bật khi provider và chính sách quản trị cho phép tạo/resolve destination động.

Nếu bật fallback, hãy nhớ rằng một lỗi gõ sai tên JNDI cũng có thể bị chuyển thành dynamic resolution. Điều này có thể che giấu lỗi cấu hình và tạo ra destination ngoài ý muốn nếu provider tự động tạo physical destination.

### 5.2. Cấu hình JNDI environment

JndiDestinationResolver kế thừa khả năng cấu hình từ Spring JNDI support. Có thể cung cấp các thuộc tính môi trường như:

- `Context.INITIAL_CONTEXT_FACTORY`: lớp InitialContextFactory do provider hoặc application server cung cấp.
- `Context.PROVIDER_URL`: URL của naming service nếu môi trường yêu cầu.
- Các thuộc tính bảo mật hoặc provider-specific khác.

Ví dụ cấu hình bằng Java:

~~~java
Properties jndiEnvironment = new Properties();
jndiEnvironment.setProperty(
        Context.INITIAL_CONTEXT_FACTORY,
        initialContextFactory
);
jndiEnvironment.setProperty(
        Context.PROVIDER_URL,
        providerUrl
);

JndiDestinationResolver resolver = new JndiDestinationResolver();
resolver.setJndiEnvironment(jndiEnvironment);
resolver.setFallbackToDynamicDestination(false);
~~~

Hai biến initialContextFactory và providerUrl phải lấy từ cấu hình thực tế của môi trường. Không có một giá trị chung cho mọi application server hoặc JMS provider.

Nếu ứng dụng chạy trong Jakarta EE container, naming context có thể đã được cung cấp sẵn. Khi đó, có thể chỉ cần dùng tên JNDI theo quy ước container và cấu hình phù hợp với môi trường.

## 6. Cache của JndiDestinationResolver

JndiDestinationResolver triển khai CachingDestinationResolver. Theo mặc định, cache được bật.

Các API quản lý cache:

~~~java
resolver.setCache(true);
resolver.setCache(false);

resolver.removeFromCache("orders.in");
resolver.clearCache();
~~~

Ý nghĩa:

- **cache=true:** lưu destination đã phân giải để tái sử dụng, tránh lookup lặp lại.
- **cache=false:** thực hiện lookup lại cho mỗi thao tác; hữu ích trong một số môi trường phát triển hoặc khi cần hot restart destination.
- **removeFromCache(name):** loại một destination khỏi cache nếu nó đã được cache.
- **clearCache():** xóa toàn bộ cache.

Nếu truy cập destination thất bại và có lý do cho rằng đối tượng cached đã mất hiệu lực, có thể loại tên đó khỏi cache rồi thử lại theo chính sách phục hồi của ứng dụng. Không nên tự động xóa cache và retry vô hạn vì lỗi có thể đến từ quyền truy cập, broker outage hoặc cấu hình sai.

### 6.1. Tên Queue và Topic phải duy nhất khi cache

JndiDestinationResolver cache dynamic queues và topics theo destination name. Vì cache key dựa trên tên, Javadoc yêu cầu dùng tên duy nhất giữa Queue và Topic.

Ví dụ không nên dùng cùng tên `orders` cho cả:

- Queue `orders`
- Topic `orders`

Hãy chọn tên rõ ràng như `orders.queue` và `orders.topic`, hoặc một quy ước namespace tách biệt. Điều này tránh một entry cache được tạo cho một domain nhưng lại được dùng trong ngữ cảnh domain còn lại.

### 6.2. Cache và thay đổi cấu hình ở broker

Nếu quản trị viên thay destination hoặc rebinding JNDI trong khi ứng dụng đang chạy, resolver có thể tiếp tục trả về đối tượng đã cache. Tùy provider, đối tượng cũ có thể còn hợp lệ hoặc đã mất hiệu lực.

Cần có quy trình rõ ràng cho thay đổi destination:

1. Thay đổi/bind destination trong môi trường quản trị.
2. Xác định cache có cần được làm mới không.
3. Gọi removeFromCache hoặc clearCache khi cần.
4. Theo dõi lỗi phân giải và lỗi gửi để xác nhận destination mới hoạt động.

Đặt cache=false có thể giúp môi trường phát triển nhìn thấy thay đổi nhanh hơn, nhưng làm tăng số lần lookup. Trong production, hãy chọn dựa trên vòng đời destination và chi phí lookup thực tế.

## 7. Cấu hình JmsTemplate với từng resolver

### 7.1. Dùng DynamicDestinationResolver mặc định

Nếu không cấu hình resolver, JmsTemplate của Spring Framework 6.2 sử dụng DynamicDestinationResolver.

Có thể viết tường minh:

~~~java
JmsTemplate queueTemplate = new JmsTemplate(connectionFactory);
queueTemplate.setDestinationResolver(
        new DynamicDestinationResolver()
);
queueTemplate.setPubSubDomain(false);

queueTemplate.convertAndSend("orders.in", payload);
~~~

Để dùng Topic:

~~~java
JmsTemplate topicTemplate = new JmsTemplate(connectionFactory);
topicTemplate.setDestinationResolver(
        new DynamicDestinationResolver()
);
topicTemplate.setPubSubDomain(true);

topicTemplate.convertAndSend("orders.events", event);
~~~

### 7.2. Dùng JndiDestinationResolver

~~~java
JndiDestinationResolver resolver = new JndiDestinationResolver();
resolver.setJndiEnvironment(jndiEnvironment);
resolver.setCache(true);
resolver.setFallbackToDynamicDestination(false);

JmsTemplate jmsTemplate = new JmsTemplate(connectionFactory);
jmsTemplate.setDestinationResolver(resolver);
jmsTemplate.setPubSubDomain(false);

jmsTemplate.convertAndSend(
        "java:comp/env/jms/OrdersQueue",
        payload
);
~~~

Trong ví dụ, JmsTemplate yêu cầu Queue vì pubSubDomain=false. JndiDestinationResolver lookup tên JNDI và kiểm tra destination trả về phù hợp với Queue.

Nếu destination JNDI là Topic, hãy cấu hình template với pubSubDomain=true hoặc dùng một JmsTemplate riêng cho Topic.

### 7.3. Đưa resolver vào Spring container

Trong ứng dụng Spring, nên cấu hình resolver thành bean và inject vào JmsTemplate:

~~~java
@Configuration
public class JmsConfiguration {

    @Bean
    public DestinationResolver destinationResolver(
            Properties jndiEnvironment) {

        JndiDestinationResolver resolver =
                new JndiDestinationResolver();

        resolver.setJndiEnvironment(jndiEnvironment);
        resolver.setCache(true);
        resolver.setFallbackToDynamicDestination(false);

        return resolver;
    }

    @Bean
    public JmsTemplate jmsTemplate(
            ConnectionFactory connectionFactory,
            DestinationResolver destinationResolver) {

        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setDestinationResolver(destinationResolver);
        template.setPubSubDomain(false);
        return template;
    }
}
~~~

Bean Properties jndiEnvironment trong ví dụ phải được cung cấp bởi cấu hình ứng dụng. Nếu dùng DynamicDestinationResolver, có thể bỏ phần JNDI environment và dùng implementation mặc định.

JmsTemplate nên được cấu hình hoàn chỉnh trước khi chia sẻ cho nhiều service. Sau khi cấu hình, template có thể được inject và sử dụng đồng thời theo thiết kế thread-safe của Spring.

## 8. Ví dụ Java 17 chạy được: kiểm tra DynamicDestinationResolver

Ví dụ sau kiểm tra resolver gọi đúng API của JMS Session cho Queue và Topic. Mockito tạo Session giả, giúp kiểm thử logic phân giải mà không cần chạy broker thật.

Ví dụ này kiểm tra cách Spring chọn createQueue/createTopic. Nó không kiểm tra provider có tự tạo physical destination hay không; hành vi đó phụ thuộc broker thực tế.

### 8.1. Cấu hình Maven

Tạo file pom.xml:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>destination-resolver-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jms</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>jakarta.jms</groupId>
            <artifactId>jakarta.jms-api</artifactId>
            <version>3.1.0</version>
        </dependency>
        <dependency>
            <groupId>org.mockito</groupId>
            <artifactId>mockito-core</artifactId>
            <version>5.14.2</version>
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

### 8.2. Chương trình hoàn chỉnh

Tạo file src/main/java/demo/DestinationResolverDemo.java:

~~~java
package demo;

import jakarta.jms.Destination;
import jakarta.jms.Queue;
import jakarta.jms.Session;
import jakarta.jms.Topic;

import org.springframework.jms.support.destination.DynamicDestinationResolver;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

public class DestinationResolverDemo {

    public static void main(String[] args) throws Exception {
        Session session = mock(Session.class);

        Queue ordersQueue = mock(Queue.class);
        Topic orderEventsTopic = mock(Topic.class);

        when(session.createQueue("orders.in"))
                .thenReturn(ordersQueue);

        when(session.createTopic("orders.events"))
                .thenReturn(orderEventsTopic);

        DynamicDestinationResolver resolver =
                new DynamicDestinationResolver();

        Destination resolvedQueue = resolver.resolveDestinationName(
                session,
                "orders.in",
                false
        );

        Destination resolvedTopic = resolver.resolveDestinationName(
                session,
                "orders.events",
                true
        );

        System.out.println("queueResolved=" + (resolvedQueue == ordersQueue));
        System.out.println(
                "topicResolved=" + (resolvedTopic == orderEventsTopic)
        );
    }
}
~~~

Chạy từ thư mục chứa pom.xml:

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=demo.DestinationResolverDemo
~~~

Stdout:

~~~text
queueResolved=true
topicResolved=true
~~~

### 8.3. Phân tích kết quả

Lời gọi đầu tiên truyền pubSubDomain=false, nên DynamicDestinationResolver gọi session.createQueue("orders.in"). Mockito trả về ordersQueue; kết quả phân giải là chính đối tượng đó.

Lời gọi thứ hai truyền pubSubDomain=true, nên resolver gọi session.createTopic("orders.events"). Kết quả là orderEventsTopic.

Ví dụ xác nhận quy tắc chọn Queue/Topic trong resolver. Khi chạy với JMS provider thật, Session và Destination sẽ do provider cung cấp; provider quyết định việc tên động có tương ứng với physical destination được tạo tự động hay không.

## 9. Tự viết DestinationResolver khi cần quy tắc riêng

Nếu quy ước tên destination của ứng dụng phức tạp, có thể tự triển khai interface:

~~~java
DestinationResolver resolver = (session, name, pubSubDomain) -> {
    if (name.startsWith("tenant.")) {
        return pubSubDomain
                ? session.createTopic(name)
                : session.createQueue(name);
    }

    throw new DestinationResolutionException(
            "Unsupported destination name: " + name
    );
};
~~~

Ví dụ này chỉ chấp nhận tên bắt đầu bằng tenant. Trong ứng dụng thực tế, custom resolver có thể:

- Ánh xạ logical name sang physical name theo tenant hoặc môi trường.
- Kiểm tra danh sách destination được phép.
- Chọn namespace theo loại nghiệp vụ.
- Gọi một registry nội bộ để tìm Destination.
- Bổ sung cache hoặc metrics theo quy ước riêng.

Không nên đưa logic phân quyền quan trọng chỉ vào resolver. Resolver chịu trách nhiệm ánh xạ tên thành Destination; quyền publish/consume vẫn phải được bảo vệ ở broker và tại ranh giới ứng dụng.

## 10. Lỗi thường gặp và cách xử lý

### 10.1. Nhầm tên logic với JNDI name

Một tên như `orders.in` có thể là dynamic destination name. Một tên như `java:comp/env/jms/OrdersQueue` thường là JNDI name. Nếu dùng JndiDestinationResolver, hãy cung cấp đúng tên đã bind trong naming service.

### 10.2. Bật fallback để che lỗi JNDI

Nếu fallback dynamic được bật, lỗi gõ sai tên JNDI có thể dẫn tới việc resolver thử dynamic destination. Điều này có thể khiến ứng dụng tiếp tục chạy nhưng gửi vào destination khác dự kiến. Chỉ bật fallback khi đó là hành vi có chủ đích.

### 10.3. Quên pubSubDomain

DynamicDestinationResolver cần biết tạo Queue hay Topic. Mặc định là Queue. Nếu tên thuộc Topic nhưng template vẫn để pubSubDomain=false, resolver sẽ yêu cầu Queue và provider có thể báo lỗi hoặc tạo sai destination theo cấu hình provider.

### 10.4. Dùng chung tên cho Queue và Topic

Với cache của JndiDestinationResolver, tên Queue và Topic phải duy nhất trên cả hai domain. Hãy dùng namespace rõ ràng để tránh đụng cache key và tránh nhầm lẫn trong cấu hình.

### 10.5. Nghĩ createQueue/createTopic luôn tạo physical destination

JMS không chuẩn hóa việc tạo physical destination động. Provider có thể yêu cầu destination đã được quản trị viên tạo trước. Kiểm tra hành vi broker trước khi dùng dynamic resolution trong production.

### 10.6. Nhầm dynamic với temporary destination

Dynamic destination dùng tên do ứng dụng quy ước. TemporaryQueue/TemporaryTopic có vòng đời gắn với Connection. Nếu cần reply queue tạm, dùng API temporary destination hoặc request-reply API thích hợp.

### 10.7. Cache giữ destination cũ

Khi JNDI binding hoặc broker destination thay đổi, cache có thể vẫn giữ đối tượng cũ. Dùng removeFromCache/clearCache khi có lý do xác định destination đã mất hiệu lực; tránh retry vô hạn.

### 10.8. Bỏ qua lỗi phân giải

DestinationResolutionException thường báo lỗi ở bước chuyển tên thành Destination. Hãy kiểm tra tên, JNDI binding, quyền lookup, domain Queue/Topic và provider. Phân biệt lỗi này với lỗi gửi Message sau khi destination đã được phân giải.

### 10.9. Nhầm hai interface DestinationResolver

Luôn kiểm tra import. Bài này dùng `org.springframework.jms.support.destination.DestinationResolver`; interface trong `org.springframework.messaging.core` thuộc abstraction khác và không nhận Jakarta JMS Session.

### 10.10. Tạo resolver mới cho mọi thao tác

Nếu resolver có cache, tạo mới mỗi lần sẽ làm mất lợi ích cache. Cấu hình một resolver bean và inject vào JmsTemplate dùng chung sau khi khởi tạo.

## 11. Chọn resolver nào?

| Nhu cầu | Resolver phù hợp | Lý do |
|---|---|---|
| Destination được xác định bằng tên lúc chạy và provider hỗ trợ dynamic lookup | DynamicDestinationResolver | Dùng Session.createQueue/createTopic |
| Destination được quản trị và bind trong JNDI | JndiDestinationResolver | Lookup tên trong naming service |
| Kết hợp destination JNDI và dynamic fallback có kiểm soát | JndiDestinationResolver | Bật fallback và cấu hình resolver dự phòng |
| Destination là Spring bean | BeanFactoryDestinationResolver | Tìm Destination từ Spring BeanFactory |
| Muốn quy tắc ánh xạ tên riêng | Custom DestinationResolver | Tự kiểm soát lookup, namespace hoặc policy |

Để chọn đúng, hãy trả lời ba câu hỏi: destination do ai quản trị, tên được biết ở thời điểm nào, và provider có hỗ trợ dynamic destination không?

Nếu destination đã được khai báo cố định trong ứng dụng, có thể inject trực tiếp Queue/Topic bean hoặc JNDI object thay vì phân giải String ở mỗi thao tác. Nếu tên chỉ biết khi chạy, resolver giúp giữ code nghiệp vụ độc lập với cách tìm destination.

## 12. Câu hỏi tự kiểm tra

1. DestinationResolver của Spring JMS nằm trong package nào?
2. Phương thức resolveDestinationName nhận ba tham số nào?
3. Vì sao JmsTemplate cần resolver khi API nhận tên destination dạng String?
4. DynamicDestinationResolver gọi Session.createQueue hay createTopic trong trường hợp nào?
5. pubSubDomain mặc định là true hay false?
6. Dynamic destination có luôn làm broker tạo physical queue/topic không?
7. JndiDestinationResolver lookup destination từ đâu?
8. Fallback sang dynamic destination được bật mặc định không?
9. Cache của JndiDestinationResolver mặc định bật hay tắt?
10. Vì sao tên Queue và Topic cần duy nhất khi cache?
11. Làm thế nào để loại một destination khỏi cache?
12. Dynamic destination khác TemporaryQueue ở vòng đời như thế nào?
13. Khi nào nên dùng hai JmsTemplate riêng cho Queue và Topic?
14. DestinationResolver trong org.springframework.messaging.core có giống interface JMS đang học không?

## 13. Kết luận

DestinationResolver là strategy của Spring JMS để chuyển tên String thành đối tượng Jakarta JMS Destination. JmsTemplate sử dụng resolver khi các thao tác gửi/nhận được gọi bằng tên destination.

DynamicDestinationResolver dùng Session.createQueue/createTopic và là implementation mặc định trong Spring Framework 6.2. Nó phù hợp khi tên destination được xác định lúc chạy và JMS provider hỗ trợ dynamic resolution. JndiDestinationResolver lookup destination đã được bind trong JNDI, hỗ trợ cache và có thể fallback sang dynamic resolver khi được bật rõ ràng.

Hãy cấu hình pubSubDomain đúng với Queue hoặc Topic, quản lý cache theo vòng đời destination và kiểm tra hành vi của JMS provider trước khi dựa vào việc tạo destination động. Resolver chỉ giải quyết tên thành Destination; nó không tự provision broker, cấu hình durability hay cấp quyền truy cập.

## Tài liệu tham khảo chính thức

- Spring Framework 6.2 — Using Spring JMS, Destination Management: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html
- DestinationResolver API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/support/destination/DestinationResolver.html
- DynamicDestinationResolver API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/support/destination/DynamicDestinationResolver.html
- JndiDestinationResolver API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/support/destination/JndiDestinationResolver.html
- JmsDestinationAccessor API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/support/destination/JmsDestinationAccessor.html
- JmsTemplate API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/core/JmsTemplate.html
- Jakarta Messaging specification: https://jakarta.ee/specifications/messaging/
