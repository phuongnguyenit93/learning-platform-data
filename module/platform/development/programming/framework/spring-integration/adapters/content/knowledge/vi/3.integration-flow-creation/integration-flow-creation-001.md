# IntegrationFlow bằng Java DSL

## 1. Mục tiêu và bối cảnh

Trong Spring Integration, `IntegrationFlow` mô tả một chuỗi xử lý message: message đi vào ở đâu, qua những thành phần nào, đến hệ thống hoặc thành phần nào và kết quả được trả về thế nào. **Java DSL** cho phép định nghĩa chuỗi đó bằng các lời gọi API Java có kiểu, nằm trong cấu hình Spring và được quản lý như các bean.

Bài học thuộc chương **Tạo integration flow** của module **SPRING_INTEGRATION_ADAPTERS**. Mục tiêu lớn hơn của module là kết nối các hệ thống bên ngoài bằng inbound/outbound adapter, gateway, poller và `MessageChannel`; thực hành trao đổi qua file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu; đồng thời kiểm soát hợp đồng message, lỗi và vòng đời kết nối.

Sau bài này, người học có thể:

- Nhận ra trách nhiệm của `IntegrationFlow`, `Message<?>`, `MessageChannel` và các endpoint.
- Tạo flow bằng `IntegrationFlow.from(...)`, `filter`, `transform`, `route`, `handle`, `channel` và `get()`.
- Đưa request từ phương thức Java vào flow qua messaging gateway, rồi trả kết quả theo cơ chế request–reply.
- Kết nối một inbound adapter hoạt động theo lịch poll với phần xử lý phía sau.
- Chọn channel, xử lý lỗi, bảo toàn header và kiểm thử các nhánh quan trọng của flow.

**Phạm vi:** tập trung vào cách *tạo và tổ chức* flow bằng Java DSL. Adapter cụ thể như SFTP, JMS, AMQP hay Kafka cần dependency, cấu hình kết nối và hợp đồng nghiệp vụ tương ứng; Java DSL không tự cung cấp những điều đó.

## 2. Mô hình tư duy: message chạy qua các endpoint

Một Spring Integration message gồm **payload** (dữ liệu nghiệp vụ) và **headers** (metadata như `id`, `timestamp`, `replyChannel`, `errorChannel`, correlation ID hoặc header do ứng dụng thêm). Các thành phần trong flow giao tiếp thông qua message thay vì gọi trực tiếp từng service theo một chuỗi phụ thuộc cứng.

~~~mermaid
flowchart LR
    IN["Nguồn message<br/>Gateway / inbound adapter"]
    CH1["MessageChannel"]
    FILTER["Filter / Transform / Router"]
    CH2["MessageChannel"]
    OUT["Service activator<br/>hoặc outbound adapter"]
    EXT["Hệ thống đích"]
    IN --> CH1 --> FILTER --> CH2 --> OUT --> EXT
~~~

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| `Message<?>` | Gói payload và headers để truyền qua flow. | Payload `Order`, header `traceId`. |
| `MessageChannel` | Nối các producer, consumer và quyết định cách chuyển giao message. | `DirectChannel`, `QueueChannel`. |
| Inbound adapter | Đọc/nhận sự kiện từ hệ thống bên ngoài và tạo message. | File watcher dùng poller, Kafka listener. |
| Transformer | Thay đổi biểu diễn payload, thường giữ nguyên các header cần thiết. | JSON thành đối tượng miền nghiệp vụ. |
| Filter | Chỉ cho các message hợp lệ đi tiếp; có thể loại hoặc chuyển hướng message bị từ chối. | Bỏ bản ghi thiếu mã giao dịch. |
| Router | Chọn channel đích theo dữ liệu hoặc header. | Chuyển VND/USD vào hai luồng xử lý. |
| Service activator / handler | Gọi logic xử lý; có thể tạo reply hoặc kết thúc luồng một chiều. | Lưu đơn hàng, gọi API. |
| Outbound adapter / gateway | Gửi dữ liệu đến đích; gateway thường cần phản hồi, adapter thường gửi một chiều. | Gửi JMS hoặc gọi HTTP API. |
| Poller | Chủ động kiểm tra nguồn hoặc tiêu thụ pollable channel theo chu kỳ. | Quét thư mục mỗi 5 giây. |

**Luồng một chiều** thường kết thúc ở handler không phát sinh reply hoặc outbound adapter. **Luồng request–reply** có đường về cho kết quả, chẳng hạn method được đánh dấu `@MessagingGateway` gọi flow và nhận một object trả về.

## 3. Từ Java DSL đến một bean IntegrationFlow

Một flow thường là một method `@Bean` trong class `@Configuration`:

~~~java
@Configuration
class BasicFlowConfiguration {

    @Bean
    IntegrationFlow uppercaseFlow() {
        return IntegrationFlow.from("text.input")
                .filter(String.class, text -> !text.isBlank())
                .transform(String.class, String::toUpperCase)
                .channel("text.output")
                .get();
    }
}
~~~

Trong ví dụ trên:

1. `from("text.input")` khai báo channel nhận message. Tên channel sẽ được Spring Integration giải quyết trong application context.
2. `filter(...)` kiểm tra payload chuỗi, bỏ qua chuỗi trắng; mặc định message bị từ chối không được chuyển xuống bước tiếp.
3. `transform(...)` tạo payload mới là chữ in hoa. Biến đổi payload không có nghĩa là phải đánh mất mọi header.
4. `channel("text.output")` chuyển message sang channel được đặt tên. Cần có consumer cho channel đó nếu kỳ vọng message được xử lý tiếp.
5. `get()` hoàn thành mô tả flow để Spring đăng ký các endpoint tương ứng.

`IntegrationFlow` là **bản khai báo**. Khi ứng dụng khởi tạo context, Spring Integration tạo và quản lý các endpoint, subscription và polling task thích hợp. Không gọi method `uppercaseFlow()` để gửi từng message; hãy gửi message tới channel đầu vào hoặc dùng gateway.

Để dùng DSL, với dự án Spring Boot đã có cấu hình quản lý dependency, có thể bắt đầu bằng:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
~~~

Ví dụ trong bài dùng Java 17 trở lên và cú pháp phổ biến của Spring Integration 6.x. Những adapter riêng như file, HTTP, JMS hoặc Kafka cần thêm module tương ứng. Khi đọc tài liệu cũ, lưu ý một số ví dụ dùng lớp factory `IntegrationFlows`; với các phiên bản hiện đại, có thể sử dụng trực tiếp `IntegrationFlow.from(...)`.

## 4. Ví dụ hoàn chỉnh: nhận đơn hàng bằng messaging gateway

Giả sử một ứng dụng cần nhận `Order`, từ chối đơn không có số tiền dương, chuyển đổi sang `PaymentCommand` và trả về `OrderResult`. Ví dụ này dùng handler nội bộ để tập trung vào DSL; nó **chưa thực hiện thu tiền thật**.

### 4.1. Code ứng dụng

~~~java
package demo.integration;

import java.math.BigDecimal;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.integration.dsl.IntegrationFlow;

@SpringBootApplication
@IntegrationComponentScan
public class OrderApplication {

    public static void main(String[] args) {
        var context = SpringApplication.run(OrderApplication.class, args);

        var gateway = context.getBean(OrderGateway.class);
        var result = gateway.submit(
                new Order("ORD-1001", new BigDecimal("250000"), "VND"));

        System.out.println(result);
    }

    @Bean
    IntegrationFlow orderFlow() {
        return IntegrationFlow.from("orders.input")
                .filter(Order.class,
                        order -> order.amount().signum() > 0,
                        endpoint -> endpoint.throwExceptionOnRejection(true))
                .transform(Order.class,
                        order -> new PaymentCommand(
                                order.id(), order.amount(), order.currency()))
                .handle(PaymentCommand.class,
                        (command, headers) -> new OrderResult(
                                command.orderId(), "ACCEPTED"))
                .get();
    }
}

@MessagingGateway(defaultRequestChannel = "orders.input")
interface OrderGateway {
    OrderResult submit(Order order);
}

record Order(String id, BigDecimal amount, String currency) {}

record PaymentCommand(String orderId, BigDecimal amount, String currency) {}

record OrderResult(String orderId, String status) {}
~~~

Ví dụ là một tệp `OrderApplication.java` trong package `demo.integration`. Tên lớp public phải trùng tên tệp. Các `record` và gateway interface có quyền truy cập package-private để ví dụ gọn; trong dự án thật có thể tách thành các tệp riêng.

### 4.2. Đường đi của request và reply

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant G as OrderGateway
    participant F as IntegrationFlow
    participant H as Handler
    C->>G: submit(Order)
    G->>F: Message<Order> vào orders.input
    F->>F: filter -> transform
    F->>H: Message<PaymentCommand>
    H-->>G: OrderResult qua replyChannel
    G-->>C: OrderResult
~~~

Điểm cần hiểu:

- `@IntegrationComponentScan` giúp Spring tìm và tạo proxy cho các interface được đánh dấu `@MessagingGateway` trong package được scan.
- `defaultRequestChannel = "orders.input"` trùng với channel đầu vào của flow.
- Gateway tạo message và bổ sung cơ chế chờ reply. Handler cuối trả một `OrderResult`; khi không còn bước xử lý kế tiếp, reply được gửi về kênh phản hồi tương ứng.
- `filter(..., endpoint -> endpoint.throwExceptionOnRejection(true))` chủ động báo lỗi nếu số tiền không hợp lệ. Nếu bỏ cấu hình này, filter mặc định loại message bị từ chối và request–reply có thể chờ đến lúc hết thời gian chờ.
- Ví dụ trên chạy theo đường gọi đồng bộ thông thường: người gọi nhận kết quả hoặc exception. Khi thay bằng channel bất đồng bộ, thời điểm xử lý, timeout và phạm vi transaction có thể thay đổi.

**Hợp đồng message:** đầu vào là `Order(id, amount, currency)`, trong đó `amount` phải lớn hơn 0; đầu ra thành công là `OrderResult(orderId, "ACCEPTED")`. Ví dụ dùng `currency = "VND"`; trường này có thể dùng cho router ở mục 5. Điều kiện dữ liệu, kiểu payload, tên channel và hành vi khi từ chối cần được thống nhất giữa các hệ thống kết nối. Với ví dụ sản xuất, nên kiểm tra thêm `id` không rỗng, `amount` khác `null`, mã tiền tệ hợp lệ và cơ chế chống xử lý trùng.

## 5. Các bước DSL thường dùng và cách kết hợp

### 5.1. `filter`: phân tách bản ghi hợp lệ và không hợp lệ

`filter` trả lời câu hỏi *message này có được tiếp tục không?*. Có hai lựa chọn phổ biến:

- **Bỏ qua hoặc gửi sang discard channel**: phù hợp dữ liệu được phép lọc; cần cân nhắc metric và audit trail.
- **Phát sinh exception**: phù hợp khi người gọi cần biết request không hợp lệ, như ví dụ đơn hàng.

Nếu bỏ qua message trong một flow có gateway đang chờ reply, phải quyết định rõ phản hồi trả cho caller là gì. Không nên để caller chờ mà không có tiêu chuẩn timeout.

### 5.2. `transform`: đổi payload nhưng giữ ngữ cảnh

Ví dụ chuyển từ bản ghi ngoài hệ thống sang DTO của ứng dụng:

~~~java
.transform(ExternalOrder.class,
        source -> new Order(
                source.externalId(),
                source.totalAmount()))
~~~

Hãy chuẩn hóa kiểu dữ liệu tại ranh giới hệ thống: timezone, đơn vị tiền tệ, encoding, tên trường, format ngày và khả năng dữ liệu null. Với header như `correlationId` hay `traceId`, bảo toàn qua các bước nếu còn cần để theo dõi và ghép phản hồi.

### 5.3. `route`: phân nhánh theo nội dung

Đoạn sau minh họa ý tưởng điều hướng theo trường `currency` của `PaymentCommand`. Hai channel `payments.vnd` và `payments.usd` cần có consumer tương ứng trong ứng dụng.

~~~java
.route(PaymentCommand.class, command -> command.currency(),
        mapping -> mapping
                .channelMapping("VND", "payments.vnd")
                .channelMapping("USD", "payments.usd"))
~~~

Router có thể cần default channel hoặc quy tắc xử lý khi không có mapping. Trường hợp currency khác dự kiến phải được xử lý rõ: từ chối, chuyển vào lỗi hoặc gửi sang nhánh kiểm duyệt.

### 5.4. `handle`: thực thi hành động cuối hoặc tạo reply

Một handler có thể gọi service nghiệp vụ. Nên tách logic nghiệp vụ phức tạp ra bean riêng, để flow chỉ mô tả cách các thành phần kết nối:

~~~java
.handle(PaymentCommand.class,
        (command, headers) -> paymentService.process(command))
~~~

Ở đây `paymentService` là dependency do ứng dụng cung cấp. Giá trị trả về của handler có thể là payload mới cho chặng kế hoặc reply cho gateway; `null` thường biểu thị không phát sinh reply. Nếu thiết kế one-way, tránh đặt một gateway đồng bộ đợi giá trị trả về không tồn tại.

### 5.5. `split` và `aggregate`: một thành nhiều, nhiều thành một

`split` chia collection hay message thành các message con. `aggregate` tập hợp chúng dựa trên thông tin tương quan và điều kiện hoàn tất nhóm. Khi sử dụng, cần trả lời trước:

- Dùng header/key nào để nhận diện cùng một nhóm?
- Khi nào nhóm được coi là đủ: đủ số phần, thỏa điều kiện nghiệp vụ hay hết thời gian chờ?
- Nếu ứng dụng restart giữa chừng, trạng thái tập hợp được lưu ở đâu?
- Một message bị gửi lặp có thể làm kết quả sai không?

Đây là các mối quan tâm về **hợp đồng và trạng thái message**, không chỉ về cú pháp DSL.

## 6. Chọn MessageChannel: đồng bộ, bộ đệm và bất đồng bộ

Trong flow, cách chọn channel ảnh hưởng trực tiếp đến thread, độ trễ, áp lực tải và ranh giới transaction.

| Loại channel | Đặc tính | Khi cân nhắc dùng |
| --- | --- | --- |
| `DirectChannel` | Bàn giao trực tiếp cho subscriber, thường xử lý trên thread gửi; phù hợp đồng bộ. | Chuỗi validate → transform → service xử lý nhanh. |
| `QueueChannel` | Lưu message trong bộ đệm và đợi consumer chủ động poll; cần quản lý dung lượng. | Tách tốc độ nguồn và đích khi có poller phù hợp. |
| `ExecutorChannel` | Chuyển việc xử lý sang `TaskExecutor`; có thể làm thay đổi ranh giới thread/transaction. | Tác vụ xử lý cần tách thread, đã xác định giới hạn executor. |
| `PublishSubscribeChannel` | Phân phát message tới nhiều subscriber. | Audit, metric và nhiều nhánh nhận cùng sự kiện. |

Các bước trong Java DSL có thể được nối trực tiếp qua channel ngầm hoặc tường minh qua `.channel(...)`. Đặt channel có tên khi cần tái sử dụng giữa các flow, có nhiều consumer, hoặc muốn quan sát/kiểm soát ranh giới xử lý.

**Lưu ý:** khai báo channel dạng queue không tự tạo consumer. Phía nhận cần poller hoặc endpoint tương thích; nếu không message có thể nằm chờ. Channel bất đồng bộ không đồng nghĩa với giao hàng bền vững: cần kiểm tra tính bền của message store, cơ chế retry và mất dữ liệu khi restart.

## 7. Ví dụ inbound adapter: poll file CSV rồi đưa vào flow

Một adapter chủ động đọc file thường cần poller. Với module `spring-integration-file` (được khai báo thông qua dependency riêng hoặc dependency management phù hợp), có thể mô tả:

~~~xml
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-file</artifactId>
</dependency>
~~~

~~~java
package demo.integration;

import java.io.File;
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.file.dsl.Files;

@Configuration
class FileFlowConfiguration {

    @Bean
    IntegrationFlow pollCsvFiles() {
        return IntegrationFlow.from(
                    Files.inboundAdapter(new File("./inbox"))
                            .patternFilter("*.csv"),
                    endpoint -> endpoint.poller(
                            Pollers.fixedDelay(Duration.ofSeconds(5))))
                .transform(File.class, File::getAbsolutePath)
                .channel("files.ready")
                .get();
    }

    @Bean
    IntegrationFlow processFilePaths() {
        return IntegrationFlow.from("files.ready")
                .handle(String.class, (path, headers) -> {
                    System.out.println("CSV file: " + path);
                    return null; // luồng một chiều
                })
                .get();
    }
}
~~~

Tạo thư mục `./inbox` trước khi chạy; đường dẫn được hiểu tương đối với working directory của ứng dụng. Ở mỗi lần poll, inbound adapter kiểm tra các file CSV phù hợp với filter; một file được phát ra dưới dạng payload `File`, sau đó transformer chuyển thành đường dẫn tuyệt đối `String`. Flow thứ hai là consumer của channel `files.ready` nên message có nơi nhận.

Đây là ví dụ **phát hiện file**, chưa đọc/parsing từng hàng CSV, chưa xử lý atomic move, file ghi dở, retry hay khôi phục. Khi triển khai thật, hãy quy định:

1. Tiêu chí file đã ghi xong (rename vào thư mục nhận, lock hoặc quy tắc riêng).
2. File nào đã được xử lý và cách tránh đọc trùng sau restart; filter chỉ là một phần của chiến lược idempotency.
3. Khi lỗi parsing/đẩy sang đích thì giữ lại, chuyển vào quarantine hay retry từ đâu.
4. Đường dẫn, quyền truy cập, charset, giới hạn kích thước và cách giám sát poller.

Có thể thay source ở đầu flow bằng SFTP inbound adapter, JMS/AMQP/Kafka message-driven inbound adapter, HTTP inbound gateway hoặc JDBC polling adapter. DSL xử lý phía sau vẫn dựa trên những khái niệm `Message`, `MessageChannel` và endpoint; riêng cơ chế nhận, kết nối, xác nhận (acknowledgement) và retry là đặc thù của từng giao thức.

## 8. Adapter, gateway và poller đặt ở đâu trong IntegrationFlow?

Một flow không bắt buộc chỉ có một kiểu đầu vào hoặc đầu ra. Cách tổ chức thường gặp:

~~~mermaid
flowchart TB
    subgraph Sources["Các cách đưa message vào"]
        FILE["File/SFTP inbound + Poller"]
        EVENT["JMS/AMQP/Kafka listener"]
        HTTPIN["HTTP inbound gateway"]
        API["Messaging gateway từ mã Java"]
    end
    PIPE["Validate → Transform → Route → Handle"]
    SINK["Outbound adapter / outbound gateway"]
    DEST["File, HTTP, database,<br/>JMS, AMQP, Kafka..."]
    FILE --> PIPE
    EVENT --> PIPE
    HTTPIN --> PIPE
    API --> PIPE
    PIPE --> SINK --> DEST
~~~

| Tình huống | Thành phần đầu/đích | Điểm cần quyết định |
| --- | --- | --- |
| Đọc thư mục hoặc SFTP định kỳ | Inbound adapter + poller | Tần suất poll, số file mỗi lần, checkpoint và file đang được ghi. |
| Nhận HTTP request và trả HTTP response | Inbound gateway | Mapping, chuyển đổi body, status code, timeout và exception. |
| Gửi message một chiều tới broker | Outbound adapter | Delivery/ack, serializer, retry, kho lưu message thất bại. |
| Gửi request tới hệ thống đích rồi nhận response | Outbound gateway | Timeout, định dạng trả về, lỗi khi hệ thống đích chậm hoặc mất kết nối. |
| Nhận sự kiện từ JMS/AMQP/Kafka | Message-driven inbound adapter | Concurrency, ack/offset, thứ tự, redelivery và idempotency. |
| Đọc thay đổi từ cơ sở dữ liệu định kỳ | JDBC inbound polling | Query chỉ lấy dữ liệu mới, transaction và dấu mốc lần đọc. |

**Adapter** thường đại diện việc nhận/gửi đơn hướng; **gateway** thể hiện trao đổi có phản hồi. **Poller** là một cơ chế lên lịch cho endpoint chủ động đọc/nhận, không phải mọi inbound endpoint đều dùng poller: message-driven endpoint thường nhận sự kiện từ callback/listener.

Không dùng tên API của connector như bằng chứng rằng xử lý đã an toàn trước duplicate hoặc đạt exactly-once. Với bất kỳ đích bên ngoài nào, cần xét lại semantics xác nhận, ranh giới transaction, retry và hành vi khi một bước đã thành công nhưng phản hồi bị mất.

## 9. Lỗi, phản hồi và khả năng quan sát

### 9.1. Phân biệt lỗi đồng bộ và lỗi bất đồng bộ

Trong một chuỗi đồng bộ với `DirectChannel`, exception từ filter, transformer hoặc handler thường lan trở lại gateway hoặc bên gửi. Với poller, executor hoặc listener chạy ở thread khác, exception được xử lý tại endpoint tương ứng và có thể được phát thành `ErrorMessage` tới một `errorChannel` được cấu hình.

Vì vậy, cần thiết kế **đường lỗi** theo đường thực tế của từng kiểu flow:

- **Request–reply:** chuẩn hóa exception thành error response có mã lỗi nghiệp vụ; đặt timeout đủ rõ cho request và reply.
- **One-way inbound:** chọn retry/backoff, error channel, dead-letter/quarantine hoặc lưu lại sự kiện để xử lý sau.
- **Outbound có side effect:** chỉ retry khi hiểu hành vi của đích; dùng idempotency key hoặc cơ chế chống trùng để giảm nguy cơ ghi/gửi hai lần.
- **Filter loại message:** phân biệt bản ghi *không cần xử lý* với bản ghi *lỗi cần báo cáo*; ghi metric hoặc audit phù hợp.

### 9.2. Tránh mất header quan trọng

Transformer/handler có thể tạo message mới. Khi làm như vậy, cần chú ý những header phục vụ reply, tương quan và tracing. Tốt nhất ghi rõ quy ước payload, kiểu header, mã correlation và nơi sinh idempotency key ở ranh giới tích hợp.

Ví dụ một message request có:

~~~text
payload = Order(id="ORD-1001", amount=250000, currency="VND")
headers = {
    correlationId: "order-ORD-1001",
    traceId: "...",
    replyChannel: <kênh tạm dùng trả kết quả>
}
~~~

`replyChannel` trong ví dụ là đối tượng channel chứ không nhất thiết là chuỗi; phía gateway thường xử lý chi tiết này. Không log nguyên thông tin nhạy cảm trong payload/headers. Với HTTP và broker, định dạng header truyền đi được giới hạn bởi giao thức và mapper cụ thể.

### 9.3. Vòng đời kết nối và tài nguyên

Spring quản lý bean của flow và endpoint, nhưng vẫn phải cấu hình đúng việc khởi động/dừng adapter, thread pool, connection factory, session cache, poller và listener container. Khi chạy nhiều instance, cần xác định liệu mỗi instance được quyền poll cùng nguồn hay phải phối hợp lock/partition. Nên thu thập metric tối thiểu gồm số message vào/ra, số lỗi, độ trễ, độ sâu queue và thời gian xử lý tại outbound.

## 10. Cách kiểm thử một IntegrationFlow

Với ví dụ `OrderGateway` ở mục 4, nên kiểm tra qua **giao diện đầu vào thật** của flow thay vì gọi trực tiếp bean method trả về `IntegrationFlow`:

~~~java
package demo.integration;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.integration.MessageRejectedException;

@SpringBootTest
class OrderFlowTest {

    @Autowired
    OrderGateway gateway;

    @Test
    void validOrderReturnsAccepted() {
        var result = gateway.submit(
                new Order("ORD-1001", new BigDecimal("250000"), "VND"));

        assertEquals("ORD-1001", result.orderId());
        assertEquals("ACCEPTED", result.status());
    }

    @Test
    void nonPositiveAmountIsRejected() {
        assertThrows(MessageRejectedException.class,
                () -> gateway.submit(
                        new Order("ORD-1002", BigDecimal.ZERO, "VND")));
    }
}
~~~

Dependency test cho dự án Spring Boot:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Kiểm thử này xác minh đường đi tích hợp thực sự: Spring đăng ký gateway, chuyển message vào channel, gọi filter → transformer → handler và trả kết quả. Tùy cấu hình gateway, phiên bản thư viện và tầng chuyển exception, loại exception nhìn thấy tại caller có thể được bọc trong một exception khác; nếu vậy hãy khẳng định *nguyên nhân gốc* thay vì phụ thuộc vào đúng lớp exception lớp ngoài.

Với adapter thật, mở rộng kiểm thử theo phạm vi hệ thống: tạo file trong thư mục tạm, chạy listener test với broker thử nghiệm, giả lập HTTP timeout, kiểm tra duplicate/retry và teardown tài nguyên sau test. Không cần khởi động SFTP/Kafka/DB thật chỉ để kiểm thử logic `transform` thuần túy; ưu tiên tách logic đó thành hàm/service kiểm thử độc lập.

## 11. Lỗi thiết kế thường gặp và cách nhận diện

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Gateway chờ mãi rồi timeout. | Flow không phát reply; filter âm thầm loại message; kết quả gửi sai channel. | Xác định rõ đường reply; cho filter phát lỗi hoặc phản hồi nghiệp vụ; cấu hình timeout. |
| Message vào channel nhưng không được xử lý. | Không có subscriber hoặc chưa có consumer poll queue. | Kiểm tra tên channel, endpoint đang chạy và cấu hình poller. |
| Xử lý lặp file/sự kiện. | Redelivery, restart, polling lại hoặc xác nhận thất bại. | Dùng checkpoint/idempotency key, quy tắc archive và ack phù hợp. |
| Transaction không bao phủ chặng sau. | Chuyển thread tại executor, queue hoặc broker. | Xác định lại ranh giới giao dịch; dùng outbox/saga hoặc cơ chế bù trừ khi cần. |
| Độ trễ tăng đột biến. | Handler chặn thread lâu, queue đầy, poller không đủ nhịp, đích chậm. | Đo độ sâu queue, giới hạn concurrency, timeout, batch và backpressure. |
| Khó biết message lỗi ở đâu. | Thiếu correlation ID, thiếu error flow hoặc log không nhất quán. | Chuẩn hóa metadata, metric và nơi tập trung message lỗi. |
| Dữ liệu đã gửi ra ngoài nhưng client thấy lỗi. | Đích xử lý thành công rồi mất response; retry có thể gây duplicate. | Thiết kế retry có idempotency, phân biệt kết quả chưa rõ với thất bại chắc chắn. |

## 12. Bài thực hành tự làm

**Yêu cầu:** tạo một flow `orderRoutingFlow` nhận đơn hàng qua gateway, kiểm tra `orderId` không rỗng và `amount > 0`, chuyển sang `PaymentCommand` rồi phân nhánh theo `currency`:

- `VND` đi tới handler giả lập thanh toán nội địa.
- `USD` đi tới handler giả lập thanh toán quốc tế.
- Mã tiền tệ khác phải nhận thông báo lỗi có thể kiểm tra được.
- Hai nhánh đều trả cùng kiểu `OrderResult` về gateway.

**Tiêu chí hoàn thành:** có test đường thành công cho mỗi currency, test dữ liệu không hợp lệ, test currency không hỗ trợ và giải thích được reply di chuyển qua channel nào. Sau đó thêm một inbound file adapter đọc CSV vào cùng logic nghiệp vụ, nhưng chọn cách chuẩn hóa mỗi hàng thành `Order` trước khi đưa vào channel chung; thử gửi lặp cùng `orderId` và đề xuất cách chặn xử lý hai lần.

Gợi ý thiết kế: tách validation/normalize trước bước router; các nhánh xử lý trả về một kiểu kết quả thống nhất; đối với đầu vào một chiều từ file, quyết định rõ nơi lưu kết quả và lỗi vì không có HTTP caller chờ reply.

## 13. Ghi nhớ

`IntegrationFlow` bằng Java DSL là cách **khai báo tuyến đi của message** thông qua các endpoint Spring quản lý. Một flow tốt cần rõ bốn yếu tố: nguồn vào và hợp đồng payload/headers, các bước biến đổi/điều hướng, channel cùng cơ chế đồng bộ hay polling, và đích đến kèm đường xử lý lỗi.

Khi kết nối file, SFTP, HTTP, JMS, AMQP, Kafka hay database, phần Java DSL giúp tái sử dụng mô hình message và cách nối các bước. Độ tin cậy cuối cùng vẫn phụ thuộc vào giao thức, cơ chế xác nhận, timeout, retry, idempotency và vòng đời kết nối đã được thiết kế, cấu hình và kiểm thử phù hợp.

