# DirectChannel và gọi handler theo chuỗi

## 1. Mục tiêu bài học

Trong chương **Message channel** của module **SPRING_INTEGRATION_PATTERN**, chúng ta học cách kết nối các thành phần theo **Enterprise Integration Patterns** bằng Spring Integration. Module hướng tới việc tạo luồng message ít phụ thuộc, dễ mở rộng; triển khai Router, Filter, Transformer, Splitter, Aggregator, Gateway; xử lý retry, error channel và correlation; đồng thời kiểm thử, theo dõi các nhánh xử lý.

Bài này tập trung vào **DirectChannel**: một kênh **point-to-point, đồng bộ**, chuyển message trực tiếp từ producer tới một handler được chọn trên **chính thread đang gọi send()**. Để tạo một quy trình xử lý nhiều bước, ta kết nối các handler bằng các channel liên tiếp hoặc sử dụng IntegrationFlow.

Sau bài học, bạn có thể:

1. Giải thích cách DirectChannel chọn handler và ý nghĩa của xử lý đồng bộ.
2. Phân biệt **nhiều subscriber trên cùng một DirectChannel** với **nhiều handler nối tiếp trong một flow**.
3. Tạo chuỗi **validate → transform → handle** bằng Java và Spring Integration DSL.
4. Dự đoán cách exception, transaction và thread ảnh hưởng đến toàn bộ chuỗi.
5. Kiểm thử đúng thứ tự gọi, dữ liệu trung gian và hành vi khi có lỗi.

## 2. DirectChannel hoạt động như thế nào?

Trong Spring Integration, **MessageChannel** là ranh giới truyền message. **DirectChannel** triển khai giao diện **SubscribableChannel** và sử dụng cơ chế dispatch đến một subscriber. Producer gửi message bằng **send()**; handler nhận message thông qua phương thức **handleMessage()**.

~~~mermaid
flowchart LR
    P["Producer<br/>thread T1"] -->|"send(message)"| C["DirectChannel"]
    C -->|"Gọi trực tiếp trên T1"| H["Một MessageHandler"]
    H -->|"Trả về hoặc ném lỗi"| P
~~~

Ba đặc điểm quan trọng:

- **Đồng bộ:** send() gọi handler trực tiếp; trong tình huống bình thường, phương thức send() chỉ hoàn tất sau khi handler hoàn tất.
- **Cùng thread:** handler chạy trên thread của sender, không mặc định chuyển sang thread pool.
- **Point-to-point:** mỗi lần dispatch, một handler được chọn để nhận message; đây không phải cơ chế broadcast.

Ví dụ, một HTTP request gọi service, service gửi message vào DirectChannel, rồi handler thực hiện thao tác trong cùng luồng thực thi. Lúc đó thời gian xử lý ở handler là một phần của thời gian trả lời HTTP request.

| Thuộc tính | DirectChannel |
| --- | --- |
| Cơ chế nhận message | Đăng ký subscriber (MessageHandler) |
| Số handler nhận một lần gửi | Một handler được dispatcher chọn |
| Thread thực thi | Thread gọi send(), trừ khi handler tự chủ động đổi thread |
| Buffer/queue mặc định | Không có |
| Backpressure bằng hàng đợi | Không có hàng đợi nội bộ để hấp thụ đột biến |
| Lỗi từ handler | Có thể truyền ngược theo call stack tới sender |
| Transaction của sender | Có thể tiếp tục qua các bước đồng bộ cùng thread |
| Công dụng thường gặp | Các bước xử lý nội bộ cần kết quả ngay, độ trễ thấp |

### Nhiều subscriber không tạo thành chuỗi

Giả sử cùng một DirectChannel đăng ký ba handler A, B, C:

~~~mermaid
flowchart TB
    P["Producer"] --> D["DirectChannel"]
    D -.->|"Chọn một subscriber"| A["Handler A"]
    D -.->|"Hoặc"| B["Handler B"]
    D -.->|"Hoặc"| C["Handler C"]
~~~

Các handler này là **các ứng viên nhận message**, chứ **không phải** thứ tự A → B → C. DirectChannel dùng **UnicastingDispatcher**; khi có nhiều subscriber, chiến lược load balancing và failover quyết định handler nào nhận, và có thử handler khác khi lỗi hay không. Các giá trị mặc định hoặc tùy chọn cụ thể phụ thuộc cấu hình/phiên bản Spring Integration.

Nếu yêu cầu là *mọi message phải đi qua A, rồi B, rồi C*, hãy xây dựng luồng nối tiếp có đầu ra của A đi đến B và đầu ra của B đi đến C. Không đăng ký cả ba lên cùng một DirectChannel rồi kỳ vọng chúng được gọi lần lượt.

## 3. Chuỗi xử lý đồng bộ: A → B → C

Mỗi bước có thể gửi message đến **DirectChannel kế tiếp**. Vì các send() được lồng nhau trên cùng thread, luồng chạy có dạng:

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant C1 as inputChannel
    participant A as Validate handler
    participant C2 as validatedChannel
    participant B as Transform handler
    participant C3 as invoiceChannel
    participant C as Invoice handler
    P->>C1: send(order)
    C1->>A: handleMessage(order)
    A->>C2: send(validatedOrder)
    C2->>B: handleMessage(validatedOrder)
    B->>C3: send(invoiceCommand)
    C3->>C: handleMessage(invoiceCommand)
    C-->>C3: return
    C3-->>B: return
    B-->>C2: return
    C2-->>A: return
    A-->>C1: return
    C1-->>P: send() hoàn tất
~~~

Điểm mấu chốt: **DirectChannel không tự xây dựng pipeline**. Việc gọi theo chuỗi hình thành từ cách các endpoint và channel được nối với nhau.

### 3.1. Ví dụ Java với ba DirectChannel

Ví dụ dưới đây dùng Java 17+ (record) và các lớp Spring Integration/Spring Messaging. Để thấy rõ cơ chế, ta chủ động đăng ký từng handler. Trong ứng dụng thực tế, nên cấu hình các endpoint bằng bean hoặc IntegrationFlow để Spring quản lý vòng đời.

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

record OrderPlaced(String orderId, BigDecimal amount) {}
record InvoiceCommand(String orderId, BigDecimal amount) {}

DirectChannel inputChannel = new DirectChannel();
DirectChannel validatedChannel = new DirectChannel();
DirectChannel invoiceChannel = new DirectChannel();

List<String> steps = new ArrayList<>();

// Handler 1: kiểm tra dữ liệu rồi gửi đến channel tiếp theo.
inputChannel.subscribe(message -> {
    steps.add("validate");
    OrderPlaced order = (OrderPlaced) message.getPayload();

    if (order.orderId() == null || order.orderId().isBlank()
            || order.amount() == null
            || order.amount().signum() <= 0) {
        throw new IllegalArgumentException("Đơn hàng không hợp lệ");
    }

    validatedChannel.send(message);
});

// Handler 2: đổi payload và đánh dấu loại sự kiện.
validatedChannel.subscribe(message -> {
    steps.add("transform");
    OrderPlaced order = (OrderPlaced) message.getPayload();

    Message<InvoiceCommand> next =
            MessageBuilder.withPayload(
                    new InvoiceCommand(order.orderId(), order.amount()))
                    .copyHeaders(message.getHeaders())
                    .setHeader("eventType", "invoice.requested")
                    .build();

    invoiceChannel.send(next);
});

// Handler 3: thực hiện tác vụ cuối cùng.
invoiceChannel.subscribe(message -> {
    steps.add("invoice");
    InvoiceCommand command = (InvoiceCommand) message.getPayload();
    System.out.println("Create invoice for " + command.orderId());
});

Message<OrderPlaced> event = MessageBuilder.withPayload(
                new OrderPlaced("ORD-42", new BigDecimal("125000")))
        .setHeader("eventType", "order.placed")
        .setHeader("correlationId", "ORD-42")
        .build();

boolean accepted = inputChannel.send(event);

System.out.println(accepted); // true khi dispatch thành công
System.out.println(steps);    // [validate, transform, invoice]
~~~

Ở đây, **mỗi DirectChannel có đúng một subscriber** nên hành vi dễ hiểu và dễ dự đoán. Lần lượt:

1. Producer gửi **OrderPlaced** vào inputChannel.
2. Handler kiểm tra dữ liệu, sau đó gọi **validatedChannel.send(message)**.
3. Handler thứ hai tạo **InvoiceCommand** và gửi vào invoiceChannel.
4. Handler cuối thực thi nghiệp vụ và trả về.
5. Sau khi các lời gọi lồng nhau hoàn tất, **inputChannel.send()** mới trả về.

Việc **copyHeaders** cần có chủ đích: ví dụ giữ lại correlationId để theo dõi đơn hàng nhưng thay eventType từ order.placed thành invoice.requested. Không sao chép mù quáng header chỉ có giá trị ở bước trước hoặc thông tin nhạy cảm. MessageBuilder xây dựng message mới; không sửa payload/headers của message gốc.

> **Lưu ý thực tế:** ví dụ dùng List để quan sát các bước trong một lần chạy. Trong service phục vụ nhiều request đồng thời, không dùng chung một ArrayList không đồng bộ cho việc ghi nhận hoạt động. Hãy dùng log/tracing theo correlationId hoặc công cụ quan sát tương ứng.

### 3.2. Vì sao một flow đồng bộ lại “gọi theo chuỗi”?

Nếu xem các lệnh send() như những lời gọi hàm, stack khi đang ở bước cuối có thể hình dung:

~~~text
producer.publish()
  inputChannel.send(order)
    validateHandler.handleMessage(order)
      validatedChannel.send(order)
        transformHandler.handleMessage(order)
          invoiceChannel.send(invoice)
            invoiceHandler.handleMessage(invoice)
~~~

Không có message queue trung gian và không mặc định tạo thread mới. Bởi vậy DirectChannel phù hợp khi những bước cần kiểm tra/biến đổi nhanh, cùng một transaction hoặc cùng context xử lý.

## 4. Thiết kế chuỗi bằng Spring Integration Java DSL

Đăng ký handler bằng **subscribe()** rất hữu ích để học cơ chế, nhưng khi xây dựng ứng dụng Spring, **IntegrationFlow** giúp khai báo rõ pipeline nghiệp vụ.

Ví dụ minh họa một flow nhận OrderPlaced, lọc đơn hàng hợp lệ, biến đổi thành InvoiceCommand và gọi service:

~~~java
import java.math.BigDecimal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class OrderIntegrationConfig {

    @Bean
    MessageChannel orderInputChannel() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow orderFlow(InvoiceService invoiceService) {
        return IntegrationFlow.from("orderInputChannel")
                .filter(OrderPlaced.class, order ->
                        order.amount() != null
                        && order.amount().signum() > 0)
                .transform(OrderPlaced.class, order ->
                        new InvoiceCommand(order.orderId(), order.amount()))
                .handle(InvoiceCommand.class, (command, headers) -> {
                    invoiceService.create(command);
                    return null; // endpoint cuối không phát message tiếp
                })
                .get();
    }
}

interface InvoiceService {
    void create(InvoiceCommand invoice);
}

record OrderPlaced(String orderId, BigDecimal amount) {}
record InvoiceCommand(String orderId, BigDecimal amount) {}
~~~

**Flow thực hiện tuần tự** qua Filter → Transformer → Service Activator. Với pipeline mặc định đồng bộ sử dụng các channel trực tiếp giữa endpoint, từng bước gọi ngay bước kế tiếp trên cùng thread. Các channel trung gian do DSL quản lý, vì vậy ví dụ không cần đặt tên cho mọi channel.

Nếu một đơn hàng không đạt điều kiện Filter, mặc định message sẽ bị loại khỏi flow, và các bước phía sau **không** chạy. Tùy yêu cầu, có thể cấu hình discard channel hoặc ném exception khi bị từ chối. Vì vậy, **send() trả về true không có nghĩa mọi message đều tới InvoiceService**.

Trong code sản phẩm, bổ sung kiểm tra orderId và quy ước rõ cách xử lý đơn không hợp lệ. Đối với các bước cần tách nhánh, có thể thêm Router; đối với payload danh sách, có thể thêm Splitter rồi Aggregator có correlation/sequence phù hợp. Những lựa chọn này cần dựa trên hợp đồng message, không chỉ dựa trên dạng pipeline.

## 5. Thread, thứ tự và khả năng đồng thời

### 5.1. Cùng thread cho một lần gửi

Nếu thread **T1** gọi send(), các handler đồng bộ của pipeline sẽ chạy trên T1. Các bước được thực thi **theo thứ tự trong một lần gửi**, và call stack phản ánh đúng chuỗi xử lý.

Tuy nhiên, hai producer có thể cùng gọi send() từ **T1** và **T2** vào cùng một DirectChannel:

~~~mermaid
flowchart LR
    P1["Request 1 / T1"] --> D["DirectChannel"]
    P2["Request 2 / T2"] --> D
    D --> H["Một handler logic"]
    H --> S["Dịch vụ nghiệp vụ"]
~~~

Khi đó handler có thể được gọi đồng thời từ hai thread. DirectChannel **không tuần tự hóa mọi request trên toàn hệ thống** và **không bảo đảm thứ tự toàn cục** giữa các lần send() từ nhiều sender.

Những hệ quả khi thiết kế:

- Handler cần **thread-safe** nếu có trạng thái dùng chung.
- Không giả định request A gửi trước thì chắc chắn hoàn tất trước request B.
- Nếu phải bảo toàn thứ tự theo khóa nghiệp vụ, cần cơ chế phù hợp: khóa theo khóa định tuyến, partition, hoặc thành phần có hàng đợi/consumer được kiểm soát.
- Tránh block lâu trong handler vì điều đó giữ thread của người gửi.

### 5.2. So với các channel khác

| Channel | Cách phân phối | Đặc tính so với DirectChannel |
| --- | --- | --- |
| **DirectChannel** | Unicast, gọi handler đồng bộ | Không có queue; cùng thread sender |
| **ExecutorChannel** | Unicast, chuyển xử lý qua Executor | Tách thread; không giữ nguyên transaction thread-bound |
| **QueueChannel** | PollableChannel, giữ message trong queue | Producer và consumer tách theo thời gian; cần poller/consumer |
| **PublishSubscribeChannel** | Phân phối tới nhiều subscriber | Phù hợp fan-out; mặc định có thể đồng bộ, nhưng semantics khác |
| **RendezvousChannel** | Sender/receiver hẹn nhau để trao message | Tạo điểm đồng bộ giữa hai bên thay vì gọi trực tiếp subscriber |

Không chọn ExecutorChannel hoặc QueueChannel chỉ để “tăng tốc” nếu downstream bắt buộc hoàn tất trước khi producer trả về. Ngược lại, không dùng DirectChannel cho công việc chậm chỉ vì code trông ngắn hơn; nó có thể kéo dài thời gian đáp ứng và giảm thông lượng của thread tiếp nhận request.

## 6. Exception và transaction đi qua chuỗi như thế nào?

### 6.1. Exception trong handler

Với DirectChannel đồng bộ, nếu handler ném exception và không có tầng nào bắt lỗi, lời gọi send() thường kết thúc bằng exception truyền ngược theo call stack; tùy dispatcher và endpoint, exception có thể được bọc trong exception thuộc hệ thống messaging.

~~~java
DirectChannel input = new DirectChannel();

input.subscribe(message -> {
    throw new IllegalStateException("Không kết nối được dịch vụ đích");
});

try {
    input.send(MessageBuilder.withPayload("ORD-42").build());
} catch (RuntimeException ex) {
    // Ghi log có correlationId, áp dụng retry/báo lỗi
    // theo chính sách của ứng dụng.
}
~~~

Không giả định rằng mọi exception từ send() sẽ tự động xuất hiện ở một **errorChannel**. Việc phát **ErrorMessage** tới error channel phụ thuộc cách flow/gateway/adapter và trình xử lý lỗi được cấu hình. Khi thread đổi qua ExecutorChannel hoặc poller, cơ chế lan truyền exception về bên gửi cũng khác.

Nếu **DirectChannel có nhiều subscriber**, cấu hình **failover** có thể khiến dispatcher thử một subscriber khác khi handler đầu tiên thất bại. Đây không phải retry nghiệp vụ tự động; cần thận trọng với thao tác có tác dụng phụ đã được thực hiện một phần trước khi lỗi xảy ra.

### 6.2. Transaction

DirectChannel chạy trên thread hiện tại, vì vậy có thể tham gia cùng **thread-bound transaction context** của producer khi transaction được Spring quản lý. Ví dụ: một service có @Transactional gửi message vào chuỗi DirectChannel, và handler cuối gọi repository; các thao tác cơ sở dữ liệu dùng cùng transaction manager có thể nằm trong một transaction.

Tuy nhiên, điều này **không** tạo transaction phân tán cho HTTP call, email, broker hay các hệ thống ngoài. Handler gửi thành công một request ra ngoài rồi thao tác DB sau đó rollback có thể dẫn đến trạng thái lệch nhau. Khi cần độ tin cậy liên hệ thống, cân nhắc outbox, idempotency, retry có giới hạn, hoặc cơ chế giao dịch được hệ thống hỗ trợ.

| Tình huống | Điều nên kỳ vọng |
| --- | --- |
| DirectChannel → handler đồng bộ → repository cùng transaction manager | Có thể tham gia transaction của sender |
| DirectChannel → ExecutorChannel → handler | Thường đổi thread; transaction của sender không tự truyền qua |
| DirectChannel → HTTP/broker adapter | Remote side effect không tự rollback theo DB |
| Handler ném lỗi ở giữa chuỗi | Những bước sau không chạy trên đường đi thông thường; transaction có thể rollback theo chính sách |
| Handler đã có side effect trước khi ném lỗi | Cần thiết kế idempotent/compensating action, không mặc định được hoàn tác |

## 7. Quy tắc thiết kế chuỗi handler dễ bảo trì

### Mỗi bước một trách nhiệm

Nên tách Validate, Transform và Act thành các thành phần có hợp đồng rõ ràng:

- **Validate:** kiểm tra tính hợp lệ và phát lỗi hoặc route sang discard; không thực hiện side effect chưa cần thiết.
- **Transform:** xây dựng payload mới mà giữ những headers thật sự có ý nghĩa.
- **Handle:** thực hiện hành động nghiệp vụ, ví dụ lưu hóa đơn, phát sự kiện hoặc gọi hệ thống ngoài.

Khi cần Router, nhánh sau Router có thể tiếp tục bằng DirectChannel riêng; khi dùng Filter cần định nghĩa rõ điều kiện từ chối; khi dùng Splitter/Aggregator cần giữ correlation và sequence metadata đúng chuẩn.

### Một channel chỉ nên có một vai trò rõ ràng

Đặt tên channel theo mục đích, chẳng hạn **orderInputChannel**, **validatedOrdersChannel**, **invoiceCommandsChannel**. Hạn chế dùng cùng một channel vừa để gửi lệnh nghiệp vụ vừa để đưa kết quả phản hồi thuộc kiểu khác nếu không có hợp đồng rõ.

### Thiết kế khả năng quan sát

Theo dõi các thông tin:

| Dữ liệu theo dõi | Ý nghĩa |
| --- | --- |
| correlationId hoặc business key | Nối các bước của cùng giao dịch |
| traceId/spanId | Theo dõi call stack và đường đi qua thành phần |
| Tên channel/endpoint | Xác định bước nào nhận message |
| Thời gian xử lý từng handler | Phát hiện bước chiếm thời gian |
| Tỷ lệ lỗi/rejection | Phân biệt lỗi hạ tầng và dữ liệu bị Filter loại |

Đừng log toàn bộ payload/headers nếu chứa dữ liệu nhạy cảm. Có thể dùng metric, observation/tracing hoặc interceptor phù hợp với phiên bản Spring Integration và công cụ vận hành; kiểm tra việc thu thập đó không làm lộ thông tin.

## 8. Kiểm thử thứ tự handler và lỗi

Test đầu tiên kiểm chứng hai đặc tính quan trọng của DirectChannel: **cùng thread** và **gọi theo chuỗi khi ta nối các channel**.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.support.MessageBuilder;

class DirectChannelChainTest {

    @Test
    void callsHandlersInOrderOnTheSenderThread() {
        DirectChannel first = new DirectChannel();
        DirectChannel second = new DirectChannel();
        DirectChannel third = new DirectChannel();

        List<String> calls = new ArrayList<>();
        Thread sender = Thread.currentThread();
        AtomicReference<Thread> lastHandlerThread = new AtomicReference<>();

        first.subscribe(message -> {
            calls.add("validate");
            second.send(message);
        });
        second.subscribe(message -> {
            calls.add("transform");
            third.send(MessageBuilder
                    .withPayload(((String) message.getPayload()).trim())
                    .copyHeaders(message.getHeaders())
                    .build());
        });
        third.subscribe(message -> {
            calls.add("handle:" + message.getPayload());
            lastHandlerThread.set(Thread.currentThread());
        });

        boolean accepted = first.send(
                MessageBuilder.withPayload(" ORD-42 ").build());

        assertTrue(accepted);
        assertEquals(List.of("validate", "transform", "handle:ORD-42"),
                calls);
        assertSame(sender, lastHandlerThread.get());
    }

    @Test
    void failureStopsTheNextStepAndReachesTheCaller() {
        DirectChannel first = new DirectChannel();
        DirectChannel second = new DirectChannel();

        List<String> calls = new ArrayList<>();
        first.subscribe(message -> {
            calls.add("validate");
            throw new IllegalArgumentException("Dữ liệu không hợp lệ");
        });
        second.subscribe(message -> calls.add("should-not-run"));

        assertThrows(RuntimeException.class,
                () -> first.send(
                        MessageBuilder.withPayload("bad").build()));
        assertEquals(List.of("validate"), calls);
    }
}
~~~

Test 1 khẳng định các handler được gọi theo thứ tự trong cùng một send() nhờ cách nối first → second → third. Test 2 khẳng định khi handler đầu ném lỗi và không gửi tiếp, handler sau không chạy. Đây là test hành vi cục bộ, không kiểm chứng transaction, broker, routing động hoặc các cấu hình error channel phức tạp.

Trong kiểm thử IntegrationFlow thực tế, nên bổ sung tình huống Filter reject, nhiều producer đồng thời, một handler bị chậm, và đường đi qua Router; sử dụng dữ liệu kiểm thử có correlationId để lần theo từng message.

## 9. Những nhầm lẫn thường gặp

| Nhầm lẫn | Vì sao sai | Cách hiểu đúng |
| --- | --- | --- |
| Đăng ký A, B, C trên cùng DirectChannel sẽ gọi A → B → C | Dispatcher là unicast | Dùng các channel nối tiếp hoặc IntegrationFlow |
| DirectChannel có sẵn queue | Nó không buffer message | Dùng QueueChannel khi cần tách thời gian gửi/nhận |
| DirectChannel luôn chỉ có một thread | Mỗi send dùng thread riêng của producer | Các sender khác nhau có thể chạy đồng thời |
| send() trả true nghĩa là cả nghiệp vụ đã thành công | Flow có thể có Filter, nhánh khác hoặc side effect ngoài hệ thống | Xác định acknowledgment theo yêu cầu nghiệp vụ |
| Exception luôn tự đi vào errorChannel | Còn phụ thuộc endpoint và cấu hình xử lý lỗi | Đặt chính sách error handling rõ ràng |
| Gắn @Transactional là rollback được HTTP/broker | Transaction local không bao trùm remote side effect | Thiết kế outbox/idempotency/compensation khi cần |
| Nhiều subscriber bảo đảm chia đều tải | Load balancing/failover tùy cấu hình, tải handler có thể khác nhau | Đo thực tế và cấu hình chiến lược phù hợp |
| Thay DirectChannel bằng ExecutorChannel không ảnh hưởng semantics | Thread, transaction, exception propagation thay đổi | Thiết kế ranh giới async và kiểm thử lại |

## 10. Bài thực hành: xử lý đơn hàng theo ba bước

Giả sử một hệ thống nhận sự kiện **order.placed** và cần:

1. **Validate:** tổng tiền dương, orderId không rỗng.
2. **Enrich/Transform:** tạo record **PaymentRequest(orderId, amount, tenantId)**, gắn header eventType=payment.requested.
3. **Handle:** gọi PaymentService xử lý yêu cầu, ghi nhận kết quả và correlationId.

Hãy triển khai một **IntegrationFlow đồng bộ** bắt đầu từ DirectChannel **orderInputChannel**. Tạo hai bài kiểm thử:

- Khi đơn hợp lệ, cả ba bước được gọi theo thứ tự và PaymentService nhận đúng dữ liệu.
- Khi đơn không hợp lệ, bước Transform và PaymentService không được gọi; quyết định rõ Filter sẽ loại message hay ném lỗi.

Sau đó thử thay một ranh giới bằng **ExecutorChannel** và trả lời: thread nào thực hiện handler cuối? Exception từ PaymentService còn truyền trực tiếp về producer không? Transaction của producer có tự tồn tại ở thread mới không?

**Câu hỏi tự kiểm tra:**

1. Vì sao một DirectChannel có ba subscriber không tạo thành chuỗi ba handler?
2. Trường hợp nào nên chọn DirectChannel thay cho ExecutorChannel hoặc QueueChannel?
3. Một flow dùng DirectChannel có bảo đảm mọi message trên hệ thống được xử lý theo thứ tự không?
4. Điều gì xảy ra nếu handler ở giữa ném exception trước khi gửi đến channel tiếp theo?
5. Khi nào việc giữ chung transaction là một lợi thế, và giới hạn của nó với hệ thống ngoài là gì?

## 11. Checklist áp dụng DirectChannel

- Xác định luồng cần **đồng bộ** hay bất đồng bộ ngay từ đầu.
- Ghi rõ mỗi channel phân phối **một message cho một handler được chọn**; dùng flow nối tiếp nếu cần nhiều bước.
- Đảm bảo handler thread-safe và không giữ thread producer quá lâu.
- Quy định rõ hành vi với dữ liệu bị Filter loại và các exception ở từng bước.
- Kiểm thử thứ tự xử lý, thread thực thi, metadata/correlation và luồng lỗi.
- Xem xét tác động đến transaction và các side effect ngoài hệ thống.
- Theo dõi độ trễ theo từng endpoint và hạn chế log dữ liệu nhạy cảm.

**Kết luận thực hành:** DirectChannel là lựa chọn phù hợp cho đoạn xử lý Spring Integration cần lời gọi ngay, chạy trong cùng thread và liên kết rõ với caller. “Gọi handler theo chuỗi” là kết quả của **kiến trúc flow**: mỗi handler tiếp tục gửi sang bước kế tiếp, hoặc DSL kết nối các endpoint. Hiểu sự khác biệt này giúp Router, Filter, Transformer và các thành phần khác phối hợp có thể dự đoán và kiểm thử được.

## Tài liệu tham khảo

- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): các loại MessageChannel, DirectChannel và những điểm khác biệt khi dispatch.
- [Spring Integration Reference — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): định nghĩa IntegrationFlow và các endpoint theo chuỗi.
- [Spring Integration API — DirectChannel](https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/DirectChannel.html): giao diện và cấu hình DirectChannel.
- [Spring Framework Reference — Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): phạm vi transaction và cơ chế gắn context vào thread.
