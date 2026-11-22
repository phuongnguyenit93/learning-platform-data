# DynamicDestinationResolver và giới hạn cấp phát vật lý trong Spring JMS

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích tại sao `DynamicDestinationResolver` đổi **tên logic** thành đối tượng JMS `Queue` hoặc `Topic` nhưng **không đảm bảo tạo tài nguyên vật lý** trong broker.
2. Theo dõi luồng giải quyết destination của `JmsTemplate` và listener container: `DestinationResolver.resolveDestinationName(Session, String, boolean)` → `Session.createQueue(...)` / `createTopic(...)`.
3. Phân biệt **destination được khai báo/tra cứu**, **đối tượng Java đại diện destination**, **địa chỉ/queue/topic được broker cấp phát**, và **temporary destination**.
4. Biết khi nào cần dùng `JndiDestinationResolver`, provision trước bằng công cụ broker, hoặc cho phép broker auto-create.
5. Đánh giá rủi ro từ tên destination sinh động: tạo bừa queue, nhầm Queue/Topic, phân mảnh hàng đợi, resource leak, ACL/tenant isolation và khả năng mất message.
6. Viết và chạy ví dụ Spring Boot + Jakarta Messaging + Artemis, đồng thời kiểm tra đúng trạng thái tài nguyên trong broker.

**Ý cốt lõi:** `DynamicDestinationResolver` là **chiến lược phân giải tên ở phía ứng dụng Spring**, không phải một API quản trị broker hay công cụ bảo đảm cấp phát queue/topic. Từ “dynamic” mô tả cách dùng tên tại runtime; nó **không bảo đảm** broker sẽ cấp phát destination vật lý.

## 1. Vấn đề: một tên destination trong code có ý nghĩa gì?

Ứng dụng Spring thường có những lời gọi rất ngắn:

~~~java
jmsTemplate.convertAndSend("orders.incoming", "order-42");
~~~

Người mới học dễ suy ra câu lệnh trên có nghĩa “Spring đã tạo queue `orders.incoming`, rồi lưu message vào đó”. Trên thực tế có ba bước độc lập:

~~~text
Ứng dụng Spring
   |
   | tên String = "orders.incoming"
   v
JmsTemplate / DestinationResolver
   |
   | trả về javax.jms.Destination hoặc jakarta.jms.Destination
   | (với Spring 6+ là jakarta.jms)
   v
JMS client/provider
   |
   | dùng đối tượng Destination để send/createConsumer
   v
Broker
   |
   | kiểm tra address/queue/topic/subscription, quyền và chính sách
   | có thể: tồn tại sẵn / tự tạo / báo lỗi / không có tuyến nhận
   v
Tài nguyên vật lý và thông điệp thực sự được lưu/định tuyến
~~~

Bước “resolve tên” **không đồng nghĩa** với bước “allocate tài nguyên vật lý”. Định danh tên có thể hợp lệ trên client nhưng broker chưa có queue, broker đang tắt auto-create, người dùng thiếu quyền tạo/ghi, hoặc tên đó thuộc sai loại destination.

### Các lớp trách nhiệm

| Lớp | Đối tượng/ví dụ | Trách nhiệm thực sự |
|---|---|---|
| Ứng dụng | `"orders.incoming"`, config `app.jms.ordersQueue` | Chọn tên và ý nghĩa nghiệp vụ. |
| Spring JMS | `DestinationResolver`, `JmsTemplate`, listener container | Biến tên thành `Destination` được JMS client hiểu. |
| Jakarta Messaging API | `Session.createQueue(String)`, `createTopic(String)` | Tạo **đối tượng tham chiếu** tới destination có tên theo provider. |
| JMS provider/client | Ví dụ Artemis Jakarta client | Chuyển lời gọi Java thành tương tác với broker theo protocol/provider. |
| Broker | Address, queue, routing, subscription, journal, ACL | Quản lý tài nguyên thực tế, cấu hình durability, retention, routing, auto-create, DLQ. |
| Vận hành | Admin API, CLI, XML/IaC | Provision/kiểm soát cấu hình và vòng đời tài nguyên. |

Đây là một bài thuộc nhóm **Destination**. Chúng ta tập trung vào cách xác định destination và giới hạn cấp phát; transaction, acknowledgement hay retry chỉ nhắc tới ở nơi ảnh hưởng đến thử nghiệm và chẩn đoán.

## 2. `DestinationResolver` là gì?

Spring khai báo interface:

~~~java
package org.springframework.jms.support.destination;

// Dạng chữ ký minh họa; import từ thư viện spring-jms thực tế.
public interface DestinationResolver {
    Destination resolveDestinationName(
            Session session,
            String destinationName,
            boolean pubSubDomain) throws JMSException;
}
~~~

Trong Spring 6/7, `Destination`, `Session` và `JMSException` ở đây thuộc package `jakarta.jms`. Dự án Spring 5 dùng `javax.jms`; không trộn namespace.

Tham số có ý nghĩa:

- `session`: JMS session đang được Spring sử dụng; resolver động cần session để gọi API tạo tham chiếu.
- `destinationName`: chuỗi tên mà caller hoặc cấu hình listener truyền vào.
- `pubSubDomain`: `false` nghĩa là **Queue** (point-to-point), `true` nghĩa là **Topic** (publish/subscribe).
- Kết quả: một `jakarta.jms.Destination`; có thể là `Queue` hoặc `Topic`. Đây là tham chiếu, không phải bằng chứng rằng broker đã có destination.

Spring có nhiều chiến lược resolution. `DynamicDestinationResolver` là **mặc định** cho `JmsTemplate`. `JndiDestinationResolver` tìm một Destination được đặt trong JNDI. Ứng dụng còn có thể tự cài `DestinationResolver` để kiểm soát whitelist, mapping theo môi trường hoặc tenant.

### Khi nào Spring phải resolve?

- `jmsTemplate.send("orders.incoming", creator)` hoặc `convertAndSend("orders.incoming", payload)`: caller truyền String, template cần biến tên thành `Destination`.
- `@JmsListener(destination = "orders.incoming")`: listener container cần destination để tạo JMS consumer; thường dùng `DestinationResolver` của container.
- `jmsTemplate.receive("orders.incoming")`: cần destination để tạo consumer nhận đồng bộ.

Nếu code truyền sẵn một đối tượng `Destination` trong overload API thích hợp thì có thể không cần phân giải lại bằng tên String.

## 3. `DynamicDestinationResolver` thực hiện điều gì?

Class ở package:

~~~java
org.springframework.jms.support.destination.DynamicDestinationResolver
~~~

Về bản chất, cách hoạt động là:

~~~java
// MÃ MÔ TẢ CƠ CHẾ, không phải nguyên văn source Spring.
public Destination resolveDestinationName(
        Session session, String destinationName, boolean pubSubDomain)
        throws JMSException {
    if (pubSubDomain) {
        return session.createTopic(destinationName);
    }
    return session.createQueue(destinationName);
}
~~~

Các phương thức `resolveTopic(...)` và `resolveQueue(...)` của resolver cho phép Spring phân nhánh sang loại tương ứng. Giá trị `pubSubDomain` có ý nghĩa ở **thời điểm resolution**, không đơn thuần là nhãn trang trí.

| Input | Lời gọi JMS điển hình | Loại kết quả |
|---|---|---|
| `"orders.incoming"`, `pubSubDomain=false` | `session.createQueue("orders.incoming")` | `Queue` |
| `"orders.incoming"`, `pubSubDomain=true` | `session.createTopic("orders.incoming")` | `Topic` |
| `"billing.queue"`, `pubSubDomain=false` | `session.createQueue("billing.queue")` | `Queue` |
| `"order.events"`, `pubSubDomain=true` | `session.createTopic("order.events")` | `Topic` |

Tên String **không tự chỉ ra** đây là Queue hay Topic. Hai hệ thống dùng cùng String nhưng khác `pubSubDomain` có thể kết nối tới tài nguyên khác nhau, nhận được hành vi khác nhau hoặc bị broker từ chối.

### 3.1. Không gọi JNDI theo mặc định

`DynamicDestinationResolver` không tự lookup tên trong JNDI. Nó dùng `Session`. Nếu deployment yêu cầu JNDI-administered destinations, cần cấu hình `JndiDestinationResolver` hoặc inject trực tiếp object `Destination` lấy từ JNDI.

### 3.2. Không tự chọn naming policy tốt cho bạn

Resolver chấp nhận tên được truyền vào và ủy quyền cho JMS provider. Nó không tự bảo đảm:

- Đúng danh sách queue được phép.
- Tên tương ứng với environment/tenant.
- Không vô tình sinh queue từ user input.
- Queue được provision với retention, DLQ, max consumers và quota phù hợp.
- Queue/Topic tồn tại đúng broker đang kết nối.
- Người dùng có quyền gửi/nhận/tạo resource.

Các kiểm soát đó thuộc tầng ứng dụng, triển khai broker và vận hành.

## 4. Ranh giới theo Jakarta Messaging: `createQueue` không tạo queue vật lý

Java API định nghĩa:

~~~java
Queue queue = session.createQueue("orders.incoming");
Topic topic = session.createTopic("orders.events");
~~~

Điểm quan trọng trong Javadoc Jakarta Messaging:

- `Session.createQueue(String)` tạo **đối tượng Queue mô tả tên queue theo provider**.
- `Session.createTopic(String)` tạo **đối tượng Topic mô tả tên topic theo provider**.
- Hai API này **không được đặc tả là thao tác tạo resource vật lý** ở broker. JMS API không chuẩn hóa lệnh chung để tạo queue/topic vật lý.
- Nhà cung cấp có thể **tự tạo** tài nguyên khi ứng dụng gửi/nhận, hoặc thậm chí trong quá trình resolution, nếu có extension/auto-create; đó là hành vi **provider-specific**.
- Việc dùng tên provider-specific có thể làm giảm tính portable của ứng dụng giữa những JMS broker khác nhau.

Do đó, hai phát biểu sau phải được tách rõ:

1. “`DynamicDestinationResolver` giải quyết được tên thành `Queue`” — mô tả kết quả tại client.
2. “Broker đã cấp phát một queue bền vững và message sẽ được lưu tại đó” — đòi hỏi kiểm tra **cấu hình, trạng thái broker và kết quả gửi/nhận**.

**Không lấy câu lệnh `createQueue` thành công làm bằng chứng provisioning thành công.**

### 4.1. “Dynamic destination” khác “Temporary destination”

| Khía cạnh | Dynamic destination (qua tên) | Temporary destination (`createTemporaryQueue/Topic`) |
|---|---|---|
| Danh tính | Tên do ứng dụng chọn, ví dụ `orders.incoming` | Provider sinh identity tạm thời |
| JMS API gọi | `createQueue(name)` / `createTopic(name)` | `createTemporaryQueue()` / `createTemporaryTopic()` |
| Tạo vật lý theo chuẩn | **Không đảm bảo** | API JMS có cơ chế tạo temporary destination |
| Vòng đời | Broker/admin policy; có thể tồn tại lâu dài | Phụ thuộc connection sở hữu và quy tắc temporary destination |
| Nhu cầu | Queue/Topic được biết bằng tên runtime | Reply queue tạm trong request-reply, phiên làm việc tạm |

`DynamicDestinationResolver` **không** phải alias cho `Session.createTemporaryQueue()`. Dù tên có chữ “dynamic”, destination được resolve từ String có thể là queue tồn tại từ trước, hoặc broker auto-create theo cấu hình và tiếp tục tồn tại sau khi ứng dụng dừng.

### 4.2. “Destination object” khác “producer/consumer”

Tạo `Queue` object không đồng nghĩa tạo `MessageProducer` hay `MessageConsumer`. Chỉ các lời gọi `createProducer(queue)`, `createConsumer(queue)`, `send` hoặc Spring listener startup mới thực sự kích hoạt tương tác cần thiết với provider/broker; lúc ấy broker mới có thể thực thi các quy tắc quyền, routing và auto-create.

## 5. Các kịch bản thực tế khi resolve tên

Giả sử `DynamicDestinationResolver` được gọi với `"orders.incoming"`, `pubSubDomain=false`:

### Kịch bản A — Queue đã được provision sẵn

Broker đã có queue `orders.incoming` với routing, durability, ACL và DLQ được quản lý. Resolver trả `Queue` object, rồi producer/consumer dùng queue đó. Đây là mô hình dễ kiểm soát nhất cho production.

### Kịch bản B — Broker bật auto-create phù hợp

Broker chưa có queue, nhưng cấu hình cho phép tự tạo queue khi producer send hoặc consumer attach. Lúc đó broker có thể tạo queue vật lý với **các thuộc tính mặc định** theo matching policy. Đây là hành vi của broker, không phải cam kết của Spring.

Phù hợp cho thử nghiệm hoặc trường hợp runtime destinations được thiết kế chủ động, nhưng production cần quota và lifecycle rõ ràng.

### Kịch bản C — Broker tắt auto-create, queue chưa tồn tại

Resolver vẫn có thể trả về object `Queue`. Khi producer send hoặc consumer tạo listener, broker/provider có thể báo destination không hợp lệ/không tồn tại, từ chối consumer, hoặc xử lý gửi không có tuyến nhận theo chính sách. **Không dự đoán duy nhất một exception hay kết quả cho mọi broker.**

### Kịch bản D — Tên hợp lệ nhưng không có quyền

Queue có thể tồn tại, nhưng principal đang kết nối không có quyền `send`/`consume` hoặc quyền tạo. Resolver không tự cấp quyền. Lỗi xuất hiện khi client thực hiện thao tác bị cấm, thường ở send/consumer initialization, và kiểu lỗi phụ thuộc provider.

### Kịch bản E — Tên là Topic, code cấu hình Queue

Nếu producer resolve `"orders.events"` thành Queue còn subscriber resolve cùng tên thành Topic, hai bên không cùng semantics. Với broker có địa chỉ và queue routing kiểu anycast/multicast, mismatch có thể dẫn đến không có consumer phù hợp hoặc message bị xử lý sai tuyến.

### Kịch bản F — Gửi thành công nhưng subscriber không nhận

Với JMS Topic, một **non-durable subscription** thường không nhận lại message được phát trong lúc subscriber offline. Có physical destination không đồng nghĩa broker sẽ lưu mọi thông điệp cho subscriber chưa tồn tại. Cần chọn durable/shared subscription đúng ngữ cảnh, không đổ lỗi cho resolver.

## 6. `pubSubDomain`: chốt loại destination từ đầu

Spring `JmsDestinationAccessor` và `JmsTemplate` có thuộc tính:

~~~java
jmsTemplate.setPubSubDomain(false); // Queue; giá trị mặc định
jmsTemplate.setPubSubDomain(true);  // Topic
~~~

Không nên thay đổi thuộc tính trên singleton `JmsTemplate` liên tục ở runtime khi các thread khác đang sử dụng; hãy cấu hình xong trước khi bean hoạt động.

- `false` = point-to-point `Queue` khi resolve theo tên.
- `true` = publish/subscribe `Topic` khi resolve theo tên.
- Chỉ đổi flag không hề chuyển một queue vật lý thành topic vật lý.

Trong Spring Boot, property `spring.jms.pub-sub-domain=true` có thể cấu hình các JMS component được auto-configure theo Topic. Nếu tự tạo `JmsTemplate` hay listener factory, hãy cấu hình chúng nhất quán.

### Hệ quả khi producer và listener không cùng domain

~~~text
Producer:
  JmsTemplate(pubSubDomain=false)
    └─ "orders.events" → Session.createQueue("orders.events")

Listener:
  ListenerFactory(pubSubDomain=true)
    └─ "orders.events" → Session.createTopic("orders.events")

Cùng tên String nhưng khác loại JMS Destination!
~~~

Không có quy tắc rằng Queue và Topic cùng tên sẽ tự liên thông với nhau. Hãy dùng tên rõ nghĩa (ví dụ `orders.commands` / `orders.events`), kiểm tra broker routing và test end-to-end trên đúng tên đã provision.

## 7. Cách Spring JMS nối resolver với `JmsTemplate`

### 7.1. Phân giải tên qua `JmsTemplate`

~~~java
// Snippet trong bean đã inject jakarta.jms.ConnectionFactory.
JmsTemplate template = new JmsTemplate(connectionFactory);
template.setDestinationResolver(new DynamicDestinationResolver());
template.setPubSubDomain(false); // Chọn Queue
template.convertAndSend("orders.incoming", "order-42");
~~~

Đoạn trên dùng `org.springframework.jms.core.JmsTemplate` và `org.springframework.jms.support.destination.DynamicDestinationResolver`. Không cần tạo resolver thủ công vì đó đã là **mặc định**, nhưng khai báo rõ giúp minh họa. `convertAndSend` dùng message converter của template (String thường thành `TextMessage`), mở/lấy session, resolve destination và gửi qua provider.

**Không thể kết luận** queue vật lý đã được tạo chỉ từ lời gọi `convertAndSend`. Trước khi gửi, hãy biết policy broker; sau khi gửi, kiểm tra queue/subscription và route thực tế.

### 7.2. Default destination

Có thể cấu hình `template.setDefaultDestinationName("orders.incoming")` để dùng `convertAndSend(payload)` mà không truyền tên mỗi lần. Tên mặc định **vẫn** chịu resolver, Queue/Topic flag, quyền và broker provisioning. Default destination là cấu hình tên, không phải công cụ tạo resource.

### 7.3. Listener container cũng cần resolver

Listener `@JmsListener` không chia sẻ mặc định mọi cấu hình của một `JmsTemplate` bean tùy ý. Các listener container có cấu hình `DestinationResolver` và `pubSubDomain` riêng qua `DefaultJmsListenerContainerFactory`, ví dụ:

~~~java
@Bean
DefaultJmsListenerContainerFactory queueListenerFactory(
        ConnectionFactory connectionFactory) {
    var factory = new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setDestinationResolver(new DynamicDestinationResolver());
    factory.setPubSubDomain(false);
    factory.setSessionTransacted(true);
    return factory;
}
~~~

Nếu tự định nghĩa factory, nhớ đặt `ConnectionFactory` và các yêu cầu transaction/concurrency. Để message thực sự đến listener, producer và consumer phải thống nhất tên, loại destination, broker cluster, credentials và routing.

## 8. `DynamicDestinationResolver` so với `JndiDestinationResolver`

Spring cung cấp `JndiDestinationResolver` để ánh xạ tên sang Destination object **đã được đăng ký trong JNDI** thay vì tự tạo tham chiếu bằng `Session.createQueue/Topic`.

| Khía cạnh | `DynamicDestinationResolver` | `JndiDestinationResolver` |
|---|---|---|
| Nguồn ánh xạ | `Session.createQueue/Topic(name)` | JNDI lookup tên resource |
| Yêu cầu JNDI registry | Không | Có, cùng môi trường JNDI phù hợp |
| Cách dùng tên | Chuỗi tên broker/provider | Tên JNDI có thể khác tên vật lý |
| Có chứng minh queue vật lý tồn tại? | Không | **Cũng không phải chứng minh vận hành**; JNDI object có thể trỏ resource sai/mất/không còn quyền |
| Khi tên không được resolve | JMS provider có thể trả tham chiếu/lỗi | JNDI lookup lỗi, trừ khi bật fallback |
| Fallback về dynamic | Bản thân đã dynamic | `setFallbackToDynamicDestination(true)` (mặc định **false**) |
| Cache | Không phải registry/provisioning manager | Cache kết quả JNDI mặc định **true**, có thể tắt qua `setCache(false)` |
| Nhu cầu thường gặp | Dev/test; broker auto-create; tên đã được quản lý ngoài code | Môi trường app server/enterprise quản lý JMS destinations qua JNDI |

Ví dụ cấu hình chặt theo JNDI:

~~~java
@Bean
JmsTemplate jndiTemplate(ConnectionFactory connectionFactory) {
    JndiDestinationResolver resolver = new JndiDestinationResolver();
    resolver.setCache(true);
    resolver.setFallbackToDynamicDestination(false);

    JmsTemplate template = new JmsTemplate(connectionFactory);
    template.setDestinationResolver(resolver);
    template.setPubSubDomain(false);
    return template;
}
~~~

*Snippet đặt trong `@Configuration` class có các import Spring tương ứng; JNDI context phải được cấu hình bởi môi trường*. Với `fallback=false`, việc lookup thiếu tên gây lỗi thay vì tự thử dynamic resolution. Điều này hữu ích khi một resource cần được admin phê duyệt.

Lưu ý Spring `JndiDestinationResolver` cache theo **destination name**; nếu tên trùng nhau giữa Queue và Topic, hành vi cache/mismatch dễ gây nhầm lẫn. Nên đặt tên phân biệt và dùng các resolver/factory rõ scope.

### 8.1. Có nên bật fallback?

~~~java
resolver.setFallbackToDynamicDestination(true);
~~~

Bật fallback nghĩa là nếu không tìm thấy JNDI entry, resolver có thể chuyển sang `DynamicDestinationResolver`. Điều này tiện khi dev, nhưng **không có nghĩa** “tự provision hợp lệ”. Trong production có chính sách quản trị chặt, fallback vô tình che giấu lỗi naming/JNDI và phụ thuộc broker auto-create; nên đánh giá kỹ trước khi bật.

## 9. Giới hạn cấp phát vật lý: một broker thực sự tạo những gì?

Không phải mọi broker biểu diễn Queue/Topic thành cùng một cấu trúc nội bộ. Lấy **ActiveMQ Artemis** làm ví dụ:

- **Address**: điểm định tuyến message.
- **Queue**: tài nguyên nhận và lưu message gắn với address.
- **Routing type ANYCAST**: message thường được định tuyến đến một queue phù hợp trên address.
- **Routing type MULTICAST**: message được phân phối cho các queue/subscription phù hợp trên address.

Mô hình JMS Queue và JMS Topic được Artemis ánh xạ sang address/queue/routing/ subscription tương ứng. Đây là cấu trúc **riêng của Artemis**, không phải JMS spec áp cho mọi nhà cung cấp.

### 9.1. Auto-create trong Artemis

Các address setting của Artemis cho phép quản lý:

- `auto-create-addresses`: có cho tạo address khi client dùng một address chưa tồn tại hay không.
- `auto-create-queues`: có cho tạo queue tương ứng khi cần hay không.
- `default-address-routing-type` và `default-queue-routing-type`: định tuyến mặc định.
- `auto-delete-addresses`, `auto-delete-queues` và các điều kiện/độ trễ xóa: vòng đời tài nguyên tự tạo.
- Quyền `createAddress`/`createDurableQueue`/`send`/`consume` và các quyền liên quan: client được làm gì.

Trong cấu hình Artemis phổ biến, auto-create được bật mặc định cho các giao thức/client hỗ trợ. **Không áp dụng giả định này cho mọi broker hay mọi môi trường**: tổ chức có thể tắt tính năng hoặc giới hạn bằng pattern địa chỉ và ACL.

### 9.2. Ví dụ cấu hình broker

Đoạn cấu hình **minh họa** bên trong `broker.xml` của Artemis, cần đặt đúng vị trí XML theo schema và phiên bản broker:

~~~xml
<!-- Tắt auto-create cho namespace production quan trọng. -->
<address-settings>
  <address-setting match="prod.orders.#">
    <auto-create-addresses>false</auto-create-addresses>
    <auto-create-queues>false</auto-create-queues>
  </address-setting>
</address-settings>
~~~

Trong khi đó, resource được quản trị chủ động:

~~~xml
<addresses>
  <address name="prod.orders.incoming">
    <anycast>
      <queue name="prod.orders.incoming" durable="true"/>
    </anycast>
  </address>
</addresses>
~~~

Hai đoạn là **các phần của cấu hình broker**, không phải file `broker.xml` đầy đủ; cần tích hợp theo schema, security settings và deployment hiện tại. Sau khi provision, verify trong broker console/management rằng address và queue đã tồn tại với đúng routing và quyền.

**Điểm cần nhớ:** Tắt auto-create **không tắt** hoạt động của `DynamicDestinationResolver` tại phía Spring. Nó chỉ thay đổi khả năng broker cấp phát queue/address khi client sử dụng destination chưa tồn tại.

### 9.3. Nếu thiếu queue khi tắt auto-create, điều gì xảy ra?

Tùy provider và policy, producer có thể nhận exception, gửi vào address mà không có queue/subscription phù hợp, hoặc message không được route tới consumer mong muốn. Một số client thực hiện kiểm tra sớm, một số kiểm tra muộn. Không viết unit test khẳng định exception xảy ra **ngay tại `createQueue()`** trừ khi đã chứng minh provider thực tế có hành vi đó.

Hãy đo bằng hai nhóm tín hiệu:

1. **Ứng dụng**: success/failure khi send, listener start, metrics và logs.
2. **Broker**: address/queue tồn tại, routing type, số message trong queue, consumer count, routing failures, DLQ.

Một bản ghi "send successful" không đủ để chứng minh mọi subscriber/worker đã xử lý message.

## 10. Demo hoàn chỉnh: Spring Boot 3.5, Java 17, Artemis

Ví dụ này mô tả quá trình Spring phân giải tên `"lesson.orders.incoming"` thành **Queue** và gửi message đến consumer. Broker chạy trong Docker với chính sách auto-create mặc định để dễ học; phần sau giải thích cách thay bằng provision chủ động.

### 10.1. Điều kiện chạy

- JDK 17+, Maven 3.9+ và Docker.
- Port `61616` (messaging) và `8161` (management console) còn trống.
- Không có ứng dụng khác cùng đọc queue demo.
- Đây là demo trên broker riêng, không thực hiện trên production.

Khởi chạy broker Artemis bằng image chính thức:

~~~bash
docker run --detach --name resolver-artemis \
  -p 61616:61616 -p 8161:8161 --rm apache/artemis:latest-alpine
~~~

Khi broker sẵn sàng, console thường ở `http://localhost:8161`. Image chính thức mặc định cung cấp username/password `artemis` cho demo. Có thể theo dõi khởi động bằng:

~~~bash
docker logs resolver-artemis
~~~

### 10.2. Cấu trúc dự án

~~~text
dynamic-resolver-demo/
├── pom.xml
└── src/main/
    ├── java/example/DynamicResolverDemoApplication.java
    └── resources/application.properties
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.5</version>
    <relativePath/>
  </parent>
  <groupId>example</groupId>
  <artifactId>dynamic-resolver-demo</artifactId>
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
~~~

`src/main/resources/application.properties`:

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=artemis
spring.artemis.password=artemis
~~~

Credentials này chỉ dùng cho bài thực hành cục bộ. Khi triển khai thật, đưa secret vào cơ chế cấu hình bảo mật.

### 10.3. Java source đầy đủ

Tạo file `src/main/java/example/DynamicResolverDemoApplication.java`:

~~~java
package example;

import jakarta.jms.ConnectionFactory;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.destination.DynamicDestinationResolver;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableJms
public class DynamicResolverDemoApplication {

    private static final String QUEUE = "lesson.orders.incoming";

    public static void main(String[] args) {
        SpringApplication.run(DynamicResolverDemoApplication.class, args);
    }

    @Bean
    JmsTemplate demoJmsTemplate(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setDestinationResolver(new DynamicDestinationResolver());
        template.setPubSubDomain(false); // Queue
        return template;
    }

    @Bean
    DefaultJmsListenerContainerFactory demoListenerFactory(
            ConnectionFactory connectionFactory) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setDestinationResolver(new DynamicDestinationResolver());
        factory.setPubSubDomain(false); // Cùng kiểu Queue với producer
        factory.setConcurrency("1");
        factory.setSessionTransacted(true);
        return factory;
    }

    @Bean
    ApplicationRunner publish(JmsTemplate demoJmsTemplate) {
        return args -> {
            demoJmsTemplate.convertAndSend(QUEUE, "order-42");
            System.out.println("Sent to: " + QUEUE);
        };
    }

    @Component
    public static class OrderListener {
        @JmsListener(destination = QUEUE,
                containerFactory = "demoListenerFactory")
        public void onMessage(String payload) {
            System.out.println("Received: " + payload);
        }
    }
}
~~~

**Tại sao ví dụ này chạy được?**

- Dependency `spring-boot-starter-artemis` có JMS client/provider integration và Spring JMS.
- Boot tạo `ConnectionFactory` nối tới Artemis theo properties.
- `JmsTemplate` được định nghĩa rõ với `DynamicDestinationResolver`. Khi gửi bằng String, resolver dùng `Session.createQueue("lesson.orders.incoming")`.
- Listener factory dùng cùng kiểu Queue và tên để tạo consumer.
- Artemis với auto-create được bật có thể tạo address/queue theo yêu cầu client nếu resource chưa tồn tại. Nếu cấu hình broker khác, phải provision trước.
- `setSessionTransacted(true)` áp dụng local JMS transaction cho listener; nó **không biến resolver thành transaction manager**.
- Listener nhận một `String` do message converter xử lý từ `TextMessage`.

### 10.4. Chạy

Ở thư mục chứa `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Trong điều kiện broker mới, không có consumer khác, ứng dụng in hai dòng nghiệp vụ đại loại như:

~~~text
Sent to: lesson.orders.incoming
Received: order-42
~~~

**Thứ tự hai dòng không được bảo đảm**, vì listener chạy trong thread của container, có thể xử lý trước hoặc sau khi publisher in “Sent”. Ngoài ra console còn log Spring Boot/Artemis. Nếu queue tồn tại từ bài thực hành trước và còn message, kết quả có thể khác; dùng broker/queue riêng để tránh nhiễu.

Mở Artemis management console, kiểm tra thực tế:

1. Có address/queue `lesson.orders.incoming` không?
2. Queue có routing kiểu nào? Có khớp với mô hình JMS Queue không?
3. Producer đã send, consumer có active và nhận message không?
4. Message count về 0 sau khi listener xử lý thành công (nếu không có thêm traffic) hay có message nằm lại?
5. Broker có report tự tạo resource hay đã provision từ trước?

Những kiểm tra này mới giúp xác nhận **trạng thái broker**, khác hẳn việc chỉ nhìn `DynamicDestinationResolver` trả object.

Kết thúc bài thử:

~~~bash
docker stop resolver-artemis
~~~

Container được chạy với `--rm` nên sẽ xóa khi dừng; **không dùng cấu hình này để lưu message lâu dài**.

### 10.5. Thử nghiệm tương phản: tắt auto-create

Để thấy giới hạn vật lý:

- Ở broker thử nghiệm riêng, tắt `auto-create-addresses` và `auto-create-queues` cho namespace `lesson.#`.
- Xác nhận queue `lesson.orders.incoming` **không tồn tại**, thử chạy app: tùy broker/client, listener có thể không khởi tạo, gửi có thể lỗi hoặc không được route như mong đợi.
- Provision address/queue thích hợp qua broker CLI/admin/config, xác nhận quyền send/consume.
- Chạy lại app mới: lúc này code Java **không đổi**, nhưng tài nguyên broker đã sẵn sàng nên gửi/nhận được.

Bài học không nằm ở tên exception cụ thể, mà ở việc cùng một `DynamicDestinationResolver` có thể hoạt động với **hai kết quả hạ tầng khác nhau** tùy provisioning policy.

## 11. Khi nào nên cấp phát động, khi nào nên quản trị sẵn?

| Tình huống | Hướng chọn | Cần xác thực |
|---|---|---|
| Demo local, test container ngắn hạn | Có thể bật auto-create trong broker riêng | Namespace cô lập, xóa sạch sau test, không lộ cổng ra mạng không tin cậy. |
| Production queue cố định cho job/command | Provision bằng cấu hình broker hoặc IaC; app dùng tên quản lý | Durability, ACL, DLQ, routing, quota, monitoring, backup. |
| Topic sự kiện dùng chung nhiều service | Provision address/topic và cấu hình subscription trước khi phát nếu cần durable | Consumer semantics, missing subscriber, TTL và retention. |
| Mỗi tenant muốn queue riêng | Chỉ cho tạo qua control-plane được giới hạn và có quota | Tenant isolation, naming, lifecycle, quyền, cardinality. |
| JMS destination do app server quản lý | `JndiDestinationResolver`/inject `Destination` | JNDI naming, broker binding, quyền, cách cache. |
| Request-reply tạm thời | `TemporaryQueue/TemporaryTopic` hoặc pattern request-reply phù hợp | Lifecycle connection, reply timeout, cleanup. |
| Tên destination đến từ user input | Allowlist/mapping server-side; không đưa input thẳng vào `convertAndSend` | Resource abuse, ACL bypass, spelling errors và “ghost queues”. |

### 11.1. Sai tên có thể trở thành “queue rác”

Nếu broker bật auto-create, typo như `orders.incomming` (thừa chữ m) có thể tạo queue mới. Producer gửi “thành công” nhưng listener nghe `orders.incoming` nên không nhận. Trên dashboard sẽ có hai queue khác nhau, một queue chỉ tích message. Nếu cùng loại lỗi tái diễn với tên sinh từ UUID/request parameter, broker có thể phình số lượng address/queue.

### 11.2. Tạo một queue mỗi request không phải chiến lược mặc định

Mỗi resource có metadata, journal/binding, consumer, metrics và chi phí quản trị. Với hàng nghìn/hàng triệu tên runtime, ngay cả khi provider hỗ trợ auto-create cũng không có nghĩa là bền vững. Ưu tiên chia sẻ queue có message properties như `tenantId`/`requestId` khi đáp ứng isolation, hoặc một control-plane tạo queue có hạn ngạch, TTL và cleanup.

### 11.3. Khi nào auto-delete gây mất dữ liệu?

Với broker có chính sách tự xóa queue/address khi không còn consumer, nếu cấu hình không đúng, message chưa nhận hoặc subscription chưa bền vững có thể không còn nơi lưu. Quy tắc xóa thường xét số message, consumer count, delay và loại tài nguyên; cần kiểm tra thực tế, không suy ra từ tên “dynamic”.

## 12. Chặn tên động tùy tiện bằng resolver tùy chỉnh

Có thể viết lớp bao `DynamicDestinationResolver` để **chỉ cho các tên Queue đã duyệt**. Đây là cơ chế kiểm soát **phía client**; vẫn cần ACL ở broker và provisioning.

~~~java
package example;

import jakarta.jms.Destination;
import jakarta.jms.JMSException;
import jakarta.jms.Session;
import java.util.Set;
import org.springframework.jms.support.destination.DestinationResolver;
import org.springframework.jms.support.destination.DynamicDestinationResolver;

public final class ApprovedQueueResolver implements DestinationResolver {

    private static final Set<String> APPROVED = Set.of(
            "orders.incoming",
            "orders.failed"
    );

    private final DynamicDestinationResolver delegate =
            new DynamicDestinationResolver();

    @Override
    public Destination resolveDestinationName(
            Session session, String name, boolean pubSubDomain)
            throws JMSException {

        if (pubSubDomain) {
            throw new IllegalArgumentException(
                    "This resolver only supports JMS Queues");
        }
        if (!APPROVED.contains(name)) {
            throw new IllegalArgumentException(
                    "Destination is not approved: " + name);
        }
        return delegate.resolveDestinationName(session, name, false);
    }
}
~~~

Đây là **file Java hoàn chỉnh về mặt lớp**, tên file phải là `ApprovedQueueResolver.java` và cần dependencies `spring-jms` và Jakarta Messaging ở classpath. Nó chưa phải một ứng dụng độc lập có `main` hoặc broker.

Cấu hình template:

~~~java
// Trong method @Bean hoặc cấu hình khởi tạo.
JmsTemplate template = new JmsTemplate(connectionFactory);
template.setDestinationResolver(new ApprovedQueueResolver());
template.setPubSubDomain(false);
~~~

Khi truyền `"orders.incoming"`, resolver kiểm tra whitelist rồi gọi API JMS. Với `"orders.incomming"`, lỗi xuất hiện **trước khi dùng tên chưa duyệt gửi message**. Điều đó giúp phát hiện typo trong app nhưng **không** chứng minh queue được provision.

**Đừng dựa hoàn toàn vào resolver client để chống truy cập trái phép.** Một service khác hoặc client không dùng resolver đó vẫn có thể kết nối; broker phải kiểm tra quyền theo principal, address/queue và hành động tương ứng.

### 12.1. Những chính sách có thể đặt trong custom resolver

- Mapping tên logic `"order-command"` → tên broker `"prod.orders.commands.v1"`, tách domain khỏi môi trường.
- Kiểm tra namespace và whitelist trước khi gọi JMS.
- Từ chối Queue/Topic mismatch dựa trên cấu hình module.
- Logging tên logic và resolved name để kiểm toán.
- Dùng JNDI hoặc registry đáng tin thay cho việc suy từ input.

Không nên biến `DestinationResolver` thành vòng code provisioning nặng, thực hiện HTTP admin API trong từng `send` hoặc có side effect không kiểm soát. Provisioning nên đặt ở deployment/control-plane, tách vòng đời dài của broker resource khỏi vòng đời ngắn của JMS operation.

## 13. Vòng đời và ownership của dynamic destinations

Một destination ở client và một resource vật lý ở broker có **vòng đời khác nhau**:

~~~text
App start ─► tạo JMS Connection/Session
                └─ resolver được gọi (khi dùng tên)
                   └─ Destination Java object được dùng trong send/receive

Broker start/provision ─► tạo address/queue/topic với ACL, routing, DLQ
                            └─ tồn tại cho đến khi admin/policy xóa

App stop ─► đóng connection/session
                └─ KHÔNG ngụ ý mọi queue do app từng dùng sẽ bị xóa
~~~

`DynamicDestinationResolver` không có hợp đồng `deleteDestination()`, không quản lý leases, không đếm số queue thực, không có quota broker và không biết resource có đang dùng bởi service khác. Việc ứng dụng shutdown và broker resource còn tồn tại là bình thường trong messaging bền vững.

Nếu tổ chức cần dynamic queues thực sự:

1. Control-plane xét duyệt tên, loại và requester.
2. Provision trên broker qua cơ chế quản trị (hoặc auto-create có ACL + quota rõ).
3. Lưu registry gồm owner, tenant, thời điểm tạo và thời điểm hết hạn.
4. Thông báo ứng dụng dùng đúng tên đã provision.
5. Theo dõi consumer/message count, depth, DLQ, resource usage.
6. Dọn dẹp chỉ khi đã chứng minh không còn consumer/message/điều kiện nghiệp vụ cần giữ.

## 14. Chẩn đoán lỗi thường gặp

### Triệu chứng 1 — `createQueue` không lỗi nhưng `send` thất bại

Nguyên nhân khả dĩ: broker không cho auto-create, queue chưa provision, ACL thiếu quyền send, sai routing. Bắt đầu bằng broker address/queue list và log từ JMS provider; không khẳng định resolver đã tạo resource.

### Triệu chứng 2 — `convertAndSend` trả về thành công nhưng listener im lặng

Kiểm tra *đúng broker và vhost/cluster*, Queue vs Topic domain, tên typo, consumer đang chạy, queue depth, subscription, TTL và routing. Không dùng “send không ném exception” làm bằng chứng consumer đã nhận.

### Triệu chứng 3 — Có thêm hàng trăm queue không mong muốn

Kiểm tra tên runtime có ghép trực tiếp `tenantId`, `requestId`, timestamp, UUID hoặc input từ HTTP request không. Xem auto-create policy và namespace. Chặn ở ingress bằng mapping/allowlist; broker giới hạn quyền tạo, quota, cleanup.

### Triệu chứng 4 — Topic “mất” sự kiện khi consumer offline

Không phải lỗi riêng của resolver. Non-durable subscriber không có cam kết nhận message từ trước khi kết nối; cần durable subscription đúng identity và broker policy. Đừng dùng queue mặc định của `JmsTemplate` để giả lập topic chỉ vì chuỗi tên chứa `.events`.

### Triệu chứng 5 — Môi trường dev chạy, production báo destination không hợp lệ

Dev có thể bật auto-create; production tắt để quản lý. Kiểm tra deployment provision và quyền; không “sửa” bằng cách bật fallback/JMS auto-create một cách vô điều kiện nếu chính sách tổ chức yêu cầu quản trị.

### Triệu chứng 6 — JNDI lookup lỗi nhưng broker có queue

JNDI registry và broker resource là hai hệ thống tên khác nhau. Có queue vật lý không tự tạo JNDI binding. Xem configured JNDI context, lookup name và `JndiDestinationResolver.setFallbackToDynamicDestination(...)`.

### Triệu chứng 7 — Dùng cùng tên cho Queue và Topic

`DynamicDestinationResolver` chọn theo `pubSubDomain`, không theo tên. Nên tách không gian tên/bean template/listener factory hoặc trả `Destination` đã cấu hình rõ loại. Không đổi `pubSubDomain` của singleton template theo từng message.

### Triệu chứng 8 — Queue tự biến mất sau khi ngừng listener

Có thể broker đang bật auto-delete với điều kiện không còn consumer và queue rỗng. Đọc broker settings và bằng chứng event delete; không quy kết cho `DynamicDestinationResolver`. Queue tạm (`TemporaryQueue`) lại có vòng đời khác hẳn.

## 15. Checklist triển khai an toàn

Trước khi đưa Spring JMS service lên production:

1. **Destination catalog:** xác định danh sách tên logic, broker name, loại Queue/Topic, owner và môi trường.
2. **Resolver strategy:** chốt dùng `DynamicDestinationResolver`, JNDI hay custom mapping; không để một ứng dụng vô tình fallback sang dynamic.
3. **Provisioning:** quyết định resource tạo trước bằng IaC/admin hay broker được phép auto-create; biết cụ thể địa chỉ/queue/subscription được tạo ở đâu.
4. **Quyền:** gán principal chỉ đủ `send`/`consume` và quyền create nếu thật sự cần; phân quyền theo namespace/tenant.
5. **Durability:** queue policy, retention/expiry, DLQ, auto-delete, backup, HA và quota phải được định nghĩa bên broker.
6. **Type:** producer và consumer thống nhất `pubSubDomain`, tên, routing và loại subscription.
7. **Validation:** không đưa chuỗi trực tiếp từ người dùng vào destination name; giới hạn whitelist/prefix/độ dài và cardinality.
8. **Observability:** broker có metrics số address/queue, queue depth, message rates, unrouted messages, active consumers và DLQ; app log resolved name và lỗi.
9. **Deployment test:** chạy thử cả trường hợp resource tồn tại và không tồn tại, bật/tắt auto-create, thiếu quyền và tên typo.
10. **Lifecycle:** có quy trình xóa resource và tránh xóa queue còn message/consumer; không giao nhiệm vụ này cho Spring resolver.

## 16. Câu hỏi tự kiểm tra

**1. `DynamicDestinationResolver.resolveDestinationName(session, "orders", false)` thành công có chứng minh broker đã tạo queue `orders` không?** Không. Chỉ chứng minh resolver trả được `Destination` object trong JMS client.

**2. `pubSubDomain=true` làm gì?** Resolver chọn `Session.createTopic(name)` thay vì `createQueue(name)`. Nó không đổi kiểu resource có sẵn ở broker.

**3. Tắt `auto-create-queues` có làm Spring không gọi được `session.createQueue` không?** Không nhất thiết. Lời gọi tạo object và chính sách cấp phát broker là hai trách nhiệm riêng. Lỗi thực tế có thể xuất hiện ở send/consumer startup.

**4. Dynamic destination và TemporaryQueue có giống nhau không?** Không. Dynamic dùng tên ứng dụng chọn; temporary được tạo bởi JMS API tạm thời và có vòng đời gắn với connection.

**5. Vì sao cùng code chạy local nhưng fail ở production?** Broker khác policy auto-create/ACL/provisioning hoặc khác loại destination, không phải chỉ vì Java code.

**6. `JndiDestinationResolver.setFallbackToDynamicDestination(false)` có ý nghĩa gì?** Nếu JNDI lookup không có resource thì không tự fallback sang tạo destination reference bằng cách dynamic; thuận lợi cho chính sách kiểm soát naming.

**7. Sử dụng userId/UUID làm tên queue mỗi request có rủi ro gì?** Resource explosion, leaked queues, khó quản trị ACL, metric cardinality cao, queue không ai nhận, tốn lưu trữ.

**8. Một listener Topic mở sau khi producer gửi có chắc nhận event cũ không?** Không. Non-durable subscription thường không nhận lịch sử trước khi nó hoạt động; cần thiết kế subscription và retention phù hợp.

**9. Khi `JmsTemplate.convertAndSend(...)` thành công, cần kiểm tra thêm điều gì?** Broker routing/queue, consumer depth, delivery/ack và logs. Thành công phía producer không chứng minh business consumer xử lý thành công.

**10. Cơ chế đảm bảo queue vật lý có đúng DLQ và quota là gì?** Broker provisioning/config/admin (hoặc auto-create với policy được kiểm soát), không phải bản thân `DynamicDestinationResolver`.

## 17. Tài liệu tham khảo chính thức

- [Spring Framework — Using Spring JMS / Destination Management](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): mô tả `JmsTemplate`, `DynamicDestinationResolver` mặc định, `JndiDestinationResolver` và việc physical destination phụ thuộc provider.
- [Spring Framework — API DynamicDestinationResolver](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/support/destination/DynamicDestinationResolver.html): `resolveDestinationName`, `resolveQueue`, `resolveTopic`.
- [Spring Framework — API JndiDestinationResolver](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/support/destination/JndiDestinationResolver.html): JNDI lookup, cache và fallback.
- [Jakarta Messaging API — Session](https://jakarta.ee/specifications/platform/11/apidocs/jakarta/jms/session): `createQueue`/`createTopic` chỉ tạo reference object, không cấp phát vật lý.
- [Spring Boot — JMS and Artemis](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html): cấu hình `spring-boot-starter-artemis`, `ConnectionFactory` và JMS auto-configuration.
- [Apache ActiveMQ Artemis — Address Model](https://artemis.apache.org/components/artemis/documentation/latest/address-model.html): address, queue, ANYCAST/MULTICAST.
- [Apache ActiveMQ Artemis — Address Settings](https://artemis.apache.org/components/artemis/documentation/latest/address-settings.html): `auto-create-queues`/`auto-create-addresses` và auto-delete policy.
- [Apache ActiveMQ Artemis — Docker](https://artemis.apache.org/components/artemis/documentation/latest/docker.html): image broker dùng trong ví dụ.
- [Spring Guide — Messaging with JMS](https://spring.io/guides/gs/messaging-jms/): `JmsTemplate`, `@JmsListener` và cấu hình Spring JMS.

**Điều cần ghi nhớ:** `DynamicDestinationResolver` chuyển **String → JMS Destination object**, còn **broker + chính sách vận hành** quyết định **destination vật lý có tồn tại, được tạo thế nào, có quyền gì, giữ message bao lâu và được xóa khi nào**. Hai trách nhiệm đó phải được thiết kế và kiểm chứng độc lập.
