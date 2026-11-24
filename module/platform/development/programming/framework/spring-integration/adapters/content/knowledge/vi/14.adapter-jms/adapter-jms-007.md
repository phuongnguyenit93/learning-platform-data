# Destination queue, topic và destination name trong JMS

## 1. Bài toán: gửi đúng nơi, nhận đúng cách

Giả sử một nền tảng bán hàng phát ra hai loại thông điệp:

- Lệnh `ReserveInventory` yêu cầu **một** worker kho giữ hàng cho đơn `ORD-701`.
- Sự kiện `OrderPaid` cần đến **nhiều** dịch vụ độc lập: kho, kế toán và phân tích dữ liệu.

Nếu đưa cả hai vào một destination và sử dụng cùng cách nhận, kết quả dễ sai: lệnh có thể được xử lý nhiều lần, hoặc một số dịch vụ không nhận được bản sao sự kiện cần thiết. **JMS Destination** là địa chỉ logic nhận/gửi message, nhưng **Queue** và **Topic** có hợp đồng phân phối rất khác nhau.

Trong module **SPRING_INTEGRATION_ADAPTERS**, Spring Integration kết nối hệ thống ngoài qua inbound/outbound adapter, gateway, poller và `MessageChannel`. Với JMS, chọn đúng destination là bước đầu để giữ đúng hợp đồng message, xử lý lỗi, retry và vòng đời kết nối. Bài học này tập trung vào **Destination queue, topic và destination name**: ý nghĩa, cách Spring JMS phân giải tên, cách cấu hình adapter/gateway, cách dùng subscription và cách kiểm chứng hoạt động với broker.

**Sau bài học, bạn có thể:**

1. Giải thích khác nhau giữa `jakarta.jms.Destination`, `Queue`, `Topic` và chuỗi `destinationName`.
2. Chọn queue cho competing consumers hoặc topic cho publish-subscribe.
3. Cấu hình `pubSubDomain`, `DestinationResolver` và JMS adapter bằng Java DSL/XML.
4. Thiết kế durable/shared subscription, destination tạm thời cho request-reply và đặt tên destination nhất quán.
5. Phát hiện các lỗi như queue/topic không khớp, subscription offline mất message, nhiều consumer làm thay đổi thứ tự và gửi nhầm destination.

## 2. JMS Destination là gì?

`jakarta.jms.Destination` là interface biểu diễn **đích JMS mà producer gửi tới và consumer nhận từ đó**. Hai kiểu quan trọng:

- `jakarta.jms.Queue`: mô hình **point-to-point**. Một message trên queue thường được phân phối cho một trong các consumer cạnh tranh của queue. Khi consumer rollback, broker có thể redeliver message theo policy.
- `jakarta.jms.Topic`: mô hình **publish-subscribe**. Một message được phân phối tới các subscription phù hợp; mỗi subscription độc lập có thể nhận bản sao của cùng sự kiện.

`Destination` **không phải** Spring Integration `MessageChannel`. Trong ứng dụng, `MessageChannel` vận chuyển Spring Message giữa endpoint và handler; `Destination` thuộc broker/provider và vận chuyển JMS Message bên ngoài JVM.

~~~mermaid
flowchart LR
    A["Service tạo Spring Message"] --> B["Spring Integration outbound adapter"]
    B -->|"JmsTemplate / JMS send"| C{"Destination"}
    C --> D[("Queue: inventory.commands")]
    C --> E[("Topic: orders.events")]
    D --> F["Một consumer trong nhóm worker kho"]
    E --> G["Kho: subscription"]
    E --> H["Kế toán: subscription"]
    E --> I["Analytics: subscription"]
~~~

Đường từ node `Destination` sang Queue hoặc Topic trên sơ đồ minh họa **hai phương án cấu hình cho hai nghiệp vụ**, không có nghĩa một JMS send sẽ tự gửi tới cả hai loại destination. Muốn phát cả lệnh và sự kiện, ứng dụng phải phát các message tương ứng.

### Thuật ngữ dễ nhầm

| Thuật ngữ | Ý nghĩa | Ví dụ |
|---|---|---|
| `Destination` | Đối tượng JMS đích gửi/nhận | Một `Queue` hoặc `Topic` |
| `destinationName` / `destination-name` | **Chuỗi tên** để Spring/JMS resolver tìm đối tượng `Destination` | `inventory.commands` |
| `DestinationResolver` | Chiến lược chuyển tên thành `Destination` | `DynamicDestinationResolver`, `JndiDestinationResolver` |
| `pubSubDomain` | Cờ chọn **topic** khi phân giải destination theo tên; `false` thường là queue | `true` khi publish tới topic |
| Subscription | Quan hệ một subscriber với một topic, có thể durable/shared | `accounting-service-v1` |
| `JMSReplyTo` | Một JMS `Destination` mà bên nhận request phải trả reply tới | Temporary queue hoặc reply queue cố định |
| `MessageChannel` | Abstraction nội bộ của Spring Integration | `ordersInput`, `commandsOutput` |

Điều cốt lõi: **tên destination chỉ là một chuỗi**, còn cách broker/provider hiểu chuỗi ấy phụ thuộc **loại destination, resolver, cấu hình broker và quyền truy cập**.

## 3. Queue: giao một công việc cho một consumer

Queue thường được dùng khi message mô tả một **công việc cần thực thi một lần về mặt nghiệp vụ**: nhập đơn, giữ hàng, xử lý thanh toán, tạo phiếu vận chuyển. Nhiều worker cùng lắng nghe một queue là **competing consumers**.

~~~mermaid
flowchart LR
    P["Order Service"] --> Q[("Queue: inventory.commands")]
    Q --> W1["Warehouse Worker 1"]
    Q --> W2["Warehouse Worker 2"]
    Q --> W3["Warehouse Worker 3"]
    W1 --> DB[("Kho")]
    W2 --> DB
    W3 --> DB
~~~

Sơ đồ thể hiện **nhiều consumer có thể nhận các message khác nhau từ cùng queue**. Một message cụ thể thường được giao cho **một** consumer tại một thời điểm xử lý, nhưng nếu consumer/transaction lỗi, message có thể được giao lại cho consumer khác. JMS không tự đảm bảo handler chỉ tạo tác động nghiệp vụ đúng một lần.

### Các đặc điểm quan trọng của Queue

1. **Phân phối công việc:** một queue có thể có nhiều consumer; broker quyết định consumer nhận từng message.
2. **Tồn đọng:** message có thể chờ trong queue khi chưa có consumer; khả năng lưu giữ phụ thuộc persistence, expiry, quota và broker policy.
3. **Redelivery:** nếu session transacted bị rollback hoặc consumer thất bại ở thời điểm phù hợp, broker có thể gửi lại message; thường có chính sách retry và dead-letter queue (DLQ).
4. **Thứ tự:** không mặc định nhiều consumer sẽ hoàn thành công việc đúng thứ tự gửi. Nếu thứ tự theo `orderId` là bắt buộc, hãy dùng chiến lược serialization, grouping hoặc partition theo khả năng của broker.
5. **Idempotency:** consumer phải nhận diện cùng `eventId`/`commandId` khi retry, producer gửi lại hoặc message được redeliver.

Ví dụ: ứng dụng gửi ba lệnh liên tiếp cho cùng `ORD-701` là `CREATE`, `UPDATE` và `CANCEL`. Với ba consumer song song, `CANCEL` có thể được xử lý trước `UPDATE` dù broker giao theo thứ tự nhất định. Contract nên quy định version/trạng thái hoặc cách phân nhóm lệnh theo khóa nghiệp vụ.

### Khi nào Queue không phù hợp?

Nếu một message `OrderPaid` phải tới **cả kho lẫn kế toán**, hai consumer cùng đọc **một queue** sẽ cạnh tranh nhận các message. Mỗi message không tự nhân bản cho từng dịch vụ. Cách đúng thường là **topic với hai subscription riêng**, hoặc producer/router phát hai bản vào hai queue nghiệp vụ khác nhau nếu cần tách tuyệt đối.

## 4. Topic: phát cùng sự kiện cho nhiều subscription

Topic dùng cho **publish-subscribe**. Producer publish một event; broker phân phối event cho những subscription phù hợp.

~~~mermaid
flowchart LR
    P["Order Service"] --> T[("Topic: orders.events")]
    T --> S1["Subscription kho"]
    T --> S2["Subscription kế toán"]
    T --> S3["Subscription analytics"]
    S1 --> W["Warehouse"]
    S2 --> A["Accounting"]
    S3 --> X["Analytics"]
~~~

Ở đây, kho và kế toán **không cạnh tranh trên một subscription**: mỗi subscription nhận luồng event riêng. Hai subscription có thể xử lý cùng `evt-701` độc lập. Tuy nhiên **hai consumer cùng dùng chung một shared subscription** sẽ chia nhau message của subscription đó, gần giống cách scale worker trên queue. Đây là khác biệt giữa **số subscription** và **số consumer trong một subscription**.

### Non-durable và durable subscription

| Kiểu subscription | Khi subscriber online | Khi subscriber offline | Sử dụng |
|---|---|---|---|
| **Non-durable** | Nhận message được publish trong thời gian subscription hoạt động | Thường bỏ lỡ message được phát khi subscriber không hoạt động | Live dashboard, thông báo không bắt buộc lưu |
| **Durable (unshared)** | Nhận message theo subscription bền vững | Broker có thể giữ các message đủ điều kiện cho subscription đến khi subscriber quay lại, theo expiry/quota/retention | Kế toán, đối soát sự kiện quan trọng |
| **Shared subscription** | Nhiều consumer cùng chia việc xử lý của một subscription | Offline behavior phụ thuộc shared non-durable/durable | Scale subscriber của một ứng dụng |
| **Shared durable** | Nhiều consumer chia cùng durable subscription | Có thể giữ message khi không có consumer, theo cấu hình và policy | Dịch vụ cần cả fan-out giữa hệ thống lẫn scale bên trong hệ thống |

Durable subscription **không** tự đồng nghĩa với lưu giữ vô hạn: message còn có `timeToLive`/expiry, broker quota, security policy và thiết lập retention. Cần giám sát backlog cho từng durable subscription.

Với unshared durable subscription, client ID và subscription name thường tham gia định danh subscription. Với shared subscription/durable JMS 2.0+, quy tắc định danh và concurrency thay đổi; phải kiểm tra JMS provider và lựa chọn cấu hình Spring listener container tương ứng. Không để nhiều instance vô tình đăng ký các durable subscription riêng khác nhau nếu mục tiêu chỉ là cùng nhau xử lý một bản của mỗi event.

### Một topic cho ba dịch vụ

Giả sử publish:

~~~json
{
  "eventId": "evt-701",
  "schemaVersion": 1,
  "eventType": "OrderPaid",
  "orderId": "ORD-701",
  "paidAmount": 480000
}
~~~

Nếu có ba subscription độc lập của kho, kế toán và analytics, broker có thể phân phối ba bản logic cho ba subscription. Mỗi dịch vụ **tự quyết định retry, ack, xử lý lỗi và deduplication** của mình; sự thành công của subscription kho không chứng minh kế toán đã xử lý xong.

## 5. Queue và Topic: bảng chọn nhanh

| Tiêu chí | Queue | Topic |
|---|---|---|
| Mục đích | Giao một công việc cho một thành viên của nhóm worker | Phát sự kiện cho một hoặc nhiều subscription độc lập |
| Mối quan hệ giữa nhiều consumer | Competing consumers trên queue | Mỗi subscription nhận luồng riêng; nhiều consumer có thể cùng chia một shared subscription |
| Nhận khi offline | Message đủ điều kiện có thể chờ trong queue | Non-durable thường mất sự kiện lúc offline; durable có thể giữ theo policy |
| Retry và DLQ | Thường đặt theo queue/consumer/broker policy | Đặt theo subscription/provider; có thể phân tách retry giữa các dịch vụ |
| Ordering | Phụ thuộc broker, concurrency, grouping | Phụ thuộc subscription, concurrency, partition/grouping |
| Ví dụ | `inventory.commands`, `invoice.jobs` | `orders.events`, `catalog.events` |
| Khi chọn | Chỉ một worker thực thi một command | Nhiều hệ thống cần nhận bản sao event |

Không quyết định queue/topic chỉ bằng tên `.commands` hoặc `.events`; **hợp đồng phân phối** mới là tiêu chí chính. Trong một hệ thống lớn, có thể nhận sự kiện qua topic, sau đó mỗi service chuyển công việc của mình tới queue nội bộ để xử lý theo worker pool.

## 6. `destinationName` khác gì đối tượng `Destination`?

Một JMS adapter có thể được cung cấp:

1. **Đối tượng `jakarta.jms.Destination`** đã tồn tại, chẳng hạn bean `Queue`/`Topic` do JNDI hoặc JMS provider tạo; hoặc
2. **Chuỗi tên** `destinationName`, chẳng hạn `orders.events`, để Spring phân giải khi kết nối/sử dụng.

Ví dụ Java với `JmsTemplate`:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.jms.core.JmsTemplate;

JmsTemplate queueTemplate = new JmsTemplate(connectionFactory);
queueTemplate.setPubSubDomain(false); // Tên string được phân giải thành queue.
queueTemplate.convertAndSend("inventory.commands",
        "{\"commandId\":\"cmd-701\",\"orderId\":\"ORD-701\"}");

JmsTemplate topicTemplate = new JmsTemplate(connectionFactory);
topicTemplate.setPubSubDomain(true); // Tên string được phân giải thành topic.
topicTemplate.convertAndSend("orders.events",
        "{\"eventId\":\"evt-701\",\"eventType\":\"OrderPaid\"}");
~~~

Đây là đoạn minh họa trong một method có biến `connectionFactory` đã cấu hình; không phải một ứng dụng Java chạy độc lập. Hai template khác nhau giúp thể hiện rõ **domain queue** và **domain topic**. `setPubSubDomain(true)` tác động đến cách resolver tạo/tra destination **theo tên**; với một `Destination` cụ thể, kiểu đối tượng `Queue` hoặc `Topic` đã thể hiện domain của nó.

### 6.1. `DynamicDestinationResolver`

`JmsTemplate` mặc định dùng `DynamicDestinationResolver`. Khi gọi:

~~~java
topicTemplate.convertAndSend("orders.events", payload);
~~~

Spring yêu cầu resolver ánh xạ chuỗi `orders.events` tới JMS `Destination` thích hợp. Với cấu hình `pubSubDomain=true`, resolver dùng hướng topic; với `false` dùng hướng queue.

**Tên chuỗi không bảo đảm broker tự tạo vật lý một queue/topic.** Provider có thể auto-create khi được phép, hoặc yêu cầu destination được provision trước. `DynamicDestinationResolver` làm công việc **phân giải destination**, còn việc tạo vật lý và ACL là hành vi/bảo mật của provider/broker.

Một lỗi thường thấy: producer và consumer đều dùng chuỗi `orders.events`, nhưng producer gửi tới **queue** trong khi consumer subscribe **topic**. Hai bên không gặp nhau dù tên giống hệt.

### 6.2. `JndiDestinationResolver` và destination do quản trị viên cấp

Trong một số môi trường doanh nghiệp, destination được quản trị qua JNDI hoặc application server. Khi đó ứng dụng có thể chọn `JndiDestinationResolver` để tra cứu tên logic thành `Destination` đã đăng ký:

~~~java
import org.springframework.jms.support.destination.JndiDestinationResolver;

JndiDestinationResolver resolver = new JndiDestinationResolver();
resolver.setCache(true);

JmsTemplate jmsTemplate = new JmsTemplate(connectionFactory);
jmsTemplate.setDestinationResolver(resolver);
jmsTemplate.convertAndSend("jms/OrderEvents", jsonBody);
~~~

Ví dụ giả định JNDI context đã có binding `jms/OrderEvents` và `jsonBody` là JSON `String`. `JndiDestinationResolver` có thể cấu hình fallback sang dynamic resolution khi lookup thất bại; trong môi trường quản lý destination nghiêm ngặt, cần cân nhắc **tắt fallback** để lỗi JNDI không vô tình dẫn đến gửi vào destination tên khác.

Không lấy `jms/OrderEvents` làm tên vật lý broker trừ khi admin/provider nói rõ. **Tên JNDI** và **physical broker address** có thể là hai giá trị khác nhau.

### 6.3. Bean Destination và tên string: nên dùng khi nào?

| Cách tham chiếu | Ví dụ | Ưu điểm | Điểm cần kiểm tra |
|---|---|---|---|
| String destination name | `"orders.events"` | Gọn, dễ cấu hình theo môi trường | Resolver, queue/topic domain, auto-create, ACL |
| `Destination` object | Bean `Topic` do provider/JNDI cung cấp | Loại destination rõ, không cần phân giải chuỗi ở chỗ gọi | Lifecycle bean, quyền truy cập, broker mapping |
| JNDI logical name | `"jms/OrderEvents"` | Quản trị tách biệt app và broker | Naming context, fallback, cache lookup |
| Dynamic destination từ message | `headers['targetDestination']` | Routing linh hoạt | Allowlist, validate, observability, quyền gửi |

## 7. Cấu hình queue/topic trong Spring Integration Java DSL

Ví dụ sử dụng Spring Integration 6+ và `jakarta.jms.ConnectionFactory`. Dự án cần `spring-integration-jms` cùng JMS client của provider và một broker/queue/topic tương ứng. Các đoạn Java dưới đây minh họa **các flow độc lập**, có thể tách thành nhiều bean trong ứng dụng Spring.

### 7.1. Gửi command vào Queue bằng outbound adapter

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.dsl.Jms;

@Configuration
@EnableIntegration
public class InventoryCommandFlows {

    @Bean
    public IntegrationFlow inventoryCommandOutbound(
            ConnectionFactory connectionFactory) {
        return IntegrationFlow.from("inventoryCommandOutput")
                .handle(Jms.outboundAdapter(connectionFactory)
                        .destination("inventory.commands"))
                .get();
    }
}
~~~

Trong cấu hình này, `Jms.outboundAdapter(connectionFactory)` dùng `JmsTemplate` với cách phân giải tên thông thường (queue theo mặc định) khi chưa tùy chỉnh. Gửi Spring Message chứa JSON `String` đến `inventoryCommandOutput` sẽ kích hoạt outbound adapter, chuyển thành JMS `TextMessage` và đưa vào queue `inventory.commands`.

Nếu ứng dụng có `ConnectionFactory` do Spring Boot auto-configure, có thể inject bean đó. Ví dụ không tự tạo broker hoặc destination và không chờ reply; nếu cần kết quả từ hệ thống kho, dùng JMS outbound gateway.

### 7.2. Publish event lên Topic qua JmsTemplate cấu hình rõ domain

Để bảo đảm topic domain khi truyền tên string, cấu hình một `JmsTemplate` dành cho topic rồi đưa nó cho JMS outbound adapter:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.dsl.Jms;
import org.springframework.jms.core.JmsTemplate;

@Bean("orderEventsTopicTemplate")
public JmsTemplate orderEventsTopicTemplate(ConnectionFactory connectionFactory) {
    JmsTemplate template = new JmsTemplate(connectionFactory);
    template.setPubSubDomain(true);
    return template;
}

@Bean
public IntegrationFlow orderEventTopicOutbound(
        @org.springframework.beans.factory.annotation.Qualifier("orderEventsTopicTemplate")
        JmsTemplate topicTemplate) {
    return IntegrationFlow.from("orderEventsOutput")
            .handle(Jms.outboundAdapter(topicTemplate)
                    .destination("orders.events"))
            .get();
}
~~~

Đây là các bean/method cần đặt trong class có `@Configuration` và `@EnableIntegration` (hoặc cấu hình Spring Integration tương đương). Nếu producer gửi `String`, converter mặc định thông dụng tạo JMS `TextMessage`. Cấu hình này chỉ publish tới **topic `orders.events`**; các subscription do **bên nhận** tạo/quản lý.

Vì `JmsTemplate` thường là singleton, **không** gọi `setPubSubDomain(true/false)` luân phiên trong lúc nhiều thread cùng gửi. Dùng các template/adapter được cấu hình cố định, hoặc route qua các endpoint riêng.

### 7.3. Nhận command từ Queue bằng message-driven adapter

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.dsl.Jms;

@Bean
public IntegrationFlow inventoryCommandInbound(
        ConnectionFactory connectionFactory) {
    return IntegrationFlow
            .from(Jms.messageDrivenChannelAdapter(connectionFactory)
                    .destination("inventory.commands"))
            .handle(String.class, (commandJson, headers) -> {
                // Xử lý đồng bộ, validate commandId và idempotency trong service thật.
                System.out.println("Inventory command: " + commandJson);
                return null;
            })
            .get();
}
~~~

Listener container được adapter tạo ra sẽ nhận khi broker có message; **không thêm poller**. Queue và competing consumers vẫn tuân theo broker policy. Trong production, handler cần có chiến lược transaction, redelivery và idempotency.

### 7.4. Nhận từ Topic với durable subscription

Với subscriber cần nhận sự kiện ngay cả khi tạm offline, hãy cấu hình listener container cho topic và subscription identity rồi đưa container vào adapter.

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.dsl.Jms;
import org.springframework.jms.listener.DefaultMessageListenerContainer;

@Bean
public DefaultMessageListenerContainer accountingTopicListener(
        ConnectionFactory connectionFactory) {
    DefaultMessageListenerContainer container =
            new DefaultMessageListenerContainer();
    container.setConnectionFactory(connectionFactory);
    container.setDestinationName("orders.events");
    container.setPubSubDomain(true);
    container.setSubscriptionDurable(true);
    container.setSubscriptionName("accounting-service");
    container.setClientId("accounting-client-01");
    container.setSessionTransacted(true);
    // Container chưa có listener: adapter Spring Integration sẽ đăng ký listener.
    return container;
}

@Bean
public IntegrationFlow accountingOrderEvents(
        DefaultMessageListenerContainer accountingTopicListener) {
    return IntegrationFlow
            .from(Jms.messageDrivenChannelAdapter(accountingTopicListener))
            .handle(String.class, (json, headers) -> {
                System.out.println("Accounting received: " + json);
                return null;
            })
            .get();
}
~~~

Lưu ý: đoạn code minh họa cách gắn subscription với listener. Để dùng trên production, hãy kiểm tra phiên bản Spring Integration/JMS provider, bean lifecycle, điều kiện đăng ký listener và client ID duy nhất theo broker. **Một unshared durable subscription không thể tùy ý dùng cùng identity với nhiều active consumer**; nếu muốn chia tải trong cùng subscription, cấu hình **shared durable subscription** đúng theo khả năng broker và API của container.

Khi tạo container như một bean riêng, Spring có thể quản lý start/stop của container; việc lifecycle phối hợp với endpoint cần được kiểm thử. Nên cấu hình listener container theo một cơ chế quản lý thống nhất để tránh khởi động sớm trước khi adapter đăng ký listener.

## 8. Ví dụ XML namespace: destination-name và pub-sub-domain

Trong cấu hình XML của Spring Integration, nhiều JMS adapter/gateway hỗ trợ chỉ định:

- `destination`: tham chiếu đến một bean `Destination`.
- `destination-name`: chuỗi tên sẽ được resolver phân giải.
- `pub-sub-domain`: chọn topic thay vì queue khi thích hợp.

### Queue inbound và outbound

~~~xml
<int:channel id="inventoryCommands"/>

<int-jms:message-driven-channel-adapter
        id="inventoryCommandsInbound"
        connection-factory="jmsConnectionFactory"
        destination-name="inventory.commands"
        channel="inventoryCommands"/>

<int-jms:outbound-channel-adapter
        id="inventoryCommandsOutbound"
        connection-factory="jmsConnectionFactory"
        destination-name="inventory.commands"
        channel="inventoryCommandOutput"/>
~~~

Đây là các đoạn fragment XML; cần namespace `int`, `int-jms`, bean `jmsConnectionFactory` và channel/handler đầy đủ. Nếu cùng ứng dụng vừa phát vừa nhận từ `inventory.commands` thì hai endpoint có thể hoạt động; nhưng khi kiểm thử cần tách vai trò hoặc kiểm soát luồng để không vô tình tạo vòng gửi lại vô hạn.

### Topic message-driven inbound với durable subscription

~~~xml
<int:channel id="accountingEvents"/>

<int-jms:message-driven-channel-adapter
        id="accountingTopicInbound"
        connection-factory="jmsConnectionFactory"
        destination-name="orders.events"
        pub-sub-domain="true"
        subscription-durable="true"
        subscription-name="accounting-service"
        channel="accountingEvents"/>
~~~

Với durable non-shared subscription, cấu hình **client ID** phù hợp qua listener container/connection factory và kiểm tra quy tắc của broker. Không chọn cùng một durable subscription identity cho hai dịch vụ độc lập nếu cả hai cần nhận **mỗi bên một bản sao**; phải đặt subscription name/client ID riêng.

Khi triển khai theo XML, bean `accountingEvents` phải có consumer như service activator hoặc flow nhận. Cấu hình subscription phải phù hợp JMS provider, phiên bản Spring Integration và lifecycle deployment.

### So sánh với JMS-backed Spring Integration channel

Spring Integration còn có **JMS-backed channel**, là một thành phần khác với inbound/outbound channel adapter: `<int-jms:channel>` dùng queue, còn `<int-jms:publish-subscribe-channel>` dùng topic. Khi cần message đi qua JMS ngay giữa các Spring integration endpoints, hai loại channel này cũng có thể phù hợp.

~~~xml
<int-jms:channel
        id="jmsWorkQueueChannel"
        connection-factory="jmsConnectionFactory"
        queue-name="inventory.commands"/>

<int-jms:publish-subscribe-channel
        id="jmsEventTopicChannel"
        connection-factory="jmsConnectionFactory"
        topic-name="orders.events"/>
~~~

Không nhầm `queue-name`/`topic-name` trên **JMS-backed channel** với `destination-name` trên **adapter**: đây là các phần tử cấu hình khác nhau dù cùng trỏ tới broker destination. Cần quyết định bạn muốn **endpoint nối Spring MessageChannel ra broker** hay muốn **MessageChannel tự có JMS-backed semantics**.

## 9. Destination động: linh hoạt nhưng phải giới hạn

Một vài ứng dụng cần gửi command theo loại nghiệp vụ:

~~~text
inventory.reserve  -> queue inventory.reserve.commands
inventory.release  -> queue inventory.release.commands
~~~

Spring Integration outbound adapter có thể chọn destination bằng expression thay vì chỉ định tên cố định. Ví dụ:

~~~java
IntegrationFlow.from("inventoryRoutedCommands")
        .handle(Jms.outboundAdapter(connectionFactory)
                .destinationExpression("headers['targetQueue']"))
        .get();
~~~

Đây là fragment flow; `targetQueue` phải là header **đã được server xác minh**. Không cho phép client API tùy ý truyền chuỗi destination chưa được kiểm soát vì điều đó có thể dẫn tới gửi vào queue nội bộ, phát tán dữ liệu hoặc phát sinh destination ngoài ý muốn.

### Dùng allowlist thay vì ghép tên tự do

Ví dụ một bước chuẩn hóa header khi có `commandType`:

~~~java
.enrichHeaders(headers -> headers.headerFunction(
        "targetQueue",
        message -> {
            String type = (String) message.getHeaders().get("commandType");
            return switch (type) {
                case "RESERVE" -> "inventory.reserve.commands";
                case "RELEASE" -> "inventory.release.commands";
                default -> throw new IllegalArgumentException(
                        "Unsupported commandType: " + type);
            };
        }))
.handle(Jms.outboundAdapter(connectionFactory)
        .destinationExpression("headers['targetQueue']"))
~~~

Đây là **đoạn ghép vào một IntegrationFlow**, không có phần `IntegrationFlow.from(...)` đầy đủ. Ứng dụng cần kiểm tra `commandType` khác `null`, giới hạn số lượng/độ dài header và xử lý exception. Danh sách destination nên được đưa vào cấu hình môi trường có quyền quản lý, không tự ghép `"inventory." + userInput`.

**Lưu ý về queue/topic động:** nếu cần chọn giữa **queue** và **topic** theo từng message, nên **route qua hai outbound endpoint** với template/domain được cấu hình tương ứng, hoặc trả về `Destination` object đã được cho phép. Không nên đổi `pubSubDomain` của một `JmsTemplate` singleton giữa các lần gửi.

## 10. Naming convention: đặt tên để vận hành được

JMS **không bắt buộc** một quy tắc đặt tên queue/topic chung cho mọi broker. Nhưng tên nhất quán giúp production xác định đúng chức năng, quyền truy cập, ownership và alert.

Một convention minh họa:

~~~text
inventory.reserve.commands
inventory.release.commands
orders.events
payments.events
orders.status.requests
orders.status.replies
orders.events.dlq
~~~

| Thành phần của tên | Ý nghĩa | Ví dụ |
|---|---|---|
| Domain | Ngữ cảnh nghiệp vụ | `orders`, `inventory` |
| Action/aggregate | Chủ thể hoặc thao tác | `reserve`, `status` |
| Loại thông điệp | Phân biệt commands, requests, events, replies | `.commands`, `.events` |
| Hậu tố vận hành khi cần | DLQ, retry, version | `.dlq`, `.retry`, `.v2` |

Không mặc định đặt tên dài hơn là tốt hơn; chọn convention phù hợp công cụ broker và chính sách vận hành. Broker có thể dùng **address** và **queue** riêng biệt (ví dụ một số JMS provider ánh xạ JMS topic/queue lên address model), vì vậy hãy tài liệu hóa cả **tên JMS nhìn từ ứng dụng** và **tên tài nguyên vật lý** trong môi trường.

### Tách cấu hình theo môi trường

Không hard-code URL broker, thông tin xác thực hay địa chỉ nhạy cảm trong bài hoặc ứng dụng. Đặt tên destination trong configuration và cấu hình quyền gửi/nhận tương ứng. Ví dụ:

~~~yaml
app:
  messaging:
    inventory-commands: inventory.reserve.commands
    order-events: orders.events
~~~

Đây là **ví dụ cấu hình ứng dụng** chứ không phải YAML metadata của bài học. Có thể dùng `@ConfigurationProperties` để bind tên đích vào một class cấu hình rồi truyền vào flow. Khi triển khai nhiều môi trường, tên vật lý có thể được map từ những logical key khác nhau, nhưng contract phải nhất quán.

## 11. Message selectors, TTL và subscription có ảnh hưởng gì?

### 11.1. Selector không biến một queue thành topic

JMS **message selector** lọc message theo các JMS properties, ví dụ:

~~~text
eventType = 'OrderPaid' AND region = 'VN'
~~~

Một listener chỉ nhận các message có properties khớp điều kiện. Trong **queue**, hai consumer có selectors khác nhau vẫn đọc cùng queue theo quy tắc phân phối của broker; selector không tạo hai bản sao cho mỗi consumer. Trong **topic**, mỗi subscription với selector riêng có thể nhận các event phù hợp.

Đừng dùng selector trên payload JSON trực tiếp: JMS selectors vận hành trên **headers/properties** được broker hỗ trợ, không tự parse chuỗi JSON để lọc. Producer phải đặt các JMS properties hợp lệ như `eventType` và `region` nếu selector dựa trên chúng.

### 11.2. TTL và độ bền

- **Persistent delivery** yêu cầu JMS provider áp dụng cam kết lưu bền phù hợp; độ bền còn phụ thuộc cấu hình broker.
- **Time-to-live** giới hạn thời gian hợp lệ của message. Khi hết hạn, broker có thể loại bỏ hoặc chuyển theo expiry policy.
- **Durable topic subscription** giữ message đủ điều kiện khi subscriber offline, **nhưng TTL và quota vẫn áp dụng**.
- **DLQ** là một destination/chiến lược xử lý lỗi của broker; JMS specification không mặc định mọi message sau lỗi sẽ vào một queue tên `.dlq`.

Ví dụ: sự kiện `OrderPaid` phải được xử lý ngay cả khi hệ thống kế toán dừng 4 giờ. Nếu producer đặt TTL 60 giây, subscription durable vẫn có thể không nhận được sự kiện sau 4 giờ. Cần thống nhất TTL, broker retention, năng lực backlog và SLA của consumer trước khi tuyên bố "không mất event".

### 11.3. Thứ tự và idempotency

Thêm consumer vào queue hoặc dùng shared topic subscription có thể tăng throughput nhưng phá vỡ giả định xử lý theo thứ tự. Một event có thể xuất hiện lại sau redelivery, hoặc producer gửi lại sau kết quả gửi không chắc chắn.

Hợp đồng JSON nên có khóa như:

~~~json
{
  "eventId": "evt-701",
  "aggregateId": "ORD-701",
  "aggregateVersion": 3,
  "eventType": "OrderPaid",
  "schemaVersion": 1
}
~~~

Consumer dùng `eventId` để deduplicate và `aggregateVersion` để kiểm tra thứ tự hợp lệ nếu nghiệp vụ cần. Cơ sở dữ liệu có unique constraint hoặc inbox table phù hợp giúp giảm tác động lặp. `JMSMessageID` chỉ định danh một lần gửi JMS, không thay thế hoàn toàn ID sự kiện ổn định.

## 12. Request-reply: destination yêu cầu và destination phản hồi

JMS gateway dùng **ít nhất hai hướng destination**:

~~~mermaid
sequenceDiagram
    participant Client as Spring Integration outbound gateway
    participant Broker as Broker
    participant Server as JMS inbound gateway / consumer
    Client->>Broker: Request -> orders.status.requests
    Note over Client,Broker: Request JMSReplyTo = temporary/fixed reply queue
    Broker->>Server: Nhận request
    Server->>Broker: Reply -> JMSReplyTo
    Broker-->>Client: Nhận reply qua correlation
~~~

- **Request destination:** thường là queue để một server/consumer xử lý một request.
- **Reply destination:** `JMSReplyTo` trỏ tới temporary queue hoặc queue cố định mà client nhận reply.
- **Correlation:** reply cần `JMSCorrelationID` theo contract để client ghép với đúng request, nhất là khi dùng shared reply queue.

Đừng dùng topic như reply destination mặc định chỉ để "nhiều client đều nhận được", vì một reply phải được định tuyến đúng **request của client đó**. JMS có hỗ trợ temporary topic/kiểu subscription riêng ở một số cấu hình, nhưng việc chọn nó phải có chủ đích và được gateway/provider hỗ trợ.

Một lỗi phổ biến: client gửi request đến `orders.status.requests`, server gửi reply tới `orders.status.replies`, nhưng client thực ra chờ trên một temporary destination do outbound gateway tạo. Hai bên có thể đều log "send thành công" mà client vẫn timeout. Kiểm tra **`JMSReplyTo` thực tế trên request** và cấu hình default reply destination của server.

## 13. Khắc phục sự cố thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xác minh |
|---|---|---|
| Producer gửi không lỗi, consumer không nhận | Một bên queue, một bên topic; sai broker/address; selector không khớp | Log loại destination và tên đã resolve, xem broker console |
| Queue depth tăng liên tục | Không có consumer, consumer lỗi hoặc chậm | Kiểm tra consumer active, retry, transaction, backlog |
| Chỉ một trong hai dịch vụ nhận event | Hai dịch vụ cùng cạnh tranh trên một queue | Chuyển sang topic với subscription riêng hoặc fan-out chủ động |
| Subscriber bỏ lỡ event sau restart | Non-durable subscription hoặc TTL ngắn | Kiểm tra durable setting, identity, expiry và backlog |
| Một service nhận event nhiều lần | Redelivery hoặc nhiều durable subscription vô tình trùng chức năng | Kiểm tra subscription list, eventId và retries |
| Cùng tên nhưng không có message | Resolver/JNDI mapping trỏ sai hoặc queue/topic mismatch | Xem resolved `Destination`, `pubSubDomain` và tên broker vật lý |
| Tạo destination bị từ chối | Broker không auto-create hoặc thiếu ACL | Provision destination, cấp quyền phù hợp |
| Hai instance tranh nhau durable subscription | Dùng cùng unshared durable identity | Cấu hình shared durable đúng phiên bản/provider hoặc tách identity |
| Reply gateway timeout | Sai `JMSReplyTo`, correlation, reply queue không tồn tại | Inspect request/reply headers, listener và destination |
| Đổi tên gây mất đường nhận | Producer/consumer triển khai khác version | Dùng migration plan, dual-publish có kiểm soát, theo dõi backlog |

**Quan sát cần có ở production:** số message gửi/nhận, queue depth, tuổi message cũ nhất, số consumer/subscription đang hoạt động, durable backlog, expiry count, redelivery/DLQ count, số lỗi resolve destination, số lần reconnect, JMS correlation và `eventId` để truy vết. Chỉ log metadata cần thiết; tránh log toàn bộ payload nhạy cảm.

## 14. Thực hành với broker

Chuẩn bị broker JMS thử nghiệm có hai đích:

- **Queue:** `inventory.commands`.
- **Topic:** `orders.events`.

Tạo hai ứng dụng subscriber (hoặc hai consumer cấu hình độc lập) để so sánh ngữ nghĩa. Nên dùng JMS broker thật hoặc test container tương thích provider; mock `JmsTemplate` không chứng minh được subscription, redelivery, selector hoặc retention.

### Bài A — Competing consumers trên Queue

1. Tạo một producer gửi 20 command có `commandId` khác nhau vào `inventory.commands`.
2. Chạy hai consumer cùng lắng nghe queue đó.
3. Ghi `commandId` và consumer đã xử lý; kiểm tra tổng số lệnh được xử lý thành công không thiếu, không có giả định mỗi consumer nhận đủ 20.
4. Cố ý cho một handler throw exception trong session transacted, quan sát redelivery và deduplication theo `commandId`.
5. Bật ba consumer, đo throughput và xem thứ tự hoàn tất có còn giống thứ tự gửi hay không.

### Bài B — Hai subscription độc lập trên Topic

1. Tạo hai subscription cho `orders.events`: `warehouse-service` và `accounting-service`.
2. Publish 10 event `OrderPaid`; kiểm tra mỗi subscription nhận đủ những event phù hợp với selector/policy.
3. Dừng subscriber kế toán rồi publish thêm 5 event.
4. Thử với **non-durable** và **durable** subscription. So sánh event nào nhận lại sau restart; kiểm tra TTL, policy broker và việc subscription đã được đăng ký trước đó.
5. Tạo hai consumer dùng cùng shared durable subscription (nếu broker hỗ trợ), xác nhận chúng chia nhau công việc của **một** subscription.

### Bài C — Cùng tên, khác loại destination

1. Producer dùng `JmsTemplate.setPubSubDomain(false)` gửi vào tên `orders.events`.
2. Consumer lại subscribe `orders.events` với `pubSubDomain=true`.
3. Xác nhận queue/topic mismatch bằng broker console/log (một số broker có tên tài nguyên vật lý chung nhưng routing type khác nhau).
4. Sửa producer thành topic template và kiểm tra subscriber nhận được.
5. Đổi sang JNDI lookup, quan sát khi logical name `jms/OrderEvents` trỏ tới topic vật lý `orders.events`.

### Bài D — Routing và bảo mật

1. Dùng header `commandType=RESERVE` hoặc `RELEASE`; map sang hai queue thuộc allowlist.
2. Thử giá trị lạ như `commandType=ADMIN`; xác nhận flow từ chối trước khi gửi.
3. Kiểm tra ACL broker để producer chỉ được publish vào hai destination hợp lệ.
4. Đo số lỗi destination resolution và gắn metric theo tên destination/loại domain.

### Bài E — Thay đổi hợp đồng và vận hành

1. Đổi tên topic trong một deployment nhưng giữ consumer cũ; quan sát missing event.
2. Tạo kế hoạch migration có giai đoạn dual-publish, kiểm tra duplicate `eventId` và decommission destination cũ sau khi backlog về 0.
3. Kiểm tra trường hợp subscriber offline lâu hơn TTL, và điều chỉnh retention theo SLA thực tế.
4. Restart broker và cả producer/consumer; xác minh connection recovery và subscription identity đúng.

### Câu hỏi tự đánh giá

1. Vì sao hai consumer cùng một queue không đảm bảo mỗi bên nhận một bản của cùng sự kiện?
2. Khác nhau giữa **hai subscription độc lập** và **hai consumer của shared subscription** là gì?
3. Nếu `destinationName="orders.events"` ở cả producer và consumer, còn cần kiểm tra điều gì?
4. `pubSubDomain=true` tác động đến cách phân giải tên string như thế nào?
5. Khi nào dùng `Destination` bean thay vì `destinationName`?
6. Durable subscription có giữ message vô thời hạn bất kể TTL không?
7. Vì sao producer/consumer cần thống nhất `JMSReplyTo` khi sử dụng JMS request-reply gateway?
8. Tại sao dynamic destination phải có allowlist?
9. Nếu message `OrderPaid` cần đến ba dịch vụ độc lập, bạn chọn Queue hay Topic và cấu hình subscription ra sao?
10. Làm thế nào để đổi tên destination mà giảm nguy cơ mất event hoặc xử lý trùng?

## 15. Tài liệu tham khảo

- [Spring Integration Reference — JMS Support](https://docs.spring.io/spring-integration/reference/jms.html): queue/topic cho inbound/outbound adapter, `destination`, `destinationName`, `pub-sub-domain`, durable/shared subscription và request-reply.
- [Spring Framework Reference — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): `DestinationResolver`, `DynamicDestinationResolver`, `JndiDestinationResolver`, JNDI và `JmsTemplate.pubSubDomain`.
- [Spring Integration API — Jms](https://docs.spring.io/spring-integration/api/org/springframework/integration/jms/dsl/Jms.html): các factory method Java DSL cho adapter/gateway và JMS-backed channel.
- [Spring Integration API — JmsOutboundChannelAdapterSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/jms/dsl/JmsOutboundChannelAdapterSpec.html): destination object, destination name, expression/function routing.
- [Spring Framework API — DefaultMessageListenerContainer](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html): listener destination, concurrency và topic subscriptions.

**Ghi nhớ:** `Destination` là đích JMS thực sự, còn `destinationName` là tên được `DestinationResolver` phân giải. **Queue** phân phối công việc cho một consumer trong nhóm, trong khi **Topic** phân phối event cho các subscription độc lập. Trong Spring Integration, cần cấu hình đúng `pubSubDomain`, subscription identity, reply destination và quyền truy cập; đồng thời thiết kế idempotency, TTL, retry và monitoring để luồng hoạt động đúng khi hệ thống chịu tải hoặc gặp sự cố.
