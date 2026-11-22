# Pipes and filters

## 1. Mục tiêu bài học

Trong chương **Mô hình message flow** của module **SPRING_INTEGRATION_CORE**, Pipes and Filters là nền tảng để đọc và thiết kế một luồng thông điệp: dữ liệu đi qua các bước có trách nhiệm rõ ràng, còn việc nối các bước được biểu diễn bằng channel.

Sau bài học, bạn có thể:

- Phân biệt pipe, bước xử lý, message và endpoint trong một luồng Spring Integration.
- Chuyển một phương thức xử lý nhiều trách nhiệm thành các bước Java DSL có hợp đồng đầu vào, đầu ra.
- Giải thích thứ tự xử lý, đường đi của thông điệp bị loại và đường đi của lỗi.
- Chọn vị trí cần thực thi đồng bộ hoặc cần đệm thông điệp.
- Quan sát kết quả và xác định những trường hợp cần kiểm thử trước khi mở rộng luồng.

## 2. Bài toán: một đơn hàng cần đi qua nhiều bước

Giả sử một đối tác gửi đơn hàng dưới dạng:

~~~text
 ord-101 | 125000 | vnd
~~~

Ứng dụng cần bỏ khoảng trắng thừa, chuyển dữ liệu thành đối tượng Java, chỉ chấp nhận số tiền dương với đồng tiền VND, rồi tạo kết quả tiếp nhận.

Một cách triển khai là gom tất cả vào `processOrder(String raw)`. Khi yêu cầu tăng thêm, phương thức này có thể đồng thời phân tích dữ liệu, kiểm tra nghiệp vụ, ghi cơ sở dữ liệu, gọi dịch vụ và gửi thông báo. Mỗi thay đổi nhỏ phải đi qua một khối điều phối lớn; việc dùng lại riêng bước phân tích hoặc xác định điểm thất bại cũng khó hơn.

Pipes and Filters chia công việc thành các bước độc lập và kết nối chúng bằng kênh truyền thông điệp. Mỗi bước nhận dữ liệu qua đầu vào, thực hiện trách nhiệm của mình và chuyển kết quả qua đầu ra. Đây là cấu trúc được mô tả trong [Enterprise Integration Patterns — Pipes and Filters](https://www.enterpriseintegrationpatterns.com/patterns/messaging/PipesAndFilters.html).

Với bài toán trên, ta chọn:

~~~mermaid
flowchart LR
    I["ordersInput<br/>String"] --> N["Bỏ khoảng trắng"]
    N --> P["Phân tích thành OrderCommand"]
    P --> F{"Số tiền dương<br/>và currency = VND?"}
    F -- "Đạt" --> H["Tạo OrderReceipt"]
    H --> O["acceptedOrders"]
    F -- "Không đạt" --> D["rejectedOrders"]
    P -. "Sai định dạng" .-> E["Ngoại lệ về bên gửi<br/>trong ví dụ đồng bộ"]
~~~

Các mũi tên thể hiện đường đi logic. Muốn biết thông điệp đi qua thread nào, có chờ hay có được lưu bền vững hay không, cần xem loại channel và cấu hình endpoint.

## 3. Ánh xạ mô hình vào Spring Integration

| Khái niệm | Vai trò trong luồng | Thành phần thường dùng |
| --- | --- | --- |
| Message | Mang dữ liệu và ngữ cảnh của lần xử lý | `Message<T>` với payload và headers |
| Pipe | Kết nối đầu ra của một bước với đầu vào bước khác | `MessageChannel` |
| Bước xử lý | Thực hiện một trách nhiệm trên thông điệp | Transformer, filter, service activator |
| Endpoint | Nối logic xử lý với cơ chế nhận thông điệp và vòng đời | Endpoint đăng ký trong Spring context |
| Điểm vào/ra | Kết nối người gọi hoặc hệ thống bên ngoài với luồng | Gateway, channel adapter hoặc thao tác gửi/nhận trực tiếp |
| Bản mô tả luồng | Khai báo các thành phần và quan hệ giữa chúng | `IntegrationFlow` trong Java DSL |

### 3.1. “Filter” trong tên mẫu rộng hơn `MessageFilter`

Trong cụm **Pipes and Filters**, filter là tên gọi một bước xử lý nói chung. Bước đó có thể chuyển đổi dữ liệu hoặc gọi nghiệp vụ.

Trong Spring Integration, **Message Filter** là một mẫu cụ thể: đánh giá điều kiện để quyết định thông điệp có đi tiếp hay không. Vì vậy, một pipeline triển khai Pipes and Filters có thể chứa nhiều transformer mà không có lời gọi `.filter()` nào.

Khi trao đổi thiết kế, nên dùng “bước xử lý” cho nghĩa rộng và “bộ lọc thông điệp” cho bước quyết định chấp nhận hoặc loại bỏ. Cách gọi này giúp tránh việc hiểu mọi bước của pipeline đều phải trả về `boolean`.

### 3.2. Java DSL mô tả cấu trúc, message kích hoạt xử lý

Java DSL tạo một `IntegrationFlow` dưới dạng Spring bean. Khi context khởi tạo, framework đăng ký các channel và endpoint tương ứng; những lời gọi như `.transform()` và `.handle()` khai báo các bước của luồng. Xem [Spring Integration — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html).

Do đó, đoạn cấu hình:

~~~java
IntegrationFlow.from("ordersInput")
        .transform(String.class, String::strip)
        .transform(String.class, OrderFlowDemo::parseOrder)
        .get();
~~~

không phân tích đơn hàng ngay khi gọi phương thức `@Bean`. Hai phép biến đổi được thực hiện khi có message đi vào `ordersInput`.

Giữa các endpoint liền kề, DSL có thể tạo channel nội bộ. Vì vậy, không thấy `.channel(...)` ở giữa hai dòng DSL không có nghĩa là hai bước đã mất cơ chế truyền message. Các quy tắc cấu hình và đặt tên được trình bày trong [Spring Integration — Message Channels trong Java DSL](https://docs.spring.io/spring-integration/reference/dsl/java-channels.html).

Đoạn ngắn trên chỉ minh họa cách khai báo. Ví dụ hoàn chỉnh bên dưới có channel đầu ra để nhận kết quả cuối cùng.

## 4. Thiết kế hợp đồng trước khi viết luồng

Tách một phương thức lớn thành nhiều lambda chưa đủ. Đầu ra của bước trước phải thỏa mãn điều kiện đầu vào của bước sau.

Với bài toán đơn hàng, ta định nghĩa:

| Bước | Payload đầu vào | Payload trên đường thành công | Hành vi khi không thể tiếp tục |
| --- | --- | --- | --- |
| Bỏ khoảng trắng | `String` | `String` đã `strip()` | Sai kiểu đầu vào là lỗi hợp đồng |
| Phân tích | Chuỗi có ba trường phân cách bằng `|` | `OrderCommand` | Sai cấu trúc, mã đơn rỗng hoặc số tiền không đọc được thì ném ngoại lệ |
| Kiểm tra nghiệp vụ | `OrderCommand` | Giữ nguyên thông điệp được chấp nhận | Số tiền không dương hoặc đồng tiền khác VND thì gửi sang `rejectedOrders` |
| Tạo kết quả | `OrderCommand` hợp lệ | `OrderReceipt` | Ngoại lệ trong bước này được coi là lỗi xử lý |
| Thu kết quả | `OrderReceipt` | Được giữ trong `acceptedOrders` để đọc ra | Đầu ra cần có nơi tiếp nhận phù hợp |

Ở đây, “đọc được số tiền” và “số tiền được chấp nhận” là hai điều kiện khác nhau:

- `abc` không thể phân tích thành `BigDecimal`: dữ liệu không đúng định dạng.
- `-500` phân tích được nhưng không đạt chính sách tiếp nhận: thông điệp bị loại theo nghiệp vụ.

Quyết định phân loại này thuộc thiết kế ứng dụng. Một hệ thống khác có thể đưa cả hai loại sang kênh kiểm tra thủ công; điều quan trọng là hợp đồng phải nói rõ hành vi.

## 5. Ví dụ Java DSL hoàn chỉnh

Ví dụ dùng Java có hỗ trợ `record`, cùng các thư viện Spring Context và Spring Integration Core tương thích do dự án quản lý. Không cần kết nối broker hoặc cơ sở dữ liệu.

Đặt mã nguồn sau trong `OrderFlowDemo.java`. Trong ví dụ:

- `ordersInput` là `DirectChannel`.
- Các bước giữa luồng dùng kết nối trực tiếp do DSL tạo.
- `acceptedOrders` và `rejectedOrders` là hàng đợi trong bộ nhớ, mỗi hàng đợi có sức chứa 10 message.
- `main()` đóng vai trò bên gửi và chủ động đọc kết quả từ hai hàng đợi.

~~~java
import java.math.BigDecimal;
import java.util.Locale;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;

@Configuration
@EnableIntegration
public class OrderFlowDemo {

    public record OrderCommand(
            String orderId,
            BigDecimal amount,
            String currency) {
    }

    public record OrderReceipt(
            String orderId,
            BigDecimal amount,
            String currency,
            String status) {
    }

    @Bean
    public MessageChannel ordersInput() {
        return new DirectChannel();
    }

    @Bean
    public QueueChannel acceptedOrders() {
        return new QueueChannel(10);
    }

    @Bean
    public QueueChannel rejectedOrders() {
        return new QueueChannel(10);
    }

    @Bean
    public IntegrationFlow orderFlow() {
        return IntegrationFlow.from("ordersInput")
                .transform(String.class, String::strip)
                .transform(String.class, OrderFlowDemo::parseOrder)
                .filter(
                        OrderCommand.class,
                        order -> order.amount().signum() > 0
                                && "VND".equals(order.currency()),
                        endpoint -> endpoint.discardChannel("rejectedOrders"))
                .handle(
                        OrderCommand.class,
                        (order, headers) -> new OrderReceipt(
                                order.orderId(),
                                order.amount(),
                                order.currency(),
                                "ACCEPTED"))
                .channel("acceptedOrders")
                .get();
    }

    public static OrderCommand parseOrder(String raw) {
        String[] fields = raw.split("\\|", -1);

        if (fields.length != 3) {
            throw new IllegalArgumentException(
                    "Expected orderId|amount|currency");
        }

        String orderId = fields[0].strip();
        if (orderId.isEmpty()) {
            throw new IllegalArgumentException("orderId must not be empty");
        }

        BigDecimal amount = new BigDecimal(fields[1].strip());
        String currency = fields[2].strip().toUpperCase(Locale.ROOT);

        return new OrderCommand(orderId, amount, currency);
    }

    private static void send(
            MessageChannel input, String payload, String traceId) {
        boolean sent = input.send(
                MessageBuilder.withPayload(payload)
                        .setHeader("traceId", traceId)
                        .build(),
                1_000);

        if (!sent) {
            throw new IllegalStateException("Input channel did not accept message");
        }
    }

    private static Message<?> receiveRequired(PollableChannel channel) {
        Message<?> message = channel.receive(1_000);
        if (message == null) {
            throw new IllegalStateException("Expected an output message");
        }
        return message;
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(OrderFlowDemo.class)) {

            MessageChannel input =
                    context.getBean("ordersInput", MessageChannel.class);
            PollableChannel accepted =
                    context.getBean("acceptedOrders", PollableChannel.class);
            PollableChannel rejected =
                    context.getBean("rejectedOrders", PollableChannel.class);

            send(input, " ord-101 | 125000 | vnd ", "trace-001");
            Message<?> success = receiveRequired(accepted);
            System.out.println("ACCEPTED: " + success.getPayload());
            System.out.println(
                    "TRACE: " + success.getHeaders().get("traceId"));

            send(input, "ord-102|-500|VND", "trace-002");
            Message<?> discarded = receiveRequired(rejected);
            System.out.println("REJECTED: " + discarded.getPayload());

            try {
                send(input, "ord-103|abc|VND", "trace-003");
            }
            catch (MessagingException exception) {
                System.out.println("ERROR: dữ liệu không phân tích được");
            }
        }
    }
}
~~~

Kết quả mong đợi của chương trình, ngoài log khởi động framework:

~~~text
ACCEPTED: OrderReceipt[orderId=ord-101, amount=125000, currency=VND, status=ACCEPTED]
TRACE: trace-001
REJECTED: OrderCommand[orderId=ord-102, amount=-500, currency=VND]
ERROR: dữ liệu không phân tích được
~~~

`parseOrder()` dùng `split("\\|", -1)` vì `|` có ý nghĩa đặc biệt trong biểu thức chính quy. Tham số `-1` giữ trường rỗng cuối chuỗi, giúp đầu vào như `ord-104|100|` vẫn được nhận diện đúng là ba trường, rồi đi đến bước kiểm tra đồng tiền.

Ví dụ chưa ghi nhận đơn hàng vào nơi lưu trữ. `OrderReceipt` ở đây là kết quả của bước minh họa, không phải bằng chứng rằng một giao dịch kinh doanh đã được lưu bền vững.

## 6. Đọc luồng theo từng message

### 6.1. Đơn hợp lệ

Với ` ord-101 | 125000 | vnd `:

1. `ordersInput` tiếp nhận một message có payload là chuỗi và header `traceId`.
2. Transformer thứ nhất bỏ khoảng trắng ở hai đầu chuỗi.
3. Transformer thứ hai phân tích ba trường và chuẩn hóa đồng tiền thành `VND`.
4. Filter đánh giá điều kiện trên `OrderCommand` và cho đi tiếp.
5. Handler tạo `OrderReceipt`.
6. Message kết quả được đưa vào `acceptedOrders`; `main()` đọc ra bằng `receive()`.

Trong cấu hình này, luồng xử lý đến thao tác đưa kết quả vào hàng đợi diễn ra trên thread gọi `send()`. Việc dùng hàng đợi ở đầu ra chỉ cho phép chương trình lấy kết quả sau đó; nó không tự tạo một worker xử lý nghiệp vụ.

### 6.2. Đơn bị từ chối theo nghiệp vụ

Với `ord-102|-500|VND`, bước phân tích vẫn tạo được `OrderCommand`. Filter trả về `false`, nên message đi sang `rejectedOrders` và không đi đến handler tạo receipt.

Payload bị loại là `OrderCommand` vì đó là payload tại thời điểm filter chạy. Nếu cần đối soát cả dữ liệu gốc, cần thiết kế cách giữ bản gốc hoặc tham chiếu đến bản gốc từ đầu luồng.

Header `traceId` giúp gắn những quan sát ở các bước với cùng một lần xử lý. Trong ví dụ, các hàm biến đổi trả về payload và framework xử lý việc tạo message tiếp theo; tránh tự dựng message mới rồi vô tình bỏ mất ngữ cảnh cần dùng.

### 6.3. Dữ liệu không phân tích được

Với `ord-103|abc|VND`, `new BigDecimal("abc")` thất bại trong transformer. Filter chưa được gọi, nên cấu hình `discardChannel` của filter không tiếp nhận trường hợp này.

Đó là một khác biệt quan trọng khi chẩn đoán: **kênh nhận message bị filter loại không tự động trở thành kênh nhận mọi lỗi của pipeline**.

## 7. Channel quyết định cách các bước phối hợp khi chạy

Cùng một sơ đồ nghiệp vụ có thể có hành vi thực thi rất khác khi thay channel.

| Channel | Cách chuyển giao chính | Điều cần cân nhắc khi thiết kế |
| --- | --- | --- |
| `DirectChannel` | Gọi một subscriber trên thread gửi | Các bước nối trực tiếp làm bên gửi chờ |
| `QueueChannel` | Giữ message để bên nhận lấy ra | Cần consumer đọc; xác định capacity và timeout |
| `ExecutorChannel` | Chuyển việc xử lý qua executor | Quản lý thread pool, quá tải và đường báo lỗi |
| `PublishSubscribeChannel` | Phát tới các subscriber | Dùng khi cần nhiều bên nhận; executor quyết định việc tách thread |

Nhiều consumer cùng đọc một queue không có nghĩa là mọi consumer đều nhận cùng một message. Cũng không nên dùng nhiều subscriber trên một `DirectChannel` để thay cho một chuỗi bước tuần tự.

Các khác biệt này được mô tả trong [Spring Integration — Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html).

### 7.1. Pipeline đồng bộ không có nghĩa là toàn ứng dụng chỉ có một thread

Ví dụ chính giữ mỗi lần gửi trên thread người gọi. Nếu nhiều thread đồng thời gọi `send()`, các lần xử lý vẫn có thể chạy đồng thời qua cùng các bean.

Vì vậy, nên viết các bước xử lý không giữ trạng thái thay đổi của từng message trong field dùng chung. Đoạn dưới dễ gây lẫn dữ liệu:

~~~java
// Ví dụ thiết kế cần tránh khi cùng instance nhận nhiều message.
private String currentOrderId;
~~~

Ưu tiên biến cục bộ và truyền dữ liệu qua payload hoặc headers. Trong bài này, các record chỉ chứa giá trị bất biến như `String` và `BigDecimal`, nên việc chia sẻ dữ liệu dễ kiểm soát hơn.

### 7.2. Thêm queue giữa luồng thì phải có bên lấy message ra

Nếu muốn đệm đơn đã hợp lệ trước bước xử lý nghiệp vụ, có thể thêm bean:

~~~java
@Bean
public QueueChannel validatedOrders() {
    return new QueueChannel(100);
}
~~~

Sau đó thay phần `.handle(...)` ở cuối `orderFlow()` bằng đoạn cấu hình sau, giữ nguyên các bước trước đó và `.channel("acceptedOrders").get()` phía sau:

~~~java
.channel("validatedOrders")
.handle(
        OrderCommand.class,
        (order, headers) -> new OrderReceipt(
                order.orderId(),
                order.amount(),
                order.currency(),
                "ACCEPTED"),
        endpoint -> endpoint.poller(
                Pollers.fixedDelay(Duration.ofMillis(100))
                        .maxMessagesPerPoll(10)))
~~~

Đoạn thay thế cần thêm các import:

~~~java
import java.time.Duration;
import org.springframework.integration.dsl.Pollers;
~~~

Poller gắn với endpoint đọc `validatedOrders`. Hai queue ở cuối ví dụ chính không cần poller của framework vì `main()` đã chủ động gọi `receive()`; còn queue ở giữa pipeline cần một endpoint tiếp tục lấy message để xử lý.

Sau thay đổi này, bên gửi có thể hoàn tất khi đơn hợp lệ đã vào `validatedOrders`, trong khi receipt được tạo ở lần poll tiếp theo. Cần đánh giá lại timeout chờ đầu ra và đường báo lỗi sau ranh giới queue.

Các queue mặc định giữ dữ liệu trong bộ nhớ; nếu cần sống qua lần khởi động lại, phải lựa chọn cơ chế lưu trữ phù hợp. Spring mô tả thêm các lựa chọn này trong [QueueChannel Configuration](https://docs.spring.io/spring-integration/reference/channel/configuration.html).

## 8. Thiết kế rõ đường bị loại và đường lỗi

### 8.1. Bộ lọc không đạt điều kiện

Một bộ lọc có thể cho message đi tiếp, chuyển message bị loại sang discard channel hoặc phát sinh ngoại lệ theo cấu hình. Nếu không cấu hình discard channel và không yêu cầu ném ngoại lệ, message bị loại không có đầu ra trên nhánh chính. Xem [Spring Integration — Filter](https://docs.spring.io/spring-integration/reference/filter.html).

Trong ví dụ đơn hàng, dùng `rejectedOrders` vì cần quan sát dữ liệu bị từ chối. Với yêu cầu từ chối phải được báo thành lỗi, có thể **thay** cấu hình filter hiện tại bằng:

~~~java
.filter(
        OrderCommand.class,
        order -> order.amount().signum() > 0
                && "VND".equals(order.currency()),
        endpoint -> endpoint.throwExceptionOnRejection(true))
~~~

Hai lựa chọn thể hiện hai hợp đồng tiếp nhận khác nhau. Cần chọn theo kỳ vọng của bên gọi và cách vận hành hệ thống.

### 8.2. Ngoại lệ khi thực thi

Trong một chuỗi `DirectChannel`, ngoại lệ thông thường truyền về bên gửi theo call stack. Khi xử lý đã chuyển sang task của executor hoặc poller, cần quan sát cơ chế phát `ErrorMessage`; error handler của framework có thể dùng header `errorChannel` hoặc kênh `errorChannel` chung. Xem [Spring Integration — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html).

Với ví dụ chính, `try/catch` quanh lần gửi thứ ba quan sát được lỗi phân tích. Sau khi thêm queue giữa luồng, một lỗi xảy ra trong handler được poller gọi không còn thuộc call stack của lần gửi ban đầu.

Chỉ đặt header `errorChannel` không tự biến mọi ngoại lệ đồng bộ thành một message lỗi. Khi thiết kế nhánh lỗi, cần xác định rõ thành phần nào bắt ngoại lệ và phát `ErrorMessage`.

### 8.3. Gateway cần hợp đồng phản hồi đầy đủ

Gateway có thể cung cấp một giao diện Java để gọi vào pipeline. Nếu phương thức gateway yêu cầu kết quả trả về, cần thiết kế cả trường hợp thành công, bị từ chối và lỗi.

Ví dụ hiện tại gửi kết quả vào `acceptedOrders` để đọc trực tiếp. Gắn thêm gateway vào đầu vào chưa đủ để gateway tự nhận các kết quả đang được chuyển tới queue đầu ra này.

Với endpoint tạo reply, output channel tường minh được ưu tiên; khi không cấu hình output channel, `replyChannel` có thể cung cấp địa chỉ phản hồi. Handler trả về `null` hoặc `void` cũng có thể kết thúc xử lý mà không tạo reply. Những quy tắc này được mô tả trong [Spring Integration — Service Activator](https://docs.spring.io/spring-integration/reference/service-activator.html).

Một filter loại message mà không tạo phản hồi có thể làm bên gọi request–reply chờ hết thời gian. Chẳng hạn, API tiếp nhận đơn hàng nên chọn một trong các hợp đồng:

- Trả về kết quả tiếp nhận hoặc từ chối có cấu trúc.
- Báo từ chối bằng ngoại lệ theo giao diện đã thống nhất.
- Chỉ nhận lệnh theo cơ chế một chiều và cung cấp cách quan sát kết quả riêng.

## 9. Thứ tự các bước là một phần của nghiệp vụ

Các bước có trách nhiệm riêng nhưng vẫn có thể phụ thuộc đầu ra của nhau.

Trong luồng này, điều kiện `amount().signum() > 0` yêu cầu một `BigDecimal`; do đó cần phân tích trước khi kiểm tra. Nếu chuyển filter lên trước transformer, payload vẫn là `String` và hợp đồng không còn khớp.

Tương tự, ta chuẩn hóa `vnd` thành `VND` trước khi kiểm tra. Nếu kiểm tra chuỗi đồng tiền nguyên bản bằng so sánh phân biệt chữ hoa và chữ thường, đầu vào hợp lệ theo thỏa thuận có thể bị từ chối.

Một trình tự hợp lý cho ví dụ là:

~~~text
Dữ liệu thô
→ Đọc cấu trúc và chuẩn hóa
→ Kiểm tra điều kiện tiếp nhận
→ Thực hiện tác dụng nghiệp vụ
→ Công bố kết quả
~~~

Khi thêm bước mới, hãy viết rõ:

1. Bước này cần dữ liệu đã được bước nào chuẩn bị?
2. Nếu thất bại ở đây, những tác dụng nào đã xảy ra?
3. Có cần giữ dữ liệu trước biến đổi để điều tra hoặc xử lý lại?

Ví dụ, kiểm tra số tiền sau khi đã trừ tiền làm thay đổi hậu quả của nhánh từ chối. Việc sơ đồ có thể sắp xếp lại không đảm bảo mọi thứ tự đều hợp lệ.

## 10. Ranh giới thông điệp và tác dụng phụ

### 10.1. Giữ hợp đồng dữ liệu đủ rõ

Ở đầu vào, ví dụ nhận chuỗi ba trường. Sau bước phân tích, các bước nghiệp vụ làm việc với `OrderCommand`, thay vì tự tách chuỗi lặp lại.

Nếu nhiều nguồn gửi JSON, CSV hoặc dữ liệu từ file, có thể xây dựng các đoạn chuyển đổi đầu vào riêng rồi đưa về cùng một kiểu lệnh. Phần kiểm tra và xử lý lệnh sau đó có cơ hội dùng lại.

Không nên đưa mọi yêu cầu chuyển đổi vào một bước khổng lồ. Có thể tách riêng khi hai phần có quy tắc thay đổi khác nhau, cần dùng lại hoặc cần quan sát độc lập; những thao tác nhỏ luôn đi cùng nhau vẫn có thể nằm trong một hàm.

### 10.2. Không dùng `null` để ngầm biểu diễn mọi kết quả

Transformer có trách nhiệm tạo đầu ra hợp lệ; trả về `null` không phải cách lọc message của transformer trong Spring Integration. Xem [Spring Integration — Transformer](https://docs.spring.io/spring-integration/reference/transformer.html).

Với một bước “đơn không hợp lệ thì không xử lý tiếp”, dùng filter hoặc một kết quả nghiệp vụ tường minh giúp người đọc nhìn thấy chính sách. Cần tránh việc người gọi không phân biệt được “bị từ chối”, “không tìm thấy dữ liệu” và “hàm xử lý quên trả kết quả”.

### 10.3. Retry cần biết tác dụng nào đã xảy ra

Giả sử sau này pipeline có hai bước:

~~~text
Ghi nhận thanh toán → Gửi thông báo
~~~

Nếu gửi thông báo thất bại rồi chạy lại toàn pipeline, thanh toán có thể được ghi nhận lần nữa. Khi thêm retry, cần xác định phạm vi retry và khóa nhận diện nghiệp vụ như `orderId` hoặc một idempotency key.

`traceId` chủ yếu hỗ trợ theo dõi; một đơn hàng được gửi lại có thể có `traceId` mới. Vì vậy, khóa chống thực hiện trùng cần dựa trên quy ước nghiệp vụ riêng.

Tương tự, một luồng nối nhiều bước không tự đảm bảo tất cả cùng commit hoặc cùng rollback. Cần thiết kế transaction theo các tài nguyên thật sự tham gia và cơ chế phối hợp được dùng. Ranh giới executor hoặc queue là một dấu hiệu cần xem xét lại giả định về transaction của thread gửi.

## 11. Khi pipeline mở rộng thành nhiều nhánh hoặc nhiều message

Pipes and Filters cung cấp cách ghép các bước; luồng tích hợp thực tế có thể cần thêm các mẫu trong module:

| Nhu cầu phát sinh trong bài toán đơn hàng | Hướng mở rộng |
| --- | --- |
| Phân loại đơn theo khu vực để giao cho bộ phận phù hợp | Router lựa chọn đường xử lý |
| Thông báo cùng một sự kiện cho nhiều bên quan tâm | Nhánh publish–subscribe |
| Xử lý từng dòng hàng của một đơn | Splitter tạo các message thành phần |
| Đợi kết quả các dòng hàng để lập kết quả tổng | Aggregator với quy tắc tương quan và hoàn tất |
| Bọc luồng sau một giao diện Java | Messaging gateway |

Khi một đơn trở thành nhiều message, cần xem lại ý nghĩa “đã xong”. Một dòng hàng hoàn thành chưa có nghĩa cả đơn hoàn thành.

Nếu loại một message con trước bước tổng hợp nhưng điều kiện tổng hợp vẫn chờ đủ mọi thành phần ban đầu, nhóm có thể không đạt điều kiện hoàn tất. Đây là lý do phải xem cả số lượng message, quan hệ tương quan và chính sách timeout khi mở rộng pipeline.

Các cấu hình chi tiết của router, splitter và aggregator thuộc các bài chuyên sâu tương ứng; ở đây, chúng cho thấy cách nền tảng Pipes and Filters tiếp tục được dùng trong luồng phức tạp hơn.

## 12. Đệm dữ liệu và tính toán năng lực xử lý

Queue tạo chỗ chờ tạm thời. Nó chỉ giải quyết được một đợt tăng tải khi hệ thống còn khả năng xử lý lượng tồn sau đó.

Giả sử ba bước lần lượt mất 2 ms, 3 ms và 20 ms cho một message, bỏ qua mọi chi phí khác:

- Trên một thread gọi tuần tự qua cả ba bước, một lượt mất khoảng 25 ms, tương đương khoảng 40 message/giây.
- Nếu tách thành các stage có worker riêng và mỗi stage có một worker, stage 20 ms chỉ xử lý khoảng 50 message/giây. Đây là giới hạn lý tưởng của pipeline đó.
- Nếu đầu vào liên tục là 100 message/giây trong cấu hình thứ hai, lượng tồn tăng khoảng 50 message/giây.
- Một vùng đệm 500 message ban đầu rỗng có thể đầy sau khoảng 10 giây trong giả định trên.

Các con số này là phép tính minh họa từ giả định thời gian xử lý, không phải benchmark của Spring Integration.

Khi quyết định thêm vùng đệm, cần trả lời:

- Hệ thống chấp nhận giữ tối đa bao nhiêu message và bao nhiêu dữ liệu trong bộ nhớ?
- Bên gửi phải làm gì khi vùng đệm đầy?
- Message được giữ bao lâu trước khi kết quả trở nên vô ích?
- Có cần xử lý nhiều message cùng lúc, và thứ tự hoàn tất có quan trọng không?

Timeout của một thao tác gửi thường liên quan đến việc chuyển giao vào channel, không phải hạn chót bao trùm mọi công việc downstream. Đặc biệt, truyền `1_000` vào `send()` của ví dụ không cắt ngang một handler đồng bộ đang chạy quá một giây.

`send()` trả về `true` cũng phải được hiểu theo cấu hình: với queue giữa luồng, nó có thể chỉ chứng minh rằng message đã được nhận vào vùng đệm; với nhánh bị loại, nó không chứng minh đơn hàng đã được chấp nhận.

## 13. Quan sát và kiểm thử theo hợp đồng luồng

Khi đưa ví dụ vào bộ kiểm thử, cần quan sát cả đầu ra mong đợi lẫn những đầu ra không được xuất hiện.

| Đầu vào hoặc tình huống | Điều cần xác nhận |
| --- | --- |
| ` ord-101 | 125000 | vnd ` | Một `OrderReceipt` ở `acceptedOrders`, đồng tiền là `VND`, giữ `traceId` |
| `ord-102|-500|VND` | Một `OrderCommand` ở `rejectedOrders`, không có receipt thành công |
| `ord-103|100|USD` | Bị từ chối theo chính sách đồng tiền |
| `ord-104|abc|VND` | Có lỗi phân tích; không đi qua filter hoặc handler |
| `ord-105|100` | Có lỗi cấu trúc thiếu trường |
| `|100|VND` | Có lỗi mã đơn rỗng |
| `ord-106|100|` | Bị từ chối do đồng tiền rỗng theo hợp đồng ví dụ |

Với ví dụ đồng bộ, sau khi `send()` trở về có thể đọc `acceptedOrders.receive(0)` và `rejectedOrders.receive(0)` để kiểm tra tức thời. Nên dùng context mới hoặc làm sạch dữ liệu giữa các kịch bản để không đọc nhầm message của lần chạy trước.

Với biến thể có poller, việc quan sát kết quả cần có thời gian chờ hữu hạn. Tránh suy luận “không có message” chỉ từ một lần đọc ngay sau `send()`, vì công việc có thể chưa được poll.

Để chẩn đoán một lần xử lý, ưu tiên ghi nhận:

- Tên bước và `traceId` hoặc khóa nghiệp vụ.
- Kiểu payload tại các ranh giới quan trọng.
- Số message thành công, bị loại và lỗi.
- Độ trễ xử lý và lượng tồn nếu có queue.

Những thông tin đó giúp trả lời “message dừng ở đâu” mà không phụ thuộc vào việc đọc toàn bộ payload trong mọi log.

## 14. Những lỗi thiết kế thường gặp

| Biểu hiện | Nguyên nhân có thể gặp | Hướng xử lý |
| --- | --- | --- |
| Không thấy kết quả ở handler cuối | Filter đã loại message hoặc một bước trước đó đã lỗi | Quan sát nhánh discard và nhánh lỗi |
| Thêm queue rồi luồng không chạy tiếp | Chưa có consumer hoặc poller phù hợp | Cấu hình endpoint đọc queue |
| Tưởng mỗi dòng DSL chạy trên một thread riêng | Nhầm cấu trúc logic với cơ chế thực thi | Xem loại channel và executor |
| Gateway chờ mãi đến timeout | Một nhánh không tạo reply hoặc kết quả đi vào output channel khác | Hoàn thiện hợp đồng phản hồi |
| Một subscriber nhận message nhưng subscriber khác không nhận | Dùng channel point-to-point cho nhu cầu phát tới nhiều bên | Chọn cấu trúc publish–subscribe phù hợp |
| Retry dẫn đến thao tác kinh doanh lặp lại | Phạm vi retry chứa tác dụng phụ chưa có chống trùng | Xác định idempotency và phạm vi chạy lại |
| Kết quả lẫn dữ liệu giữa các đơn | Endpoint giữ trạng thái từng message trong field dùng chung | Dùng biến cục bộ và hợp đồng dữ liệu rõ |
| Tăng dung lượng queue nhưng tồn đọng vẫn tăng | Tốc độ xử lý dài hạn thấp hơn tốc độ nhận | Đo điểm nghẽn và điều chỉnh năng lực tiếp nhận/xử lý |

## 15. Thực hành mở rộng

1. Thêm một bước chuẩn hóa mã đơn về chữ hoa. Giữ `parseOrder()` chỉ tập trung vào cấu trúc dữ liệu, rồi xác định vị trí đặt bước mới sao cho filter và receipt cùng thấy mã đã chuẩn hóa.
2. Bổ sung một nhánh tiếp nhận đơn ngoại tệ để đối soát riêng. Quyết định khi nào cần router thay cho điều kiện chấp nhận/loại của filter hiện tại.
3. Áp dụng biến thể `validatedOrders` và poller, sau đó tạo một lỗi trong handler để quan sát sự khác nhau giữa lỗi trước và sau queue.
4. Thay bước tạo receipt bằng một service có thao tác lưu trữ. Xác định khóa chống trùng và hành vi khi bên gửi gửi lại cùng một đơn.

Trong mỗi thay đổi, ghi lại hợp đồng payload, đường đi thành công, đường bị từ chối và cách quan sát lỗi trước khi sửa Java DSL.
