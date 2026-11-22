# Splitter output channel

## 1. Mục tiêu và ngữ cảnh

Trong chương **Splitter** của module **SPRING_INTEGRATION_CORE**, bài này giải thích nơi các message con được gửi đến sau khi tách một message đầu vào. Đây là điểm nối giữa logic chia dữ liệu và các endpoint tiếp theo như transformer, router, filter, service activator hoặc aggregator.

Sau bài học, bạn có thể:

- Chỉ ra output channel của splitter trong Java DSL và cấu hình annotation.
- Phân biệt channel cấu hình trực tiếp với header `replyChannel`.
- Chọn loại channel phù hợp với nhu cầu xử lý đồng bộ, đệm dữ liệu hoặc xử lý bằng executor.
- Theo dõi message con bằng các header correlation và sequence.
- Nhận diện lỗi giao nhận, kết quả gửi dở dang và nhu cầu gom kết quả trước khi trả về gateway.
- Viết kiểm thử quan sát trực tiếp các message xuất hiện trên output channel.

Ví dụ dùng API Spring Integration 6.5 và Java 17. Dự án cần có `org.springframework.integration:spring-integration-core`; phần kiểm thử dùng JUnit Jupiter. Phiên bản dependency cần theo bộ quản lý dependency của dự án để tương thích với Spring Framework đang dùng.

## 2. Output channel nhận từng message con

Giả sử một request chứa ba mã hàng:

~~~text
Message đầu vào:
  payload = ["BOOK", "PEN", "BAG"]
  headers.batchId = "B-42"
~~~

Sau khi tách, splitter gửi ba message riêng biệt:

~~~text
Message 1: payload = "BOOK"
Message 2: payload = "PEN"
Message 3: payload = "BAG"
~~~

`outputChannel` là đích mà splitter dùng để gửi các message đó. Một output channel có thể nhận nhiều lần gọi `send(...)` trong quá trình xử lý một message đầu vào. Tài liệu [Splitter của Spring Integration](https://docs.spring.io/spring-integration/reference/6.5/splitter.html) mô tả mô hình một message được chia thành nhiều phần và từng phần được gửi đi để xử lý độc lập.

~~~mermaid
flowchart LR
    A["Message chứa List gồm 3 mã hàng"] --> B["Channel batches"]
    B --> C["Splitter"]
    C -->|"Message BOOK"| D["Output channel lineItems"]
    C -->|"Message PEN"| D
    C -->|"Message BAG"| D
    D --> E["Endpoint xử lý một mã hàng"]
~~~

Trong ví dụ này, `lineItems` nhận ba message có payload kiểu `String`. Nó không nhận một message có payload là toàn bộ danh sách ba phần tử.

Cũng không có quy tắc tự động gửi phần tử thứ nhất sang channel A, phần tử thứ hai sang channel B. Nếu cần chọn đích theo nội dung từng phần tử, hãy đặt router sau splitter. Nếu cần mọi subscriber đều nhận từng phần tử, hãy chọn một channel có ngữ nghĩa publish-subscribe.

Việc tách thành nhiều message cũng chưa quyết định số thread xử lý. Một luồng dùng toàn `DirectChannel` vẫn có thể thực hiện mọi công việc tuần tự trên thread gửi ban đầu.

## 3. Splitter xác định đích gửi như thế nào?

### 3.1. Output channel được khai báo rõ

Trong luồng thông thường, cấu hình output channel trực tiếp là cách dễ quan sát nhất:

~~~java
IntegrationFlow.from("batches")
        .split()
        .channel("lineItems")
        .get();
~~~

Ở vị trí này, `.channel("lineItems")` nối output của splitter vào channel `lineItems`. Đây là cấu hình cấu trúc của flow.

Các hình thức cấu hình tương ứng gồm:

| Cách cấu hình | Vị trí khai báo |
|---|---|
| Java DSL | `.split().channel("lineItems")` |
| Annotation | `@Splitter(outputChannel = "lineItems")` |
| XML | `<int:splitter ... output-channel="lineItems"/>` |
| Cấu hình handler bằng Java | `splitter.setOutputChannel(channel)` hoặc `setOutputChannelName("lineItems")` |

Không cấu hình đồng thời cả đối tượng channel và tên output channel trên cùng một handler. Khi dùng DSL, nên để DSL nối các bước của flow, tránh tự gán một đích khác bên trong handler rồi lại khai báo đích phía sau.

### 3.2. Fallback qua header replyChannel

Nếu không có output channel trực tiếp, splitter có thể dùng `replyChannel` để tìm nơi gửi kết quả.

Với luồng không sử dụng Routing Slip, quy tắc là:

1. Dùng output channel đã cấu hình nếu có.
2. Nếu chưa có, tìm `replyChannel` trên message yêu cầu.
3. Nếu vẫn chưa có và kết quả là một message có `replyChannel` riêng, có thể dùng header đó.
4. Nếu cần gửi kết quả mà không tìm được đích, phát sinh lỗi phân giải đích.

`replyChannel` có thể là một đối tượng `MessageChannel` hoặc tên channel dạng `String`. Quy tắc trên được thể hiện trong [AbstractMessageProducingHandler của Spring Integration 6.5.0](https://github.com/spring-projects/spring-integration/blob/v6.5.0/spring-integration-core/src/main/java/org/springframework/integration/handler/AbstractMessageProducingHandler.java). Routing Slip có cơ chế chọn đích riêng khi không khai báo output channel; các ví dụ trong bài không sử dụng cơ chế đó.

Ví dụ xây dựng một request có địa chỉ phản hồi:

~~~java
QueueChannel replies = new QueueChannel();

Message<List<String>> request = MessageBuilder
        .withPayload(List.of("BOOK", "PEN"))
        .setReplyChannel(replies)
        .build();
~~~

Nếu splitter không có output channel, các message con có thể được gửi đến `replies`. Nếu splitter đã được nối tới `lineItems`, các message con đi tới `lineItems`; header `replyChannel` vẫn có thể được giữ lại để một endpoint phía sau trả kết quả cuối cùng.

Đặt một header tùy ý có tên `outputChannel` không tương đương với cấu hình output channel của endpoint.

### 3.3. Phân biệt các trường hợp không có dữ liệu đầu ra

| Trường hợp | Hành vi cần hiểu |
|---|---|
| Có message con nhưng không có đích gửi | Có lỗi phân giải đích; thường thấy nguyên nhân `DestinationResolutionException` |
| Splitter trả một collection rỗng | Không có message con để gửi; có thể đưa request gốc đến discard channel nếu đã cấu hình |
| Logic split trả `null` | Mặc định kết thúc nhánh; nếu bật `requiresReply` thì cần xét lỗi thiếu reply |
| Output là `nullChannel` | Message con được gửi đến channel loại bỏ dữ liệu |
| Output là queue chưa có consumer | Message có thể đang nằm trong queue, chưa được xử lý |

Một collection rỗng khác với một collection chứa message có payload rỗng. Khi không có phần tử, không tự xuất hiện một message báo “đã hoàn tất”.

## 4. Ví dụ đầy đủ: từ batch đến queue chứa từng mã hàng

Cấu hình sau khai báo tường minh cả channel đầu vào và đầu ra. `batches` là `DirectChannel` để nhận request; `lineItems` là `QueueChannel` để quan sát kết quả.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
public class SplitterOutputConfig {

    @Bean
    public DirectChannel batches() {
        return new DirectChannel();
    }

    @Bean
    public QueueChannel lineItems() {
        return new QueueChannel(100);
    }

    @Bean
    public IntegrationFlow batchToItems() {
        return IntegrationFlow.from("batches")
                .split()
                .channel("lineItems")
                .get();
    }
}
~~~

`.split()` ở đây dùng splitter mặc định với payload là `List<String>`. Mỗi phần tử trở thành payload của một message con.

Đoạn chương trình sau mở Spring context, gửi một batch và đọc các message đầu ra. Đặt lớp này cùng package với `SplitterOutputConfig`.

~~~java
import java.util.List;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class SplitterOutputDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(
                             SplitterOutputConfig.class)) {

            DirectChannel input =
                    context.getBean("batches", DirectChannel.class);
            QueueChannel output =
                    context.getBean("lineItems", QueueChannel.class);

            Message<List<String>> request = MessageBuilder
                    .withPayload(List.of("BOOK", "PEN", "BAG"))
                    .setHeader("batchId", "B-42")
                    .build();

            input.send(request);

            for (int i = 0; i < 3; i++) {
                Message<?> item = output.receive(1000);

                if (item == null) {
                    throw new IllegalStateException(
                            "Thiếu message con thứ " + (i + 1));
                }

                Object number = item.getHeaders().get(
                        IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER);
                Object size = item.getHeaders().get(
                        IntegrationMessageHeaderAccessor.SEQUENCE_SIZE);

                System.out.printf(
                        "%s | batchId=%s | sequence=%s/%s%n",
                        item.getPayload(),
                        item.getHeaders().get("batchId"),
                        number,
                        size);
            }
        }
    }
}
~~~

Kết quả mong đợi:

~~~text
BOOK | batchId=B-42 | sequence=1/3
PEN  | batchId=B-42 | sequence=2/3
BAG  | batchId=B-42 | sequence=3/3
~~~

Độ rộng khoảng trắng khi in có thể khác; ba payload và giá trị sequence là phần cần quan sát.

Trong cấu hình này:

- Một request đi vào `batches`.
- Splitter được gọi trên thread gửi request.
- Ba message con được lần lượt đặt vào `lineItems`.
- Chương trình tự gọi `receive(...)` để lấy từng message ra.
- Chưa có endpoint nghiệp vụ tự động xử lý các message trong queue.

Giới hạn `100` của queue được chọn cho bài thực hành. Với batch lớn hơn khả năng chứa và không có consumer đồng thời, việc gửi có thể chờ rồi thất bại theo timeout.

## 5. Channel tường minh và channel ngầm trong Java DSL

### 5.1. Nối trực tiếp tới một endpoint

Không nhất thiết phải đặt tên mọi channel:

~~~java
@Bean
public IntegrationFlow normalizeItems() {
    return IntegrationFlow.from("rawBatches")
            .split()
            .transform(String.class, value -> value.strip().toUpperCase(
                    java.util.Locale.ROOT))
            .channel("normalizedItems")
            .get();
}
~~~

Đây là đoạn cấu hình thay thế minh họa; cần khai báo `normalizedItems` theo cách muốn nhận kết quả.

Giữa splitter và transformer, DSL tạo kết nối qua channel ngầm, thông thường là `DirectChannel`. Output channel trực tiếp của splitter chính là channel ngầm trước transformer. `normalizedItems` nằm sau transformer nên là output của transformer.

~~~text
rawBatches
  -> splitter
  -> channel ngầm
  -> transformer
  -> normalizedItems
~~~

Cách đọc này giúp tránh nhầm mọi `.channel(...)` xuất hiện phía sau với output trực tiếp của splitter. Java DSL xây dựng các channel và endpoint trong Spring context, như giải thích trong [tài liệu Java DSL](https://docs.spring.io/spring-integration/reference/6.5/dsl.html).

### 5.2. Đặt channel có tên ở ranh giới cần quan sát

Một channel có tên hữu ích khi:

- Một flow khác cần nhận message từ điểm đó.
- Kiểm thử cần thu hoặc kiểm tra message.
- Cần interceptor, wire tap hoặc theo dõi lưu lượng tại một ranh giới cụ thể.
- Muốn thay đổi cơ chế giao nhận bằng cách đổi loại channel.

Tên channel thể hiện trách nhiệm, chẳng hạn `lineItems` hoặc `validatedItems`, thường dễ đọc hơn một tên gắn chặt với vị trí như `splitterOutput3`.

### 5.3. Cấu hình bằng annotation

Có thể thay flow splitter ở phần 4 bằng một endpoint annotation:

~~~java
import java.util.List;

import org.springframework.integration.annotation.MessageEndpoint;
import org.springframework.integration.annotation.Splitter;

@MessageEndpoint
public class BatchSplitter {

    @Splitter(
            inputChannel = "batches",
            outputChannel = "lineItems")
    public List<String> split(List<String> items) {
        return items;
    }
}
~~~

Phương thức trả danh sách; adapter splitter thực hiện việc tạo và gửi các message con. Cần đăng ký `BatchSplitter` qua component scanning hoặc `@Bean`, đồng thời giữ các channel cần thiết.

Đây là **phương án thay thế** cho `batchToItems()`. Nếu đăng ký cả hai trên cùng `DirectChannel batches`, bạn tạo hai consumer cạnh tranh. Message đầu vào có thể được phân phối giữa chúng, khiến việc quan sát sai với mục đích bài thực hành.

API [@Splitter](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/annotation/Splitter.html) cũng cung cấp cấu hình `applySequence`, `sendTimeout` và poller cho endpoint.

## 6. Loại output channel thay đổi hành vi toàn luồng

Tên `outputChannel` chỉ nói đến vai trò. Lớp channel cụ thể quyết định cách giao message cho consumer.

| Loại channel | Cách tiếp nhận từng message con | Khi áp dụng |
|---|---|---|
| `DirectChannel` | Gọi một subscriber trên thread gửi | Xử lý đồng bộ, chuỗi bước ngắn |
| `ExecutorChannel` | Giao việc qua executor; thường chạy trên worker thread | Cần tách thread hoặc xử lý đồng thời có giới hạn |
| `QueueChannel` | Đưa message vào queue để consumer nhận sau | Cần đệm dữ liệu và tách tốc độ gửi khỏi tốc độ lấy |
| `PublishSubscribeChannel` | Phát mỗi message tới các subscriber | Mỗi phần tử cần kích hoạt nhiều nhánh |
| `nullChannel` | Nhận rồi loại bỏ message | Chủ động kết thúc một nhánh |

`DirectChannel` và `QueueChannel` có ngữ nghĩa point-to-point: một message được một consumer nhận thành công, dù có thể có nhiều consumer đăng ký hoặc cùng lấy từ queue. Cơ chế failover của dispatcher có thể thử subscriber khác khi subscriber trước lỗi.

Với `PublishSubscribeChannel`, mỗi phần tử tách ra được phát tới các subscriber. Chẳng hạn ba phần tử và hai subscriber tạo sáu lượt gọi subscriber trong điều kiện mọi lần giao nhận đều thành công.

`ExecutorChannel` chuyển việc giao nhận qua executor; chính sách của executor có thể khiến thread gửi phải tự chạy công việc khi quá tải. Thứ tự hoàn tất vì vậy phải được xác định theo thiết kế. Các ngữ nghĩa này được mô tả trong [Message Channel Implementations](https://docs.spring.io/spring-integration/reference/6.5/channel/implementations.html).

### 6.1. Thứ tự phát khác với thứ tự hoàn tất

Với một batch `List`, splitter thông thường duyệt theo thứ tự của list. Nếu mọi bước phía sau đồng bộ và chỉ có một đường xử lý, từng phần tử có thể hoàn tất trước khi phần tử tiếp theo được gửi.

Khi có worker song song, tình huống sau là bình thường:

~~~text
Thứ tự phát:        BOOK -> PEN -> BAG
Thứ tự hoàn tất:    PEN  -> BAG -> BOOK
sequenceNumber:     2      3      1
~~~

`sequenceNumber` mô tả vị trí phần tử trong lần tách, không ép scheduler thực thi theo thứ tự đó. Nếu nghiệp vụ yêu cầu tuần tự, cần thiết kế consumer tuần tự hoặc dùng cơ chế sắp xếp phù hợp.

### 6.2. Hệ quả đối với thời gian xử lý

Giả sử một batch gồm 100 phần tử, mỗi phần tử cần khoảng 50 ms cho công việc đồng bộ. Với một đường xử lý tuần tự, riêng phần việc này cần xấp xỉ 5 giây, chưa tính chi phí khác.

Đổi sang queue có thể giúp lời gọi gửi trở về sớm khi còn chỗ chứa. Thời điểm trả về lúc đó cho biết message đã được queue tiếp nhận; nó chưa chứng minh toàn bộ batch đã được xử lý nghiệp vụ thành công.

## 7. Output là QueueChannel: consumer, poller và giới hạn chờ

### 7.1. Poller gắn với endpoint đọc queue

Đặt `QueueChannel` làm output không tự tạo một consumer. Có thể đọc thủ công bằng `receive(...)` như phần 4, hoặc dùng một endpoint có poller.

Ví dụ sau là cấu hình bổ sung độc lập. Đặt các phương thức `@Bean` vào một lớp `@Configuration` có `@EnableIntegration` và import `QueueChannel`, `IntegrationFlow`, `Pollers`:

~~~java
import org.springframework.integration.dsl.Pollers;

@Bean
public QueueChannel queuedItems() {
    return new QueueChannel(32);
}

@Bean
public IntegrationFlow queueingFlow() {
    return IntegrationFlow.from("queuedBatches")
            .splitWith(spec -> spec
                    .applySequence(true)
                    .sendTimeout(500))
            .channel("queuedItems")
            .get();
}

@Bean
public IntegrationFlow consumingFlow() {
    return IntegrationFlow.from("queuedItems")
            .handle(message -> {
                System.out.println(
                        "Đang xử lý: " + message.getPayload());
            }, endpoint -> endpoint.poller(
                    Pollers.fixedDelay(100)
                            .maxMessagesPerPoll(10)))
            .get();
}
~~~

`queuedBatches` là điểm vào của ví dụ này. Consumer ở `consumingFlow` dùng poller để lấy tối đa 10 message trong mỗi lần poll.

Phân biệt vị trí poller:

~~~text
DirectChannel queuedBatches
  -> splitter
  -> QueueChannel queuedItems
  -> endpoint có poller
~~~

Splitter ở đây không cần poller vì input của nó là channel subscribable. Endpoint phía sau cần poller vì input của endpoint đó là queue. Nếu input của chính splitter là một `PollableChannel`, khi đó splitter endpoint mới cần poller.

`splitWith(...)` có từ Spring Integration 6.2; bài dùng API này để cấu hình endpoint. Xem [BaseIntegrationFlowDefinition](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/dsl/BaseIntegrationFlowDefinition.html) và [SplitterSpec](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/dsl/SplitterSpec.html).

### 7.2. sendTimeout chỉ giới hạn thao tác gửi có thể chờ

Trong ví dụ:

~~~java
.sendTimeout(500)
~~~

Giá trị tính bằng millisecond và áp dụng cho thao tác gửi của endpoint khi channel hỗ trợ việc chờ, chẳng hạn queue đã đầy. Đây không phải:

- Deadline cho toàn bộ batch.
- Timeout của một HTTP request trong consumer.
- Cơ chế hủy consumer đang chạy lâu trên `DirectChannel`.
- Giới hạn số message được tách ra.

Nếu queue có capacity 32 và tạm thời không có consumer, một batch 40 phần tử có thể gửi được 32 message rồi mắc tại message tiếp theo. Khi hết thời gian chờ mà queue vẫn đầy, thao tác gửi thất bại; những message đã vào queue không tự biến mất.

Vì vậy, cần đặt capacity theo dung lượng có thể chấp nhận và bảo đảm tốc độ consumer phù hợp. Queue trong bộ nhớ thông thường cũng không bảo đảm dữ liệu còn nguyên sau khi tiến trình dừng.

## 8. Các header đi qua output channel

Với ví dụ `List<String>` ở phần 4 và `applySequence=true`, các message con có thông tin dùng cho việc theo dõi và gom nhóm:

| Header | Giá trị minh họa | Ý nghĩa |
|---|---|---|
| `id` | ID riêng của message con | Phân biệt từng message |
| `correlationId` | ID của message đầu vào splitter | Liên kết các phần tử trong cùng lần tách |
| `sequenceNumber` | `1`, `2`, `3` | Vị trí phần tử |
| `sequenceSize` | `3` | Số phần tử của lần tách |
| `batchId` | `B-42` | Header nghiệp vụ được truyền tiếp |

Các hằng số cho correlation và sequence nằm trong `IntegrationMessageHeaderAccessor`. Với splitter thông thường, `applySequence` mặc định bật. Thay đổi loại output channel không tự thay đổi quy tắc gán các header này.

Phân biệt hai loại định danh:

- `correlationId` phục vụ lần xử lý message và cơ chế gom nhóm.
- `batchId` hoặc `orderId` là định danh nghiệp vụ, hữu ích khi đối soát và thiết kế chống xử lý trùng.

Khi transformer hoặc service activator tạo kết quả cho mỗi phần tử, cần bảo toàn các header mà bước tiếp theo đang dựa vào. Tự dựng message mới và loại bỏ toàn bộ header có thể làm aggregator mất thông tin gom nhóm.

### 8.1. Trường hợp không biết trước số phần tử

Nếu logic split trả `Iterator` hoặc nguồn khác mà framework không xác định được kích thước, `sequenceSize` có thể bằng `0`. Điều đó biểu thị kích thước chưa biết, không biểu thị rằng không có message nào được phát.

Ví dụ, một iterator có thể phát 10.000 phần tử nhưng mỗi message vẫn có `sequenceSize=0`. Aggregator dùng điều kiện đủ số lượng mặc định sẽ cần một chính sách hoàn tất khác.

Khi quyết định tắt `applySequence` để giảm header hoặc phối hợp với một quy tắc gom nhóm riêng, phải thiết kế cơ chế correlation và điều kiện hoàn tất tương ứng. Tham khảo API [AbstractMessageSplitter](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/splitter/AbstractMessageSplitter.html).

## 9. Nối output với router, filter, aggregator và gateway

### 9.1. Router quyết định nhánh cho từng phần tử

Ví dụ một batch chứa mã `DIGITAL-BOOK` và `PEN`:

~~~java
@Bean
public IntegrationFlow routeItems() {
    return IntegrationFlow.from("mixedBatches")
            .split()
            .<String, Boolean>route(
                    code -> code.startsWith("DIGITAL-"),
                    mapping -> mapping
                            .channelMapping(true, "digitalItems")
                            .channelMapping(false, "physicalItems"))
            .get();
}
~~~

Đây là một cấu hình thay thế; cần khai báo và nối consumer cho `digitalItems`, `physicalItems`.

Router nhận từng mã hàng sau khi splitter đã tách. Hai channel nhánh là đích của router; output trực tiếp của splitter là kết nối đến router.

### 9.2. Filter có thể làm thay đổi điều kiện hoàn tất batch

Giả sử splitter phát ba message có `sequenceSize=3`. Một filter loại bỏ `PEN` và chỉ hai message còn lại đi đến aggregator.

Nếu aggregator đang chờ đủ ba phần tử theo sequence, nhóm sẽ chưa hoàn tất. Output channel vẫn hoạt động đúng; vấn đề nằm ở hợp đồng giữa bước lọc và bước gom.

Một số lựa chọn thiết kế:

- Lọc danh sách trước splitter nếu nghiệp vụ chỉ cần gom các phần tử hợp lệ.
- Giữ một kết quả trạng thái cho mỗi phần tử, kể cả phần tử bị từ chối.
- Định nghĩa điều kiện release và xử lý timeout phù hợp nếu số kết quả hợp lệ thay đổi.

Các lựa chọn có ý nghĩa khác nhau. Chẳng hạn một báo cáo cần kết quả cho mọi dòng nhập liệu thường phù hợp với việc trả cả trạng thái thành công và thất bại, để tổng số kết quả vẫn phản ánh batch gốc.

### 9.3. Gateway cần một kết quả tổng hợp nếu hợp đồng là request-reply

Một gateway có phương thức trả `List<String>` không tự thu tất cả message do splitter phát thành một list. Kiểu trả về của phương thức Java không thay thế aggregator.

Nếu yêu cầu là gửi một batch và nhận một kết quả chung:

~~~mermaid
flowchart LR
    G["Gateway request-reply"] --> S["Splitter"]
    S --> C["Channel xử lý từng phần tử"]
    C --> T["Transformer hoặc service activator"]
    T --> A["Aggregator"]
    A --> R["Một reply tổng hợp về gateway"]
~~~

Đoạn flow sau minh họa cấu trúc đó, giả sử gateway gửi vào `requestReplyBatches` và payload là `List<String>`:

~~~java
@Bean
public IntegrationFlow requestReplyBatchFlow() {
    return IntegrationFlow.from("requestReplyBatches")
            .split()
            .transform(String.class, value -> value.toUpperCase(
                    java.util.Locale.ROOT))
            .aggregate()
            .get();
}
~~~

Trong ví dụ không làm mất phần tử này, aggregator có thể dùng correlation và sequence do splitter gán để tạo một message có payload là danh sách kết quả. Vì không có output channel cố định ở cuối, kết quả được gửi theo địa chỉ phản hồi của yêu cầu.

Tài liệu [Aggregator](https://docs.spring.io/spring-integration/reference/6.5/aggregator.html) giải thích cách gom theo correlation và giải phóng nhóm theo sequence. Tài liệu [Messaging Gateways](https://docs.spring.io/spring-integration/reference/6.5/gateway.html) giải thích reply channel tạm mà gateway sử dụng.

Cần giữ địa chỉ phản hồi qua các bước xử lý. Nếu luồng đi qua broker hoặc ranh giới cần tuần tự hóa message, phải thiết kế cách mang thông tin phản hồi phù hợp; một tham chiếu channel cục bộ không tự trở thành địa chỉ phản hồi từ xa.

## 10. Lỗi đầu ra và việc gửi được một phần batch

### 10.1. Channel tồn tại nhưng không có subscriber

Một `DirectChannel` không có subscriber không thể giữ message để chờ consumer xuất hiện. Khi splitter gửi message con tới đó, có thể gặp lỗi dispatch và delivery, với thông báo dạng:

~~~text
Dispatcher has no subscribers
~~~

Đối với channel đồng bộ, kiểm tra endpoint phía sau đã được đăng ký và đang chạy. Đối với queue, kiểm tra consumer hoặc poller đang lấy dữ liệu.

### 10.2. Lỗi đồng bộ và bất đồng bộ

Với `DirectChannel`, exception ở consumer có thể đi ngược stack gọi đến sender. Đặt header `errorChannel` không tự biến mọi exception đồng bộ thành error message.

Khi xử lý qua executor hoặc scheduled poller của Spring Integration, cơ chế error handler có thể xuất bản `ErrorMessage` đến header `errorChannel` hoặc channel lỗi mặc định. Cần xét error handler thực tế của executor, poller và gateway.

Trong cả hai trường hợp, `errorChannel` khác với output channel nhận kết quả thành công. Xem [Error Handling](https://docs.spring.io/spring-integration/reference/6.5/error-handling.html).

### 10.3. Một batch có thể đã có tác động trước khi lỗi xuất hiện

Xét đường xử lý đồng bộ đơn giản, không có recovery tiếp tục xử lý:

~~~text
BOOK -> gửi và xử lý thành công
PEN  -> consumer ném exception
BAG  -> chưa được gửi do vòng xử lý bị ngắt
~~~

Việc request ban đầu thất bại không đủ để kết luận tác động của `BOOK` đã được hoàn tác. Khả năng rollback phụ thuộc transaction và loại tài nguyên tham gia.

Với output queue, có thể xảy ra trường hợp một số message đã được đưa vào queue trước khi queue đầy và thao tác gửi tiếp theo thất bại. Với executor, một số công việc có thể đã được lên lịch hoặc hoàn tất trước khi lỗi ở công việc khác xuất hiện.

Nếu gửi lại toàn bộ batch, phần tử đã thành công có thể được xử lý lần nữa. Một khóa như `(batchId, itemId)` có thể là cơ sở thiết kế idempotency khi phù hợp với nghiệp vụ. Việc kiểm tra và ghi nhận khóa cũng cần gắn với thao tác nghiệp vụ để tránh hai worker cùng xử lý một phần tử.

Từ đó, thiết kế output channel cần đi kèm quyết định rõ ràng: retry từng phần tử hay cả batch, ghi nhận phần tử thất bại ở đâu, và cách xác nhận một batch đã hoàn tất.

## 11. Kiểm thử hành vi tại output channel

Kiểm thử một hàm trả danh sách chỉ chứng minh thuật toán tạo danh sách. Để kiểm tra hợp đồng output channel, cần quan sát message mà splitter thực sự gửi.

Lớp kiểm thử sau dùng `SplitterOutputConfig` ở phần 4. Mỗi test tạo context riêng, vì vậy queue không chứa dữ liệu còn lại từ test trước.

~~~java
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

class SplitterOutputTest {

    @Test
    void sendsOneMessagePerItemWithSequenceHeaders() {
        try (var context =
                     new AnnotationConfigApplicationContext(
                             SplitterOutputConfig.class)) {

            var input = context.getBean("batches", DirectChannel.class);
            var output = context.getBean("lineItems", QueueChannel.class);

            Message<List<String>> request = MessageBuilder
                    .withPayload(List.of("BOOK", "PEN", "BAG"))
                    .setHeader("batchId", "B-42")
                    .build();

            assertTrue(input.send(request));

            List<String> expected = List.of("BOOK", "PEN", "BAG");

            for (int i = 0; i < expected.size(); i++) {
                Message<?> item = output.receive(1000);
                assertNotNull(item);

                assertEquals(expected.get(i), item.getPayload());
                assertEquals(
                        "B-42",
                        item.getHeaders().get("batchId"));
                assertEquals(
                        request.getHeaders().getId(),
                        item.getHeaders().get(
                                IntegrationMessageHeaderAccessor.CORRELATION_ID));
                assertEquals(
                        Integer.valueOf(i + 1),
                        item.getHeaders().get(
                                IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER));
                assertEquals(
                        Integer.valueOf(3),
                        item.getHeaders().get(
                                IntegrationMessageHeaderAccessor.SEQUENCE_SIZE));
            }

            assertNull(output.receive(0));
        }
    }

    @Test
    void configuredOutputChannelTakesPriorityOverReplyChannel() {
        try (var context =
                     new AnnotationConfigApplicationContext(
                             SplitterOutputConfig.class)) {

            var input = context.getBean("batches", DirectChannel.class);
            var output = context.getBean("lineItems", QueueChannel.class);
            var replies = new QueueChannel();

            Message<List<String>> request = MessageBuilder
                    .withPayload(List.of("BOOK"))
                    .setReplyChannel(replies)
                    .build();

            assertTrue(input.send(request));

            Message<?> item = output.receive(1000);
            assertNotNull(item);
            assertEquals("BOOK", item.getPayload());
            assertNull(output.receive(0));
            assertNull(replies.receive(0));
        }
    }

    @Test
    void emptyListProducesNoChildMessage() {
        try (var context =
                     new AnnotationConfigApplicationContext(
                             SplitterOutputConfig.class)) {

            var input = context.getBean("batches", DirectChannel.class);
            var output = context.getBean("lineItems", QueueChannel.class);

            Message<List<String>> request = MessageBuilder
                    .withPayload(List.<String>of())
                    .build();

            assertTrue(input.send(request));
            assertNull(output.receive(0));
        }
    }
}
~~~

Ở đây, `receive(1000)` có timeout để test không chờ vô hạn khi thiếu output. `receive(0)` chỉ kiểm tra tức thời. Việc kiểm tra tức thời là phù hợp vì trong cấu hình cụ thể này splitter đã hoàn thành thao tác gửi đồng bộ trước khi `input.send(...)` trả về.

Khi thay output bằng cơ chế xử lý bất đồng bộ, cần chờ một tín hiệu hoàn tất hoặc kết quả có timeout trước khi kết luận. Không suy ra “không có message dư” chỉ từ một lần kiểm tra tức thời trong khi worker vẫn đang chạy.

Những tình huống nên bổ sung vào bộ kiểm thử của ứng dụng thực tế:

| Tình huống | Điều cần chứng minh |
|---|---|
| Không khai báo output nhưng request có reply channel | Message con đến đúng địa chỉ phản hồi |
| Output queue đầy | Thời gian chờ được giới hạn và ứng dụng nhận diện được việc gửi dở dang |
| Consumer đồng bộ lỗi ở phần tử giữa | Xác định phần tử nào đã xử lý, phần tử nào chưa gửi |
| Có executor song song | Mọi phần tử cần thiết đều có kết quả; không giả định thứ tự hoàn tất |
| Filter trước aggregator | Nhóm vẫn có điều kiện hoàn tất hợp lệ |
| Gateway nhận một batch | Có đúng một kết quả tổng hợp theo hợp đồng |

## 12. Chẩn đoán khi không thấy message sau splitter

Bắt đầu từ cấu trúc flow và lần theo một request cụ thể:

1. Xác nhận request đã đến input của splitter bằng log hoặc interceptor phù hợp.
2. Xác định kết quả split có phần tử hay là collection rỗng, `null`.
3. Tìm output trực tiếp: `.channel(...)` ngay sau splitter hoặc channel ngầm nối tới endpoint kế tiếp.
4. Nếu không có output cố định, kiểm tra địa chỉ `replyChannel` và cơ chế Routing Slip nếu ứng dụng có dùng.
5. Kiểm tra subscriber đối với channel subscribable; kiểm tra độ sâu queue và consumer đối với channel pollable.
6. Quan sát timeout, lỗi dispatch, lỗi consumer và error flow.
7. Nếu đang chờ một kết quả chung, kiểm tra số phần tử thật sự đến aggregator và điều kiện release.

Ví dụ, “gateway không nhận phản hồi” có thể xuất phát từ việc tất cả message con đang nằm trong output queue, hoặc aggregator mới nhận hai trong ba kết quả. Cả hai đều có thể xảy ra dù splitter đã gửi đúng các message con.

Điểm cần nắm để thiết kế luồng là: **splitter tạo các message con; output channel xác định cách bàn giao từng message cho bước tiếp theo**. Từ ranh giới đó, ứng dụng phải xác định rõ ai tiêu thụ message, khi nào một phần tử được coi là hoàn tất và khi nào toàn bộ batch có thể trả kết quả.
