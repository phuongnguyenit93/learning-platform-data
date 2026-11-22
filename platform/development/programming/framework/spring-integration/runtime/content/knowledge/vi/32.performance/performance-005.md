# Message history, logging và chi phí quan sát

Khi một message đi qua nhiều <code>MessageChannel</code>, consumer endpoint, transformer, router, poller, executor và handler của Spring Integration, lỗi có thể xuất hiện ở rất xa nguồn phát. Người vận hành muốn trả lời: *message đã đi qua đâu, nằm chờ ở đâu, handler nào xử lý chậm, lỗi xảy ra trước hay sau transaction commit?* Những thông tin này cực kỳ hữu ích, nhưng việc ghi lại toàn bộ đường đi hoặc log mỗi message cũng tiêu tốn CPU, heap, I/O và tài nguyên của hệ thống quan sát.

Bài học thuộc chương **Hiệu năng** của module **SPRING_INTEGRATION_RUNTIME**. Trọng tâm là **message history**, **logging** và **chi phí quan sát** trong Spring Integration runtime: cách bật có chọn lọc, đọc đúng dữ liệu, hiểu tác động tới throughput/latency/GC, kiểm tra các ranh giới async/transaction và thiết kế phép đo trước khi quyết định cấu hình production.

> **Nguyên tắc:** Quan sát phải phục vụ một câu hỏi vận hành rõ ràng. Không mặc định bật history cho mọi component, log toàn bộ payload và tạo span tại mọi hop chỉ vì framework hỗ trợ. Một dòng log hoặc một history entry có thể rẻ trong unit test nhưng đắt khi đi qua hàng chục hop ở lưu lượng cao.

## 1. Phân biệt bốn lớp quan sát

| Cơ chế | Dữ liệu cung cấp | Nơi dữ liệu được giữ | Chi phí nổi bật |
|---|---|---|---|
| <code>MessageHistory</code> | Tên, loại component và timestamp của các hop được theo dõi | Trong **header của từng message** | Tăng kích thước message, bộ nhớ, serialization, sao chép qua nhánh |
| Framework debug logging | Sự kiện runtime ở channel/dispatcher/handler | Logging backend, appender, log collector | Kiểm tra log level, format/toString, queue appender, ghi đĩa/mạng |
| <code>LoggingHandler</code>, DSL <code>.log()</code>, <code>WireTap</code> | Nội dung message hoặc phần thông tin được chọn | Dòng log hoặc nhánh phụ riêng | Interceptor, định dạng, đồng bộ/async, payload và dữ liệu nhạy cảm |
| Micrometer metrics / Observation / tracing | Timer, counter, outcome, span, trace context | Meter registry/tracer và hệ thống export | Recording, timer, span creation, context propagation, cardinality, export |

Những cơ chế trên **bổ trợ nhưng không thay thế nhau**:

- **History** trả lời “message đã qua component được track nào?” nhưng không tự chứng minh transaction đã commit.
- **Log** trả lời “ở thời điểm đó component báo điều gì?” nhưng có thể mất/thất thứ tự vì async appender hoặc sampling.
- **Metric** trả lời “tỷ lệ lỗi, p95 latency, throughput và backlog ra sao?” nhưng không cho biết toàn bộ đường đi của một message cụ thể.
- **Trace** nối các khoảng thời gian của nhiều operation và thread/process khi có cấu hình propagation phù hợp; không tự là một audit record bền vững.

~~~mermaid
flowchart LR
    S["Inbound adapter"] --> C["orders.in"]
    C --> V["Validate handler"]
    V --> X["ExecutorChannel"]
    X --> D["JDBC/HTTP handler"]
    D --> O["orders.out"]
    H["MessageHistory header"] -. "hop name/type/time" .-> C
    H -. "hop name/type/time" .-> V
    H -. "hop name/type/time" .-> X
    L["Logs"] -. "event/error" .-> D
    M["Metrics / tracing"] -. "timers/spans" .-> D
~~~

Khi <code>ExecutorChannel</code> chuyển việc sang worker khác, lịch sử message vẫn có thể đi cùng headers, trong khi <code>ThreadLocal</code> như MDC hoặc transaction JDBC ở thread sender **không** tự đi theo.

## 2. Message history lưu những gì?

Spring Integration có mẫu thiết kế **Message History**: framework bổ sung header tên <code>MessageHistory.HEADER_NAME</code> (thường là <code>history</code>) cho những message đi qua component được theo dõi. Mỗi entry thường có:

~~~text
[
  {name=orders.input, type=channel, timestamp=...},
  {name=orders.validate, type=service-activator, timestamp=...},
  {name=orders.output, type=channel, timestamp=...}
]
~~~

Đây là biểu diễn **minh họa**: tên và component type thực tế phụ thuộc DSL, bean ID và loại endpoint. History chỉ ghi component có tên/ID và khớp pattern theo cấu hình; không nhất thiết mọi Java method hoặc mọi hop trong flow đều có entry.

Những thông tin này hữu ích để:

1. Xác định message đến được <code>orders.validate</code> hay đã rẽ sang nhánh router khác.
2. Điều tra message qua <code>DirectChannel</code> rồi <code>ExecutorChannel</code> tại điểm nào.
3. So sánh đường đi của message thành công và message lỗi.
4. Nhận biết một message quay lại cùng component trong vòng lặp/routing.
5. Bổ sung dấu vết trong <code>ErrorMessage</code> khi failed/original message còn đủ header.

**Không suy ra latency tuyệt đối từ hai timestamp history một cách thiếu kiểm chứng.** Timestamp thể hiện thời điểm component được ghi nhận, không nhất thiết là thời điểm handler bắt đầu/kết thúc chính xác, không bao gồm mọi lần chờ queue và chịu ảnh hưởng đồng hồ/độ phân giải. Muốn đo duration đáng tin cậy, dùng timer/observation và metric riêng cho queue lag.

### Đọc MessageHistory từ message

~~~java
import org.springframework.integration.history.MessageHistory;
import org.springframework.messaging.Message;
import java.util.Properties;

public static void showHistory(Message<?> message) {
    MessageHistory history = MessageHistory.read(message);
    if (history == null) {
        System.out.println("History chưa được bật hoặc message chưa qua tracked component");
        return;
    }

    for (Properties hop : history) {
        System.out.printf("component=%s, type=%s, timestamp=%s%n",
            hop.getProperty(MessageHistory.NAME_PROPERTY),
            hop.getProperty(MessageHistory.TYPE_PROPERTY),
            hop.getProperty(MessageHistory.TIMESTAMP_PROPERTY));
    }
}
~~~

<code>MessageHistory.read(message)</code> trả về <code>null</code> nếu header không tồn tại. History là metadata điều tra **đính vào message**, không phải một bảng audit hoặc trace store tập trung. Nếu message bị xóa khỏi queue/store hoặc headers bị header mapper bỏ qua, thông tin history đó cũng có thể biến mất.

## 3. Bật history cho đúng component

Spring Integration hỗ trợ <code>@EnableMessageHistory</code> từ package <code>org.springframework.integration.config</code>. Nếu khai báo không có pattern, cơ chế này theo dõi tất cả **trackable named components**:

~~~java
@Configuration
@EnableIntegration
@EnableMessageHistory
public class FullHistoryForLocalDebug {
}
~~~

Trong production, nên bắt đầu với các channel/handler quan trọng thay vì dùng cấu hình trên. Ví dụ:

~~~java
@Configuration
@EnableIntegration
@EnableMessageHistory({
    "orders.input",
    "orders.validate",
    "orders.payment*",
    "orders.output"
})
public class TargetedHistoryConfig {
}
~~~

Pattern có thể là một tên chính xác hoặc chuỗi có wildcard <code>*</code>. Ở ví dụ trên, các tên phải **khớp tên component thực tế** trong Spring context; không phải tên biến Java. Nếu một endpoint có ID được sinh tự động, nên đặt ID ổn định hoặc kiểm tra metadata runtime trước khi viết pattern.

Một nguồn cấu hình <code>@EnableMessageHistory</code> cho mỗi application context là lựa chọn dễ quản trị; không khai báo nhiều configurer với pattern không nhất quán. <code>MessageHistoryConfigurer</code> được framework đăng ký từ annotation. Không tự tạo một bean configurer generic chỉ để bật nhanh lịch sử.

### Vì sao “bật history nhưng header rỗng”?

| Tình huống | Điều cần kiểm tra |
|---|---|
| Không có <code>history</code> header | Chưa bật history, configurer đã stop, hoặc message chưa đi qua named component phù hợp |
| Pattern <code>orders.*</code> không có entry như mong muốn | Tên bean/managed component do DSL sinh khác tên dự đoán |
| Message mới sau converter không còn history | Header mapper, custom <code>MessageBuilder</code>, transport mapping hoặc code tự tạo message không mang header |
| Bản tin trong nhánh router có lịch sử khác nhánh khác | Mỗi nhánh đi qua các component khác nhau; history phải được tách phù hợp |
| History tăng bất thường | Message đi lặp qua cùng flow, retry/resubscribe hoặc quá nhiều tracked hops |

**Không coi history là cơ chế bảo đảm một message chỉ xử lý một lần.** Một redelivery có thể chứa history trước đó, mất history, hoặc có thêm hop mới tùy transport và cách xây dựng lại message. Idempotency phải dựa trên business event ID cùng kho dữ liệu bền vững tương ứng.

## 4. Ví dụ Java DSL có history, log chọn lọc và output kiểm tra

Ví dụ minh họa dùng Java 17+, Spring Integration 6.x. Flow nhận một đơn hàng, log **chỉ metadata cần thiết**, gọi service rồi đưa reply vào <code>QueueChannel</code> để test có thể đọc.

~~~java
public record OrderCommand(String orderId, int quantity) {}
public record OrderResult(String orderId, String status) {}

public class OrderService {
    public OrderResult process(OrderCommand command) {
        if (command.quantity() <= 0) {
            throw new IllegalArgumentException("quantity phải dương");
        }
        return new OrderResult(command.orderId(), "ACCEPTED");
    }
}
~~~

~~~java
@Configuration
@EnableIntegration
@EnableMessageHistory({"orders.*"})
@EnableIntegrationManagement(defaultLoggingEnabled = "false")
public class OrderHistoryFlowConfig {

    @Bean
    OrderService orderService() {
        return new OrderService();
    }

    @Bean(name = "orders.input")
    DirectChannel ordersInput() {
        return new DirectChannel();
    }

    @Bean(name = "orders.output")
    QueueChannel ordersOutput() {
        return new QueueChannel();
    }

    @Bean
    IntegrationFlow orderFlow(OrderService service) {
        return IntegrationFlow.from("orders.input")
            .log(LoggingHandler.Level.DEBUG, "orders.path", message ->
                "messageId=" + message.getHeaders().getId()
                + ", correlationId=" + message.getHeaders().get("correlationId"))
            .handle(service, "process",
                endpoint -> endpoint.id("orders.process"))
            .channel("orders.output")
            .get();
    }
}
~~~

Các import chính:

~~~java
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.config.EnableMessageHistory;
import org.springframework.integration.config.EnableIntegrationManagement;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.handler.LoggingHandler;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
~~~

**Tại sao cấu hình này đáng học?**

- <code>@EnableMessageHistory({"orders.*"})</code> chỉ định theo dõi các named component thuộc nhánh <code>orders</code> thay vì mọi flow trong ứng dụng.
- <code>.log(...)</code> thêm log tại một **điểm** của flow, dùng logger <code>orders.path</code>; biểu thức không truy cập trực tiếp payload.
- <code>LoggingHandler.Level.DEBUG</code> giúp kiểm soát log bằng log level của backend thay vì luôn ghi ở INFO.
- <code>@EnableIntegrationManagement(defaultLoggingEnabled="false")</code> giảm logging debug thông thường trong **main message flow** do các managed component hỗ trợ; nó không tự tắt <code>.log()</code> được cấu hình rõ, không tắt exception logging và không vô hiệu hóa message history.
- <code>orders.output</code> là <code>QueueChannel</code>; test phải <code>receive(timeout)</code> thay vì chờ subscriber event-driven.

Không tạo thêm endpoint chỉ để nhận cùng <code>orders.input</code> nếu muốn test một luồng duy nhất. Tên <code>orders.process</code> là ID endpoint dùng để quản trị; history entry cụ thể có thể ghi tên component liên quan khác tùy framework.

### Đọc history ở output

~~~java
Message<OrderCommand> request = MessageBuilder
    .withPayload(new OrderCommand("O-42", 2))
    .setHeader("correlationId", "checkout-42")
    .build();

ordersInput.send(request);
Message<?> reply = ordersOutput.receive(5_000);
if (reply == null) {
    throw new IllegalStateException("Không nhận được kết quả");
}

System.out.println(reply.getPayload());
showHistory(reply);
~~~

<code>MessageBuilder</code> thuộc <code>org.springframework.integration.support</code>. Trong ví dụ, <code>ordersInput</code> và <code>ordersOutput</code> là các bean được inject. Việc <code>send()</code> thành công không mặc nhiên chứng minh toàn bộ downstream đã hoàn tất ở các topology khác, đặc biệt khi dùng executor hoặc reactive channel.

## 5. Thay đổi quan trọng ở Spring Integration 6.3: append-only history

Tài liệu Spring Integration mô tả hai cơ chế lưu lịch sử khác nhau theo phiên bản:

| Phiên bản | Cách ghi history | Hệ quả hiệu năng |
|---|---|---|
| Trước 6.3 | Khi thêm track, framework tạo bản <code>MessageHistory</code> mới và tạo lại message để phản ánh header đã cập nhật | Tăng allocation và copy ở flow nhiều hop |
| Từ 6.3 | Lần ghi đầu tạo container; các lần <code>MessageHistory.write()</code> sau có thể **append** entry vào container hiện hữu, không tạo message mới cho mỗi track | Giảm đáng kể việc copy message, nhưng history vẫn tiêu thụ bộ nhớ và serialization |

Thay đổi này **không biến history thành miễn phí**. Mỗi entry cần chứa các metadata và đi theo message, đặc biệt tốn kém nếu message còn tồn tại lâu trong queue/delayer/group store hoặc bị gửi qua broker.

### Fan-out cần tách lịch sử theo nhánh

~~~mermaid
flowchart TD
    M["Message gốc<br/>history: input"] --> R["Router / PublishSubscribeChannel"]
    R --> A["Nhánh A<br/>history: input → A"]
    R --> B["Nhánh B<br/>history: input → B"]
    A --> A1["Audit"]
    B --> B1["Notification"]
~~~

Vì history từ 6.3 có tính append-only trong container, nếu hai nhánh **chung một container mutable** và cùng bổ sung entry, lịch sử có thể trộn đường đi của hai nhánh. Các thành phần fan-out do framework quản lý như <code>PublishSubscribeChannel</code>, router, <code>WireTap</code> và splitter đã xử lý việc **clone history** khi cần.

Nếu tự viết một component phát nhiều message độc lập từ cùng message gốc, cần tuân theo cơ chế clone/copy phù hợp. Spring Integration giới thiệu <code>AbstractIntegrationMessageBuilder.cloneMessageHistoryIfAny()</code> cho các use case tự tạo nhánh. Không sửa <code>MessageHistory</code> trực tiếp bằng code ứng dụng và không giả định cứ copy tham chiếu header sang một message khác là có đường đi độc lập.

**Khi nâng từ 6.2 lên 6.3+:** đo lại allocation/throughput thay vì dùng kết quả cũ; kiểm tra custom splitter/router, serializable headers, handler nào tự viết lại message và cách snapshot history khi audit.

## 6. Logging trong Spring Integration: chi phí khác history

Spring Integration có hai nhóm log:

1. **Framework debug logging** trong channel, dispatcher, handler hoặc endpoint khi log level cho phép.
2. **Logging endpoint/wiretap do flow tự thêm**, ví dụ <code>LoggingHandler</code>, Java DSL <code>.log(...)</code>.

Chúng không phải một cơ chế. Tắt log debug thông thường thông qua <code>@EnableIntegrationManagement(defaultLoggingEnabled="false")</code> không phải là việc tắt toàn bộ các logger, exception, metric hay <code>LoggingHandler</code>.

Một nguyên tắc quan trọng trong môi trường lưu lượng cao: ngay cả thao tác kiểm tra <code>isDebugEnabled()</code> có thể có chi phí tùy logging subsystem. Spring Integration có tùy chọn <code>defaultLoggingEnabled</code> chính để tránh các kiểm tra/logging trong main flow khi cần.

~~~java
@Configuration
@EnableIntegration
@EnableIntegrationManagement(defaultLoggingEnabled = "false")
class QuietManagedComponentsConfig {
}
~~~

Thuộc tính này chỉ áp dụng mặc định cho component **chưa được cấu hình loggingEnabled thủ công**. Một channel gọi <code>setLoggingEnabled(true)</code> có thể giữ giá trị override. Log exception/debug phát ở những đường xử lý lỗi khác vẫn tồn tại theo thiết kế.

### Đừng log full message chỉ để xem một header

~~~java
// Có thể vô tình gọi toString() trên toàn bộ payload và headers:
.log(LoggingHandler.Level.INFO, "orders.flow")

// Tốt hơn: chỉ log metadata cần điều tra.
.log(LoggingHandler.Level.DEBUG, "orders.flow", message ->
    "messageId=" + message.getHeaders().getId()
    + ", correlationId=" + message.getHeaders().get("correlationId"))
~~~

Các đoạn trên là **mảnh Java DSL** minh họa vị trí operator trong flow. Biểu thức log cần tránh:

- <code>payload.toString()</code> nếu payload lớn, có graph object sâu hoặc chứa thông tin nhạy cảm;
- chuyển cả message thành JSON chỉ để lấy ID;
- lặp log ở quá nhiều channel quanh cùng một business step;
- đưa nguyên payload lên log collector không có giới hạn kích thước và retention;
- tạo logger category động cho mỗi tenant/request.

Khi logger đã tắt, backend có thể tránh ghi ra sink, nhưng không nên dựa vào giả định mọi biến thể API đều **không đánh giá** biểu thức log. Nếu biểu thức rất đắt, phải đo thực tế hoặc kiểm soát/giảm sampling ngay trong thiết kế.

## 7. Java DSL .log() và WireTap: “quan sát” vẫn nằm trên đường xử lý

Toán tử <code>.log()</code> của Spring Integration Java DSL được triển khai bằng **<code>WireTap</code> channel interceptor** cùng <code>LoggingHandler</code> nhận message ở nhánh phụ. Nó là một điểm quan sát, không phải handler nghiệp vụ tự động sinh reply.

~~~text
Producer → Channel + WireTap → Business Handler → Output
                 │
                 └→ LoggingHandler → log appender
~~~

Nếu tap được gọi đồng bộ trên thread sender và log backend phải format hoặc ghi dữ liệu chậm, **độ trễ của send** có thể tăng, kể cả business handler không đổi. Nếu tap chuyển sang executor, chi phí có thể rời khỏi critical path một phần, nhưng sẽ xuất hiện queue backlog, memory và chính sách overflow/rejection của logging branch.

**Phân biệt wiretap và durable audit:**

| Thiết kế | Điểm mạnh | Rủi ro |
|---|---|---|
| <code>.log()</code> trực tiếp | Dễ thêm/xóa khi debug; không cần broker | Chi phí ngay trong runtime, log không có delivery guarantee |
| WireTap → channel/handler riêng | Cô lập điểm quan sát, dễ lọc và kiểm tra | Có thể gây thêm subscriber/queue và lỗi trong nhánh tap |
| Async appender | Giảm phần I/O đồng bộ trên thread handler | Buffer đầy có thể block/drop theo chính sách logging |
| Persistent audit/outbox | Có hợp đồng lưu giữ, transaction/replay rõ | Chi phí DB/storage và nghiệp vụ xử lý riêng |

Trong Spring Integration 6.0+, <code>.log()</code> được thiết kế để không đổi kết quả flow khi đặt ở cuối hay giữa; nếu flow là **one-way** và sau logging không còn consumer/reply, nên dùng <code>.nullChannel()</code> hoặc terminal handler đúng nghĩa. Không cố dùng LoggingHandler làm endpoint kinh doanh chỉ để tránh lỗi không có subscriber.

## 8. Tại sao log làm thay đổi thứ tự, thread và thời điểm nhận lỗi?

Một hệ thống có thể có topology:

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant C as DirectChannel + WireTap
    participant L as LoggingHandler / Appender
    participant H as Business Handler
    P->>C: send(M)
    C->>L: log selected fields
    L-->>C: return
    C->>H: handle(M)
    H-->>P: business result
    Note over P,L: Logging đồng bộ có thể làm tăng send latency
~~~

Sơ đồ là **mô hình minh họa chi phí đồng bộ**, không phải lời khẳng định mọi cấu hình wiretap đều gọi log trước handler theo một thứ tự bất biến. Thứ tự interceptor/dispatcher và việc dùng executor cần được xác nhận trong topology thực tế.

Nếu ghi log sang <code>ExecutorChannel</code> hoặc async appender, dòng log có thể xuất hiện **sau** log của handler, dù sự kiện quan sát bắt đầu trước. Vì vậy:

- Không dùng thứ tự dòng log giữa các thread để suy ra quan hệ *happens-before* một cách tuyệt đối.
- Gắn message ID, correlation ID và thời gian đo/trace span đúng boundary.
- Không dùng log “message received” làm bằng chứng đã commit transaction.
- Khi async logging queue đầy, cần hiểu chính sách block/drop; không tự nhận đây là đường audit đáng tin cậy.
- Nếu handler bị retry hoặc broker redeliver, có thể xuất hiện nhiều dòng log cho **cùng business event**, không nhất thiết là lỗi logic log.

## 9. Ước lượng chi phí quan sát trước khi bật toàn hệ thống

Chi phí có nhiều tầng và không thể gói vào một câu “mỗi history entry chỉ có vài byte”.

| Tầng | Nguồn overhead | Dấu hiệu trong production |
|---|---|---|
| CPU | Tạo metadata, timestamp, kiểm tra pattern/log level, format string, serialization | CPU tăng dù business logic và traffic không đổi |
| Heap/GC | Header history tăng theo hop, log event object, async queue, trace/span context | Allocation rate tăng, GC pause/heap usage tăng |
| Latency | Logging đồng bộ, lock appender, exporter hoặc network chậm | p95/p99 end-to-end latency tăng |
| Throughput | Worker bị giữ bởi log I/O hoặc exporter; queue đầy gây backpressure | TPS giảm, poller lag hoặc executor backlog tăng |
| Message size | History và trace headers đi qua broker/DB/Redis | Bản ghi lớn, deserialize chậm, tăng băng thông/storage |
| Telemetry backend | Metric series, trace spans, log ingest và index | Scrape/export queue tăng, chi phí lưu trữ và truy vấn tăng |
| An toàn dữ liệu | Payload/headers chứa PII, token và ID nghiệp vụ | Log collector giữ dữ liệu nhạy cảm quá phạm vi cần thiết |

### Mô hình bộ nhớ theo Little's Law

Giả sử:

- <code>λ</code>: tốc độ message trung bình đi vào flow (message/giây).
- <code>W</code>: thời gian một message nằm trong hệ thống (giây), kể cả chờ queue.
- <code>k</code>: số entry history trung bình trên mỗi message đang tồn tại.
- <code>b</code>: **số byte bổ sung đo được** cho một entry (gồm object, metadata và collection overhead theo JVM/version).

Thì ước lượng phần memory sống thêm bởi history:

\[
\text{History bytes in flight} \approx \lambda \times W \times k \times b
\]

Ví dụ **giả định để tính quy mô, không phải benchmark thực tế**: 5.000 message/giây, mỗi message tồn tại trung bình 0,2 giây, đi qua 8 tracked hops; nếu đo được 160 byte bổ sung/entry thì:

~~~text
In-flight ≈ 5.000 × 0,2 = 1.000 message
History tăng thêm ≈ 1.000 × 8 × 160 B = 1.280.000 B (~1,28 MB)
~~~

Nếu thời gian nằm trong queue tăng từ 0,2 lên 20 giây, số message đang tồn tại có thể tăng 100 lần và lượng history trong heap **cũng có thể tăng tương ứng**, ngay cả khi throughput không đổi. Với persistent store, phải tính thêm kích thước dữ liệu đã serialize và cách DB/broker buffer message.

Đây chỉ là mô hình định hướng. Object layout, alignment, Java version, reference sharing, compression, payload và việc clone history ở fan-out có thể khiến số đo khác đáng kể. Hãy **đo allocation/JFR và kích thước message thực** trước khi áp dụng để lập capacity plan.

### Mô hình dung lượng log

Dung lượng log thô tương đối dễ ước lượng:

\[
\text{Bytes/s} \approx \text{messages/s} \times \text{log points/message} \times \text{bytes/log event}
\]

Ví dụ: 10.000 message/giây, mỗi message tạo 3 log event, mỗi event 300 byte sau formatting, tương đương **9 MB/giây** hay khoảng **778 GB/ngày** log thô theo đơn vị thập phân, *chưa* tính chỉ mục collector, replication, metadata của hệ thống logging và nén. Đây là chi phí hoàn toàn có thể phát sinh chỉ vì ba <code>.log()</code> ở lưu lượng cao.

Khi sử dụng async appender, dữ liệu có thể nằm tạm trong queue trên heap. Nếu sink chậm hơn producer, queue sẽ đầy; lúc đó hệ thống phải **block**, **drop**, **spill** hay **fail** theo cấu hình backend. Không nên coi async là cách làm biến mất chi phí.

## 10. Message history trên các kiểu channel khác nhau

Tác động hiệu năng tùy topology, không chỉ tùy số hop:

| Ranh giới runtime | History/log sẽ ảnh hưởng ra sao? | Điều cần đo |
|---|---|---|
| <code>DirectChannel</code> | Handler, interceptor và log đồng bộ có thể nằm trong latency của sender | Duration <code>send()</code>, p99 latency, CPU sender |
| <code>ExecutorChannel</code> | Có thread handoff, task queue; message cùng headers/history được tham chiếu bởi task | Executor queue wait, active threads, heap |
| <code>QueueChannel</code> in-memory | History nằm cùng message đang chờ | Queue depth × message size, GC và receive lag |
| <code>JdbcChannelMessageStore</code> | Header history được ghi/đọc cùng message tùy serializer | Kích thước row, serialize/deserialize, DB I/O |
| <code>MessageGroupStore</code> aggregator | Nhiều fragment mang history; group giữ tới release/timeout | Group size, group age, store size, retention |
| Delayer | Message có thể giữ header trong store rất lâu | Delay count, expired age, storage và reschedule cost |
| <code>PublishSubscribeChannel</code>/router | Fan-out tạo các đường history riêng; tổng số entry tăng trên các nhánh | Branch count, copied headers, payload size |
| Broker inbound/outbound adapter | History chỉ sống qua transport nếu header mapper/serializer cho phép | Header size, broker quota, network throughput |
| Reactor <code>FluxMessageChannel</code> | Subscription/backpressure và context propagation có semantics riêng | Demand, prefetch, worker wait, onError, headers |

Một lưu ý quan trọng: thêm <code>ThreadPoolTaskExecutor</code> để chuyển logging ra thread riêng có thể cải thiện **latency nhìn từ sender**, nhưng không cải thiện throughput tổng thể nếu logging backend vẫn là nút cổ chai và queue phải chứa backlog tăng vô hạn.

## 11. Metrics và tracing: không thay thế history nhưng cũng phải có ngân sách

Spring Integration 6.x hỗ trợ Micrometer/Observation. Có thể cấu hình <code>@EnableIntegrationManagement</code> để chọn những managed component tạo Observation:

~~~java
@Configuration
@EnableIntegration
@EnableIntegrationManagement(
    defaultLoggingEnabled = "false",
    observationPatterns = {
        "orders.process",
        "orders.outbound*"
    })
class TargetedObservationConfig {
}
~~~

Ví dụ này là **lựa chọn cấu hình riêng**, không phải bean thứ hai cần cộng vào <code>OrderHistoryFlowConfig</code> nếu ứng dụng đã bật management ở đó. Trong ứng dụng thật, hợp nhất các annotation vào một cấu hình để không mơ hồ về việc configurer nào đang áp dụng.

<code>observationPatterns</code> mặc định **không bật Observation cho tất cả component**; cần có <code>ObservationRegistry</code> và <code>ObservationHandler</code> phù hợp để xuất meter/tracing. Với Spring Boot Actuator, xem lại auto-configuration hiện có trước khi tự tạo registry hoặc handler thứ hai.

| Quan sát | Metric/tracing phù hợp | History phù hợp |
|---|---|---|
| Tỷ lệ lỗi handler trong 5 phút | Counter/timer và outcome tags | Không hiệu quả để tổng hợp từ từng message |
| Latency p95/p99 của handler | <code>spring.integration.handler</code> timer khi Observation được bật | Timestamp hop không thay thế duration |
| Queue lag và backlog | Queue depth, age, enqueue-to-start timer riêng | History có thể thiếu thời gian chờ chính xác |
| Một message đi nhầm nhánh router | Trace + history có chọn lọc | Rất hữu ích để xác định các hop đã qua |
| Context xuyên broker/process | Tracing propagator + message headers | Chỉ nếu history header được bảo toàn |
| Audit bắt buộc, không mất khi crash | Persistent audit/outbox có transaction và retention | Không đủ làm nguồn chứng cứ duy nhất |

Các meter dựa trên Observation thường có tên như <code>spring.integration.handler</code> hoặc <code>spring.integration.producer</code>. Khi dùng cơ chế meter truyền thống, có thể gặp <code>spring.integration.send</code>, <code>spring.integration.receive</code>. Đừng xây dashboard trên tên meter không kiểm tra: phiên bản Spring Integration/Micrometer và cấu hình instrumentation quyết định những meter nào thực sự có mặt.

### Cardinality là chi phí độc lập với log volume

Nếu mỗi message mang <code>orderId</code> khác nhau rồi bạn biến order ID thành **metric tag**, registry/Prometheus có thể phải quản lý hàng triệu time series. Chỉ dùng low-cardinality tag như component name ổn định, environment, result, loại handler. Business ID nên nằm ở **trace/log có chính sách lưu giữ** hoặc trong hệ thống truy vấn nghiệp vụ; tuyệt đối không dùng làm nhãn mặc định của timer.

Với dynamic tenant flow, managed name sinh theo UUID tenant cũng có thể làm tăng cardinality khi mỗi tenant tạo một series. Nên quyết định trước có cần metric theo tenant hay chỉ cần theo nhóm tenant/loại flow, và cấu hình meter filter/sampling phù hợp.

## 12. Bật/tắt message history có kiểm soát ở runtime

<code>MessageHistoryConfigurer</code> hỗ trợ thay đổi component-name patterns và có lifecycle riêng. Tài liệu yêu cầu **stop configurer trước khi đổi pattern**, sau đó start lại:

~~~java
@Component
public class MessageHistoryController {
    private final MessageHistoryConfigurer configurer;

    public MessageHistoryController(MessageHistoryConfigurer configurer) {
        this.configurer = configurer;
    }

    public synchronized void trackOrdersOnly() {
        configurer.stop();
        try {
            configurer.setComponentNamePatternsString("orders.*");
        } finally {
            configurer.start();
        }
    }
}
~~~

<code>MessageHistoryConfigurer</code> thuộc <code>org.springframework.integration.history</code>. Đoạn code giả định application context đã bật <code>@EnableMessageHistory</code> và chỉ có một configurer phù hợp.

**Stop ở đây là stop hoạt động ghi history**, không phải stop tất cả <code>IntegrationFlow</code> hoặc tiêu hủy message đang nằm trong queue. Những message đã có history header có thể vẫn mang metadata cũ qua các chặng tiếp theo; thay pattern không “xóa ngược” lịch sử trong message đã gửi.

Với JMX được cấu hình, configurer có thể được xuất làm MBean để điều chỉnh pattern phục vụ điều tra sự cố. Không mở thao tác này công khai; thay đổi tracking toàn hệ thống ở giờ cao điểm có thể khiến chi phí và số lượng message header tăng đột biến.

### Quy trình dùng history như một công tắc chẩn đoán

1. Xác định flow và tên component cần điều tra từ graph/runtime.
2. Đo baseline CPU/latency/heap/log ingest ở trạng thái hiện tại.
3. Bật pattern hẹp cho một nhóm component, ghi thời gian bắt đầu và thời gian dự kiến tắt.
4. Lấy một số message mẫu từ test hoặc error path được phép, đọc history để tìm hop thiếu.
5. Điều chỉnh logging/observation nếu cần, không tự động bật tất cả cùng lúc.
6. Sau khi chẩn đoán, trả configurer về pattern phù hợp chính sách production và kiểm tra metrics/chi phí đã trở về baseline.

**Không thay đổi pattern bằng cách tạo thêm annotation hoặc bean runtime liên tục.** Khi nhiều configurer cùng tồn tại, khó xác định nguồn cấu hình hiệu lực và có thể vi phạm yêu cầu single source của Spring Integration.

## 13. Tối ưu logging mà không làm mất khả năng điều tra

Một chính sách log theo mức ưu tiên:

| Trạng thái | Log nên có | Log nên tránh |
|---|---|---|
| Bình thường | Business event ID, correlation, endpoint và kết quả tổng quát tại các ranh giới trọng yếu | Mọi hop, full payload, toàn bộ headers |
| Khi latency tăng | p95/p99 metrics, thread/queue lag, log một số message chậm | Bật DEBUG mọi package trong thời gian dài |
| Khi handler lỗi | Exception chain, failed message metadata được phép, retry count, transaction outcome | Lặp cùng stack trace trên mỗi tầng, dump dữ liệu nhạy cảm |
| Khi truy vết một batch | Message history pattern hẹp, trace sampling theo correlation hợp lệ | Metric tag chứa batch ID/cardinality cao |
| Khi nghi mất message | Source ACK/redelivery, store state, error channel và audit | Chỉ dựa vào dòng “message received” |

### Redaction và truy cập dữ liệu

Log full headers có thể chứa thông tin nhạy cảm như token, cookie, email, tenant identifier, payload PII hoặc thông tin kết nối. Một <code>LoggingHandler</code> có biểu thức <code>m.getHeaders()</code> trông tiện cho debug nhưng không phù hợp để bật diện rộng.

Nên:

- sử dụng whitelist field được phép ghi thay vì blacklist các field “nguy hiểm đã biết”;
- không gọi <code>toString()</code> trên payload/object không kiểm soát;
- ghi correlation ID và business ID đã che/biến đổi nếu cần;
- giới hạn độ dài log event, retention và người có quyền đọc;
- phân tách log debugging khỏi audit bền vững;
- tránh dùng nội dung payload làm khóa lấy mẫu/metric tag nếu chưa có đánh giá bảo mật.

<code>MessageHistory</code> thường chỉ ghi metadata tên/type/timestamp, nhưng tên component có thể chứa tenant hoặc thông tin vận hành. Đừng coi header này tự động an toàn để chuyển qua mọi hệ thống ngoài hoặc lưu vô hạn.

## 14. Benchmark chi phí: đo theo A/B có kiểm soát

Một bài test đo hiệu năng không nên chỉ gửi vài message rồi dùng <code>System.nanoTime()</code> tính trung bình. JIT warm-up, GC, logging appender, persistence backend, thread contention và scheduler đều có thể làm kết quả khác biệt.

Đề xuất bốn cấu hình A/B, trên **cùng topology và cùng workload**:

| Cấu hình | History | Logging | Metrics/tracing |
|---|---|---|---|
| A — baseline | Tắt | INFO tối thiểu, không log per-message | Metric hệ thống cơ bản |
| B — history | Pattern chỉ chọn 3–5 hop | Giống A | Giống A |
| C — log | Giống A | Thêm một log metadata ở một hop | Giống A |
| D — quan sát chọn lọc | Pattern giống B | Log metadata giống C | Observation một số handler quan trọng |

Giữ cố định: Java/Spring version, JVM flags, CPU/memory limit, thread pool, DB/broker latency, payload size, message rate, số tenant và tỷ lệ error/retry. Đặc biệt phải kiểm tra source không tự bottleneck sớm khiến bạn kết luận thêm logging “không ảnh hưởng gì”.

### Chỉ số cần thu thập

1. **Throughput:** message nghiệp vụ được xử lý thành công/giây, không phải chỉ số lần <code>send()</code> được chấp nhận.
2. **End-to-end latency:** thời gian nhận đến completion/commit/ACK theo hợp đồng; xem p50/p95/p99 và tail latency.
3. **CPU, allocation, GC:** CPU user/system, allocation rate, heap, GC pause, object histogram; dùng JFR/JMC hoặc profiler phù hợp.
4. **Threading:** executor active, queue wait, poller lag, thread dump nếu có block.
5. **Log system:** event/giây, bytes/giây, appender queue depth, drop/block count, thời gian export.
6. **Persistence/network:** kích thước message trước/sau có history, DB read/write latency, broker bytes/giây.
7. **Correctness:** số message mất/trùng, side effect, error channel, retry attempt, correlation còn nguyên.

**Không tối ưu throughput bằng cách làm rơi log bắt buộc hoặc ACK sớm message chưa xử lý.** Kết quả phải so sánh trong cùng một hợp đồng delivery; nếu D “nhanh hơn” vì đã bỏ lưu audit/transaction, phép so sánh không công bằng.

### Ví dụ báo cáo benchmark theo cấu trúc

~~~text
Runtime: Java 17, Spring Integration 6.x
Topology: inbound → DirectChannel → validation
             → ExecutorChannel → JDBC handler → outbound
Load: [message rate, payload size, duration, concurrency]
Run: warm-up và đo đủ nhiều vòng, cùng dữ liệu đầu vào

             A baseline   B history   C logging   D combined
TPS          <đo>        <đo>        <đo>        <đo>
p99 latency  <đo>        <đo>        <đo>        <đo>
alloc MB/s   <đo>        <đo>        <đo>        <đo>
GC pause     <đo>        <đo>        <đo>        <đo>
log MB/s     <đo>        <đo>        <đo>        <đo>
~~~

Các ô <code>&lt;đo&gt;</code> là **dữ liệu phải thu thập thực tế**, không phải kết quả đã được đo trong bài học. Với overhead rất nhỏ ở một method, JMH có thể giúp đánh giá allocation/chi phí thao tác; với Spring Integration runtime, **load test end-to-end** mới phản ánh cạnh tranh CPU, store, network và logging backend.

## 15. Kiểm thử history và log ở runtime

### 15.1. Test history xuất hiện sau khi đi qua tracked component

Ví dụ sử dụng Spring context của <code>OrderHistoryFlowConfig</code> ở mục 4:

~~~java
@SpringJUnitConfig(OrderHistoryFlowConfig.class)
class OrderHistoryFlowTest {

    @Autowired
    @Qualifier("orders.input")
    DirectChannel input;

    @Autowired
    @Qualifier("orders.output")
    QueueChannel output;

    @Test
    void messageHasTrackedHistoryAfterPassingFlow() {
        Message<OrderCommand> request = MessageBuilder
            .withPayload(new OrderCommand("O-77", 1))
            .setHeader("correlationId", "checkout-77")
            .build();

        assertTrue(input.send(request));
        Message<?> reply = output.receive(3_000);
        assertNotNull(reply);
        assertEquals(new OrderResult("O-77", "ACCEPTED"),
            reply.getPayload());

        MessageHistory history = MessageHistory.read(reply);
        assertNotNull(history);
        assertFalse(history.isEmpty());
        assertTrue(history.stream().anyMatch(hop ->
            String.valueOf(hop.get(MessageHistory.NAME_PROPERTY))
                .startsWith("orders.")));
    }
}
~~~

<code>@SpringJUnitConfig</code> thuộc <code>org.springframework.test.context.junit.jupiter</code>; assertions thuộc JUnit Jupiter. Kiểm tra <code>history.isEmpty()</code> và prefix của component thay vì so cứng từng timestamp/entry theo thứ tự chính xác: component do framework sinh và cấu trúc message có thể đổi khi nâng cấp version.

Nếu test thêm nhiều message vào cùng <code>QueueChannel</code>, cần **drain/reset fixture** sau mỗi ca để không đọc nhầm message từ test trước. Nếu đổi sang <code>ExecutorChannel</code>, dùng latch/chờ điều kiện có timeout thay vì assert handler hoàn tất ngay sau <code>send()</code>.

### 15.2. Test hàm tạo nội dung log không dump payload

Một test đơn giản có thể kiểm tra **log expression** đã được chọn trước khi wiring vào <code>.log()</code>:

~~~java
Function<Message<?>, String> safeLog = message ->
    "messageId=" + message.getHeaders().getId()
    + ", correlationId=" + message.getHeaders().get("correlationId");

Message<String> message = MessageBuilder
    .withPayload("secret-card-token")
    .setHeader("correlationId", "corr-100")
    .build();

String line = safeLog.apply(message);
assertTrue(line.contains("corr-100"));
assertFalse(line.contains("secret-card-token"));
~~~

<code>Function</code> thuộc <code>java.util.function</code>. Test này chỉ xác minh biểu thức đã **không đưa payload vào nội dung**, không chứng minh logging backend, appender hoặc các log khác trong ứng dụng cũng đã redaction đúng. Nếu cần test output log thực, dùng capture appender ở tầng logging framework và kiểm thử nhiều nguồn lỗi.

### 15.3. Test fan-out không làm trộn lịch sử

Thiết kế bài test với <code>PublishSubscribeChannel</code> và hai output branch khác nhau:

1. Gửi một message có <code>correlationId</code> duy nhất vào channel trước fan-out.
2. Mỗi nhánh đi qua một named component riêng rồi nhận tại queue/sink riêng.
3. Đọc <code>MessageHistory</code> trong message ở mỗi sink.
4. Xác nhận các entry ở phần gốc được giữ; entry của nhánh A không rò sang nhánh B và ngược lại theo hành vi framework ở phiên bản test.
5. Lặp test khi có concurrency và khi custom router/splitter tạo message mới.

Test này đặc biệt hữu ích khi migration từ phiên bản trước **6.3** sang 6.3+ hoặc có custom component tự nhân bản message.

## 16. Quan sát lỗi mà không vô tình thay đổi retry/transaction

Logging và history **không phải các advice thực hiện recovery**. Một handler ném exception trong <code>DirectChannel</code> có thể đưa exception về sender; nếu đi qua <code>ExecutorChannel</code>, lỗi xảy ra ở worker và phải được quan sát qua error handler/error flow tương ứng.

| Tình huống | Vì sao dễ hiểu sai? | Bằng chứng thực sự cần |
|---|---|---|
| Log “received” rồi không có log “completed” | Có thể block, crash, cancel, timeout, logging bị drop | Handler completion/error, queue, transaction, trace |
| History có <code>orders.handler</code> | Không chứng minh side effect downstream đã commit | DB state, transaction outcome, outbox/ACK |
| Một history có cùng handler nhiều lần | Có thể do retry, loop, nhiều lượt hợp lệ | Retry attempt, message ID, business event ID |
| ErrorMessage chứa history | History thường là đoạn đã đi tới điểm lỗi, không cho biết bước nào rollback | Failed/original message, cause, transaction |
| Log xuất hiện sau khi sender timeout | Async task hoặc buffered logger chưa hoàn tất trước timeout | Thread trace, completion boundary |
| Trace kết thúc thành công nhưng nghiệp vụ lỗi | Recovery biến exception thành completion hoặc outcome đo sai boundary | Business result, DLQ, recoverer và error policy |

Không dùng <code>onErrorResume</code>, <code>catch (Exception)</code> hoặc một <code>ErrorMessage</code> consumer trả về bình thường chỉ để ghi log mà quên propagate lỗi theo hợp đồng. Điều này có thể khiến nguồn ACK message sớm và không retry dù nghiệp vụ chưa hoàn tất.

Trong hệ thống có retry, nên gắn **attempt number** vào structured log ở boundary retry (theo thông tin có sẵn của retry context) và dùng một **business idempotency key** ổn định. Message ID ngẫu nhiên hoặc số entry trong history không đủ để kết luận số lần side effect đã xảy ra.

## 17. Chẩn đoán khi bật history/logging rồi hệ thống chậm

| Triệu chứng | Giả thuyết nên kiểm tra | Hành động |
|---|---|---|
| p99 <code>DirectChannel.send()</code> tăng | Log/wiretap đồng bộ hoặc payload <code>toString()</code> đắt | Đo formatter/appender, chuyển sang metadata-only, thu hẹp điểm log |
| Allocation rate và GC tăng mạnh | History quá nhiều hop, clone trên fan-out hoặc log events | Giảm pattern, kiểm tra Java/Spring version, JFR allocation |
| Queue tăng khi DEBUG được bật | Thread/executor bị log I/O chặn hoặc pool logging đã đầy | Đo queue wait và appender saturation; kiểm tra drop/block policy |
| JDBC store phình nhanh | History header được persist cùng message, nhiều pending group | Đo message bytes/row và retention/group timeout |
| Broker báo message/header quá lớn | Headers/history/trace baggage vượt quota | Kiểm tra mapping và giới hạn header/payload, tách audit |
| Chỉ một tenant gây nhiều metric series | Managed names/tags động theo tenant | Điều chỉnh naming, meter filter và cardinality |
| Trace không nối qua queue/broker | Context propagation không được bật đúng producer/consumer | Kiểm tra ObservationRegistry, propagation và header mapper |
| Tắt DEBUG nhưng CPU vẫn cao | History/trace vẫn bật, logging handler vẫn dùng INFO hoặc appender đắt | Kiểm tra **từng** lớp quan sát độc lập |
| Đã bật history nhưng không giúp debug | Pattern sai tên, branch custom làm mất history | Liệt kê component name, test header và custom message builder |

### Runbook theo thứ tự

1. Xác nhận **workload** không đổi: ingress rate, payload size, retry/error ratio và topology.
2. Đo p95/p99 end-to-end, CPU/GC, queue depth và backend logging/export.
3. Liệt kê message history pattern, <code>LoggingHandler</code>/<code>.log()</code> active, framework log levels, Observation patterns và tracing sampler.
4. Tắt/giảm **một lớp** quan sát có kiểm soát rồi đo lại (không tắt tất cả một lúc nếu đang có sự cố cần điều tra).
5. Với long-lived message, đo header size thực ở QueueChannel/JDBC store/broker.
6. Nếu có multiple branch hoặc custom splitter, kiểm tra clone history và message count trên từng nhánh.
7. Kiểm tra nghiệp vụ vẫn đúng: output, ACK/commit, retry, error channel, idempotency.
8. Chọn cấu hình production nhỏ nhất đáp ứng yêu cầu on-call; ghi nhận giới hạn và chi phí bằng số đo.

## 18. Checklist production

- [ ] Chỉ bật <code>@EnableMessageHistory</code> khi cần và thu hẹp pattern tới những named component quan trọng.
- [ ] Xác nhận phiên bản Spring Integration, hiểu append-only và fan-out cloning từ 6.3 trở đi.
- [ ] Không dùng history header làm audit store hay bằng chứng transaction commit.
- [ ] Dùng <code>LoggingHandler</code>/<code>.log()</code> với metadata được whitelist; tránh full payload và headers nhạy cảm.
- [ ] Hiểu <code>defaultLoggingEnabled=false</code> chỉ ảnh hưởng framework logging được quản lý, không tắt mọi log/metric/history.
- [ ] Đã đo latency/throughput/heap/GC và log bytes/giây khi bật các lớp quan sát quan trọng.
- [ ] Biết rõ chính sách overflow và lifecycle của async appender/telemetry exporter.
- [ ] Cân nhắc history/header size ở persistent queue, delayed message, aggregator group và broker.
- [ ] Trace/metrics dùng component/tag low-cardinality; không đặt message ID/order ID vào meter tags mặc định.
- [ ] Có runbook bật history có thời hạn, stop configurer trước khi đổi pattern và hoàn nguyên sau điều tra.
- [ ] Test header history, log redaction, branch isolation, error/retry và correctness ở ranh giới thread/transaction.
- [ ] Cân bằng quan sát với an toàn dữ liệu, retention, truy cập log và yêu cầu audit bền vững.

**Kết luận:** <code>MessageHistory</code> cho thấy *message đã đi qua những component được theo dõi nào*, logging kể lại sự kiện ở những điểm đã chọn, còn metrics/tracing giúp phát hiện vấn đề theo tỷ lệ và thời gian. Tất cả đều có chi phí. Trong Spring Integration runtime, cách làm bền vững là **đặt tên component ổn định → chọn ít hop quan trọng → log metadata an toàn → đo overhead end-to-end → chỉ mở rộng khi có câu hỏi điều tra cụ thể**. Làm như vậy giúp vẫn chẩn đoán được lỗi threading, correlation, retry và message store mà không biến công cụ quan sát thành bottleneck của chính message flow.

## Tài liệu tham khảo

- [Spring Integration Reference — Message History](https://docs.spring.io/spring-integration/reference/message-history.html)
- [Spring Integration Reference — Metrics and Management](https://docs.spring.io/spring-integration/reference/metrics.html)
- [Spring Integration Reference — Logging Channel Adapter](https://docs.spring.io/spring-integration/reference/logging-adapter.html)
- [Spring Integration Reference — Java DSL log() Operator](https://docs.spring.io/spring-integration/reference/dsl/java-log.html)
- [Spring Integration 6.5 Javadoc — MessageHistory](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/history/MessageHistory.html)
- [Spring Integration 6.5 Javadoc — MessageHistoryConfigurer](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/history/MessageHistoryConfigurer.html)
- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html)
- [Micrometer Reference — Observation](https://docs.micrometer.io/micrometer/reference/observation/introduction.html)
