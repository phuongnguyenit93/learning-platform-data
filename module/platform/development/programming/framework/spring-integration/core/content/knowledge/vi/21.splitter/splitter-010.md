# Splitter và downstream aggregator

## Mục tiêu bài học

Trong chương **Splitter** của module **SPRING_INTEGRATION_CORE**, bài học này nối thao tác tách một thông điệp thành nhiều phần với thao tác gom kết quả ở phía sau. Trọng tâm là thiết kế một luồng thông điệp hoàn chỉnh bằng `Message`, `MessageChannel`, endpoint và Java DSL, đồng thời xác định ảnh hưởng của transformer, router, filter và xử lý lỗi đến việc hoàn tất nhóm.

Sau bài học, bạn có thể:

- Giải thích vai trò của `correlationId`, `sequenceNumber` và `sequenceSize`.
- Viết luồng `split → xử lý từng phần → aggregate` bằng Java DSL.
- Phân biệt điều kiện gom đủ với phép tính tạo kết quả tổng hợp.
- Xử lý phần tử bị từ chối, kết quả đến muộn, timeout và dữ liệu đầu vào rỗng.
- Thiết kế kiểm thử cho tính đầy đủ, cách ly nhóm và thứ tự kết quả.

Ví dụ dùng Java 17 và API của Spring Integration 6.5. Dự án cần quản lý phiên bản dependency bằng BOM phù hợp; các đoạn mã không yêu cầu chọn một phiên bản Spring Boot cụ thể. Cấu hình chính là một ví dụ chạy trong Spring Context, còn các đoạn mở rộng được ghi rõ vị trí thay thế.

## 1. Vì sao splitter thường đi cùng aggregator?

Giả sử một đơn hàng có ba dòng sản phẩm. Hệ thống cần tính tiền từng dòng rồi trả về một bảng kết quả cho cả đơn:

~~~text
Đơn hàng O-100
  Dòng 1: 2 × 120000
  Dòng 2: 3 ×  50000
  Dòng 3: 1 ×  70000

Kết quả:
  Dòng 1: 240000
  Dòng 2: 150000
  Dòng 3:  70000
  Tổng:   460000
~~~

Splitter quyết định các đơn vị công việc. Các endpoint trung gian xử lý từng đơn vị. Aggregator tập hợp những kết quả liên quan trước khi tạo phản hồi cấp đơn hàng.

~~~mermaid
flowchart LR
    A["Message chứa Order"] --> S["Splitter"]
    S --> P1["Message dòng 1"]
    S --> P2["Message dòng 2"]
    S --> P3["Message dòng 3"]
    P1 --> W["Xử lý từng dòng"]
    P2 --> W
    P3 --> W
    W --> G["Aggregator: nhóm và chờ đủ"]
    G --> R["Message chứa OrderSummary"]
~~~

Trong bài này, **downstream aggregator** là aggregator nằm sau splitter trong đường đi của message; giữa hai endpoint có thể có nhiều channel và bước xử lý.

| Thành phần | Câu hỏi cần trả lời | Ví dụ trong luồng đơn hàng |
|---|---|---|
| Splitter | Một yêu cầu được chia thành những phần nào? | Một `LineTask` cho mỗi dòng hàng |
| Transformer hoặc service activator | Mỗi phần tạo ra kết quả gì? | Một `LineResult` |
| Correlation strategy | Kết quả này thuộc nhóm nào? | Nhóm của một lần tách đơn hàng |
| Release strategy | Khi nào được tạo kết quả tổng hợp? | Khi đã nhận kết quả của tất cả dòng |
| Output processor | Nhóm kết quả được chuyển thành gì? | `OrderSummary` chứa danh sách và tổng tiền |
| Message group store | Dữ liệu chờ gom nằm ở đâu? | Bộ nhớ của ứng dụng trong ví dụ |

Aggregator lưu trạng thái của nhóm, vì vậy vòng đời của nhóm là một phần của thiết kế luồng. Khái niệm gom nhóm và tạo kết quả được trình bày trong [tài liệu Aggregator của Spring Integration](https://docs.spring.io/spring-integration/reference/aggregator.html).

Kết quả tổng hợp không nhất thiết khôi phục payload ban đầu. Bạn có thể gom ba dòng hàng thành một báo cáo, một số tổng, hoặc một đối tượng có cả thành công lẫn thất bại.

## 2. Hợp đồng thông điệp giữa splitter và aggregator

### 2.1. Ba header cần giữ

Với một collection có kích thước xác định, splitter bật `applySequence` sẽ cung cấp thông tin chuỗi cho các message con:

| Header | Ý nghĩa | Ví dụ |
|---|---|---|
| `correlationId` | Nhận diện nhóm của lần tách hiện tại | `C-100` |
| `sequenceNumber` | Vị trí của phần tử, bắt đầu từ 1 | `1`, `2`, `3` |
| `sequenceSize` | Tổng số phần tử của chuỗi | `3` |

Splitter bật hành vi này theo mặc định; ví dụ bên dưới vẫn cấu hình tường minh để thể hiện hợp đồng. Xem [cấu hình sequence của splitter](https://docs.spring.io/spring-integration/reference/6.5/aggregator.html) và [API SplitterSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/SplitterSpec.html).

Ví dụ ở một cấp tách, khi message đầu vào có `id = C-100`:

~~~text
Message gốc: id=C-100, payload=Order(O-100, 3 dòng)

Message con 1:
  id=M-1, correlationId=C-100, sequenceNumber=1, sequenceSize=3

Message con 2:
  id=M-2, correlationId=C-100, sequenceNumber=2, sequenceSize=3

Message con 3:
  id=M-3, correlationId=C-100, sequenceNumber=3, sequenceSize=3
~~~

Các message con có danh tính riêng. `orderId` là khóa nghiệp vụ; `correlationId` là khóa liên kết message cho bước gom hiện tại. Đừng đặt giả định hai giá trị này luôn giống nhau.

### 2.2. Giữ đủ thông tin khi thay payload

Sau khi tính tiền dòng hàng, payload chuyển từ `LineTask` sang `LineResult`. Những header liên kết nhóm vẫn cần đi tiếp:

~~~text
LineTask + headers chuỗi
            |
            v
        Transformer
            |
            v
LineResult + headers chuỗi
~~~

Trong Java DSL, các động từ `split`, `transform` và `aggregate` tạo các endpoint tương ứng. Transformer trả payload là cách thuận tiện để dùng cơ chế tạo reply của framework. Xem [DSL Basics](https://docs.spring.io/spring-integration/reference/dsl/java-basics.html).

Nếu tự xây message mới, hãy chủ động sao chép các header cần truyền:

~~~java
Message<LineResult> resultMessage = MessageBuilder
        .withPayload(result)
        .copyHeaders(partMessage.getHeaders())
        .build();
~~~

Đoạn trên minh họa việc tạo message, với `result` và `partMessage` do bước xử lý cung cấp. Nó cần `org.springframework.messaging.Message` và `org.springframework.messaging.support.MessageBuilder`.

Các header hệ thống `id` và `timestamp` của message đầu ra do builder quản lý. Mục đích là giữ metadata nghiệp vụ và metadata liên kết chuỗi, không ép message mới dùng danh tính của message cũ.

Khi message đi qua broker hoặc ranh giới tiến trình, hãy kiểm tra header mapping, kiểu dữ liệu sau giải mã và khóa correlation thực tế. Một flow đúng trong bộ nhớ chưa chứng minh được hợp đồng truyền qua hệ thống ngoài.

## 3. Gom đúng nhóm và biết khi nào đủ là hai việc riêng

Aggregator thường cần ba quyết định độc lập:

1. **Correlation:** chọn khóa nhóm từ message.
2. **Release:** xác định nhóm đã sẵn sàng hay chưa.
3. **Aggregation:** tính payload kết quả khi nhóm được giải phóng.

Ở cấu hình mặc định, khóa nhóm lấy từ `correlationId`. Với chuỗi có kích thước xác định, `SimpleSequenceSizeReleaseStrategy` so sánh số message đã tích lũy với kích thước dự kiến. Strategy này không kiểm tra trùng `sequenceNumber`. Vì vậy, “đã đủ số lượng” chỉ có ý nghĩa khi luồng bảo đảm mỗi phần tạo đúng một kết quả. Xem [SimpleSequenceSizeReleaseStrategy](https://docs.spring.io/spring-integration/api/org/springframework/integration/aggregator/SimpleSequenceSizeReleaseStrategy.html).

Với nhóm ba phần, trường hợp bình thường là:

~~~text
Nhận phần 2: nhóm có 1/3 → chờ
Nhận phần 1: nhóm có 2/3 → chờ
Nhận phần 3: nhóm có 3/3 → tạo OrderSummary
~~~

Việc phần 3 đã đến không tự chứng minh các phần 1 và 2 đều có mặt. Đây là lý do không nên dùng quy tắc “nhận message có sequenceNumber bằng sequenceSize thì release” trong luồng có thể xử lý song song.

Nếu chỉ cấu hình `.aggregate()`, output processor mặc định tạo một message chứa danh sách payload của nhóm. Khi cần một hợp đồng trả về rõ ràng, có thể cung cấp output processor tạo đối tượng nghiệp vụ. Xem [DefaultAggregatingMessageGroupProcessor](https://docs.spring.io/spring-integration/api/org/springframework/integration/aggregator/DefaultAggregatingMessageGroupProcessor.html).

Trong ví dụ tiếp theo, mọi dòng hàng tạo một kết quả, kể cả dòng bị từ chối vì số lượng không hợp lệ. Nhờ đó, aggregator vẫn có thể hoàn thành hợp đồng số lượng.

## 4. Ví dụ Java DSL hoàn chỉnh: tính tiền từng dòng rồi gom đơn

### 4.1. Dependency và cách tổ chức

Nếu dự án đã quản lý phiên bản Spring Integration, dependency cho phần cấu hình chính là:

~~~xml
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-core</artifactId>
</dependency>
~~~

Đặt lớp bên dưới trong package `demo.integration`. Ví dụ dùng `@EnableIntegration` để có hạ tầng Spring Integration khi chạy bằng Spring Context thông thường.

Luồng chính:

~~~text
orderInput
    → splitOrder
    → priceLine
    → orderAggregator
    → orderResults

Nhóm thiếu kết quả hoặc message đến muộn
    → aggregationDiscards
~~~

`orderResults` và `aggregationDiscards` là queue để có thể quan sát kết quả trong kiểm thử. Ví dụ không sử dụng gateway nên lời gọi `send()` không trả về `OrderSummary`; consumer đọc kết quả từ `orderResults`.

### 4.2. Mô hình dữ liệu và cấu hình

~~~java
package demo.integration;

import java.math.BigDecimal;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.store.MessageGroup;
import org.springframework.integration.store.MessageGroupStore;
import org.springframework.integration.store.SimpleMessageStore;
import org.springframework.messaging.MessageChannel;

@Configuration(proxyBeanMethods = false)
@EnableIntegration
public class SplitAggregateConfig {

    public record OrderLine(
            int position,
            String sku,
            int quantity,
            BigDecimal unitPrice) {

        public OrderLine {
            Objects.requireNonNull(sku, "sku");
            Objects.requireNonNull(unitPrice, "unitPrice");
            if (position < 1 || unitPrice.signum() < 0) {
                throw new IllegalArgumentException(
                        "position phải >= 1 và unitPrice phải >= 0");
            }
        }
    }

    public record Order(String orderId, List<OrderLine> lines) {
        public Order {
            Objects.requireNonNull(orderId, "orderId");
            lines = List.copyOf(lines);
            if (lines.isEmpty()) {
                throw new IllegalArgumentException("Đơn hàng phải có dòng hàng");
            }
            long distinctPositions = lines.stream()
                    .map(OrderLine::position)
                    .distinct()
                    .count();
            if (distinctPositions != lines.size()) {
                throw new IllegalArgumentException("position không được trùng");
            }
        }
    }

    public record LineTask(String orderId, OrderLine line) {
    }

    public enum LineStatus {
        ACCEPTED, REJECTED
    }

    public record LineResult(
            String orderId,
            int position,
            String sku,
            LineStatus status,
            BigDecimal amount,
            String reason) {
    }

    public record OrderSummary(
            String orderId,
            List<LineResult> lines,
            BigDecimal acceptedTotal,
            boolean allSuccessful) {

        public OrderSummary {
            lines = List.copyOf(lines);
        }
    }

    @Bean
    public MessageChannel orderInput() {
        return new DirectChannel();
    }

    @Bean
    public QueueChannel orderResults() {
        return new QueueChannel(100);
    }

    @Bean
    public QueueChannel aggregationDiscards() {
        return new QueueChannel(100);
    }

    @Bean
    public MessageGroupStore orderGroupStore() {
        return new SimpleMessageStore();
    }

    @Bean
    public IntegrationFlow orderFlow(
            @Qualifier("orderInput") MessageChannel input,
            @Qualifier("orderResults") QueueChannel results,
            @Qualifier("aggregationDiscards") QueueChannel discards,
            @Qualifier("orderGroupStore") MessageGroupStore groupStore) {

        return IntegrationFlow.from(input)
                .split(
                        Order.class,
                        SplitAggregateConfig::splitOrder,
                        splitter -> splitter.applySequence(true))
                .<LineTask, LineResult>transform(
                        SplitAggregateConfig::priceLine)
                .aggregate(aggregator -> aggregator
                        .id("orderAggregator")
                        .messageStore(groupStore)
                        .outputProcessor(SplitAggregateConfig::summarize)
                        .groupTimeout(5_000)
                        .sendPartialResultOnExpiry(false)
                        .expireGroupsUponCompletion(false)
                        .expireGroupsUponTimeout(false)
                        .minimumTimeoutForEmptyGroups(60_000)
                        .discardChannel(discards))
                .channel(results)
                .get();
    }

    private static List<LineTask> splitOrder(Order order) {
        return order.lines().stream()
                .map(line -> new LineTask(order.orderId(), line))
                .toList();
    }

    private static LineResult priceLine(LineTask task) {
        OrderLine line = task.line();

        if (line.quantity() <= 0) {
            return new LineResult(
                    task.orderId(),
                    line.position(),
                    line.sku(),
                    LineStatus.REJECTED,
                    BigDecimal.ZERO,
                    "INVALID_QUANTITY");
        }

        BigDecimal amount = line.unitPrice()
                .multiply(BigDecimal.valueOf(line.quantity()));

        return new LineResult(
                task.orderId(),
                line.position(),
                line.sku(),
                LineStatus.ACCEPTED,
                amount,
                null);
    }

    private static OrderSummary summarize(MessageGroup group) {
        List<LineResult> lines = group.getMessages().stream()
                .map(message -> (LineResult) message.getPayload())
                .sorted(Comparator.comparingInt(LineResult::position))
                .toList();

        BigDecimal acceptedTotal = lines.stream()
                .filter(line -> line.status() == LineStatus.ACCEPTED)
                .map(LineResult::amount)
                .reduce(BigDecimal.ZERO, BigDecimal::add);

        boolean allSuccessful = lines.stream()
                .allMatch(line -> line.status() == LineStatus.ACCEPTED);

        return new OrderSummary(
                lines.get(0).orderId(),
                lines,
                acceptedTotal,
                allSuccessful);
    }
}
~~~

### 4.3. Những lựa chọn trong ví dụ

**Tách thành `LineTask` thay vì chỉ lấy `OrderLine`.** Mỗi phần mang sẵn `orderId`, giúp logic tính tiền và kết quả nghiệp vụ không phụ thuộc việc tra cứu lại đơn gốc.

**Materialize thành `List`.** Splitter biết số phần tử cần phát cho đơn hàng nhỏ. Đây là lựa chọn có chủ đích cho ví dụ; với tập dữ liệu rất lớn, chi phí bộ nhớ cần được thiết kế lại.

**Giữ correlation và release mặc định.** Luồng không ghi đè `correlationStrategy` hoặc `releaseStrategy`, vì thông tin chuỗi do splitter tạo đã phù hợp với quy tắc một phần tử tạo một kết quả.

**Sắp xếp theo `position` nghiệp vụ.** Output processor tạo danh sách theo hợp đồng trả về. Thứ tự hoàn tất tác vụ không quyết định thứ tự hiển thị.

**Trả về một record tổng hợp.** `OrderSummary` làm rõ kiểu dữ liệu downstream, chứa cả kết quả từng dòng và tổng tiền. Danh sách kết quả là một bản sao, không giữ tham chiếu đến collection nội bộ của store.

**Không coi nhóm thiếu là một đơn hàng hoàn chỉnh.** `sendPartialResultOnExpiry(false)` đưa nhóm không đủ điều kiện hoàn tất sang hướng discard khi timeout. Các phương thức DSL tương ứng được mô tả trong [AggregatorSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/AggregatorSpec.html) và [CorrelationHandlerSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/CorrelationHandlerSpec.html).

**Giữ dấu vết nhóm sau khi hoàn tất trong một khoảng thời gian.** Hai tùy chọn `expireGroupsUponCompletion(false)` và `expireGroupsUponTimeout(false)` giúp từ chối message đến muộn trong thời gian còn metadata. Mốc 60 giây của ví dụ phục vụ minh họa; production phải chọn thời gian giữ theo giới hạn retry và độ trễ thực tế.

Ví dụ này tính tiền thuần túy, không tạo side effect ngoài ứng dụng. Khi thay `priceLine` bằng lời gọi dịch vụ, cần bổ sung quy tắc timeout, retry và idempotency cho từng phần.

## 5. “Hoàn thành nhóm” khác “mọi phần đều thành công”

Với ba dòng hàng và dòng thứ hai có `quantity = 0`, luồng phát ba kết quả:

~~~text
Dòng 1 → ACCEPTED, amount=240000
Dòng 2 → REJECTED, amount=0, reason=INVALID_QUANTITY
Dòng 3 → ACCEPTED, amount=70000

Aggregator nhận đủ 3 kết quả:
  acceptedTotal = 310000
  allSuccessful = false
~~~

Nhóm đã đủ thông tin để trả lời dù có kết quả nghiệp vụ không thành công.

Có thể biểu diễn hai điều kiện:

~~~text
complete = đã nhận kết quả cuối cùng của mọi phần được mong đợi

allSuccessful = mọi kết quả cuối cùng đều thành công
~~~

Cách biểu diễn này hữu ích với kiểm tra nhiều mặt hàng, gọi nhiều nguồn báo giá hoặc nhập một tập bản ghi. Caller biết phần nào thất bại mà không phải suy đoán từ việc aggregator im lặng.

Không nên biến mọi ngoại lệ thành `REJECTED` một cách máy móc. Lỗi dữ liệu đã dự kiến và lỗi lập trình có cách xử lý khác nhau. Hợp đồng kết quả phải chỉ rõ lỗi nào có thể biểu diễn thành dữ liệu và lỗi nào khiến toàn bộ lần xử lý thất bại.

## 6. Filter và router có thể phá vỡ điều kiện “đủ số lượng”

### 6.1. Filter sau splitter làm thiếu kết quả

Giả sử splitter phát ba message với `sequenceSize = 3`, sau đó filter bỏ một message:

~~~text
Splitter phát:    1, 2, 3        sequenceSize=3
Filter bỏ:          2
Aggregator nhận: 1,    3        chỉ có 2 message
~~~

Nếu không có cơ chế hoàn tất khác, nhóm tiếp tục chờ. Spring Integration nêu trực tiếp trường hợp này trong [lưu ý về filter trước aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html).

Các thiết kế có thể chọn:

| Nhu cầu nghiệp vụ | Cách thiết kế |
|---|---|
| Chỉ xử lý các phần hợp lệ và không cần báo cáo phần bị loại | Lọc collection trước splitter để splitter tạo chuỗi mới đúng kích thước |
| Cần báo cáo mọi phần, kể cả phần bị loại | Phát một kết quả `REJECTED` hoặc `SKIPPED` cho phần đó |
| Chấp nhận kết quả không đầy đủ sau thời gian chờ | Thiết kế timeout và payload partial riêng |
| Số lượng được quyết định bởi hợp đồng khác | Cung cấp release strategy và kiểm thử hợp đồng đó |

Trong ví dụ đơn hàng, trả về `LineResult(REJECTED)` giữ được một kết quả cuối cùng cho mỗi dòng. Chỉ ghi log ở discard channel của filter chưa giải quyết việc aggregator thiếu message.

### 6.2. Router chia đường đi nhưng vẫn phải có điểm hội tụ

Một router có thể phân loại dòng thường và dòng cần kiểm tra đặc biệt:

~~~text
                         → xử lý thông thường ─────┐
Splitter → Router                                  ├→ cùng aggregator
                         → kiểm tra đặc biệt ──────┘
~~~

Hai nhánh cần:

- Trả về cùng hợp đồng payload, chẳng hạn `LineResult`.
- Giữ thông tin correlation của lần tách.
- Mỗi phần đóng góp đúng số kết quả mà hợp đồng release mong đợi.
- Có cách xử lý nhánh không tìm thấy route hoặc kết thúc sớm.

Nếu một phần được phát đồng thời sang hai nhánh và cả hai đều quay lại aggregator, số message tăng so với chuỗi ban đầu. Khi cần nhiều kết quả cho mỗi phần, hãy mô hình hóa một cấp tách/gom khác hoặc xây hợp đồng release tương ứng.

## 7. Xử lý lỗi mà không để nhóm chờ vô hạn

### 7.1. Lỗi đồng bộ và lỗi bất đồng bộ

Trong flow dùng `DirectChannel`, exception từ handler thường truyền về caller trên cùng call stack. Khi có executor hoặc poller, lỗi cần được chuyển qua cơ chế thông điệp thích hợp; `ErrorMessage` có payload là exception. Đặt một header `errorChannel` không tự biến mọi lời gọi đồng bộ thành xử lý lỗi bất đồng bộ. Xem [Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html).

Đối với cặp splitter–aggregator, câu hỏi cần trả lời là: **sau lỗi, phần đang xử lý còn tạo ra kết quả cuối cùng cho nhóm hay không?**

Ví dụ:

~~~text
Phần 1 → thành công → aggregator
Phần 2 → gọi dịch vụ lỗi → error flow
Phần 3 → thành công → aggregator
~~~

Nếu error flow chỉ ghi log, aggregator nhận hai kết quả trên tổng ba phần. Timeout vẫn cần thiết dù hệ thống đã có error channel.

### 7.2. Ba chính sách lỗi thường dùng

| Chính sách | Hành vi của phần bị lỗi | Hành vi cấp nhóm |
|---|---|---|
| Retry rồi trả kết quả lỗi | Retry có giới hạn, sau đó tạo `LineResult` lỗi | Có thể nhận đủ kết quả và trả báo cáo |
| Dừng cả yêu cầu | Ghi nhận thất bại của lần xử lý, kết thúc hoặc bù trừ các phần khác | Cần cơ chế điều phối hủy và dọn nhóm |
| Chấp nhận partial | Phần lỗi không đóng góp kết quả thành công | Trả payload ghi rõ thiếu phần nào sau deadline |

Với chính sách thứ nhất, message bù cho phần lỗi phải giữ header của **message con bị lỗi**. Sao chép từ message đơn hàng gốc sẽ không mang đúng vị trí và kích thước chuỗi của phần đó.

Đoạn minh họa tại điểm recovery:

~~~java
// failedPart: message con lấy từ ngữ cảnh lỗi/retry.
// failureResult: LineResult cuối cùng cho chính phần đó.
// aggregateInput: channel đi vào aggregator, không đi qua splitter.
Message<LineResult> recoveryMessage = MessageBuilder
        .withPayload(failureResult)
        .copyHeaders(failedPart.getHeaders())
        .build();

aggregateInput.send(recoveryMessage);
~~~

Để áp dụng vào cấu hình chính, cần tách một channel đặt tên trước aggregator và cho recovery gửi vào channel đó. Không gửi recovery về `orderInput`, vì channel này nhận `Order` và bắt đầu một lần tách.

Error flow cần xác định được failed message từ exception hoặc ngữ cảnh recovery thực tế. Không giả định header của lớp vỏ `ErrorMessage` chính là header của message con.

### 7.3. Timeout của nhóm không hủy tác vụ

Nếu tác vụ thứ hai vẫn đang gọi dịch vụ khi nhóm hết hạn, aggregator không tự dừng request HTTP hay luồng thực thi của tác vụ đó.

Cần phối hợp:

- Timeout tại lời gọi bên ngoài.
- Giới hạn retry.
- Thời gian chờ của nhóm.
- Thời gian chờ phản hồi của gateway hoặc caller.
- Chính sách với kết quả đến sau khi nhóm đã kết thúc.

Ví dụ, caller chỉ chờ 2 giây nhưng aggregator chờ 5 giây sẽ tạo kết quả sau khi caller đã ngừng đợi. Luồng phải xác định nơi nhận kết quả đó, thay vì coi timeout của caller là bằng chứng nhóm đã được hủy.

## 8. Timeout, partial result và vòng đời nhóm

### 8.1. `groupTimeout` là khoảng chờ không có message mới

Với `groupTimeout(5_000)`, lịch hoàn tất cưỡng bức của nhóm được đặt lại khi message mới đến mà nhóm chưa release. Vì vậy đây là khoảng chờ tính từ message mới nhất của nhóm, không mặc nhiên là deadline 5 giây từ lúc nhận đơn hàng. Chi tiết được mô tả trong [Aggregator and Group Timeout](https://docs.spring.io/spring-integration/reference/aggregator.html#aggregator-and-group-timeout).

Ví dụ:

~~~text
t = 0s: nhận phần 1 → dự kiến timeout tại t = 5s
t = 4s: nhận phần 2 → dự kiến timeout chuyển sang t = 9s
t = 9s: vẫn thiếu phần 3 → bắt đầu xử lý timeout
~~~

Nhóm chỉ tồn tại sau khi ít nhất một message đến aggregator. Nếu tất cả phần đều mất hoặc bị lỗi trước điểm gom, timeout của aggregator không phát hiện được yêu cầu đó; cần theo dõi deadline ở cấp yêu cầu.

Khi nghiệp vụ cần thời điểm kết thúc tuyệt đối, hãy mang deadline trong hợp đồng và dùng timeout expression phù hợp, đồng thời quy định cách xử lý message đến sau deadline.

### 8.2. Partial phải là một hợp đồng khác có chủ đích

`sendPartialResultOnExpiry(true)` cho phép tạo output từ các message đang có khi nhóm không đủ điều kiện release tại thời điểm hết hạn. Đổi một cờ này chưa đủ để biến `OrderSummary` thành một phản hồi partial đúng nghĩa.

Một phản hồi partial nên thể hiện ít nhất:

~~~text
requestId:       R-100
status:          PARTIAL
expectedCount:   3
receivedCount:   2
completedParts:  [1, 3]
missingParts:    [2]
acceptedTotal:   310000
~~~

Ví dụ chính dùng `false` để tránh trả một tổng tiền thiếu dòng dưới hình thức đơn hàng đã xử lý đầy đủ. Nếu muốn partial, hãy đổi cả output processor và kiểu dữ liệu kết quả.

### 8.3. Hoàn tất nhóm và xóa nhóm có tác dụng khác nhau

| Lựa chọn | Tác dụng cần chú ý |
|---|---|
| Giữ metadata sau khi hoàn tất | Có thể nhận diện và discard message đến muộn cùng khóa |
| `expireGroupsUponCompletion(true)` | Xóa nhóm sau hoàn tất bình thường; message cùng khóa đến sau có thể tạo nhóm mới |
| `expireGroupsUponTimeout(true)` | Cho phép xóa nhóm sau timeout; cần cân nhắc kết quả đến muộn |
| `minimumTimeoutForEmptyGroups(...)` | Giới hạn thời gian giữ metadata nhóm rỗng sau release theo cơ chế tương ứng |
| Reaper hoặc cơ chế purge | Dọn trạng thái cũ theo chính sách của store và endpoint |

Các tùy chọn vòng đời được mô tả trong [CorrelationHandlerSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/CorrelationHandlerSpec.html). Cơ chế quét nhóm theo lịch có thể dùng [MessageGroupStoreReaper](https://docs.spring.io/spring-integration/api/org/springframework/integration/store/MessageGroupStoreReaper.html); riêng việc khai báo reaper không thay thế cho việc lên lịch gọi nó.

Thời gian giữ metadata là một cửa sổ bảo vệ có giới hạn. Sau khi metadata bị xóa, message cũ có cùng correlation key có thể được nhìn như khởi đầu nhóm mới. Nếu cần chống xử lý lặp lâu hơn, phải có lưu trữ idempotency ở cấp nghiệp vụ.

## 9. Xử lý song song: splitter không tự tạo thread

Trong cấu hình chính, các bước liên tiếp dùng channel đồng bộ cho đến queue đầu ra. Thao tác tách thành nhiều message không đồng nghĩa các dòng được xử lý song song.

Có thể bổ sung một `ExecutorChannel` ngay sau splitter:

~~~text
Splitter → ExecutorChannel → tính tiền từng dòng → Aggregator
~~~

Các bean sau là phần mở rộng cho `SplitAggregateConfig`:

~~~java
@Bean
public org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor
        lineExecutor() {

    var executor =
            new org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("order-line-");
    return executor;
}

@Bean
public MessageChannel lineWorkers(
        @Qualifier("lineExecutor")
        org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor executor) {

    return new org.springframework.integration.channel.ExecutorChannel(executor);
}
~~~

Sau đó inject thêm `@Qualifier("lineWorkers") MessageChannel workers` vào phương thức tạo flow và chèn `.channel(workers)` giữa `.split(...)` và `.transform(...)`.

Khi mở rộng như vậy:

- Kết quả có thể đến aggregator khác thứ tự đầu vào.
- Handler xử lý phần tử phải an toàn khi được gọi đồng thời.
- Hàng đợi executor đầy có thể khiến việc gửi tác vụ bị từ chối.
- Thời gian chờ ở executor nằm trong độ trễ toàn bộ yêu cầu.
- Retry và recovery phải xử lý được lỗi trên thread của executor.

Nếu một lần gửi bị gián đoạn giữa chừng, một số phần có thể đã được giao thực thi. Vì thế không suy ra toàn bộ đơn hàng chưa được xử lý chỉ từ việc caller nhận exception.

Aggregator gom kết quả theo khóa và điều kiện release; việc sắp xếp kết quả trong `summarize` là lựa chọn riêng để đáp ứng thứ tự nghiệp vụ. Nếu downstream cần nhận từng message theo thứ tự thay vì một đối tượng tổng hợp, hãy xem xét resequencer.

## 10. Collection rỗng và dữ liệu không biết trước kích thước

### 10.1. Không có message con thì không có nhóm để chờ

Nếu splitter trả collection rỗng, nó không phát phần tử sang aggregator. Không tồn tại một “message con số 0” để báo nhóm đã xong. Splitter có thể dùng discard channel cho đầu vào tạo container rỗng; kết quả `null` có ý nghĩa kết thúc luồng riêng. Xem [Splitter](https://docs.spring.io/spring-integration/reference/splitter.html).

Trong cấu hình chính, constructor `Order` từ chối danh sách rỗng trước khi message được gửi vào flow. Đây là quy tắc ví dụ, không phải quy tắc bắt buộc của mọi hệ thống.

Nếu đơn hàng rỗng là hợp lệ, một thiết kế rõ ràng là router trước splitter:

~~~text
Order không có dòng → tạo OrderSummary rỗng → output

Order có dòng       → splitter → xử lý từng dòng → aggregator → output
~~~

Nhánh rỗng cần tạo kết quả trực tiếp; chờ timeout ở aggregator sẽ không giúp vì chưa có message nào tạo nhóm.

### 10.2. Iterator và stream có thể không cung cấp kích thước

Khi splitter không xác định được kích thước của nguồn iterator hoặc stream, `sequenceSize` có thể là `0`. Strategy chờ đủ chuỗi không có tổng số phần tử cần đợi. Một số splitter chuyên biệt có thể suy ra kích thước, nên cần xét implementation thực tế. Xem [hỗ trợ iterator của Splitter](https://docs.spring.io/spring-integration/reference/splitter.html#splitter-iterators).

Các hướng thiết kế:

| Đặc điểm đầu vào | Hướng chọn |
|---|---|
| Tập nhỏ, có thể tải toàn bộ | Chuyển thành collection trước khi tách |
| Tập lớn nhưng biết tổng số phần tử từ manifest | Mang số lượng mong đợi và xây hợp đồng release tương ứng |
| Tập không biết trước kích thước | Dùng giao thức kết thúc có kiểm chứng hoặc cửa sổ thời gian |
| Cần xử lý vô hạn hoặc liên tục | Dùng micro-batch/window với ranh giới nghiệp vụ rõ ràng |

Một marker “đã phát hết” chỉ cho biết producer đã gửi xong. Trong luồng song song, marker có thể tới trước các kết quả đang chạy. Muốn dựa vào marker để release, cần biết tổng số phần được mong đợi và xác nhận đã có kết quả của các phần đó.

## 11. Correlation tùy chỉnh, retry và xử lý trùng

### 11.1. Chọn khóa cho đúng một lần xử lý

Ví dụ chính dùng correlation do splitter tạo, nên hai message đầu vào có cùng `orderId` vẫn có thể tạo hai nhóm độc lập.

Điều này phù hợp khi cùng một đơn có hai lần tính lại. Nó không tự ngăn việc tính lại một yêu cầu bị gửi trùng.

Nếu ghi đè correlation bằng `orderId`, hãy xác định trước:

- Hai lần xử lý đồng thời cùng đơn có được phép hay không.
- Tenant khác nhau có thể trùng `orderId` hay không.
- Sau retry, kết quả cũ và mới có được phép cùng nhóm hay không.
- Lúc nào khóa được phép tái sử dụng.

Một khóa theo hợp đồng có thể gồm `tenantId + orderId + processingRunId`. Khóa nên có biểu diễn ổn định và quy tắc bằng nhau rõ ràng, đặc biệt khi dùng persistent store.

### 11.2. Retry không được tạo thêm kết quả cuối cùng

Giả sử nhóm cần ba phần nhưng nhận:

~~~text
Kết quả phần 1
Kết quả phần 1 được gửi lại với Message.id mới
Kết quả phần 3
~~~

Số lượng đã là ba nhưng phần 2 vẫn thiếu. Strategy đếm số lượng không thay thế cho việc phát hiện trùng kết quả.

Cần phân biệt:

| Danh tính | Mục đích |
|---|---|
| `Message.id` | Nhận diện một message cụ thể |
| `processingRunId` hoặc correlation key | Nhận diện lần xử lý cấp nhóm |
| `partId` hoặc vị trí dòng trong lần xử lý | Nhận diện một đơn vị công việc |
| Idempotency key của side effect | Ngăn lặp thao tác nghiệp vụ như ghi nhận hoặc thanh toán |

Một thiết kế có thể đặt idempotent receiver trước aggregator với khóa gồm lần xử lý và phần tử. Nếu release strategy tự kiểm tra tập part key, vẫn cần xử lý các bản sao trong output processor; chỉ đếm số khóa khác nhau chưa loại bản sao khỏi dữ liệu đem tính tổng.

Nếu retry toàn bộ yêu cầu bằng một message đầu vào mới, splitter có thể tạo một nhóm mới. Chống lặp ở cấp phần tử và chống lặp yêu cầu gốc là hai phạm vi cần được thiết kế riêng.

## 12. Splitter lồng nhau và giới hạn triển khai

### 12.1. Gom theo thứ tự ngược với các cấp tách

Ví dụ một lô có nhiều đơn, mỗi đơn có nhiều dòng:

~~~text
Batch
  → splitter cấp batch
      → Order
          → splitter cấp order
              → LineTask
              → LineResult
          → aggregator cấp order
      → OrderSummary
  → aggregator cấp batch
  → BatchSummary
~~~

Mỗi cấp gom cần khôi phục metadata của cấp bao ngoài sau khi hoàn tất. Spring Integration hỗ trợ sequence details cho cấu trúc lồng nhau và hành vi `popSequence` ở aggregator. Nếu tự tạo message hoặc sửa sequence headers, phải giữ đúng thông tin cấp tách; xem [sequence details trong Aggregator](https://docs.spring.io/spring-integration/reference/6.5/aggregator.html).

Trong thiết kế này, aggregator cấp order gom các dòng của một đơn; aggregator cấp batch gom các `OrderSummary`. Nếu cả hai cùng gom theo một `orderId` tùy ý mà bỏ cấp batch, các lần xử lý có thể bị lẫn.

### 12.2. Store trong bộ nhớ phù hợp với ví dụ, không bảo đảm phục hồi

`SimpleMessageStore` trong bài giữ dữ liệu chờ gom trong tiến trình hiện tại. Khi ứng dụng dừng, ví dụ không có cơ chế phục hồi nhóm còn thiếu.

Với yêu cầu phục hồi hoặc nhiều instance, cần quyết định:

- Mỗi nhóm có được định tuyến về cùng một instance không.
- Có dùng store dùng chung hay persistent store không.
- Cơ chế khóa có phối hợp giữa các instance không.
- Payload và header có thể lưu/khôi phục đúng kiểu không.
- Nhóm dang dở sau restart được tiếp tục hay kết thúc ra sao.
- Việc phát output và cập nhật trạng thái có cần giao dịch hoặc outbox không.

Chỉ thay store sang một nơi dùng chung chưa giải quyết toàn bộ phối hợp đồng thời và tính nhất quán. Khóa nội bộ của một tiến trình không điều phối các tiến trình khác.

Chi phí trạng thái có thể ước lượng:

~~~text
Dung lượng chờ gom
  ≈ tổng payload và header đang nằm trong các nhóm chưa hoàn tất
    + metadata các nhóm đã hoàn tất nhưng chưa xóa
    + cấu trúc phụ trợ của store
~~~

Giới hạn kích thước nhóm, số nhóm mở và thời gian giữ trạng thái cần đi cùng giới hạn queue. Nếu phần lớn thời gian chờ là chờ một dịch vụ chậm, tăng số worker có thể làm số nhóm mở tăng nhanh.

## 13. Kiểm thử hợp đồng splitter–aggregator

Phần này cung cấp mã kiểm thử để người học chạy trong dự án có JUnit 5, `spring-test` và Spring Integration. Đây là nội dung thực hành của bài, không phải báo cáo rằng các test đã được chạy.

### 13.1. Kiểm thử tích hợp luồng chính

Đặt lớp kiểm thử cùng package với cấu hình:

~~~java
package demo.integration;

import java.math.BigDecimal;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit.jupiter.SpringExtension;

import demo.integration.SplitAggregateConfig.LineStatus;
import demo.integration.SplitAggregateConfig.Order;
import demo.integration.SplitAggregateConfig.OrderLine;
import demo.integration.SplitAggregateConfig.OrderSummary;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = SplitAggregateConfig.class)
class SplitAggregateFlowTest {

    @Autowired
    @Qualifier("orderInput")
    MessageChannel input;

    @Autowired
    @Qualifier("orderResults")
    QueueChannel results;

    @Test
    void aggregatesAllThreeLines() {
        Order order = new Order("O-100", List.of(
                line(1, "A", 2, "120000"),
                line(2, "B", 3, "50000"),
                line(3, "C", 1, "70000")));

        assertTrue(input.send(MessageBuilder.withPayload(order).build()));

        OrderSummary summary = receiveSummary();

        assertEquals("O-100", summary.orderId());
        assertEquals(List.of(1, 2, 3), summary.lines().stream()
                .map(result -> result.position())
                .toList());
        assertEquals(0, new BigDecimal("460000")
                .compareTo(summary.acceptedTotal()));
        assertTrue(summary.allSuccessful());
    }

    @Test
    void rejectedLineStillContributesOneFinalResult() {
        Order order = new Order("O-200", List.of(
                line(1, "A", 1, "100000"),
                line(2, "B", 0, "50000")));

        assertTrue(input.send(MessageBuilder.withPayload(order).build()));

        OrderSummary summary = receiveSummary();

        assertEquals(2, summary.lines().size());
        assertEquals(LineStatus.REJECTED, summary.lines().get(1).status());
        assertEquals("INVALID_QUANTITY", summary.lines().get(1).reason());
        assertEquals(0, new BigDecimal("100000")
                .compareTo(summary.acceptedTotal()));
        assertFalse(summary.allSuccessful());
    }

    @Test
    void separateInputMessagesWithSameOrderIdCreateSeparateGroups() {
        Order first = new Order("O-SAME", List.of(
                line(1, "A", 1, "10")));
        Order second = new Order("O-SAME", List.of(
                line(1, "B", 1, "20")));

        assertTrue(input.send(MessageBuilder.withPayload(first).build()));
        assertTrue(input.send(MessageBuilder.withPayload(second).build()));

        OrderSummary firstSummary = receiveSummary();
        OrderSummary secondSummary = receiveSummary();

        assertEquals(0, new BigDecimal("10")
                .compareTo(firstSummary.acceptedTotal()));
        assertEquals(0, new BigDecimal("20")
                .compareTo(secondSummary.acceptedTotal()));
    }

    private OrderSummary receiveSummary() {
        Message<?> message = results.receive(1_000);
        assertNotNull(message, "Luồng phải tạo kết quả tổng hợp");
        assertTrue(message.getPayload() instanceof OrderSummary);
        return (OrderSummary) message.getPayload();
    }

    private static OrderLine line(
            int position, String sku, int quantity, String price) {

        return new OrderLine(
                position, sku, quantity, new BigDecimal(price));
    }
}
~~~

Các test dùng queue receive có timeout, tránh sleep tùy ý. Test thứ ba kiểm tra cách ly hai lần gửi khi giữ correlation mặc định; nó không chứng minh cơ chế chống lặp nghiệp vụ.

### 13.2. Những tình huống cần kiểm tra khi mở rộng

| Tình huống | Dữ liệu hoặc cách gây ra | Điều cần xác minh |
|---|---|---|
| Kết quả đến lệch thứ tự | Cho các phần có thời gian xử lý khác nhau | Chỉ xuất một summary và thứ tự trả về đúng hợp đồng |
| Hai nhóm xen kẽ | Gửi phần của hai correlation key luân phiên | Không trộn payload của hai nhóm |
| Thiếu một phần | Không gửi một kết quả vào aggregator | Không release bình thường; xử lý timeout đúng chính sách |
| Filter loại phần tử | Bỏ phần số 2 sau splitter | Tái hiện nhóm thiếu hoặc xác nhận có kết quả bù |
| Kết quả gửi lặp | Gửi hai message khác id cho cùng part key | Không tính tiền trùng theo cơ chế đã chọn |
| Kết quả đến muộn | Gửi sau completion/timeout | Discard hoặc tạo nhóm mới đúng chính sách vòng đời |
| Danh sách đầu vào rỗng | Tạo yêu cầu không có dòng | Từ chối sớm hoặc trả summary rỗng trực tiếp |
| Iterator không có tổng | Tạo nguồn không biết trước số phần | Không dựa vào release theo sequence size mặc định |
| Restart khi nhóm dang dở | Dùng môi trường có persistent store | Khôi phục hoặc kết thúc nhóm đúng quy định |
| Executor quá tải | Dùng queue nhỏ và handler bị chặn có kiểm soát | Không bỏ sót xử lý thất bại của yêu cầu |

Để kiểm thử timeout nhanh, hãy tạo cấu hình test có khoảng chờ ngắn và một channel đặt tên ngay trước aggregator. Gửi có chủ đích các message chứa `correlationId`, `sequenceNumber`, `sequenceSize` vào channel đó; không dùng ngẫu nhiên thời gian sleep để hy vọng tạo được nhóm thiếu.

## 14. Chẩn đoán nhóm không release

Khi một yêu cầu không có kết quả tổng hợp, nên lần theo một processing run cụ thể:

~~~text
Message gốc
  → đã tách bao nhiêu phần?
  → từng phần đã đi vào nhánh nào?
  → phần nào có kết quả cuối cùng?
  → kết quả mang correlation key gì?
  → aggregator đã lưu bao nhiêu message?
  → release strategy đang chờ điều kiện nào?
  → nhóm đã timeout, hoàn tất hay bị xóa chưa?
~~~

| Triệu chứng | Nguyên nhân có thể kiểm tra |
|---|---|
| Nhóm có 2 message và `sequenceSize=3` | Filter, lỗi một nhánh hoặc không phát recovery |
| `sequenceSize=0` | Nguồn tách không biết kích thước |
| Mỗi kết quả tạo một nhóm riêng | Mất hoặc thay sai correlation key |
| Hai lần chạy bị lẫn | Correlation key quá rộng, tái dùng khóa |
| Release trước khi có mọi phần | Kết quả lặp hoặc release strategy không đúng hợp đồng |
| Có summary thiếu dòng nhưng trông như hoàn chỉnh | Partial result không được thể hiện trong payload |
| Bộ nhớ tăng dù đã xử lý xong | Nhóm dang dở hoặc metadata hoàn tất chưa được dọn |
| Timeout không xuất hiện | Chưa có message nào đến aggregator hoặc scheduler không hoạt động |
| Message cũ tạo nhóm mới | Metadata nhóm cũ đã bị xóa |

Log hữu ích ở các điểm tách, trước gom và tại recovery/discard gồm: processing run, order id, part key, correlation key, sequence number, sequence size, trạng thái kết quả và endpoint. Hạn chế log toàn bộ payload khi nó lớn hoặc chứa dữ liệu nhạy cảm.

Các số đo nên gắn với hợp đồng vận hành: số nhóm đang mở, tuổi nhóm lâu nhất, thời gian từ phần đầu đến khi release, số nhóm timeout, số message discard và số kết quả lặp bị chặn.

Một cặp splitter–aggregator được thiết kế đầy đủ cần trả lời được bốn điều: phần tử thuộc lần xử lý nào, mỗi phần đóng góp bao nhiêu kết quả, khi nào nhóm được kết thúc và trạng thái còn lại được giữ trong bao lâu.
