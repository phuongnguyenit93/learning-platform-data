# Tránh tạo bridge vòng

**Chương:** Bridge  
**Chủ đề:** Tránh tạo bridge vòng  
**Phạm vi học tập:** `SPRING_INTEGRATION_PATTERN` — triển khai Enterprise Integration Patterns (EIP) bằng Spring Integration để xây dựng luồng thông điệp ít phụ thuộc, dễ mở rộng; kết hợp Bridge với Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, correlation, kiểm thử và theo dõi nhánh xử lý.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Nhận diện **bridge vòng (circular bridge / message routing loop)** trong đồ thị message channel và endpoint.
2. Phân biệt vòng trực tiếp, vòng gián tiếp qua Router/Transformer và vòng vượt ranh giới adapter hoặc broker.
3. Giải thích vì sao một vòng lặp có thể gây đệ quy vô hạn, tiêu tốn CPU/thread, tăng số message, nghẽn queue hoặc làm hệ thống phát lại cùng nghiệp vụ.
4. Thiết kế Bridge **một chiều** với channel đầu vào và đầu ra rõ vai trò, không để đường xử lý quay về đầu vào.
5. Sử dụng sơ đồ đồ thị, kiểm tra cấu hình, hop limit, correlation và idempotency để nhận biết và giới hạn vòng lặp.
6. Xây dựng test xác nhận một message đi qua Bridge đúng số lần, có điểm kết thúc, và không trở lại channel nguồn.
7. Tách biệt vòng lặp nguy hiểm với vòng lặp nghiệp vụ có chủ đích như retry hữu hạn hoặc state machine có điều kiện dừng.

## 2. Bridge làm gì trong Spring Integration?

**Bridge** là một Enterprise Integration Pattern có nhiệm vụ nối hai message channel khi không cần sửa payload, chọn nhánh nghiệp vụ hay biến đổi thông điệp. Trong Spring Integration Java DSL, một bridge endpoint thường được khai báo bằng `.bridge()`. Nó nhận message ở input channel và chuyển tiếp tới output channel của endpoint.

Một luồng hợp lệ:

~~~mermaid
flowchart LR
    P["Producer"] --> A["ordersIn"]
    A --> B["Bridge"]
    B --> C["ordersToProcess"]
    C --> H["Service Activator"]
    H --> Z["Kết thúc / ghi nhận kết quả"]
~~~

Bridge ở đây cung cấp ranh giới tổ chức giữa hai channel. Không có cạnh nào dẫn từ `ordersToProcess` trở lại `ordersIn`, vì vậy mỗi message không tự quay lại cùng một Bridge.

Cần phân biệt các khái niệm:

| Thành phần | Vai trò | Có tự ngăn vòng lặp không? |
|---|---|---|
| `Bridge` | Chuyển tiếp message sang output channel. | Không; nó không tự duyệt đồ thị để biết mình đã được gọi trước đó. |
| `DirectChannel` | Dispatch message đồng bộ tới handler/subscriber. | Không; vòng đồng bộ có thể gọi lặp trên cùng call stack. |
| `QueueChannel` | Giữ message cho consumer/poller lấy sau. | Không; message có thể được lấy rồi đưa ngược lại queue ban đầu. |
| `ExecutorChannel` | Giao xử lý cho executor bất đồng bộ. | Không; vòng lặp có thể tạo task liên tục. |
| `Router` | Chọn channel đích theo điều kiện. | Chỉ an toàn nếu mọi nhánh có quy tắc dừng và không quay về đường nguồn sai cách. |
| `Filter` | Cho qua hoặc loại message theo điều kiện. | Có thể cắt vòng nếu điều kiện thay đổi và được kiểm thử; không phải cơ chế phòng vòng mặc định. |
| `Service Activator` | Thực hiện nghiệp vụ, tùy cấu hình có thể phát kết quả. | Có thể vô tình tạo cạnh quay lại input nếu gửi output sai channel. |

**Ý chính:** Bridge là một mắt xích trong **đồ thị định tuyến**. Sự an toàn của nó phụ thuộc vào cả các endpoint và channel liên quan, bao gồm đường xử lý lỗi, retry và outbound/inbound adapter.

## 3. Khi nào một vòng Bridge hình thành?

Hãy mô hình hóa mỗi channel là một đỉnh và mỗi hành vi chuyển tiếp là một cạnh có hướng. Nếu có một đường đi từ channel A qua một hay nhiều endpoint, rồi cuối cùng trở lại A, đồ thị có **chu trình**.

Chu trình là điều kiện cảnh báo. Nó trở thành vòng xử lý nguy hiểm khi message đi theo chu trình mà **không có điều kiện dừng hữu hiệu**.

### 3.1 Vòng trực tiếp

~~~mermaid
flowchart LR
    A["channelA"] --> B1["Bridge A → B"]
    B1 --> B["channelB"]
    B --> B2["Bridge B → A"]
    B2 --> A
~~~

Ở đây, một message vào `channelA` sẽ đi qua `channelB` rồi bị đẩy về `channelA`. Nếu không có điều kiện dừng, hành vi này lặp mãi.

### 3.2 Vòng gián tiếp qua nhiều pattern

~~~mermaid
flowchart TD
    A["inputChannel"] --> BR["Bridge"]
    BR --> M["mainChannel"]
    M --> R{"Router"}
    R -->|Hợp lệ| H["Business handler"]
    H --> DONE["completedChannel"]
    R -->|Nhánh cấu hình sai| OLD["legacyChannel"]
    OLD --> T["Transformer"]
    T --> A
~~~

Một Bridge riêng lẻ có thể được cấu hình đúng, nhưng một nhánh Router hoặc output của Transformer vô tình trả message về channel đầu vào, tạo vòng gián tiếp. Vì vậy không thể kiểm tra Bridge độc lập mà bỏ qua các edge xung quanh.

### 3.3 Vòng qua hai dịch vụ

~~~mermaid
flowchart LR
    subgraph S1["Service A"]
        I1["Inbound adapter A"] --> C1["Channel A"]
        C1 --> O1["Outbound adapter A"]
    end
    O1 --> Q1[("Broker topic/queue 1")]
    Q1 --> I2["Inbound adapter B"]
    subgraph S2["Service B"]
        I2 --> C2["Channel B"]
        C2 --> O2["Outbound adapter B"]
    end
    O2 --> Q2[("Broker topic/queue 2")]
    Q2 --> I1
~~~

Ở cấp mã nguồn của từng dịch vụ, bạn có thể không thấy chu trình. Nhưng nếu A phát sang B và B lại phát sang A cho **cùng một sự kiện** mà không phân biệt loại event hay trạng thái, message có thể chạy vòng qua broker. Vấn đề này không thể giải quyết chỉ bằng `Bridge` trong một ứng dụng.

## 4. Hậu quả tùy loại channel

Cùng một đồ thị vòng có thể biểu hiện khác nhau khi thay loại channel.

| Cấu hình | Dấu hiệu thường gặp | Vì sao nguy hiểm? |
|---|---|---|
| Hai `DirectChannel` nối vòng | Đệ quy sâu, `StackOverflowError`, ứng dụng mất ổn định. | Chuyển tiếp đồng bộ gọi ngược lại handler trên cùng thread. |
| `ExecutorChannel` trong vòng | Số task tăng, worker bận, queue của executor đầy, task bị từ chối. | Vòng tạo thêm công việc qua các thread; ngắt call stack không loại chu trình. |
| `QueueChannel` + poller | Message được lấy rồi enqueue lại, backlog và lưu lượng bất thường. | Poller tiếp tục tái phát thông điệp; hàng đợi có thể liên tục bận. |
| `PublishSubscribeChannel` trong vòng | Một message có thể tỏa thành nhiều bản, gây khuếch đại. | Fan-out kết hợp đường quay lại làm số lần xử lý tăng nhanh. |
| Broker hoặc Kafka topic | Lượng publish/consume tăng; lag, chi phí và retention bị ảnh hưởng. | Mỗi vòng có thể tạo một record mới, ngay cả khi ACK/offset của vòng trước đã thành công. |
| Error/retry flow quay về đầu nguồn | Exception và retry liên tục, DLQ khó kiểm soát. | Một lỗi có thể kích hoạt ngay cùng lỗi mà không có giới hạn hoặc backoff. |

**Đổi từ `DirectChannel` sang `QueueChannel` không phải là sửa vòng lặp.** Nó chỉ thay đổi cách vòng lặp bộc lộ: từ đệ quy trong một call stack sang vòng enqueue/dequeue theo thời gian.

### 4.1 Vì sao `send() == true` không phải bằng chứng xử lý đúng?

Trong Bridge cục bộ, `send()` thường biểu thị message đã được channel chấp nhận theo hợp đồng của channel. Nó không chứng minh rằng message:

- đã đi đúng tuyến;
- chỉ đi qua một lần;
- không bị gửi ngược lại channel nguồn;
- đã được consumer cuối cùng xử lý xong;
- đã được lưu bền vững hay được ACK bởi broker.

Một vòng có thể làm **hàng nghìn lần gửi thành công** nhưng nghiệp vụ vẫn không hoàn thành.

## 5. Ví dụ cấu hình vòng cần tránh

Đoạn Java DSL sau **chỉ dùng để nhận diện lỗi cấu hình, không chạy như ứng dụng hoặc unit test**, vì có thể gây đệ quy liên tục nếu cả hai channel là đồng bộ.

~~~java
// ANTI-PATTERN: KHÔNG CHẠY.
@Configuration
@EnableIntegration
class CircularBridgeConfig {

    @Bean
    MessageChannel channelA() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel channelB() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow aToB() {
        return IntegrationFlow.from("channelA")
                .bridge()
                .channel("channelB")
                .get();
    }

    @Bean
    IntegrationFlow bToA() {
        return IntegrationFlow.from("channelB")
                .bridge()
                .channel("channelA")
                .get();
    }
}
~~~

Hai flow tạo đồ thị:

~~~text
channelA → bridge(aToB) → channelB
channelB → bridge(bToA) → channelA
~~~

Giả sử producer gửi `OrderPlaced` vào `channelA`. `DirectChannel` gọi Bridge thứ nhất; Bridge gửi sang `channelB`; Bridge thứ hai gửi ngược về `channelA`; từ đây chuỗi lời gọi lặp lại. Dù payload và headers giữ nguyên, **định tuyến vẫn sai**.

Nếu thay `channelB` bằng `QueueChannel` có poller, có thể không còn đệ quy đồng bộ nhưng message sẽ được poll rồi gửi trở lại `channelA`. Kết quả vẫn là một vòng lặp logic.

**Không cần thực thi đoạn cấu hình lỗi để “chứng minh” nó nguy hiểm.** Đồ thị phụ thuộc đã đủ chỉ ra chu trình; những test không giới hạn số bước có thể làm treo tiến trình kiểm thử.

## 6. Cấu hình đúng: Bridge một chiều tới điểm kết thúc

Bài toán: ứng dụng nhận sự kiện `OrderPlaced`, đặt vào queue để worker xử lý hóa đơn. Bridge chỉ cần nối **channel đầu vào** với **queue xử lý**, và worker phải kết thúc việc xử lý thay vì trả message vào channel đầu vào.

~~~mermaid
flowchart LR
    P["Order publisher"] --> I["ordersIngress"]
    I --> BR["Bridge"]
    BR --> Q[["ordersQueue"]]
    Q --> POL["Poller"]
    POL --> H["Invoice handler"]
    H --> DB[("Invoice DB")]
~~~

Ví dụ Java DSL minh họa cấu hình một chiều:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

record OrderPlaced(String eventId, String orderId) {}

interface InvoiceService {
    void createInvoiceOnce(String eventId, String orderId);
}

@Configuration
@EnableIntegration
public class SafeOrderBridgeConfig {

    @Bean
    MessageChannel ordersIngress() {
        return new DirectChannel();
    }

    @Bean
    PollableChannel ordersQueue() {
        return new QueueChannel(100);
    }

    @Bean
    IntegrationFlow ordersBridgeFlow() {
        return IntegrationFlow.from("ordersIngress")
                .bridge()
                .channel("ordersQueue")
                .get();
    }

    @Bean
    IntegrationFlow invoiceProcessingFlow(InvoiceService invoiceService) {
        return IntegrationFlow.from(
                    "ordersQueue",
                    endpoint -> endpoint.poller(
                        Pollers.fixedDelay(500)
                               .maxMessagesPerPoll(5)))
                .handle(OrderPlaced.class, (event, headers) -> {
                    invoiceService.createInvoiceOnce(
                            event.eventId(), event.orderId());
                    return null; // Hoàn tất flow một chiều.
                })
                .get();
    }
}
~~~

Giải thích:

1. `ordersIngress` nhận message ban đầu.
2. Bridge chuyển tiếp một chiều tới `ordersQueue`.
3. Poller đưa message tới `InvoiceService`.
4. Handler trả về `null` để kết thúc flow một chiều; nó **không gửi lại** sự kiện `OrderPlaced` vào `ordersIngress`.
5. `createInvoiceOnce` là hợp đồng idempotency của nghiệp vụ. Triển khai thực tế phải ghi nhận `eventId` với unique constraint hoặc cơ chế chống trùng phù hợp.

`QueueChannel(100)` lưu trong bộ nhớ, **không bảo đảm phục hồi sau restart**. Nếu bài toán yêu cầu durable delivery, cân nhắc persistent message store hoặc broker phù hợp và kiểm thử transaction, ACK và redelivery. Đây là mối quan tâm khác với việc đồ thị có chu trình hay không.

### 6.1 Phân biệt nhánh kết thúc và nhánh trả lời

Nếu hệ thống cần thông báo thành công sau khi tạo hóa đơn, hãy dùng **channel kết quả riêng** như `invoiceCompleted` hoặc reply destination được quy định rõ. Không nên dùng chính `ordersIngress` làm output cho sự kiện hoàn tất.

Một ví dụ định tuyến dễ hiểu:

~~~text
ordersIngress
    → Bridge
    → ordersQueue
    → InvoiceHandler
    → invoiceCompleted
    → NotificationHandler
    → kết thúc
~~~

Nếu `NotificationHandler` cần phát sự kiện tiếp theo, nó nên tạo event có ý nghĩa mới như `InvoiceCreated`, với định danh nghiệp vụ rõ ràng, gửi tới topic/channel tương ứng; không phát lại nguyên trạng `OrderPlaced` vào cùng đầu nguồn.

## 7. Quy tắc kiểm tra đồ thị trước khi chạy

Với mỗi cấu hình, biểu diễn các đường chuyển tiếp thành **đồ thị có hướng**. Ghi đầy đủ các cạnh từ:

- Bridge: input channel → output channel.
- Router: input → từng channel có thể được chọn.
- Transformer/Service Activator có output: input → output.
- Publish/subscribe: input → tất cả nhánh subscriber có thể phát tiếp.
- Gateway hoặc request–reply: luồng request, reply và timeout/error nếu chúng dẫn tới channel khác.
- Retry và error handler: nơi message lỗi hoặc message retry được gửi đến.
- Outbound/inbound adapter: liên kết qua topic, queue, destination hoặc HTTP callback nếu hệ thống có thể quay lại cùng dịch vụ.

### 7.1 Thuật toán phát hiện chu trình

Một cách thông dụng là DFS với ba trạng thái đỉnh:

- `UNVISITED`: chưa duyệt.
- `VISITING`: đang nằm trên đường đi DFS hiện tại.
- `VISITED`: đã duyệt xong mọi đường từ đỉnh đó.

Khi DFS đi tới một đỉnh đang ở trạng thái `VISITING`, có một chu trình trong các cạnh đã mô hình hóa.

~~~text
detectCycle(graph):
    state = {node: UNVISITED for node in graph}

    visit(node):
        state[node] = VISITING

        for next in graph.outgoing(node):
            if state[next] == VISITING:
                reportCycle(node, next)
            else if state[next] == UNVISITED:
                visit(next)

        state[node] = VISITED

    for node in graph.nodes:
        if state[node] == UNVISITED:
            visit(node)
~~~

Thuật toán DFS có độ phức tạp `O(V + E)` với số đỉnh `V` và cạnh `E` trong đồ thị đã thu thập. Nó giúp nhận diện cấu hình đáng nghi **trước khi gửi message thử**.

Có thể dùng thuật toán strongly connected components (Tarjan/Kosaraju) để liệt kê nhóm endpoint/channel có đường quay lại nhau. Mọi strongly connected component chứa nhiều đỉnh, hoặc một đỉnh tự nối chính nó, đều cần được xem xét.

**Giới hạn:** cấu hình Router dùng biểu thức động, routing key tạo từ dữ liệu, dịch vụ khác và broker topology có thể khiến đồ thị tĩnh thiếu cạnh. “Không thấy vòng khi scan code” chỉ đúng trong phạm vi cấu hình đã duyệt; vẫn cần integration test và theo dõi khi vận hành.

### 7.2 Xác định một chu trình có thật sự nguy hiểm không

Không phải mọi chu trình trong topology đều sai. Một vòng retry nghiệp vụ có thể **có chủ đích**, nhưng phải chứng minh được tất cả các điều kiện:

1. Điều kiện lặp được mô tả rõ.
2. Có số lần thử/giới hạn thời gian hoặc điều kiện kết thúc có thể đo.
3. Mỗi vòng không tạo hiệu ứng nghiệp vụ trùng không kiểm soát.
4. Có backoff và giới hạn tài nguyên.
5. Khi hết giới hạn, message tới một nơi **không quay lại vòng**, chẳng hạn quarantine/DLQ hoặc trạng thái thất bại cuối.

Nếu thiếu một trong các điều kiện này, vòng đó vẫn là điểm rủi ro cần thiết kế lại.

## 8. Retry hữu hạn khác với bridge vòng

Ví dụ lỗi API thanh toán. Thiết kế sai:

~~~mermaid
flowchart LR
    IN["paymentIn"] --> B["Bridge"]
    B --> H["Payment handler"]
    H -->|Bất kỳ lỗi nào| IN
~~~

Nó chuyển lại cùng message ngay lập tức vào đầu nguồn, không phân loại lỗi và không có ngưỡng dừng.

Thiết kế đúng hơn:

~~~mermaid
flowchart TD
    IN["paymentIn"] --> H["Payment handler"]
    H --> S{"Kết quả"}
    S -->|Thành công| DONE["Completed"]
    S -->|Lỗi tạm thời| C{"attempt < maxAttempts?"}
    S -->|Lỗi vĩnh viễn| Q["Quarantine / DLQ"]
    C -->|Có| D["Backoff / delayed retry"]
    D --> H
    C -->|Không| Q
~~~

Ở đây vẫn có một đường quay lại handler, nhưng **chỉ trong một chính sách retry hữu hạn**, với điểm kết thúc rõ ràng. Tùy hạ tầng, bạn có thể dùng retry advice, retry topic, delayed queue hoặc scheduler phù hợp. Không cần dựng Bridge vòng để có retry.

### 8.1 Hop limit chỉ là lớp phòng vệ bổ sung

Một số hệ thống có thể thêm header `xHopCount` để đo message đã đi qua bao nhiêu ranh giới. Ví dụ hàm Java sau tăng hop count và từ chối khi vượt giới hạn:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public final class HopGuard {

    private HopGuard() {}

    public static Message<?> nextHop(
            Message<?> original, int maxHops) {
        Object raw = original.getHeaders().get("xHopCount");
        int current = raw instanceof Number number
                ? number.intValue()
                : 0;

        if (current < 0 || maxHops <= 0 || current >= maxHops) {
            throw new IllegalStateException(
                    "Message hop limit exceeded: " + current);
        }

        return MessageBuilder.fromMessage(original)
                .setHeader("xHopCount", current + 1)
                .build();
    }
}
~~~

Nếu đặt guard ở ranh giới bắt buộc, một message chỉ có thể đi tối đa `maxHops` lần **qua ranh giới đó**. Nhưng có các giới hạn:

- `xHopCount` là metadata; nó có thể bị xóa hoặc thay đổi bởi Transformer, adapter, header mapper hoặc publisher khác.
- Một vòng không đi qua guard sẽ không bị đếm.
- Một fan-out có thể tạo **nhiều bản sao** với hop count giống nhau; hop limit không chống message amplification hoàn toàn.
- Khi guard ném exception, cần có đường xử lý lỗi cuối cùng và tránh để chính error flow quay lại vòng.
- Tăng header nghĩa là có một **bước biến đổi metadata**; không nên gọi đó là tính năng mặc định của Bridge thuần túy.

Hop limit hữu ích để **giới hạn thiệt hại và hỗ trợ chẩn đoán**; biện pháp chính vẫn là loại bỏ chu trình không hợp lệ khỏi topology.

### 8.2 Dùng event ID và trạng thái nghiệp vụ

Nếu cùng `eventId` xuất hiện trở lại liên tục, cần biết đó là:

- broker redelivery hợp lệ sau lỗi;
- một vòng định tuyến;
- producer publish lại vì timeout;
- hay nhiều sự kiện con cùng correlation ID.

Nên giữ riêng `eventId`, `correlationId`, `messageId`, `retryAttempt` và `traceId`. Khi cần chống tác động trùng, dùng business `eventId` hoặc khóa idempotency ổn định; **không dựa duy nhất vào Spring `MessageHeaders.ID`**, vì một sự kiện có thể được xây dựng lại thành message mới.

## 9. Router, Filter, Transformer và Gateway có thể tạo vòng gián tiếp

### Router

Router chọn nhánh động; một cấu hình default output channel vô tình trỏ về input channel có thể làm mọi message không khớp rule quay lại từ đầu.

Ví dụ:

~~~text
ingress -> Router
               |-- type=INVOICE --> invoiceChannel -> done
               |-- type=PAYMENT --> paymentChannel -> done
               |-- default ------> ingress          (SAI)
~~~

Cách sửa: đưa message không biết loại tới `unknownTypeChannel` rồi quarantine/alert, hoặc kết thúc bằng một xử lý rõ ràng. Đừng mặc định “cứ quay lại đầu vào để thử lại”, vì dữ liệu không thay đổi thì kết quả phân loại cũng không thay đổi.

### Filter

Một Filter có thể loại message không hợp lệ. Nếu Filter gửi message bị từ chối về chính channel trước Bridge, một vòng có thể hình thành khi giá trị dùng lọc vẫn không thay đổi.

Cần phân biệt **bỏ qua hợp lệ** (ví dụ event đã xử lý), **lỗi dữ liệu vĩnh viễn** (đưa quarantine) và **lỗi tạm thời** (retry hữu hạn).

### Transformer

Transformer có thể tạo payload mới và thay đổi header. Nếu một Transformer vô tình đổi loại event thành loại khiến Router chọn lại nhánh trước đó, có thể tạo vòng gián tiếp mà không có Bridge B → A rõ ràng. Test nên theo dõi chuỗi channel đã đi qua và kỳ vọng của từng trạng thái.

### Gateway và request–reply

Gateway yêu cầu reply có thể phát sinh request mới nếu reply được định tuyến nhầm vào channel request. Ví dụ, mapping `replyChannel` sai làm message kết quả được diễn giải lại như request ban đầu.

Với request–reply qua broker, cần tách rõ request destination và reply destination, correlation ID, timeout, xử lý reply muộn và duplicate. Không dùng cùng một topic/queue hai chiều mà không có quy tắc phân loại message rõ ràng.

## 10. Splitter, Aggregator và message amplification

Splitter biến một message thành nhiều message con. Nếu một nhánh của các message con quay lại Splitter hoặc Bridge phía trước mà không có điều kiện dừng, số lượng message có thể tăng theo cấp số nhân.

Ví dụ một message chia thành ba phần, mỗi phần bị đưa ngược lại đầu Splitter và tiếp tục chia ba:

~~~text
Vòng 0: 1 message
Vòng 1: 3 message
Vòng 2: 9 message
Vòng 3: 27 message
Vòng 4: 81 message
~~~

Đây là mô hình khuếch đại lý thuyết khi mỗi phần sinh ba phần mới; con số thực tế phụ thuộc logic Splitter, Filter và việc nhánh nào được chạy lại.

Với Aggregator, một message con bị tạo lặp có thể làm nhóm lớn lên bất thường, chờ release strategy sai hoặc hoàn tất với dữ liệu trùng. Hãy xác định:

- `correlationId` dùng để gom nhóm.
- `sequenceNumber`, `sequenceSize` hoặc quy tắc release riêng.
- Định danh message con để chống nhận trùng.
- `MessageGroupStore` bền vững nếu nhóm cần tồn tại sau restart.
- Quy tắc timeout và xử lý nhóm không hoàn chỉnh.

Bridge thuần không quản lý sequence/release. Không kỳ vọng Bridge tự chống message con lặp lại.

## 11. Error channel cũng có thể tạo vòng

Giả sử flow xử lý gặp lỗi và gửi `ErrorMessage` tới `errorChannel`. Nếu error handler cố “cứu” bằng cách gửi **nguyên message thất bại** về input không giới hạn, lỗi có thể lặp ngay.

Một vòng thường thấy:

~~~mermaid
flowchart LR
    I["inputChannel"] --> H["Handler"]
    H -->|Throw| E["errorChannel"]
    E --> R["Error handler: resend"]
    R --> I
~~~

Cách cải thiện:

1. Phân loại lỗi `transient` hoặc `permanent`.
2. Giới hạn retry và đặt backoff, không tạo vòng resend tức thì.
3. Đảm bảo thao tác tạo bản ghi lỗi/DLQ là **terminal** hoặc có policy riêng không quay lại đầu nguồn.
4. Nếu error handler cũng thất bại, có quy tắc cảnh báo hoặc propagate phù hợp, tránh tạo một lỗi mới quay lại cùng channel không dừng.
5. Khi sử dụng inbound broker adapter, xác định rõ ai quyết định ACK/NACK, rollback và offset commit. Lỗi xuất hiện ở error channel **không tự đảm bảo** broker sẽ redeliver.

**Lưu ý:** một exception trong `DirectChannel` có thể đi ngược về caller đồng bộ; một lỗi ở poller hoặc async boundary có thể được phát thành `ErrorMessage`. Muốn phát hiện vòng phải xét cả cách exception được chuyển tiếp và cách error flow được gắn vào transport.

## 12. Vòng qua broker: ACK và durable message không giúp cắt vòng

Giả sử Service A nhận một message từ `orders.in`, chuyển qua Bridge tới outbound adapter phát vào `orders.out`. Service B đọc `orders.out` rồi do cấu hình sai phát ngược `orders.in`. Hai service có thể ACK/commit thành công **trong từng lần xử lý** trong khi vòng toàn hệ thống vẫn hoạt động.

Điều đó dẫn tới ba ngộ nhận:

- “Broker đã ACK, nghĩa là message được xử lý xong và không quay lại”: sai, vì một service có thể publish một message mới đại diện cho cùng sự kiện.
- “Queue durable sẽ bảo vệ hệ thống”: durability giúp lưu message khi lỗi, **không ngăn đường định tuyến vòng**.
- “Exactly-once của transport sẽ ngăn vòng”: cơ chế chống duplicate trong một phạm vi transport/transaction không tự loại bỏ một logic republish sai qua nhiều dịch vụ hoặc hệ thống ngoài.

Phòng vệ phù hợp gồm phân chia topic/queue theo ý nghĩa message, rõ vai trò producer/consumer, event type và version, routing key, idempotency, hop/causation metadata và một topology không có chu trình ngoài ý định.

Ví dụ phân chia:

| Destination | Vai trò | Đích hợp lệ |
|---|---|---|
| `orders.created` | Sự kiện đã tạo đơn | Billing, Inventory, Analytics |
| `billing.invoice.requested` | Yêu cầu tạo hóa đơn | Billing worker |
| `billing.invoice.created` | Kết quả tạo hóa đơn | Notification, Order status |
| `billing.invoice.failed` | Sự kiện lỗi đã phân loại | Recovery/quarantine/operations |

Nếu một consumer của `billing.invoice.created` lại tạo `orders.created` cho **chính đơn hàng cũ** thì phải xem lại nghiệp vụ, vì đây có thể là một vòng sự kiện dù tên topic khác nhau.

## 13. Quan sát và phát hiện vòng khi vận hành

Ngoài rà soát đồ thị tĩnh, ứng dụng cần đo các triệu chứng bất thường của message loop.

| Tín hiệu | Ý nghĩa có thể có | Hành động chẩn đoán |
|---|---|---|
| Một `eventId` xuất hiện quá nhiều lần trong thời gian ngắn | Loop, retry storm hoặc republish liên tục | Xem chuỗi channel/endpoint và retry metadata. |
| Số lần `send` lớn nhưng nghiệp vụ hoàn thành ít | Message đang quay vòng qua các bước nội bộ | Đo terminal completion theo event ID. |
| CPU/thread tăng, lỗi stack overflow | Vòng đồng bộ hoặc async quá tải | Rà `DirectChannel`, `ExecutorChannel` và những cạnh ngược. |
| Queue depth/consumer lag tăng liên tục | Vòng tạo lại message hoặc consumer không theo kịp | Đối chiếu enqueue/dequeue và event lineage. |
| DLQ tăng do cùng payload | Poison message hoặc policy error/requeue sai | Kiểm tra error handler và điều kiện dừng. |
| `xHopCount` tăng liên tục | Message đi qua lặp lại guard boundary | Dùng trace để xác định chu trình. |
| Aggregator có nhóm quá lớn/không release | Message con bị lặp hoặc correlation/release sai | Kiểm tra sequence, duplicate và group store. |

### 13.1 Ghi log đủ để lần theo đường đi

Một bản ghi quan sát hữu ích:

~~~text
eventId=evt-501
correlationId=order-723
messageId=<Spring message UUID>
sourceEndpoint=ordersInboundAdapter
currentChannel=ordersIngress
nextChannel=ordersQueue
hopCount=2
retryAttempt=1
traceId=<distributed trace ID>
outcome=forwarded | completed | retried | quarantined
~~~

`hopCount`, `retryAttempt` và `traceId` là dữ liệu cần được cấu hình hoặc do ứng dụng tạo; Spring Integration không tự bảo đảm mọi message đều có đủ các trường này.

Không log toàn bộ payload chứa thông tin cá nhân, access token hoặc dữ liệu nhạy cảm chỉ để phát hiện vòng. Chỉ cần metadata định danh, các mốc thời gian, kết quả xử lý và ngữ cảnh đủ cho điều tra.

### 13.2 Kiểm tra sơ đồ runtime

Nếu môi trường có hỗ trợ quản lý/quan sát Spring Integration, có thể dùng sơ đồ integration graph và thông tin endpoint để đối chiếu topology thực tế với sơ đồ thiết kế. Lưu ý graph cục bộ thường không biểu diễn đầy đủ đường đi qua nhiều microservice hoặc động tác publish lại ở broker.

Khi chỉ số báo hiệu vòng, bước đầu nên là **xác định cạnh quay về nguồn** rồi sửa routing. Giới hạn rate và tạm ngừng nguồn gây khuếch đại có thể giúp giảm tác động khi xử lý sự cố, nhưng không phải sửa lỗi topology.

## 14. Cách kiểm thử vòng mà không gây treo

Không chạy trực tiếp cấu hình Bridge vòng đồng bộ để chờ `StackOverflowError`. Hãy ưu tiên các kiểm thử **hữu hạn, có timeout và có assertion**.

### 14.1 Test topology tĩnh

Với cấu hình khai báo, thu thập danh sách cạnh:

~~~text
ordersIngress -> ordersQueue
ordersQueue   -> invoiceHandler
invoiceHandler -> terminal
~~~

Kiểm tra không có đường từ `ordersQueue` hoặc `invoiceHandler` quay lại `ordersIngress`. Nếu có Router hoặc dynamic endpoint, bổ sung tất cả nhánh đích có thể có, bao gồm default/error/retry destinations.

Một danh sách cạnh có thể được dùng làm fixture để chạy `detectCycle(graph)`; không nhất thiết phải khởi động toàn ứng dụng để chạy thử vòng vô hạn.

### 14.2 Test chuyển tiếp cục bộ một lần

Đoạn test dưới đây sử dụng cấu hình Bridge **một chiều chỉ có hai channel**. Đây là fixture riêng để dễ quan sát đầu ra; không có poller nào cạnh tranh lấy message.

~~~java
@Configuration
@EnableIntegration
class BridgeOnlyTestConfig {

    @Bean
    MessageChannel testInput() {
        return new DirectChannel();
    }

    @Bean
    PollableChannel testOutput() {
        return new QueueChannel(10);
    }

    @Bean
    IntegrationFlow testBridge() {
        return IntegrationFlow.from("testInput")
                .bridge()
                .channel("testOutput")
                .get();
    }
}
~~~

Và test JUnit 5:

~~~java
@SpringJUnitConfig(BridgeOnlyTestConfig.class)
class BridgeOnlyTest {

    @Autowired
    @Qualifier("testInput")
    MessageChannel input;

    @Autowired
    @Qualifier("testOutput")
    PollableChannel output;

    @Test
    void forwardsExactlyOneMessageToTerminalQueue() {
        Message<String> sent = MessageBuilder
                .withPayload("order-723")
                .setHeader("eventId", "evt-501")
                .build();

        assertTrue(input.send(sent));

        Message<?> first = output.receive(1_000);
        assertNotNull(first);
        assertEquals("order-723", first.getPayload());
        assertEquals("evt-501",
                     first.getHeaders().get("eventId"));

        // Không có cạnh nào phát lại vào testOutput.
        assertNull(output.receive(100));
    }
}
~~~

Các import Spring, JUnit, Spring Test được lược bớt ở ví dụ để tập trung vào pattern. Test trên xác minh **một lần enqueue và một lần receive** trong cấu hình riêng. Nó không chứng minh toàn bộ hệ thống đa dịch vụ không có vòng; điều đó cần graph review và integration test theo topology thực.

### 14.3 Test nghiệp vụ trên đường đi thật

Trong môi trường integration test kiểm soát được, hãy kiểm tra:

1. Gửi một `eventId` hợp lệ vào channel nguồn.
2. Chờ sự kiện hoàn thành ở channel/DB đích trong một deadline hữu hạn.
3. Đếm số lần handler nghiệp vụ được gọi; nếu có at-least-once delivery, phân biệt **lần gọi** với **tác động commit**.
4. Quan sát số lần cùng `eventId` xuất hiện ở từng endpoint; đặt ngưỡng hợp lý cho retry dự kiến.
5. Kiểm tra không có publish ngược tới nguồn đối với loại event đã hoàn tất.
6. Cố tình cho handler lỗi transient rồi xác minh retry có giới hạn và đường kết thúc DLQ khi vượt số lần.
7. Chạy thêm trường hợp fan-out, Router default path, error handler lỗi và restart.

Mọi test dùng timeout hoặc deadline; khi phát hiện quá ngưỡng lặp, dừng nguồn test và ghi lại trace, tránh để job CI chạy vô hạn.

## 15. Quy trình rà soát cấu hình trước khi triển khai

Một quy trình review thực tế:

| Bước | Nội dung kiểm tra | Kết quả cần có |
|---|---|---|
| 1. Liệt kê channel | Tên, loại channel, phạm vi ứng dụng | Danh sách input/output và chủ sở hữu rõ ràng. |
| 2. Liệt kê endpoint | Bridge, Router, Filter, Transformer, Splitter, Aggregator, Gateway, adapters | Mỗi endpoint có input/output hoặc terminal rõ ràng. |
| 3. Lập đồ thị | Đánh dấu các cạnh thường, error, retry và reply | Nhìn được mọi đường có khả năng quay về nguồn. |
| 4. Dò chu trình | DFS/SCC với đồ thị tĩnh; đánh giá routing động | Tất cả chu trình được phân loại, có lý do và điểm dừng. |
| 5. Kiểm tra identity | `eventId`, `correlationId`, headers và trace context | Có khả năng theo dõi message qua mỗi vòng và chống duplicate. |
| 6. Kiểm tra tài nguyên | Queue capacity, executor, poll rate, retry delay | Không có vòng gửi nhanh vô hạn hoặc fan-out bùng nổ. |
| 7. Kiểm thử lỗi | Timeout, rollback, failed handler, ACK/offset, dead-letter | Không quay lại nguồn ngoài ý định; kết thúc đúng policy. |
| 8. Giám sát | Hop count, per-event count, message age, lag, completed count | Có thể phát hiện bất thường sớm và tìm chu trình. |

Khi phát hiện vòng, hãy ưu tiên **loại bỏ cạnh sai** hoặc tách vai trò channel. Chỉ thêm guard/hop count sau khi đã xác định kiến trúc, để guard là tuyến phòng vệ thứ hai.

## 16. Các lỗi thiết kế thường gặp

1. **Đặt output của Bridge bằng input của chính nó** hoặc tạo hai Bridge đối xứng A → B và B → A.
2. **Nhầm async với đã loại bỏ vòng:** đổi `DirectChannel` sang executor/queue chỉ giấu vòng lặp dưới dạng task hoặc enqueue liên tục.
3. **Đặt Router default channel quay về ingress:** message không khớp rule mãi mãi quay lại Router.
4. **Dùng Bridge làm retry:** gửi lại nguyên message tức thì không giới hạn số lần, không phân loại lỗi.
5. **Error handler gửi ngược failed message:** tạo vòng lỗi, có thể làm lỗi trong lúc ghi DLQ sinh ra lỗi mới.
6. **Không tính đường đi qua adapter và broker:** mỗi service nhìn riêng có thể thấy đồ thị không vòng, nhưng toàn hệ thống vẫn vòng.
7. **Không phân biệt event mới và cùng event được phát lại:** tạo nghiệp vụ trùng dưới dạng nhiều message ID.
8. **Không xét fan-out:** một vòng qua Splitter/PublishSubscribe có thể khuếch đại số lượng message.
9. **Chỉ test `send() == true`:** không xác minh đã hoàn tất, không đếm số lần qua endpoint, không kiểm tra lặp.
10. **Thiếu điều kiện dừng và giám sát:** ngay cả vòng được thiết kế có chủ đích cũng có thể trở thành retry storm khi dependency hỏng.

## 17. Checklist thực hành

- [ ] Sơ đồ flow thể hiện đúng mọi input/output channel, Bridge và các nhánh Router.
- [ ] Không có đường trả message đã chuyển tiếp trở lại channel nguồn trừ khi có chủ đích và điều kiện dừng.
- [ ] Với mỗi chu trình chủ đích, có `maxAttempts` hoặc quy tắc dừng định lượng, backoff, DLQ/quarantine và tài liệu hóa.
- [ ] Đã duyệt đường lỗi, retry, reply, dead-letter và các vòng qua broker giữa dịch vụ.
- [ ] `DirectChannel` không tạo đệ quy vô hạn; `ExecutorChannel` và queue có giới hạn tài nguyên.
- [ ] Có business `eventId` ổn định, correlation, deduplication và idempotent consumer.
- [ ] Có sơ đồ/kiểm tra đồ thị tĩnh, test hữu hạn, timeout và assertion về số lần đi qua các endpoint.
- [ ] Có metric lặp theo event ID, queue depth, consumer lag, retry count, hop count và completed count.
- [ ] Nếu có durable message/transaction/ACK, đã kiểm thử riêng cơ chế phục hồi; không đánh đồng với kiểm tra vòng.
- [ ] Các output terminal và error terminal được định nghĩa rõ, có chủ sở hữu vận hành.

## 18. Kết luận

Bridge giúp nối hai channel trong Spring Integration mà không cần thay đổi payload. Khi các Bridge hoặc endpoint khác tạo thành **chu trình chuyển tiếp**, message có thể quay về nơi bắt đầu. Với channel đồng bộ, chu trình dễ dẫn đến đệ quy sâu; với queue, executor hoặc broker, nó có thể chuyển thành vòng gửi lại kéo dài, nghẽn tài nguyên hoặc khuếch đại thông điệp.

Cách xử lý bền vững là thiết kế **đường đi một chiều tới điểm kết thúc**, kiểm tra đồ thị toàn hệ thống bao gồm Router, Gateway, adapter, retry và error flow, rồi kiểm thử message ở điểm nhận cuối. Những vòng lặp nghiệp vụ có chủ đích phải có điều kiện dừng, giới hạn tài nguyên, idempotency và khả năng quan sát. Hop limit giúp giảm tác động khi lỗi xuất hiện, nhưng không thay thế việc loại bỏ cạnh định tuyến sai.
