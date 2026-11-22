# Spring Integration và các mẫu tích hợp dựa trên Message

> Phạm vi: Spring Integration 7.1.1, Spring Messaging và Java 17+. Bài học giải thích cách ghép các thành phần message thành một luồng tích hợp, vai trò của channel, endpoint, adapter và gateway, cùng các Enterprise Integration Patterns (EIP) thường dùng trong ứng dụng Spring.

## 1. Spring Integration giải quyết vấn đề gì?

Một ứng dụng doanh nghiệp thường phải trao đổi dữ liệu với nhiều hệ thống: REST API, file server, cơ sở dữ liệu, email, JMS, RabbitMQ, Kafka, MQTT hoặc một dịch vụ nội bộ. Nếu mỗi nơi gọi trực tiếp nơi tiếp theo, logic nghiệp vụ sẽ bị trộn với giao thức, retry, chuyển đổi dữ liệu, định tuyến và quản lý lỗi.

Spring Integration cung cấp một mô hình messaging để kết nối các hệ thống đó bằng những thành phần nhỏ, có thể ghép lại thành message flow. Thành phần gửi tạo message và đưa vào channel; endpoint nhận message rồi xử lý, chuyển đổi hoặc định tuyến; adapter và gateway nối flow với hệ thống bên ngoài.

Thư viện hiện thực nhiều Enterprise Integration Patterns. Thay vì tự viết vòng lặp polling, queue, router, splitter hay cơ chế correlation cho từng dự án, ta cấu hình các thành phần đã có sẵn và tập trung vào quy tắc nghiệp vụ.

Một flow đơn giản có thể là:

~~~text
File/HTTP/Broker
      |
Inbound Adapter hoặc Gateway
      |
   MessageChannel
      |
  Transformer
      |
    Filter
      |
    Router
   /      \
Service   Service
Activator Activator
   \      /
   Reply/Outbound Gateway
      |
External system hoặc caller
~~~

Spring Integration không phải là message broker. Các channel như DirectChannel hoặc QueueChannel thường nằm trong bộ nhớ của ứng dụng. Khi cần giao tiếp bền vững giữa các process, dùng adapter/gateway kết nối broker hoặc hệ thống lưu trữ phù hợp. Channel trong ứng dụng là điểm nối giữa các thành phần; broker là hạ tầng vận chuyển và lưu trữ message ở bên ngoài.

## 2. Ba abstraction cốt lõi: Message, MessageChannel và MessageHandler

### 2.1. Message là đơn vị dữ liệu được truyền

Spring Messaging định nghĩa interface `Message<T>` với hai phần:

- `payload`: nội dung chính, thường là DTO, record, chuỗi, byte array hoặc đối tượng miền nghiệp vụ.
- `headers`: metadata như ID, timestamp, content type, correlation ID, reply channel, error channel hoặc thông tin định tuyến.

Có thể tạo message bằng `MessageBuilder`:

~~~java
Message<OrderCreated> message = MessageBuilder
    .withPayload(new OrderCreated("ORD-1001", 125000))
    .setHeader("eventType", "order.created")
    .setHeader("tenantId", "tenant-42")
    .build();
~~~

Header là metadata, không nên dùng để thay thế dữ liệu nghiệp vụ mà consumer cần lưu trữ hoặc diễn giải lâu dài. Một số header có ý nghĩa nội bộ trong Spring, ví dụ `replyChannel` và `errorChannel`; adapter có thể ánh xạ hoặc loại bỏ header khi chuyển qua giao thức bên ngoài.

`MessageHeaders` là cấu trúc bất biến sau khi message được tạo. Payload không tự động bất biến: nếu payload là object mutable và nhiều consumer dùng chung object đó, việc sửa nội dung có thể gây side effect khó đoán. DTO/record bất biến thường phù hợp hơn.

Spring có thể tự sinh `id` và `timestamp` cho mỗi message instance. Đây là metadata của instance Spring Message, không nhất thiết là ID sự kiện bền vững của nghiệp vụ. Nếu cần chống xử lý trùng qua retry hoặc broker redelivery, hãy đặt business event ID riêng trong payload hoặc header đã được quy định và bảo đảm nó được giữ nguyên qua các lần gửi lại.

### 2.2. MessageChannel tách producer khỏi consumer

`MessageChannel` là điểm gửi message. Producer chỉ cần biết channel đích, không cần biết handler cụ thể nào sẽ nhận message. Consumer đăng ký với channel và có thể được thay đổi mà không buộc producer thay đổi.

Phương thức cơ bản là `send(Message<?>)`, trả về boolean cho biết message đã được chấp nhận gửi hay không. Một số channel hỗ trợ `send(message, timeout)` để giới hạn thời gian chờ khi channel bị đầy hoặc cần đồng bộ với consumer.

Channel không nhất thiết là queue. Một channel có thể dispatch đồng bộ đến subscriber, broadcast đến nhiều subscriber, hoặc lưu message để consumer polling sau.

### 2.3. MessageHandler thực hiện công việc

`MessageHandler` nhận message và thực hiện xử lý. Trong ứng dụng, ta thường không cần tự triển khai interface này. Service activator, transformer, filter, router, splitter và aggregator là các endpoint/handler chuyên biệt cho từng mục đích.

Một endpoint gắn handler với input channel và có thể kết nối output channel. Endpoint còn quản lý vòng đời, poller, interceptor và advice theo cấu hình.

Phân biệt ba vai trò:

| Thành phần | Trách nhiệm |
|---|---|
| Message | Đóng gói payload và headers |
| MessageChannel | Chuyển message từ producer tới consumer |
| Endpoint/MessageHandler | Nhận message và xử lý hoặc chuyển tiếp |

## 3. Các loại MessageChannel và cách chọn

Lựa chọn channel ảnh hưởng đến thứ tự, threading, buffering, backpressure và khả năng mất message.

| Channel | Cách hoạt động | Khi nên dùng |
|---|---|---|
| `DirectChannel` | Point-to-point; dispatch đồng bộ trên thread gửi | Flow nội bộ cần đơn giản, phản hồi ngay và có thể dùng cùng transaction thread |
| `PublishSubscribeChannel` | Gửi một message đến mọi subscriber | Fan-out, cập nhật nhiều projection hoặc nhiều listener |
| `QueueChannel` | Lưu message trong queue; consumer gọi `receive` hoặc dùng poller | Tách thời điểm gửi và nhận, buffering trong bộ nhớ |
| `PriorityChannel` | Pollable queue có thứ tự ưu tiên | Xử lý message theo priority header |
| `RendezvousChannel` | Handoff trực tiếp giữa sender và receiver, sender có thể phải chờ | Đồng bộ producer-consumer với cơ chế bắt tay |
| `ExecutorChannel` | Dispatch qua executor, thường sang thread khác | Tách xử lý khỏi thread gửi và tăng concurrency |
| `FluxMessageChannel` | Channel dựa trên Reactive Streams | Flow cần tích hợp với Publisher/Subscriber reactive |

`DirectChannel` là lựa chọn mặc định thường gặp trong flow đồng bộ. Nếu có nhiều subscriber, nó chọn một subscriber để xử lý message; nó không broadcast như `PublishSubscribeChannel`.

`PublishSubscribeChannel` có ngữ nghĩa fan-out. Nếu một subscriber lỗi, cần xác định chính sách xử lý lỗi và việc gửi tới các subscriber còn lại theo cấu hình dispatcher. Không giả định rằng publish-subscribe tự tạo bản sao bền vững cho từng consumer.

`QueueChannel` tách sender và receiver theo thời gian, nhưng queue trong bộ nhớ không phải durable queue. Nếu process dừng, message chưa được xử lý có thể mất. Cần capacity, timeout, poller và chiến lược overflow phù hợp.

`ExecutorChannel` tạo ranh giới bất đồng bộ. Vì xử lý có thể chạy trên thread khác, không nên giả định transaction hoặc ThreadLocal từ thread gửi tự động được truyền sang thread xử lý. Cần quản lý executor, queue và rejection policy; không để backlog tăng vô hạn.

### 3.1. SubscribableChannel và PollableChannel

Hai nhóm interface giúp nhận biết cách consumer lấy message:

- `SubscribableChannel`: consumer đăng ký handler; channel đẩy message đến subscriber khi có message.
- `PollableChannel`: consumer chủ động gọi `receive()`; có thể dùng poller để lấy message theo lịch.

`DirectChannel`, `PublishSubscribeChannel` và `ExecutorChannel` thuộc nhóm subscribable. `QueueChannel`, `PriorityChannel` và `RendezvousChannel` thuộc nhóm pollable.

Không đặt poller lên channel đẩy message như `DirectChannel`. Poller phù hợp với `MessageSource` hoặc `PollableChannel`, ví dụ kiểm tra thư mục theo chu kỳ hoặc đọc queue.

## 4. Endpoint, Channel Adapter và Gateway

### 4.1. Message endpoint

Endpoint là thành phần nối logic xử lý với channel. Nó có thể gọi service, chuyển đổi payload, lọc message, định tuyến, chia message hoặc ghép kết quả.

Các annotation thường gặp:

- `@ServiceActivator`: gọi method xử lý nghiệp vụ.
- `@Transformer`: biến đổi payload hoặc message.
- `@Filter`: quyết định message có được đi tiếp hay không.
- `@Router`: chọn channel đích.
- `@Splitter`: chia một message thành nhiều message con.
- `@Aggregator`: gom một nhóm message thành kết quả.
- `@BridgeFrom` / `@BridgeTo`: nối channel trong các cấu hình phù hợp.

Các endpoint này có thể được khai báo bằng annotation, XML hoặc Java DSL.

### 4.2. Channel adapter: tích hợp một chiều

Channel adapter kết nối một nguồn/đích bên ngoài với channel trong ứng dụng theo hướng một chiều:

- Inbound channel adapter đọc từ bên ngoài rồi gửi message vào flow.
- Outbound channel adapter nhận message từ flow rồi gửi ra bên ngoài.

Ví dụ: inbound file adapter đọc file CSV và phát message; outbound file adapter ghi payload thành file. Adapter không yêu cầu một reply nghiệp vụ cho từng message.

### 4.3. Gateway: request-reply

Gateway phù hợp khi caller cần gửi request và chờ reply. Gateway che giấu chi tiết messaging, cho phép ứng dụng gọi một interface Java như gọi service bình thường.

Một messaging gateway có thể khai báo bằng `@MessagingGateway`, với các method gắn `@Gateway` để chỉ định request channel, reply channel hoặc timeout. Outbound gateway kết nối flow với hệ thống bên ngoài theo mô hình request/reply; inbound gateway nhận request từ hệ thống bên ngoài rồi gửi reply lại.

Không nhầm gateway với adapter: adapter chủ yếu gửi/nhận một chiều, còn gateway có hợp đồng request/reply. Gateway cũng không tự bảo đảm thao tác bên ngoài là atomic với transaction database của ứng dụng.

### 4.4. Messaging Bridge

Bridge chuyển message từ một channel sang channel khác mà không thay đổi payload theo logic nghiệp vụ. Nó hữu ích để nối hai flow, chuyển giữa channel có chính sách dispatch khác nhau, hoặc tạo điểm ghép giữa module.

## 5. Enterprise Integration Patterns quan trọng

Spring Integration hiện thực nhiều EIP. Mỗi pattern giải quyết một vấn đề cụ thể; không nên thêm pattern chỉ vì nó có sẵn trong framework.

### 5.1. Service Activator: gọi logic nghiệp vụ

Service activator nối một Spring-managed bean với input channel. Method nhận payload hoặc toàn bộ `Message<?>`; nếu method trả về giá trị, framework có thể tạo reply message và gửi đến output channel hoặc `replyChannel` của request.

~~~java
@Service
public class OrderService {

    @ServiceActivator(inputChannel = "orders.toProcess")
    public OrderAccepted process(OrderCommand command) {
        return new OrderAccepted(command.orderId(), "ACCEPTED");
    }
}
~~~

Trong Java DSL, `.handle(...)` biểu diễn service activator. Dùng service activator cho logic nghiệp vụ như kiểm tra đơn hàng, gọi domain service hoặc ghi dữ liệu. Tránh đưa quá nhiều quy tắc nghiệp vụ vào SpEL hoặc lambda cấu hình khó kiểm thử.

### 5.2. Transformer: đổi dạng dữ liệu

Transformer thay đổi payload hoặc cấu trúc message để component tiếp theo làm việc với định dạng phù hợp.

Ví dụ:

- CSV row thành `OrderCommand`.
- XML thành DTO.
- Chuỗi ngày tháng thành `Instant`.
- Chuẩn hóa tên field hoặc đơn vị đo.
- Thêm dữ liệu cần thiết bằng content enricher.

Transformer không nên tự quyết định message có được phép xử lý hay không; đó là trách nhiệm của filter hoặc service/domain validation.

### 5.3. Filter: cho hoặc chặn message

Filter đánh giá điều kiện boolean. Nếu message thỏa điều kiện, nó đi tiếp; nếu không, nó bị loại khỏi luồng chính. Có thể cấu hình discard channel để đưa message bị loại sang flow riêng, chẳng hạn audit hoặc quarantine.

Filter phù hợp với điều kiện đơn giản như bỏ message rỗng, loại event type không quan tâm hoặc chỉ cho qua message có trạng thái phù hợp. Điều kiện bảo mật hoặc invariant quan trọng vẫn phải được kiểm tra ở server/domain boundary, không dựa vào filter như cơ chế authorization duy nhất.

### 5.4. Router: chọn nơi xử lý

Router chọn một hoặc nhiều channel dựa trên payload, header hoặc quy tắc định tuyến. Ví dụ:

- Đơn hàng theo vùng được gửi đến channel của vùng đó.
- Message theo event type được gửi tới handler tương ứng.
- Lệnh có priority cao đi đến worker riêng.

Cần định nghĩa hành vi khi không tìm thấy route: channel mặc định, route fallback, lỗi định tuyến hoặc quarantine. Không để message biến mất âm thầm khi route key bị sai.

Ví dụ annotation router trả về tên channel:

~~~java
@Router(inputChannel = "orders.in")
public String route(OrderCommand command) {
    return switch (command.region()) {
        case "VN" -> "orders.vn";
        case "SG" -> "orders.sg";
        default -> "orders.review";
    };
}
~~~

Tên channel cần tồn tại hoặc được giải quyết theo cấu hình. Test cần bao phủ từng nhánh và trường hợp giá trị không nhận diện.

### 5.5. Splitter và Aggregator: chia rồi ghép

Splitter biến một message có nhiều phần tử thành nhiều message con. Ví dụ một order batch chứa nhiều order line có thể được chia thành các message riêng để xử lý song song.

Splitter/aggregator thường dùng các header sequence và correlation:

- `correlationId`: xác định các message con thuộc cùng một nhóm.
- `sequenceNumber`: thứ tự của message trong nhóm.
- `sequenceSize`: số lượng phần tử dự kiến trong nhóm.

Aggregator giữ message theo correlation group, sau đó phát kết quả khi release strategy cho biết nhóm đã đủ điều kiện. Điều kiện có thể là nhận đủ số message, đạt predicate nghiệp vụ hoặc hết timeout. Message store giữ trạng thái group; với ứng dụng cần phục hồi sau restart hoặc scale nhiều instance, cần cân nhắc persistent MessageStore và chiến lược cleanup.

Phải thiết kế các tình huống message đến trễ, thiếu, trùng hoặc sai thứ tự. Nếu aggregator chờ mãi một message không đến, group có thể giữ tài nguyên. Cần timeout, expiry, discard/recovery và metric cho group bị kẹt.

### 5.6. Resequencer

Resequencer giữ message trong nhóm và phát theo thứ tự sequence number, hữu ích khi upstream xử lý song song khiến kết quả về không đúng thứ tự. Resequencer khác aggregator: nó sắp lại thứ tự và phát từng message, trong khi aggregator tạo một kết quả từ cả nhóm.

### 5.7. Scatter-Gather

Scatter-Gather gửi request tới nhiều recipient rồi gom phản hồi. Ví dụ truy vấn giá từ nhiều nhà cung cấp cùng lúc và tổng hợp báo giá. Cần xác định timeout, số phản hồi tối thiểu, cách xử lý lỗi từng recipient và tiêu chí kết thúc. Không nên đợi vô hạn mọi recipient nếu một hệ thống có thể không phản hồi.

### 5.8. Content Enricher và Claim Check

Content enricher bổ sung dữ liệu vào message, ví dụ lấy thông tin khách hàng từ CRM trước khi gửi đơn hàng sang hệ thống fulfillment.

Claim check lưu một payload lớn hoặc dữ liệu không cần truyền qua mọi bước vào kho lưu trữ, rồi thay bằng một token/claim để flow sau lấy lại khi cần. Cần kiểm soát quyền truy cập, thời hạn sống và dọn dữ liệu đã lưu; claim token không nên trở thành URL hoặc quyền truy cập công khai không giới hạn.

### 5.9. Wire Tap

Wire Tap gửi bản sao message sang một channel phụ để quan sát, audit hoặc metrics mà không làm thay đổi luồng chính. Không dùng wire tap để thực hiện side effect nghiệp vụ bắt buộc nếu không có cơ chế bảo đảm giao nhận phù hợp. Dữ liệu nhạy cảm cần được che trước khi gửi sang log/audit flow.

## 6. Ghép flow bằng Java DSL

Java DSL cung cấp API fluent để định nghĩa `IntegrationFlow` dưới dạng các bước nối tiếp. Các operator phổ biến:

- `from(...)`: điểm bắt đầu từ channel, source hoặc endpoint.
- `filter(...)`: loại message không thỏa điều kiện.
- `transform(...)`: đổi payload/message.
- `route(...)`: định tuyến.
- `split(...)`: chia message.
- `aggregate(...)`: ghép message.
- `handle(...)`: gọi service activator.
- `channel(...)`: gửi kết quả đến channel được chỉ định.
- `gateway(...)`: gọi flow khác theo request/reply.
- `log()` và `wireTap(...)`: quan sát hoặc gửi bản sao.

Các endpoint trong flow Java DSL mặc định thường được nối bằng `DirectChannel` ngầm định. Có thể chỉ định channel rõ ràng để tách module hoặc kết nối với adapter. `IntegrationFlow` không phải một khối xử lý không thể tách; các channel được đặt tên có thể là điểm vào/ra mà thành phần khác sử dụng.

### 6.1. Ví dụ Java 17 chạy độc lập

Ví dụ dưới đây tạo một flow nhận chuỗi đơn hàng, bỏ chuỗi rỗng, chuẩn hóa bằng cách trim và uppercase, rồi chuyển tới handler cuối cùng. Đây là demo chạy trong một process; chưa kết nối broker hoặc database.

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-integration-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.integration</groupId>
            <artifactId>spring-integration-core</artifactId>
            <version>7.1.1</version>
        </dependency>
    </dependencies>
</project>
~~~

**IntegrationDemo.java**:

~~~java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.GenericMessage;

public class IntegrationDemo {

    public static void main(String[] args) {
        try (var context =
                 new AnnotationConfigApplicationContext(FlowConfiguration.class)) {

            MessageChannel input =
                context.getBean("ordersInput", MessageChannel.class);

            input.send(new GenericMessage<>("  order-42  "));
            input.send(new GenericMessage<>("   "));
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableIntegration
    static class FlowConfiguration {

        @Bean
        MessageChannel ordersInput() {
            return new DirectChannel();
        }

        @Bean
        IntegrationFlow orderFlow() {
            return IntegrationFlow.from("ordersInput")
                .<String>filter(payload -> !payload.isBlank())
                .<String, String>transform(String::trim)
                .<String, String>transform(String::toUpperCase)
                .handle(System.out::println)
                .get();
        }
    }
}
~~~

Chạy từ thư mục chứa `pom.xml` và `IntegrationDemo.java`.

Linux/macOS:

~~~bash
mvn -q dependency:build-classpath -Dmdep.outputFile=cp.txt
javac -cp "$(cat cp.txt)" IntegrationDemo.java
java -cp ".:$(cat cp.txt)" IntegrationDemo
~~~

Windows PowerShell:

~~~powershell
mvn -q dependency:build-classpath "-Dmdep.outputFile=cp.txt"
$cp = (Get-Content .\cp.txt -Raw).Trim()
javac -cp $cp .\IntegrationDemo.java
java -cp ".;$cp" IntegrationDemo
~~~

Output:

~~~text
ORDER-42
~~~

Message đầu tiên đi qua filter, được trim, chuyển thành chữ hoa và in ra. Message thứ hai là chuỗi trắng nên filter không cho đi tiếp; flow không in dòng thứ hai.

`DirectChannel` dispatch đồng bộ, vì vậy handler chạy trong luồng gửi. Khi flow có I/O chậm hoặc cần xử lý bất đồng bộ, hãy cân nhắc channel/executor phù hợp và đặt giới hạn concurrency/backlog thay vì mặc định chuyển mọi bước sang thread pool.

## 7. Poller và MessageSource

Không phải nguồn dữ liệu nào cũng đẩy message đến ứng dụng. File system, database query hoặc một số API cần được polling. `MessageSource<T>` tạo message khi được hỏi; poller xác định khi nào endpoint gọi source.

Poller có thể cấu hình theo:

- fixed delay hoặc fixed rate;
- cron;
- số message tối đa mỗi lần polling (`maxMessagesPerPoll`);
- receive timeout;
- transaction advice hoặc error handling.

Không dùng polling quá dày khi nguồn dữ liệu không thể đáp ứng. Cần cân nhắc tải hệ thống, thời gian xử lý, số lượng message tồn đọng và khả năng chạy nhiều instance cùng polling một nguồn.

Khi nhiều instance đọc chung một nguồn, cần cơ chế lock/claim hoặc partition để tránh cùng xử lý một bản ghi/file. Poller không tự bảo đảm một message chỉ được xử lý đúng một lần.

## 8. Error handling, retry và dead-letter

Lỗi có thể xảy ra ở nhiều vị trí: giải mã payload, transformer, router, service activator, adapter hoặc hệ thống bên ngoài.

Trong Spring Integration:

- Lỗi trong flow đồng bộ như `DirectChannel` thường có thể truyền ngược về thread gửi.
- Với poller hoặc xử lý bất đồng bộ, lỗi có thể được chuyển thành `ErrorMessage` và gửi đến error channel của message hoặc channel lỗi mặc định khi có cấu hình phù hợp.
- Có thể gắn retry/recovery advice vào endpoint.
- Error flow có thể phân loại lỗi, ghi nhận metadata, gửi dead-letter hoặc thông báo vận hành.

Không retry tất cả lỗi như nhau:

- Lỗi tạm thời như timeout hoặc kết nối gián đoạn có thể retry có giới hạn với backoff.
- Lỗi dữ liệu như schema sai hoặc trường bắt buộc thiếu thường cần quarantine/dead-letter, không retry liên tục.
- Lỗi phân quyền thường không được biến thành retry vô hạn.
- Lỗi nghiệp vụ như đơn hàng đã bị hủy cần xử lý theo quy tắc miền nghiệp vụ.

Retry có thể làm side effect lặp nếu handler không idempotent. Với thao tác ghi, dùng idempotency key, transaction, unique constraint hoặc inbox/outbox pattern tùy kiến trúc. Giới hạn retry, ghi nhận số lần thử và giữ đủ thông tin để điều tra mà không log secret hoặc toàn bộ payload nhạy cảm.

Dead-letter không phải thùng rác. Cần chính sách retention, quyền truy cập, replay có kiểm soát, cảnh báo và quy trình sửa dữ liệu trước khi gửi lại.

## 9. Transaction và độ tin cậy

Transaction có thể được gắn vào endpoint/poller bằng transaction advice. Với `DirectChannel`, các bước chạy cùng thread có thể tham gia transaction thread-bound nếu dùng cùng transaction manager và resource phù hợp.

Khi dùng `ExecutorChannel`, queue hoặc broker, luồng xử lý có thể đi qua ranh giới thread/process. Không giả định một transaction database cục bộ bao trùm toàn bộ message flow. Gửi message ra broker và commit database là hai side effect riêng trừ khi dùng cơ chế transaction tích hợp phù hợp.

Các chiến lược thường gặp:

- **Transactional outbox**: ghi dữ liệu nghiệp vụ và bản ghi outbox trong cùng transaction; publisher đọc outbox rồi gửi message.
- **Idempotent consumer/inbox**: ghi nhận message đã xử lý cùng transaction với cập nhật nghiệp vụ.
- **Retry + backoff**: phục hồi lỗi tạm thời với giới hạn.
- **Compensation/Saga**: hoàn tác nghiệp vụ bằng hành động bù khi không thể có transaction phân tán nguyên tử.
- **Durable broker**: lưu message và acknowledgement theo semantics của transport.

Cần xác định rõ semantics giao nhận: at-most-once, at-least-once hoặc cơ chế khác do broker/adapter cung cấp. Không tuyên bố exactly-once chỉ vì flow có transaction hoặc message ID.

## 10. Reactive Streams và Spring Integration

Spring Integration có hỗ trợ Reactive Streams, bao gồm channel và endpoint làm việc với `Publisher`. Điều này giúp kết nối flow với Reactor và các API reactive.

Reactive flow có demand/backpressure; channel truyền thống không tự động trở thành reactive chỉ vì một handler trả về `Flux` hoặc `Mono`. Cần chọn đúng reactive channel/endpoint và hiểu khi nào framework subscribe vào publisher, cách error được chuyển, và lifecycle của subscription.

Không gọi `subscribe()` thủ công trong service activator chỉ để chạy side effect rồi bỏ qua publisher. Hãy trả publisher cho framework khi API/endpoint hỗ trợ reactive return type. Nếu một đoạn flow dùng blocking I/O, cần bố trí scheduler/executor phù hợp và đặt giới hạn concurrency.

## 11. Quan sát và quản lý flow

Khi hệ thống có nhiều flow, cần biết message đang đi qua endpoint nào, channel nào và bị chậm ở đâu.

Spring Integration cung cấp các khả năng như:

- Message history để ghi lại các component message đã đi qua khi được bật.
- Metrics và Micrometer instrumentation cho throughput, send/receive, error và thời gian xử lý tùy endpoint.
- Integration Graph để quan sát các component và kết nối.
- Logging channel adapter hoặc wire tap để quan sát flow.
- JMX/management endpoint và control bus cho quản lý khi được cấu hình.

Nên log message ID, correlation ID, event type, route và error category. Che dữ liệu cá nhân, token và payload nhạy cảm. Không bật log payload toàn phần ở production nếu chưa có chính sách bảo vệ dữ liệu.

## 12. Kiểm thử Spring Integration flow

### 12.1. Unit test handler

Test riêng service/transformer/filter/router như Java method thông thường khi logic không phụ thuộc framework. Điều này nhanh và giúp xác định lỗi nghiệp vụ.

### 12.2. Test flow với QueueChannel

Có thể dùng `QueueChannel` làm output trong test để gửi message vào input rồi đọc reply một cách xác định:

~~~java
@SpringJUnitConfig(FlowTestConfiguration.class)
class OrderFlowTests {

    @Autowired
    @Qualifier("ordersInput")
    MessageChannel input;

    @Autowired
    @Qualifier("ordersOutput")
    PollableChannel output;

    @Test
    void trimsAndUppercasesOrderId() {
        input.send(new GenericMessage<>("  order-42  "));

        Message<?> result = output.receive(1000);

        assertNotNull(result);
        assertEquals("ORDER-42", result.getPayload());
    }
}
~~~

Test configuration có thể định nghĩa `ordersInput` là `DirectChannel`, `ordersOutput` là `QueueChannel`, rồi nối flow bằng `.transform(String::trim)`, `.transform(String::toUpperCase)` và `.channel("ordersOutput")`. Queue output cho phép test lấy reply bằng `receive(timeout)` mà không phải mock toàn bộ framework.

### 12.3. Spring Integration Test module

Dependency `spring-integration-test` cung cấp `@SpringIntegrationTest`, `MockIntegrationContext`, `MockIntegration` và `MockMessageHandler`.

Dùng `@SpringIntegrationTest(noAutoStartup = ...)` để ngăn inbound adapter thật tự khởi động trong test, ví dụ adapter kết nối broker, file server hoặc database. Sau đó dùng `MockIntegrationContext` để thay MessageSource hoặc MessageHandler bằng mock, và gọi `resetBeans()` để khôi phục endpoint sau test.

`MockIntegration.mockMessageSource(...)` tạo source test; `MockMessageHandler` cho phép stub hành vi one-way hoặc request-reply và capture message đầu vào. Các tiện ích này giúp kiểm tra flow mà không cần kết nối hệ thống bên ngoài ở mỗi unit/integration test.

### 12.4. Ma trận kiểm thử nên có

- Payload hợp lệ đi qua đúng transformer và handler.
- Filter loại message không thỏa điều kiện; discard channel nhận đúng message nếu được cấu hình.
- Router chọn đúng channel cho từng route key; route không xác định đi theo fallback.
- Splitter tạo đúng số message con, sequence và correlation.
- Aggregator release khi đủ message; timeout/thiếu message được xử lý.
- Gateway trả reply đúng hoặc timeout theo hợp đồng.
- Poller không xử lý lặp khi nhiều instance cùng chạy.
- Handler lỗi được chuyển đến error flow hoặc trả về caller đúng cách.
- Retry không tạo side effect trùng.
- Shutdown/restart không để message durable bị mất theo semantics đã cam kết.

Test integration với broker/file server thật nên chạy ở tầng CI phù hợp hoặc test container. Mock không thể chứng minh cấu hình serialization, acknowledgement, reconnect, transaction hoặc delivery semantics của broker production.

## 13. Lỗi thiết kế thường gặp

1. **Coi channel như broker bền vững.** DirectChannel và QueueChannel trong bộ nhớ không cung cấp durability khi process dừng.
2. **Dùng sai loại channel.** Cần broadcast nhưng dùng DirectChannel; cần buffering nhưng dùng synchronous channel.
3. **Không đặt capacity hoặc timeout.** Queue/backlog có thể tăng, producer có thể bị block hoặc message bị từ chối.
4. **Lẫn adapter với gateway.** Adapter một chiều không có hợp đồng reply; gateway phục vụ request/reply.
5. **Router không có fallback.** Message có route key lạ có thể lỗi hoặc bị bỏ theo cấu hình ngoài dự kiến.
6. **Filter được dùng như cơ chế bảo mật.** Filter không thay thế authentication/authorization và domain checks.
7. **Aggregator không có timeout/expiry.** Group thiếu message có thể giữ memory/store lâu dài.
8. **Retry vô hạn.** Hệ thống lỗi có thể bị quá tải thêm và dead-letter không được xử lý.
9. **Giả định transaction qua executor/broker.** Ranh giới thread/process phá vỡ nhiều giả định về transaction cục bộ.
10. **Tự subscribe reactive publisher.** Framework không còn quản lý lifecycle, lỗi và backpressure như mong đợi.
11. **Log toàn bộ message.** Có thể làm lộ token, dữ liệu cá nhân hoặc thông tin nghiệp vụ nhạy cảm.
12. **Chỉ test handler mà không test flow.** Lỗi mapping channel, poller, routing, header hoặc adapter chỉ xuất hiện khi tích hợp.

## 14. Quy trình chọn pattern cho một bài toán

Khi thiết kế flow mới, hãy mô tả đường đi dữ liệu trước rồi chọn pattern:

1. Dữ liệu đến từ đâu và đi ra đâu? Chọn inbound/outbound adapter hoặc gateway.
2. Caller có cần reply không? Chọn adapter một chiều hay gateway request/reply.
3. Các bước có cần chạy đồng bộ, broadcast, buffering hay bất đồng bộ? Chọn channel.
4. Có cần chuẩn hóa payload không? Dùng transformer.
5. Có cần loại bỏ message không? Dùng filter và định nghĩa discard behavior.
6. Có nhiều đích xử lý? Dùng router và fallback.
7. Một message chứa nhiều đơn vị công việc? Dùng splitter; nếu cần kết quả chung, ghép bằng aggregator.
8. Có yêu cầu thứ tự? Dùng resequencer hoặc partition/order semantics từ transport.
9. Lỗi tạm thời và lỗi vĩnh viễn được xử lý thế nào? Định nghĩa retry, error flow và dead-letter.
10. Message có thể gửi lặp hoặc process restart không? Thiết kế idempotency, durable storage và transaction boundary.
11. Cần quan sát điều gì? Bật metrics, message history hoặc wire tap với chính sách bảo vệ dữ liệu.
12. Kiểm thử được cả logic và transport chưa? Dùng unit, flow test và integration test tương ứng.

Một flow tốt là tập hợp các bước có trách nhiệm rõ ràng. Mỗi pattern nên giải quyết một yêu cầu cụ thể, và channel/endpoint nên được chọn theo semantics về dispatch, durability, threading, transaction và failure handling.

## Tài liệu tham khảo

- [Spring Integration Reference — 7.1.1](https://docs.spring.io/spring-integration/reference/index.html): tài liệu chính thức về core messaging, EIP, Java DSL, adapters, gateways và reactive support.
- [Core Messaging](https://docs.spring.io/spring-integration/reference/core.html): MessageChannel, poller, channel adapter và messaging bridge.
- [Message Routing](https://docs.spring.io/spring-integration/reference/message-routing.html): router, filter, splitter, aggregator, resequencer và scatter-gather.
- [Message Transformation](https://docs.spring.io/spring-integration/reference/message-transformation.html): transformer, content enricher, claim check và codec.
- [Service Activator](https://docs.spring.io/spring-integration/reference/service-activator.html): endpoint gọi Spring-managed service và reply channel.
- [Java DSL — Working With Message Flows](https://docs.spring.io/spring-integration/reference/dsl/java-flows.html): cách xây dựng IntegrationFlow và kết nối channel.
- [Testing support](https://docs.spring.io/spring-integration/reference/testing.html): SpringIntegrationTest, MockIntegrationContext và integration mocks.
- [Spring Integration project](https://spring.io/projects/spring-integration): tổng quan dự án, adapters, gateways và các pattern được hỗ trợ.
