# Publish-subscribe semantics

## 1. Một sự kiện, nhiều bên quan tâm

Trong chương **Kiểu channel** của module **SPRING_INTEGRATION_CORE**, publish-subscribe mô tả cách một thông điệp được phát tới nhiều subscriber. Spring Integration cung cấp `PublishSubscribeChannel` để thể hiện cách phân phối này trong một luồng tích hợp.

Giả sử hệ thống vừa ghi nhận sự kiện `OrderPlaced`. Bộ phận kiểm toán cần lưu dấu vết, dịch vụ thông báo cần quyết định có gửi thông báo hay không, còn bộ phận phân tích cần ghi nhận doanh thu. Producer chỉ phát sự kiện; từng subscriber chịu trách nhiệm xử lý phần việc của mình.

~~~mermaid
flowchart LR
    P["Producer: OrderPlaced"] --> C["PublishSubscribeChannel"]
    C --> A["Nhánh kiểm toán"]
    C --> N["Nhánh thông báo"]
    C --> R["Nhánh phân tích"]
~~~

`PublishSubscribeChannel` triển khai `SubscribableChannel`: consumer đăng ký `MessageHandler` và được gọi khi có thông điệp gửi vào channel. Channel không triển khai `PollableChannel` và không có `receive()` để consumer lấy thông điệp bằng polling. Đây là cơ chế broadcast, khác với việc phân chia mỗi thông điệp cho một consumer. [Spring Integration: Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html)

Sau bài học, người học cần phân biệt được:

- **Phân phối:** một thông điệp đi tới một hay nhiều subscriber.
- **Thực thi:** handler chạy trên thread gửi hay qua executor.
- **Hoàn tất:** channel nhận gửi, handler trả về và nghiệp vụ hoàn tất là các mốc khác nhau.
- **Độ tin cậy:** lưu bền, retry, khử trùng lặp và khôi phục là các quyết định thiết kế bổ sung.

Các ví dụ dùng Java 17 và API Spring Integration 6.5. Ví dụ cấu hình cần `spring-integration-core` cùng Spring Context; ví dụ kiểm thử cần JUnit Jupiter. Các lớp cấu hình minh họa độc lập được đặt trong ứng dụng đã có các thư viện này; bài không yêu cầu thay cấu hình build.

## 2. Hợp đồng phân phối: broadcast khác competing consumers

Hai handler cùng subscribe vào một `DirectChannel` không tạo thành hai nhánh đều nhận sự kiện. Channel đó có ngữ nghĩa point-to-point: mỗi lần dispatch hướng tới một handler, với chính sách cân bằng tải/failover tương ứng. `ExecutorChannel` cũng là point-to-point dù có sử dụng executor. [Spring Integration: DirectChannel và ExecutorChannel](https://docs.spring.io/spring-integration/reference/channel/implementations.html)

| Kiểu channel | Cách phân phối | Cách nhận | Trường hợp điển hình |
| --- | --- | --- | --- |
| `DirectChannel` | Một handler cho một lần dispatch thành công | Subscribe; xử lý trực tiếp | Một bước xử lý nghiệp vụ |
| `ExecutorChannel` | Một handler cho một lần dispatch thành công | Subscribe; dispatch qua executor | Một bước cần tách thread |
| `QueueChannel` | Các consumer cạnh tranh lấy thông điệp khỏi queue | Polling | Đệm công việc cho nhóm worker |
| `PublishSubscribeChannel` | Phát tới các handler đang subscribe | Subscribe | Một sự kiện cho nhiều nhánh |

Hãy viết yêu cầu nghiệp vụ trước khi chọn channel:

- “Mỗi hóa đơn chỉ có một worker xử lý” phù hợp mô hình cạnh tranh công việc.
- “Mỗi sự kiện thanh toán cần được kiểm toán và thống kê” phù hợp broadcast.
- “Đơn hàng chỉ đi tới nhóm xử lý theo vùng” phù hợp router.
- “Cần hỏi nhiều dịch vụ rồi trả một kết quả chung” cần thêm cơ chế tập hợp kết quả sau khi fan-out.

Trong ví dụ đơn hàng, tên “subscriber kiểm toán” chỉ một vai trò nghiệp vụ. Một subscriber như vậy có thể là một endpoint đầu vào của cả `IntegrationFlow` gồm transformer, filter và service activator. Số endpoint nằm sâu trong nhánh không phải số subscriber trực tiếp của channel.

## 3. Phạm vi của subscriber và thời điểm đăng ký

`PublishSubscribeChannel` thông thường là channel trong bộ nhớ của ứng dụng. Nó không tự trở thành một topic phân tán chỉ vì có từ “publish-subscribe” trong tên. Nếu chạy ba instance ứng dụng, ba bean channel trong các instance là ba đối tượng riêng.

Điều này dẫn tới các quyết định kiến trúc:

1. Producer và subscriber trong cùng application context có thể trao đổi trực tiếp qua channel.
2. Subscriber khởi động sau khi sự kiện đã được phát không có lịch sử để đọc lại từ channel này.
3. Việc process dừng không có cơ chế khôi phục thông điệp từ chính `PublishSubscribeChannel`.
4. Nếu cần truyền qua nhiều process, phải bổ sung adapter hoặc channel dựa trên hạ tầng messaging phù hợp.

Không nên suy diễn những cam kết của một broker cụ thể, chẳng hạn durable subscription, replay hay acknowledgment, sang channel cục bộ. Với yêu cầu “không được mất sự kiện đơn hàng sau khi commit”, cần thiết kế đường lưu bền và khôi phục, ví dụ transactional outbox kết hợp một hệ thống messaging phù hợp; fan-out trong bộ nhớ chỉ là một đoạn của kiến trúc đó.

Khi quản lý endpoint bằng Spring, lifecycle của endpoint quyết định lúc nó đăng ký và hủy đăng ký handler. Vì vậy, một ứng dụng có đủ bean định nghĩa chưa chắc đã có đủ subscriber đang hoạt động tại mọi thời điểm. Với luồng bắt buộc phải có consumer, cần coi khởi động, dừng endpoint và triển khai lại là các tình huống thiết kế thực tế.

## 4. Ví dụ trực tiếp: quan sát hai subscriber nhận một message

Đoạn mã dưới đây tập trung vào hợp đồng channel, chưa dùng Java DSL:

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class PublishSubscribeDemo {

    public record OrderPlaced(
            String eventId,
            String orderId,
            BigDecimal amount) {
    }

    public static void main(String[] args) {
        var channel = new PublishSubscribeChannel(true);

        List<String> audit = new ArrayList<>();
        List<String> notifications = new ArrayList<>();

        channel.subscribe(message -> {
            OrderPlaced order = (OrderPlaced) message.getPayload();
            audit.add("AUDIT:" + order.orderId());
        });

        channel.subscribe(message -> {
            OrderPlaced order = (OrderPlaced) message.getPayload();
            notifications.add("NOTIFY:" + order.orderId());
        });

        Message<OrderPlaced> message = MessageBuilder
                .withPayload(new OrderPlaced(
                        "evt-42",
                        "O-42",
                        new BigDecimal("1500000")))
                .setHeader("source", "checkout")
                .build();

        boolean sent = channel.send(message);

        System.out.println(sent);
        System.out.println(audit);
        System.out.println(notifications);
    }
}
~~~

Kết quả mong đợi:

~~~text
true
[AUDIT:O-42]
[NOTIFY:O-42]
~~~

Ví dụ chọn `new PublishSubscribeChannel(true)` để yêu cầu có subscriber. Constructor không có executor gọi handler trên thread của bên gửi. Constructor mặc định `new PublishSubscribeChannel()` cũng dùng thread gửi nhưng không yêu cầu phải có subscriber. [PublishSubscribeChannel API](https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/PublishSubscribeChannel.html)

Hai danh sách trong ví dụ chỉ được ghi trên cùng thread, nên đủ cho mục đích quan sát đồng bộ. Khi đổi sang thực thi trên nhiều thread, cần chọn cấu trúc dữ liệu và cách đồng bộ thích hợp thay vì giữ nguyên giả định này.

## 5. Broadcast không đồng nghĩa với chạy song song

### 5.1. Không có executor: các lần gọi nối tiếp trên thread gửi

Với channel không được cung cấp executor, có thể hình dung một lần gửi như sau, giả sử thứ tự dispatch là A, B, C:

~~~text
thread gửi:
  send(message)
    -> handler A
    -> handler B
    -> handler C
  send() trả về
~~~

Nếu A mất 20 ms, B mất 300 ms và C mất 10 ms, riêng thời gian các lời gọi handler đã khoảng 330 ms. Một nhánh chậm làm tăng thời gian gửi của cả luồng.

Trong trường hợp mọi handler xử lý công việc ngay trong lời gọi và đều trả về bình thường, khi `send()` trả về thì các lời gọi đó đã kết thúc. Nếu handler chỉ nộp việc sang hệ thống khác, gửi vào một queue hoặc khởi tạo tác vụ nền, thời điểm đó chưa chứng minh công việc phía sau đã hoàn tất.

Có thể cấu hình thứ tự endpoint trong trường hợp cần kiểm soát thứ tự gọi. Tuy nhiên, nếu B chỉ được phép chạy sau khi A tạo ra kết quả nghiệp vụ, cách diễn đạt rõ hơn là nối A rồi B trong cùng một nhánh xử lý.

### 5.2. Có executor: thêm ranh giới thực thi

Cung cấp executor cho phép channel giao các lần gọi handler cho executor. Mức độ song song phụ thuộc executor; executor chỉ có một worker vẫn thực thi tuần tự các tác vụ. Ngoài ra, một số executor có thể chạy công việc ngay trên thread gọi, nên không thể suy ra “có executor là luôn đổi thread”.

Với thread pool nhiều worker, mô hình thường là:

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant C as PublishSubscribeChannel
    participant E as Executor
    participant A as Handler A
    participant B as Handler B
    P->>C: send(message)
    C->>E: Nộp tác vụ A
    C->>E: Nộp tác vụ B
    C-->>P: Trả kết quả gửi
    E->>A: Thực thi
    E->>B: Thực thi
    Note over A,B: Thời điểm hoàn tất có thể khác nhau
~~~

Đây là sơ đồ minh họa một khả năng lập lịch, không phải bảo đảm rằng worker chỉ bắt đầu sau khi `send()` trả về.

Executor cần được quản lý bởi container để có lifecycle rõ ràng. Ví dụ bean có giới hạn queue:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Bean
public ThreadPoolTaskExecutor orderEventExecutor() {
    var executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(200);
    executor.setThreadNamePrefix("order-event-");
    executor.setWaitForTasksToCompleteOnShutdown(true);
    executor.setAwaitTerminationSeconds(15);
    return executor;
}
~~~

Đây là một phương thức đặt trong lớp `@Configuration`. Các con số minh họa cần được điều chỉnh theo tải thực tế. Với ba subscriber, một sự kiện có thể tạo ba tác vụ dispatch; năng lực pool cần tính theo tổng tải các nhánh.

Khi executor từ chối tác vụ vì quá tải hoặc đang dừng, lần gửi có thể phát sinh lỗi ngay ở bước nộp việc. Một vài nhánh có thể đã được nộp trước đó. Vì vậy, lỗi gửi không chứng minh rằng chưa nhánh nào nhận sự kiện.

## 6. Giá trị trả về, subscriber tối thiểu và nguy cơ mất thông điệp âm thầm

Ba khái niệm cần tách riêng:

| Cấu hình/tình huống | Ý nghĩa cần quan sát |
| --- | --- |
| `requireSubscribers=false`, `minSubscribers=0` | Không có subscriber vẫn có thể trả về `true` |
| `requireSubscribers=true` và không có subscriber | Dispatch bị từ chối bằng exception |
| `minSubscribers=n` | Đặt ngưỡng số lần dispatch được tính là thành công |
| Có executor | Kết quả dispatch không xác nhận handler đã hoàn tất nghiệp vụ |
| `send()` trả về `false` | Không được suy ra rằng các nhánh chưa chạy |

Ví dụ chỉ thay đổi cách xác định kết quả gửi:

~~~java
PublishSubscribeChannel channel = new PublishSubscribeChannel();
channel.setMinSubscribers(2);

channel.subscribe(message -> System.out.println("Một subscriber nhận"));
boolean sent = channel.send(
        MessageBuilder.withPayload("event").build());

System.out.println(sent);
~~~

Với cấu hình này, handler duy nhất vẫn được gọi, nhưng `sent` là `false`. Ngưỡng hai subscriber không phải một bước kiểm tra trước có tác dụng ngăn toàn bộ việc gửi. Mã nguồn dispatcher thực hiện các lần dispatch rồi so sánh số lần được tính với `minSubscribers`. [BroadcastingDispatcher, Spring Integration 6.5.0](https://raw.githubusercontent.com/spring-projects/spring-integration/v6.5.0/spring-integration-core/src/main/java/org/springframework/integration/dispatcher/BroadcastingDispatcher.java)

Hệ quả cho ví dụ đơn hàng: nếu producer thấy `false` rồi phát lại toàn bộ sự kiện, nhánh kiểm toán có thể nhận lần thứ hai. Cần quyết định rõ chính sách retry và dùng khóa nghiệp vụ, chẳng hạn `eventId` kết hợp tên subscriber, để chống thực hiện trùng tác dụng phụ.

`requireSubscribers=true` giúp phát hiện trường hợp hoàn toàn không có subscriber. Nó không xác nhận ba subscriber hiện diện đúng là “kiểm toán”, “thông báo” và “phân tích”; số lượng không thay thế kiểm tra cấu hình và kiểm thử hành vi.

## 7. Java DSL: ba nhánh với transformer và filter

Ví dụ sau cung cấp cấu hình hoàn chỉnh để quan sát fan-out qua các queue kết quả. Ba nhánh có mục đích khác nhau:

- Kiểm toán luôn tạo bản ghi dạng chuỗi.
- Thông báo chỉ nhận đơn từ 1.000.000 trở lên.
- Phân tích lấy giá trị tiền của đơn.

Queue kết quả chỉ dùng để quan sát và kiểm thử, không đại diện cho cơ chế lưu bền.

~~~java
import java.math.BigDecimal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
public class OrderFanOutConfig {

    public record OrderPlaced(
            String eventId,
            String orderId,
            BigDecimal amount) {
    }

    @Bean
    public DirectChannel orderEventsInput() {
        return new DirectChannel();
    }

    @Bean
    public QueueChannel auditResults() {
        return new QueueChannel(20);
    }

    @Bean
    public QueueChannel notificationResults() {
        return new QueueChannel(20);
    }

    @Bean
    public QueueChannel analyticsResults() {
        return new QueueChannel(20);
    }

    @Bean
    public IntegrationFlow orderFanOutFlow() {
        return IntegrationFlow.from(orderEventsInput())
                .publishSubscribeChannel(subscribers -> subscribers
                        .subscribe(flow -> flow
                                .<OrderPlaced, String>transform(
                                        order -> "AUDIT:" + order.orderId())
                                .channel(auditResults()))
                        .subscribe(flow -> flow
                                .<OrderPlaced>filter(order ->
                                        order.amount().compareTo(
                                                new BigDecimal("1000000")) >= 0)
                                .<OrderPlaced, String>transform(
                                        order -> "NOTIFY:" + order.orderId())
                                .channel(notificationResults()))
                        .subscribe(flow -> flow
                                .<OrderPlaced, BigDecimal>transform(
                                        OrderPlaced::amount)
                                .channel(analyticsResults())))
                .get();
    }
}
~~~

`orderEventsInput` là cửa vào của flow. Thành phần `publishSubscribeChannel` phía sau mới là điểm broadcast. Mỗi `subscribe(...)` khai báo một subflow nhận thông điệp từ điểm đó. DSL hỗ trợ cả cấu hình subflow tại chỗ và tách các subscriber thành các `IntegrationFlow` riêng. [Spring Integration: Sub-flows support](https://docs.spring.io/spring-integration/reference/dsl/java-subflows.html)

Bảng hành vi mong đợi:

| Thông điệp | `auditResults` | `notificationResults` | `analyticsResults` |
| --- | --- | --- | --- |
| `O-42`, 1.500.000 | `AUDIT:O-42` | `NOTIFY:O-42` | `1500000` |
| `O-43`, 200.000 | `AUDIT:O-43` | Không có message | `200000` |

Filter chỉ loại thông điệp khỏi nhánh thông báo. Nó không hủy việc xử lý của hai nhánh còn lại. Nếu quy tắc yêu cầu “đơn không hợp lệ không được tới bất kỳ nhánh nào”, cần đặt bước kiểm tra chung trước điểm fan-out.

Transformer trong nhánh tạo đầu ra riêng cho nhánh đó. Kết quả `AUDIT:O-42` không trở thành payload đầu vào của nhánh phân tích.

Để chuyển ví dụ sang executor đã khai báo ở mục trước, thêm bean executor vào cùng lớp cấu hình và đổi lời mở đầu của điểm fan-out sang overload `publishSubscribeChannel(orderEventExecutor(), subscribers -> ...)`, giữ nguyên ba khối `subscribe`. Không đồng thời giữ hai flow đồng bộ và bất đồng bộ cùng subscribe vào `orderEventsInput` để “so sánh”, vì đầu vào `DirectChannel` sẽ có các consumer cạnh tranh.

Một bước nối tiếp ngay sau `publishSubscribeChannel(...)` có thể trở thành một subscriber bổ sung của điểm broadcast. Không dùng vị trí viết tiếp trong DSL để suy ra đó là bước chờ mọi nhánh hoàn tất; cần thiết kế phép join rõ ràng.

Các queue trong ví dụ có capacity 20. Nếu chạy liên tục mà không lấy kết quả ra, queue có thể đầy và làm bước gửi vào queue chờ. Dùng capacity hữu hạn không đồng nghĩa với tự có chính sách timeout hoặc loại bỏ thông điệp.

## 8. Message bất biến không có nghĩa payload được sao chép sâu

`Message` giữ payload và headers. Cấu trúc map headers không cho phép sửa trực tiếp, nhưng payload hoặc giá trị đối tượng nằm trong headers vẫn có thể là mutable. [Spring Integration: Message](https://docs.spring.io/spring-integration/reference/message.html)

Vì vậy, đây là thiết kế nguy hiểm:

~~~java
// Một nhánh sửa đối tượng dùng chung:
MutableOrder order = (MutableOrder) message.getPayload();
order.setStatus("NOTIFIED");
~~~

Nếu nhánh khác đọc `status`, kết quả có thể phụ thuộc thứ tự gọi. Khi có executor, vấn đề còn có thể thành data race.

Quy tắc áp dụng cho bài toán đơn hàng:

1. Phát một snapshot chứa các dữ kiện đã xảy ra, ví dụ `OrderPlaced`.
2. Dùng dữ liệu bất biến như `String`, `BigDecimal` và các giá trị thời gian phù hợp.
3. Nếu record chứa collection, tạo bản sao collection và bảo đảm phần tử cũng đáp ứng yêu cầu bất biến.
4. Nhánh muốn thay đổi trạng thái nghiệp vụ nên thực hiện qua dịch vụ của mình hoặc tạo kết quả mới.
5. Không dùng đối tượng mutable trong headers để truyền kết quả ngầm giữa các subscriber.

`record` chỉ bảo vệ các tham chiếu trường khỏi bị gán lại; một `List` bên trong record vẫn có thể chứa dữ liệu mutable. Trong `OrderPlaced` của ví dụ, các thành phần `String` và `BigDecimal` giúp tránh vấn đề này.

Việc tạo message mới cho từng nhánh cũng không tự tạo bản sao sâu của payload. Chỉ nên dựa vào sự độc lập dữ liệu khi chính mô hình dữ liệu và phép sao chép đã bảo đảm điều đó.

## 9. Xử lý lỗi: từng nhánh có thể có kết quả khác nhau

### 9.1. Luồng đồng bộ với mặc định không bỏ qua lỗi

Giả sử thứ tự dispatch là kiểm toán, thông báo, phân tích:

~~~text
Kiểm toán thành công
Thông báo ném exception
Phân tích chưa được gọi trong lần dispatch này
Producer nhận exception từ send()
~~~

Đó là một lần xử lý một phần. Nếu kiểm toán đã ghi ra một dịch vụ bên ngoài, việc exception quay về producer không tự xóa tác dụng phụ đó.

Có thể cấu hình `setIgnoreFailures(true)` để dispatcher tiếp tục cố gắng gọi các handler khác khi một handler lỗi. Đây là quyết định chấp nhận best-effort; nó không tạo retry hay biến kết quả thành tất cả cùng thành công. Với executor, bỏ qua lỗi còn có thể làm mất đường phát error message cho exception đã bị giữ lại. [BroadcastingDispatcher: ignoreFailures](https://raw.githubusercontent.com/spring-projects/spring-integration/v6.5.0/spring-integration-core/src/main/java/org/springframework/integration/dispatcher/BroadcastingDispatcher.java)

Không nên bật tùy chọn này chỉ để “luồng không bị đỏ”. Với nhánh có tác dụng phụ quan trọng, cần quy định rõ cách ghi nhận thất bại, ai retry và khi nào đưa ra xử lý thủ công.

### 9.2. Luồng qua executor

Trong channel do Spring quản lý, nếu có executor và không cấu hình `ErrorHandler` riêng, chiến lược mặc định phát lỗi tới channel trong header `errorChannel` của message, hoặc tới bean `errorChannel` mặc định. Nếu không có executor, `ErrorHandler` của channel không được dùng để bắt thay cho đường exception trực tiếp về thread gửi. [PublishSubscribeChannel: khởi tạo và error handler](https://raw.githubusercontent.com/spring-projects/spring-integration/v6.5.0/spring-integration-core/src/main/java/org/springframework/integration/channel/PublishSubscribeChannel.java)

Ví dụ tạo message chỉ định nơi nhận lỗi của tác vụ bất đồng bộ:

~~~java
import org.springframework.messaging.MessageHeaders;

Message<OrderFanOutConfig.OrderPlaced> message = MessageBuilder
        .withPayload(new OrderFanOutConfig.OrderPlaced(
                "evt-42",
                "O-42",
                new BigDecimal("1500000")))
        .setHeader(MessageHeaders.ERROR_CHANNEL, orderErrors)
        .build();
~~~

Ở đây `orderErrors` là một `MessageChannel` đã được khai báo trong ứng dụng và có đường tiêu thụ lỗi; nếu dùng `QueueChannel` để quan sát thì phải có bên đọc queue. Header đó không phải một chỉ thị tự động đổi mọi exception đồng bộ thành thông điệp lỗi.

Cần phân biệt hai đường thất bại:

| Thời điểm lỗi | Điều producer có thể quan sát |
| --- | --- |
| Không có subscriber khi yêu cầu phải có | Exception trong lần gửi |
| Executor không nhận tác vụ | Lỗi nộp việc có thể xuất hiện trong lần gửi |
| Handler ném exception trên worker | Đi theo error handler của tác vụ; producer có thể đã nhận kết quả gửi |
| Hệ thống bên ngoài lỗi sau khi handler đã bàn giao việc | Cần cơ chế phản hồi/giám sát ở hệ thống đó |

Các nhánh đã nộp việc vào executor có thể tiếp tục chạy dù một nhánh khác thất bại. Muốn hủy công việc đã chạy cần một giao thức khác; broadcast không cung cấp cơ chế hủy đồng loạt.

Để quan sát và retry chính xác, nên mang theo `eventId`, `orderId` và thông tin nhận diện nhánh ở nơi ghi lỗi. Mỗi subscriber cần chiến lược chống trùng phù hợp với tác dụng phụ của chính nó.

## 10. Transaction và thứ tự: cần ranh giới rõ ràng

Khi các handler được gọi đồng bộ trên cùng thread, chúng có thể tham gia transaction đang hoạt động nếu transaction manager và tài nguyên được cấu hình tương thích. Điều này không làm mọi thao tác trong các nhánh trở thành một giao dịch nguyên tử: lời gọi HTTP hoặc email đã gửi không tự rollback cùng database.

Khi dispatch sang worker của thread pool, không nên giả định transaction gắn với thread gửi được truyền sang worker. Nếu worker cần transaction database, cần cấu hình transaction cho phần xử lý trên worker.

Ví dụ yêu cầu:

> Chỉ gửi thông báo cho đơn hàng đã được commit, và phải có thể gửi lại khi dịch vụ thông báo tạm ngừng.

Một thiết kế có thể xem xét là ghi đơn hàng và bản ghi outbox trong transaction database, sau đó một luồng riêng đọc outbox để phát sự kiện. Khi đó, cần giải thích rõ cơ chế đánh dấu đã phát và chống trùng ở consumer. Chỉ thêm executor vào fan-out không giải quyết yêu cầu này.

Tương tự, nếu sự kiện `OrderCancelled` được gửi sau `OrderPlaced`, một pool nhiều worker có thể hoàn tất việc xử lý hai sự kiện theo thứ tự khác nhau. Đối với dữ liệu cần thứ tự theo `orderId`, hãy thiết kế cách tuần tự hóa theo khóa hoặc xử lý phiên bản sự kiện tại subscriber.

## 11. Khi cần gom kết quả: applySequence và aggregator

Một broadcast dùng cho thông báo không nhất thiết cần phản hồi. Nếu yêu cầu là “gọi ba phép tính và lấy một kết quả tổng hợp”, cần thêm thiết kế fan-out/fan-in:

~~~mermaid
flowchart LR
    I["Yêu cầu"] --> P["PublishSubscribeChannel: applySequence=true"]
    P --> A["Tính giá"]
    P --> B["Tính phí giao hàng"]
    P --> C["Tính thuế"]
    A --> R["Channel kết quả chung"]
    B --> R
    C --> R
    R --> G["Aggregator"]
    G --> O["Một kết quả tổng hợp"]
~~~

Cấu hình channel:

~~~java
@Bean
public PublishSubscribeChannel quoteRequests() {
    var channel = new PublishSubscribeChannel(true);
    channel.setApplySequence(true);
    return channel;
}
~~~

`applySequence` mặc định là `false`. Khi bật, channel bổ sung correlation và sequence headers cho các message gửi tới subscriber. Với ba subscriber trực tiếp, các nhánh có sequence number tương ứng và sequence size bằng ba. Message có headers riêng vẫn dùng chung tham chiếu payload. [Spring Integration: cấu hình PublishSubscribeChannel](https://docs.spring.io/spring-integration/reference/channel/configuration.html)

Aggregator mặc định nhóm theo `correlationId` và xét hoàn tất theo kích thước sequence. Các nhánh cần gửi kết quả về đúng nơi tập hợp và bảo toàn các headers cần thiết. [Spring Integration: Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html)

`applySequence=true` không tự sinh aggregator và không tự chờ:

- Nếu một nhánh kết thúc bằng handler không có reply, sẽ thiếu kết quả.
- Nếu một filter loại message, aggregator không tự biết nhánh đó đã “xong nhưng không có kết quả”.
- Nếu một nhánh phát nhiều kết quả, quy ước một kết quả cho một sequence position có thể không còn phù hợp.
- Nếu một nhánh chậm hoặc lỗi, cần quy định timeout và xử lý nhóm chưa đầy đủ.

Áp dụng vào ví dụ đơn hàng: không thể bật `applySequence` rồi gom kết quả của cả ba nhánh một cách máy móc, vì filter thông báo có thể loại message. Một lựa chọn là để nhánh thông báo trả một kết quả rõ ràng như `SKIPPED` khi không cần thông báo. Lựa chọn khác là thiết kế correlation/release strategy theo hợp đồng nghiệp vụ khác.

Phản hồi nên chứa tên vai trò, chẳng hạn `PRICE`, `SHIPPING` hoặc `TAX`, thay vì diễn giải vai trò bằng thứ tự phần tử trả về.

## 12. Gateway: một API gọi không tự tổng hợp nhiều reply

Có thể dùng messaging gateway để business code gọi một interface:

~~~java
import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway(defaultRequestChannel = "orderEventsInput")
public interface OrderEventGateway {

    void publish(OrderFanOutConfig.OrderPlaced event);
}
~~~

Gateway cần được đăng ký theo cấu hình ứng dụng, chẳng hạn qua `@IntegrationComponentScan` trong package chứa interface. Mục đích là che API `MessageChannel` khỏi bên gọi; gateway không thay đổi hợp đồng broadcast của luồng phía sau. [Spring Integration: Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html)

Với method `void`, API thể hiện rằng bên gọi không yêu cầu một reply nghiệp vụ. Điều đó không tự làm lời gọi bất đồng bộ: nếu flow phía sau đang xử lý đồng bộ, bên gọi vẫn chịu thời gian xử lý và có thể nhận exception tương ứng.

Nếu API cần trả `QuoteSummary` từ nhiều nhánh, hãy bảo đảm chỉ một kết quả tổng hợp được đưa về gateway sau bước aggregator. Không để ba subscriber trả ba reply cạnh tranh vào đường reply rồi kỳ vọng gateway tự biến chúng thành một danh sách.

Trong bài toán đơn hàng, cũng cần làm rõ tên API “publish” có nghĩa gì: đã tiếp nhận ở channel, đã ghi bền, hay đã hoàn tất các subscriber. Chữ ký method không đủ diễn đạt các bảo đảm đó nếu hợp đồng của ứng dụng không nêu rõ.

## 13. Kiểm thử hành vi fan-out

Đoạn kiểm thử dưới đây đi cùng `OrderFanOutConfig` ở mục 7 và dùng JUnit Jupiter. Nó kiểm tra tác động quan sát được ở ba nhánh thay vì chỉ xác nhận giá trị trả về của `send()`.

~~~java
import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class OrderFanOutTest {

    @Test
    void highValueOrderReachesAllThreeBranches() {
        try (var context = new AnnotationConfigApplicationContext(
                OrderFanOutConfig.class)) {

            MessageChannel input = context.getBean(
                    "orderEventsInput", MessageChannel.class);
            QueueChannel audit = context.getBean(
                    "auditResults", QueueChannel.class);
            QueueChannel notification = context.getBean(
                    "notificationResults", QueueChannel.class);
            QueueChannel analytics = context.getBean(
                    "analyticsResults", QueueChannel.class);

            boolean sent = input.send(MessageBuilder.withPayload(
                    new OrderFanOutConfig.OrderPlaced(
                            "evt-42",
                            "O-42",
                            new BigDecimal("1500000"))).build());

            assertTrue(sent);
            assertPayload("AUDIT:O-42", audit.receive(0));
            assertPayload("NOTIFY:O-42", notification.receive(0));
            assertPayload(new BigDecimal("1500000"), analytics.receive(0));

            assertNull(audit.receive(0));
            assertNull(notification.receive(0));
            assertNull(analytics.receive(0));
        }
    }

    @Test
    void lowValueOrderIsFilteredOnlyInNotificationBranch() {
        try (var context = new AnnotationConfigApplicationContext(
                OrderFanOutConfig.class)) {

            MessageChannel input = context.getBean(
                    "orderEventsInput", MessageChannel.class);
            QueueChannel audit = context.getBean(
                    "auditResults", QueueChannel.class);
            QueueChannel notification = context.getBean(
                    "notificationResults", QueueChannel.class);
            QueueChannel analytics = context.getBean(
                    "analyticsResults", QueueChannel.class);

            assertTrue(input.send(MessageBuilder.withPayload(
                    new OrderFanOutConfig.OrderPlaced(
                            "evt-43",
                            "O-43",
                            new BigDecimal("200000"))).build()));

            assertPayload("AUDIT:O-43", audit.receive(0));
            assertNull(notification.receive(0));
            assertPayload(new BigDecimal("200000"), analytics.receive(0));
        }
    }

    private static void assertPayload(Object expected, Message<?> actual) {
        assertNotNull(actual);
        assertEquals(expected, actual.getPayload());
    }
}
~~~

Trong cấu hình đồng bộ này, khi gửi xong thì các bước đưa kết quả vào queue đã diễn ra, nên `receive(0)` phù hợp. Khi dùng executor, cần chờ kết quả với timeout hữu hạn, chẳng hạn `receive(2000)`, hoặc đồng bộ bằng latch ở điểm hoàn tất cần kiểm tra. Không dùng `Thread.sleep(...)` làm bằng chứng hoàn tất.

Đối với nhánh không được phép sinh output trong kiểm thử bất đồng bộ, việc đọc ngay bằng timeout 0 không chứng minh output sẽ không đến sau đó. Cần chờ tín hiệu hoàn tất của nhánh hoặc quan sát trong một khoảng giới hạn phù hợp với hợp đồng kiểm thử.

Các trường hợp bổ sung nên kiểm tra khi triển khai thật:

| Tình huống | Bằng chứng cần thu được |
| --- | --- |
| Không có subscriber nhưng bắt buộc phải có | Producer nhận lỗi gửi |
| Một handler lỗi đồng bộ | Xác định nhánh đã chạy và nhánh chưa chạy theo thứ tự cấu hình |
| Một handler lỗi trên worker | Thông điệp lỗi đến đúng đường xử lý lỗi |
| Một nhánh rất chậm | Có giới hạn chờ và cơ chế phát hiện |
| Phát lại cùng `eventId` | Tác dụng phụ của subscriber được khử trùng theo yêu cầu |
| Executor quá tải | Quan sát được lỗi nộp việc và trạng thái xử lý một phần |
| Fan-in thiếu một kết quả | Aggregator có đường timeout/nhóm không đầy đủ |

Đây là mã và kịch bản kiểm thử để người học thực hành trong ứng dụng của mình.

## 14. Chọn đúng mô hình cho từng yêu cầu

| Yêu cầu | Hướng thiết kế |
| --- | --- |
| Mỗi sự kiện cần tới kiểm toán, thông báo và phân tích | `PublishSubscribeChannel` cùng các subscriber riêng |
| Chọn một nhánh xử lý theo nội dung | Router |
| Nhiều worker chia nhau xử lý mỗi công việc | Channel có ngữ nghĩa point-to-point |
| Một nhánh cần nhận sự kiện nhưng chỉ xử lý khi hợp lệ | Filter trong nhánh |
| Nhiều phép tính phải trả về một đáp án | Fan-out kết hợp aggregator và hợp đồng phản hồi |
| Các instance ứng dụng đều cần nhận sự kiện | Hạ tầng truyền thông liên process với ngữ nghĩa subscription rõ ràng |
| Sự kiện phải khôi phục sau sự cố | Thiết kế lưu bền, xác nhận, retry và khử trùng |

Một thiết kế tốt cho `OrderPlaced` bắt đầu bằng câu hỏi “ai cần biết sự kiện này và mỗi bên cam kết làm gì”, sau đó mới chọn đồng bộ hay executor, chỗ đặt filter, đường xử lý lỗi và cơ chế kiểm thử.

Điểm cần giữ khi đọc một integration flow là: **publish-subscribe xác định các bên nhận thông điệp; việc các bên chạy trên thread nào, hoàn tất lúc nào và được khôi phục ra sao cần được thiết kế riêng**.

