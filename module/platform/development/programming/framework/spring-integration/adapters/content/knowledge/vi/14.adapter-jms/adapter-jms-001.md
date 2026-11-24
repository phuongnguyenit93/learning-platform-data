# JMS inbound channel adapter polling

## 1. Bài toán: lấy message từ JMS theo lịch

Trong Spring Integration, **JMS inbound channel adapter dạng polling** là điểm vào một chiều đưa message từ một JMS destination (thường là queue) vào luồng xử lý qua `MessageChannel`. Thành phần này chủ động gọi `JmsTemplate.receive()` theo lịch của **poller**. Nó phù hợp khi ứng dụng muốn kiểm soát thời điểm hoặc nhịp nhập dữ liệu, chẳng hạn cứ vài giây quét queue chứa yêu cầu đồng bộ từ hệ thống ERP cũ.

Đây là một trong các cách kết nối hệ thống ngoài của module **SPRING_INTEGRATION_ADAPTERS**: inbound adapter nhận dữ liệu, outbound adapter gửi dữ liệu, gateway phục vụ trao đổi yêu cầu–phản hồi, còn `MessageChannel` tách nguồn JMS khỏi bước xử lý nghiệp vụ. Chủ đề này đi sâu vào **JMS inbound channel adapter polling**, không thay thế toàn bộ kiến thức về các adapter file, SFTP, HTTP, AMQP, Kafka hay database.

Ví dụ xuyên suốt: hệ thống ERP gửi JSON đơn hàng vào queue `orders.in`. Ứng dụng Spring Integration quét queue mỗi 5 giây, lấy tối đa 10 message mỗi lượt, chuyển chúng sang Spring Message và giao cho handler nhập đơn hàng. Nghiệp vụ cho phép trễ vài giây; nếu yêu cầu phản ứng ngay khi broker nhận message, giải pháp message-driven thường thích hợp hơn.

### Mô hình dữ liệu và đường đi

~~~mermaid
flowchart LR
    A["ERP / hệ thống ngoài"] -->|"JMS TextMessage"| B[("Broker: orders.in")]
    P["Poller: fixedDelay 5 giây"] -->|"Kích hoạt receive()"| C["JMS inbound adapter"]
    B -->|"JmsTemplate.receive()"| C
    C -->|"Spring Message"| D["MessageChannel"]
    D --> E["Validate / xử lý đơn hàng"]
    E --> F[("Cơ sở dữ liệu")]
~~~

Luồng thực thi của một lượt polling:

1. `TaskScheduler` kích hoạt poller theo `fixedDelay`, `fixedRate` hoặc cron.
2. Inbound adapter gọi `receive()` trên JMS destination. Nếu không có message và dùng chế độ nhận không chờ, lượt nhận kết thúc ngay.
3. `MessageConverter` chuyển JMS message thành payload của Spring Message; `JmsHeaderMapper` ánh xạ các header phù hợp.
4. Adapter gửi Spring Message đến `MessageChannel`; consumer phía sau nhận và xử lý.
5. Nếu `maxMessagesPerPoll` lớn hơn 1, poller có thể lặp lại thao tác nhận trong cùng lượt, dừng khi đạt giới hạn hoặc nguồn không còn message.

**Phân biệt hai nhịp polling:** poller ở **đầu vào JMS** quyết định khi nào gọi `receive()`; nếu về sau bạn đưa message vào `QueueChannel` và có một polling consumer khác, consumer đó có **lịch lấy khỏi `QueueChannel` riêng**. Không nên nhầm hai tầng này.

## 2. Những thành phần cần hiểu

| Thành phần | Vai trò | Điểm cần chú ý |
|---|---|---|
| JMS broker và `Destination` | Lưu/phân phối message, ví dụ queue `orders.in` | Queue thích hợp cho mô hình một message được một consumer xử lý; topic có ngữ nghĩa subscription khác |
| `ConnectionFactory` | Tạo kết nối JMS đến broker | Dùng provider tương thích và cấu hình kết nối, xác thực, khôi phục kết nối |
| `JmsTemplate` | Cung cấp lệnh nhận JMS đồng bộ | `receiveTimeout` quyết định một lần nhận có chờ message hay không |
| `JmsDestinationPollingSource` | `MessageSource` dùng trong JMS inbound adapter | Lấy JMS message và chuyển thành Spring Message |
| `SourcePollingChannelAdapter` và poller | Kích hoạt `MessageSource.receive()` theo lịch | Quyết định khoảng cách các lượt, số message tối đa mỗi lượt và transaction advice |
| `MessageChannel` | Giao message cho bước tiếp theo | `DirectChannel` giữ lời gọi handler đồng bộ trên cùng luồng; channel bất đồng bộ làm thay đổi ranh giới xử lý |
| Message handler | Validate, transform, ghi dữ liệu hoặc gọi dịch vụ | Cần thiết kế idempotent và xử lý lỗi nhất quán |

Adapter **không trả response về JMS producer**. Khi cần mô hình request/reply, hãy xem JMS inbound/outbound gateway; khi cần gửi message ra broker, hãy dùng JMS outbound channel adapter.

## 3. Cấu hình bằng Spring Integration Java DSL

Ví dụ sau dùng API quen thuộc của Spring Integration 6+ và Jakarta JMS (các phiên bản Spring cũ có thể dùng package `javax.jms`). Dự án cần `spring-integration-jms` và thư viện JMS client/starter phù hợp với broker; ví dụ Maven khi phiên bản được quản lý bởi Spring Boot BOM:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-jms</artifactId>
</dependency>
<!-- Thêm JMS provider / Spring Boot JMS starter phù hợp với broker. -->
~~~

`ConnectionFactory` phải là bean đã kết nối được đến broker. Phần dưới minh họa điểm tích hợp; địa chỉ broker, credentials và việc tạo queue tùy provider nên không được giả định.

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.dsl.Jms;

@Configuration
@EnableIntegration
public class OrderJmsPollingConfig {

    @Bean
    public IntegrationFlow importOrdersFromJms(ConnectionFactory connectionFactory) {
        return IntegrationFlow.from(
                Jms.inboundAdapter(connectionFactory)
                        .destination("orders.in")
                        // Không giữ luồng poller chờ khi queue đang rỗng.
                        .configureJmsTemplate(template ->
                                template.receiveTimeout(-1)),
                endpoint -> endpoint.poller(poller ->
                        poller.fixedDelay(5000)
                                .maxMessagesPerPoll(10)))
                .channel("ordersInput")
                .handle(String.class, (jsonBody, headers) -> {
                    // Demo: thay bằng service validate, nhập DB và xử lý idempotency.
                    System.out.println("Nhận đơn hàng: " + jsonBody);
                    return null; // Handler một chiều, không phát reply.
                })
                .get();
    }
}
~~~

`.destination("orders.in")` chọn queue cần đọc; tên queue phải đúng cấu hình broker. `.channel("ordersInput")` xác định điểm giao Spring Message (DSL có thể tạo một `DirectChannel` khi channel này chưa được khai báo). Handler dùng `String.class` vì ví dụ giả định producer gửi `TextMessage`; nếu producer gửi `BytesMessage` hoặc một định dạng khác, cần điều chỉnh converter và handler.

Để đẩy một message thử vào queue bằng thành phần Spring JMS trong cùng môi trường kết nối:

~~~java
// jmsTemplate là bean đã được cấu hình bằng cùng JMS provider.
jmsTemplate.convertAndSend(
        "orders.in",
        "{\"eventId\":\"evt-1001\",\"orderId\":\"ORD-42\",\"total\":125000}");
~~~

Khi broker hoạt động, message hợp lệ và flow được khởi động, sau lượt poll phù hợp bạn sẽ thấy payload trong log. Đoạn `System.out.println` chỉ dùng để minh họa; triển khai thực tế phải thay bằng xử lý nghiệp vụ và theo dõi lỗi có cấu trúc.

### Cấu hình XML tương đương về lịch polling

Trong ứng dụng dùng XML namespace của Spring Integration, phần quan trọng tương ứng là:

~~~xml
<int:channel id="ordersInput"/>

<int-jms:inbound-channel-adapter
        id="orderJmsInbound"
        connection-factory="jmsConnectionFactory"
        destination-name="orders.in"
        channel="ordersInput">
    <int:poller fixed-delay="5000" max-messages-per-poll="10"/>
</int-jms:inbound-channel-adapter>
~~~

Ví dụ XML là đoạn cấu hình thành phần; ứng dụng còn cần khai báo namespace, bean `jmsConnectionFactory` và consumer của `ordersInput`. Nó cho thấy `<int:poller>` là thành phần thiết yếu để inbound adapter chủ động lấy message theo lịch.

## 4. Chọn lịch polling và giới hạn lượt nhận

| Tham số | Ý nghĩa | Cách cân nhắc |
|---|---|---|
| `fixedDelay(5000)` | Chờ 5 giây **sau khi lượt polling trước hoàn tất** rồi mới bắt đầu lượt tiếp theo | Dễ kiểm soát khoảng nghỉ, phù hợp xử lý theo lô nhỏ |
| `fixedRate(5000)` | Lập lịch theo mốc đều nhau 5 giây; thời gian xử lý có thể ảnh hưởng việc thực thi thực tế | Dùng khi quan tâm nhịp kích hoạt; đừng mặc định các lượt chạy song song |
| `cron(...)` | Chỉ poll vào khung thời gian nhất định | Dùng cho cửa sổ đồng bộ hoặc giờ tải thấp |
| `maxMessagesPerPoll(10)` | Tối đa 10 lần nhận message trong một lượt, hoặc dừng sớm khi nguồn không có message | Điều chỉnh theo backlog, tốc độ handler và yêu cầu nhường tài nguyên |
| `receiveTimeout(-1)` | Với `JmsTemplate`, thực hiện nhận **không chờ** (`receiveNoWait`) | Tránh mỗi lần quét queue rỗng chiếm lâu một luồng của scheduler |
| `receiveTimeout` dương | Có thể chờ tối đa khoảng thời gian cấu hình trong một lần nhận | Cân nhắc tổng thời gian chờ của nhiều lần nhận và số luồng scheduler |

Với `SourcePollingChannelAdapter`, giá trị `maxMessagesPerPoll` mặc định là **1** nếu không cấu hình. Ví dụ `fixedDelay = 5 s` và `maxMessagesPerPoll = 10`, nếu xử lý rất nhanh, một instance có năng lực lấy xấp xỉ tối đa 10 message cho mỗi chu kỳ hơn 5 giây; đó **không phải cam kết throughput** vì thời gian handler, broker, network và transaction có thể làm chu kỳ dài hơn. Khi queue liên tục có dữ liệu, tăng giới hạn có thể giảm backlog nhưng cũng khiến một lượt chiếm luồng lâu hơn.

Một số lưu ý:

- Khi queue rỗng, `receive()` trả về `null` nếu không có message trong thời gian chờ; poller kết thúc lượt hiện tại, chứ không gửi Spring Message có payload `null`.
- Nếu `maxMessagesPerPoll` đặt âm, poller có thể tiếp tục nhận cho đến khi nguồn trả về `null`. Với nguồn luôn có message, lượt polling có thể kéo dài quá mức và làm chậm phản ứng với lệnh dừng; thường nên có giới hạn cụ thể.
- `receiveTimeout(-1)` là lựa chọn chủ động trong ví dụ. Mặc định phụ thuộc cách adapter tạo `JmsTemplate`, cấu hình cache consumer và phiên bản; không suy luận rằng mọi cấu hình đều có hành vi không chờ.
- Tăng số luồng nhận hoặc sử dụng nhiều consumer phải cân nhắc thứ tự xử lý của queue, tính độc lập giữa các message và khả năng chịu tải của downstream.

## 5. Hợp đồng message: từ JMS sang Spring Integration

Khi `extractPayload` được bật (mặc định), converter tạo payload từ phần body của JMS message. Với `SimpleMessageConverter` thường gặp:

| Kiểu JMS đầu vào | Payload Spring Message thường thấy | Cách xử lý |
|---|---|---|
| `TextMessage` | `String` | Parse JSON/XML, validate schema và version |
| `BytesMessage` | `byte[]` | Giải mã theo charset/format đã thỏa thuận |
| `ObjectMessage` | Đối tượng `Serializable` | Cẩn trọng với tương thích class và rủi ro deserialization; ưu tiên định dạng trung lập như JSON |

Các metadata JMS như message ID, correlation ID, type và một số property được ánh xạ vào Spring Message headers tùy `JmsHeaderMapper`. Không nên giả định mọi property hay header đều được giữ nguyên qua mọi adapter và converter; hãy kiểm tra contract thực tế của producer/consumer.

Một hợp đồng đơn hàng hữu dụng có thể là:

~~~json
{
  "eventId": "evt-1001",
  "schemaVersion": 1,
  "orderId": "ORD-42",
  "total": 125000
}
~~~

Handler nên kiểm tra `schemaVersion`, trường bắt buộc và kiểu dữ liệu trước khi ghi DB. Dùng `eventId` làm khóa idempotency ở phía nhận để chống xử lý trùng khi broker redeliver hoặc producer gửi lại. `JMSMessageID` hữu ích để theo dấu một lần gửi; nó không luôn thay thế được ID nghiệp vụ ổn định giữa nhiều lần phát lại logic.

Nếu cần nhận nguyên đối tượng `jakarta.jms.Message`, có thể cấu hình `extractPayload(false)` ở adapter, nhưng khi đó downstream bị ràng buộc vào JMS API và vòng đời/session của provider. Với luồng nghiệp vụ thông thường, chuyển sớm sang payload domain và headers đã chọn giúp giảm coupling.

## 6. Giao dịch, acknowledge và redelivery

Đây là ranh giới dễ sai nhất của JMS polling: **đã lấy được message khỏi broker không đồng nghĩa xử lý nghiệp vụ phía sau đã hoàn tất**.

### Trường hợp không có transaction bao trùm

1. Poller gọi `JmsTemplate.receive()`.
2. JMS session xác nhận/commit việc nhận theo mode và cấu hình template.
3. Adapter gửi Spring Message đến `MessageChannel`.
4. Handler xử lý lỗi hoặc DB không ghi được.

Nếu bước nhận đã được xác nhận trước bước 4, broker có thể không redeliver message dù nghiệp vụ thất bại. Chỉ bật `sessionTransacted = true` cho riêng JMS inbound adapter cũng **chưa đảm bảo** rollback được lỗi ở downstream: theo tài liệu Spring Integration, transaction riêng của lần `receive()` có thể commit trước khi message được gửi vào channel.

### Khi cần rollback theo kết quả handler

Đặt transaction advice trên **poller** bằng `JmsTransactionManager`, để việc nhận và chuyển qua chuỗi xử lý **đồng bộ** có cùng ranh giới transaction JMS. Ví dụ thêm bean:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.connection.JmsTransactionManager;

@Bean
public JmsTransactionManager jmsTransactionManager(ConnectionFactory connectionFactory) {
    return new JmsTransactionManager(connectionFactory);
}
~~~

Sau đó, tại phần cấu hình endpoint của flow ở mục 3, thay poller bằng:

~~~java
endpoint -> endpoint.poller(poller ->
        poller.fixedDelay(5000)
              .maxMessagesPerPoll(10)
              .transactional(jmsTransactionManager))
~~~

Ở đây `jmsTransactionManager` là bean được inject thêm vào phương thức cấu hình flow. Ví dụ này **thay thế** cấu hình poller trước đó, không tạo thêm một flow cùng đọc `orders.in`.

Điều kiện để rollback theo lỗi nghiệp vụ hoạt động như dự kiến:

- Đường xử lý cần giữ **đồng bộ trong phạm vi transaction** (ví dụ `DirectChannel` và handler chạy cùng thread). Nếu đưa message vào `ExecutorChannel` hoặc `QueueChannel`, công việc phía sau có thể diễn ra sau khi transaction poller đã kết thúc.
- Lỗi cần được đưa ra khỏi handler để transaction đánh dấu rollback. Nếu bắt exception rồi chỉ log và trả về bình thường, poller có thể commit.
- Broker/provider phải hỗ trợ session transaction, chính sách redelivery và dead-letter queue phù hợp. Không mặc định một lỗi sẽ được thử lại vô hạn hoặc tự động vào DLQ.
- `JmsTransactionManager` điều phối transaction JMS cục bộ; nó **không** tự động biến cập nhật DB và xác nhận JMS thành một transaction nguyên tử. Khi phối hợp DB và broker, cần idempotency, mô hình xử lý có thể thử lại, hoặc cơ chế transaction phân tán khi thực sự cần và được hỗ trợ.

**Kỳ vọng delivery:** với cấu hình transaction và lỗi đồng bộ được truyền đúng cách, message có thể được phát lại sau rollback. Vì thế nghiệp vụ nên chịu được **at-least-once** và xử lý trùng. Không tuyên bố `exactly-once` chỉ dựa vào một option cấu hình.

## 7. Xử lý lỗi và vận hành

| Tình huống | Biểu hiện | Hướng giải quyết |
|---|---|---|
| Broker mất kết nối | Lỗi JMS hoặc poller không đọc được queue | Theo dõi connection/consumer; cấu hình recovery của provider; cảnh báo khi backlog tăng |
| Queue rỗng | `receive()` không có message | Là trạng thái bình thường; dùng timeout không chờ nếu muốn quét nhẹ |
| JSON sai schema | Converter/handler ném lỗi | Phân loại lỗi dữ liệu, ghi thông tin truy vết an toàn, đưa vào DLQ/quarantine theo policy |
| DB tạm thời không sẵn sàng | Handler ném exception | Rollback nếu transaction bao trùm, retry có giới hạn và backoff hợp lý |
| Message lặp | Cùng `eventId` xử lý nhiều lần | Unique constraint hoặc inbox/idempotency store theo `eventId` |
| Backlog tăng liên tục | Độ trễ queue lớn, thời gian nhập kéo dài | Đo tốc độ vào/ra, tối ưu handler, cân nhắc thay polling bằng message-driven |

Spring Integration có `errorChannel` và cơ chế gửi `ErrorMessage` khi endpoint phát sinh lỗi trong các hoàn cảnh phù hợp. Tuy vậy, **gửi lỗi sang channel không tự đảm bảo rollback, retry hay chuyển sang DLQ**. Cần xác định exception có được ném lại qua transaction advice hay đã bị error handler xử lý, và cấu hình broker redelivery/DLQ rõ ràng.

Trong production, theo dõi tối thiểu: độ sâu queue, tuổi message cũ nhất, số message nhận/xử lý thành công, số xử lý lỗi, số redelivery, thời gian handler, khoảng trễ giữa khi phát và khi xử lý, trạng thái kết nối JMS và trạng thái poller. Log nên có `eventId`, JMS message ID/correlation ID nếu có và tên destination; tránh log toàn bộ payload chứa dữ liệu nhạy cảm.

### Ví dụ thiết kế idempotency

Với message `eventId = evt-1001`, handler có thể:

1. Mở transaction DB và chèn `evt-1001` vào bảng `processed_event` có ràng buộc unique.
2. Nếu khóa đã tồn tại, coi như message đã được xử lý và kết thúc an toàn.
3. Nếu khóa chưa tồn tại, validate và cập nhật đơn hàng trong cùng transaction DB, rồi commit.
4. Chỉ báo thành công cho poller sau khi công việc đồng bộ hoàn tất; nếu lỗi, để exception được xử lý theo chiến lược transaction/retry.

Cách này giảm rủi ro ghi trùng khi một message bị phát lại. Cần thiết kế trạng thái nhập đơn, unique key và thứ tự commit đúng theo nghiệp vụ; không suy ra rằng JDBC và JMS sẽ commit nguyên tử với nhau.

## 8. Khi nào dùng polling, khi nào chuyển sang message-driven?

| Tiêu chí | JMS inbound **polling** | JMS **message-driven** inbound adapter |
|---|---|---|
| Kích hoạt nhận | Scheduler gọi `receive()` theo lịch | JMS listener container nhận và đẩy message khi có |
| Độ trễ khi queue ít message | Có thể bằng khoảng đợi đến lượt poll | Thường thấp hơn, gần thời điểm message đến |
| Điều tiết nhịp | Rõ ràng qua fixed delay/rate, cron, số message/lượt | Điều chỉnh qua listener container, concurrency và tải downstream |
| Mục đích điển hình | Batch, đồng bộ định kỳ, hệ thống chấp nhận trễ | Xử lý sự kiện liên tục, tải vừa/cao, yêu cầu phản hồi nhanh |
| Transaction | Cần xét transaction trên poller và downstream đồng bộ | Listener container thường có hỗ trợ transaction/acknowledgement trực tiếp |

Tài liệu Spring Integration khuyến nghị message-driven cho **phần lớn kịch bản nhận JMS** vì không cần chờ chu kỳ polling. Dùng polling khi chính yêu cầu vận hành đòi hỏi lịch quét, nhịp xử lý hoặc tải định kỳ. Không dùng polling chỉ vì quen với `@Scheduled` nếu SLA lại cần nhận tức thời.

## 9. Thực hành kiểm chứng

Trên môi trường thử nghiệm có broker và queue `orders.in`:

1. **Đường thành công:** gửi một `TextMessage` hợp lệ; xác nhận handler chạy sau lượt poll và nhận đúng payload.
2. **Queue rỗng:** để queue không có message; xác nhận flow không tạo message giả, scheduler vẫn hoạt động.
3. **Giới hạn batch:** gửi hơn 10 message trước một lượt poll; kiểm tra `maxMessagesPerPoll(10)` giới hạn số lần nhận trong lượt đó và backlog còn lại sẽ xử lý ở các lượt kế tiếp.
4. **Lỗi dữ liệu:** gửi JSON sai schema; kiểm tra xử lý lỗi, chính sách DLQ và việc message có được redeliver hay không.
5. **Lỗi tạm thời:** giả lập handler ném exception trong flow có transactional poller; quan sát rollback/redelivery, sau đó xác nhận `eventId` không làm phát sinh bản ghi trùng.
6. **Dừng/khởi động lại:** dừng endpoint hoặc ứng dụng, đưa message mới vào queue, khởi động lại và kiểm tra message tồn đọng được xử lý.

Khi kiểm thử giao dịch và redelivery, hãy dùng broker/provider thực hoặc môi trường container có hành vi tương ứng; mock `JmsTemplate` chỉ kiểm chứng được một phần logic gọi phương thức.

### Câu hỏi tự đánh giá

1. Vì sao `maxMessagesPerPoll = 10` không có nghĩa hệ thống chắc chắn xử lý 10 message mỗi 5 giây?
2. Khi nào `receiveTimeout(-1)` có lợi và vì sao timeout nhận có thể ảnh hưởng số luồng scheduler?
3. Vì sao chỉ bật `sessionTransacted` trên adapter chưa đủ để rollback lỗi ở handler?
4. Điều gì thay đổi nếu thay `DirectChannel` bằng `ExecutorChannel` trong flow có transactional poller?
5. Với nghiệp vụ cần nhận message trong vài chục mili giây, nên chọn polling hay message-driven? Vì sao?

## Tài liệu tham khảo

- [Spring Integration Reference — JMS Support](https://docs.spring.io/spring-integration/reference/jms.html): cấu hình inbound channel adapter, message conversion, transaction và so sánh message-driven.
- [Spring Integration Reference — Channel Adapter](https://docs.spring.io/spring-integration/reference/channel-adapter.html): `SourcePollingChannelAdapter`, `maxMessagesPerPoll` và cơ chế poller.

**Ghi nhớ:** JMS polling inbound adapter là ranh giới chuyển message từ broker sang Spring Integration theo lịch. Độ đúng của luồng phụ thuộc đồng thời vào tần suất nhận, kiểu channel, hợp đồng payload/header, transaction quanh xử lý đồng bộ, chiến lược redelivery và idempotency.
