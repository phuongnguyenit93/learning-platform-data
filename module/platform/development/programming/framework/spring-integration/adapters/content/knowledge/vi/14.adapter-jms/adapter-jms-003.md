# JMS outbound channel adapter

## 1. JMS outbound channel adapter giải quyết bài toán gì?

Giả sử dịch vụ quản lý đơn hàng của doanh nghiệp cần thông báo cho hệ thống kho mỗi khi một đơn đã thanh toán. Nghiệp vụ nội bộ đã tạo sự kiện `OrderPaid` dưới dạng Spring Message; hệ thống kho lại chỉ nhận message qua JMS queue `warehouse.orders`. **JMS outbound channel adapter** là điểm cuối của luồng Spring Integration, nhận Spring Message và gửi một JMS message tới queue/topic trên broker.

Trong phạm vi module **SPRING_INTEGRATION_ADAPTERS**, outbound adapter là cầu nối từ `MessageChannel` tới hệ thống ngoài. Inbound adapter mang dữ liệu vào Spring Integration; gateway hỗ trợ trao đổi request/reply; poller điều phối nguồn dữ liệu phải lấy theo lịch. Bài này tập trung vào chiều **Spring Integration → JMS broker**, đồng thời làm rõ hợp đồng message, xử lý lỗi, transaction và vòng đời kết nối.

Điểm quan trọng nhất: **outbound channel adapter là một endpoint một chiều**. Nó gửi message tới JMS destination và kết thúc việc gửi; không chờ nhận kết quả xử lý nghiệp vụ từ JMS consumer. Nếu bên nhận phải trả lời một request qua JMS reply destination, cần xem **JMS outbound gateway**.

### Sơ đồ trao đổi

~~~mermaid
flowchart LR
    A["Order Service"] -->|"Spring Message<OrderPaid JSON>"| B["MessageChannel"]
    B --> C["JMS outbound channel adapter"]
    C -->|"JmsTemplate.convertAndSend"| D[("JMS broker: warehouse.orders")]
    D -->|"Delivery theo broker"| E["Warehouse consumer"]
    E --> F[("Hệ thống kho")]
~~~

Từ góc nhìn ứng dụng gửi:

1. Một thành phần tạo Spring Message gồm payload và headers phù hợp.
2. `MessageChannel` chuyển message tới `JmsSendingMessageHandler` của outbound adapter.
3. Handler chọn JMS destination, chuyển body của Spring Message qua `MessageConverter` và ánh xạ metadata bằng `JmsHeaderMapper`.
4. `JmsTemplate` sử dụng `ConnectionFactory` để gửi JMS message qua provider tới broker.
5. Lời gọi gửi kết thúc hoặc ném exception; **thành công ở bước gửi không chứng minh consumer đã xử lý message**.

Outbound adapter **không tự polling** và cũng không cần JMS `MessageListenerContainer`: nó được gọi khi có Spring Message đi vào endpoint.

## 2. Các thành phần và ranh giới trách nhiệm

| Thành phần | Vai trò | Lưu ý khi thiết kế |
|---|---|---|
| `MessageChannel` | Nhận Spring Message từ bước trước | `DirectChannel` gọi handler đồng bộ; channel bất đồng bộ tách thời điểm xử lý |
| `JmsSendingMessageHandler` | Endpoint Spring Integration thực hiện gửi JMS | Không có reply message như gateway |
| `JmsTemplate` | Tạo session/producer và gửi tới destination | Cấu hình session transaction, QoS, converter, exception translation |
| `ConnectionFactory` | Mở và quản lý kết nối JMS qua provider | Cấu hình URL, xác thực, TLS, recovery/caching theo broker |
| `MessageConverter` | Biến payload Java thành JMS `TextMessage`, `BytesMessage`... | Phải tương thích hợp đồng tiêu thụ của hệ thống ngoài |
| `JmsHeaderMapper` | Ánh xạ Spring headers thành JMS header/properties được hỗ trợ | Chú ý kiểu dữ liệu hợp lệ và tên header đặc biệt |
| `Destination` / `DestinationResolver` | Xác định queue/topic cần nhận message | Có thể cố định hoặc tính động từ message đã kiểm tra |
| JMS broker | Nhận, lưu trữ/phân phối message | Quản lý durability, quota, expiry, ACL, DLQ và consumer |

Không nhầm **Spring Message** (`org.springframework.messaging.Message`) với **JMS Message** (`jakarta.jms.Message`). Hai đối tượng có phần body, header/property và vòng đời khác nhau; outbound adapter thực hiện chuyển đổi tại ranh giới tích hợp.

## 3. Cấu hình Java DSL: đẩy thông báo đơn hàng ra queue

Ví dụ dành cho Spring Integration 6+ với Jakarta JMS. Dự án dùng Spring Boot có thể khai báo dependency như sau khi version được quản lý qua Spring Boot BOM:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-jms</artifactId>
</dependency>
<!-- Bổ sung JMS starter/client phù hợp broker được triển khai. -->
~~~

Ứng dụng cần có bean `ConnectionFactory` đã kết nối tới broker, destination `warehouse.orders` và quyền gửi tương ứng. Cách cấu hình kết nối và tạo queue phụ thuộc ActiveMQ Artemis, IBM MQ hoặc JMS provider thực tế.

### 3.1. Khai báo channel và outbound flow

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.dsl.Jms;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class WarehouseJmsOutboundConfig {

    @Bean
    public MessageChannel warehouseOutboundChannel() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow warehouseOutboundFlow(
            ConnectionFactory connectionFactory,
            @Qualifier("warehouseOutboundChannel") MessageChannel warehouseOutboundChannel) {

        return IntegrationFlow.from(warehouseOutboundChannel)
                .handle(Jms.outboundAdapter(connectionFactory)
                        .destination("warehouse.orders"))
                .get();
    }
}
~~~

Giải thích:

- `IntegrationFlow.from(warehouseOutboundChannel)` dùng một channel làm điểm bắt đầu của đoạn flow; nơi phát message có thể là service, integration flow khác hoặc gateway.
- `.handle(Jms.outboundAdapter(connectionFactory).destination("warehouse.orders"))` đăng ký handler gửi JMS. Khi message đến, handler gọi `JmsTemplate`, không dùng poller.
- `DirectChannel` giữ lời gọi handler trong cùng luồng thực thi với sender. Nếu có lỗi đồng bộ khi gửi, caller có cơ hội nhận exception ngay. Dùng channel bất đồng bộ sẽ thay đổi ranh giới lỗi và xác nhận.
- Ví dụ dùng queue định danh cố định; nó không tự sinh tên queue hoặc thay đổi địa chỉ broker.

### 3.2. Gửi message từ một service

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class WarehouseNotificationService {
    private final MessageChannel outboundChannel;

    public WarehouseNotificationService(
            @Qualifier("warehouseOutboundChannel") MessageChannel outboundChannel) {
        this.outboundChannel = outboundChannel;
    }

    public void notifyPaidOrder(String jsonPayload, String eventId) {
        boolean accepted = outboundChannel.send(
                MessageBuilder.withPayload(jsonPayload)
                        .setHeader("eventId", eventId)
                        .setHeader("schemaVersion", 1)
                        .setHeader("sourceSystem", "order-service")
                        .build());

        if (!accepted) {
            throw new IllegalStateException("Spring MessageChannel từ chối message");
        }
    }
}
~~~

Giả sử `jsonPayload` có nội dung:

~~~json
{
  "eventId": "evt-3010",
  "schemaVersion": 1,
  "eventType": "OrderPaid",
  "orderId": "ORD-301",
  "paidAt": "2026-11-23T01:00:00Z"
}
~~~

Với converter mặc định thông dụng, payload kiểu `String` tạo ra JMS `TextMessage`. Các header tùy biến kiểu chuỗi/số nguyên có thể được ánh xạ thành JMS properties nếu header mapper cho phép. Sender nên thống nhất tên trường và định dạng JSON với consumer; không tự giả định ứng dụng nhận hiểu Java object nội bộ.

**Ý nghĩa của `send()`:** trả về `true` cho biết message được Spring `MessageChannel` tiếp nhận theo ngữ nghĩa channel. Với `DirectChannel`, adapter được gọi đồng bộ trước khi trả về; với channel dạng queue/executor, `true` có thể chỉ nghĩa là đã được đưa vào channel, **chưa phải gửi JMS thành công**. Ngay cả khi JMS send hoàn tất, consumer và database phía sau vẫn có thể chưa xử lý.

### 3.3. Cấu hình XML tương đương

~~~xml
<int:channel id="warehouseOutboundChannel"/>

<int-jms:outbound-channel-adapter
        id="warehouseJmsSender"
        channel="warehouseOutboundChannel"
        connection-factory="jmsConnectionFactory"
        destination-name="warehouse.orders"/>
~~~

Fragment XML cần các namespace Spring Integration `int` và `int-jms`, bean `jmsConnectionFactory`, cùng thành phần đưa message vào channel. Nếu đã dùng Java DSL thì không đăng ký thêm XML adapter cùng channel trừ khi chủ ý gửi nhiều bản sao, vì nhiều subscriber trên `DirectChannel` không có nghĩa mọi subscriber đều nhận từng message.

## 4. Hợp đồng payload và cách ánh xạ headers

Mặc định, thuộc tính `extractPayload` của outbound channel adapter là `true`. Điều này nghĩa là adapter lấy **payload của Spring Message** để làm body JMS, còn Spring headers được xử lý riêng qua header mapper.

| Spring payload | JMS message thường được tạo bằng `SimpleMessageConverter` | Điểm cần lưu ý |
|---|---|---|
| `String` | `TextMessage` | Thích hợp JSON/XML/chuỗi theo schema rõ ràng |
| `byte[]` | `BytesMessage` | Thống nhất encoding, format và giới hạn kích thước |
| `Map` với dữ liệu hợp lệ | `MapMessage` | Kiểm tra giá trị được JMS hỗ trợ |
| `Serializable` | `ObjectMessage` | Phụ thuộc class Java, serialVersionUID và độ tin cậy dữ liệu; tránh làm hợp đồng liên dịch vụ |

Với `extractPayload(false)`, adapter có thể chuyển **toàn bộ Spring Message** thành JMS body theo converter phù hợp. Chế độ này phù hợp rất ít tình huống, vì consumer phải giải mã được hình dạng Spring Message và dữ liệu nội bộ. Đối với tích hợp giữa các dịch vụ, nên ưu tiên `extractPayload(true)` cùng định dạng thông điệp độc lập nền tảng như JSON hoặc Avro/Protobuf đã có schema.

### Header JMS chuẩn và JMS properties

JMS phân biệt:

1. **Header chuẩn** như `JMSCorrelationID`, `JMSReplyTo`, `JMSType`, `JMSPriority`, `JMSExpiration`.
2. **Application properties** là các giá trị primitive/`String` do ứng dụng định nghĩa.

`DefaultJmsHeaderMapper` có thể ánh xạ các Spring headers được hỗ trợ sang các trường tương ứng, nhưng không phải mọi Spring header đều hợp lệ làm JMS property. Các header là đối tượng tùy ý, kiểu dữ liệu không được JMS chấp nhận hoặc tên không hợp lệ có thể bị bỏ qua/không ánh xạ. Ví dụ `eventId` và `sourceSystem` kiểu `String` là lựa chọn đơn giản cho tracing.

Các trường quan trọng nên đặt trong **payload contract** hoặc một header đã được thỏa thuận; đừng dựa vào việc mọi header nội bộ của Spring tự động được lưu trên broker. `JMSMessageID` thường do JMS provider sinh cho một lần gửi, còn `eventId` là mã sự kiện nghiệp vụ phải ổn định để phía nhận phát hiện message trùng.

`correlationId` của Spring Integration và `jms_correlationId` ánh xạ tới `JMSCorrelationID` không hoàn toàn là một. Khi dùng request/reply hoặc theo dõi chuỗi xử lý, cần xác định rõ consumer cần trường nào. Outbound channel adapter chỉ **gửi**, nên việc có `JMSCorrelationID` không làm nó trở thành gateway nhận reply.

### Chọn converter phù hợp

Không mặc định mọi đối tượng domain tự chuyển thành JSON. Nếu payload là `OrderPaid` (Java object), `SimpleMessageConverter` có thể xử lý theo Java serialization hoặc không tương thích với consumer mong đợi JSON. Để truyền JSON, có thể:

- Serialize domain object thành JSON ở bước `.transform(...)` trước outbound adapter, với schema và version được kiểm soát.
- Cấu hình `MessageConverter` JMS thích hợp và thống nhất mapping với phía nhận.

Ví dụ một bước transform khi nguồn đã có object `OrderPaid`:

~~~java
// Ví dụ minh họa phần flow; objectMapper là Jackson ObjectMapper.
.transform(OrderPaid.class, event -> {
    try {
        return objectMapper.writeValueAsString(event);
    } catch (com.fasterxml.jackson.core.JsonProcessingException ex) {
        throw new IllegalStateException("Không thể serialize OrderPaid", ex);
    }
})
.handle(Jms.outboundAdapter(connectionFactory)
        .destination("warehouse.orders"))
~~~

Đây là fragment cần đặt trong IntegrationFlow thích hợp, có biến `objectMapper` được inject. Lỗi serialize được chuyển thành exception không kiểm tra để flow xử lý trước khi gửi JMS.

## 5. Chọn destination cố định hoặc động

Đa số nghiệp vụ nên dùng một destination cố định và phân biệt loại sự kiện bằng `eventType`/`schemaVersion`, giúp ACL, giám sát và triển khai consumer rõ ràng.

Khi phải định tuyến tới nhiều queue, Java DSL hỗ trợ expression/function quyết định destination từ Spring Message. Ví dụ:

~~~java
.handle(Jms.outboundAdapter(connectionFactory)
        .destinationExpression("headers['targetQueue']"))
~~~

`targetQueue` phải được một bước **kiểm tra và ánh xạ allowlist** tạo ra; không sử dụng trực tiếp giá trị do client không đáng tin cậy truyền vào. Nếu ứng dụng chỉ cho phép `warehouse.orders` và `warehouse.returns`, hãy validate giá trị đó trước khi gửi. Khi destination thay đổi theo payload, theo dõi metric/ACL riêng cho từng queue và xử lý trường hợp thiếu header.

**Queue và topic khác nhau về phân phối:** queue thường phục vụ competing consumers, một message được một consumer xử lý; topic có thể fan-out tới nhiều subscription. Cần cấu hình JMS `pubSubDomain` hoặc `Destination` tương ứng trong `JmsTemplate`/provider; không thể chỉ đổi tên queue thành topic rồi mặc nhiên có semantics publish-subscribe. Với topic, cần xem loại subscription (durable/non-durable) ở phía consumer nếu muốn nhận khi subscriber offline.

## 6. QoS: persistent delivery, priority và time-to-live

JMS cung cấp một số thuộc tính chất lượng gửi (QoS):

| Thuộc tính | Ý nghĩa | Rủi ro nếu chọn sai |
|---|---|---|
| `DeliveryMode.PERSISTENT` | Yêu cầu provider lưu message theo cam kết durability phù hợp | Có chi phí I/O; độ bền thực tế còn phụ thuộc broker và cấu hình |
| `DeliveryMode.NON_PERSISTENT` | Cho phép gửi với độ bền thấp hơn | Có thể mất message khi broker gặp sự cố |
| `priority` (0–9) | Gợi ý broker ưu tiên phân phối | Không nên dựa vào priority để bảo đảm thứ tự nghiệp vụ |
| `timeToLive` (mili giây) | Thời gian sống của message tính từ lúc gửi; hết hạn có thể bị loại bỏ hoặc xử lý theo policy | Đặt TTL quá ngắn có thể khiến consumer không bao giờ thấy message |

Mặc định của JMS send thường là persistent, priority 4 và TTL không giới hạn, nhưng cần kiểm tra thiết lập cuối của provider. Để một số cấu hình QoS động trên `JmsSendingMessageHandler` có hiệu lực, `JmsTemplate` phải bật **`explicitQosEnabled`**; Spring Integration Java DSL dùng `DynamicJmsTemplate` khi cấu hình adapter từ `ConnectionFactory`.

Ví dụ chỉ dùng cho **thông báo có thể hết hạn**:

~~~java
.handle(Jms.outboundAdapter(connectionFactory)
        .destination("warehouse.notifications")
        .timeToLiveExpression("60000")
        .configureJmsTemplate(template -> template.explicitQosEnabled(true)))
~~~

Khi đó TTL đặt là 60.000 ms. Đây là fragment để đưa vào flow, không được thêm một adapter thứ hai vào cùng message path nếu bạn chỉ muốn gửi một bản. Sự kiện tài chính, thay đổi trạng thái đơn hàng hoặc thông điệp cần audit thường **không nên có TTL ngắn**. `JMSExpiration` là timestamp hết hạn sau khi message được gửi; `timeToLive` là thời lượng đưa vào thao tác gửi, hai giá trị không đồng nhất.

## 7. Transaction: gửi thành công và tính nhất quán dữ liệu

Outbound adapter dùng `JmsTemplate`. Khi đặt `sessionTransacted=true` cho template, nếu **không có transaction JMS bên ngoài**, template có thể tự tạo một giao dịch JMS cục bộ cho thao tác gửi rồi commit khi gửi thành công. Nếu có transaction JMS đang hoạt động trên cùng tài nguyên và luồng thực thi, send có thể tham gia transaction đó. Cấu hình XML `session-transacted` trên outbound adapter cũng phục vụ mục đích này.

### Trường hợp nhận từ một JMS queue rồi chuyển sang queue khác

Một flow có thể đọc `orders.in` qua JMS message-driven inbound adapter, xử lý đồng bộ rồi gửi `orders.out` qua outbound adapter. Khi hai bước dùng **cùng `ConnectionFactory`**, JMS transaction được cấu hình đúng và luồng xử lý giữ đồng bộ, việc nhận và gửi có thể cùng transaction JMS. Nếu handler ném lỗi trước commit, broker có cơ hội rollback cả việc nhận lẫn việc gửi. Tuy vậy, phải kiểm tra thực tế việc sử dụng cùng JMS session/transaction, cách listener container được cấu hình và đặc tính provider; không mặc định cứ có hai endpoint JMS là giao dịch sẽ tự gộp.

### Trường hợp ghi database rồi gửi JMS

Giả sử hệ thống thực hiện:

1. Ghi trạng thái đơn hàng `PAID` vào database.
2. Gửi `OrderPaid` đến `warehouse.orders`.

Hai tài nguyên **database và JMS broker** không tự thuộc một giao dịch nguyên tử. Nếu DB commit rồi JVM crash trước bước 2, đơn hàng đã thanh toán nhưng chưa có event. Nếu JMS send được commit trước khi transaction DB thất bại, consumer có thể nhận event về một trạng thái chưa tồn tại trong DB. Chỉ thêm `@Transactional` dùng `DataSourceTransactionManager` không tự biến JMS send thành một phần của transaction DB.

~~~mermaid
flowchart TD
    A["Bắt đầu DB transaction"] --> B["Ghi Order=PAID"]
    B --> C["Ghi event vào outbox cùng DB transaction"]
    C --> D["Commit DB"]
    D --> E["Outbox publisher đọc bản ghi chưa gửi"]
    E --> F["JMS outbound adapter gửi event"]
    F --> G{"Gửi thành công?"}
    G -->|Có| H["Đánh dấu outbox đã gửi"]
    G -->|Thất bại| I["Giữ outbox để retry có kiểm soát"]
~~~

**Transactional outbox** là mô hình thực dụng cho các sự kiện quan trọng: ghi thay đổi nghiệp vụ và bản ghi outbox trong **cùng DB transaction**; worker/integration flow khác đọc outbox và gửi JMS, sau đó đánh dấu kết quả. Vì bước đánh dấu và JMS send vẫn có cửa sổ lỗi, event **có thể được gửi nhiều lần**; consumer cần idempotency dựa trên `eventId`.

Nếu phát event đã được tạo từ một JMS inbound adapter giao dịch, hãy giữ `DirectChannel`/xử lý đồng bộ khi muốn exception ảnh hưởng transaction ở upstream. Chèn `ExecutorChannel` hoặc `QueueChannel` có thể tách transaction và khiến inbound đã commit trước khi outbound gửi thất bại.

**Không hứa hẹn exactly-once chỉ nhờ cấu hình JMS transaction.** Tính đúng đắn xuyên hệ thống thường yêu cầu outbox/inbox, idempotent consumer, retry và monitoring; distributed/XA transaction chỉ thích hợp khi thực sự được provider và hạ tầng hỗ trợ, đồng thời chấp nhận chi phí vận hành.

## 8. Lỗi khi gửi, retry và dead-letter

### Lỗi xảy ra ở đâu?

- **Trước khi gửi:** thiếu destination, serialize JSON lỗi, giá trị property sai, converter thất bại.
- **Trong lúc gửi:** kết nối JMS bị đóng, broker quá tải, thiếu quyền gửi, network timeout hoặc provider báo lỗi.
- **Sau khi gửi nhưng chưa biết kết quả:** ứng dụng mất kết nối đúng lúc broker đã nhận message nhưng client không nhận được xác nhận; retry có thể tạo bản sao.
- **Sau khi broker chấp nhận:** consumer downstream có thể thất bại hoặc bị dừng; outbound adapter không biết kết quả đó.

Với `DirectChannel`, exception từ `JmsSendingMessageHandler` thường truyền ngược về thành phần đang gọi `send()` (có thể được bọc trong exception của messaging). Caller hoặc advice ở upstream phải quyết định rollback, retry hoặc ghi lỗi. Nếu dùng `ExecutorChannel`, thread gửi ban đầu có thể đã kết thúc; lỗi đi qua cơ chế error handling bất đồng bộ, vì vậy phải quan sát `errorChannel` và cấu hình executor phù hợp.

**`errorChannel` không tự retry JMS send và không tự đưa message vào DLQ.** JMS dead-letter queue chủ yếu là một phần của broker/consumer redelivery; với lỗi **producer không gửi được**, hãy dùng retry/outbox/quarantine phía producer hoặc kênh lỗi do ứng dụng thiết kế.

### Chính sách retry có trách nhiệm

| Loại lỗi | Có nên retry tự động? | Hướng xử lý |
|---|---|---|
| Broker tạm mất kết nối | Có, giới hạn số lần/giãn cách | Backoff, retry qua outbox, cảnh báo backlog |
| Broker quá tải/rate limit | Có, tôn trọng tài nguyên | Giảm tốc phát, không tạo vòng lặp nóng |
| Destination không tồn tại hoặc ACL từ chối | Thường không retry tức thời vô hạn | Sửa cấu hình hoặc quyền, đưa trạng thái lỗi rõ ràng |
| Payload không hợp schema | Không gửi lại nguyên vẹn không giới hạn | Validate trước khi gửi, quarantine bản ghi lỗi |
| Kết quả send không chắc chắn | Có thể retry nhưng phải chấp nhận gửi trùng | `eventId` ổn định, idempotency phía nhận |

Ví dụ pseudo-flow của ứng dụng sử dụng outbox:

~~~text
DB outbox PENDING
    -> đọc batch có lock/lease
    -> gửi qua JMS outbound adapter
        -> thành công: đánh dấu SENT
        -> lỗi tạm thời: ghi attempts, next_retry_at, last_error
        -> lỗi vĩnh viễn: chuyển FAILED/quarantine, cảnh báo
~~~

Tách thời điểm gửi lại bằng backoff và giới hạn attempts giúp tránh một publisher bận liên tục khi broker gặp sự cố. Dùng idempotency ở phía consumer vì publisher có thể crash sau khi broker nhận message nhưng trước khi đánh dấu `SENT`.

### Dừng/khởi động lại ứng dụng

Outbound adapter không có listener chạy liên tục để tự tiêu thụ message. Nó sử dụng `ConnectionFactory`/`JmsTemplate` khi handler được gọi. Khi broker không sẵn sàng, thao tác gửi có thể lỗi; nếu ứng dụng chỉ giữ thông báo trong RAM, việc restart có nguy cơ làm mất dữ liệu chưa gửi. Muốn replay an toàn, lưu sự kiện vào outbox hoặc một thành phần có độ bền tương ứng và kiểm soát thứ tự gửi.

Theo dõi tối thiểu: số message gửi thành công/thất bại, thời gian gửi, số retry, độ sâu outbox, tuổi bản ghi PENDING cũ nhất, trạng thái kết nối broker, quota destination, số message hết hạn và tỉ lệ consumer xử lý thành công ở hệ thống nhận nếu có metrics liên thông.

## 9. So sánh outbound adapter với các lựa chọn khác

| Nhu cầu | Endpoint phù hợp | Vì sao |
|---|---|---|
| Đẩy một event sang JMS queue và không đợi reply | **JMS outbound channel adapter** | Một chiều, chuyển Spring Message thành JMS Message |
| Gửi JMS request rồi đợi JMS reply | JMS outbound gateway | Có reply destination, correlation và timeout |
| Lấy message từ JMS queue theo lịch | JMS polling inbound adapter | `JmsTemplate.receive()` theo poller |
| Nhận JMS ngay khi broker giao | JMS message-driven inbound adapter | JMS listener container |
| Phát sang HTTP/Kafka/AMQP | Adapter/gateway tương ứng protocol | Mỗi protocol có contract và retry riêng |

Việc có header `JMSReplyTo` trên message **không khiến outbound adapter tự nhận response**. Nếu cần kết quả từ consumer, chọn gateway ngay từ thiết kế hợp đồng: request destination, reply destination, correlation ID, timeout và cách xử lý reply muộn.

## 10. Thực hành: chuyển sự kiện thanh toán sang hệ thống kho

**Bối cảnh:** ứng dụng gửi JSON `OrderPaid` tới queue `warehouse.orders`, hệ thống kho có consumer đọc và xác nhận việc nhập event. Dùng broker thử nghiệm thật hoặc container được cấu hình phù hợp.

1. **Happy path:** cấu hình `ConnectionFactory`, queue và Java DSL như mục 3; gửi `evt-3010`; kiểm tra queue/consumer nhận `TextMessage` đúng JSON.
2. **Header contract:** quan sát các property được mapper chuyển, kiểm tra `eventId`/`schemaVersion`, JMS message ID và tên destination. Đừng giả định mọi Spring header đều tới được consumer.
3. **Converter:** thử payload `String` và một Java domain object; giải thích vì sao cần serializer/converter phù hợp để consumer nhận JSON.
4. **Broker offline:** ngắt broker, gọi flow qua `DirectChannel`; kiểm tra exception, retry/outbox và số event còn chờ.
5. **Timeout/kết quả không chắc chắn:** mô phỏng lỗi kết nối sau khi gửi, retry cùng `eventId`; xác minh consumer không tạo hai lần tác động nghiệp vụ.
6. **QoS:** gửi notification thử với TTL ngắn và quan sát policy expiry. Không dùng đơn hàng thật để kiểm thử TTL.
7. **Destination động:** thử `targetQueue` hợp lệ và không hợp lệ; xác minh allowlist ngăn gửi tùy ý.
8. **Transaction:** ghi DB rồi chủ động làm lỗi JMS send; quan sát tình huống bất nhất và triển khai outbox để có thể retry.
9. **Dừng/khởi động lại:** restart publisher khi outbox còn PENDING; xác minh publisher tiếp tục gửi và số bản ghi nghiệp vụ phía nhận không tăng trùng.

Khi kiểm chứng transaction và độ bền, cần dùng JMS broker/provider thật; unit test mock `JmsTemplate` không thể chứng minh broker đã persist message, xử lý reconnect hoặc semantics crash giữa các lần commit.

### Câu hỏi tự đánh giá

1. Khi `warehouseOutboundChannel.send(...)` trả `true`, những khâu nào đã được xác nhận và những khâu nào vẫn chưa?
2. Vì sao outbound adapter không cần poller? Nó khác message-driven inbound ở điểm kích hoạt nào?
3. `extractPayload(true)` và `extractPayload(false)` tạo khác biệt gì ở JMS body?
4. Vì sao `JMSMessageID` không đủ để chống xử lý trùng một sự kiện nghiệp vụ được gửi lại?
5. Nếu ghi DB thành công nhưng gửi JMS thất bại, mô hình outbox giúp khôi phục như thế nào?
6. Tại sao cần `explicitQosEnabled` khi cấu hình QoS động qua outbound adapter?
7. Với yêu cầu producer phải nhận trạng thái xử lý từ warehouse, nên thay adapter bằng endpoint nào?

## 11. Tài liệu tham khảo

- [Spring Integration Reference — JMS Support](https://docs.spring.io/spring-integration/reference/jms.html): `JmsSendingMessageHandler`, outbound adapter, `extractPayload`, mapping, QoS và transaction.
- [Spring Integration Java DSL API — JmsOutboundChannelAdapterSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/jms/dsl/JmsOutboundChannelAdapterSpec.html): lựa chọn destination cố định/động, header mapper và biểu thức QoS.
- [Spring Framework Reference — JMS](https://docs.spring.io/spring-framework/reference/integration/jms.html): `JmsTemplate`, converter, giao dịch và hạ tầng JMS.

**Ghi nhớ:** JMS outbound channel adapter đưa Spring Message ra JMS broker theo nhu cầu gửi từ luồng tích hợp. Thiết kế tin cậy cần làm rõ hợp đồng payload/header, destination và QoS, xử lý exception, ranh giới transaction với database, outbox/retry và idempotency của consumer. Broker nhận message thành công là một bước trong quy trình, không phải bằng chứng rằng nghiệp vụ downstream đã hoàn thành.
