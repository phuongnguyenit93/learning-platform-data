# JMS message-driven channel adapter

## 1. Vấn đề mà message-driven adapter giải quyết

Giả sử hệ thống bán hàng gửi sự kiện đơn hàng vào JMS queue `orders.in`. Dịch vụ tiếp nhận cần bắt đầu xử lý gần như ngay sau khi message xuất hiện, không muốn tự viết vòng lặp kiểm tra queue theo chu kỳ. **JMS message-driven inbound channel adapter** của Spring Integration là đầu vào phù hợp: một **JMS listener container** lắng nghe destination, nhận message do broker phân phối và đẩy chúng vào `MessageChannel` của Spring Integration.

Trong module **SPRING_INTEGRATION_ADAPTERS**, adapter đóng vai trò kết nối hệ thống ngoài với luồng tích hợp. Adapter inbound mang dữ liệu vào Spring Integration; adapter outbound gửi dữ liệu ra ngoài; gateway hỗ trợ trao đổi hai chiều; `MessageChannel` kết nối các bước xử lý; còn poller chủ động gọi nguồn dữ liệu theo lịch. Bài này tập trung vào **JMS message-driven channel adapter**, tức kiểu JMS inbound hoạt động dựa trên listener, và liên hệ đến hợp đồng message, lỗi và vòng đời kết nối mà module yêu cầu.

**Mục tiêu sau bài học:** bạn có thể cấu hình một listener cho queue JMS, hiểu nơi chuyển đổi `jakarta.jms.Message` thành Spring Message, lựa chọn concurrency hợp lý, giải thích khi nào broker xác nhận message, và xây dựng chiến lược xử lý lỗi/redelivery không làm ghi trùng dữ liệu.

### Khác biệt cốt lõi so với polling

- **Polling inbound adapter:** scheduler kích hoạt một lần `JmsTemplate.receive()` theo `fixedDelay`, `fixedRate` hoặc cron; độ trễ lấy message phụ thuộc lịch poll và thời gian chờ nhận.
- **Message-driven inbound adapter:** `MessageListenerContainer` chủ động quản lý consumer và vòng chờ nhận; khi broker có message, callback của listener chuyển ngay message vào integration flow. **Không cấu hình poller** trên endpoint này.

Message-driven thường là lựa chọn đầu tiên cho luồng nhận sự kiện JMS liên tục hoặc cần độ trễ thấp. Polling vẫn hữu ích khi yêu cầu nghiệp vụ phải giới hạn thời điểm nhận, ví dụ chỉ đồng bộ theo cửa sổ xử lý.

## 2. Kiến trúc và đường đi của một message

~~~mermaid
flowchart LR
    A["Ứng dụng gửi / ERP"] -->|"JMS TextMessage"| B[("JMS broker: orders.in")]
    B -->|"Broker giao cho consumer"| C["Listener container"]
    C -->|"MessageListener callback"| D["JMS message-driven inbound adapter"]
    D -->|"Chuyển đổi / ánh xạ header"| E["Spring Message"]
    E --> F["MessageChannel"]
    F --> G["Validate + xử lý nghiệp vụ"]
    G --> H[("Cơ sở dữ liệu")]
~~~

Các lớp trách nhiệm:

| Thành phần | Chịu trách nhiệm | Điểm cần nhớ |
|---|---|---|
| JMS broker | Lưu và phân phối message theo ngữ nghĩa queue/topic | Cần thiết lập policy retry và dead-letter tại broker/provider khi muốn dùng |
| `ConnectionFactory` | Cấp JMS connection/session | Có thể được Spring Boot tạo từ starter của nhà cung cấp JMS |
| `DefaultMessageListenerContainer` | Duy trì JMS consumer, vòng nhận, số consumer đồng thời, recovery và transaction của listener | Spring JMS cung cấp; Spring Integration dùng container này hoặc container thích hợp khác |
| JMS message-driven inbound adapter | Nhận callback từ container, chuyển JMS message thành Spring Message và gửi ra channel | Đây là điểm bắt đầu integration flow, không có poller |
| `MessageConverter` và header mapper | Chuyển payload, sao chép metadata đã hỗ trợ | Hợp đồng message cần được thỏa thuận với producer |
| `MessageChannel` | Giao Spring Message cho consumer kế tiếp | Channel đồng bộ hay bất đồng bộ ảnh hưởng mạnh đến xác nhận JMS |
| Message handler | Validate, lưu dữ liệu, gọi hệ thống khác | Phải xử lý trùng lặp và ném lỗi đúng lúc nếu muốn rollback |

Trình tự thường gặp với **queue**:

1. Khi endpoint khởi động, listener container tạo JMS consumer trên `orders.in` và quản lý vòng đời kết nối.
2. Broker giao một message cho consumer. Listener container gọi mã xử lý đã đăng ký trong cùng luồng nhận.
3. Adapter đọc nội dung, chuyển sang Spring Message (payload và headers), sau đó gửi tới `MessageChannel`.
4. Một hoặc nhiều handler xử lý message. Trong đường xử lý đồng bộ, lỗi có thể truyền ngược về listener container.
5. JMS session xác nhận hoặc rollback việc nhận theo acknowledge mode và cấu hình transaction. Chính sách broker quyết định xử lý message sau rollback.

**Phạm vi:** đây là **inbound channel adapter một chiều**. Nó không tự tạo JMS response cho producer. Nếu tác vụ cần **request/reply** với `JMSReplyTo`, hãy dùng JMS inbound gateway; nếu cần ghi message lên destination, hãy dùng outbound adapter.

## 3. Tạo một integration flow message-driven bằng Java DSL

Ví dụ dùng Spring Integration 6+ (JMS API dùng package `jakarta.jms`); với dự án cũ hơn, một số import có thể thuộc `javax.jms`. Thêm Spring Integration JMS và JMS client tương ứng với broker. Dưới đây là phần dependency Maven tối thiểu về phía Spring Integration trong dự án Spring Boot có BOM quản lý version:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-jms</artifactId>
</dependency>
<!-- Bổ sung JMS provider hoặc JMS starter tương ứng broker đang dùng. -->
~~~

Điều kiện tiên quyết: ứng dụng có bean `ConnectionFactory` kết nối được đến broker, và broker có queue `orders.in`. Không giả định broker tự tạo queue hoặc có địa chỉ, mật khẩu mặc định.

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.dsl.Jms;

@Configuration
@EnableIntegration
public class OrderJmsInboundConfiguration {

    @Bean
    public IntegrationFlow orderJmsInboundFlow(
            ConnectionFactory connectionFactory,
            OrderImportService orderImportService) {

        return IntegrationFlow
                .from(Jms.messageDrivenChannelAdapter(connectionFactory)
                        .destination("orders.in"))
                .handle(String.class, (jsonBody, headers) -> {
                    // Hàm này xử lý đồng bộ; nếu thất bại, service phải báo lỗi.
                    orderImportService.importOrder(jsonBody);
                    return null; // Adapter một chiều, không tạo message phản hồi.
                })
                .get();
    }
}
~~~

Trong ví dụ, `OrderImportService` là bean nghiệp vụ do ứng dụng tự xây dựng; interface tối giản có thể là:

~~~java
public interface OrderImportService {
    void importOrder(String jsonBody);
}
~~~

Flow này không dùng `@Scheduled`, `PollerMetadata` hay `maxMessagesPerPoll`. `Jms.messageDrivenChannelAdapter(connectionFactory)` tạo điểm vào từ JMS listener container; `.destination("orders.in")` chọn destination. Lệnh `.handle(String.class, ...)` giả định producer gửi `TextMessage` được converter biến thành `String`. Handler trả `null` vì việc nhập đơn hàng là tác vụ một chiều.

**Chú ý khi chạy:** `OrderImportService` phải có implementation, `ConnectionFactory` phải được cấu hình bằng provider thực và queue phải sẵn sàng. Nếu nhận `BytesMessage`, kiểu payload hoặc converter phải thay đổi; nếu lỗi xảy ra ở converter trước handler, chính sách xử lý lỗi cần tính đến giai đoạn đó.

### Minh họa producer gửi một sự kiện

~~~java
import org.springframework.jms.core.JmsTemplate;

// Một service khác đã được inject JmsTemplate.
jmsTemplate.convertAndSend(
        "orders.in",
        "{\"eventId\":\"evt-2001\",\"schemaVersion\":1,"
        + "\"orderId\":\"ORD-82\",\"amount\":250000}");
~~~

Khi cả broker và consumer hoạt động, listener nhận message mà không cần đợi một chu kỳ 5 hoặc 10 giây. **Không có bảo đảm tuyệt đối về độ trễ**: network, broker, listener concurrency, thời gian handler và tải hệ thống đều có thể ảnh hưởng.

### XML namespace cho dự án cấu hình XML

~~~xml
<int:channel id="ordersInput"/>

<int-jms:message-driven-channel-adapter
        id="ordersInbound"
        connection-factory="jmsConnectionFactory"
        destination-name="orders.in"
        channel="ordersInput"/>

<int:service-activator
        input-channel="ordersInput"
        ref="orderMessageHandler"
        method="handle"/>
~~~

Đây là fragment XML: ứng dụng cần khai báo namespace `int`, `int-jms`, bean `jmsConnectionFactory` và bean `orderMessageHandler`. Điểm khác XML của polling inbound là **`message-driven-channel-adapter` không có `<int:poller>`**.

## 4. Listener container, số consumer và vòng đời kết nối

Spring Integration sử dụng cơ chế listener của Spring JMS; `DefaultMessageListenerContainer` (DMLC) thường được dùng vì hỗ trợ cấu hình concurrency, reconnect/recovery và transaction linh hoạt. Với lưu lượng tăng, bạn không cần tạo nhiều flow giống nhau chỉ để mở thêm consumer: hãy điều chỉnh cấu hình listener container phù hợp.

| Thiết lập của listener container | Tác dụng | Lưu ý vận hành |
|---|---|---|
| `destinationName` hoặc `destination` | Chỉ rõ queue/topic nhận | Phân biệt queue và topic, tên phải đúng broker |
| `concurrentConsumers` | Số consumer tối thiểu duy trì | Tăng số consumer thường tăng throughput cho queue nếu downstream xử lý song song được |
| `maxConcurrentConsumers` | Mức concurrency tối đa khi container hỗ trợ tăng/giảm consumer động | Đặt dựa trên broker, CPU, pool DB và yêu cầu thứ tự |
| `sessionTransacted` | Yêu cầu JMS session transaction | Giúp rollback/redelivery khi lỗi truyền ra khỏi listener |
| `transactionManager` | Gắn manager nếu yêu cầu transaction được quản lý bên ngoài container | Xác định rõ transaction JMS riêng hay phối hợp nhiều tài nguyên |
| `recoveryInterval` / `BackOff` | Điều khiển thời điểm thử khôi phục kết nối sau sự cố | Cần monitoring và backoff thích hợp khi broker mất kết nối |
| `pubSubDomain` | Chọn ngữ nghĩa topic thay vì queue | Với topic, phải quyết định durable/shared subscription theo nhu cầu |

Ví dụ giá trị thiết kế cho ứng dụng nhập đơn: bắt đầu với **một consumer** để đơn giản hóa việc theo dõi thứ tự, sau đó tăng thành 2–4 consumer nếu các đơn độc lập và DB chịu được. Khi có nhiều consumer, **thứ tự xử lý hoàn tất không được bảo đảm như lúc chỉ có một consumer**; nếu hệ thống phải xử lý các sự kiện của cùng một đơn đúng thứ tự, cần chiến lược ordering/partition hoặc grouping được broker hỗ trợ.

Không nhầm ba khái niệm:

- **Consumer concurrency:** số JMS consumer mà listener container sử dụng để nhận message song song.
- **Channel executor:** số luồng xử lý downstream sau `ExecutorChannel`; có thể tách thời điểm xác nhận JMS khỏi thời điểm xử lý nghiệp vụ.
- **Số instance triển khai:** tổng số consumer trên các instance cùng đọc queue. Thêm instance có thể tăng throughput nhưng cũng làm khó bảo toàn thứ tự.

### Queue và topic không có ngữ nghĩa giống nhau

Với **queue**, mỗi message thường được giao cho **một** trong các competing consumers, phù hợp để phân phối công việc. Với **topic**, một message có thể được phân phối tới các subscription khác nhau; non-durable subscriber có thể bỏ lỡ message khi offline, còn durable subscription duy trì quyền nhận phù hợp với điều kiện cấu hình của broker/provider. Cần cấu hình `pubSubDomain` và các thuộc tính client/subscription tương ứng thay vì chỉ thay tên destination.

### Khởi động, dừng và khôi phục

Khi ứng dụng khởi động, Spring quản lý start của endpoint và listener container; khi shutdown, container dừng nhận thêm message và xử lý việc dừng consumer đang hoạt động theo cấu hình. Nếu ứng dụng crash giữa chừng, việc nhận có được broker phát lại hay không phụ thuộc transaction, acknowledge và policy của broker. Đừng xem restart là biện pháp đảm bảo mọi message tự động được xử lý đúng một lần.

Khi broker tạm ngắt kết nối, DMLC có cơ chế thử recovery, nhưng cần kiểm tra trạng thái thực tế, độ sâu queue và số lần recovery thất bại. Bật health check/metrics bên cạnh log lỗi, tránh dựa vào việc tiến trình Java còn sống để kết luận listener vẫn nhận được message.

## 5. Hợp đồng message: payload và JMS headers

JMS định nghĩa các loại message như `TextMessage`, `BytesMessage`, `MapMessage` và `ObjectMessage`. Spring JMS `MessageConverter` chuyển phần body sang đối tượng Java; Spring Integration tạo Spring Message để handler dùng. Với converter mặc định thường gặp:

| JMS message | Payload thường nhận | Khuyến nghị |
|---|---|---|
| `TextMessage` | `String` | Thống nhất encoding và JSON schema/version |
| `BytesMessage` | `byte[]` | Ghi rõ định dạng binary, giới hạn kích thước |
| `MapMessage` | `Map` hoặc biểu diễn phù hợp converter | Giữ nhất quán key/value, hạn chế phụ thuộc provider |
| `ObjectMessage` | Đối tượng Java serialize | Cẩn trọng class compatibility và deserialization; ưu tiên hợp đồng độc lập ngôn ngữ |

Ví dụ sự kiện:

~~~json
{
  "eventId": "evt-2001",
  "schemaVersion": 1,
  "orderId": "ORD-82",
  "amount": 250000
}
~~~

Các trường `eventId`, `schemaVersion` và `orderId` là **hợp đồng nghiệp vụ trong payload**; không phải trường tự động do JMS tạo. `eventId` cần ổn định khi cùng một sự kiện được gửi lại. Handler validate đủ trường, kiểm tra version và dùng `eventId` làm khóa idempotency để tránh ghi trùng khi redelivery.

Metadata chuẩn của JMS gồm `JMSMessageID`, `JMSCorrelationID`, `JMSType`, `JMSRedelivered`, `JMSPriority`, `JMSExpiration`... Spring Integration sử dụng header mapper để ánh xạ một phần thông tin này vào Spring Message headers. Không giả định tên hoặc sự hiện diện của **tất cả** header đều giống nhau giữa các phiên bản, converter và cấu hình; kiểm thử các header thật sự được dùng trong flow.

**Hai kiểu ID khác nhau:** JMS message ID mô tả lần gửi/bản ghi do provider cấp; `eventId` mô tả sự kiện nghiệp vụ. Producer có thể phát lại cùng một sự kiện thành một JMS message mới mang ID khác, vì vậy deduplication nên dựa vào `eventId` hoặc khóa nghiệp vụ có ý nghĩa.

Nếu cần thao tác trực tiếp với JMS API, adapter có tùy chọn giữ nguyên JMS message thay vì chỉ trích payload. Cách này tăng coupling với broker/JMS session và thường không cần trong domain handler; ưu tiên chuyển sớm sang kiểu dữ liệu nghiệp vụ đã kiểm tra.

## 6. Acknowledge, transaction và redelivery

Một lỗi phổ biến là hiểu rằng **listener đã nhận message** tương đương **đơn hàng đã được ghi thành công**. Thời điểm broker xem message đã được xác nhận phụ thuộc cách Spring JMS listener container được cấu hình.

### Những chế độ quan trọng

| Chế độ | Điều cần hiểu |
|---|---|
| `AUTO_ACKNOWLEDGE` | Với `DefaultMessageListenerContainer`, xác nhận có thể diễn ra trước lúc listener chạy; exception trong handler không đảm bảo broker redeliver |
| `CLIENT_ACKNOWLEDGE` | Phụ thuộc container và cách gọi acknowledge; không nên giả định lỗi nghiệp vụ luôn dẫn đến redelivery |
| JMS session `transacted` | Container commit sau callback thành công và rollback khi lỗi được truyền ra ngoài trong ranh giới transaction |
| Transaction manager ngoài | Có thể quản lý transaction theo cấu hình; cần phân biệt local JMS transaction với transaction DB |

Muốn broker có cơ hội phát lại khi handler đồng bộ thất bại, cấu hình **`sessionTransacted = true`** cho listener container là một điểm khởi đầu thường dùng. Trong Java, `DefaultMessageListenerContainer` cung cấp setter `setSessionTransacted(true)`; khi cấu hình qua DSL/XML, ánh xạ tùy chọn transaction tương ứng vào listener container của adapter.

Không nên đặt logic retry trong một vòng lặp vô hạn bên trong listener. Một message lỗi vĩnh viễn (ví dụ sai schema) có thể bị redeliver liên tục, gây nghẽn queue. Chọn chính sách broker retry có giới hạn, backoff và dead-letter queue (DLQ), đồng thời phân biệt lỗi nghiệp vụ vĩnh viễn với lỗi phụ thuộc tạm thời như DB timeout.

### Sơ đồ quyết định khi xử lý lỗi

~~~mermaid
flowchart TD
    A["Listener nhận JMS message"] --> B["Chuyển đổi và validate"]
    B --> C{"Xử lý thành công?"}
    C -->|Có| D["Commit / acknowledge theo cấu hình"]
    C -->|Không| E{"Exception có đến listener container?"}
    E -->|Có, session transacted| F["Rollback JMS session"]
    F --> G["Broker redelivery / DLQ theo policy"]
    E -->|Không, đã bị xử lý| H["Container có thể coi callback thành công"]
    H --> I["Có nguy cơ commit dù nghiệp vụ lỗi"]
~~~

**Ranh giới đồng bộ rất quan trọng.** Nếu adapter gửi vào `DirectChannel` và handler tiếp theo chạy trong cùng thread, exception có cơ hội truyền ngược về listener container. Nếu chèn `ExecutorChannel`, `QueueChannel` hoặc một lời gọi bất đồng bộ, listener có thể kết thúc và xác nhận JMS trước khi xử lý ở thread/consumer khác hoàn tất. Khi đó rollback JMS của message ban đầu không còn bao trùm kết quả cuối của handler downstream.

### Vì sao transaction JMS không đồng nghĩa transaction DB?

Giả sử service ghi đơn hàng vào PostgreSQL rồi listener cố commit JMS transaction. Nếu database commit thành công nhưng JMS commit lỗi, broker có thể giao lại cùng message. Ngược lại, nếu listener đã xác nhận và downstream bất đồng bộ thất bại, đơn hàng có thể bị mất khỏi luồng xử lý. `JmsTransactionManager` quản lý giao dịch JMS cục bộ; bản thân nó **không bảo đảm atomic commit giữa JMS và DB**.

Trong đa số ứng dụng tích hợp, cách thực dụng là thiết kế **at-least-once + idempotency**:

1. Producer cấp `eventId` ổn định.
2. Handler mở transaction DB; ghi `eventId` vào bảng inbox/`processed_event` có unique constraint.
3. Trong **cùng transaction DB**, cập nhật đơn hàng và đánh dấu sự kiện đã xử lý.
4. Nếu `eventId` đã tồn tại, handler xem như sự kiện đã được xử lý và trả thành công mà không ghi lặp.
5. Nếu lỗi tạm thời, ném exception để listener container/JMS transaction xử lý rollback theo policy.

Đối với hệ thống yêu cầu ràng buộc nguyên tử giữa nhiều resource, phải đánh giá kiến trúc outbox/inbox, transaction phân tán nếu thực sự có hỗ trợ, và đánh đổi vận hành. Không tuyên bố `exactly-once` chỉ vì đã bật `sessionTransacted`.

## 7. `errorChannel` và cách giữ đúng ngữ nghĩa lỗi

JMS message-driven inbound adapter có khả năng đưa các lỗi qua cơ chế xử lý `ErrorMessage`/`errorChannel` của Spring Integration theo cấu hình. Việc gửi exception vào error channel hữu ích cho log, cảnh báo và phân loại lỗi. Tuy nhiên, **error flow hấp thụ exception có thể làm JMS listener container thấy callback thành công**. Trong chế độ transacted, điều này có thể dẫn đến commit thay vì rollback.

Vì vậy cần quyết định rõ một trong các chính sách:

- **Lỗi tạm thời, muốn broker redeliver:** exception phải đi tới ranh giới transaction của listener. Nếu error handler xử lý lỗi, cần bảo đảm nó **ném lại** exception khi muốn rollback.
- **Lỗi vĩnh viễn và chấp nhận bỏ qua sau khi lưu quarantine:** ghi an toàn vào kho lỗi/DLQ theo chiến lược đã thiết kế, rồi kết thúc callback; xác định rõ khi nào có thể acknowledge.
- **Lỗi downstream bất đồng bộ:** đưa vào một hàng đợi công việc có xác nhận độc lập hoặc cơ chế retry riêng; không trông đợi transaction của JMS inbound bảo vệ công việc đã tách thread.

Chuyển một `ErrorMessage` vào `errorChannel` **không tự động** thực hiện retry, rollback hay đưa message vào DLQ. Muốn xác định hành vi, cần kiểm tra cấu hình adapter, error handler, exception được propagate, chế độ transaction của listener container và broker policy.

### Một số lỗi vận hành thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xác minh |
|---|---|---|
| Queue có message nhưng handler không chạy | Kết nối lỗi, destination sai, listener chưa start, converter ném exception | Kiểm tra trạng thái container, destination, log, metrics và error channel |
| Message biến mất dù handler báo lỗi | AUTO_ACK hoặc error handler nuốt exception, xử lý async | Kiểm tra transaction/acknowledge và ranh giới đồng bộ |
| Message xử lý lặp | Redelivery sau rollback, producer gửi lại hoặc crash giữa DB/JMS commit | Theo dõi `eventId` và cờ JMS redelivered nếu có |
| Một message xấu gây nghẽn | Redelivery không giới hạn | Tạo policy retry/DLQ và xử lý poison message |
| Đơn bị xử lý sai thứ tự | Nhiều consumer hoặc downstream async | Kiểm tra concurrency, ordering và partition/grouping |
| Broker hồi phục nhưng tiêu thụ chậm | Recovery thất bại lặp lại, giới hạn container hoặc downstream nghẽn | Theo dõi consumer active, backlog, thread pool, pool DB |

Hãy log tối thiểu: tên destination, `eventId`, JMS message ID/correlation ID (nếu có), loại lỗi, số lần thử lại hoặc dấu hiệu redelivery. Tránh log toàn bộ payload nhạy cảm. Các chỉ số cần quan sát gồm **độ sâu queue**, tuổi message cũ nhất, số consumer đang hoạt động, throughput xử lý, tỉ lệ lỗi, số redelivery/DLQ và độ trễ xử lý.

## 8. Khi nào dùng adapter, gateway hoặc polling?

| Nhu cầu | Thành phần phù hợp | Lý do |
|---|---|---|
| Nhận JMS event liên tục với độ trễ thấp | **JMS message-driven inbound adapter** | Listener luôn sẵn sàng nhận; không cần lịch poll |
| Chỉ kiểm tra queue ở thời điểm/batch định trước | JMS polling inbound adapter | Poller kiểm soát lượt lấy message |
| Nhận JMS request và gửi JMS reply theo correlation | JMS inbound gateway | Hỗ trợ request/reply |
| Đẩy Spring Message ra JMS queue/topic | JMS outbound channel adapter | Hướng dữ liệu từ Spring Integration sang broker |
| Muốn xử lý cùng một sự kiện ở nhiều dịch vụ độc lập | Topic cùng subscriptions phù hợp | Mỗi subscription nhận bản phân phối của topic theo cấu hình |

Một ứng dụng có thể dùng **nhiều adapter** trong cùng hệ thống: nhận đơn qua message-driven JMS inbound, lưu DB, gửi thông báo sang Kafka/AMQP bằng outbound adapter, cập nhật file hoặc gọi HTTP gateway. Tuy nhiên mỗi ranh giới kết nối có timeout, transaction, retry và hợp đồng message riêng; không có một transaction JMS tự bảo vệ mọi bước xuyên các hệ thống.

## 9. Bài thực hành: tiếp nhận đơn hàng qua queue

**Bối cảnh:** broker có queue `orders.in`, ứng dụng nhận JSON đơn hàng; mỗi đơn chỉ được lưu một lần theo `eventId`. Bạn có thể thực hiện theo thứ tự:

1. **Thiết lập:** cấu hình provider cho `ConnectionFactory`, tạo queue `orders.in`, đăng ký flow message-driven và implement `OrderImportService`.
2. **Happy path:** producer gửi payload hợp lệ `evt-2001`; quan sát listener gọi handler mà không đợi poll, và DB xuất hiện một bản ghi đơn hàng.
3. **Idempotency:** gửi lại cùng `eventId` trong một JMS message khác; xác nhận DB vẫn chỉ có một tác động nghiệp vụ.
4. **Lỗi schema:** gửi JSON thiếu `orderId`; xác nhận flow ghi nhận lỗi và áp dụng chính sách retry/quarantine/DLQ được thiết kế.
5. **Lỗi DB:** giả lập service ném exception khi DB timeout; kiểm tra redelivery với listener transacted và exception truyền ra tới container.
6. **Đường async:** thay channel đồng bộ bằng `ExecutorChannel` ở môi trường thử, lặp lại lỗi DB và giải thích vì sao rollback JMS gốc không còn bảo đảm.
7. **Concurrency:** gửi 100 message thuộc nhiều đơn độc lập; thay đổi consumer concurrency từ 1 lên 3, đo throughput và kiểm tra thứ tự hoàn tất.
8. **Recovery:** tạm dừng broker rồi khởi động lại; quan sát trạng thái listener và backlog, không kết luận thành công chỉ từ việc ứng dụng còn chạy.

Để thử luồng từ broker đến Spring Integration, nên dùng broker/provider thật hoặc môi trường container tương ứng. Unit test chỉ mock handler sẽ không chứng minh được hành vi acknowledge, rollback, redelivery, durable subscription hay recovery.

### Câu hỏi tự kiểm tra

1. Trong JMS message-driven inbound adapter, ai kích hoạt việc nhận message? Vì sao không cần `PollerMetadata`?
2. `DefaultMessageListenerContainer` quản lý những tài nguyên nào, và tại sao tăng `concurrentConsumers` có thể thay đổi thứ tự xử lý?
3. Vì sao `AUTO_ACKNOWLEDGE` trên DMLC không đủ để bảo đảm redelivery khi handler ném exception?
4. Điều gì xảy ra với transaction JMS nếu `errorChannel` xử lý và nuốt exception?
5. Vì sao cần khóa `eventId` ngay cả khi đã cấu hình listener `sessionTransacted`?
6. Nên chọn JMS inbound gateway hay inbound channel adapter nếu producer yêu cầu nhận một JMS reply?

## 10. Tài liệu tham khảo

- [Spring Integration Reference — JMS Support](https://docs.spring.io/spring-integration/reference/jms.html): message-driven channel adapter, gateway, converter và cách dùng transaction.
- [Spring Framework Reference — JMS Message Listener Containers](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): vòng đời, acknowledge, transaction và listener container.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): `DirectChannel`, `ExecutorChannel`, `QueueChannel` và tác động tới xử lý đồng bộ/bất đồng bộ.

**Ghi nhớ:** message-driven inbound adapter giúp broker chủ động đưa JMS message vào Spring Integration qua listener container. Để xử lý an toàn trong production, cần xác định rõ loại destination, hợp đồng payload, concurrency, ranh giới đồng bộ, acknowledge/transaction, việc propagate lỗi và idempotency ở tầng nghiệp vụ.
