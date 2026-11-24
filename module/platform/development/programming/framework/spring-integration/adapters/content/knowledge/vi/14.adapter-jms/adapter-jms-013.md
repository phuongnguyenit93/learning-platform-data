# Header mapping giữa JMS và Spring Message

## 1. Tại sao payload đúng mà integration vẫn sai?

Một dịch vụ đặt hàng gửi JSON `OrderPaid` tới JMS queue `orders.paid.in`. Người nhận parse JSON thành công, nhưng không biết đây là sự kiện của tenant nào, không lọc được `eventType` qua JMS selector và không ghép được phản hồi với yêu cầu ban đầu. Lý do: thông tin cần cho **định tuyến, tương quan, ưu tiên và quan sát** có thể nằm ở **headers/properties**, không nằm trong JMS body.

Trong Spring Integration, dữ liệu di chuyển qua **Spring Message** có `payload` và `MessageHeaders`; ra ngoài JVM, JMS broker vận chuyển **JMS Message** có **body**, **JMS headers tiêu chuẩn** và **JMS properties**. Một adapter/gateway phải chuyển metadata qua hai cấu trúc mà không làm lẫn những trường điều khiển giao thức với trường nghiệp vụ.

Chủ đề **Header mapping giữa JMS và Spring Message** thuộc chương **Adapter JMS** của module **SPRING_INTEGRATION_ADAPTERS**. Module sử dụng inbound/outbound adapter, gateway, poller và `MessageChannel` để kết nối hệ thống ngoài như file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu; đồng thời chú trọng hợp đồng message, lỗi và vòng đời kết nối. Bài này giải thích **JMS header mapper**, cách cấu hình và kiểm thử trong các luồng đó, đặc biệt khi tích hợp nhiều công nghệ.

**Kết quả mong đợi:** bạn có thể phân biệt JMS API headers và JMS properties; đọc và ghi header qua `DefaultJmsHeaderMapper`; giải thích `jms_correlationId` so với `correlationId`; cấu hình Java DSL/XML; không nhầm QoS với message property; giới hạn metadata được phép đưa ra broker; và kiểm chứng header mapping bằng JMS provider thật.

## 2. Bức tranh tổng thể: hai chiều mapping

~~~mermaid
flowchart LR
    A["Producer / Spring Integration"] --> B["Spring Message"]
    B --> C["JMS outbound adapter hoặc gateway"]
    C --> D["MessageConverter: payload -> JMS body"]
    C --> E["JmsHeaderMapper: headers -> JMS metadata"]
    D --> F[("JMS broker")]
    E --> F
    F --> G["JMS inbound adapter hoặc gateway"]
    G --> H["MessageConverter: JMS body -> payload"]
    G --> I["JmsHeaderMapper: JMS metadata -> headers"]
    H --> J["Spring Message -> MessageChannel"]
    I --> J
~~~

Ba phạm vi không được trộn lẫn:

| Phạm vi | Java API thường gặp | Ví dụ | Ai xử lý? |
|---|---|---|---|
| **JMS body** | `TextMessage`, `BytesMessage`, `MapMessage` | JSON chứa `eventId`, `orderId` | `MessageConverter` |
| **JMS API headers** | `getJMSCorrelationID()`, `getJMSReplyTo()`, `getJMSMessageID()` | Correlation, reply destination, timestamp | JMS provider cùng `JmsHeaderMapper` |
| **JMS application properties** | `getStringProperty("eventType")`, `getIntProperty("schemaVersion")` | Event type, schema version, tenant key được kiểm soát | `JmsHeaderMapper` |
| **Spring MessageHeaders** | `Message.getHeaders()` | `eventType`, `jms_correlationId`, `priority` | Spring Integration, transformers, routers |

**`MessageConverter` và `JmsHeaderMapper` khác nhau:** converter chuyển dữ liệu body sang Java object hoặc ngược lại; mapper chuyển metadata. Đổi converter từ `SimpleMessageConverter` sang Jackson **không tự giải quyết** một JMS property bị mất hoặc header correlation bị gắn sai.

### Hai hướng cần nhớ

**Outbound, Spring → JMS:**

~~~text
Spring Message:
  payload     = "{\"eventId\":\"evt-1301\",\"orderId\":\"ORD-1301\"}"
  headers:
    eventType     = "OrderPaid"
    schemaVersion = 1
    traceId       = "trace-1301"

Header mapper:
  eventType       -> JMS property eventType
  schemaVersion   -> JMS property schemaVersion
  traceId         -> JMS property traceId

Converter:
  String payload  -> JMS TextMessage body
~~~

**Inbound, JMS → Spring:**

~~~text
JMS TextMessage:
  body                      = JSON String
  property eventType        = "OrderPaid"
  property schemaVersion    = 1
  property traceId          = "trace-1301"
  header JMSCorrelationID   = "corr-1301"

Header mapper:
  JMS properties            -> Spring Message headers
  JMSCorrelationID          -> Spring header jms_correlationId

Converter:
  TextMessage body          -> Spring payload String
~~~

JMS selectors hoạt động trên **JMS headers/properties được hỗ trợ**, không tự parse JSON body. Nếu consumer cần selector `eventType = 'OrderPaid'`, producer phải đặt JMS property `eventType`; chỉ có `eventType` trong JSON là chưa đủ.

## 3. Phân loại JMS metadata trước khi viết code

### 3.1. JMS API headers tiêu chuẩn

JMS message có các trường do API JMS quản lý:

| JMS API field | Mục đích | Lưu ý khi ánh xạ |
|---|---|---|
| `JMSMessageID` | ID của lần gửi JMS | Do provider gán; inbound đọc được, không tự gán để ghi đè message ID outbound |
| `JMSTimestamp` | Thời điểm gửi do provider ghi nhận | Khác `timestamp` sinh tự động của Spring Message |
| `JMSCorrelationID` | Ghép reply với request hoặc một chuỗi trao đổi | Map tới header `jms_correlationId`; khác `correlationId` |
| `JMSReplyTo` | `Destination` phía nhận request cần gửi reply tới | Header chứa đối tượng `Destination`, không chỉ là tên chuỗi |
| `JMSDestination` | Destination message được gửi tới | Thường do producer/provider xác lập; đừng xem là quyền tùy ý định tuyến |
| `JMSType` | Type label của JMS message | Có thể dùng cho contract kế thừa; không thay schema validation |
| `JMSPriority` | Priority 0–9 | JMS QoS, cần phân biệt với cách dùng Spring `priority` |
| `JMSDeliveryMode` | Persistent hoặc non-persistent | Thuộc QoS gửi, không chỉ là property tùy ý |
| `JMSExpiration` | Thời điểm hết hạn JMS message | Được provider tính từ TTL; không phải TTL dạng duration |
| `JMSRedelivered` | Thông tin khả năng được giao lại | Do provider xác định; inbound-only đối với mapper mặc định |

Trong các phiên bản Spring Framework/Spring Integration hiện đại, hằng số tên header JMS nằm trong `org.springframework.jms.support.JmsHeaders` (ví dụ `JmsHeaders.CORRELATION_ID`). Tài liệu Spring Integration cũng sử dụng tên thực tế như `jms_correlationId`. Khi viết Java, ưu tiên **hằng số được phiên bản thư viện đang dùng công bố**, thay vì ghép chuỗi `"jms_" + tên trường` thủ công.

**Đặc biệt:** `JMSMessageID` và `JMSRedelivered` được `DefaultJmsHeaderMapper` chuyển **từ JMS inbound vào Spring headers**. Không thể đặt Spring header `jms_messageId` hoặc `jms_redelivered` rồi buộc broker chấp nhận chúng như ID/flag provider cấp khi gửi outbound.

### 3.2. JMS properties do ứng dụng định nghĩa

JMS hỗ trợ các property có giá trị đơn giản: `boolean`, các kiểu số nguyên, `float`, `double` và `String` (cùng quy tắc của JMS API). Ví dụ:

~~~text
eventType      = "OrderPaid"   (String)
schemaVersion  = 1             (int)
region         = "VN"          (String)
traceId        = "trace-1301"  (String)
isReplay       = false         (boolean)
~~~

Không dùng một tùy ý `UUID`, DTO, `Map` phức tạp hoặc `MessageChannel` làm JMS property. JMS property names phải thỏa quy tắc tên/identifier của JMS, không chứa ký tự tùy ý; tránh tự đặt property trùng vùng tên hệ thống như `JMS...`/`JMSX...`. Bên nhận còn cần kiểm tra provider-specific property nào được hỗ trợ.

### 3.3. Spring headers nội bộ

Một Spring Message thường có `id` và `timestamp`. Spring Integration còn có các headers như `replyChannel`, `errorChannel`, `correlationId`, `sequenceNumber` hoặc thông tin trace nội bộ.

**Không coi mọi Spring header là một metadata contract dùng được qua JMS.** `replyChannel` có thể là đối tượng `MessageChannel`, không phải một chuỗi JMS property hợp lệ; gửi nó ra một broker cho hệ thống bên ngoài có thể gây lỗi hoặc coupling. Chỉ những metadata đã được chọn và ánh xạ hợp lệ mới được dùng làm contract liên dịch vụ.

## 4. `DefaultJmsHeaderMapper` hoạt động như thế nào?

Spring Integration cung cấp `org.springframework.integration.jms.JmsHeaderMapper` và implementation thông dụng `DefaultJmsHeaderMapper`.

- **`fromHeaders(MessageHeaders, jakarta.jms.Message)`:** ánh xạ Spring headers **sang** JMS message; những JMS API headers được hỗ trợ đi qua setter chuyên biệt, còn application headers phù hợp đi thành JMS properties.
- **`toHeaders(jakarta.jms.Message)`:** đọc JMS headers/properties và tạo một `Map<String,Object>` cho Spring Message.
- Với các custom properties, mapper có thể thêm prefix riêng khi đọc vào Spring hoặc khi ghi ra JMS.
- JMS APIs có quyền quản lý một số trường; mapper không được thay thế provider khi phát sinh `JMSMessageID`, TTL hoặc redelivery flag.

~~~mermaid
flowchart TB
    S["Spring MessageHeaders"] --> M["DefaultJmsHeaderMapper.fromHeaders"]
    M --> API["JMS API header setters, ví dụ setJMSCorrelationID"]
    M --> PROP["JMS setStringProperty / setIntProperty / ..."]
    API --> JMS["JMS Message"]
    PROP --> JMS
    JMS --> IN["DefaultJmsHeaderMapper.toHeaders"]
    IN --> OUT["Spring MessageHeaders"]
~~~

Với các metadata thông thường như `eventType`/`schemaVersion`, default mapper có thể sao chép chúng theo tên giữa Spring header và JMS property. **Không phải mọi header đều được chuyển:** một header có giá trị không biểu diễn được bằng JMS property có thể bị bỏ qua hoặc gây lỗi theo nơi xử lý; đừng xây contract phụ thuộc vào object nội bộ.

### `JmsHeaderMapper` không phải Jackson converter

Ví dụ Spring Message chứa `payload=OrderPaidEvent` và header `eventType="OrderPaid"`:

1. `MessageConverter` quyết định DTO trở thành `TextMessage` JSON, `BytesMessage` hay `ObjectMessage`.
2. `DefaultJmsHeaderMapper` quyết định metadata `eventType` có được gán lên `JMS Message` như một property hay không.
3. Broker phân phối JMS message; inbound adapter dùng converter/mapper ở chiều ngược.
4. Handler Spring nhận payload và metadata tách biệt.

Một converter tùy chỉnh cho body vẫn có thể được Spring Integration bọc bởi `HeaderMappingMessageConverter` để phối hợp với JMS header mapper. Vì vậy, thay `MessageConverter` không mặc nhiên có nghĩa bỏ mapping.

## 5. Header nào được bảo toàn và header nào có quy tắc đặc biệt?

| Spring header | JMS field tương ứng | Điều cần chú ý |
|---|---|---|
| `eventType` | Application property `eventType` | Value nên là `String` hoặc scalar được JMS cho phép |
| `schemaVersion` | Application property `schemaVersion` | Chọn kiểu `int` ổn định giữa producer/consumer |
| `traceId` | Application property `traceId` | Tránh đưa thông tin bí mật/PII vào trace |
| `jms_correlationId` | `JMSCorrelationID` | Dùng cho JMS request-reply, không thay `correlationId` |
| `jms_replyTo` | `JMSReplyTo` | Cần một đối tượng JMS `Destination` hợp lệ |
| `jms_type` | `JMSType` | Nhất quán type label với contract |
| `jms_messageId` | `JMSMessageID` | Chủ yếu inbound; provider tạo khi gửi |
| `jms_redelivered` | `JMSRedelivered` | Chủ yếu inbound; không tự đánh dấu redelivery |
| `priority` | Thông tin ưu tiên Spring | Có mapping inbound từ `JMSPriority`; outbound QoS phải cấu hình đúng |
| `jms_deliveryMode` và `jms_expiration` | `JMSDeliveryMode` và `JMSExpiration` | Inbound mapping có thể cần bật tường minh |

Một số phiên bản JMS/Spring có hằng số hoặc alias hỗ trợ nhiều tên hơn bảng trên. Hãy đối chiếu `JmsHeaders`, `DefaultJmsHeaderMapper` và broker đang dùng. Bảng này mô tả ngữ nghĩa, không phải lời hứa mọi Java header được giữ nguyên byte-for-byte khi đi qua JMS.

### `correlationId` khác `jms_correlationId`

Đây là bẫy phổ biến:

~~~text
Spring Message:
  correlationId     = UUID("...")   // Ghép message trong aggregator/resequencer
  jms_correlationId = "corr-1301"   // JMSCorrelationID cho request-reply

JMS outbound:
  property correlationId            = UUID.toString()
  JMS header JMSCorrelationID       = "corr-1301"

JMS inbound:
  Spring correlationId              = String
  Spring jms_correlationId          = String
~~~

Từ Spring Integration 4.3, `DefaultJmsHeaderMapper` hỗ trợ `correlationId` của Spring dưới dạng JMS **application property**, gọi `toString()` khi giá trị là UUID. Đây là cách khác với header `jms_correlationId`, vốn gắn trực tiếp với **`JMSCorrelationID`** của giao thức. Hai giá trị **không tự đồng bộ**; khi thiết kế request-reply, dùng đúng JMS correlation header/contract.

## 6. Cấu hình Java DSL: outbound adapter gửi metadata

Ví dụ dùng Spring Integration 6+, Spring Framework 6+, Java 17+ và JMS API `jakarta.jms`. Cần có broker JMS, driver tương ứng, bean `ConnectionFactory` và queue `orders.paid.in`.

Với Spring Boot quản lý phiên bản:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-jms</artifactId>
</dependency>
<!-- Thêm dependency cho JMS provider đã chọn và cấu hình ConnectionFactory. -->
~~~

### 6.1. Tạo mapper và outbound flow

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.DefaultJmsHeaderMapper;
import org.springframework.integration.jms.dsl.Jms;

@Configuration
@EnableIntegration
public class OrdersJmsHeaderConfiguration {

    @Bean
    public DefaultJmsHeaderMapper orderJmsHeaderMapper() {
        return new DefaultJmsHeaderMapper();
    }

    @Bean
    public IntegrationFlow orderEventsOutbound(
            ConnectionFactory connectionFactory,
            DefaultJmsHeaderMapper orderJmsHeaderMapper) {

        return IntegrationFlow.from("orderEventsOutput")
                .handle(Jms.outboundAdapter(connectionFactory)
                        .destination("orders.paid.in")
                        .headerMapper(orderJmsHeaderMapper))
                .get();
    }
}
~~~

`.headerMapper(...)` chỉ định mapper cho endpoint JMS. Adapter này là **một chiều**, gửi Spring Message ra JMS khi có message trên channel `orderEventsOutput`; nó không đợi JMS reply.

### 6.2. Producer tạo Spring Message với contract headers

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class OrderPaidPublisher {
    private final MessageChannel orderEventsOutput;

    public OrderPaidPublisher(
            @Qualifier("orderEventsOutput") MessageChannel orderEventsOutput) {
        this.orderEventsOutput = orderEventsOutput;
    }

    public void publish(String jsonBody, String eventId, String traceId) {
        Message<String> message = MessageBuilder.withPayload(jsonBody)
                .setHeader("eventType", "OrderPaid")
                .setHeader("schemaVersion", 1)
                .setHeader("eventId", eventId)
                .setHeader("traceId", traceId)
                .build();

        if (!orderEventsOutput.send(message)) {
            throw new IllegalStateException("Spring Message không được gửi");
        }
    }
}
~~~

Ví dụ dự kiến upstream đã serialize DTO thành JSON `String`; với converter mặc định, JMS outbound thường tạo `TextMessage`. `eventId` được giữ trong **JSON payload** để làm business idempotency key; đặt thêm nó trong property nhằm tracing/selector, không thay payload contract.

**Chú ý:** `MessageChannel.send(...)` trả `true` chỉ biểu thị thao tác gửi trên channel thành công theo semantics của channel/handler, không chứng minh consumer bên kia broker đã commit database. Với `DirectChannel`, lỗi đồng bộ của handler có thể truyền ra caller; với channel bất đồng bộ, cần theo dõi error channel riêng.

## 7. Java DSL: inbound adapter nhận JMS headers

Bên nhận có thể dùng **JMS message-driven inbound channel adapter** để đưa message từ broker sang `MessageChannel`. Nó dùng listener container thay vì poller của Spring Integration.

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.DefaultJmsHeaderMapper;
import org.springframework.integration.jms.dsl.Jms;

@Bean
public IntegrationFlow orderPaidInbound(
        ConnectionFactory connectionFactory,
        DefaultJmsHeaderMapper orderJmsHeaderMapper,
        OrderPaidService orderPaidService) {

    return IntegrationFlow
            .from(Jms.messageDrivenChannelAdapter(connectionFactory)
                    .destination("orders.paid.in")
                    .headerMapper(orderJmsHeaderMapper)
                    .configureListenerContainer(container ->
                            container.sessionTransacted(true)))
            .handle(String.class, (json, headers) -> {
                String eventType = (String) headers.get("eventType");
                Integer schemaVersion = (Integer) headers.get("schemaVersion");
                String traceId = (String) headers.get("traceId");

                orderPaidService.handle(json, eventType, schemaVersion, traceId);
                return null;
            })
            .get();
}
~~~

Giả sử `OrderPaidService` là interface có method:

~~~java
public interface OrderPaidService {
    void handle(String json, String eventType, Integer schemaVersion,
                String traceId);
}
~~~

Các method `@Bean` cần được đặt trong một class `@Configuration` và hệ thống đã bật Spring Integration. Khi dùng cả producer và consumer trong cùng một ứng dụng để kiểm thử, hãy phân biệt rõ hai vai trò; trong thực tế chúng thường là hai tiến trình độc lập.

Đoạn `(Integer) headers.get("schemaVersion")` dựa trên **contract producer đặt JMS `int` property**. Nếu client bên ngoài gửi `String` `"1"` thay vì `int`, cast sẽ lỗi. Với đối tác nhiều ngôn ngữ, nên validate loại header và dùng transformer chuyển đổi rõ ràng thay vì giả định mọi provider/caller giữ type giống nhau.

### Header từ listener có thể không giống JSON field

Một `TextMessage` có thể chứa `eventType` trong JSON nhưng **không có JMS property `eventType`**. Khi đó `headers.get("eventType")` có thể là `null` dù JSON chứa trường tương tự. Hãy xác định nguồn sự thật:

- **Payload** chứa hợp đồng nghiệp vụ: `eventId`, `schemaVersion`, `orderId` và kết quả xử lý.
- **JMS property** hỗ trợ lọc/định tuyến sớm: `eventType`, `region`, `tenantKey` không nhạy cảm.
- **JMS API header** hỗ trợ giao thức: `JMSCorrelationID`, `JMSReplyTo`, `JMSMessageID` và các field do provider quản lý.

Không so sánh header với payload bằng giả định chúng tự đồng bộ. Nếu cần sự thống nhất, validate chúng và đưa message bất nhất vào lỗi contract/quarantine.

### Spring Message sau khi đã mapping

~~~text
Spring Message<String>:
  payload                 = "{\"eventId\":\"evt-1301\",...}"
  headers.eventType       = "OrderPaid"
  headers.schemaVersion   = 1
  headers.traceId         = "trace-1301"
  headers.jms_messageId   = <do JMS provider cấp>
  headers.jms_redelivered = false (nếu được provider/mapping cung cấp)
~~~

JMS message ID và redelivery flag chủ yếu dùng để quan sát. Để idempotency, consumer phải lấy `eventId` ổn định từ payload và lưu unique key khi thực hiện nghiệp vụ.

## 8. Tùy biến header mapper: inbound/outbound prefix

`DefaultJmsHeaderMapper` cho phép thay đổi cách đặt tên **application properties** bằng hai setter:

- `setInboundPrefix("...")`: thêm prefix vào **tên Spring Message header** khi đọc một JMS application property vào ứng dụng.
- `setOutboundPrefix("...")`: thêm prefix vào **tên JMS property** khi ghi một Spring application header ra ngoài.

Các prefix này **không áp dụng cho các JMS API header tiêu chuẩn** như `JMSCorrelationID` hoặc `JMSReplyTo`; các header đó có tên mapping do `JmsHeaders` xác định.

### Ví dụ prefix cho một chiều

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.jms.DefaultJmsHeaderMapper;

@Bean("prefixedInboundMapper")
public DefaultJmsHeaderMapper prefixedInboundMapper() {
    DefaultJmsHeaderMapper mapper = new DefaultJmsHeaderMapper();
    mapper.setInboundPrefix("external_");
    return mapper;
}
~~~

JMS message:

~~~text
JMS property eventType = "OrderPaid"
JMS property traceId   = "trace-1301"
JMSCorrelationID       = "corr-1301"
~~~

Sau mapping:

~~~text
Spring header external_eventType = "OrderPaid"
Spring header external_traceId   = "trace-1301"
Spring header jms_correlationId  = "corr-1301"
~~~

**Không gán prefix lên `jms_correlationId`** vì đó là JMS API header. Đây là cách đánh dấu rõ các property đến từ nguồn ngoài, tránh nhầm với header nội bộ có cùng tên.

### Ví dụ outbound prefix

~~~java
DefaultJmsHeaderMapper mapper = new DefaultJmsHeaderMapper();
mapper.setOutboundPrefix("app_");
~~~

Spring `headers.eventType="OrderPaid"` khi được mapper xử lý sẽ thành JMS **application property** `app_eventType="OrderPaid"`. Nếu một consumer đặt JMS selector `eventType='OrderPaid'`, nó sẽ **không match** nữa; selector phải dùng đúng tên `app_eventType` hoặc bạn phải giữ tên property theo contract cũ.

**Prefix không phải chức năng namespace hai chiều tự đảo ngược:** nếu bên gửi thêm `app_` nhưng bên nhận cũng thêm `external_`, Spring bên nhận sẽ thấy `external_app_eventType`. Muốn có tên business header nhất quán, phải chuẩn hóa thêm bằng transformer hoặc thống nhất tên đầu vào/đầu ra.

### Không tùy tiện dùng prefix để xử lý bảo mật

Prefix chỉ đổi **tên**, không tự lọc thông tin nhạy cảm. Header `accessToken` dù được đổi thành `app_accessToken` vẫn là một property có thể bị gửi đến broker và lộ trong công cụ quản trị. Cần dùng allowlist hoặc tạo Spring Message với tập headers đã duyệt trước khi đi vào outbound adapter.

## 9. XML namespace: cấu hình `header-mapper`

Spring Integration JMS XML namespace hỗ trợ cấu hình tham chiếu header mapper cho các adapter và gateway. Ví dụ:

~~~xml
<bean id="orderJmsHeaderMapper"
      class="org.springframework.integration.jms.DefaultJmsHeaderMapper"/>

<int:channel id="orderOutbound"/>
<int:channel id="orderInbound"/>

<int-jms:outbound-channel-adapter
        id="ordersOutboundAdapter"
        connection-factory="jmsConnectionFactory"
        destination-name="orders.paid.in"
        channel="orderOutbound"
        header-mapper="orderJmsHeaderMapper"/>

<int-jms:message-driven-channel-adapter
        id="ordersInboundAdapter"
        connection-factory="jmsConnectionFactory"
        destination-name="orders.paid.in"
        channel="orderInbound"
        header-mapper="orderJmsHeaderMapper"
        acknowledge="transacted"/>
~~~

Đây là **fragment XML**, cần khai báo namespace `int` và `int-jms`, bean `jmsConnectionFactory` và consumer của `orderInbound`. Hai adapter này được đặt cạnh nhau để so sánh hai chiều, **không bắt buộc cùng ứng dụng vừa phát vừa tiêu thụ một queue**.

Với JMS inbound/outbound gateway, có thể dùng `header-mapper="orderJmsHeaderMapper"` trên phần tử `<int-jms:inbound-gateway>` hoặc `<int-jms:outbound-gateway>` tương ứng. Hãy kiểm tra version schema và cấu hình reply destination/correlation của gateway, không sao chép một cấu hình adapter một chiều rồi cho rằng gateway tự biết cách ghép reply.

### Mapper tùy biến khác với converter

~~~xml
<!-- Hai thuộc tính này có vai trò khác nhau. -->
<int-jms:message-driven-channel-adapter
        id="typedOrderInbound"
        connection-factory="jmsConnectionFactory"
        destination-name="orders.typed.in"
        channel="typedOrderChannel"
        header-mapper="orderJmsHeaderMapper"
        message-converter="orderPaidJsonConverter"/>
~~~

`orderPaidJsonConverter` là bean `org.springframework.jms.support.converter.MessageConverter` đã được cấu hình theo contract riêng (ví dụ converter Jackson JMS). Không phải `JmsHeaderMapper`; **body conversion và header mapping cần được kiểm thử riêng**.

## 10. Spring Integration khác gì với `JmsTemplate` trực tiếp?

Khi dùng `JmsTemplate.convertAndSend(...)`, bạn có thể đặt JMS properties trong `MessagePostProcessor`:

~~~java
// jmsTemplate là bean Spring JMS đã cấu hình ConnectionFactory.
jmsTemplate.convertAndSend(
        "orders.paid.in",
        "{\"eventId\":\"evt-1302\",\"orderId\":\"ORD-1302\"}",
        jmsMessage -> {
            jmsMessage.setStringProperty("eventType", "OrderPaid");
            jmsMessage.setIntProperty("schemaVersion", 1);
            jmsMessage.setJMSCorrelationID("corr-1302");
            return jmsMessage;
        });
~~~

Đây là **thao tác JMS trực tiếp qua Spring JMS**, không có Spring `MessageHeaders` hoặc `MessageChannel` để mapper tự đọc. Phần `MessagePostProcessor` tự đặt JMS metadata.

Ngược lại, khi dùng Spring Integration outbound adapter, bạn phát **Spring Message** và `DefaultJmsHeaderMapper` chuyển metadata phù hợp tới JMS message. Đừng viết cả hai lớp mapping cho cùng một header mà không xác định thứ tự/nguồn sự thật: có thể gây ghi đè hoặc làm bên nhận thấy giá trị khác với hợp đồng.

Nếu dùng `JmsTemplate.send(...)` với `MessageCreator`, bạn còn có thể gọi các setter JMS trực tiếp trên `TextMessage`/`BytesMessage`. Đó là API hợp lệ, nhưng Spring Integration mapper giúp tiêu chuẩn hóa metadata khi dữ liệu đi qua nhiều transformer, router và service activator.

### `extractPayload` không phải công tắc giữ/mất headers

Trong adapter/gateway Spring Integration, tùy chọn `extractPayload`, `extractRequestPayload` hoặc `extractReplyPayload` quyết định **đối tượng nào** được đưa cho body converter (Spring payload hay toàn Spring Message/JMS Message).

Khi giữ mặc định trích payload, Spring Integration **vẫn có thể mapping headers độc lập** bằng `HeaderMappingMessageConverter` và `JmsHeaderMapper`. Đừng đặt `extractPayload(false)` chỉ để “giữ headers”; việc này có thể đẩy **toàn Spring Message** vào JMS body và khiến phía ngoài phụ thuộc type nội bộ của Spring.

## 11. JMS request-reply: correlation và reply destination

Header mapping trong **JMS gateway** phức tạp hơn adapter một chiều vì client và server phải đồng ý **gửi reply về đâu** và **reply thuộc request nào**.

~~~mermaid
sequenceDiagram
    participant Client as Spring outbound gateway
    participant Broker as JMS broker
    participant Server as JMS inbound gateway / service
    Client->>Broker: Request tới inventory.check.requests
    Note over Client,Broker: JMSReplyTo = temporary/fixed reply destination
    Note over Client,Broker: JMSMessageID hoặc JMSCorrelationID theo contract
    Broker->>Server: Nhận request
    Server->>Broker: Reply tới JMSReplyTo
    Note over Server,Broker: JMSCorrelationID theo quy tắc đã thống nhất
    Broker-->>Client: JMS reply
    Client-->>Client: Ghép reply với Spring request đang chờ
~~~

### 11.1. Vai trò từng header

| Header | Ai thường đặt? | Vai trò |
|---|---|---|
| `JMSReplyTo` | Client/gateway trước khi gửi | Destination server phải trả JMS reply tới |
| `JMSMessageID` trên request | JMS provider khi request được gửi | Một cách định danh request JMS |
| `JMSCorrelationID` trên reply | Server theo contract | Ghép reply với request tương ứng |
| `requestId` trong JSON | Ứng dụng client | Business ID, phục vụ tracing và idempotency |
| Spring `replyChannel` | Spring Integration | Kênh **nội bộ JVM** để gateway trả Spring Message |

**Không đặt `replyChannel` thành một chuỗi JMS property rồi chờ server hiểu nó:** Spring `replyChannel` là abstraction bên trong application; `JMSReplyTo` mới là địa chỉ JMS cần gửi reply tới.

### 11.2. Correlation dùng JMSMessageID

Một hợp đồng phổ biến:

~~~text
Request:
  JMSMessageID      = ID:REQ-1301
  JMSReplyTo        = TemporaryQueue(client)

Reply:
  JMSCorrelationID  = ID:REQ-1301
  Destination       = TemporaryQueue(client)
~~~

Nếu gateway không cấu hình `correlationKey` tùy biến, Spring Integration outbound gateway thường mong server trả `JMSCorrelationID` của reply bằng `JMSMessageID` của request (theo chế độ gateway). Khi dùng fixed reply queue có nhiều request đồng thời, client có thể dùng JMS selectors/correlation để lọc reply.

### 11.3. Correlation ID do gateway đặt

Với fixed reply destination và reply listener, có thể cấu hình một key:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.dsl.Jms;

@Bean
public IntegrationFlow inventoryJmsRequestFlow(
        ConnectionFactory connectionFactory) {

    return IntegrationFlow.from("inventoryRequests")
            .handle(Jms.outboundGateway(connectionFactory)
                    .requestDestination("inventory.check.requests")
                    .replyDestination("inventory.check.replies")
                    .correlationKey("JMSCorrelationID")
                    .receiveTimeout(5000)
                    .replyContainer())
            .get();
}
~~~

Với mode này, gateway tạo correlation ID trên **`JMSCorrelationID`** của JMS request và server cần **echo đúng giá trị** lên `JMSCorrelationID` của reply. Nếu server thay vào đó đặt correlation bằng `JMSMessageID` của request, matcher của gateway có thể không tìm thấy reply, dẫn đến timeout.

**Phân biệt với Spring header `jms_correlationId`:** trong một Spring Message đã có ID hợp lệ, nó có thể map ra `JMSCorrelationID`. Nhưng outbound gateway còn có quyền điều khiển hoặc tạo correlation theo `correlationKey` và chế độ reply destination. Phải kiểm tra **JMS headers thực sự trên wire**, không chỉ log Spring headers trước gateway rồi giả định chúng được giữ nguyên.

### 11.4. Server không được phản hồi sai loại destination

`JMSReplyTo` thường chứa đối tượng `jakarta.jms.Destination` do client/gateway cung cấp; nó có thể là `TemporaryQueue`. Phía server dùng chính destination này để gửi reply, thay vì tự gửi đến một queue tên cố định bất kể request đã ghi gì.

Với gateway inbound, Spring Integration hỗ trợ xử lý `JMSReplyTo` theo giao thức. Nếu không có `JMSReplyTo`, chỉ sử dụng default reply destination khi hai phía thống nhất trước. **Không chấp nhận destination tùy ý từ nguồn không đáng tin cậy** mà chưa kiểm soát quyền send của broker.

## 12. QoS: priority, delivery mode và TTL không chỉ là JMS properties

**Đây là điểm kỹ thuật dễ sai nhất khi mapping headers.** JMS có ba thuộc tính Quality of Service (QoS) quan trọng:

- **Delivery mode:** persistent hoặc non-persistent.
- **Priority:** thường 0–9, giá trị mặc định phổ biến là 4.
- **Time-to-live (TTL):** thời gian sống của message khi gửi; JMS provider tính `JMSExpiration` từ thời điểm gửi và TTL.

Nhiều JMS provider **không cho sửa** những trường QoS bằng cách gọi setters trên một JMS Message đã được tạo. Giá trị đúng phải được truyền tới overload của `MessageProducer.send(message, deliveryMode, priority, timeToLive)` hoặc thông qua template hỗ trợ QoS.

Vì lý do đó, `DefaultJmsHeaderMapper` **không đơn giản lấy header từ Spring rồi set trực tiếp mọi QoS field lên JMS message**. Spring Integration có `DynamicJmsTemplate` để chuyển giá trị QoS từ Spring Message vào lời gọi gửi; việc truyền QoS có hiệu lực khi **`explicitQosEnabled=true`**.

### 12.1. Bật explicit QoS trong Java DSL

~~~java
@Bean
public IntegrationFlow prioritizedOrderEvents(
        ConnectionFactory connectionFactory) {

    return IntegrationFlow.from("prioritizedOrderOutput")
            .handle(Jms.outboundAdapter(connectionFactory)
                    .destination("orders.paid.in")
                    .configureJmsTemplate(template ->
                            template.explicitQosEnabled(true)
                                    .priority(4)
                                    .deliveryPersistent(true)
                                    .timeToLive(60_000)))
            .get();
}
~~~

Trong ví dụ này:

- `explicitQosEnabled(true)` cho phép template chủ động dùng các giá trị QoS.
- `priority(4)` là priority mặc định ở mức adapter/template; Spring `priority` header có thể ghi đè theo cơ chế `DynamicJmsTemplate` hỗ trợ.
- `deliveryPersistent(true)` yêu cầu persistent delivery.
- `timeToLive(60_000)` đặt TTL 60 giây. **Đừng áp dụng TTL ngắn này cho sự kiện thanh toán cần xử lý sau nhiều giờ**; đây là con số lab, không phải SLA production.

Những property QoS chỉ điều khiển gửi khi producer/provider áp dụng chúng; không chứng minh consumer đã xử lý. Ngoài ra, broker có thể áp dụng quy tắc delivery/expiry riêng.

### 12.2. Priority từ Spring header

Một Spring Message có thể đặt:

~~~java
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.support.MessageBuilder;

var springMessage = MessageBuilder.withPayload(
            "{\"eventId\":\"evt-priority-1303\"}")
        .setHeader(IntegrationMessageHeaderAccessor.PRIORITY, 8)
        .setHeader("eventType", "OrderPaid")
        .build();
~~~

Với một JMS outbound adapter có `DynamicJmsTemplate` và `explicitQosEnabled(true)`, header `priority` có thể ảnh hưởng `MessageProducer.send(...)`. Nếu không bật explicit QoS, thay `priority` trong Spring Message **không nhất thiết thay đổi JMSPriority mà broker giao**.

Đừng nhầm `priority` dùng trong Spring Integration với property JMS tùy ý `"priority"`. Giá trị thực tế cần kiểm tra bằng `JMSMessage.getJMSPriority()` ở consumer.

### 12.3. Inbound mapper cho delivery mode và expiration

Từ Spring Integration 5.1, có thể bật mapping inbound cho `JMSDeliveryMode` và `JMSExpiration`:

~~~java
@Bean("observabilityJmsHeaderMapper")
public DefaultJmsHeaderMapper observabilityJmsHeaderMapper() {
    DefaultJmsHeaderMapper mapper = new DefaultJmsHeaderMapper();
    mapper.setMapInboundDeliveryMode(true);
    mapper.setMapInboundExpiration(true);
    mapper.setMapInboundPriority(true);
    return mapper;
}
~~~

Khi bật, `JMSDeliveryMode` và `JMSExpiration` có thể xuất hiện dưới Spring headers `jms_deliveryMode` và `jms_expiration` (theo hằng số `JmsHeaders`). `JMSPriority` còn được map tới Spring `priority` từ Spring Integration 4.0; nếu muốn tắt, có `setMapInboundPriority(false)`.

### 12.4. `JMSExpiration` là timestamp, không phải TTL

JMS `JMSExpiration` biểu diễn một **mốc thời gian hết hạn**, trong khi `timeToLive` ở send là **khoảng thời gian**. Nếu muốn forward một JMS message sang queue khác mà **giữ phần thời gian sống còn lại**, có thể tính:

~~~text
remainingTtl = max(0, originalJmsExpiration - currentTimeMillis)
~~~

Nhưng phải phân biệt trường hợp `JMSExpiration=0` nghĩa là **không có expiry** theo JMS; áp dụng công thức máy móc sẽ tính TTL=0 và có thể thay đổi contract. Hãy dùng xử lý riêng cho `expiration=0`, clock skew, latency và message đã hết hạn.

Ví dụ XML diễn đạt ý tưởng tính TTL động, chỉ khi biết expiration khác 0 và policy cho phép:

~~~xml
<int-jms:outbound-channel-adapter
        id="forwardOrders"
        connection-factory="jmsConnectionFactory"
        channel="ordersToForward"
        destination-name="orders.forwarded"
        explicit-qos-enabled="true"
        time-to-live-expression="headers.jms_expiration - T(java.lang.System).currentTimeMillis()"/>
~~~

Đây là **fragment minh họa** cho luồng có `jms_expiration` khác 0, còn trong tương lai, và đã validate. Production cần xử lý explicit trường hợp expiration không tồn tại, bằng 0 hoặc đã hết hạn; không để biểu thức sinh TTL âm và giả định sẽ được broker hiểu đúng. JMS TTL không tự kéo dài chỉ vì message được forward.

## 13. Header mapping cho JMS selector, routing và tracing

### 13.1. JMS selector làm việc với properties, không đọc JSON

Một hệ thống xử lý sự kiện từ queue `orders.events` có thể cần chỉ nhận `OrderPaid` tại khu vực `VN`:

~~~text
eventType = 'OrderPaid' AND region = 'VN'
~~~

JMS selector được broker/provider áp dụng lên các **JMS message headers/properties** được hỗ trợ. Vì vậy, producer phải ghi các JMS properties:

~~~java
// Đoạn producer dùng JmsTemplate trực tiếp.
jmsTemplate.convertAndSend(
        "orders.events",
        "{\"eventId\":\"evt-1304\",\"eventType\":\"OrderPaid\"}",
        jmsMessage -> {
            jmsMessage.setStringProperty("eventType", "OrderPaid");
            jmsMessage.setStringProperty("region", "VN");
            return jmsMessage;
        });
~~~

Nếu chỉ đặt `eventType` trong body JSON, selector trên queue sẽ không đọc được trường đó. Nếu mapper dùng outbound prefix `app_` thì selector phải đổi sang `app_eventType`; thay đổi tên property mà quên sửa selector có thể khiến listener không nhận được message dù broker chứa dữ liệu.

**Lưu ý queue/topic:** nhiều consumers trên một queue với selectors khác nhau vẫn chia việc theo semantics queue; selector không biến queue thành topic để mọi consumer nhận cùng một bản. Với topic, mỗi subscription có thể nhận luồng phù hợp selector riêng, theo cấu hình durable/shared.

### 13.2. Dùng header cho routing trong IntegrationFlow

Sau inbound adapter, một router có thể đọc `eventType` để phân luồng:

~~~java
// Fragment Java DSL sau JMS inbound adapter.
.route("headers['eventType']", mapping -> mapping
        .channelMapping("OrderPaid", "paidOrderEvents")
        .channelMapping("OrderCancelled", "cancelledOrderEvents"))
~~~

`paidOrderEvents` và `cancelledOrderEvents` phải được cấu hình có consumer phù hợp. Đây là routing **trong Spring Integration** sau khi JMS message đã đến, khác với JMS selector lọc **trước khi consumer nhận từ broker**.

Nếu `eventType` thiếu hoặc không được mapper truyền vào, router có thể không tìm được nhánh xử lý. Hãy thiết kế default route/error channel và validation; không thả message vào `nullChannel` khi contract yêu cầu bắt mọi event.

### 13.3. Trace ID và hành trình qua các hệ thống

`traceId`/`spanId` dạng chuỗi giúp tra cứu một giao dịch xuyên HTTP → Spring Integration → JMS → DB. Nhưng:

- Không coi mọi tracing header do client cung cấp là đáng tin tuyệt đối.
- Đặt tên và encoding thống nhất, ví dụ `traceId` chỉ dùng chuỗi không có thông tin nhận dạng cá nhân.
- Không truyền cả tracing context chứa object không được JMS hỗ trợ.
- Khi bắt đầu một request mới sau timeout, giữ **business requestId** để truy vết retry, nhưng tạo/duy trì tracing context theo quy tắc của hệ quan sát.
- Ưu tiên instrument tracing tiêu chuẩn của framework nếu có; tránh tự sao chép nội dung nhạy cảm vào headers.

## 14. Giới hạn type, bảo mật và kiểm soát dữ liệu đi ra broker

### 14.1. Vì sao mapper không nên sao chép mọi header?

Giả sử Spring Message có:

~~~text
headers:
  eventType   = "OrderPaid"
  traceId     = "trace-1301"
  tenantKey   = "tenant-42"
  accessToken = "Bearer <secret>"  // Không được truyền ra ngoài
  replyChannel = DirectChannel(...) // Không hợp lệ làm JMS scalar property
~~~

`DefaultJmsHeaderMapper` mặc định hỗ trợ các headers có kiểu JMS property phù hợp, nên **`accessToken` là chuỗi có thể bị truyền ra ngoài nếu không được loại bỏ**. Việc một object `replyChannel` không thể được biểu diễn bằng JMS property **không phải cơ chế lọc bảo mật**. Cần có allowlist minh bạch.

### 14.2. Tạo Spring Message chỉ với headers được cho phép

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public final class JmsEventEnvelope {
    private JmsEventEnvelope() {}

    public static Message<String> newOrderPaid(
            String jsonBody,
            String eventId,
            String traceId) {

        if (eventId == null || eventId.isBlank()) {
            throw new IllegalArgumentException("Missing eventId");
        }
        if (traceId == null || traceId.length() > 128) {
            throw new IllegalArgumentException("Invalid traceId");
        }

        // MessageBuilder sinh các header nội bộ cần thiết;
        // code chỉ thêm ba application headers thuộc allowlist.
        return MessageBuilder.withPayload(jsonBody)
                .setHeader("eventId", eventId)
                .setHeader("eventType", "OrderPaid")
                .setHeader("traceId", traceId)
                .build();
    }
}
~~~

Phương án này phù hợp khi **biên gửi JMS được phép tạo envelope mới** từ payload và dữ liệu đã validate. Nếu upstream có Spring Message cần giữ thêm thông tin cho giao thức nội bộ, đừng sao chép cả bản gốc ra broker mà không xác định rõ trường hợp nào được phép.

Trong các hệ thống cần lọc header nghiêm ngặt, có thể viết một `JmsHeaderMapper` tùy chỉnh chỉ map các property thuộc allowlist. Khi đó vẫn phải xử lý riêng JMS API headers mà gateway cần (`JMSCorrelationID`, `JMSReplyTo`), đồng thời có unit/integration tests cho cả hai chiều; không viết mapper lọc hết headers rồi làm mất request-reply correlation.

### 14.3. Metadata không phải bằng chứng xác thực

Header `tenantKey="tenant-42"` hoặc `userId` do producer gửi tới **không tự là danh tính đáng tin cậy**. JMS broker authentication/ACL, authorization theo service identity và validation nghiệp vụ phải xác định sender có quyền gửi cho tenant nào. Không dựa vào tenant header tự khai báo để cấp quyền truy cập dữ liệu nhạy cảm.

Trong production cần xác định ai được đọc JMS properties qua broker console, quyền xuất log, thời hạn retention và cách masking. Những gì đã vào JMS message có thể được lưu trong broker persistence, DLQ, tracing hoặc audit theo chính sách.

## 15. Header mapping có ảnh hưởng gì tới lỗi, retry và transaction?

Header mapper có thể lỗi **trước khi business handler xử lý**, ví dụ:

| Triệu chứng | Nguyên nhân thường gặp | Hành động phù hợp |
|---|---|---|
| Consumer thấy `eventType=null` | Producer chỉ ghi JSON, không đặt JMS property; mapper đổi prefix | Kiểm tra JMS properties trên wire, thống nhất tên |
| ClassCastException với `schemaVersion` | Producer gửi `String` thay vì `int` | Validate type và schema; chuyển đổi có chủ đích |
| JMS request-reply bị timeout | `jms_correlationId`/`JMSCorrelationID` không khớp; `JMSReplyTo` sai | Inspect request/reply headers và gateway correlationKey |
| Selector không match | Tên property có prefix khác; field không có | Kiểm tra selector, mapped property names |
| `JMSMessageID` thay đổi sau retry | Producer gửi lại JMS Message mới | Dùng `eventId`/`requestId` cho business deduplication |
| Priority trên broker không như mong đợi | Chưa bật explicit QoS; provider áp default | Bật `explicitQosEnabled` và đọc `JMSPriority` thực tế |
| `jms_expiration` không xuất hiện inbound | Mặc định không map inbound expiration | Bật `setMapInboundExpiration(true)` nếu cần |
| Header có kiểu object không hợp lệ | JMS property không hỗ trợ type | Chuyển thành scalar/JSON có schema hoặc loại bỏ |
| Token bị lộ trong JMS properties | Mapper chuyển chuỗi từ Spring header | Allowlist, masking, authorization và kiểm tra logs |
| Lỗi conversion/header trong listener | Message không được tạo thành Spring Message hợp lệ | Xử lý `errorChannel`, JMS transaction và poison-message policy |

### Transaction không thuộc trách nhiệm header mapper

`DefaultJmsHeaderMapper` **không** quản lý `Session.commit()`, `Session.rollback()`, TTL, broker redelivery hoặc DLQ. Với JMS inbound message-driven adapter, khi lỗi mapper/converter gây exception và exception **lan tới listener transacted**, broker có thể redeliver message. Nếu error flow hấp thụ lỗi rồi kết thúc bình thường, listener có thể commit.

Khi chuyển `DirectChannel` sang `ExecutorChannel` hoặc `QueueChannel`, handler có thể chạy sau khi JMS receive đã commit; lỗi đọc Spring headers trong handler async không tự rollback JMS message ban đầu. Đừng dựa vào việc metadata vẫn có mặt để suy ra transaction đang còn hiệu lực.

### Idempotency cần khóa nghiệp vụ ổn định

Nếu producer retry một sự kiện `OrderPaid` sau timeout, JMS provider có thể cấp `JMSMessageID` mới. Handler phải dùng business `eventId` từ payload (hoặc một contract đã xác thực) làm khóa duy nhất trong DB/inbox. `JMSRedelivered` và `JMSXDeliveryCount` giúp điều tra, không thay khóa nghiệp vụ.

## 16. Bài thực hành: kiểm tra header mapping trên broker

**Môi trường:** Java 17+, Spring Integration/JMS, một broker thử nghiệm (ví dụ ActiveMQ Artemis), `ConnectionFactory` hợp lệ, JMS queue `orders.header.test` và hai ứng dụng/role producer–consumer.

Trong bài thực hành, **không để raw JMS receiver và message-driven adapter cùng cạnh tranh trên một queue khi đang kiểm chứng cùng một message**. Mỗi lần thử, chọn một consumer hoặc dùng queue test khác nhau để không hiểu nhầm message bị mapper làm mất.

### Bài A — Spring headers thành JMS properties

1. Tạo outbound adapter như mục 6, thay destination thành `orders.header.test`.
2. Gửi một Spring Message có JSON `String`, cùng headers `eventType="OrderPaid"`, `schemaVersion=1`, `traceId="trace-1301"`.
3. Trong một test consumer JMS thuần, đọc message và so sánh body với properties.
4. Kiểm tra `eventType` là `String`, `schemaVersion` là `int` và không có object Java phức tạp trong JMS properties.

Một test consumer minh họa:

~~~java
import jakarta.jms.Message;
import jakarta.jms.TextMessage;
import org.springframework.jms.core.JmsTemplate;

// Được gọi trong integration test khi JMS inbound adapter chưa chạy.
public void inspectRawJmsMessage(JmsTemplate template) throws Exception {
    Message message = template.receive("orders.header.test");
    if (!(message instanceof TextMessage text)) {
        throw new IllegalStateException("Expected JMS TextMessage");
    }

    System.out.println("body = " + text.getText());
    System.out.println("eventType = "
            + message.getStringProperty("eventType"));
    System.out.println("schemaVersion = "
            + message.getIntProperty("schemaVersion"));
    System.out.println("JMSMessageID = "
            + message.getJMSMessageID());
    System.out.println("JMSCorrelationID = "
            + message.getJMSCorrelationID());
}
~~~

`JmsTemplate` của test nên được cấu hình `receiveTimeout` dương (ví dụ 2000 ms), tránh treo vô hạn khi message không có. Đây là **đoạn test**, không phải consumer production. `receive()` có thể trả `null` nếu hết thời gian chờ, nên code sẽ ném exception như mong muốn cho một case kiểm tra thất bại.

### Bài B — Inbound mapper đọc lại metadata

1. Dừng raw JMS consumer, chạy message-driven inbound adapter ở mục 7.
2. Gửi một event mới cùng tập properties.
3. Xác minh handler nhận payload `String` và Spring headers `eventType`, `schemaVersion`, `traceId`.
4. Gửi thiếu property `eventType`; xác nhận validation/error flow thay vì tự đoán giá trị từ JSON.
5. Gửi `schemaVersion` dưới dạng `String`; xác minh hệ thống phân loại lỗi type đúng, không để `ClassCastException` không có context.

### Bài C — Prefix và JMS selectors

1. Bật mapper inbound `setInboundPrefix("external_")`; kiểm tra Spring header `external_eventType` thay vì `eventType`.
2. Bật outbound prefix `app_`; kiểm tra JMS property `app_eventType`.
3. Cấu hình JMS selector chờ `eventType='OrderPaid'`; quan sát không match nếu chỉ có `app_eventType`.
4. Sửa selector hoặc prefix theo contract, xác minh consumer nhận lại message.
5. So sánh selector tại broker với router đọc Spring header sau inbound.

### Bài D — `correlationId` và `jms_correlationId`

1. Tạo Spring Message có `correlationId` dạng UUID và `jms_correlationId` dạng chuỗi `corr-1301`.
2. Gửi qua outbound adapter, đọc JMS `getJMSCorrelationID()` và JMS property `correlationId`.
3. Nhận lại qua inbound adapter, kiểm tra `correlationId` là `String` còn `jms_correlationId` phản ánh JMS API header.
4. Thử một JMS outbound gateway có fixed reply queue và `correlationKey("JMSCorrelationID")`; kiểm tra reply correlation do gateway sử dụng thực tế.
5. Cố ý cho server trả sai correlation; quan sát timeout và xác định header sai.

### Bài E — QoS thực tế

1. Gửi `priority=8` nhưng **không** bật `explicitQosEnabled`; đọc `JMSPriority` ở JMS consumer.
2. Bật `explicitQosEnabled(true)` và gửi lại; kiểm tra priority áp dụng.
3. Đặt TTL ngắn trong **môi trường test** rồi chờ hết hạn; quan sát expiry policy riêng của broker, không mặc định sẽ thành DLQ xử lý lỗi.
4. Bật `setMapInboundDeliveryMode(true)` và `setMapInboundExpiration(true)`, đọc Spring headers tương ứng.
5. Thử case `JMSExpiration=0`, xác minh forwarding code **không** biến “no expiry” thành “đã hết hạn”.

### Bài F — Bảo mật, lỗi và recovery

1. Thêm Spring header `accessToken` dưới dạng chuỗi trong một sự kiện giả lập (không dùng token thật); xem vì sao default mapping có thể làm lộ metadata này.
2. Đổi producer sang hàm allowlist ở mục 14; xác minh token không còn được gửi vào JMS properties.
3. Gửi header có kiểu object không phù hợp JMS; kiểm tra adapter xử lý lỗi và không làm mất message âm thầm.
4. Với listener transacted, thử conversion/header error; so sánh khi exception được propagate và khi error flow hấp thụ.
5. Dừng broker rồi khởi động lại; kiểm tra mapping còn đúng sau reconnect và phân biệt lỗi kết nối với lỗi contract.

### Ma trận PASS tối thiểu

| Case | Kết quả cần chứng minh |
|---|---|
| Header `eventType` dạng chuỗi | JMS property đúng tên và giá trị |
| Header `schemaVersion` dạng số nguyên | JMS property đọc lại bằng `getIntProperty` đúng |
| JMS `JMSCorrelationID` | Spring header `jms_correlationId` đúng chiều mapping |
| Spring `correlationId` dạng UUID | Được biểu diễn thành property `String` khác với JMS correlation |
| Inbound prefix | Chỉ application properties có prefix, JMS API headers giữ tên mapping đặc thù |
| Outbound prefix | Tên JMS properties đổi; selector được cập nhật theo contract |
| `JMSMessageID`/`JMSRedelivered` | Provider quyết định; application không tự ghi đè |
| QoS priority/TTL | Giá trị áp dụng khi template bật explicit QoS và provider hỗ trợ |
| Body conversion | JMS body đúng JSON, metadata không bị trộn vào payload |
| Secret/internal header | Không bị gửi ra broker sau bước allowlist |
| Header sai kiểu/thiếu field | Báo lỗi rõ và transaction/error flow hoạt động đúng |

Với selector, JMS transaction, redelivery, TTL và correlation, **phải dùng một JMS broker/provider thực hoặc test container tương ứng**. Mock `JmsTemplate` và unit test riêng của mapper có giá trị ở tầng logic nhưng không chứng minh chính sách provider.

## 17. Checklist thiết kế hợp đồng headers cho production

Trước khi đưa một endpoint Spring Integration JMS vào production, nên trả lời được:

1. **Body contract:** payload là `TextMessage` JSON hay định dạng khác? `schemaVersion` ở đâu và ai validate?
2. **Metadata contract:** trường nào nằm trong JMS properties, trường nào nằm trong JMS API headers, trường nào chỉ tồn tại trong Spring Message?
3. **Names & types:** tên property có hợp lệ cho JMS không? Kiểu `int`/`String`/`boolean` được producer và consumer thống nhất chưa?
4. **Correlation:** request-reply dùng `JMSCorrelationID` theo quy ước nào? `JMSReplyTo` có được server tôn trọng không?
5. **Header mapper:** endpoint đang dùng `DefaultJmsHeaderMapper` hay custom? Có prefix nào không? Test cả hai chiều chưa?
6. **Converter:** body converter có độc lập với header mapper không? Có nguy cơ serialize hai lần hoặc dùng `ObjectMessage` ngoài chủ ý không?
7. **QoS:** cần priority, persistent delivery hay TTL? `explicitQosEnabled` và broker policy đã được kiểm tra chưa?
8. **Security:** những headers nào được phép rời JVM? Có token, PII, internal channel/serialized object hoặc thông tin không đáng tin không?
9. **Failure handling:** lỗi header mapping trước handler đi đâu? Listener transacted, error channel, retry và DLQ có được thiết kế đúng không?
10. **Observability:** log có `eventId`/`requestId`, JMS message ID/correlation ID và destination khi cần, nhưng không rò rỉ payload nhạy cảm không?

## 18. Câu hỏi tự đánh giá

1. JMS `Message` khác Spring `Message<?>` ở các nhóm metadata nào?
2. `MessageConverter` và `JmsHeaderMapper` giải quyết hai bài toán khác nhau thế nào?
3. `DefaultJmsHeaderMapper.fromHeaders(...)` và `toHeaders(...)` hoạt động theo hướng nào?
4. Vì sao JMS `JMSMessageID` thường chỉ map inbound mà không cho caller tự ghi đè?
5. Tại sao Spring header `correlationId` không đồng nghĩa với JMS `JMSCorrelationID`?
6. Khi JMS `JMSReplyTo` chứa `TemporaryQueue`, có thể thay trực tiếp bằng một chuỗi tùy ý từ HTTP header không?
7. Vì sao Java `UUID` không phải một JMS application property type tiêu chuẩn?
8. Nếu outbound mapper thêm prefix `app_`, JMS selector phải thay đổi thế nào?
9. Vì sao `extractPayload(false)` không phải giải pháp để giữ Spring headers?
10. Tại sao bật `setMapInboundExpiration(true)` không đồng nghĩa bảo toàn TTL qua thao tác forward?
11. `JMSExpiration=0` có ý nghĩa gì với việc tính TTL còn lại?
12. Vì sao một header `accessToken` dạng `String` có thể nguy hiểm dù không nằm trong JMS body?
13. Trường hợp nào exception do header mapper không thể rollback JMS message đã được ack?
14. Producer retry cùng event với JMS message ID mới: handler dựa vào khóa nào để chống trùng?
15. Khi dùng request-reply gateway với fixed reply queue, correlation contract cần được kiểm tra những gì?

## 19. Tài liệu tham khảo chính thức

- [Spring Integration Reference — JMS Support](https://docs.spring.io/spring-integration/reference/jms.html): **Mapping Message Headers to and from JMS Message**, default mapper, correlation, `priority`, QoS và gateway.
- [Spring Integration API — DefaultJmsHeaderMapper](https://docs.spring.io/spring-integration/api/org/springframework/integration/jms/DefaultJmsHeaderMapper.html): `fromHeaders`, `toHeaders`, `setInboundPrefix`, `setOutboundPrefix`, `setMapInboundDeliveryMode`, `setMapInboundExpiration`.
- [Spring Integration API — JmsHeaderMapper](https://docs.spring.io/spring-integration/api/org/springframework/integration/jms/JmsHeaderMapper.html): contract ánh xạ Spring headers ↔ JMS message.
- [Spring Framework API — JmsHeaders](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/support/JmsHeaders.html): các hằng số tên JMS headers trong Spring messaging.
- [Spring Integration API — JmsMessageDrivenChannelAdapterSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/jms/dsl/JmsMessageDrivenChannelAdapterSpec.html): cấu hình `headerMapper` cho inbound DSL.
- [Spring Integration API — JmsOutboundChannelAdapterSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/jms/dsl/JmsOutboundChannelAdapterSpec.html): cấu hình `headerMapper`, expression và adapter gửi.
- [Spring Integration API — JmsTemplateSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/jms/dsl/JmsTemplateSpec.html): `explicitQosEnabled`, `priority`, `timeToLive`, converter.
- [Spring Framework Reference — JMS](https://docs.spring.io/spring-framework/reference/integration/jms.html): `JmsTemplate`, `MessagePostProcessor`, JMS operations và Quality of Service.
- [Jakarta Messaging Specification](https://jakarta.ee/specifications/messaging/3.1/): JMS standard headers, properties, delivery modes và message selectors.

**Ghi nhớ:** `DefaultJmsHeaderMapper` kết nối metadata của Spring `MessageHeaders` với JMS API headers và JMS properties; `MessageConverter` xử lý **body** riêng biệt. Đừng đánh đồng `correlationId` với `jms_correlationId`, đừng ghi đè JMS headers do provider cấp, và đừng nghĩ QoS tự có hiệu lực chỉ vì Spring Message chứa `priority`. Header mapping đúng phải đi cùng **hợp đồng tên/type**, explicit QoS khi cần, validation, allowlist bảo mật, transaction/error handling và integration test với broker thực.




