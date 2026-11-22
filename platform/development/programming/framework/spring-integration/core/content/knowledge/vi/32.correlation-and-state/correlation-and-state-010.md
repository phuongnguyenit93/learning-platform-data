# Incomplete group — xử lý nhóm thông điệp chưa đầy đủ

## 1. Mục tiêu và bối cảnh

Trong chương **Correlation và state** của module **SPRING_INTEGRATION_CORE**, incomplete group là tình huống một nhóm đã nhận được một số thông điệp nhưng chưa đáp ứng điều kiện để tổng hợp. Bài học này kết nối `Message`, `MessageChannel`, aggregator endpoint, router và Java DSL để thiết kế cách kết thúc việc chờ một cách có chủ đích.

Sau bài học, bạn có thể:

- Phân biệt “nhóm chưa đủ dữ liệu” với “nhóm đã đóng trong framework”.
- Tìm nguyên nhân khiến nhóm chờ mãi.
- Chọn giữa kết quả một phần, thất bại toàn bộ và thử lại có kiểm soát.
- Cấu hình thời gian chờ, vòng đời metadata và kênh nhận thông điệp bị loại.
- Thiết kế dữ liệu đầu ra để consumer biết còn thiếu gì.
- Lập các tình huống kiểm thử cho thông điệp trùng, đến muộn và ứng dụng khởi động lại.

Giả sử một dịch vụ lấy báo giá vận chuyển từ ba nhà cung cấp **A, B, C**. Mỗi lần hỏi có một khóa yêu cầu riêng. Nếu A và B trả lời nhưng C không trả lời, dịch vụ cần quyết định khi nào kết thúc chờ và báo cho phía gọi điều gì.

## 2. Hiểu đúng về incomplete group

### 2.1. Correlation, release và output là ba quyết định khác nhau

Aggregator giữ thông điệp theo khóa correlation và hỏi `ReleaseStrategy` xem nhóm đã được phép tổng hợp hay chưa. `MessageGroupProcessor` tạo kết quả đầu ra từ nhóm được giải phóng. Correlation mặc định sử dụng header `correlationId`; bạn có thể thay bằng chiến lược riêng. Đây là các vai trò độc lập trong cơ chế aggregator. [Tài liệu Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html)

Trong ví dụ báo giá:

| Quyết định | Câu hỏi nghiệp vụ | Lựa chọn của bài học |
|---|---|---|
| Correlation | Những phản hồi nào thuộc cùng một lần hỏi? | Cùng `requestKey` |
| Release bình thường | Đã có đủ phản hồi cần thiết chưa? | Có cả A, B và C |
| Output | Consumer cần nhận cấu trúc gì? | Báo giá đã nhận, danh sách còn thiếu, cờ đầy đủ |
| Timeout | Chờ đến thời điểm nào? | Hết khoảng im lặng được cấu hình |
| Sau khi đóng | Phản hồi đến muộn được xử lý ra sao? | Chuyển sang kênh theo dõi riêng |

Đặt:

~~~text
E = {A, B, C}       tập nhà cung cấp được kỳ vọng
R = {A, B}          tập nhà cung cấp đã phản hồi
M = E \ R = {C}    tập còn thiếu
~~~

Nhóm đầy đủ khi `M` rỗng. Với hợp đồng yêu cầu đủ cả ba nguồn, nhóm có hai báo giá vẫn là incomplete dù đã có thể trả một kết quả hữu ích cho người dùng.

### 2.2. Complete về vòng đời không bảo đảm đầy đủ về nghiệp vụ

`MessageGroup` có trạng thái hoàn tất và chứa các thông điệp liên quan. Trạng thái vòng đời của nhóm phục vụ quản lý xử lý trong framework. [API MessageGroup](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/store/MessageGroup.html)

Ứng dụng nên mô hình hóa riêng:

- **Đầy đủ dữ liệu:** đã có tất cả nguồn theo hợp đồng.
- **Đã kết thúc chờ:** ứng dụng sẽ không chờ thêm trong lần hỏi này.

Một lần hỏi có thể đã kết thúc chờ nhưng chỉ có hai trên ba báo giá. Vì vậy, tên trường nghiệp vụ như `complete` phải được tính từ các nguồn đã nhận, thay vì suy từ việc aggregator đã phát đầu ra.

### 2.3. Đủ số lượng chưa chắc đủ thành phần

`SimpleSequenceSizeReleaseStrategy` so sánh số thông điệp với kích thước sequence kỳ vọng; chiến lược này không kiểm tra trùng `sequenceNumber`. Không nên coi nó là cơ chế chống thông điệp trùng. [API SimpleSequenceSizeReleaseStrategy](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/aggregator/SimpleSequenceSizeReleaseStrategy.html)

Ví dụ A gửi hai thông điệp khác ID và B gửi một thông điệp:

~~~text
Thông điệp: A1, A2, B1
Số lượng:   3
Nguồn:      {A, B}
Còn thiếu:  {C}
~~~

Nếu dùng `group.size() == 3`, ứng dụng có thể kết luận sai. Trong bài học, release dựa trên tập nguồn duy nhất. Việc loại thông điệp trùng trước khi lưu vẫn cần thiết nếu muốn tránh nhóm phình lớn.

## 3. Vì sao nhóm không bao giờ đầy đủ?

Không nên mặc định rằng mọi incomplete group đều do dịch vụ ngoài chậm.

| Nguyên nhân | Ví dụ | Hướng xử lý |
|---|---|---|
| Nhánh không phản hồi | C không trả lời vì lỗi mạng | Deadline, retry giới hạn hoặc kết quả một phần |
| Filter loại mất phản hồi | Filter bỏ báo giá không hợp lệ nhưng kỳ vọng vẫn là ba nguồn | Ghi nhận kết quả lỗi hoặc điều chỉnh hợp đồng trước khi phát nhánh |
| Router không phát đủ nhánh | Chỉ A và B phù hợp vùng giao hàng | Lưu tập nguồn thực sự được chọn |
| Correlation không nhất quán | A dùng mã đơn, B dùng mã lần hỏi | Chuẩn hóa khóa trước khi gom nhóm |
| Transformer làm mất thông tin | Không giữ header `requestKey` | Bảo toàn hoặc tái tạo khóa một cách xác định |
| Trùng khóa giữa nhiều lần hỏi | Retry dùng lại khóa của lần đã đóng | Đưa phiên bản hoặc lần thử vào khóa |
| Metadata sequence không phù hợp | Kỳ vọng ba phần nhưng upstream chỉ tạo hai phần | Sửa hợp đồng sequence ở nơi tạo nhánh |
| Mất state | Ứng dụng dừng khi nhóm đang nằm trong bộ nhớ | Chọn store phù hợp và thiết kế phục hồi |

Ví dụ, nếu C trả về “không hỗ trợ địa chỉ này”, đó có thể là **một phản hồi hợp lệ với trạng thái không có báo giá**. C đã phản hồi, nhưng không có giá để so sánh. Nếu filter xóa thông điệp đó, hệ thống biến một kết quả đã biết thành sự im lặng.

Trong hệ thống thực tế, nên cân nhắc payload kiểu:

~~~text
BranchOutcome:
  source
  status = SUCCESS | NO_OFFER | FAILED
  quote
  errorCode
~~~

Khi đó, cần tách “đã nhận kết quả của tất cả nhánh” khỏi “tất cả nhánh thành công”. Ví dụ Java phía dưới chỉ dùng báo giá thành công để giữ trọng tâm vào nhóm còn thiếu.

## 4. Chọn chính sách nghiệp vụ trước khi cấu hình

### 4.1. Ba cách kết thúc chờ

| Chính sách | Khi phù hợp | Hợp đồng đầu ra |
|---|---|---|
| Trả phần đã nhận | Trang so sánh có thể hiển thị ít lựa chọn | Nêu rõ nguồn còn thiếu và trạng thái một phần |
| Thất bại toàn bộ | Kết quả thiếu sẽ dẫn đến quyết định sai | Phát kết quả thất bại hoặc sự kiện xử lý tiếp |
| Thử lại nhánh thiếu | Lỗi tạm thời, còn ngân sách thời gian | Có giới hạn số lần thử và khóa lần xử lý rõ ràng |

Đối với ví dụ báo giá, ta chọn **trả phần đã nhận sau timeout**. Một bộ phận khác có thể dùng danh sách thiếu để thống kê lỗi hoặc quyết định thử lại. Việc tổng hợp không tự tạo lệnh retry.

Nếu dữ liệu đang được dùng để quyết toán tài chính, trả phần đã nhận có thể không đáp ứng hợp đồng. Khi đó, nhánh timeout phải tạo một kết quả thất bại có thể theo dõi thay vì công bố số liệu như đã đầy đủ.

### 4.2. Bốn thuộc tính không thay thế nhau

| Thuộc tính | Vai trò |
|---|---|
| `groupTimeout` | Lập thời điểm xử lý timeout cho nhóm |
| `sendPartialResultOnExpiry` | Chọn tổng hợp phần đã có khi xử lý hết hạn |
| `expireGroupsUponCompletion` | Chọn xóa toàn bộ nhóm sau release bình thường |
| `expireGroupsUponTimeout` | Chọn xóa toàn bộ nhóm khi xử lý timeout |

Với đường timeout mà release vẫn chưa đạt, `sendPartialResultOnExpiry(true)` cho phép tổng hợp phần đã nhận; `false` đưa phần đó sang đường discard. Chỉ bật cờ này không tạo bộ đếm thời gian. [Mã nguồn xử lý expiry](https://raw.githubusercontent.com/spring-projects/spring-integration/v6.5.0/spring-integration-core/src/main/java/org/springframework/integration/aggregator/AbstractCorrelatingMessageHandler.java)

`expireGroupsUponCompletion(false)` giúp giữ metadata nhóm đã đóng sau release bình thường. Thông điệp của nhóm được dọn khỏi nhóm đã xử lý. [API AggregatingMessageHandler](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/aggregator/AggregatingMessageHandler.html), [mã nguồn afterRelease](https://raw.githubusercontent.com/spring-projects/spring-integration/v6.5.0/spring-integration-core/src/main/java/org/springframework/integration/aggregator/AggregatingMessageHandler.java)

Tương tự, chọn `expireGroupsUponTimeout(false)` để giữ dấu vết nhóm đã đóng sau timeout. Nếu xóa sạch metadata, một thông điệp cùng khóa có thể tạo nhóm mới. Mặc định của cờ timeout là `true`, nên cần cấu hình tường minh khi muốn chặn trường hợp đó. [API AbstractCorrelatingMessageHandler](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/aggregator/AbstractCorrelatingMessageHandler.html)

## 5. Ví dụ Java DSL: báo giá đầy đủ và báo giá một phần

### 5.1. Hợp đồng của ví dụ

Ví dụ dùng Java 17 và API có trong Spring Integration 6.5.0. Cần dependency `org.springframework.integration:spring-integration-core` cùng các dependency Spring tương thích; trong dự án Spring Boot, dùng quản lý phiên bản của Boot.

Các giả định:

- Mọi yêu cầu đều hỏi đúng ba nguồn A, B, C.
- Header `requestKey` nhận diện một lần hỏi, có phạm vi tenant và lần thử.
- Các phản hồi đi vào flow có payload `QuoteReply`.
- Nếu một nguồn gửi nhiều giá trong một lần hỏi, ví dụ lấy giá nhỏ nhất. Đây là quy tắc minh họa; hệ thống có cập nhật giá cần hợp đồng phiên bản riêng.
- Timeout hai giây là giá trị dùng để quan sát ví dụ, không phải khuyến nghị vận hành.

Sơ đồ đường đi:

~~~mermaid
flowchart TD
    I["quoteReplies: Message có requestKey"] --> A["Aggregator và MessageGroupStore"]
    A -->|Đủ A, B, C| O["Tạo QuoteBatch"]
    A -->|Timeout: chỉ có A, B| O
    O --> R{"QuoteBatch.complete?"}
    R -->|true| C["completeQuotes"]
    R -->|false| P["partialQuotes"]
    A -->|Cùng khóa đã đóng| D["discardedReplies"]
~~~

`outputProcessor` cho phép tạo payload đầu ra riêng thay cho collection payload mặc định. Ở đây, cùng một processor phục vụ cả release đầy đủ và release một phần. [API AggregatorSpec](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/dsl/AggregatorSpec.html)

### 5.2. Cấu hình và chương trình minh họa

~~~java
import java.math.BigDecimal;
import java.time.Duration;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.stream.Collectors;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.store.MessageGroup;
import org.springframework.integration.store.MessageGroupStore;
import org.springframework.integration.store.SimpleMessageStore;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@Configuration
@EnableIntegration
public class IncompleteGroupDemo {

    private static final Set<String> EXPECTED = Set.of("A", "B", "C");
    private static final String REQUEST_KEY = "requestKey";

    public record QuoteReply(String supplier, BigDecimal price) {
        public QuoteReply {
            if (!EXPECTED.contains(supplier)) {
                throw new IllegalArgumentException("Unknown supplier: " + supplier);
            }
            if (price == null || price.signum() < 0) {
                throw new IllegalArgumentException("Price must be non-negative");
            }
        }
    }

    public record QuoteBatch(
            String requestKey,
            boolean complete,
            Set<String> missingSuppliers,
            Map<String, BigDecimal> quotes) {
    }

    @Bean
    public DirectChannel quoteReplies() {
        return new DirectChannel();
    }

    @Bean
    public QueueChannel completeQuotes() {
        return new QueueChannel();
    }

    @Bean
    public QueueChannel partialQuotes() {
        return new QueueChannel();
    }

    @Bean
    public QueueChannel discardedReplies() {
        return new QueueChannel();
    }

    @Bean
    public MessageGroupStore quoteGroupStore() {
        return new SimpleMessageStore();
    }

    @Bean
    public IntegrationFlow quoteFlow(MessageGroupStore quoteGroupStore) {
        return IntegrationFlow.from(quoteReplies())
                .aggregate(spec -> spec
                        .messageStore(quoteGroupStore)
                        .correlationStrategy(message -> {
                            String key = message.getHeaders()
                                    .get(REQUEST_KEY, String.class);
                            if (key == null || key.isBlank()) {
                                throw new IllegalArgumentException(
                                        "Missing requestKey");
                            }
                            return key;
                        })
                        .releaseStrategy(group ->
                                receivedSuppliers(group).containsAll(EXPECTED))
                        .groupTimeout(2_000L)
                        .sendPartialResultOnExpiry(true)
                        .expireGroupsUponCompletion(false)
                        .expireGroupsUponTimeout(false)
                        .minimumTimeoutForEmptyGroups(60_000L)
                        .expireTimeout(30_000L)
                        .expireDuration(Duration.ofSeconds(5))
                        .discardChannel(discardedReplies())
                        .outputProcessor(IncompleteGroupDemo::toBatch))
                .<QuoteBatch, Boolean>route(
                        QuoteBatch::complete,
                        mapping -> mapping
                                .channelMapping(true, "completeQuotes")
                                .channelMapping(false, "partialQuotes"))
                .get();
    }

    private static Set<String> receivedSuppliers(MessageGroup group) {
        return group.getMessages().stream()
                .map(message -> (QuoteReply) message.getPayload())
                .map(QuoteReply::supplier)
                .collect(Collectors.toSet());
    }

    private static QuoteBatch toBatch(MessageGroup group) {
        Map<String, BigDecimal> quotes = new TreeMap<>();
        for (Message<?> message : group.getMessages()) {
            QuoteReply reply = (QuoteReply) message.getPayload();
            quotes.merge(reply.supplier(), reply.price(), BigDecimal::min);
        }

        Set<String> missing = new TreeSet<>(EXPECTED);
        missing.removeAll(quotes.keySet());

        String requestKey = group.getOne().getHeaders()
                .get(REQUEST_KEY, String.class);

        return new QuoteBatch(
                requestKey,
                missing.isEmpty(),
                Set.copyOf(missing),
                Map.copyOf(quotes));
    }

    private static Message<QuoteReply> reply(
            String requestKey, String supplier, String price) {
        return MessageBuilder
                .withPayload(new QuoteReply(supplier, new BigDecimal(price)))
                .setHeader(REQUEST_KEY, requestKey)
                .build();
    }

    private static void show(String label, Message<?> message) {
        if (message == null) {
            throw new IllegalStateException("No message for: " + label);
        }
        System.out.println(label + ": " + message.getPayload());
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(
                             IncompleteGroupDemo.class)) {

            DirectChannel input =
                    context.getBean("quoteReplies", DirectChannel.class);
            QueueChannel full =
                    context.getBean("completeQuotes", QueueChannel.class);
            QueueChannel partial =
                    context.getBean("partialQuotes", QueueChannel.class);
            QueueChannel discarded =
                    context.getBean("discardedReplies", QueueChannel.class);

            String fullKey = "tenant-01:req-001:attempt-1";
            input.send(reply(fullKey, "A", "30000"));
            input.send(reply(fullKey, "B", "28000"));
            input.send(reply(fullKey, "C", "32000"));
            show("Full", full.receive(1_000));

            String partialKey = "tenant-01:req-002:attempt-1";
            input.send(reply(partialKey, "A", "30000"));
            input.send(reply(partialKey, "B", "28000"));
            show("Partial", partial.receive(5_000));

            input.send(reply(partialKey, "C", "32000"));
            show("Late", discarded.receive(1_000));
        }
    }
}
~~~

Các `QueueChannel` ở đây là điểm quan sát bằng `receive`. Trong ứng dụng thật, cần consumer cho từng đường kết quả và giới hạn dung lượng phù hợp với tải.

### 5.3. Diễn giải kết quả

Kỳ vọng quan sát:

| Nhãn | Payload đáng chú ý | Lý do |
|---|---|---|
| `Full` | `complete=true`, không thiếu nguồn nào | A, B, C đã phản hồi |
| `Partial` | `complete=false`, `missingSuppliers={C}` | Timeout khi chỉ có A, B |
| `Late` | `QuoteReply` của C | Nhóm cùng khóa đã đóng và metadata còn được giữ |

Thứ tự in phần tử trong các collection bất biến không phải hợp đồng của ví dụ.

Bộ gom không cần đoán “đang được gọi vì timeout hay vì nhận đủ”. Processor tính `complete` từ tập nguồn có mặt. Do release bình thường đòi đủ A, B, C, một kết quả thiếu nguồn của ví dụ thể hiện đường kết thúc chờ khi còn thiếu dữ liệu.

Nếu thay chiến lược bằng quorum hai trên ba nguồn, kết quả không đủ cả ba có thể được phát theo release bình thường. Khi đó, nên bổ sung trường riêng như `completionPolicy`; không suy nguyên nhân phát kết quả chỉ từ cờ `complete`.

Các giá trị `expireTimeout` và `expireDuration` cấu hình việc quét nhóm cũ, hỗ trợ dọn state ngoài các lịch timeout đang sống. `groupTimeout`, `minimumTimeoutForEmptyGroups` và các tùy chọn này có trong API DSL được sử dụng ở ví dụ. [API CorrelationHandlerSpec](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/dsl/CorrelationHandlerSpec.html)

## 6. Phân biệt các loại thời gian chờ

### 6.1. Khoảng im lặng sau thông điệp gần nhất

Với `groupTimeout(2_000L)`, lịch timeout được tính lại khi có thông điệp mới mà nhóm vẫn chưa release. Vì vậy, đây là khoảng chờ theo hoạt động của nhóm, không bảo đảm toàn bộ yêu cầu kết thúc sau hai giây. [Tài liệu Group Timeout](https://docs.spring.io/spring-integration/reference/aggregator.html#_aggregator_and_group_timeout)

~~~text
t = 0,0 s   A đến
t = 1,5 s   B đến
t ≈ 3,5 s   xử lý timeout nếu C chưa đến
~~~

Hệ quả thiết kế: một nguồn gửi liên tục các phản hồi trùng có thể kéo dài việc chờ. Khử trùng trước aggregator giúp giảm vấn đề này; deadline tuyệt đối còn cần thiết nếu hợp đồng quy định một hạn chót.

### 6.2. Hạn chót gắn với thời điểm tạo nhóm

Thay dòng `groupTimeout(2_000L)` bằng:

~~~java
.groupTimeout(group ->
        new java.util.Date(group.getTimestamp() + 2_000L))
~~~

Hàm timeout có thể trả `Date` để chỉ một thời điểm tuyệt đối. Không cấu hình đồng thời hai cách trên cùng endpoint. [API groupTimeout](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/CorrelationHandlerSpec.html#groupTimeout(java.util.function.Function))

Điểm bắt đầu ở đây là thời điểm tạo **nhóm**, có thể muộn hơn thời điểm người dùng gửi yêu cầu. Nếu yêu cầu được tạo lúc 10:00:00 nhưng phản hồi đầu tiên chỉ đến lúc 10:00:04, hạn tính theo nhóm không tự bao phủ bốn giây trước đó.

Nếu hợp đồng là “trả lời trong năm giây từ lúc nhận yêu cầu”, hãy ghi `deadlineAt` ngay ở đầu quy trình, giữ nhất quán qua các nhánh và dùng mốc đó cho chính sách kết thúc.

### 6.3. Trường hợp không có phản hồi nào

Nếu cả A, B, C đều im lặng, flow chỉ nhận phản hồi chưa có thông điệp nào để tạo nhóm. Không thể trông chờ một lịch của nhóm chưa tồn tại sẽ phát kết quả rỗng.

Một thiết kế đầy đủ cần theo dõi yêu cầu từ lúc bắt đầu:

1. Ghi nhận yêu cầu đang chờ cùng tập nguồn kỳ vọng và deadline.
2. Gửi các nhánh.
3. Cập nhật kết quả theo từng phản hồi.
4. Đến deadline, kết thúc yêu cầu kể cả khi chưa có phản hồi.
5. Bảo đảm đường nhận đủ và đường deadline chỉ công bố một kết quả cuối.

Có thể dùng một bộ điều phối deadline riêng và kho trạng thái yêu cầu. Nếu dùng thông điệp khởi tạo để tạo nhóm, phải phân biệt nó với phản hồi nguồn; không được để nó tăng số lượng phản hồi nghiệp vụ.

### 6.4. Timeout của gateway là một giới hạn khác

Thời gian chờ reply của gateway phục vụ phía gọi; timeout của aggregator phục vụ nhóm. Nếu phía gọi đã ngừng chờ trước khi nhóm phát kết quả, kết quả một phần không tự đến được caller ban đầu.

Khi tích hợp gateway, cần thống nhất deadline, đường nhận kết quả và cách tra cứu trạng thái. Luồng đồng bộ cần đủ ngân sách cho tổng hợp và xử lý tiếp. Luồng bất đồng bộ có thể trả mã yêu cầu rồi cho phép truy vấn hoặc nhận sự kiện kết quả.

## 7. Nhóm đã đóng, thông điệp đến muộn và dọn state

### 7.1. Vì sao phải giữ một dấu vết?

Sau khi lần hỏi `req-002:attempt-1` đã trả kết quả thiếu C, phản hồi C tới sau đó không được âm thầm thay đổi kết quả đã công bố.

Trong ví dụ, cả hai cờ xóa nhóm đều đặt `false`. Metadata giữ lại đóng vai trò dấu vết rằng khóa này đã kết thúc. Đường `discardedReplies` giúp lưu bằng chứng thay vì bỏ qua phản hồi muộn.

Nếu metadata đã được dọn hoặc bị mất do restart với store trong bộ nhớ, cùng khóa có thể được tiếp nhận như một nhóm mới. Chính sách xử lý muộn vì vậy có một khoảng hiệu lực, không phải bảo đảm vĩnh viễn.

Các lựa chọn nghiệp vụ cho phản hồi muộn gồm:

- Ghi nhận rồi bỏ qua.
- Phát một sự kiện điều chỉnh có phiên bản mới.
- Lưu cho phân tích chất lượng nhà cung cấp.
- Gắn với một quy trình đối soát riêng.

Không đưa phản hồi của lần thử cũ vào lần thử mới chỉ vì cùng mã đơn hàng.

### 7.2. Giữ metadata cũng tiêu tốn tài nguyên

Giữ mọi khóa đã đóng mãi mãi khiến số nhóm tăng theo tổng số yêu cầu từng xử lý. Cần xác định khoảng thời gian còn chấp nhận thông điệp muộn, sau đó dọn metadata.

Trong ví dụ, `minimumTimeoutForEmptyGroups(60_000L)` đặt khoảng tối thiểu cho việc giữ nhóm rỗng theo cơ chế dọn tương ứng. Lịch quét định kỳ có thể làm thời điểm dọn thực tế muộn hơn mốc tối thiểu. Đây không phải độ chính xác thời gian thực. [API giữ nhóm rỗng](https://docs.spring.io/spring-integration/api/org/springframework/integration/aggregator/AbstractCorrelatingMessageHandler.html#setMinimumTimeoutForEmptyGroups(long))

Ước lượng thiết kế đơn giản:

~~~text
Số dấu vết đang giữ ≈ số yêu cầu kết thúc mỗi giây × thời gian giữ
~~~

Với 500 yêu cầu mỗi giây và giữ 10 phút, riêng dấu vết có thể vào khoảng 300.000 nhóm. Còn phải tính kích thước khóa, metadata, index và chi phí của store.

### 7.3. Reaper và lịch timeout riêng cho nhóm

`MessageGroupStoreReaper` cung cấp phương thức `run()` để quét các nhóm quá ngưỡng trong store. Tạo bean reaper chưa đủ để nó tự quét định kỳ; cần cơ chế gọi `run()` theo lịch. [API MessageGroupStoreReaper](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/store/MessageGroupStoreReaper.html)

Nếu thay cách purge trong ví dụ bằng reaper, hãy thiết kế rõ:

- Store nào thuộc quyền quản lý của reaper.
- Ngưỡng quá hạn của nhóm đang chờ.
- Khoảng giữ metadata của nhóm đã đóng.
- Chu kỳ quét và độ trễ được chấp nhận.

Tránh gắn nhiều cơ chế dọn có ngưỡng mâu thuẫn. Ví dụ, một bộ quét kết thúc nhóm sau một giây sẽ làm chính sách chờ hai giây không còn đúng như người đọc cấu hình mong đợi.

## 8. Restart, xử lý đồng thời và tính tin cậy

### 8.1. Lưu bền không đồng nghĩa phục hồi toàn bộ quy trình

`SimpleMessageStore` lưu trong bộ nhớ. Spring Integration có các lựa chọn store dùng JDBC, Redis và MongoDB cho những nhu cầu lưu trữ khác. Việc chọn store là một phần của thiết kế độ bền dữ liệu. [Tài liệu Message Store](https://docs.spring.io/spring-integration/reference/message-store.html)

Khi chuyển sang lưu bền, cần trả lời thêm:

- Payload và header nào được lưu, khôi phục theo định dạng nào?
- Ai tiếp tục xử lý các nhóm còn chờ sau restart?
- Các lịch timeout được thiết lập lại hoặc thay thế bằng quét như thế nào?
- Điều gì xảy ra nếu ứng dụng dừng giữa lúc gửi kết quả và ghi trạng thái hoàn tất?
- Consumer chống việc xử lý lại cùng một kết quả bằng cách nào?

Một kho lưu bền không tự biến thao tác “đọc nhóm, phát kết quả, cập nhật kho và gọi dịch vụ ngoài” thành một giao dịch nguyên tử.

### 8.2. Hai loại khóa cần phân biệt

**Khóa correlation** xác định tập thông điệp thuộc cùng lần xử lý. **Khóa đồng bộ hóa** bảo vệ thao tác đồng thời lên state.

Với nhiều instance cùng thao tác lên một store, thiết kế phải bảo đảm việc kiểm tra và đóng cùng nhóm không tạo nhiều kết quả cuối. Cần đánh giá cơ chế khóa, giao dịch và cách chia sẻ store phù hợp với triển khai.

Dù cơ chế đồng bộ bảo vệ tốt state, consumer vẫn nên có hợp đồng idempotency cho kết quả, chẳng hạn khóa `requestKey + resultVersion`. Điều này xử lý được trường hợp phát lại khi khôi phục hoặc gửi lại sau lỗi mạng.

### 8.3. Không dùng một không gian state lẫn lộn

Mỗi aggregator nên có phạm vi store và khóa rõ ràng. Tài liệu cảnh báo việc dùng chung một `MessageGroupStore` cho nhiều endpoint có xử lý expiry vì callback có thể tác động nhầm nhóm. Khi dùng chung hạ tầng vật lý, hãy tách vùng lưu trữ phù hợp với implementation. [Tài liệu quản lý state của Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html)

Trong thiết kế báo giá, khóa còn cần phân biệt tenant, yêu cầu và lần thử. Ví dụ:

~~~text
tenant-01 / req-002 / attempt-1
tenant-01 / req-002 / attempt-2
tenant-02 / req-002 / attempt-1
~~~

Nếu các thành phần khóa là chuỗi tùy ý, dùng cách mã hóa hoặc cấu trúc khóa không nhập nhằng; không chỉ nối chuỗi bằng dấu phân cách có thể xuất hiện trong dữ liệu.

### 8.4. Timeout không phải ngoại lệ của luồng

Nhóm thiếu dữ liệu đến hạn có thể là một kết quả nghiệp vụ được dự kiến. Trong ví dụ, nó đi qua `partialQuotes`. `errorChannel` dành cho lỗi xử lý; `discardedReplies` dành cho thông điệp bị loại theo chính sách.

Lỗi của đoạn chạy đồng bộ có thể trả về thread người gửi. Lỗi phát sinh trên scheduler hoặc executor cần đường xử lý lỗi tương ứng; không nên giả định caller đang chờ vẫn bắt được ngoại lệ đó. [Tài liệu Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)

Khi processor hoặc consumer của kết quả timeout gặp lỗi, cần ghi đủ khóa yêu cầu, giữ bằng chứng và xác định có thử lại hay không. Không công bố thành công chỉ vì scheduler đã kích hoạt.

## 9. Kiểm thử hành vi cần quan sát

Ví dụ `main` minh họa ba đường cơ bản. Khi triển khai, nên kiểm thử ở mức hợp đồng dữ liệu và hành vi của flow.

| Tình huống | Kỳ vọng |
|---|---|
| Nhận A, B, C trong thời gian chờ | Một `QuoteBatch` đầy đủ |
| Chỉ nhận A, B | Một kết quả thiếu C sau timeout |
| Chỉ nhận A | Kết quả thiếu B và C |
| Nhận A, A, B | Chưa release bình thường; C vẫn thiếu |
| Nhận C sau khi kết quả một phần đã phát | Đi vào discard khi metadata còn giữ |
| Nhận phản hồi cũ sau khi metadata bị dọn | Kiểm tra chính sách nhận lại và idempotency |
| Hai `requestKey` xen kẽ | Không trộn nguồn giữa các yêu cầu |
| Phản hồi thiếu `requestKey` | Bị từ chối với lỗi rõ ràng |
| Không có bất kỳ phản hồi nào | Bộ điều phối yêu cầu xử lý deadline |
| Hai thread đưa phần cuối và timeout gần nhau | Không tạo hai kết quả cuối thành công |
| Restart khi nhóm còn chờ | Phục hồi theo store và chính sách đã chọn |
| Đường nhận kết quả gặp lỗi | Có bằng chứng lỗi và chính sách phục hồi |

Một kiểm tra đơn thuần rằng collection có hai phần tử chưa đủ cho đường partial. Phải kiểm tra ít nhất khóa yêu cầu, `complete=false`, đúng `missingSuppliers` và đúng các nguồn đã nhận.

Để kiểm thử timeout:

- Đặt thời gian kiểm thử ngắn nhưng có dư địa cho scheduler trên CI.
- Chờ kết quả bằng cơ chế có giới hạn thời gian; tránh `Thread.sleep` cố định rồi phỏng đoán.
- Kiểm tra thêm rằng không có kết quả đầy đủ phát sinh sau một kết quả một phần đã chốt.
- Với race condition, lặp tình huống có kiểm soát và kiểm tra số kết quả được công bố.
- Với restart, dùng loại store tương ứng triển khai; store trong bộ nhớ không chứng minh được khả năng phục hồi state.

## 10. Chẩn đoán một nhóm bị treo

Khi nhận phản ánh “aggregator không trả kết quả”, điều tra theo thứ tự:

1. **Xác định một lần hỏi cụ thể.** Lấy tenant, `requestKey`, lần thử và deadline.
2. **Đối chiếu tập kỳ vọng.** Những nhánh nào thực sự được phát? Có nhánh bị router bỏ qua không?
3. **Theo dấu từng phản hồi.** Nhánh nào chưa về, bị filter loại hoặc mất khóa correlation?
4. **Kiểm tra điều kiện release.** Nó đang kiểm tra số lượng, nguồn duy nhất hay trạng thái từng nhánh?
5. **Kiểm tra lịch thời gian.** Đang dùng khoảng im lặng hay deadline? Có thông điệp trùng kéo dài lịch không?
6. **Kiểm tra kết quả và state sau đóng.** Nhóm còn chờ, đã phát một phần, đã discard hay đã bị xóa?
7. **Kiểm tra nơi nhận kết quả.** Có consumer, lỗi xử lý hoặc caller đã hết thời gian chờ không?

Các chỉ số hữu ích gồm số nhóm còn chờ, tuổi nhóm lâu nhất, tỷ lệ kết quả một phần, nguồn thường xuyên vắng mặt, lượng thông điệp đến muộn và số metadata đang được giữ.

Không đưa `requestKey` có số lượng giá trị rất lớn thành nhãn metric. Dùng khóa này trong log hoặc trace; metric nên dùng các chiều hữu hạn như nhà cung cấp, loại kết quả và môi trường.

## 11. Bài thực hành

Mở rộng ví dụ theo ba bước:

1. Thay tập A, B, C cố định bằng tập nguồn được chọn cho từng yêu cầu. Bảo đảm mọi phản hồi cùng nhóm dùng cùng hợp đồng kỳ vọng.
2. Thêm `BranchOutcome` để một phản hồi `NO_OFFER` vẫn được tính là nhánh đã hoàn tất. Phân biệt số nhánh đã phản hồi và số báo giá có thể dùng.
3. Thiết kế nhánh thử lại cho nguồn thiếu với ngân sách thời gian và khóa lần thử mới. Quy định rõ phản hồi của lần thử trước sẽ đi đâu.

Bài làm đạt yêu cầu khi giải thích được kết quả của các trường hợp: A phản hồi hai lần, B báo không có giá, C đến sau deadline; và khi không nguồn nào phản hồi. Mỗi trường hợp phải chỉ rõ dữ liệu được công bố, thời điểm kết thúc chờ, state được giữ và cách xử lý thông điệp tiếp theo.
