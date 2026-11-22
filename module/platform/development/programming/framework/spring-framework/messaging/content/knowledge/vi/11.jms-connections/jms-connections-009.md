# Phân biệt phân giải Destination với tạo tài nguyên vật lý trên broker

## Mục tiêu

Trong Spring JMS, ứng dụng thường truyền tên destination như `orders.in` hoặc `orders.events` cho `JmsTemplate` hay listener container. Spring phải chuyển tên đó thành một đối tượng JMS `Destination` để gửi hoặc nhận message. Công việc này gọi là **phân giải destination** (destination resolution).

Việc tạo Queue hoặc Topic vật lý trên broker là một công việc khác. Nó có thể cần quản trị viên, cấu hình broker, lệnh quản lý hoặc management API của nhà cung cấp. Hiểu rõ hai bước này giúp tránh lỗi kiểu “Spring tìm được destination object nhưng broker báo queue không tồn tại”.

Sau bài này, bạn có thể:

- Phân biệt tên destination, đối tượng JMS `Destination` và tài nguyên vật lý trên broker.
- Giải thích `Session.createQueue()` và `Session.createTopic()` thực sự làm gì.
- Hiểu vai trò của `DestinationResolver`, `DynamicDestinationResolver`, `SimpleDestinationResolver` và `JndiDestinationResolver`.
- Cấu hình `JmsTemplate` và listener container để tra cứu destination.
- Xác định khi nào broker tự tạo destination và khi nào cần provision trước.
- Chẩn đoán lỗi JNDI, sai Queue/Topic, cache và quyền truy cập broker.

## 1. Bốn khái niệm cần tách biệt

Một ứng dụng có thể gặp bốn thứ cùng mang một tên, nhưng chúng nằm ở các lớp khác nhau:

| Khái niệm | Ví dụ | Ý nghĩa |
|---|---|---|
| Tên destination | `orders.in` | Chuỗi tên ứng dụng dùng để chỉ Queue hoặc Topic |
| JMS Destination object | `Queue` hoặc `Topic` | Đối tượng Java đại diện cho destination theo hợp đồng Jakarta Messaging |
| Tài nguyên vật lý trên broker | Queue `orders.in` được khai báo trên broker | Nơi broker thực sự lưu trữ, định tuyến và quản lý message |
| Administered object trong JNDI | `java:comp/env/jms/OrdersIn` | Tên tra cứu trong registry JNDI trỏ tới một JMS Destination đã được quản trị/cấu hình |

Luồng điển hình:

~~~text
Tên destination trong ứng dụng
        |
        v
Spring DestinationResolver
        |
        v
JMS Destination object (Queue / Topic)
        |
        v
JMS provider / broker xử lý thao tác send hoặc receive
        |
        v
Tài nguyên vật lý trên broker
~~~

JNDI là một con đường khác để lấy Destination object: ứng dụng tra cứu một administered object đã được đăng ký. Việc tra cứu JNDI cũng không tự động provision Queue hoặc Topic vật lý trên broker.

## 2. Destination object không đồng nghĩa với tài nguyên vật lý

Jakarta Messaging định nghĩa `Session.createQueue(String)` và `Session.createTopic(String)` để tạo một đối tượng `Queue` hoặc `Topic` bao bọc tên provider-specific.

Ví dụ:

~~~java
import jakarta.jms.Queue;
import jakarta.jms.Session;
import jakarta.jms.Topic;

Queue queue = session.createQueue("orders.in");
Topic topic = session.createTopic("orders.events");
~~~

Hai lời gọi này tạo đối tượng JMS đại diện cho tên Queue/Topic. Theo đặc tả Jakarta Messaging, chúng **không tạo Queue hoặc Topic vật lý trên broker**. Đặc tả cũng không cung cấp API chuẩn để tạo tài nguyên vật lý, vì cách provision phụ thuộc nhà cung cấp JMS.

Thông thường, tài nguyên vật lý được tạo bằng một trong các cách:

- Broker management console.
- Lệnh CLI của broker.
- Management/JMX/REST API do broker cung cấp.
- File cấu hình hoặc cơ chế khai báo hạ tầng (Infrastructure as Code).
- Công cụ quản trị của nền tảng JMS/Jakarta EE.

Có một ngoại lệ cần nhớ: `Session.createTemporaryQueue()` và `Session.createTemporaryTopic()` tạo temporary destination theo vòng đời kết nối/session của provider. Đây là API riêng cho tài nguyên tạm thời, khác với `createQueue(name)` và `createTopic(name)`.

### 2.1. Vì sao đôi khi gọi createQueue lại thấy Queue xuất hiện trên broker?

Một số JMS provider có tính năng **auto-create destination**. Khi client gửi hoặc đăng ký consumer với một tên chưa tồn tại, broker có thể tự tạo tài nguyên vật lý theo chính sách của provider.

Đó là hành vi riêng của broker, không phải cam kết portable của Jakarta Messaging. Ví dụ:

- Broker có thể bật auto-create cho Queue nhưng tắt cho Topic.
- Broker có thể chỉ cho phép auto-create trong một namespace.
- Tài nguyên tự tạo có thể nhận cấu hình mặc định về durability, TTL, dead-letter, giới hạn dung lượng hoặc quyền truy cập.
- Môi trường production có thể tắt auto-create để tránh tạo nhầm destination do sai tên.

Vì vậy, khi thấy Queue xuất hiện sau `session.createQueue("orders.in")`, hãy kiểm tra chính sách auto-create của broker. Đừng kết luận rằng phương thức JMS đã provision tài nguyên vật lý theo chuẩn.

## 3. DestinationResolver trong Spring JMS

Spring cung cấp interface `org.springframework.jms.support.destination.DestinationResolver` để chuyển tên String thành đối tượng JMS `Destination`.

Phương thức cốt lõi:

~~~java
Destination resolveDestinationName(
    Session session,
    String destinationName,
    boolean pubSubDomain
) throws JMSException;
~~~

Ý nghĩa tham số:

- `session`: JMS Session hiện tại, dùng khi resolver cần gọi API của provider.
- `destinationName`: tên destination mà ứng dụng truyền vào.
- `pubSubDomain`: `false` nghĩa là Queue/point-to-point; `true` nghĩa là Topic/publish-subscribe.

Các lớp như `JmsTemplate` và listener container dùng resolver khi nhận tên destination dạng String. Nếu ứng dụng truyền trực tiếp một đối tượng `Destination`, nó đã có sẵn đối tượng đích và không cần bước phân giải tên đó.

Ví dụ hai cách gửi:

~~~java
// Spring phân giải tên String thành Destination.
jmsTemplate.convertAndSend("orders.in", payload);

// Ứng dụng đã có Destination object, truyền trực tiếp.
jmsTemplate.convertAndSend(ordersQueue, payload);
~~~

`DestinationResolver` không phải broker administration API. Nhiệm vụ chính của nó là cung cấp đúng đối tượng JMS cho thao tác gửi/nhận.

## 4. DynamicDestinationResolver và SimpleDestinationResolver

### 4.1. DynamicDestinationResolver

`DynamicDestinationResolver` phân giải tên bằng JMS Session:

- Nếu `pubSubDomain=false`, gọi `Session.createQueue(destinationName)`.
- Nếu `pubSubDomain=true`, gọi `Session.createTopic(destinationName)`.

Resolver này không thực hiện JNDI lookup. Nó yêu cầu JMS provider tạo một đối tượng Destination cho tên đã cho. Việc broker có tạo tài nguyên vật lý khi destination được sử dụng hay không vẫn do provider quyết định.

Resolver này phân giải mới ở mỗi lần gọi. Nó hữu ích khi cần fresh resolution hoặc khi Destination object phụ thuộc Session theo cách riêng của provider.

### 4.2. SimpleDestinationResolver

`SimpleDestinationResolver` kế thừa `DynamicDestinationResolver` và cache các Queue/Topic object theo tên destination. Nó phù hợp với provider có Destination object ổn định và không phụ thuộc vào vòng đời của từng Session.

Theo API Javadoc của Spring Framework:

- Spring Framework 6.2 dùng `DynamicDestinationResolver` làm resolver mặc định.
- Từ Spring Framework 7.0, `SimpleDestinationResolver` là resolver mặc định cho `JmsTemplate` và listener container.

Nếu cần phân giải mới ở mọi lần gọi trong Spring 7, có thể cấu hình rõ `DynamicDestinationResolver`.

Ví dụ:

~~~java
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.destination.DynamicDestinationResolver;
import org.springframework.jms.support.destination.SimpleDestinationResolver;

JmsTemplate template = new JmsTemplate(connectionFactory);

// Spring 7: resolver mặc định có cache Destination object.
template.setDestinationResolver(new SimpleDestinationResolver());

// Chỉ dùng khi muốn resolve mới theo từng lần gọi.
template.setDestinationResolver(new DynamicDestinationResolver());
~~~

Cả hai resolver trên đều dựa vào JMS Session để tạo Queue/Topic object. Chúng không thay thế thao tác quản trị tạo tài nguyên vật lý trên broker.

## 5. JndiDestinationResolver: tra cứu administered object

Trong môi trường doanh nghiệp, Queue/Topic thường được quản trị sẵn và đăng ký trong JNDI. Ứng dụng dùng tên JNDI để lấy đối tượng Destination đã được cấu hình.

Ví dụ tên JNDI:

~~~text
java:comp/env/jms/OrdersIn
java:comp/env/jms/OrdersEvents
~~~

`JndiDestinationResolver` tra cứu destination name như một JNDI location. Nó phù hợp khi:

- Destination được quản trị viên hoặc application server cấu hình trước.
- Ứng dụng cần dùng đúng tài nguyên đã khai báo, có sẵn policy và quyền truy cập.
- Tên JNDI được quản lý tách khỏi code.
- Muốn tránh tạo destination động khi tên tra cứu sai.

Fallback sang dynamic resolution bị tắt mặc định. Có thể giữ hành vi này một cách tường minh:

~~~java
import org.springframework.jms.support.destination.JndiDestinationResolver;

JndiDestinationResolver resolver = new JndiDestinationResolver();
resolver.setFallbackToDynamicDestination(false);
~~~

Nếu bật fallback:

~~~java
resolver.setFallbackToDynamicDestination(true);
~~~

khi JNDI lookup không tìm thấy tên, resolver có thể chuyển sang dynamic resolution. Điều đó có thể hữu ích trong môi trường phát triển, nhưng cũng có thể che giấu lỗi sai tên hoặc cấu hình thiếu trong production.

JNDI lookup trả về Destination object đã đăng ký. Bản thân thao tác lookup không tạo Queue/Topic vật lý. Việc tạo và cấu hình tài nguyên vẫn thuộc broker hoặc nền tảng quản trị.

## 6. Các resolver thường gặp

| Resolver | Cách lấy Destination object | Có tự provision tài nguyên vật lý không? |
|---|---|---|
| `DynamicDestinationResolver` | Gọi `Session.createQueue/createTopic` theo tên | Không theo chuẩn; provider có thể auto-create khi sử dụng |
| `SimpleDestinationResolver` | Cách trên, đồng thời cache object theo tên | Không theo chuẩn; provider có thể auto-create khi sử dụng |
| `JndiDestinationResolver` | Tra cứu tên trong JNDI; fallback dynamic là tùy chọn và mặc định tắt | Không; JNDI lookup không provision broker |
| `BeanFactoryDestinationResolver` | Tra cứu Destination bean trong Spring BeanFactory | Không; bean phải được cung cấp sẵn |

Một lựa chọn khác là inject trực tiếp Queue/Topic bean hoặc JNDI object vào ứng dụng. Khi đó, ứng dụng có thể truyền thẳng Destination object vào `JmsTemplate`.

## 7. Cấu hình JmsTemplate với destination đã quản trị

Ví dụ cấu hình một template sử dụng JNDI resolver:

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.destination.JndiDestinationResolver;

@Configuration
public class JmsConfiguration {

    @Bean
    JndiDestinationResolver destinationResolver() {
        var resolver = new JndiDestinationResolver();
        resolver.setFallbackToDynamicDestination(false);
        return resolver;
    }

    @Bean
    JmsTemplate jmsTemplate(
            ConnectionFactory connectionFactory,
            JndiDestinationResolver destinationResolver) {
        var template = new JmsTemplate(connectionFactory);
        template.setDestinationResolver(destinationResolver);
        template.setPubSubDomain(false); // Queue domain
        return template;
    }
}
~~~

Gửi bằng tên JNDI:

~~~java
jmsTemplate.convertAndSend(
    "java:comp/env/jms/OrdersIn",
    new OrderCreated("order-42")
);
~~~

Ví dụ trên giả định JNDI context đã được cấu hình và administered object `java:comp/env/jms/OrdersIn` đã được đăng ký. Nó không tự tạo Queue trên broker.

Nếu ứng dụng dùng Topic, cần cấu hình `pubSubDomain=true` hoặc dùng template riêng cho Topic. Resolver phải trả về đúng loại Destination mà thao tác đang yêu cầu.

## 8. Cấu hình resolver cho listener container

Listener container cũng phải phân giải tên destination. Nếu `@JmsListener` sử dụng tên JNDI, cấu hình resolver cho factory tương ứng:

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.support.destination.DestinationResolver;

@Configuration
public class JmsListenerConfiguration {

    @Bean
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory,
            DestinationResolver destinationResolver) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setDestinationResolver(destinationResolver);
        factory.setSessionTransacted(true);
        return factory;
    }
}
~~~

Listener:

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    @JmsListener(
        destination = "java:comp/env/jms/OrdersIn",
        containerFactory = "jmsListenerContainerFactory"
    )
    public void handle(OrderCreated event) {
        // Xử lý event.
    }
}
~~~

Tên destination được resolver tra cứu khi listener container khởi tạo hoặc thiết lập consumer. Nếu JNDI name sai, context không truy cập được hoặc object không đúng loại, listener có thể không khởi động được.

## 9. Provision tài nguyên vật lý trên broker

Tài nguyên vật lý cần được tạo theo công cụ và cú pháp của broker đang dùng. Một quy trình production thường gồm:

1. Xác định Queue hay Topic, tên vật lý và namespace.
2. Khai báo tài nguyên qua management console, CLI, management API hoặc Infrastructure as Code.
3. Thiết lập các thuộc tính như durability, routing, TTL/expiry, maximum size, dead-letter address/queue và chính sách redelivery nếu broker hỗ trợ.
4. Cấp quyền send, consume, browse hoặc manage cho các tài khoản ứng dụng.
5. Nếu ứng dụng tra cứu bằng JNDI, đăng ký administered object trỏ tới tài nguyên đã provision.
6. Cấu hình Spring dùng JNDI resolver hoặc Destination object được inject.
7. Kiểm tra kết nối, quyền truy cập và khả năng gửi/nhận bằng một smoke test.
8. Theo dõi số message, consumer, dung lượng, dead-letter và trạng thái destination trong broker.

Không có lệnh tạo Queue/Topic vật lý chung cho mọi JMS provider. Cùng một Jakarta Messaging API có thể được triển khai bởi các broker khác nhau, mỗi broker có lệnh quản trị và chính sách riêng.

### 9.1. Ví dụ về chính sách auto-create

Giả sử code gửi vào tên `orders.in`:

~~~java
jmsTemplate.convertAndSend("orders.in", payload);
~~~

Có ba khả năng:

- Queue đã tồn tại: broker định tuyến message vào Queue đó nếu ứng dụng có quyền.
- Queue chưa tồn tại và auto-create bật: broker có thể tạo Queue theo cấu hình mặc định hoặc policy của nó.
- Queue chưa tồn tại và auto-create tắt: thao tác send hoặc tạo consumer có thể thất bại, tùy provider và thời điểm kiểm tra.

Cả ba trường hợp đều có thể bắt đầu từ cùng một lời gọi Java. Do đó, chỉ đọc code Spring không đủ để biết tài nguyên vật lý có tồn tại hay được tạo hay không; cần kiểm tra broker configuration và trạng thái quản trị.

## 10. Phân biệt các loại lỗi

| Triệu chứng | Lớp có vấn đề | Cách kiểm tra |
|---|---|---|
| JNDI name not found | JNDI lookup | Context factory, namespace, binding name và quyền lookup |
| Không phân giải được tên Queue/Topic | DestinationResolver | Tên, `pubSubDomain`, loại Destination và resolver được cấu hình |
| Resolver trả object nhưng send thất bại vì destination không tồn tại | Broker provisioning hoặc auto-create policy | Kiểm tra tài nguyên vật lý và broker log |
| Access denied khi send/consume | Broker authorization | ACL/role cho destination và principal của ConnectionFactory |
| Consumer không nhận message | Destination, selector, subscription hoặc routing | Queue/topic name, selector, subscription và binding |
| Chạy được ở local nhưng lỗi production | Khác biệt broker policy | Auto-create, JNDI binding, namespace và quyền giữa hai môi trường |
| Destination object cũ sau khi broker thay đổi | Resolver cache hoặc provider object | Kiểm tra cache; xóa cache hoặc khởi tạo lại resolver theo API hỗ trợ |

Một điểm chẩn đoán quan trọng: **resolver thành công không chứng minh broker đã provision destination**. Resolver có thể chỉ tạo một object chứa tên. Lỗi chỉ xuất hiện khi provider thực hiện thao tác gửi, tạo consumer hoặc xác thực quyền.

## 11. Cache và vòng đời Destination object

Resolver có cache cần được dùng phù hợp với provider:

- `SimpleDestinationResolver` cache Queue/Topic object theo tên.
- `JndiDestinationResolver` mặc định cache kết quả lookup.
- `JndiDestinationResolver.setCache(false)` buộc tra cứu lại mỗi lần.
- Các resolver triển khai `CachingDestinationResolver` có thể cung cấp `clearCache()` hoặc `removeFromCache(name)`.

Cache giúp tránh tạo hoặc tra cứu object lặp lại. Tuy nhiên, nếu broker hoặc JNDI binding bị thay đổi, object đã cache có thể không còn phù hợp. Khi gặp lỗi sau khi thay đổi destination, kiểm tra cache và vòng đời của provider object.

Không nên tắt cache theo mặc định chỉ để tránh lỗi. Hãy xác định provider có yêu cầu Destination object ổn định hay không và chỉ làm mới cache khi có lý do.

## 12. Chọn cách quản lý destination

| Nhu cầu | Cách tiếp cận |
|---|---|
| Destination được quản trị tập trung trong application server | JNDI + `JndiDestinationResolver` |
| Ứng dụng muốn dùng Destination bean đã inject | `BeanFactoryDestinationResolver` hoặc truyền trực tiếp object |
| Tên destination được xác định lúc chạy, broker hỗ trợ dynamic/auto-create | Dynamic resolution, kèm kiểm tra policy provider |
| Cần object ổn định và tái sử dụng theo tên trên Spring 7 | `SimpleDestinationResolver` mặc định |
| Cần fresh resolution mỗi lần gọi | `DynamicDestinationResolver` |
| Production cần cấu hình Queue/Topic rõ ràng, có policy và ACL | Provision trên broker trước, sau đó tra cứu object bằng JNDI hoặc cấu hình đã quản trị |

Trong production, việc provision trước giúp tài nguyên có policy và quyền truy cập đúng ngay từ đầu. Auto-create có thể hữu ích trong local development hoặc môi trường ephemeral, nhưng cần kiểm soát rõ để tránh typo tạo ra destination ngoài dự kiến.

## 13. Lỗi thường gặp

- **Gọi `session.createQueue(name)` rồi cho rằng broker đã có Queue vật lý:** phương thức chuẩn chỉ tạo đối tượng Queue bao bọc tên. Provision tài nguyên qua broker.
- **Cho rằng Spring DynamicDestinationResolver luôn tạo Queue vật lý:** resolver gọi API JMS; broker có auto-create hay không phụ thuộc provider.
- **Dùng tên JNDI như tên vật lý của broker:** JNDI binding và physical destination name có thể khác nhau. Tra cứu đúng binding đã đăng ký.
- **Bật fallback dynamic trong production mà không kiểm soát:** tên JNDI sai có thể rơi sang dynamic resolution và che giấu cấu hình thiếu.
- **Dùng sai `pubSubDomain`:** resolver tạo Queue khi ứng dụng mong Topic hoặc ngược lại.
- **Đổi tên Queue trên broker nhưng vẫn giữ resolver cache cũ:** object đã cache có thể cần được làm mới.
- **Tưởng tạo Destination bean trong Spring là đã provision broker:** bean chỉ cung cấp object cho ứng dụng; broker vẫn phải có tài nguyên hoặc bật auto-create.
- **Không kiểm tra quyền:** destination tồn tại nhưng principal của ứng dụng không được phép send hoặc consume.
- **Dùng dynamic auto-create cho destination quan trọng mà không thiết lập policy:** Queue có thể xuất hiện với cấu hình mặc định không phù hợp.

## 14. Checklist triển khai

- [ ] Đã xác định tên logic trong ứng dụng và tên vật lý trên broker.
- [ ] Đã xác định destination là Queue hay Topic.
- [ ] Đã chọn resolver phù hợp: JNDI, bean, simple hoặc dynamic.
- [ ] Đã kiểm tra resolver mặc định theo phiên bản Spring đang dùng.
- [ ] Đã hiểu `Session.createQueue/createTopic` chỉ tạo Destination object theo chuẩn.
- [ ] Đã kiểm tra broker auto-create bật hay tắt và policy áp dụng.
- [ ] Đã provision tài nguyên vật lý nếu broker yêu cầu.
- [ ] Đã cấu hình administered object/JNDI binding nếu ứng dụng dùng JNDI.
- [ ] `JmsTemplate` và listener container dùng resolver và Queue/Topic domain phù hợp.
- [ ] Đã cấp quyền send/consume/manage theo nguyên tắc tối thiểu.
- [ ] Đã kiểm tra TTL, durability, dead-letter, redelivery và giới hạn dung lượng.
- [ ] Đã có smoke test và giám sát trạng thái destination trên broker.

## 15. Tài liệu tham khảo

- [Jakarta Messaging 3.1 — Session.createQueue/createTopic](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.jms/jakarta/jms/session)
- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)
- [Spring Framework — Using Spring JMS: Destination Management](https://docs.spring.io/spring-framework/reference/integration/jms/using.html)
- [Spring Framework — DestinationResolver API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/support/destination/DestinationResolver.html)
- [Spring Framework — SimpleDestinationResolver API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/support/destination/SimpleDestinationResolver.html)
- [Spring Framework — DynamicDestinationResolver API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/support/destination/DynamicDestinationResolver.html)
- [Spring Framework — JndiDestinationResolver API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/support/destination/JndiDestinationResolver.html)
- [Spring Framework — JmsDestinationAccessor API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/support/destination/JmsDestinationAccessor.html)
