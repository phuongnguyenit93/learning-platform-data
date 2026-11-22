# Pipes and Filters gồm các bước xử lý độc lập

## 1. Bối cảnh và mục tiêu

Trong module **SPRING_INTEGRATION_PATTERN**, chúng ta học triển khai các **Enterprise Integration Patterns** bằng **Spring Integration** để xây dựng luồng thông điệp ít phụ thuộc, dễ mở rộng và dễ kiểm thử. Một trong những nền tảng quan trọng nhất của kiến trúc tích hợp là **Pipes and Filters**: chia một quy trình thành những bước xử lý có nhiệm vụ riêng và nối chúng qua kênh chuyển dữ liệu.

Ví dụ: khi hệ thống thương mại điện tử nhận đơn hàng, nó có thể cần **kiểm tra dữ liệu → chuẩn hóa → tính thông tin giao vận → ghi lệnh xử lý**. Nếu tất cả công việc nằm trong một phương thức khổng lồ, mọi thay đổi đều tác động đến cùng một đoạn mã. Với Pipes and Filters, mỗi bước xử lý một nhiệm vụ rõ ràng và chỉ cần biết **hợp đồng message đầu vào/đầu ra**.

Sau bài học, bạn có thể:

1. Giải thích vì sao Pipes and Filters gồm những bước xử lý có thể phát triển, kiểm thử và thay thế tương đối độc lập.
2. Phân biệt **filter của mẫu kiến trúc** với endpoint **Message Filter** cụ thể trong Spring Integration.
3. Mô hình hóa một flow gồm **Message**, **Channel**, **Endpoint** và các bước biến đổi dữ liệu.
4. Cài đặt pipeline bằng **IntegrationFlow Java DSL**, hiểu thứ tự thực thi và tính chất đồng bộ/bất đồng bộ của channel.
5. Thiết kế xử lý lỗi, correlation, retry, idempotency và quan sát cho một pipeline có nhiều bước.

## 2. Pipes and Filters là gì?

Pipes and Filters là mẫu kiến trúc tổ chức xử lý dữ liệu theo đường đi gồm nhiều bước:

- **Filter**: một thành phần nhận dữ liệu đầu vào, thực hiện một công việc có phạm vi rõ ràng, rồi tạo đầu ra, loại dữ liệu hoặc phát lỗi theo hợp đồng.
- **Pipe**: kênh liên kết các bước, mang dữ liệu từ đầu ra của bước này đến đầu vào của bước kế tiếp.
- **Pipeline**: đường đi hợp thành từ nhiều filter và pipe để đạt một kết quả nghiệp vụ.

~~~mermaid
flowchart LR
    S["Nguồn: đơn hàng mới"] --> P1["Pipe 1"]
    P1 --> F1["Filter A<br/>Kiểm tra"]
    F1 --> P2["Pipe 2"]
    P2 --> F2["Filter B<br/>Chuẩn hóa"]
    F2 --> P3["Pipe 3"]
    P3 --> F3["Filter C<br/>Tạo lệnh"]
    F3 --> P4["Pipe 4"]
    P4 --> D["Đích: hệ thống xử lý"]
~~~

**Độc lập** ở đây không có nghĩa các bước không có liên hệ. Chúng có **quan hệ dữ liệu thông qua hợp đồng**, nhưng tránh phụ thuộc trực tiếp vào cấu trúc nội bộ và cách cài đặt của nhau. Một bước chỉ cần biết **message mình nhận là gì**, **kết quả mình tạo là gì** và **điều gì xảy ra khi không thể xử lý**.

Chẳng hạn, bước chuẩn hóa địa chỉ không cần biết bước ghi dữ liệu dùng JDBC, JPA hay gọi REST. Nó chỉ cần xuất ra một payload hợp lệ để bước tiếp theo tiếp nhận.

### 2.1. “Filter” có hai nghĩa cần phân biệt

Trong **mẫu Pipes and Filters**, từ *filter* có nghĩa rộng là một công đoạn xử lý; một filter có thể **biến đổi**, **kiểm tra**, **làm giàu** hoặc **chuyển tiếp** dữ liệu.

Trong **Spring Integration**, **Message Filter** là một endpoint cụ thể: nó kiểm tra một điều kiện và quyết định **cho message đi tiếp hay loại bỏ**; thông thường nó không biến đổi payload. Các endpoint như **Transformer**, **Service Activator** và **Enricher** đều có thể đóng vai trò một “bước” trong kiến trúc Pipes and Filters.

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Filter theo mẫu kiến trúc | Bất kỳ bước xử lý độc lập trong pipeline | Chuẩn hóa địa chỉ giao hàng |
| Message Filter của Spring Integration | Kiểm tra predicate để cho đi tiếp hoặc từ chối | Bỏ đơn có tổng tiền không hợp lệ |
| Transformer | Tạo nội dung/kiểu message mới từ dữ liệu cũ | OrderReceived → DispatchCommand |
| Enricher | Bổ sung thông tin vào payload hoặc headers | Gắn tên kho xử lý theo vùng |
| Service Activator | Gọi logic nghiệp vụ/ứng dụng ở một endpoint | Ghi lệnh giao hàng |
| MessageChannel | Truyền message giữa các endpoint | DirectChannel, QueueChannel |

Không nhầm việc **lọc message** với **toàn bộ mẫu kiến trúc**. Một pipeline chỉ gồm Transformer và Service Activator vẫn có thể là một hiện thực Pipes and Filters.

## 3. Các nguyên tắc giúp từng bước độc lập

### 3.1. Một bước nên có một trách nhiệm rõ ràng

Hãy tách các hành động dễ thay đổi vì những lý do khác nhau. Ví dụ:

| Bước | Đầu vào | Trách nhiệm | Đầu ra |
| --- | --- | --- | --- |
| Validate | OrderReceived | Kiểm tra mã đơn, số tiền, địa chỉ bắt buộc | OrderReceived hợp lệ hoặc lỗi/từ chối |
| Normalize | OrderReceived hợp lệ | Chuẩn hóa tên tỉnh và dữ liệu định dạng | NormalizedOrder |
| Map | NormalizedOrder | Tạo lệnh giao vận | DispatchCommand |
| Dispatch | DispatchCommand | Gọi adapter ghi lệnh vào hệ thống đích | Hoàn tất hoặc lỗi nghiệp vụ |

Bước **Normalize** không cần biết lỗi từ database đích; bước **Dispatch** không nên lặp lại các quy tắc chuẩn hóa chuỗi. Ranh giới rõ giúp thay một bước mà hạn chế sửa các bước khác.

### 3.2. Phụ thuộc vào hợp đồng dữ liệu, không phụ thuộc trực tiếp vào nhau

So sánh hai cách:

~~~java
// Liên kết chặt: từng bước tự tạo và gọi bước tiếp theo.
class CoupledOrderProcessor {
    void process(OrderReceived input) {
        NormalizedOrder order = new AddressNormalizer().normalize(input);
        DispatchCommand command = new DispatchMapper().map(order);
        new RemoteDispatchClient().send(command);
    }
}
~~~

Trong ví dụ trên, lớp xử lý biết rõ cách khởi tạo và gọi từng thành phần. Muốn thay client, thêm một bước hoặc chạy bất đồng bộ, ta phải sửa logic điều phối.

Với Pipes and Filters, thành phần chỉ cần biết **hợp đồng input/output**. Spring Integration giữ nhiệm vụ kết nối các endpoint bằng channel và cấu hình flow:

~~~mermaid
flowchart LR
    A["OrderReceived"] --> F1["Validate"]
    F1 -->|"Message<OrderReceived>"| F2["Normalize"]
    F2 -->|"Message<NormalizedOrder>"| F3["Map"]
    F3 -->|"Message<DispatchCommand>"| F4["Dispatch"]
~~~

Khi đổi logic chuẩn hóa, ta có thể sửa/test Normalize độc lập miễn là hợp đồng đầu ra vẫn phù hợp với Map.

### 3.3. Ưu tiên phép biến đổi thuần và dữ liệu bất biến

Các bước biến đổi dễ kiểm thử nhất khi **đầu ra phụ thuộc vào đầu vào**, hạn chế đọc trạng thái toàn cục hoặc thay đổi đối tượng đầu vào. Trong Java, **record** có ích cho mô hình dữ liệu nhỏ; tuy vậy record chỉ làm các field tham chiếu bất biến, không biến đối tượng mutable nằm bên trong thành bất biến sâu.

~~~java
import java.util.Locale;

record OrderReceived(String orderId, String province) {}
record NormalizedOrder(String orderId, String provinceCode) {}

final class ProvinceNormalizer {
    NormalizedOrder normalize(OrderReceived input) {
        if (input == null || input.orderId() == null
                || input.province() == null) {
            throw new IllegalArgumentException("Thiếu dữ liệu bắt buộc");
        }
        return new NormalizedOrder(
                input.orderId().trim(),
                input.province().trim().toUpperCase(Locale.ROOT));
    }
}
~~~

Phép biến đổi này không phụ thuộc vào channel, database hay network. Có thể tạo trực tiếp đối tượng ProvinceNormalizer trong unit test, rồi kiểm tra nhiều input mà không khởi động Spring.

Lưu ý: **chuẩn hóa chữ hoa không tương đương mã tỉnh hành chính thực tế**. Ví dụ ở đây chỉ minh họa phép biến đổi chuỗi. Nếu nghiệp vụ cần bảng mã tỉnh hợp lệ, nên dùng một bước tra cứu/mapping có hợp đồng riêng.

### 3.4. Hợp đồng lỗi là một phần của hợp đồng bước

Mỗi filter cần nêu rõ:

- Khi input hợp lệ: trả ra payload cùng kiểu, kiểu mới hay không trả gì?
- Khi input không hợp lệ: loại message, gửi sang discard channel hay ném exception?
- Khi xảy ra lỗi tạm thời: lỗi có thể retry an toàn hay không?
- Có side effect nào đã diễn ra trước khi lỗi?

Nếu không định nghĩa rõ, hai bước độc lập về code vẫn có thể kết hợp sai về mặt nghiệp vụ.

## 4. Ánh xạ mẫu kiến trúc sang Spring Integration

Spring Integration cung cấp các cấu phần thực thi Pipes and Filters:

| Thành phần Spring Integration | Vai trò trong pipeline |
| --- | --- |
| **Message<T>** | Bao bọc payload và headers của dữ liệu di chuyển giữa các bước |
| **MessageChannel** | Pipe đưa message từ endpoint trước đến endpoint sau |
| **MessageHandler / endpoint** | Thành phần tiếp nhận và xử lý message |
| **Message Filter** | Cho message đi tiếp hoặc từ chối theo predicate |
| **Transformer** | Biến đổi payload, đôi khi cả headers và cấu trúc message |
| **Header Enricher / Content Enricher** | Bổ sung metadata hoặc dữ liệu từ nguồn khác |
| **Service Activator** | Gọi dịch vụ nghiệp vụ và có thể tạo kết quả hoặc kết thúc nhánh |
| **Router** | Chọn đường đi tiếp dựa trên nội dung/headers |
| **Splitter / Aggregator** | Chia và ghép các phần của một nhóm dữ liệu |
| **Gateway** | Tạo ranh giới gọi từ mã ứng dụng sang flow và nhận phản hồi khi cần |
| **IntegrationFlow** | Khai báo topology các bước và channel bằng Java DSL |

Nhờ các abstraction này, mỗi endpoint có thể tập trung xử lý một bước. Quy tắc **chuyển tiếp message** được đặt trong cấu hình flow, giúp việc thêm/bỏ một bước rõ ràng hơn so với chuỗi lời gọi cứng.

### Message và headers

Message đi qua nhiều bước mang:

1. **Payload**: dữ liệu nghiệp vụ; có thể đổi kiểu sau Transformer.
2. **Headers**: metadata như eventType, traceId, tenantId, correlationId.

Mỗi bước phải quyết định headers nào cần truyền tiếp. Ví dụ một Transformer đổi **OrderReceived** thành **DispatchCommand** nên giữ correlationId để truy vết, nhưng có thể phải đổi eventType từ **order.received** thành **dispatch.requested**. Không truyền một routing hint chỉ có hiệu lực ở chặng cũ sang chặng mới một cách vô thức.

**Message** bất biến về cấu trúc (không có setter để thay payload/headers), nhưng nếu payload chứa object mutable thì object ấy vẫn có thể bị sửa qua tham chiếu khác. Các kiểu dữ liệu bất biến hoặc bản sao phòng vệ giúp bước độc lập hơn trong flow bất đồng bộ.

### “Pipe” không đồng nghĩa một thread hoặc một queue

MessageChannel có nhiều semantics:

| Channel | Đặc điểm | Hệ quả với pipeline |
| --- | --- | --- |
| **DirectChannel** | Dispatch đồng bộ đến một handler được chọn, trên thread sender | Thuận tiện cho pipeline nhanh, cùng call stack |
| **ExecutorChannel** | Chuyển việc dispatch qua Executor | Tách scheduling/thread, cần xử lý lỗi async và giới hạn tài nguyên |
| **QueueChannel** | PollableChannel có queue | Producer và consumer tách thời điểm; cần poller/receive |
| **PublishSubscribeChannel** | Phát cho nhiều subscriber | Hữu ích để rẽ nhánh fan-out; không phải chuỗi tuần tự |

Nếu một DirectChannel có **ba subscriber**, mỗi message thường được giao **cho một subscriber được dispatcher chọn**, chứ không chạy A rồi B rồi C. Muốn pipeline A → B → C, phải **nối các endpoint bằng các channel theo thứ tự**, hoặc định nghĩa tuyến bằng **IntegrationFlow**.

## 5. Ví dụ xuyên suốt: đơn hàng thành lệnh giao vận

Giả sử một API nhận sự kiện đặt hàng; hệ thống cần:

1. **Validate**: mã đơn không rỗng, số tiền phải lớn hơn 0, tỉnh nhận hàng phải có giá trị.
2. **Normalize**: chuẩn hóa chuỗi tỉnh nhận hàng.
3. **Map**: đổi mô hình OrderReceived sang DispatchCommand.
4. **Dispatch**: ghi lệnh giao vận qua một service riêng.

~~~mermaid
flowchart LR
    API["Checkout API"] --> I["orderInputChannel"]
    I --> V{"Validate"}
    V -->|"Hợp lệ"| C1["validatedOrdersChannel"]
    V -->|"Không hợp lệ"| X["Exception / discard policy"]
    C1 --> N["Normalize"]
    N --> M["Map to DispatchCommand"]
    M --> C2["dispatchCommandsChannel"]
    C2 --> D["Dispatch service"]
~~~

### 5.1. Định nghĩa model và port

Các record thể hiện hợp đồng dữ liệu. Port cho bước cuối giúp tách xử lý thông điệp khỏi cách lưu/gửi dữ liệu thực tế.

~~~java
import java.math.BigDecimal;

record OrderReceived(
        String orderId,
        BigDecimal total,
        String destinationProvince) {}

record NormalizedOrder(
        String orderId,
        BigDecimal total,
        String destinationProvince) {}

record DispatchCommand(
        String orderId,
        BigDecimal declaredValue,
        String destinationProvince) {}

interface DispatchPort {
    void createDispatch(DispatchCommand command);
}
~~~

### 5.2. Các phép biến đổi độc lập

Ta gom logic thuần thành phương thức nhỏ để dễ unit test. Mỗi phương thức có kiểu input/output và điều kiện rõ ràng.

~~~java
import java.util.Locale;

final class OrderSteps {
    private OrderSteps() {}

    static boolean isValid(OrderReceived order) {
        return order != null
                && order.orderId() != null
                && !order.orderId().isBlank()
                && order.total() != null
                && order.total().signum() > 0
                && order.destinationProvince() != null
                && !order.destinationProvince().isBlank();
    }

    static NormalizedOrder normalize(OrderReceived order) {
        if (!isValid(order)) {
            throw new IllegalArgumentException("Đơn hàng không hợp lệ");
        }
        return new NormalizedOrder(
                order.orderId().trim(),
                order.total(),
                order.destinationProvince().trim()
                        .toUpperCase(Locale.ROOT));
    }

    static DispatchCommand toCommand(NormalizedOrder order) {
        return new DispatchCommand(
                order.orderId(),
                order.total(),
                order.destinationProvince());
    }
}
~~~

**Độc lập ở mức code**: toCommand không gọi normalize, normalize không gọi DispatchPort, còn isValid không phụ thuộc database hoặc channel. Flow sẽ quyết định thứ tự phối hợp các bước đó.

### 5.3. Ghép các bước bằng IntegrationFlow Java DSL

Ví dụ sau sử dụng Spring Integration Java DSL và Java 17+. Các record, OrderSteps và DispatchPort ở trên nằm trong cùng package với cấu hình flow.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class OrderPipelineConfiguration {

    @Bean
    MessageChannel orderInputChannel() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel validatedOrdersChannel() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel dispatchCommandsChannel() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow orderToDispatchFlow(DispatchPort dispatchPort) {
        return IntegrationFlow.from("orderInputChannel")
                // Bước 1: chỉ cho order hợp lệ đi tiếp.
                .filter(OrderReceived.class, OrderSteps::isValid,
                        filter -> filter.throwExceptionOnRejection(true))
                .channel("validatedOrdersChannel")
                // Bước 2: chuẩn hóa kiểu dữ liệu đầu vào.
                .transform(OrderReceived.class, OrderSteps::normalize)
                // Bước 3: chuyển sang hợp đồng của hệ thống giao vận.
                .transform(NormalizedOrder.class, OrderSteps::toCommand)
                .channel("dispatchCommandsChannel")
                // Bước 4: thực hiện tác dụng phụ ở biên ứng dụng.
                .handle(DispatchCommand.class, (command, headers) -> {
                    dispatchPort.createDispatch(command);
                    return null; // Endpoint cuối, không phát message kế tiếp.
                })
                .get();
    }
}
~~~

Trong ví dụ:

- **Filter** chặn dữ liệu sai; cấu hình **throwExceptionOnRejection(true)** khiến trường hợp từ chối phát lỗi thay vì âm thầm bỏ message.
- Hai **Transformer** chuyển payload qua các kiểu **OrderReceived → NormalizedOrder → DispatchCommand**.
- **Service Activator** gọi DispatchPort để thực hiện tác dụng phụ.
- Các **DirectChannel** chuyển message đồng bộ giữa các endpoint, giúp quan sát thứ tự xử lý qua call stack.
- Có thể thêm hoặc thay một bước khi giữ được kiểu và ngữ nghĩa đầu vào/đầu ra mà bước kế tiếp mong đợi.

Tên channel tường minh giúp theo dõi flow. Khi không cần ranh giới channel có tên, DSL có thể quản lý các channel trung gian. Điều quan trọng hơn tên là **hợp đồng truyền message** và đường lỗi.

### 5.4. Gửi message từ producer

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Component;

@Component
class OrderPublisher {
    private final MessageChannel orderInput;

    OrderPublisher(
            @Qualifier("orderInputChannel") MessageChannel orderInput) {
        this.orderInput = orderInput;
    }

    void publish(OrderReceived order, String traceId) {
        if (order == null) {
            throw new IllegalArgumentException("Thiếu order");
        }

        Message<OrderReceived> message = MessageBuilder.withPayload(order)
                .setHeader("eventType", "order.received")
                .setHeader("correlationId", order.orderId())
                .setHeader("traceId", traceId)
                .build();

        boolean accepted = orderInput.send(message);
        if (!accepted) {
            throw new IllegalStateException("Không gửi được order message");
        }
    }
}
~~~

**MessageBuilder** mang metadata để Router, error handler hoặc hệ thống quan sát có thể nhận diện sự kiện. Trong hệ thống thật, traceId và tenant context nên lấy từ ngữ cảnh đã xác thực, tránh nhận tùy tiện từ input không đáng tin cậy.

Vì flow này đi qua DirectChannel đồng bộ, producer thường chờ tới khi các handler xử lý xong. Nếu DispatchPort ném exception, lỗi có thể đi ngược call stack; không nên hiểu **send() trả true** là mọi tác động ngoài hệ thống chắc chắn đã được commit bền vững.

## 6. Bước độc lập và thứ tự trong pipeline

Độc lập **không** có nghĩa các bước có thể sắp xếp tùy ý. Pipeline có **phụ thuộc theo dữ liệu**:

~~~mermaid
flowchart LR
    A["Validate<br/>OrderReceived"] --> B["Normalize<br/>NormalizedOrder"]
    B --> C["Map<br/>DispatchCommand"]
    C --> D["Dispatch<br/>Side effect"]
~~~

Nếu hoán đổi Map và Normalize, bước Map sẽ nhận kiểu đầu vào sai. Nếu đặt Dispatch trước Validate, một lệnh giao vận sai có thể được phát ra trước khi phát hiện lỗi.

Có thể phân biệt ba loại phụ thuộc:

| Loại | Nội dung | Cách giảm phụ thuộc |
| --- | --- | --- |
| **Phụ thuộc dữ liệu** | Đầu ra bước trước là đầu vào bước sau | Dùng type/contract và validate rõ ràng |
| **Phụ thuộc kỹ thuật** | Bước A khởi tạo/gọi trực tiếp lớp B | Nối qua channel hoặc port/interface |
| **Phụ thuộc thời gian** | B phải hoàn tất trước C hay có thể chạy sau | Chọn DirectChannel/ExecutorChannel/QueueChannel theo yêu cầu |

Các bước độc lập thường giúp **phát triển, triển khai logic và test dễ hơn**, nhưng nếu toàn bộ flow chạy trong cùng ứng dụng, chúng vẫn chia sẻ vòng đời tiến trình và có thể chung transaction. Muốn tách thành dịch vụ triển khai độc lập, còn cần ranh giới mạng, serialization, hợp đồng phiên bản và cơ chế giao message tin cậy.

### Đặt tên theo hành vi

Một tên như **normalizeProvince** hoặc **convertOrderToDispatchCommand** làm rõ chức năng. Những tên quá rộng như **processData** hoặc **handleSomething** khiến khó nhận biết trách nhiệm và khó phân tích lỗi.

### Một bước, một dạng lỗi

Lỗi validate khác lỗi gọi REST. Một cách phân biệt:

- **Dữ liệu không hợp lệ:** không retry vô hạn; trả lỗi hoặc đưa sang luồng xử lý dữ liệu lỗi.
- **Hệ thống ngoài tạm thời không sẵn sàng:** có thể retry với backoff và giới hạn số lần.
- **Lỗi lập trình hoặc hợp đồng message:** phải ghi nhận, cảnh báo và sửa logic; retry liên tục có thể gây quá tải.

## 7. Mở rộng pipeline: Router, Splitter và Aggregator

Pipes and Filters thường không chỉ có một đường thẳng. Spring Integration cho phép rẽ nhánh hoặc kết hợp luồng bằng các pattern khác:

~~~mermaid
flowchart LR
    IN["OrderReceived"] --> V["Filter: hợp lệ"]
    V --> R{"Router theo khu vực"}
    R -->|"Nội thành"| L["Local dispatch"]
    R -->|"Liên tỉnh"| X["Remote dispatch"]
    L --> AUD["Audit event"]
    X --> AUD
~~~

**Router** quyết định message đi nhánh nào dựa trên payload hoặc header. Với Router, hãy xác định **default route** hoặc policy rõ ràng nếu không có nhánh phù hợp. Không giả định một message được gửi tới nhiều nhánh chỉ vì có nhiều channel đầu ra.

**Splitter** tách một message chứa tập phần tử thành nhiều message con; **Aggregator** ghép chúng trở lại khi đáp ứng điều kiện hoàn thành. Khi đó cần chú ý:

1. **Correlation ID**: nhận diện các message con thuộc cùng một nhóm.
2. **Sequence number/size**: giúp mô tả thứ tự và kích thước nhóm khi được sử dụng.
3. **Release strategy**: điều kiện để Aggregator phát kết quả.
4. **Timeout/message store**: quản lý nhóm chưa đủ phần tử và khả năng xử lý sau lỗi.

Các header correlation và sequence **không tự bảo đảm** các message được xử lý đúng thứ tự hay không bị mất. Đó là trách nhiệm phối hợp của channel, endpoint, message store, producer và consumer.

**Gateway** có thể cung cấp giao diện method call cho ứng dụng bên ngoài flow. Với request/reply, cần xác định đường trả lời và timeout; một pipeline chỉ có endpoint kết thúc không trả kết quả sẽ không tự đáp ứng yêu cầu reply.

## 8. Đồng bộ, bất đồng bộ và hậu quả đối với filter

Mỗi pipe có semantics riêng; thay channel có thể thay đổi đáng kể hành vi mà không phải sửa logic business của từng filter.

### 8.1. Chuỗi đồng bộ qua DirectChannel

~~~mermaid
sequenceDiagram
    participant P as Producer / Thread T1
    participant C as DirectChannel
    participant F1 as Validate
    participant F2 as Normalize
    participant F3 as Dispatch
    P->>C: send(order)
    C->>F1: handleMessage
    F1->>F2: chuyển tiếp qua channel kế
    F2->>F3: chuyển tiếp qua channel kế
    F3-->>F2: return
    F2-->>F1: return
    F1-->>C: return
    C-->>P: send() hoàn tất
~~~

Ưu điểm:

- Dễ suy luận thứ tự trong **một lần gửi**.
- Exception đồng bộ có thể truyền tới caller.
- Có thể giữ transaction gắn với thread nếu các thành phần dùng cùng transaction manager.

Hạn chế:

- Caller phải chờ các bước chạy xong.
- Handler chậm giữ thread của producer.
- Nhiều producer vẫn có thể chạy **đồng thời**; DirectChannel không bảo đảm thứ tự toàn cục giữa các message đến từ các thread khác nhau.

### 8.2. Đưa một ranh giới sang bất đồng bộ

Giả sử bước Dispatch cần gọi API chậm. Có thể đặt **ExecutorChannel** hoặc **QueueChannel** trước bước này:

~~~mermaid
flowchart LR
    P["Producer"] --> V["Validate"]
    V --> N["Normalize"]
    N --> Q["Async boundary<br/>Executor / Queue"]
    Q --> D["Dispatch"]
    D --> E["External API"]
~~~

Điều thay đổi:

| Thuộc tính | Đồng bộ qua DirectChannel | Tách qua ExecutorChannel/QueueChannel |
| --- | --- | --- |
| Thread | Thường cùng thread sender | Có thể tách thread hoặc thời điểm |
| Lúc send() trả về | Thường sau khi handler hoàn tất | Có thể trước khi xử lý hoàn tất |
| Truyền exception về sender | Có thể theo call stack | Lỗi sau đó cần đường xử lý riêng |
| Transaction gắn với thread | Có thể tiếp tục trong một call stack | Không tự động truyền sang worker/poller |
| Khả năng chịu tải tăng vọt | Không có queue trung gian mặc định | Phụ thuộc capacity và cấu hình |
| Bảo đảm sau restart | Không tự có | ExecutorChannel không tự bền; QueueChannel in-memory cũng không tự bền |

**ExecutorChannel** đưa việc dispatch sang executor; queue task nếu có thuộc executor, cần cấu hình bounded queue và rejection policy. **QueueChannel** chứa message và cần consumer/poller để tiếp tục xử lý. Chúng **không** mặc nhiên đảm bảo exactly-once hoặc durable delivery.

## 9. Khi một filter thất bại: lỗi đi đâu?

Một pipeline tốt không chỉ có đường thành công.

~~~mermaid
flowchart TD
    A["Input"] --> V{"Validate"}
    V -->|"Pass"| N["Normalize"]
    V -->|"Reject"| Q["Discard / business error"]
    N --> D["Dispatch"]
    D -->|"Success"| S["Completed"]
    D -->|"Transient failure"| R["Retry có giới hạn"]
    R --> D
    D -->|"Persistent failure"| E["Error channel / DLQ tùy cấu hình"]
~~~

### 9.1. Filter từ chối dữ liệu

Message Filter có thể:

- **Bỏ message** theo chính sách mặc định trong một số cấu hình, tức các bước sau không chạy.
- **Gửi tới discard channel** nếu bạn muốn lưu vết hoặc xử lý trường hợp bị loại.
- **Ném exception** khi cấu hình **throwExceptionOnRejection(true)**.

Chọn theo ý nghĩa nghiệp vụ. Chẳng hạn, loại duplicate event đã xử lý thành công có thể là hành vi bình thường; từ chối đơn hàng thiếu trường bắt buộc thường cần phản hồi có thể chẩn đoán được.

### 9.2. Exception đồng bộ và bất đồng bộ

Trong chuỗi DirectChannel, exception từ một handler thường truyền ngược theo call stack (có thể được bọc bởi exception messaging). Khi chuyển sang executor, poller hoặc inbound adapter bất đồng bộ, exception có thể được chuyển qua **ErrorMessage/errorChannel** tùy kiểu endpoint và cấu hình error handler. Không nên giả định mọi lỗi đều tự động xuất hiện ở cùng một error channel.

### 9.3. Retry và idempotency

Giả sử DispatchPort đã gửi lệnh giao vận tới một hệ thống khác nhưng mất kết nối trước khi nhận phản hồi. Retry có thể phát lệnh thêm lần nữa.

Vì vậy, **retry không đồng nghĩa an toàn**. Hãy dùng **idempotency key** (ví dụ orderId kết hợp loại tác vụ), unique constraint hoặc cơ chế deduplication ở consumer. Giới hạn số lần retry, bổ sung backoff, ghi nhận lỗi cuối và có đường xử lý message không thể xử lý.

### 9.4. Transaction không tự bao trùm mọi pipe

DirectChannel trong cùng thread có thể giữ transaction context của Spring. Tuy nhiên gọi HTTP, gửi email hoặc publish sang broker không tự được rollback khi database transaction của ứng dụng rollback.

Khi cần giữ nhất quán giữa cập nhật dữ liệu và phát sự kiện, có thể áp dụng **transactional outbox**; khi cần phục hồi message sau restart, xem xét persistent message store hoặc broker có cam kết phù hợp.

## 10. Quan sát: biết message đã qua bước nào

Pipes and Filters chia việc lớn thành bước nhỏ, nên có thể theo dõi latency và lỗi **theo từng endpoint**.

| Dữ liệu quan sát | Giá trị |
| --- | --- |
| correlationId / business key | Liên kết các message của cùng đơn hàng |
| traceId | Nối log và trace xuyên nhiều bước/hệ thống |
| Tên endpoint và channel | Xác định bước nào đã chạy |
| Số message vào/ra/từ chối | Theo dõi Filter loại dữ liệu và phát hiện bất thường |
| Thời gian xử lý từng bước | Phát hiện điểm nghẽn |
| Số lần retry và lỗi cuối | Xác định rủi ro lỗi lặp hoặc message mắc kẹt |
| Queue depth / độ tuổi message | Giám sát backlog ở ranh giới bất đồng bộ |

Hãy lưu ý **giá trị header không mặc nhiên đáng tin** nếu do hệ thống bên ngoài gửi tới. tenantId cần được xác thực; traceId nên được truyền theo cơ chế quan sát phù hợp. Tránh log toàn bộ payload và headers có chứa dữ liệu cá nhân, token hay thông tin nhạy cảm.

Khi quan sát một pipeline có nhiều nhánh, correlationId liên kết về mặt nghiệp vụ, trong khi trace/span giúp xác định thời điểm và vị trí thực thi. Chúng bổ sung cho nhau chứ không thay thế các cơ chế xác nhận xử lý.

## 11. Kiểm thử từng bước và kiểm thử toàn pipeline

Tách trách nhiệm khiến việc kiểm thử có hai cấp rõ ràng:

**Unit test** xác minh logic của từng filter/transformer bằng input-output, ít phụ thuộc Spring.

**Integration test** xác minh các endpoint thực sự được nối đúng: message đến đúng handler, thứ tự cho một flow đồng bộ, header cần thiết được giữ, đường bị loại và lỗi hoạt động theo hợp đồng.

### 11.1. Unit test bước chuẩn hóa và mapping

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;

class OrderStepsTest {
    @Test
    void normalizeAndMapWithoutStartingSpring() {
        OrderReceived input = new OrderReceived(
                " ORD-7 ", new BigDecimal("120000"), "  ha noi  ");

        assertTrue(OrderSteps.isValid(input));

        NormalizedOrder normalized = OrderSteps.normalize(input);
        assertEquals("ORD-7", normalized.orderId());
        assertEquals("HA NOI", normalized.destinationProvince());

        DispatchCommand command = OrderSteps.toCommand(normalized);
        assertEquals("ORD-7", command.orderId());
        assertEquals(new BigDecimal("120000"), command.declaredValue());
    }

    @Test
    void invalidAmountIsRejected() {
        OrderReceived input =
                new OrderReceived("ORD-8", BigDecimal.ZERO, "Ha Noi");

        assertFalse(OrderSteps.isValid(input));
        assertThrows(IllegalArgumentException.class,
                () -> OrderSteps.normalize(input));
    }
}
~~~

Test này kiểm tra chính xác **hợp đồng một bước**, không cần channel hay cơ sở dữ liệu. Nếu thay thuật toán chuẩn hóa, ta biết thay đổi ảnh hưởng kiểu dữ liệu nào.

### 11.2. Kiểm thử cách các bước nối nhau qua DirectChannel

Ví dụ sau dựng ba channel độc lập trong bộ nhớ để xác minh thứ tự dispatch, propagation header và việc các bước chạy trên thread sender. Đây là **kiểm thử cơ chế nối chuỗi**, còn cấu hình IntegrationFlow sản phẩm cần được kiểm thử trong Spring context riêng.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class PipeChainTest {
    @Test
    void runsIndependentStepsInDeclaredOrder() {
        DirectChannel input = new DirectChannel();
        DirectChannel checked = new DirectChannel();
        DirectChannel output = new DirectChannel();

        List<String> visited = new ArrayList<>();
        AtomicReference<Message<?>> finalMessage = new AtomicReference<>();
        AtomicReference<Thread> consumerThread = new AtomicReference<>();
        Thread senderThread = Thread.currentThread();

        input.subscribe(message -> {
            visited.add("validate");
            String payload = (String) message.getPayload();
            if (payload.isBlank()) {
                throw new IllegalArgumentException("Trống");
            }
            checked.send(message);
        });

        checked.subscribe(message -> {
            visited.add("normalize");
            String normalized =
                    ((String) message.getPayload()).trim().toUpperCase();
            output.send(MessageBuilder.withPayload(normalized)
                    .copyHeaders(message.getHeaders())
                    .build());
        });

        output.subscribe(message -> {
            visited.add("handle");
            finalMessage.set(message);
            consumerThread.set(Thread.currentThread());
        });

        Message<String> sent = MessageBuilder.withPayload("  order-7  ")
                .setHeader("correlationId", "order-7")
                .build();

        assertTrue(input.send(sent));
        assertEquals(List.of("validate", "normalize", "handle"), visited);
        assertEquals("ORDER-7", finalMessage.get().getPayload());
        assertEquals("order-7",
                finalMessage.get().getHeaders().get("correlationId"));
        assertSame(senderThread, consumerThread.get());
    }

    @Test
    void aFailureStopsTheNextStep() {
        DirectChannel input = new DirectChannel();
        DirectChannel next = new DirectChannel();
        List<String> visited = new ArrayList<>();

        input.subscribe(message -> {
            visited.add("validate");
            throw new IllegalArgumentException("Invalid payload");
        });
        next.subscribe(message -> visited.add("should-not-run"));

        assertThrows(RuntimeException.class,
                () -> input.send(
                        MessageBuilder.withPayload("bad").build()));
        assertEquals(List.of("validate"), visited);
    }
}
~~~

Điểm cần kiểm chứng thêm với **IntegrationFlow** hoàn chỉnh:

1. Filter được cấu hình để ném lỗi hay discard đúng yêu cầu.
2. Payload và headers giữa các Transformer đúng kiểu và giá trị.
3. Service cuối không bị gọi nếu một bước đầu từ chối message.
4. Retry không tạo side effect trùng khi handler gọi hệ thống ngoài.
5. Khi thay một pipe thành ExecutorChannel/QueueChannel, test thread, timeout, backpressure và error handling được điều chỉnh tương ứng.

### Không nhầm unit test với bảo đảm vận hành

Unit test chạy thành công không chứng minh message sẽ sống qua restart, không chứng minh transaction distributed, và cũng không chứng minh bảo đảm exactly-once. Các yêu cầu này cần test tích hợp với hạ tầng lưu trữ, broker, transaction, khởi động lại tiến trình và tình huống lỗi thật.

## 12. Khi nào Pipes and Filters phù hợp?

Mẫu này phù hợp khi:

- Công việc gồm một chuỗi **bước biến đổi/kiểm tra** rõ ràng.
- Mỗi bước có thể mô tả bằng **đầu vào, đầu ra, trạng thái lỗi**.
- Cần thay đổi một bước hoặc bổ sung bước mới mà ít tác động tới phần khác.
- Có nhu cầu quan sát/kiểm thử kết quả theo từng công đoạn.
- Muốn kết hợp các Enterprise Integration Patterns như Filter, Transformer, Router, Splitter/Aggregator.

Mẫu này có giới hạn khi:

- Một nghiệp vụ đòi hỏi rất nhiều trạng thái toàn cục chia sẻ hoặc điều phối tương tác phức tạp giữa nhiều nhánh.
- Mỗi bước thực hiện side effect mà không có cơ chế kiểm soát giao dịch, retry và idempotency.
- Quá nhiều bước nhỏ làm tăng độ phức tạp topology, serialization hoặc logging so với giá trị mang lại.
- Cần điều phối quy trình dài ngày, chờ sự kiện bên ngoài và quản lý state qua nhiều lần restart; khi đó có thể cần saga/process manager hoặc workflow engine bổ sung.

**Bước độc lập** là nguyên tắc thiết kế, không phải lời hứa rằng mọi hệ thống đều có thể xử lý song song hoặc thay bước mà không cần xét hợp đồng dữ liệu.

## 13. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách tránh |
| --- | --- | --- |
| Xem Message Filter là toàn bộ Pipes and Filters | Bỏ qua Transformer, Service Activator và vai trò channel | Phân biệt mẫu kiến trúc với endpoint |
| Đăng ký mọi handler lên một DirectChannel rồi chờ chúng chạy lần lượt | DirectChannel unicast tới một subscriber được chọn | Dùng IntegrationFlow hoặc các channel nối tiếp |
| Để một bước gọi trực tiếp mọi bước còn lại | Phụ thuộc cứng, khó thay và test | Tách công đoạn, cho flow/channel điều phối |
| Mỗi bước tùy ý thay đổi headers | Correlation/route sai ở downstream | Định nghĩa hợp đồng header và nguyên tắc propagation |
| Dùng payload mutable được chia sẻ qua nhiều nhánh | Race condition, kết quả khó đoán | Immutable model hoặc defensive copy |
| Cho Filter âm thầm loại dữ liệu sai cần phản hồi | Khó nhận ra nguyên nhân từ chối | Cấu hình discard hoặc exception có chủ đích |
| Chèn ExecutorChannel mà không xét transaction | Thay đổi thread và đường truyền lỗi | Thiết kế ranh giới async, retry và test lại |
| Retry cả flow có side effect không idempotent | Đơn hàng, thông báo, giao vận có thể bị tạo lặp | Dùng idempotency key, retry theo bước |
| Xem QueueChannel in-memory là bền vững | Có thể mất backlog khi restart | Message store bền hoặc broker phù hợp |
| Không đo latency và reject theo bước | Không biết điểm nghẽn và nguyên nhân mất message | Metrics, tracing và correlationId |

## 14. Bài thực hành: xây dựng pipeline nhập dữ liệu

Hãy thiết kế một flow nhận dữ liệu **ProductImported(productId, rawPrice, category)** và tạo **CatalogCommand**.

**Yêu cầu:**

1. **Validate:** productId và category phải có giá trị; rawPrice phải chuyển được thành số dương.
2. **Normalize:** chuẩn hóa category theo một quy ước xác định, ví dụ trim và chữ hoa.
3. **Map:** tạo CatalogCommand với kiểu giá tiền **BigDecimal**.
4. **Persist:** gọi CatalogPort để ghi vào hệ thống đích.
5. **Observability:** giữ correlationId cho toàn bộ flow, ghi nhận từng bước đã chạy.
6. **Error handling:** định nghĩa hành vi với giá sai định dạng và với lỗi database tạm thời.

Gợi ý kiến trúc:

~~~mermaid
flowchart LR
    A["ProductImported"] --> V{"Validate"}
    V -->|"OK"| N["Normalize"]
    V -->|"Invalid"| E["Business error"]
    N --> M["Map to CatalogCommand"]
    M --> P["CatalogPort"]
    P -->|"Transient error"| R["Retry / DLQ theo policy"]
~~~

**Mở rộng**: giả sử một sản phẩm cần đồng thời cập nhật **search index** và **audit log**. Hãy xác định nên dùng Router, PublishSubscribeChannel hay hai bước tuần tự. Đáp án phụ thuộc việc **cả hai nhánh có bắt buộc chạy**, có thể **thất bại độc lập** hay phải **thành công trong cùng một giao dịch**. Nếu cần phục hồi sau restart, chỉ thêm PublishSubscribeChannel nội bộ là chưa đủ.

### Câu hỏi tự kiểm tra

1. “Filter độc lập” trong kiến trúc Pipes and Filters được hiểu theo những hợp đồng nào?
2. Vì sao một Spring Integration Transformer vẫn có thể được coi là filter trong nghĩa kiến trúc?
3. Sự khác nhau giữa phụ thuộc dữ liệu và phụ thuộc cài đặt trực tiếp là gì?
4. Điều gì thay đổi khi thêm ExecutorChannel trước bước Persist?
5. Filter từ chối message nên ném lỗi hay discard trong trường hợp nào?
6. Tại sao correlationId và idempotency key có vai trò khác nhau?
7. Một flow có nhiều bước nhỏ luôn dễ bảo trì hơn một flow ngắn hay không? Hãy nêu điều kiện.

## 15. Checklist thiết kế một pipeline có thể mở rộng

- Mỗi bước có **một trách nhiệm chính** và hợp đồng đầu vào/đầu ra cụ thể.
- Kiểu payload và những headers bắt buộc được mô tả rõ.
- Không cố định quan hệ giữa các filter bằng các lệnh khởi tạo/gọi lẫn nhau không cần thiết.
- Cấu hình rõ đường đi của message hợp lệ, message bị loại và message lỗi.
- Chọn DirectChannel/ExecutorChannel/QueueChannel dựa trên semantics của từng ranh giới.
- Xác định thứ tự, concurrency, transaction, khả năng lưu bền và backpressure cần bảo đảm.
- Những side effect có retry phải được xem xét về idempotency.
- Có unit test các bước thuần và integration test topology của flow.
- Theo dõi trace/correlation, latency, retry và tỷ lệ từ chối theo từng endpoint.

**Kết luận:** Pipes and Filters cho phép xây dựng quy trình bằng các bước xử lý **độc lập về trách nhiệm và cài đặt**, liên kết với nhau qua **hợp đồng message và channel**. Spring Integration cung cấp công cụ để ghép những bước đó bằng IntegrationFlow, từ các pipeline đồng bộ đơn giản đến flow rẽ nhánh, chia/ghép message hoặc xử lý bất đồng bộ. Mức độ tin cậy của toàn luồng còn phụ thuộc vào lựa chọn channel, cơ chế lỗi, transaction, retry và kiểm thử.

## Tài liệu tham khảo

- [Spring Integration Reference](https://docs.spring.io/spring-integration/reference/): các thành phần Enterprise Integration Patterns và hướng dẫn xây dựng flow.
- [Spring Integration — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): IntegrationFlow, Transformer, Filter và Service Activator trong cấu hình Java.
- [Spring Integration — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): hành vi DirectChannel, ExecutorChannel, QueueChannel và PublishSubscribeChannel.
- [Spring Framework — Integration](https://docs.spring.io/spring-framework/reference/integration.html): nền tảng messaging và tích hợp của Spring.
