# Chọn output channel sau aggregation

Trong **Spring Integration**, Aggregator gom nhiều message có liên quan thành một kết quả. Tuy nhiên, sau khi nhóm được **release**, hệ thống còn phải quyết định **kết quả sẽ được gửi tới channel nào**: một channel xử lý cố định, một Router chọn nhánh động, một adapter xuất event hay đường reply cho Gateway.

Bài **Chọn output channel sau aggregation** thuộc chương **Aggregator** của module **SPRING_INTEGRATION_PATTERN**. Module hướng tới xây dựng luồng thông điệp ít phụ thuộc, dễ mở rộng bằng Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, correlation và các kỹ thuật kiểm thử, giám sát từng nhánh.

Trọng tâm của bài là phân biệt **điều kiện tạo ra output** với **đích nhận output**. Một Aggregator có thể gom đúng dữ liệu nhưng Gateway vẫn timeout, result bị gửi nhầm channel hoặc consumer không nhận được nếu không thiết kế đường đi và headers phù hợp.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Mô tả chuỗi xử lý **correlation → release → output processor → output channel**.
2. Phân biệt output channel của Aggregator với `replyChannel`, `errorChannel`, `discardChannel` và `MessageGroupStore`.
3. Cấu hình channel đầu ra cố định bằng Java DSL `.aggregate().channel(...)`.
4. Dùng Transformer và Router **sau aggregation** để chọn destination theo kết quả tổng hợp.
5. Hiểu điều kiện cần để trả reply về Gateway, đặc biệt khi output message hợp nhất headers từ nhiều part.
6. Chọn `DirectChannel`, `QueueChannel`, `ExecutorChannel`, `PublishSubscribeChannel` hoặc outbound adapter theo yêu cầu.
7. Thiết kế riêng các tình huống partial result, expiry, message lỗi và late arrival.
8. Kiểm thử chỉ có một output khi nhóm hoàn tất, route đúng nhánh, không phát sớm và bảo toàn metadata cần thiết.
9. Nhận diện lỗi cấu hình channel, thiếu consumer, sai correlation, mất reply header, xử lý trùng và retry.
10. Kết hợp Aggregator với Splitter, Filter, Transformer, Router, Gateway và error flow một cách có thể quan sát.

## 2. Aggregator tạo kết quả ở giai đoạn nào?

Một Aggregator thực hiện ba trách nhiệm chính trước khi tìm kênh gửi:

- **Correlation strategy**: message nào thuộc cùng một nhóm?
- **Release strategy**: nhóm đã có đủ dữ liệu để phát kết quả chưa?
- **Output processor**: tổng hợp các message của nhóm thành payload/message gì?

Sau khi output processor tạo kết quả, framework mới gửi message theo output routing tương ứng.

~~~mermaid
flowchart LR
    P["Message parts"] --> C["Correlation strategy"]
    C --> S[("MessageGroupStore")]
    S --> R{"Release strategy"}
    R -->|"Chưa đủ"| W["Giữ nhóm, chờ thêm"]
    R -->|"Đủ"| O["Output processor"]
    O --> CH["Output channel"]
    CH --> D["Downstream"]
~~~

| Câu hỏi | Thành phần | Ví dụ |
|---|---|---|
| Các message có liên quan không? | Correlation | Cùng `orderId=ORDER-1001` |
| Đã đủ chưa? | Release | Đủ 3 part với `sequenceSize=3` |
| Tạo kết quả gì? | Output processor | `Collection<PricedLine>` |
| Kết quả đi đâu? | Output channel/Router/reply | `orders.aggregated` |
| Handler sau đó hoàn tất chưa? | Downstream/ack/metric | DB commit, broker ack |

**Không được xem release là một thao tác đã hoàn thành nghiệp vụ downstream.** Một nhóm được release và output đã gửi vào queue vẫn chưa chứng minh consumer đã lưu DB.

### 2.1. Ví dụ một đơn hàng

~~~text
ORDER-1001
SKU-A: 2 x 100.00 = 200.00
SKU-B: 1 x  50.00 =  50.00
SKU-C: 3 x  25.00 =  75.00
--------------------------
Tổng cộng         325.00
~~~

Nếu mọi đơn đều qua bước đối soát, output có thể gửi tới channel cố định `orders.aggregated`. Nếu chỉ đơn từ **1.000.00** trở lên cần xử lý high-value, Router sau aggregation sẽ chọn `orders.highValue` hoặc `orders.standard` dựa trên **tổng kết quả**, không dựa trên một dòng lẻ.

## 3. Quy tắc chọn output channel trong Spring Integration

Ở một message-producing endpoint của Spring Integration, cách hiểu tổng quát là:

1. Nếu endpoint có **output channel đã cấu hình rõ**, dùng đích đó cho reply/output.
2. Nếu không có output channel cố định, framework có thể dùng **replyChannel từ message kết quả** theo contract messaging.
3. Nếu không tìm được đích hợp lệ, output có thể không được dispatch và xảy ra lỗi hoặc Gateway timeout tùy topology.

~~~mermaid
flowchart TD
    A["Group release thành công"] --> B["Tạo aggregated output"]
    B --> C{"Output channel cố định?"}
    C -->|Có| D["Dispatch tới channel đã định"]
    C -->|Không| E{"Output message có replyChannel hợp lệ?"}
    E -->|Có| F["Dispatch tới reply channel"]
    E -->|Không| G["Thiếu đường gửi: xử lý lỗi theo topology"]
~~~

Với Aggregator, điểm quan trọng là **output message được hình thành từ nhiều part**, nên headers trên output không mặc nhiên giống mọi header của từng part. Không nên lấy `replyChannel` ở message cuối cùng rồi mặc định đó là replyChannel của toàn group.

### 3.1. Phân biệt các channel và metadata

| Thành phần | Chức năng | Có phải đường output thành công mặc định? |
|---|---|---|
| `outputChannel` | Đích gửi kết quả đã tổng hợp | Có, khi cấu hình |
| `replyChannel` | Đích trả lời một request | Có thể, khi output không có đích cố định và header còn hợp lệ |
| `errorChannel` | Đường xử lý exception theo topology | Không |
| `discardChannel` | Đường cho message/group bị loại theo cấu hình | Không |
| `MessageGroupStore` | Lưu trạng thái nhóm | Không |
| `correlationId` | Khóa liên kết message của nhóm | Không |
| `sequenceNumber`, `sequenceSize` | Metadata về các part | Không |
| `businessCorrelationId` | Dấu liên kết nghiệp vụ | Không |

**Output channel cố định có ưu tiên hơn reply addressing qua header** tại endpoint đó. Muốn vừa publish event vừa trả Gateway, cần thiết kế hai đường có chủ đích; đừng kỳ vọng Spring tự gửi hai bản từ một reply.

## 4. Chọn loại channel nào?

| Channel | Đặc điểm | Thích hợp | Rủi ro chính |
|---|---|---|---|
| `DirectChannel` | Gọi một consumer đồng bộ trên sender thread | Một bước xử lý nhanh tiếp theo | Consumer chậm/lỗi chặn flow |
| `QueueChannel` | Consumer poll/receive message | Tách nhịp xử lý hoặc test | Mặc định trong bộ nhớ, cần poller |
| `ExecutorChannel` | Dispatch qua thread pool | Xử lý không đồng bộ trong một JVM | Backlog, rejection, lỗi worker |
| `PublishSubscribeChannel` | Broadcast tới subscriber | Audit + analytics + notification | Nhiều nhánh với error/latency khác nhau |
| Channel nối outbound adapter | Chuyển event tới broker/API | Tích hợp hệ thống khác | Delivery/ack phụ thuộc adapter/broker |
| Channel có Router ở phía sau | Chuyển kết quả sang policy định tuyến | Đích theo amount/status/region | Phải có đúng output schema |

Không nên chọn `QueueChannel` chỉ vì “đầu ra cần queue”, rồi quên cấu hình poller/consumer. Tương tự, đưa output vào `PublishSubscribeChannel` **không biến kết quả thành durable event** có thể replay sau restart.

## 5. Ví dụ Java 17: model đầu vào và xử lý từng dòng

Ta xây một flow có thể chạy integration test: nhận `List<OrderLine>`, Splitter tạo từng message, Transformer tính tiền, Aggregator gom chúng vào một message output.

### 5.1. Kiểu payload

~~~java
import java.math.BigDecimal;

public record OrderLine(
        String sku,
        BigDecimal unitPrice,
        int quantity
) {}

public record PricedLine(
        String sku,
        BigDecimal lineTotal
) {}
~~~

Hai record `public` cần được đặt trong source file Java riêng có tên tương ứng khi triển khai project thực tế. Payload sử dụng kiểu `BigDecimal` để xử lý giá tiền thay vì `double`.

### 5.2. Policy biến đổi từng dòng

~~~java
import java.math.BigDecimal;
import java.util.Objects;

public final class LinePricingPolicy {

    public PricedLine price(OrderLine line) {
        Objects.requireNonNull(line, "line");

        if (line.sku() == null || line.sku().isBlank()) {
            throw new IllegalArgumentException("SKU_REQUIRED");
        }
        if (line.unitPrice() == null
                || line.unitPrice().signum() < 0) {
            throw new IllegalArgumentException("PRICE_INVALID");
        }
        if (line.quantity() <= 0) {
            throw new IllegalArgumentException("QUANTITY_INVALID");
        }

        return new PricedLine(
                line.sku(),
                line.unitPrice().multiply(
                        BigDecimal.valueOf(line.quantity())));
    }
}
~~~

Policy là hàm thuần, không gọi DB hay HTTP. Nếu một part không hợp lệ, nó ném lỗi để flow không coi part sai là một kết quả đã tính. Không bỏ qua lỗi một cách âm thầm rồi để Aggregator đợi thiếu `sequenceSize`.

## 6. Output channel cố định bằng Java DSL

Đây là trường hợp dễ triển khai nhất: mọi group hoàn tất đều đến cùng một channel `orders.aggregated`.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
public class FixedOutputAggregationConfig {

    @Bean(name = "orders.lines.input")
    public MessageChannel inputChannel() {
        return new DirectChannel();
    }

    @Bean(name = "orders.aggregated")
    public PollableChannel outputChannel() {
        return new QueueChannel();
    }

    @Bean
    public LinePricingPolicy linePricingPolicy() {
        return new LinePricingPolicy();
    }

    @Bean
    public IntegrationFlow aggregateOrderLines(
            LinePricingPolicy policy) {

        return IntegrationFlow.from("orders.lines.input")
                .split()
                .transform(OrderLine.class, policy::price)
                .aggregate()
                .channel("orders.aggregated")
                .get();
    }
}
~~~

Hai dòng then chốt:

~~~java
.aggregate()
.channel("orders.aggregated")
~~~

`aggregate()` thực hiện tập hợp các part theo correlation/release strategy. `channel("orders.aggregated")` đặt **điểm đến cố định** cho kết quả mà endpoint này phát. Nó không quyết định message thuộc nhóm nào và không khiến group chưa đủ tự release.

### 6.1. Vì sao output không phải dòng cuối cùng?

~~~text
Producer:
  Message<List<OrderLine>>

Splitter:
  Message<OrderLine> A (1/3)
  Message<OrderLine> B (2/3)
  Message<OrderLine> C (3/3)

Transformer:
  Message<PricedLine> A
  Message<PricedLine> B
  Message<PricedLine> C

Aggregator:
  Một Message<Collection<PricedLine>>

Output:
  orders.aggregated
~~~

Với default aggregation processor trong ví dụ cơ bản, payload output thường là một **collection các payload**. Nó không tự tính một tổng tiền duy nhất. Nếu downstream cần một `OrderSummary`, phải thêm output processor hoặc một Transformer sau Aggregator.

### 6.2. Thời điểm phát message

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant S as Splitter
    participant T as Transformer
    participant G as Aggregator
    participant O as orders.aggregated

    P->>S: 3 OrderLine
    S->>T: Part A, sequence 1/3
    T->>G: PricedLine A
    Note over G: Chưa release
    S->>T: Part B, sequence 2/3
    T->>G: PricedLine B
    Note over G: Chưa release
    S->>T: Part C, sequence 3/3
    T->>G: PricedLine C
    Note over G: Group release
    G->>O: Một message tổng hợp
~~~

Đừng gắn logic gửi event thành công trong `releaseStrategy`; policy này có thể được gọi nhiều lần trong vòng đời nhóm. Gửi output là trách nhiệm của Aggregator và endpoint phía sau.

## 7. Kiểm thử output cố định qua MessageChannel

Unit test của `LinePricingPolicy` không thể chứng minh aggregator đã gửi output tới đúng channel. Dùng Spring Test, JUnit 5 và `QueueChannel` để xác minh wiring.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.Collection;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = FixedOutputAggregationConfig.class)
class FixedOutputAggregationTest {

    @Autowired
    @Qualifier("orders.lines.input")
    MessageChannel input;

    @Autowired
    @Qualifier("orders.aggregated")
    PollableChannel output;

    @Test
    void oneGroupProducesOneOutputOnChosenChannel() {
        List<OrderLine> lines = List.of(
                new OrderLine(
                        "SKU-A", new BigDecimal("100.00"), 2),
                new OrderLine(
                        "SKU-B", new BigDecimal("50.00"), 1),
                new OrderLine(
                        "SKU-C", new BigDecimal("25.00"), 3));

        assertTrue(input.send(
                MessageBuilder.withPayload(lines)
                        .setHeader("traceId", "trace-1001")
                        .build()));

        Message<?> aggregate = output.receive(1000);

        assertNotNull(aggregate);
        assertInstanceOf(
                Collection.class, aggregate.getPayload());

        Collection<?> values =
                (Collection<?>) aggregate.getPayload();
        assertEquals(3, values.size());

        Set<PricedLine> actual = values.stream()
                .map(PricedLine.class::cast)
                .collect(Collectors.toSet());

        assertEquals(Set.of(
                new PricedLine("SKU-A",
                        new BigDecimal("200.00")),
                new PricedLine("SKU-B",
                        new BigDecimal("50.00")),
                new PricedLine("SKU-C",
                        new BigDecimal("75.00"))), actual);

        assertNull(output.receive(0));
    }
}
~~~

Test xác minh một message chứa ba kết quả tới `orders.aggregated`. Nó **không** chứng minh DB đã commit, broker đã ack hoặc output sẽ tồn tại qua restart. Test fixtures dùng QueueChannel in-memory, không phải persistent broker.

### 7.1. Trường hợp chưa đủ part

Flow Splitter đồng bộ trong ví dụ thường xử lý mọi part trong một lần gửi. Để kiểm thử “chưa đủ nhóm”, tạo Aggregator nhận các `Message<PricedLine>` rời với `correlationId`/`sequenceNumber`/`sequenceSize` hợp lệ, hoặc dùng nguồn message độc lập cùng custom correlation/release. Trước khi đủ part, `receive(0)` ở output phải không có message.

### 7.2. Nhiều batch

Gửi hai batch A/B và xác nhận có **hai** message output riêng, không trộn nội dung. Nếu bật xử lý concurrent, test thêm trường hợp parts xen kẽ giữa hai group để xác nhận correlation strategy đúng.

## 8. Khi nào cần chọn output channel động?

Giả sử toàn bộ đơn được đánh giá theo **tổng tiền**:

- Tổng từ `1000.00` trở lên: `orders.highValue`.
- Tổng nhỏ hơn `1000.00`: `orders.standard`.

Mọi dòng hàng đều có thể nhỏ hơn 1000, nhưng **tổng của nhóm** có thể vượt ngưỡng. Đặt Router **trước** aggregation sẽ phân loại theo từng dòng riêng, không phải theo toàn đơn.

~~~mermaid
flowchart LR
    L["Các PricedLine"] --> A["Aggregator"]
    A --> T["Transformer: OrderSummary"]
    T --> R{"Router theo total"}
    R -->|"total >= 1000"| H["orders.highValue"]
    R -->|"total < 1000"| S["orders.standard"]
~~~

**Nguyên tắc:** khi quyết định destination phụ thuộc dữ liệu của cả group, hãy đưa Aggregator ra **một kết quả có kiểu rõ ràng**, sau đó đặt Router.

## 9. Tạo DTO tổng hợp trước khi route

### 9.1. OrderSummary

~~~java
import java.math.BigDecimal;
import java.util.List;

public record OrderSummary(
        List<PricedLine> lines,
        BigDecimal total
) {
    public OrderSummary {
        lines = List.copyOf(lines);
    }
}
~~~

Để tập trung vào cơ chế chọn output channel, DTO mẫu chưa chứa `orderId`. Với production, output nên có business group key đáng tin để trace/idempotency: ví dụ `orderId` hoặc composite `tenantId+orderId`.

### 9.2. SummaryAssembler

~~~java
import java.math.BigDecimal;
import java.util.Collection;
import java.util.Comparator;
import java.util.List;

public final class OrderSummaryAssembler {

    public OrderSummary assemble(Collection<?> parts) {
        if (parts == null || parts.isEmpty()) {
            throw new IllegalArgumentException(
                    "EMPTY_AGGREGATION_RESULT");
        }

        List<PricedLine> lines = parts.stream()
                .map(PricedLine.class::cast)
                .sorted(Comparator.comparing(PricedLine::sku))
                .toList();

        BigDecimal total = lines.stream()
                .map(PricedLine::lineTotal)
                .reduce(BigDecimal.ZERO, BigDecimal::add);

        return new OrderSummary(lines, total);
    }
}
~~~

Hàm này thuần túy chuyển **collection output** thành summary. Nó **không phải Aggregator endpoint** bởi không giữ các message trong MessageGroup và không quyết định release. Nó có thể được dùng ở bước Transformer sau Aggregator.

Việc sort theo SKU chỉ nhằm hiển thị ổn định. Nếu nghiệp vụ cần đúng thứ tự line ban đầu, hãy giữ `lineIndex` hoặc `sequenceNumber` đáng tin và sort theo khóa đó; không giả định arrival order luôn được giữ trong xử lý bất đồng bộ.

## 10. Router chọn channel theo dữ liệu đã gom

### 10.1. Router annotation

~~~java
import java.math.BigDecimal;

import org.springframework.integration.annotation.Router;

public final class OrderSummaryRouter {

    private static final BigDecimal HIGH_VALUE =
            new BigDecimal("1000.00");

    @Router(inputChannel = "orders.summary")
    public String destination(OrderSummary summary) {
        return summary.total().compareTo(HIGH_VALUE) >= 0
                ? "orders.highValue"
                : "orders.standard";
    }
}
~~~

`@Router` trả tên channel cho output message đã tổng hợp. Nó không nên lấy channel từ header do client chưa xác thực đưa vào, vì điều đó có thể cho phép gửi tới kênh nội bộ không được phép.

### 10.2. Cấu hình một flow động độc lập

~~~java
import java.util.Collection;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
public class DynamicOutputAggregationConfig {

    @Bean(name = "orders.dynamic.input")
    MessageChannel input() {
        return new DirectChannel();
    }

    @Bean(name = "orders.summary")
    MessageChannel summary() {
        return new DirectChannel();
    }

    @Bean(name = "orders.highValue")
    PollableChannel highValue() {
        return new QueueChannel();
    }

    @Bean(name = "orders.standard")
    PollableChannel standard() {
        return new QueueChannel();
    }

    @Bean
    LinePricingPolicy pricingPolicy() {
        return new LinePricingPolicy();
    }

    @Bean
    OrderSummaryAssembler summaryAssembler() {
        return new OrderSummaryAssembler();
    }

    @Bean
    OrderSummaryRouter router() {
        return new OrderSummaryRouter();
    }

    @Bean
    IntegrationFlow aggregateAndRoute(
            LinePricingPolicy pricing,
            OrderSummaryAssembler assembler) {

        return IntegrationFlow.from("orders.dynamic.input")
                .split()
                .transform(OrderLine.class, pricing::price)
                .aggregate()
                .transform(Collection.class, assembler::assemble)
                .channel("orders.summary")
                .get();
    }
}
~~~

Cách hoạt động:

1. `orders.dynamic.input` nhận List dòng hàng.
2. Splitter tạo message riêng, Transformer tạo PricedLine.
3. Aggregator release một collection.
4. Transformer `OrderSummaryAssembler` tạo `OrderSummary`.
5. Result đi đến `orders.summary`.
6. Router subscribe vào `orders.summary` và chọn `orders.highValue` hoặc `orders.standard`.

`orders.summary` ở đây là **channel trung gian cố định**, còn **đích nghiệp vụ cuối cùng là động**. Điều này không mâu thuẫn: mỗi endpoint có một trách nhiệm, Router là nơi chọn nhánh.

**Đây là cấu hình demo khác** với `FixedOutputAggregationConfig`; không đăng ký cả hai lên cùng một input channel hoặc tên bean bị trùng rồi kỳ vọng chúng tạo một chuỗi xử lý.

## 11. Integration test cho routing động

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = DynamicOutputAggregationConfig.class)
class DynamicOutputAggregationTest {

    @Autowired
    @Qualifier("orders.dynamic.input")
    MessageChannel input;

    @Autowired
    @Qualifier("orders.highValue")
    PollableChannel high;

    @Autowired
    @Qualifier("orders.standard")
    PollableChannel normal;

    @Test
    void routesHighValueOnlyToHighChannel() {
        List<OrderLine> lines = List.of(
                new OrderLine(
                        "SKU-A", new BigDecimal("500.00"), 2),
                new OrderLine(
                        "SKU-B", new BigDecimal("50.00"), 1));

        assertTrue(input.send(
                MessageBuilder.withPayload(lines).build()));

        Message<?> routed = high.receive(1000);
        assertNotNull(routed);
        assertInstanceOf(OrderSummary.class, routed.getPayload());
        OrderSummary summary =
                (OrderSummary) routed.getPayload();

        assertEquals(
                new BigDecimal("1050.00"), summary.total());
        assertEquals(2, summary.lines().size());

        assertNull(normal.receive(0));
        assertNull(high.receive(0));
    }

    @Test
    void routesStandardOnlyToStandardChannel() {
        List<OrderLine> lines = List.of(
                new OrderLine(
                        "SKU-C", new BigDecimal("100.00"), 2));

        assertTrue(input.send(
                MessageBuilder.withPayload(lines).build()));

        Message<?> routed = normal.receive(1000);
        assertNotNull(routed);
        assertInstanceOf(OrderSummary.class, routed.getPayload());

        OrderSummary summary =
                (OrderSummary) routed.getPayload();

        assertEquals(
                new BigDecimal("200.00"), summary.total());

        assertNull(high.receive(0));
        assertNull(normal.receive(0));
    }
}
~~~

Cần test thêm giá trị biên **999.99**, **1000.00** và **1000.01**. Với `BigDecimal.compareTo(...) >= 0`, đúng 1000.00 thuộc nhánh highValue. Nếu dùng `double`, phép tính tiền có thể chịu sai số, gây phân loại sai quanh ngưỡng.

### 11.1. Phân tầng test

| Tầng | Nội dung |
|---|---|
| Unit test `OrderSummaryAssembler` | Tính tổng đúng, xử lý collection rỗng |
| Unit test routing policy | Trả tên channel theo ngưỡng |
| Integration test Spring | Bean/channel wiring đúng và result chỉ vào một nhánh |
| Failure test | Không output khi thiếu part, lỗi processor, sai channel name |
| End-to-end test | Downstream xử lý/ack/DB idempotency đúng |

Hai integration test trên chỉ kiểm tra trong một ApplicationContext đồng bộ. Không suy ra chúng xác minh broker durability hay hành vi nhiều JVM.

## 12. Một channel chung rồi mới chia nhánh

Một số hệ thống muốn **mọi kết quả** đi qua một bước xác minh chung trước khi Router:

~~~mermaid
flowchart LR
    A["Aggregator"] --> C["orders.aggregated"]
    C --> V["OrderSummaryValidator"]
    V --> R{"Router"}
    R --> H["High value"]
    R --> S["Standard"]
    V -->|Invalid| E["Reject / error"]
~~~

Cách này có ích khi:

- Tất cả các output phải qua validation cho toàn nhóm.
- Cần ghi một metric/audit chung.
- Muốn chuẩn hóa schema output trước khi phân nhánh.
- Cần áp dụng một enrichment hoặc chính sách idempotency chung.
- Muốn thay đổi Router mà không sửa correlation/release logic của Aggregator.

**Không đưa logic routing nghiệp vụ vào release strategy.** Release strategy có thể được gọi mỗi khi group thay đổi và không nên chứa side effect hoặc chọn destination ở một điểm chưa có output payload hoàn chỉnh.

## 13. Output channel và replyChannel của Gateway

Một Gateway gửi request và thường chờ reply theo timeout. Nếu bên trong có Splitter → Aggregator, reply cuối có thể được đưa về Gateway khi topology được thiết kế phù hợp.

~~~mermaid
sequenceDiagram
    participant G as Gateway
    participant S as Splitter
    participant A as Aggregator
    participant R as ReplyChannel

    G->>S: Request + replyChannel
    S->>A: Part 1
    S->>A: Part 2
    S->>A: Part 3
    Note over A: Group release
    A-->>R: Aggregated result nếu reply routing hợp lệ
    R-->>G: Reply
~~~

Điều cần kiểm tra:

- Aggregator có **outputChannel cố định** hay không?
- Message output sau aggregate có còn **replyChannel** hợp lệ?
- Output processor có tạo `Message<?>` mới và làm mất header không?
- Khi group có parts từ nhiều nguồn, reply headers có mâu thuẫn không?
- Gateway timeout có phù hợp thời gian cần để nhóm hoàn tất không?

### 13.1. Vì sao một output cố định có thể làm Gateway timeout?

Giả sử Gateway gửi request có replyChannel tạm, nhưng flow cấu hình:

~~~java
.aggregate()
.channel("orders.aggregated")
~~~

Kết quả được dispatch tới `orders.aggregated`. Gateway **không tự nhận một bản sao** chỉ vì request ban đầu có replyChannel. Nếu channel đó chỉ có consumer khác không trả kết quả về Gateway, Gateway có thể timeout. Cần chọn một **đường reply tường minh**, hoặc thiết kế result được gửi ở một event/queue khác và caller truy vấn trạng thái.

### 13.2. Khi nào không nên chờ reply đồng bộ?

Một batch gồm vài dòng có thể gom nhanh và trả reply trong thời gian ngắn. Nhưng khi group chờ `PaymentCaptured` và `InventoryReserved` từ những producer độc lập, thời gian có thể là nhiều phút hoặc lâu hơn. Không nên giữ HTTP request hoặc Gateway thread chờ không giới hạn.

Một mô hình phù hợp hơn:

~~~text
POST /orders/ORDER-1001/complete
  -> 202 Accepted + trackingId

OrderRegistered / PaymentCaptured / InventoryReserved
  -> Aggregator theo orderId
  -> OrderReady event
  -> Status store / outbound adapter

Client:
  GET /orders/ORDER-1001/status
~~~

Trong mô hình này, output channel sau Aggregator thường nối tới broker/event handler, **không phải reply channel tạm** của request HTTP đã kết thúc.

### 13.3. Headers của nhiều part không giống nhau

Một group có thể chứa part của ba producer, mỗi part có `replyChannel`, `traceId` và `errorChannel` khác nhau. Aggregator không thể tự biết Gateway nào là đích đúng cho **cả nhóm** nếu metadata không có hợp đồng thống nhất.

Trong mô hình nhiều nguồn độc lập, thường nên cấu hình **output channel cố định** và có business correlation/tracking ID rõ ràng thay vì lấy replyChannel ngẫu nhiên của một part.

## 14. Kiểm soát headers sau aggregation

Một aggregated output message không phải “part đến cuối được forward”. Framework phải xử lý metadata của **nhiều message đầu vào**. Các giá trị header không nhất quán có thể bị loại hoặc xử lý theo chính sách aggregate headers; do đó không nên mặc định header của mọi part được giữ nguyên.

| Header | Ý nghĩa | Nguyên tắc sau aggregation |
|---|---|---|
| `correlationId` | Liên kết group hoặc batch split | Kiểm tra contract nhóm/result |
| `sequenceNumber` | Thứ tự một part | Không coi là thứ tự output message |
| `sequenceSize` | Số part dự kiến | Không tự suy nó biểu diễn output mới |
| `traceId` | Theo dõi span/flow | Chọn trace context nhất quán |
| `businessCorrelationId` | ID nghiệp vụ của group | Tạo từ business key đáng tin |
| `replyChannel` | Địa chỉ nhận reply | Chỉ dùng nếu output có header hợp lệ |
| `errorChannel` | Đường thông báo lỗi | Không chuyển mù qua boundary |
| `tenantId` | Phạm vi quyền truy cập | Kiểm tra chung toàn group |
| `MessageHeaders.ID` | Định danh message instance | Không dùng thay event ID |
| `routingHint` | Gợi ý đích xử lý | Chỉ tin giá trị đã được tính/xác thực |

### 14.1. Không route theo header của part cuối

Giả sử Order và Payment có metadata khác nhau, nhưng part Inventory tới sau cùng. Nếu dùng `priority` từ Inventory làm kết luận cho OrderReady, output có thể bị đưa sai nhánh.

Cách an toàn:

1. Correlation strategy gom đúng các part cùng business group.
2. Release strategy đảm bảo có đủ dữ kiện bắt buộc.
3. Output processor tạo DTO kết quả từ **toàn nhóm**.
4. Router dùng DTO đã được xác minh để chọn destination.

### 14.2. Custom output Message

Một output processor có thể trả một `Message<?>` được xây chủ động:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

// Đoạn minh họa trong một phương thức xử lý:
Message<OrderSummary> output = MessageBuilder
        .withPayload(summary)
        .setHeader("businessCorrelationId", trustedGroupKey)
        .setHeader("schemaVersion", 1)
        .build();
~~~

`summary` và `trustedGroupKey` là biến đã được tính theo hợp đồng bên ngoài snippet. Khi tạo Message mới, **cần chủ động giữ những header cần thiết**. Không copy mù tất cả headers của một part, đặc biệt ở ranh giới broker/cross-JVM với `replyChannel` hoặc object Java không serializable.

## 15. Output cho nhiều subscriber

Nếu một kết quả tổng hợp cần đến Audit, Analytics và Notification, có thể dùng `PublishSubscribeChannel` sau Aggregator:

~~~mermaid
flowchart LR
    G["Aggregator"] --> P(("PublishSubscribeChannel"))
    P --> A["Audit"]
    P --> N["Notification"]
    P --> M["Analytics"]
~~~

Lưu ý:

- Publish–Subscribe phát đến những subscriber đang đăng ký, không lưu lịch sử.
- Không có executor thì dispatch thường đồng bộ, một subscriber lỗi có thể ảnh hưởng nhánh khác tùy cấu hình.
- Có executor thì gửi thành công ở cấp channel không có nghĩa mọi handler đã hoàn tất.
- Những nhánh có side effect phải idempotent nếu output có thể bị redeliver.
- Nếu output cần durable delivery, broker/outbox đáng tin cậy thường cần thiết.

Đừng thay Router bằng Publish–Subscribe nếu business cần **chọn đúng một đích**, và đừng dùng Router nếu business cần **phát cho mọi subscriber**.

## 16. Output qua QueueChannel hoặc ExecutorChannel

### 16.1. QueueChannel

`QueueChannel` nhận output rồi chờ poller/consumer lấy tiếp. Nó hữu ích để tách nhịp xử lý hoặc làm test fixture, nhưng mặc định là queue in-memory. Nếu không có poller, message có thể nằm trong queue mà không handler nào thực thi.

### 16.2. ExecutorChannel

`ExecutorChannel` cho phép việc dispatch đến consumer chạy qua thread pool. Cần quản lý:

- Kích thước pool và queue capacity hữu hạn.
- Backpressure/rejection policy.
- Timeout và error handling trên worker.
- Ordering khi các group output xử lý đồng thời.
- Tracing/correlation qua thread boundary.

Không coi `send()==true` là bằng chứng rằng worker đã commit DB. Đo kết quả xử lý tại handler hoặc ack của broker.

### 16.3. Adapter đến broker

Đặt một outbound adapter sau channel cho phép phát aggregate output tới hệ thống ngoài. Nhưng channel nội bộ không phải transaction outbox. Nếu broker ack thành công mà DB fail, hoặc ngược lại, có thể cần outbox/idempotency theo yêu cầu nghiệp vụ.

## 17. Nhóm chưa đủ, timeout và partial result

Nếu release strategy trả `false`, Aggregator **chưa phát kết quả thành công**. Việc lựa chọn output channel chỉ có nghĩa khi có một result cần gửi.

~~~mermaid
flowchart TD
    G["MessageGroup"] --> R{"Release?"}
    R -->|Đủ| O["Complete result"]
    O --> C["orders.completed"]
    R -->|Chưa đủ| W["Chờ part tiếp"]
    W --> T{"Timeout/expiry?"}
    T -->|Chưa| W
    T -->|Rồi| P{"Cho phép partial?"}
    P -->|Có, đã cấu hình| I["Partial result"]
    I --> IC["orders.incomplete"]
    P -->|Không| E["Expiry/discard/monitor"]
~~~

Partial result chỉ nên gửi nếu **downstream biết đó là partial**. Một analytics report có thể cho phép thiếu dữ liệu, nhưng lệnh giao hàng không được đánh dấu “ready” khi thiếu InventoryReserved.

### 17.1. Kết quả có trạng thái tường minh

~~~java
public enum CompletionStatus {
    COMPLETE,
    PARTIAL
}

public record AggregationOutcome<T>(
        CompletionStatus status,
        T value,
        String reasonCode
) {}
~~~

Các kiểu top-level `public` trong snippet cần source file riêng khi đưa vào project. Đây là kiểu domain minh họa, không phải class có sẵn của Spring Integration.

Nếu group có thể phát partial, Router sau Aggregator cần xem `status`:

~~~text
AggregationOutcome(COMPLETE) -> orders.completed
AggregationOutcome(PARTIAL)  -> orders.incomplete
~~~

Không chỉ dựa vào số lượng message rồi gửi vào cùng một channel success. Cấu hình timeout, expiry và send-partial cụ thể phụ thuộc nghiệp vụ và phiên bản Spring Integration đang dùng, cần integration test.

### 17.2. Error channel không phải đường partial

- **Error**: output processor/handler ném exception hoặc dispatch thất bại.
- **Incomplete**: nhóm chưa có đủ dữ liệu khi đến hạn.
- **Partial result**: kết quả nghiệp vụ có chủ đích từ một nhóm chưa đầy đủ.
- **Discard**: nhánh loại theo cấu hình.

Bốn trường hợp không nên trộn trong một success channel rồi để consumer tự suy đoán.

## 18. Late arrivals, duplicate và correction

Nếu Aggregator đã phát `OrderReady` mà một part tới muộn hoặc được replay, tùy group lifecycle có thể phát sinh một nhóm mới, bỏ part hoặc một kết quả khác. Điều đó ảnh hưởng trực tiếp tới output channel và side effect.

~~~text
OrderReady hoàn chỉnh -> orders.ready.events
Bản sửa sau đó       -> orders.corrections
Duplicate đã biết    -> dedup / reject
~~~

Một sự kiện correction phải có hợp đồng riêng; không phát lại như một kết quả hoàn tất mới mà không đánh dấu version/correction.

### 18.1. Idempotency

- Dùng `eventId` ổn định để deduplicate các input part.
- Dùng `(tenantId, orderId)` hoặc business key thích hợp để correlation.
- Dùng output event ID/version ổn định để downstream xử lý idempotent.
- Có chính sách group completion/tombstone/retention cho late arrivals.
- Tách transaction/ack của broker và DB, bổ sung outbox nếu cần.

**Aggregator không tự bảo đảm exactly-once side effect**. Một output được gửi hai lần tới cùng handler có thể gây hai email hoặc hai giao dịch nếu downstream không tự phòng ngừa.

## 19. Trường hợp ba nguồn sự kiện độc lập

Một đơn chỉ sẵn sàng giao khi nhận đủ:

- `OrderRegistered(orderId)`.
- `PaymentCaptured(orderId)`.
- `InventoryReserved(orderId)`.

~~~mermaid
flowchart LR
    A["OrderRegistered"] --> G["Aggregator by orderId"]
    B["PaymentCaptured"] --> G
    C["InventoryReserved"] --> G
    G -->|"đủ loại bắt buộc"| O["OrderReady"]
    O --> CH["orders.ready.events"]
    CH --> PUB["Broker adapter / consumer"]
~~~

Trong trường hợp này, nên:

1. Correlate theo `orderId` hoặc composite key có tenant đáng tin cậy.
2. Release khi đủ **loại dữ liệu**, không chỉ khi `group.size()==3` vì duplicate Payment không thay được Inventory.
3. Output processor tạo `OrderReady` với schema ổn định.
4. Chọn một output channel cố định `orders.ready.events` nếu tất cả kết quả hoàn tất cần phát cùng loại event.
5. Tạo đường xử lý **timeout/partial/correction** riêng.
6. Dùng persistent MessageGroupStore nếu phải khôi phục nhóm qua restart.
7. Dùng idempotency khi input/output có thể redeliver.

**Không chọn đích theo loại part đến cuối.** Cùng một group có thể nhận Payment cuối hoặc Inventory cuối; kết quả nghiệp vụ vẫn là `OrderReady`, không phải kết quả riêng của producer cuối.

## 20. Phát hiện lỗi: group đã release nhưng output ở đâu?

~~~mermaid
flowchart TD
    A["Không thấy output"] --> B{"Group đã release?"}
    B -->|Chưa| C["Kiểm tra correlation/release/part thiếu"]
    B -->|Rồi| D{"Output processor thành công?"}
    D -->|Không| E["Xem exception/error flow"]
    D -->|Rồi| F{"Destination hợp lệ?"}
    F -->|Không| H["Tên channel/replyChannel"]
    F -->|Có| I{"Có consumer/poller?"}
    I -->|Không| J["Kiểm tra lifecycle, poller"]
    I -->|Có| K["Kiểm tra executor/broker/downstream"]
~~~

### 20.1. Sai bean name của channel

**Triệu chứng:** Router chọn `orders.complete` nhưng cấu hình tạo `orders.completed`. Cần test tất cả branches, không chỉ branch chuẩn.

### 20.2. QueueChannel không có poller

**Triệu chứng:** Aggregator gửi vào queue, nhưng downstream không thực thi. Cần poller hoặc consumer `receive()` thực sự; QueueChannel không phải DirectChannel.

### 20.3. DirectChannel không có subscriber

**Triệu chứng:** message dispatch failure vì không có consuming endpoint. Kiểm tra bean wiring và lifecycle.

### 20.4. Gateway timeout dù queue có result

**Triệu chứng:** result ở channel cố định nhưng Gateway không nhận reply. Kiểm tra output channel precedence và thiết kế reply flow.

### 20.5. Không có result vì nhóm chưa đủ

**Triệu chứng:** output queue rỗng, group store còn message. Cần kiểm tra `sequenceSize`, các part bị Filter loại, correlation nhầm, timeout và release strategy.

### 20.6. Output processor tạo Message mới làm mất metadata

**Triệu chứng:** mất business correlation/trace hoặc replyChannel. Kiểm thử headers trên **aggregated output**, không chỉ headers ở input part.

### 20.7. Executor/broker lỗi ở thread khác

**Triệu chứng:** producer thấy `send()==true`, nhưng DB chưa ghi. Theo dõi error channel, consumer error, retry, backlog và handler outcome.

### 20.8. Output xuất hiện hai lần

**Triệu chứng:** phát email trùng sau retry/redelivery. Kiểm tra duplicate/late-arrival policy và idempotency của output handler.

## 21. Kiểm thử toàn bộ topology

Không chỉ test output policy. Các tình huống quan trọng:

| Ca kiểm thử | Điều cần chứng minh |
|---|---|
| Một group đủ part | Một output đúng kiểu tới channel mong đợi |
| Chưa đủ part | Không có success output |
| Hai group xen kẽ | Không bị trộn |
| Đúng ngưỡng 1000.00 | Route highValue |
| Dưới ngưỡng 999.99 | Route standard |
| Router trả channel không tồn tại | Lỗi được quan sát |
| Output processor lỗi | Không phát success output sai |
| Một part bị Filter loại | Nhóm chờ/timeout theo policy |
| Headers có xung đột | Không reply/routing theo metadata bất kỳ |
| Gateway cần reply | Output thực sự tới reply path |
| Group hết hạn | Partial/expired đi nhánh riêng |
| Message đến muộn | Correction/reject theo contract |
| Broker redelivery | Idempotency ngăn side effect trùng |
| Executor quá tải | Có backpressure/rejection policy |

### 21.1. Unit test cho chính sách route

Nếu muốn policy độc lập với annotation, có thể tách:

~~~java
import java.math.BigDecimal;

public final class OrderOutputPolicy {

    private static final BigDecimal HIGH_VALUE =
            new BigDecimal("1000.00");

    public String choose(OrderSummary summary) {
        return summary.total().compareTo(HIGH_VALUE) >= 0
                ? "orders.highValue"
                : "orders.standard";
    }
}
~~~

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;
import java.util.List;

import org.junit.jupiter.api.Test;

class OrderOutputPolicyTest {

    private final OrderOutputPolicy policy =
            new OrderOutputPolicy();

    @Test
    void handlesBoundary() {
        assertEquals("orders.highValue",
                policy.choose(new OrderSummary(
                        List.of(),
                        new BigDecimal("1000.00"))));
        assertEquals("orders.standard",
                policy.choose(new OrderSummary(
                        List.of(),
                        new BigDecimal("999.99"))));
    }
}
~~~

Unit test policy rất nhanh, nhưng **không xác nhận** những channel names đó thật sự có bean và consumer. Integration test phải bao phủ phần wiring.

## 22. Quan sát output của Aggregator

Một bộ metric/log nên tách rõ trạng thái group và dispatch:

| Chỉ số | Ý nghĩa |
|---|---|
| `aggregation_groups_open` | Số nhóm đang chờ |
| `aggregation_groups_released_total` | Số nhóm đạt release condition |
| `aggregation_output_created_total` | Số message kết quả tạo ra |
| `aggregation_output_sent_total{channel}` | Số output được dispatch theo channel |
| `aggregation_output_failed_total{channel,type}` | Lỗi dispatch/output processor |
| `aggregation_group_expired_total` | Số nhóm timeout/expiry |
| `aggregation_partial_total` | Số kết quả partial |
| `aggregation_late_arrival_total` | Số part đến sau group đóng |
| `downstream_completed_total{consumer}` | Business handler hoàn tất |

Metric nên dùng những labels có cardinality thấp như channel type, reason code, outcome. Không đưa `orderId`, `eventId` hoặc `traceId` làm metric label tùy ý; để truy vết message cụ thể, dùng logs/traces có chính sách dữ liệu phù hợp.

Ví dụ log:

~~~text
flow=order-aggregation
groupKey=tenant-a/ORDER-1001
release=true
outputType=OrderSummary
destination=orders.highValue
dispatch=SUCCESS
downstreamOutcome=PENDING
traceId=trace-1001
~~~

Dòng log này chỉ nói **message đã dispatch**, chưa chứng minh downstream commit thành công. Ghi outcome thực ở handler sau khi công việc kết thúc.

## 23. Bài tập thực hành

**Bài 1 — Channel cố định.** Dựng `FixedOutputAggregationConfig`, gửi batch ba dòng. Assert một message ở `orders.aggregated`, payload chứa đủ ba PricedLine.

**Bài 2 — DTO sau aggregation.** Dùng `OrderSummaryAssembler` để tính total. Nêu rõ vì sao Transformer sau Aggregator không thay thế cơ chế MessageGroup/release.

**Bài 3 — Routing theo ngưỡng.** Dựng `DynamicOutputAggregationConfig` và Router. Test tổng 999.99, 1000.00, 1000.01.

**Bài 4 — Router sai vị trí.** Đặt Router trước Aggregator, gửi nhiều dòng nhỏ có tổng lớn. Giải thích khác biệt giữa routing từng part và routing cả group.

**Bài 5 — Gateway.** Tạo request–reply flow có Aggregator. Kiểm tra điều kiện replyChannel hợp lệ; sau đó đặt output channel cố định và giải thích vì sao Gateway có thể timeout.

**Bài 6 — Header mapping.** Gửi các part có traceId, businessCorrelationId và replyChannel. Xác minh headers output theo contract, nhất là khi output processor tự tạo Message mới.

**Bài 7 — Queue/poller.** Đổi output sang QueueChannel, bổ sung poller, theo dõi thời điểm phát output và thời điểm consumer hoàn tất.

**Bài 8 — Publish–Subscribe.** Gửi một aggregate output cho Audit và Analytics; xử lý lỗi từ một subscriber, không nhầm điều kiện send với side effect thành công.

**Bài 9 — Partial/expired.** Cấu hình group timeout, cho phép partial theo business case và route sang `orders.incomplete`. Không đưa dữ liệu thiếu vào `orders.completed`.

**Bài 10 — Two groups.** Gửi parts của A/B xen kẽ; bảo đảm mỗi group cho một output đúng business key và đúng channel.

**Bài 11 — Late arrival.** Gửi part muộn sau khi group đóng; thiết kế correction/dedup thay vì phát lại đơn hoàn chỉnh như mới.

**Bài 12 — Durable output.** Kết nối outbound adapter đến broker và thiết kế idempotency/outbox theo yêu cầu. Mô phỏng lỗi giữa gửi event và ghi database.

### Câu hỏi tự kiểm tra

1. Aggregator chọn output ở giai đoạn nào?
2. Correlation strategy và output channel trả lời hai câu hỏi khác nhau thế nào?
3. `.aggregate().channel("orders.aggregated")` có nghĩa gì?
4. Sau Splitter, output mặc định của Aggregator thường có payload kiểu nào?
5. Khi nào cần Transformer sau Aggregator?
6. Khi nào cần Router sau Aggregator?
7. Vì sao Router theo tổng tiền đặt trước Aggregator có thể sai?
8. `outputChannel` và `replyChannel` khác nhau thế nào?
9. Tại sao Gateway có thể timeout dù output đã vào một queue?
10. Vì sao replyChannel của các part không nhất thiết là replyChannel của output?
11. QueueChannel có tự gọi downstream handler không?
12. Khi group chưa release, channel success có output không?
13. Partial result cần được đánh dấu và route thế nào?
14. Tại sao không gửi `OrderReady` khi chưa có InventoryReserved?
15. Late arrival và duplicate có thể gây hệ quả gì?
16. `send()==true` có chứng minh DB commit không?
17. Nên kiểm soát header nào khi output processor tạo Message mới?
18. Cần test gì để phân biệt lỗi thiếu part với lỗi không có consumer?

## 24. Checklist trước khi triển khai

- [ ] Phân biệt rõ correlation, release, output processing và output channel.
- [ ] Output payload có schema và business group key tin cậy.
- [ ] Dùng channel cố định khi mọi result đi cùng processing stage.
- [ ] Dùng Router sau Aggregator nếu đích phụ thuộc toàn nhóm.
- [ ] Không nhét side effect vào release strategy.
- [ ] Không gửi success output khi group chưa đủ.
- [ ] Partial, expired, error và correction có hợp đồng riêng.
- [ ] Output channel, replyChannel, errorChannel, discardChannel không bị trộn nghĩa.
- [ ] Gateway có timeout, reply path và header propagation hợp lệ.
- [ ] Không dùng header của part cuối làm đại diện tự động cho nhóm.
- [ ] Có consumer/poller phù hợp với loại channel đầu ra.
- [ ] Backpressure, retries, queue depth và worker errors đã được xác định.
- [ ] Broker/outbox được cân nhắc nếu cần durable delivery.
- [ ] Idempotency downstream xử lý được retry/redelivery.
- [ ] Có unit test output policy và integration tests fixed/dynamic/Gateway.
- [ ] Có test duplicate, missing part, timeout, late arrival và nhiều group.
- [ ] Có metric group released, output sent, dispatch errors và downstream completion.
- [ ] Không đưa thông tin nhạy cảm hoặc ID cardinality cao vào metric label.

## 25. Tổng kết

**Chọn output channel sau aggregation** là quyết định **kết quả của một MessageGroup sẽ đi đâu**. Quyết định đó xảy ra sau khi Aggregator xác định nhóm theo correlation, đánh giá release condition và tạo aggregated output. Với kết quả đi chung một tuyến, Java DSL `.aggregate().channel("orders.aggregated")` thể hiện một đích cố định. Khi business cần chọn nhánh theo **tổng kết quả**, hãy tạo DTO tường minh rồi dùng **Router** sau aggregation.

Nếu cần trả về Gateway, output message phải có **replyChannel hợp lệ** và topology không được vô tình chuyển output cố định đến nơi khác. Group chưa đủ không có success output; partial/expired/error không được phát vào nhánh complete mà không có hợp đồng. Loại channel được chọn còn ảnh hưởng sync/async, consumer lifecycle, durability và retry.

Khi bảo toàn correlation/headers, kiểm thử đường đi thực và thiết kế idempotency cho downstream, Aggregator có thể phối hợp an toàn với Splitter, Filter, Transformer, Router, Gateway và error channel của module **SPRING_INTEGRATION_PATTERN**, tạo các luồng dễ mở rộng và dễ chẩn đoán.

### Tài liệu tham khảo

- Spring Integration Reference — Aggregator: https://docs.spring.io/spring-integration/reference/aggregator.html
- Spring Integration Reference — Splitter: https://docs.spring.io/spring-integration/reference/splitter.html
- Spring Integration Reference — Java DSL: https://docs.spring.io/spring-integration/reference/dsl.html
- Spring Integration Reference — Router: https://docs.spring.io/spring-integration/reference/router.html
- Spring Integration Reference — Message Channels: https://docs.spring.io/spring-integration/reference/channel/implementations.html
- Spring Integration Reference — Gateway: https://docs.spring.io/spring-integration/reference/gateway.html
- Spring Integration Reference — Message Store: https://docs.spring.io/spring-integration/reference/message-store.html
- Spring Integration API — AbstractCorrelatingMessageHandler: https://docs.spring.io/spring-integration/api/org/springframework/integration/aggregator/AbstractCorrelatingMessageHandler.html
- Spring Integration API — DefaultAggregatingMessageGroupProcessor: https://docs.spring.io/spring-integration/api/org/springframework/integration/aggregator/DefaultAggregatingMessageGroupProcessor.html

