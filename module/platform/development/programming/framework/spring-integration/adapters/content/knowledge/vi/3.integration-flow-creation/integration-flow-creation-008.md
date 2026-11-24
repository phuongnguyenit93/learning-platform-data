# Chọn input-channel và output-channel

## 1. Vì sao cần chọn đúng channel?

Trong Spring Integration, adapter và các endpoint trao đổi dữ liệu thông qua `MessageChannel`. Một message có **payload** chứa dữ liệu nghiệp vụ và **headers** chứa metadata như mã tương quan, thông tin nguồn, `replyChannel` hoặc `errorChannel`. Khi xây dựng integration flow, người phát message cần biết **gửi vào channel nào**, còn thành phần nhận cần biết **đọc từ channel nào**.

Chương **Tạo integration flow** của module **SPRING_INTEGRATION_ADAPTERS** tập trung vào việc nối các thành phần đó thành tuyến xử lý. Trong module này, hệ thống có thể dùng inbound/outbound adapter, gateway, poller và `MessageChannel` để kết nối file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu; đồng thời phải kiểm soát hợp đồng message, lỗi và vòng đời kết nối. Việc đặt `input-channel` và `output-channel` đúng là nền tảng để mọi tuyến xử lý hoạt động.

Ví dụ, một file inbound adapter phát `Message<File>` vào `files.received`. Một service activator đang lắng nghe `orders.validated` **không tự nhận được** message từ `files.received` chỉ vì cùng nằm trong application context. Phải có một endpoint trung gian chuyển message giữa hai channel hoặc sửa lại topology để các tên nối khớp nhau.

Sau bài này, người học có thể:

- Phân biệt **input-channel của endpoint** với **output-channel của endpoint** và giải thích vì sao cùng một channel có thể là output của thành phần trước nhưng là input của thành phần sau.
- Chọn đúng channel cho inbound adapter, outbound adapter, transformer, filter, service activator, bridge và gateway.
- Khai báo, kết nối và đặt tên channel bằng Java DSL, annotation hoặc XML namespace.
- Thiết kế flow có nhiều chặng, trong đó message chuyển đúng payload và headers qua mỗi bước.
- Phân biệt `outputChannel` với `replyChannel` trong request–reply.
- Hiểu loại channel ảnh hưởng thế nào đến thread, poller, transaction, timeout và khả năng chịu tải.
- Kiểm thử đường nối channel và nhận diện nguyên nhân gây mất message, timeout hoặc consumer không được gọi.

**Nguyên tắc:** “input” và “output” được xác định **tương đối với từng endpoint**, không phải đặc tính cố định của channel. Channel đứng giữa hai endpoint đồng thời là **output của endpoint trước** và **input của endpoint sau**.

## 2. Mô hình producer → channel → consumer

~~~mermaid
flowchart LR
    SRC["Inbound adapter<br/>producer"]
    CH1["files.received<br/>MessageChannel"]
    TRANS["Transformer<br/>consumer + producer"]
    CH2["orders.validated<br/>MessageChannel"]
    HAND["Service activator<br/>consumer + producer"]
    CH3["orders.accepted<br/>MessageChannel"]
    SINK["Outbound handler<br/>consumer"]
    SRC -->|"output"| CH1
    CH1 -->|"input"| TRANS
    TRANS -->|"output"| CH2
    CH2 -->|"input"| HAND
    HAND -->|"output"| CH3
    CH3 -->|"input"| SINK
~~~

Mỗi channel là một điểm bàn giao message. Trong sơ đồ:

- Inbound adapter là **producer**: nó đọc dữ liệu bên ngoài và phát message đến một channel.
- Transformer vừa là **consumer** của channel đầu vào, vừa là **producer** của channel đầu ra sau khi chuyển đổi payload.
- Service activator có thể chỉ **tiêu thụ** message để thực hiện side effect, hoặc **trả giá trị** để sinh reply và tiếp tục flow.
- Outbound adapter thường là **consumer**: nó nhận message rồi gửi dữ liệu ra ngoài hệ thống.

Ví dụ một endpoint xử lý dữ liệu cần được cấu hình:

~~~text
input-channel  = orders.validated
output-channel = orders.accepted
~~~

Điều đó có nghĩa endpoint **nhận** từ `orders.validated` và, **nếu tạo message kết quả**, phát tới `orders.accepted`. Cấu hình output channel không tự tạo reply: một method `void` hoặc handler trả `null` thường không phát sinh message mới để gửi đi.

### 2.1. Bảng chọn channel theo loại endpoint

| Thành phần | Channel dùng để nhận | Channel dùng để phát | Lưu ý |
| --- | --- | --- | --- |
| Inbound adapter | Không có input channel nội bộ vì dữ liệu đến từ nguồn ngoài. | `channel` hoặc thuộc tính tương đương, ví dụ `files.received`. | Với nguồn polling phải có poller. |
| Outbound adapter | `input-channel` hoặc channel nhận message. | Thường không có reply/output channel nghiệp vụ. | Là điểm kết thúc một chiều. |
| Transformer | `input-channel`. | `output-channel` nếu có chặng sau. | Sinh payload/message kết quả. |
| Filter | `input-channel`. | `output-channel` cho message được chấp nhận. | Có thể thêm discard channel cho message bị loại. |
| Router | `input-channel`. | Chọn một hoặc nhiều channel đích theo quy tắc. | Không có một output duy nhất trong mọi cấu hình. |
| Service activator | `input-channel`. | `output-channel` khi có reply cần chuyển tiếp. | Method `void` thường kết thúc một chiều. |
| Bridge | `input-channel`. | `output-channel`. | Chuyển message sang channel khác, không biến đổi nghiệp vụ. |
| Messaging gateway | `request-channel` hoặc `defaultRequestChannel`. | Reply từ flow đi về `replyChannel` của request hoặc kênh reply cấu hình. | Phân biệt request và reply của caller. |

Tên thuộc tính thay đổi giữa annotation, Java DSL và XML. Điều quan trọng là hiểu **hướng message**, sau đó tra đúng tên thuộc tính của endpoint trong cách cấu hình đang dùng.

## 3. Đặt tên channel và giải quyết bean trong Spring context

Một channel thường được đăng ký dưới dạng bean. Với Java configuration:

~~~java
@Bean(name = "orders.inbound")
MessageChannel ordersInbound() {
    return new DirectChannel();
}

@Bean(name = "orders.validated")
MessageChannel ordersValidated() {
    return new DirectChannel();
}

@Bean(name = "orders.accepted")
MessageChannel ordersAccepted() {
    return new DirectChannel();
}
~~~

Tên trong `@Bean(name = "...")` là tên channel để các endpoint tham chiếu. `orders.inbound` khác `order.inbound`, `orders.input` hoặc `orders.validated`. Việc đặt tên nên phản ánh **loại message hoặc trạng thái xử lý** tại ranh giới đó.

| Tên gợi ý | Ý nghĩa thực tế | Payload dự kiến |
| --- | --- | --- |
| `files.detected` | File adapter vừa phát hiện file phù hợp. | `File`. |
| `orders.raw` | Dữ liệu đơn hàng chưa chuẩn hóa. | `RawOrder` hoặc nội dung đọc từ nguồn. |
| `orders.validated` | Đơn đã qua validation và mapping. | `ValidatedOrder`. |
| `orders.accepted` | Kết quả chấp nhận đơn đang chờ handler kế tiếp. | `OrderReceipt`. |
| `payments.toBroker` | Lệnh thanh toán được chuyển tới adapter gửi broker. | `PaymentEvent`. |
| `integration.errors` | Nơi nhận message lỗi theo policy được cấu hình. | `ErrorMessage` hoặc DTO lỗi nghiệp vụ. |

Không phải mọi channel đều cần xuất hiện dưới dạng bean riêng: Java DSL có thể tạo **channel ngầm** giữa các endpoint. Tuy nhiên, khi cần nối hai flow độc lập, có nhiều producer/consumer hoặc muốn quan sát một ranh giới cụ thể, channel tên rõ ràng giúp dễ kiểm tra và bảo trì.

**Đừng giả định trùng tên có nghĩa trùng kiểu.** Hai producer phát cùng một channel nhưng dùng payload `File` và `OrderEvent` có thể làm consumer nhận sai kiểu. Hợp đồng channel cần xác định payload/headers mà cả producer và consumer tuân thủ.

## 4. Ví dụ hoàn chỉnh: chọn input-channel và output-channel bằng Java DSL và annotation

Bài toán: ứng dụng nhận `IncomingOrder` từ code Java, kiểm tra dữ liệu, đổi thành `ValidatedOrder`, gọi service xác nhận và đưa `OrderReceipt` đến một handler ghi nhận kết quả.

Flow được chia thành ba điểm nối:

~~~text
orders.inbound
    → filter/transform (IntegrationFlow)
    → orders.validated
    → @ServiceActivator (trả OrderReceipt)
    → orders.accepted
    → @ServiceActivator (void, kết thúc)
~~~

Cả hai `@ServiceActivator` cùng một ứng dụng nhưng sử dụng **input-channel khác nhau**, nên mỗi handler chỉ nhận message ở đúng chặng được giao.

### 4.1. Dependency

Ví dụ dùng Java 17+, Spring Boot và Spring Integration với dependency do Spring Boot quản lý:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
~~~

### 4.2. Cấu hình và code có thể chạy

Đặt đoạn dưới trong tệp `ChannelSelectionApplication.java` thuộc package `demo.channels`. Các record và component phụ có phạm vi package-private để ví dụ gọn trong một tệp.

~~~java
package demo.channels;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.MessageRejectedException;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableIntegration
public class ChannelSelectionApplication {

    public static void main(String[] args) {
        SpringApplication.run(ChannelSelectionApplication.class, args);
    }

    @Bean(name = "orders.inbound")
    MessageChannel ordersInbound() {
        return new DirectChannel();
    }

    @Bean(name = "orders.validated")
    MessageChannel ordersValidated() {
        return new DirectChannel();
    }

    @Bean(name = "orders.accepted")
    MessageChannel ordersAccepted() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow validateOrderFlow() {
        return IntegrationFlow.from("orders.inbound")
                .filter(IncomingOrder.class,
                        order -> order.id() != null
                                && !order.id().isBlank()
                                && order.quantity() > 0,
                        endpoint -> endpoint.throwExceptionOnRejection(true))
                .transform(IncomingOrder.class,
                        order -> new ValidatedOrder(
                                order.id().trim(), order.quantity()))
                .channel("orders.validated")
                .get();
    }

    @Bean
    ApplicationRunner sample(
            @Qualifier("orders.inbound") MessageChannel inbound) {
        return args -> inbound.send(
                MessageBuilder.withPayload(
                                new IncomingOrder("ORD-1001", 3))
                        .setHeader("correlationId", "trace-1001")
                        .build());
    }
}

record IncomingOrder(String id, int quantity) {}

record ValidatedOrder(String id, int quantity) {}

record OrderReceipt(String orderId, String status) {}

@Component
class OrderApprovalService {

    @ServiceActivator(
            inputChannel = "orders.validated",
            outputChannel = "orders.accepted")
    public OrderReceipt approve(ValidatedOrder order) {
        return new OrderReceipt(order.id(), "ACCEPTED");
    }
}

@Component
class ReceiptSink {

    private final List<OrderReceipt> receipts =
            new CopyOnWriteArrayList<>();

    @ServiceActivator(inputChannel = "orders.accepted")
    public void capture(OrderReceipt receipt) {
        receipts.add(receipt);
        System.out.println("Receipt: " + receipt);
    }

    public List<OrderReceipt> snapshot() {
        return List.copyOf(receipts);
    }

    public void clear() {
        receipts.clear();
    }
}
~~~

`@EnableIntegration` kích hoạt cơ chế xử lý Spring Integration trong ví dụ. `@SpringBootApplication` quản lý cấu hình và component scan cho các class trong package ứng dụng. Handler `@ServiceActivator` được framework đăng ký thành consumer của channel tương ứng.

### 4.3. Đọc kỹ hai điểm chuyển channel

**Điểm chuyển thứ nhất:** Java DSL lấy message từ `orders.inbound`, filter và transform, rồi chuyển payload `ValidatedOrder` tới `orders.validated`:

~~~java
IntegrationFlow.from("orders.inbound")
        .filter(IncomingOrder.class,
                order -> order.quantity() > 0)
        .transform(IncomingOrder.class,
                order -> new ValidatedOrder(
                        order.id(), order.quantity()))
        .channel("orders.validated")
        .get();
~~~

Đây là snippet rút gọn để thấy **hướng channel**; trong ứng dụng hoàn chỉnh ở trên, filter còn kiểm tra `id`. `from("orders.inbound")` chọn **đầu vào** của flow. `.channel("orders.validated")` chọn **đầu ra** ở cuối chặng transform. Nếu cần xử lý thêm trong cùng flow, có thể tiếp tục DSL sau `.channel(...)`.

**Điểm chuyển thứ hai:** annotation trên method Java:

~~~java
@ServiceActivator(
        inputChannel = "orders.validated",
        outputChannel = "orders.accepted")
public OrderReceipt approve(ValidatedOrder order) {
    return new OrderReceipt(order.id(), "ACCEPTED");
}
~~~

Service activator **nhận từ** `orders.validated` và **gửi kết quả tới** `orders.accepted`. Method trả `OrderReceipt`, vì vậy framework có message kết quả để gửi. Handler cuối lắng nghe `orders.accepted` và trả `void`, kết thúc luồng một chiều.

~~~mermaid
sequenceDiagram
    participant A as ApplicationRunner
    participant I as orders.inbound
    participant V as Java DSL validation
    participant C as orders.validated
    participant S as OrderApprovalService
    participant O as orders.accepted
    participant R as ReceiptSink
    A->>I: Message<IncomingOrder>
    I->>V: filter + transform
    V->>C: Message<ValidatedOrder>
    C->>S: approve(payload)
    S->>O: Message<OrderReceipt>
    O->>R: capture(payload)
    R-->>A: xử lý xong (không có reply nghiệp vụ)
~~~

**Hợp đồng payload:** `IncomingOrder(id, quantity)` ở channel đầu, `ValidatedOrder(id, quantity)` ở channel thứ hai và `OrderReceipt(orderId, status)` ở channel cuối. Các header như `correlationId` nên được bảo toàn hoặc map rõ ràng khi cần phục vụ tracing.

**Đường gửi một chiều:** `MessageChannel.send(...)` trả về kết quả bàn giao message qua channel, không phải một `OrderReceipt`. Nếu caller muốn nhận `OrderReceipt` như giá trị trả về, cần xây một hợp đồng request–reply thích hợp (mục 6).

## 5. Input-channel và output-channel trong Java DSL

Java DSL không luôn biểu diễn bằng hai thuộc tính XML có tên `input-channel`/`output-channel`; nó thể hiện qua chuỗi các lời gọi:

~~~java
@Bean
IntegrationFlow transferFlow() {
    return IntegrationFlow.from("transfer.requests")
            .transform(String.class, String::trim)
            .channel("transfer.normalized")
            .handle(String.class, (text, headers) -> {
                System.out.println(text);
                return null;
            })
            .get();
}
~~~

Trong flow này, `from("transfer.requests")` chọn channel đầu vào; `.channel("transfer.normalized")` tạo ranh giới channel trước handler. Endpoint handler phía sau trở thành consumer của `transfer.normalized`.

| Java DSL | Vai trò | Lưu ý |
| --- | --- | --- |
| `IntegrationFlow.from("source.channel")` | Chọn nguồn hoặc channel đầu vào của flow. | Channel cần có producer hoặc adapter gửi message. |
| `.channel("next.channel")` | Chuyển message tới channel được đặt tên. | Channel cần có consumer phù hợp. |
| `.handle(...)` | Thực thi handler, có thể trả kết quả hoặc kết thúc. | Trả `null` thường không có message tiếp. |
| `.transform(...)` | Tạo payload mới ở chặng sau. | Đảm bảo consumer tiếp nhận đúng kiểu. |
| `.filter(...)` | Cho message được chấp nhận đi tiếp. | Với request–reply cần policy từ chối rõ ràng. |
| `.route(...)` | Lựa chọn channel theo key/rule. | Mỗi nhánh cần endpoint tiêu thụ. |
| `.bridge()` | Chuyển tiếp message đến channel kế tiếp. | Dùng khi nối hai channel/flow mà không biến đổi dữ liệu. |

### 5.1. Khi nào không cần đặt channel tường minh?

~~~java
@Bean
IntegrationFlow compactFlow() {
    return IntegrationFlow.from("input.text")
            .transform(String.class, String::toUpperCase)
            .handle(String.class, (text, headers) -> {
                System.out.println(text);
                return null;
            })
            .get();
}
~~~

Ở đây không khai báo channel trung gian bằng tên. DSL tự nối các endpoint thích hợp. Nếu các bước chỉ thuộc một flow nhỏ và không cần ranh giới theo tên, đây là cách dễ đọc.

Chỉ tạo channel tường minh khi có lý do như **tái sử dụng giữa flow**, **đổi chế độ đồng bộ/buffer**, **quan sát**, **kiểm soát subscriber** hoặc **giữ giao diện ổn định** giữa các module.

### 5.2. Nối hai flow độc lập bằng Bridge

Nếu flow A kết thúc ở `orders.validated` còn flow B bắt đầu từ `orders.toProcess`, có thể thêm bridge:

~~~java
@Bean
IntegrationFlow handoffFlow() {
    return IntegrationFlow.from("orders.validated")
            .bridge()
            .channel("orders.toProcess")
            .get();
}
~~~

Đây là ví dụ **độc lập**, không đưa nguyên dạng vào ứng dụng mục 4 vì channel `orders.validated` đã có service activator đăng ký consumer. Nếu muốn nối flow khác, cần thay topology để không tạo consumer cạnh tranh.

Bridge chỉ làm nhiệm vụ bàn giao message; nếu đầu nhận yêu cầu kiểu payload khác, phải transformer/validate ở ranh giới đó.

## 6. Output-channel khác replyChannel ở điểm nào?

Đây là một khác biệt quan trọng khi thiết kế gateway request–reply.

- **`outputChannel`** (hoặc `output-channel` trong XML) là nơi **endpoint hiện tại** gửi kết quả của nó tới bước kế tiếp. Đây thường là channel cố định trong topology.
- **`replyChannel`** là header trong **message request**, cho biết reply của request này nên gửi về đâu. Messaging gateway có thể dùng một reply channel tạm để ghép đúng response với lời gọi đang đợi.
- **`errorChannel`** là header/channel giúp điều hướng các lỗi theo cấu hình, nhất là khi xử lý đã chuyển sang thread khác.

Ví dụ khi `@MessagingGateway` gọi flow:

~~~java
@MessagingGateway(defaultRequestChannel = "queries.input")
interface QueryGateway {
    QueryResult query(QueryRequest request);
}

@Component
class QueryHandler {

    @ServiceActivator(inputChannel = "queries.input")
    public QueryResult handle(QueryRequest request) {
        return new QueryResult(request.id(), "FOUND");
    }
}

record QueryRequest(String id) {}
record QueryResult(String id, String status) {}
~~~

Đây là một **ví dụ độc lập**; để chạy cần đăng ký gateway interface bằng `@IntegrationComponentScan` và các bean/class trong Spring context. Khi caller gọi `query(...)`, proxy gửi request vào `queries.input` với thông tin đường reply. Handler trả `QueryResult`, framework gửi reply về kênh phản hồi của gateway khi không có output channel khác buộc chuyển hướng.

### 6.1. Điều gì xảy ra nếu đặt outputChannel cố định?

Giả sử sửa handler thành:

~~~java
@ServiceActivator(
        inputChannel = "queries.input",
        outputChannel = "queries.audit")
public QueryResult handle(QueryRequest request) {
    return new QueryResult(request.id(), "FOUND");
}
~~~

Kết quả của handler sẽ được đưa tới `queries.audit` theo cấu hình. **Không thể giả định gateway vẫn tự nhận kết quả đó** nếu downstream không có bước hoàn thành đường reply tương ứng. Một gateway đang đợi reply có thể timeout.

Nếu cần cả audit và reply, phải thiết kế fan-out/audit phù hợp rồi giữ một đường reply rõ ràng, hoặc thực hiện audit như side effect không làm mất đường phản hồi. Đừng chỉ thay `outputChannel` theo tên mà bỏ qua hợp đồng request–reply.

### 6.2. Khi nào dùng reply channel cố định?

Spring Integration hỗ trợ cấu hình reply channel khi thực sự cần định tuyến kết quả qua một channel có tên. Tuy nhiên, reply channel dùng chung cho nhiều request đồng thời cần cơ chế correlation và consumer thích hợp. Với request–reply đơn giản, gateway tự tạo đường reply thường dễ an toàn và ít lỗi hơn.

Không đưa nguyên đối tượng header `replyChannel` (có thể là một `MessageChannel` trong bộ nhớ) qua HTTP/JMS/Kafka như một chuỗi dữ liệu tùy ý. Adapter giao thức cần mapper và cơ chế tương quan tương ứng.

## 7. Chọn channel cho inbound và outbound adapter

### 7.1. Inbound adapter: chọn channel để phát message

Một inbound adapter đọc dữ liệu **bên ngoài** rồi phát message **vào Spring Integration**. Với annotation:

~~~java
@Bean
@InboundChannelAdapter(
        value = "files.received",
        poller = @Poller(fixedDelay = "5000",
                         maxMessagesPerPoll = "5"))
MessageSource<File> fileSource() {
    var source = new FileReadingMessageSource();
    source.setDirectory(new File("./inbox"));
    return source;
}
~~~

Snippet cần các import `@Bean`, `@InboundChannelAdapter`, `@Poller`, `MessageSource`, `File` và `FileReadingMessageSource`; cần module `spring-integration-file` và thư mục nguồn. Thuộc tính `value = "files.received"` chỉ định **channel đầu ra của inbound adapter**. Endpoint poller lấy `Message<File>` từ source rồi gửi tới channel đó.

Chú ý: đây là ví dụ rút gọn để tập trung vào hướng message, chưa cấu hình filter/accept-once/file-ready/idempotency. Khi dùng file thực tế, cần tránh đọc file đang ghi và xác định chính sách xử lý trùng.

### 7.2. Outbound adapter: chọn channel để nhận message

Outbound adapter/handler là **consumer của message từ flow**. Với service activator một chiều:

~~~java
@ServiceActivator(inputChannel = "files.toArchive")
public void archive(File file) {
    fileArchiveClient.save(file);
}
~~~

`fileArchiveClient` là dependency ứng dụng tự triển khai. Method nhận từ `files.toArchive` và không phát reply; không cần đặt một `outputChannel` cho nó.

Với adapter JMS, Kafka, SFTP hoặc HTTP có sẵn, cách khai báo khác nhau nhưng hướng tổng quát vẫn là **message từ input channel → handler gửi ra hệ thống ngoài**. Khi đích trả phản hồi cần sử dụng trong flow, cân nhắc **outbound gateway** thay vì adapter một chiều.

### 7.3. Bảng lựa chọn theo giao thức

| Trường hợp | Channel cần thiết | Hành vi khác cần cấu hình |
| --- | --- | --- |
| File/SFTP inbound polling | Adapter phát ra channel nhận file. | Poller, filter, file-ready, remote session, checkpoint. |
| HTTP inbound gateway | Request được gửi đến request channel của flow. | Mapping request/response, HTTP status và timeout. |
| JMS/AMQP/Kafka inbound listener | Adapter/listener phát message vào channel xử lý. | Ack/offset, transaction, retry, consumer concurrency. |
| JDBC inbound polling | Message source phát record vào channel. | Query chỉ nhận dữ liệu mới, transaction, dấu mốc và lock. |
| File/SFTP outbound adapter | Consumer nhận từ channel chuẩn bị gửi file. | Naming, ghi tạm/rename, lỗi tồn tại file và permissions. |
| JMS/AMQP/Kafka outbound adapter | Consumer nhận event/command từ channel. | Serializer, broker ack, delivery failure, idempotency. |
| HTTP outbound gateway | Consumer nhận request từ flow và tạo reply. | URL, method, status, error mapping, response timeout. |

**Một tên channel đúng không thay thế hợp đồng dữ liệu.** Ví dụ `orders.toKafka` có thể nhận `OrderEvent` đã serialize hoặc object chưa serialize tùy adapter; payload và headers phải tương thích producer/handler ở hai phía.

## 8. Cấu hình input-channel và output-channel bằng XML namespace

XML namespace diễn đạt cùng ý tưởng một cách tường minh:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:int="http://www.springframework.org/schema/integration"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           http://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/integration
           http://www.springframework.org/schema/integration/spring-integration.xsd">

    <int:channel id="orders.raw"/>
    <int:channel id="orders.normalized"/>
    <int:channel id="orders.accepted"/>

    <!-- Nhận từ raw, biến đổi và phát tới normalized. -->
    <int:transformer
            input-channel="orders.raw"
            output-channel="orders.normalized"
            expression="payload.trim()"/>

    <!-- Service activator nhận từ normalized và phát reply tới accepted. -->
    <bean id="orderService" class="demo.xml.OrderService"/>
    <int:service-activator
            input-channel="orders.normalized"
            output-channel="orders.accepted"
            ref="orderService"
            method="approve"/>

    <!-- Consumer của orders.accepted phải được định nghĩa ở nơi khác. -->
</beans>
~~~

Ví dụ này giả định `orders.raw` mang payload `String` và `demo.xml.OrderService.approve(String)` trả một object kết quả. `OrderService` là class người học phải tự cung cấp. XML chỉ minh họa **channel wiring**, không phải chương trình đầy đủ vì thiếu consumer cuối.

Với file inbound adapter, cú pháp thường dùng `channel="files.raw"`:

~~~xml
<int-file:inbound-channel-adapter
        id="fileInbound"
        channel="files.raw"
        directory="./inbox"
        filename-pattern="*.csv">
    <int:poller fixed-delay="5000"
                max-messages-per-poll="5"/>
</int-file:inbound-channel-adapter>
~~~

Để dùng snippet này phải khai báo thêm namespace/XSD `int-file` và dependency `spring-integration-file`. Ở đây `channel` là **đầu ra** của inbound adapter. Ngược lại, outbound adapter thường có `channel` hoặc `input-channel` tương ứng với kênh **nhận message**, tùy schema cụ thể; luôn đối chiếu XSD phiên bản đang dùng.

### 8.1. Bridge giữa hai channel trong XML

~~~xml
<int:channel id="legacy.orders"/>
<int:channel id="orders.processing"/>

<int:bridge
        input-channel="legacy.orders"
        output-channel="orders.processing"/>
~~~

Bridge chuyển message từ input channel sang output channel mà không cần biến đổi payload nghiệp vụ. Nếu `legacy.orders` là `QueueChannel`, bridge consumer cần poller phù hợp.

### 8.2. Tránh chạy hai cấu hình trùng nhau

Ứng dụng có thể kết hợp XML với Java DSL qua `@ImportResource`, nhưng không nên tạo hai consumer cạnh tranh trên cùng `DirectChannel` hoặc hai inbound adapter cùng poll một nguồn nếu không có thiết kế cụ thể. Trùng tên bean cũng có thể làm context khởi tạo thất bại hoặc bị ghi đè theo cấu hình.

## 9. Chọn DirectChannel, QueueChannel hay ExecutorChannel?

Việc chọn input/output channel liên quan **kiểu channel** chứ không chỉ tên. Kiểu channel ảnh hưởng cách message được bàn giao.

| Loại channel | Cách hoạt động | Hệ quả khi nối endpoint |
| --- | --- | --- |
| `DirectChannel` | Gửi trực tiếp tới một subscriber, thường xử lý trong thread sender. | Handler chậm có thể chặn producer; exception đồng bộ thường lan về caller/poller. |
| `QueueChannel` | Giữ message trong bộ đệm để consumer lấy khi poll. | Consumer cần poller; phải quản lý capacity, độ bền và retry. |
| `ExecutorChannel` | Dispatcher chuyển việc xử lý sang `TaskExecutor`. | Có ranh giới thread, giới hạn executor/queue và đường lỗi khác. |
| `PublishSubscribeChannel` | Phân phát message cho nhiều subscriber theo cấu hình. | Hữu ích cho fan-out; phải quyết định xử lý lỗi ở từng nhánh. |

### 9.1. DirectChannel: chọn cho luồng đồng bộ đơn giản

Ví dụ `orders.inbound → filter → orders.validated → approve` ở mục 4 dùng `DirectChannel`. Khi `send()` được gọi, consumer có thể được thực thi ngay trên thread gửi. Nếu consumer gọi HTTP mất 10 giây, sender cũng có thể mất 10 giây.

**Không coi việc gửi vào DirectChannel thành công là hệ thống đích đã xử lý nghiệp vụ.** Kết quả của `MessageChannel.send` nói về bàn giao nội bộ; thành công ở HTTP/broker/database cần thêm hợp đồng riêng.

### 9.2. QueueChannel: khi cần buffer, consumer phải poll

~~~java
@Bean(name = "orders.buffered")
QueueChannel ordersBuffered() {
    return new QueueChannel(100);
}

@ServiceActivator(
        inputChannel = "orders.buffered",
        poller = @Poller(
                fixedDelay = "500",
                maxMessagesPerPoll = "10"))
public void consume(ValidatedOrder order) {
    orderProcessor.process(order);
}
~~~

Snippet giả định có imports `QueueChannel`, `@Bean`, `@ServiceActivator`, `@Poller` và bean `orderProcessor`, cùng kiểu `ValidatedOrder` như ví dụ trước. Đây là **biến thể** minh họa cho input channel dạng queue, không đăng ký đồng thời với handler đang nhận `orders.validated` trong ứng dụng mục 4.

Queue giúp tách thời điểm producer gửi với consumer xử lý. Nó **không tự tạo độ bền xuyên restart** nếu dùng queue bộ nhớ mặc định. Khi queue đầy, hành vi gửi/timeout phải được thiết kế rõ.

### 9.3. ExecutorChannel: tách thread không phải tự động tăng độ tin cậy

Nếu gắn consumer sau `ExecutorChannel`, Spring chuyển việc xử lý sang executor theo cấu hình. Caller có thể trả về trước khi handler xong; lỗi handler sẽ không nhất thiết truyền trở lại call stack nguồn. Phải giám sát executor capacity, rejection, shutdown và error channel.

Khi thay đổi loại channel ở ranh giới flow, kiểm thử lại transaction, retry và reply timeout; không chỉ thay một dòng cấu hình rồi giữ nguyên giả định đồng bộ.

### 9.4. Nhiều consumer trên một channel

`DirectChannel` thường bàn giao mỗi message cho **một** subscriber theo chiến lược dispatcher, không phải phát cho toàn bộ subscriber. Nếu muốn cùng một event đến hai dịch vụ độc lập, dùng `PublishSubscribeChannel` hoặc cơ chế multicast rõ ràng. Nếu muốn chọn một trong nhiều channel dựa trên currency/loại message, dùng router.

Thêm hai `@ServiceActivator(inputChannel="orders.validated")` không đồng nghĩa hai method cùng nhận mỗi message. Một số trường hợp chỉ một handler chạy, dẫn đến khó tìm lỗi nếu không hiểu semantics của channel.

## 10. Khi nào cần channel trung gian và khi nào nên nối trực tiếp?

Không phải mọi endpoint đều cần tách thành channel có tên mới. Một flow tuyến tính có thể ngắn gọn:

~~~java
@Bean
IntegrationFlow simpleFlow() {
    return IntegrationFlow.from("events.in")
            .filter(Event.class, event -> event.isValid())
            .transform(Event.class, Event::toCommand)
            .handle(Command.class, (command, headers) -> {
                commandService.execute(command);
                return null;
            })
            .get();
}
~~~

Snippet này là **mẫu minh họa**, giả định các class `Event`, `Command` và bean `commandService` đã được định nghĩa. Không cần một channel được đặt tên riêng giữa mỗi bước.

Nên thêm channel trung gian khi:

1. **Có nhiều nguồn vào chung một hợp đồng:** file/SFTP, HTTP, JMS, Kafka đều chuẩn hóa thành `OrderEvent` rồi gửi tới `orders.normalized`.
2. **Một chặng được dùng lại bởi flow khác:** nhiều producer đẩy message vào một channel mà consumer thống nhất xử lý.
3. **Cần thay đổi ranh giới xử lý:** queue/executor nhằm giảm chặn producer hoặc điều tiết tải.
4. **Cần vận hành và quan sát:** theo dõi queue backlog, lỗi dispatch, consumer start/stop hoặc triển khai từng module.
5. **Cần bảo đảm topology ổn định:** giữ tên channel khi thay một adapter bằng adapter giao thức khác.

Hạn chế tạo channel chỉ để tăng số lượng bean: nhiều ranh giới không cần thiết làm cấu hình khó đọc và có thể đổi hành vi transaction/thread ngoài ý muốn.

## 11. Lỗi phổ biến khi chọn input/output channel

| Hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| Adapter phát message nhưng handler không được gọi. | Sai tên channel, endpoint chưa start hoặc không có consumer. | So khớp output của adapter với input của endpoint kế tiếp. |
| `DirectChannel` báo không có subscriber. | Channel chưa có handler đăng ký đúng. | Kiểm tra `@ServiceActivator`, Java DSL hoặc XML consumer. |
| Gateway chờ đến timeout. | Handler không tạo reply; outputChannel cố định dẫn reply đi nơi khác; filter âm thầm loại message. | Vẽ đường request/reply, kiểm tra `replyChannel` và policy lỗi. |
| Message tới handler sai kiểu. | Producer gửi `File` nhưng consumer đòi `Order`. | Chuẩn hóa payload/headers trước channel chung. |
| Hai handler cùng nhận một channel nhưng không cùng chạy. | `DirectChannel` không multicast. | Dùng router hoặc publish–subscribe theo yêu cầu. |
| Thay channel thành QueueChannel rồi message nằm chờ mãi. | Thiếu poller/consumer. | Đăng ký polling endpoint cho channel queue. |
| Chuyển sang ExecutorChannel rồi exception mất khỏi caller. | Handler chạy trên thread khác. | Đặt error channel/monitoring/retry theo semantics mới. |
| File/SFTP bị đọc lặp sau restart. | Filter chỉ lưu RAM; checkpoint không bền. | Dùng metadata store, archive, idempotency. |
| Đích xử lý thành công nhưng caller thấy timeout. | Reply mất hoặc đến muộn, dẫn tới retry. | Đối soát bằng ID/idempotency key, không retry mù. |
| Header correlation bị mất. | Tự tạo message mới và bỏ header. | Kiểm tra mapper/transformer và test qua channel thực. |
| Poller xử lý chậm dù fixed-delay ngắn. | Handler đồng bộ giữ thread poller. | Đo thời gian xử lý, điều chỉnh channel/poller và timeout. |
| App tạo hai endpoint xử lý trùng. | XML và DSL cùng đăng ký consumer hoặc nhiều adapter đọc chung nguồn. | Kiểm tra bean ID, component scan và topology. |

## 12. Hợp đồng message tại mỗi channel

Chọn channel là quyết định về **dữ liệu** và **vận hành**. Ví dụ:

~~~text
Channel: orders.validated
Payload: ValidatedOrder {
    id: "ORD-1001",
    quantity: 3
}
Headers:
    correlationId: "trace-1001"
    sourceSystem: "file-import"
    idempotencyKey: "order:ORD-1001"
~~~

Hợp đồng nên làm rõ:

- **Payload type**: loại Java hoặc schema mà consumer chấp nhận, trường bắt buộc, nullability và validation.
- **Headers**: correlation, tracing, tenant, nguồn dữ liệu, message key; có cần giữ xuyên transformer/bridge không?
- **Delivery semantics**: đồng bộ hay async, có queue không, ACK/offset do nguồn nào quản lý?
- **Reply semantics**: one-way hay request–reply, kết quả trả đi đâu, timeout thế nào?
- **Error semantics**: khi validation fail, exception xảy ra hoặc downstream mất kết nối, message đi đâu?
- **Idempotency**: khi nguồn gửi lặp hoặc retry sau lỗi, side effect có bị thực hiện hai lần không?

Ở module Spring Integration Adapters, nhiều giao thức có thể cùng tạo message nhưng khác nhau về header và ack. Đừng đặt cùng một channel cho các producer có kiểu payload không tương thích nếu không có transformer rõ ràng. Khi gửi message ra HTTP/JMS/AMQP/Kafka, không tự động serialize mọi header Spring nội bộ như `replyChannel`; dùng header mapping tương thích giao thức.

## 13. Lỗi, thread, transaction và vòng đời

### 13.1. Đường lỗi phải đi theo topology thật

~~~mermaid
flowchart TD
    A["Adapter nhận dữ liệu"]
    B["Input channel của processor"]
    C["Validate/Transform"]
    D["Output channel"]
    E["Outbound handler"]
    OK["Đích xác nhận theo hợp đồng"]
    ERROR["Error flow / retry / quarantine"]
    A --> B --> C --> D --> E --> OK
    A -. "lỗi đọc nguồn" .-> ERROR
    B -. "dispatch thất bại" .-> ERROR
    C -. "validation lỗi" .-> ERROR
    E -. "timeout / lỗi đích" .-> ERROR
~~~

Trong flow đồng bộ với `DirectChannel`, exception từ downstream có thể lan về caller hoặc poller. Khi sử dụng queue/executor/listener, lỗi có thể phát sinh trên thread khác, cần error channel, `ErrorMessage` và policy recovery phù hợp.

**Output channel nhận được message không có nghĩa hệ thống đích đã hoàn tất.** Cần phân biệt source đã đọc, message đã bàn giao vào channel, handler đã chạy và hệ thống ngoài đã xử lý thành công.

### 13.2. Transaction không tự xuyên mọi channel

Nếu message đi qua hai `DirectChannel` trong cùng thread, transaction Spring đang hoạt động có thể bao phủ các thao tác nội bộ phù hợp. Khi chuyển qua `QueueChannel`, `ExecutorChannel` hoặc broker, không nên giả định vẫn nằm trong cùng transaction. Và một transaction DB nội bộ không tự rollback được HTTP request đã được đối tác xử lý.

Với các side effect như gửi thanh toán hoặc tạo đơn, cần idempotency key, unique constraint, transactional outbox hoặc quy trình đối soát nếu kết quả không rõ. Cấu hình input/output channel đơn thuần không cung cấp exactly-once.

### 13.3. Kiểm soát vòng đời

Inbound adapter, poller, listener container và outbound connection pool thường có lifecycle riêng. Khi endpoint dừng, có thể xảy ra tình huống channel còn tồn tại nhưng không có consumer hoặc queue giữ message chờ. Cần giám sát trạng thái endpoint, số message vào/ra, lỗi, queue depth, latency và kết nối đến hệ thống ngoài.

Khi triển khai nhiều instance, mỗi instance có thể poll cùng nguồn file/SFTP hoặc cùng truy vấn DB nếu thiếu lock/claim/partition. Channel nằm trong bộ nhớ của từng instance không tự hợp nhất và cũng không phải bus chung giữa các process.

## 14. Kiểm thử đường nối input/output channel

Test unit gọi trực tiếp method `approve(...)` chỉ kiểm tra business logic. Để xác minh tên channel, endpoint và kiểu payload, hãy khởi động Spring context rồi **gửi message vào channel đầu vào**.

Với ứng dụng mục 4, thêm dependency test:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Tạo `ChannelSelectionApplicationTest.java` trong package `demo.channels`:

~~~java
package demo.channels;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.integration.MessageRejectedException;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootTest
class ChannelSelectionApplicationTest {

    @Autowired
    @Qualifier("orders.inbound")
    MessageChannel input;

    @Autowired
    ReceiptSink sink;

    @BeforeEach
    void clearResults() {
        sink.clear();
    }

    @Test
    void validOrderReachesAcceptedChannelAndSink() {
        boolean sent = input.send(
                MessageBuilder.withPayload(
                        new IncomingOrder("ORD-2001", 2))
                        .setHeader("correlationId", "trace-test-2001")
                        .build());

        assertTrue(sent);
        assertEquals(
                List.of(new OrderReceipt("ORD-2001", "ACCEPTED")),
                sink.snapshot());
    }

    @Test
    void invalidOrderDoesNotReachSink() {
        assertThrows(MessageRejectedException.class,
                () -> input.send(MessageBuilder.withPayload(
                        new IncomingOrder("ORD-2002", 0)).build()));

        assertTrue(sink.snapshot().isEmpty());
    }
}
~~~

Vì hai channel trung gian đều là `DirectChannel`, flow và handler thường hoàn tất đồng bộ trước khi lời gọi `send` trả về. Do đó test có thể kiểm tra danh sách `sink.snapshot()` ngay lập tức.

Test chứng minh **đường nối** từ `orders.inbound` qua `orders.validated`, `orders.accepted` đến handler cuối; nó không thử kết nối file/SFTP/Kafka hay cơ chế xác nhận của hệ thống ngoài. Nếu thay channel bằng queue hoặc executor, cần chờ kết quả theo điều kiện có timeout và kiểm soát concurrency.

### 14.1. Những test bổ sung đáng làm

1. Gửi message có payload khác hợp đồng, xác nhận quy tắc reject/transform rõ.
2. Đổi sai một channel name ở cấu hình test có chủ đích để quan sát lỗi khi không có subscriber.
3. Đặt filter loại message trong flow request–reply và kiểm tra caller nhận lỗi hay timeout.
4. Chuyển `orders.validated` thành `QueueChannel`, thêm poller cho consumer rồi so sánh thời điểm gửi và xử lý.
5. Mô phỏng outbound handler timeout/exception và kiểm tra nơi nhận `ErrorMessage`, thời điểm retry và chống duplicate.
6. Gửi nhiều request đồng thời qua messaging gateway để xác minh không tráo reply giữa các caller.

## 15. Bài tập: thiết kế channel cho luồng nhiều giao thức

**Bài toán:** một hệ thống nhận đơn hàng từ file SFTP và JMS. Cả hai nguồn cần chuẩn hóa thành `OrderEvent`, kiểm tra trùng, gửi sang API đối tác và lưu kết quả xử lý vào database.

Yêu cầu:

1. Đặt tên channel cho mỗi nguồn chưa chuẩn hóa: `orders.sftp.raw` và `orders.jms.raw`.
2. Dùng transformer riêng cho từng nguồn rồi gửi message hợp lệ vào channel chung `orders.normalized`.
3. Chọn input-channel và output-channel của validation service. Message không hợp lệ đi vào error/quarantine flow riêng.
4. Gửi các đơn hợp lệ tới `orders.toPartner`. Nếu API đối tác cần response, thiết kế outbound gateway và channel trả kết quả.
5. Đưa kết quả chấp nhận vào `orders.results` và dùng handler ghi database; xác định trách nhiệm của transaction.
6. Giải thích nên chọn `DirectChannel`, `QueueChannel` hay `ExecutorChannel` tại từng ranh giới, dựa trên tải và yêu cầu khôi phục.
7. Mô phỏng API đối tác đã tạo đơn nhưng phản hồi bị mất; chứng minh retry với idempotency key không tạo đơn trùng.
8. Viết integration test có message cùng ID đến từ SFTP và JMS, kiểm tra hợp đồng payload/header, dedup và kết quả cuối.

**Tiêu chí đạt:** không có channel bỏ trống consumer ngoài chủ đích; hai nguồn thống nhất payload trước channel chung; đường request–reply có reply rõ ràng; mọi side effect có quy ước timeout/retry/ack; sơ đồ thể hiện đúng hướng message và loại channel ở mỗi điểm bàn giao.

## 16. Câu hỏi tự kiểm tra

1. Một channel có thể vừa là output của endpoint này, vừa là input của endpoint khác không?
2. Vì sao inbound adapter chỉ cần cấu hình channel phát message mà không có input-channel nội bộ?
3. Nếu `@ServiceActivator` khai báo `outputChannel` nhưng method trả `void`, điều gì xảy ra?
4. Khi nào dùng `IntegrationFlow.from(...)` và khi nào dùng `.channel(...)`?
5. `@MessagingGateway` cần channel request và đường reply theo hai vai trò nào?
6. Vì sao không thể đồng nhất `outputChannel` với header `replyChannel`?
7. Hai `@ServiceActivator` cùng nhận từ `DirectChannel` có mặc nhiên cùng xử lý một message không?
8. Nếu thay input channel bằng `QueueChannel`, cần bổ sung thành phần gì?
9. Một message được chuyển tới output channel chứng minh được điều gì và chưa chứng minh được điều gì?
10. Khi handler chuyển sang thread khác, lỗi và transaction thay đổi ra sao?
11. Làm thế nào kiểm thử cấu hình channel mà không phải khởi động SFTP/JMS/Kafka thật?
12. Vì sao nhiều adapter dùng một channel chung vẫn phải chuẩn hóa payload/header trước?

**Gợi ý:** input/output là vai trò của từng endpoint; gateway bổ sung đường reply cho request; channel quyết định semantics bàn giao; kiểm thử qua Spring context mới phát hiện lỗi wiring; tính tin cậy cuối cùng phụ thuộc trạng thái nguồn, side effect đích và chiến lược retry.

## 17. Ghi nhớ

**Chọn input-channel và output-channel** là xác định đường đi của message giữa producer, endpoint và consumer trong Spring Integration. Inbound adapter phát message tới channel đầu vào của flow; transformer/filter/service activator đọc từ channel của chặng trước và, khi có kết quả, phát tới channel của chặng sau; outbound adapter tiêu thụ message để gửi ra đích.

Đối với file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu, hãy kết hợp **tên channel nhất quán**, **hợp đồng payload/headers rõ ràng**, **loại channel phù hợp với thread và tải**, **đường reply/lỗi có chủ đích** cùng **kiểm thử topology thực tế**. Channel được nối đúng giúp message đến đúng thành phần; việc xử lý an toàn còn đòi hỏi timeout, retry, idempotency và xác nhận nghiệp vụ theo từng hệ thống.

