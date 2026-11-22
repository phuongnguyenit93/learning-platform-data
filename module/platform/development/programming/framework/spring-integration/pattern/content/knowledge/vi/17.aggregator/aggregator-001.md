# Aggregator gom nhiều message thành một kết quả

Trong **Spring Integration**, **Aggregator** là một endpoint hiện thực Enterprise Integration Pattern **Aggregator**: nó nhận **nhiều message có liên quan**, lưu chúng vào một *message group*, chờ tới khi nhóm thỏa điều kiện hoàn thành rồi phát **một message kết quả tổng hợp**. Đây là lời giải cho những tình huống như một đơn hàng có nhiều dòng chi tiết, nhiều kết quả xử lý song song phải hội tụ, hoặc các sự kiện thanh toán – tồn kho – đơn hàng đến ở những thời điểm khác nhau.

Bài này thuộc chương **Aggregator** của module **SPRING_INTEGRATION_PATTERN**. Module học cách triển khai EIP với Spring Integration để tạo luồng thông điệp ít phụ thuộc, dễ mở rộng; thực hành Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation, đồng thời kiểm thử và theo dõi các nhánh xử lý.

Điều quan trọng nhất không phải chỉ là gọi phương thức `aggregate()`, mà là xác định **những message nào thuộc cùng một nhóm**, **khi nào nhóm được xem là đủ**, **đầu ra phải có hình dạng gì**, và **cách xử lý nhóm bị thiếu, trùng, tới muộn hoặc hết hạn**.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Giải thích Aggregator theo mô hình **N message → một kết quả** và phân biệt nó với Splitter, Transformer, Content Enricher, Router và Publish–Subscribe.
2. Mô tả vòng đời một `MessageGroup`: tạo nhóm, nhận phần tử, đánh giá release, phát output và hoàn tất/expire group.
3. Thiết kế **correlation strategy** để các message cùng nghiệp vụ vào đúng nhóm mà không trộn nhóm của nhiều tenant/đơn hàng.
4. Thiết kế **release strategy** để tránh phát kết quả khi thiếu thông tin hoặc có message trùng.
5. Hiểu vai trò của **aggregation output processor**: tạo payload kết quả từ tập các message đã gom.
6. Hiểu `correlationId`, `sequenceNumber`, `sequenceSize` do Splitter cung cấp và giới hạn khi dùng chúng cho event độc lập.
7. Cấu hình luồng `Splitter → Transformer → Aggregator` bằng Spring Integration Java DSL và thử nghiệm qua channel.
8. Xây mô hình hội tụ nhiều sự kiện `OrderRegistered`, `PaymentCaptured` và `InventoryReserved`.
9. Xử lý timeout, incomplete groups, duplicate, late arrival, concurrency, persistence, retry và idempotency.
10. Viết unit test cho quy tắc nhóm/assemble và integration test cho luồng thực.

## 2. Aggregator giải quyết bài toán gì?

Giả sử một đơn có ba dòng hàng:

~~~text
OrderLines(orderId=ORDER-1001)
  - SKU-A, quantity=2, unitPrice=100.00
  - SKU-B, quantity=1, unitPrice=50.00
  - SKU-C, quantity=3, unitPrice=25.00
~~~

Hệ thống dùng Splitter tách batch thành ba message và tính tổng từng dòng. Đến một thời điểm, downstream cần nhận **một kết quả cho cả đơn**, chẳng hạn:

~~~text
OrderPriceResult(
  orderId=ORDER-1001,
  lines=[
    SKU-A: 200.00,
    SKU-B:  50.00,
    SKU-C:  75.00
  ],
  total=325.00
)
~~~

Để tạo kết quả ấy, không thể chỉ dùng một `MessageFilter` hoặc một `Router`. Cần tập hợp các dòng đã xử lý thành một nhóm, chờ đủ rồi tổng hợp:

~~~mermaid
flowchart LR
    B["Order batch"] --> S["Splitter"]
    S --> A["Line A"]
    S --> C["Line B"]
    S --> D["Line C"]
    A --> T["Transformer: priced line"]
    C --> T
    D --> T
    T --> G["Aggregator"]
    G -->|"đủ nhóm"| O["Một kết quả"]
~~~

Với các nguồn độc lập, ý tưởng vẫn giống nhau nhưng thời gian chờ không được xác định trước:

~~~mermaid
flowchart LR
    O["OrderRegistered"] --> G["Aggregator"]
    P["PaymentCaptured"] --> G
    I["InventoryReserved"] --> G
    G --> M["MessageGroup theo orderId"]
    M --> R{"Đủ ba loại?"}
    R -->|"Chưa"| W["Giữ trạng thái, chờ"]
    R -->|"Rồi"| OUT["OrderReady"]
~~~

**Aggregator không đơn thuần là phép nối List.** Nó còn sở hữu trách nhiệm **nhóm, tích lũy, hoàn tất và quản lý vòng đời** trong môi trường message có thể đến không đồng bộ.

### 2.1. Định nghĩa theo ba câu hỏi

Một Aggregator phải trả lời được:

- **Nhóm nào?** `correlationStrategy(message) → groupKey`.
- **Khi nào đủ?** `releaseStrategy(messageGroup) → boolean`.
- **Kết quả là gì?** `outputProcessor(messageGroup) → output`.

Nếu không xác định ba điều này, một aggregator có thể đợi mãi, release sớm, trộn đơn khác nhau hoặc trả dữ liệu downstream không hiểu.

## 3. So sánh Aggregator với các EIP liên quan

| Pattern | Trách nhiệm | Hình dạng điển hình |
|---|---|---|
| **Splitter** | Tách một message thành nhiều phần | 1 → N |
| **Aggregator** | Tập hợp các message liên quan và phát kết quả | N → 1 |
| **Content Enricher** | Thêm dữ liệu tra cứu vào một message hiện có | 1 → 1, có lookup |
| **Transformer** | Chuyển đổi payload hoặc message | 1 → 1 hoặc tạo collection tùy contract |
| **Filter** | Cho qua hoặc loại message | 1 → 1 hay 1 → 0 |
| **Router** | Chọn channel đích | 1 → một/một số đích theo cấu hình |
| **Publish–Subscribe** | Gửi message đến các subscriber | Một lần phát → nhiều consumer |
| **Gateway** | Liên kết request–reply với ứng dụng | Request → Reply |
| **Resequencer** | Sắp xếp lại các message liên quan | N message → N message đúng thứ tự |

Ví dụ, một Transformer nhận một `List<OrderLine>` và tính tổng ngay trong bộ nhớ **không phải Aggregator theo nghĩa messaging** nếu không có các message riêng cần gom. Một Content Enricher gọi API để lấy customer tier cho một đơn **không cần MessageGroup**. Ngược lại, ba event phát từ ba producer riêng **cần cơ chế chờ và tương quan** nếu output chỉ hợp lệ khi cả ba đã đến.

**Lưu ý:** ký hiệu N→1 mô tả một nhóm **hoàn tất thành công**. Trường hợp timeout, reject, discard hoặc partial release có thể tạo đầu ra khác, hoặc không có output theo hợp đồng.

## 4. Ba thành phần cốt lõi của Aggregator

### 4.1. Correlation strategy — chọn đúng nhóm

Mỗi message phải được gán một **group key**. Với từng dòng hàng, key thường là batch correlation ID. Với các sự kiện của đơn hàng, key có thể là `orderId`.

~~~text
Message A: orderId=ORDER-1001 -> group ORDER-1001
Message B: orderId=ORDER-1002 -> group ORDER-1002
Message C: orderId=ORDER-1001 -> group ORDER-1001
~~~

Không được đưa C vào nhóm ORDER-1002. Trong hệ thống đa tenant, nếu order IDs chỉ duy nhất **trong mỗi tenant**, key cần gồm cả tenant đáng tin cậy:

~~~java
public record GroupKey(String tenantId, String orderId) {}
~~~

Không dùng `MessageHeaders.ID` riêng của từng message làm group key cho những sự kiện cần gom, bởi mỗi message có ID khác nhau.

### 4.2. Release strategy — nhóm đã đủ chưa?

Khi group có thêm message, Aggregator phải quyết định đã đủ điều kiện tạo kết quả hay chưa. Với dữ liệu sau Splitter, có thể dùng sequence metadata: `sequenceSize` cho biết số lượng phần tử mong đợi.

Với các event độc lập, một điều kiện kiểu `group.size() == 3` thường **chưa đủ an toàn**. Ba message có thể gồm hai `PaymentCaptured` trùng và một `OrderRegistered`, trong khi `InventoryReserved` còn thiếu. Release strategy phải kiểm tra **đúng thành phần** mà output cần.

### 4.3. Output processor — tạo kết quả mới

Sau khi nhóm đủ, Aggregator dùng các message trong group để tạo output:

~~~text
MessageGroup
  + PricedLine(SKU-A, 200.00)
  + PricedLine(SKU-B,  50.00)
  + PricedLine(SKU-C,  75.00)

Output processor
  -> OrderPriceResult(orderId, lines, total=325.00)
~~~

Kết quả có thể là collection payloads, DTO tổng hợp, hoặc một `Message<?>` có header phù hợp. Output processor phải xác định **schema, thứ tự dữ liệu nếu cần, cách xử lý header và quy tắc duplicate**.

## 5. Vòng đời của một MessageGroup

Spring Integration lưu trữ các message liên quan trong một `MessageGroup`. Các nhóm được quản lý thông qua `MessageGroupStore`; cơ chế lưu thực tế phụ thuộc cấu hình.

~~~mermaid
flowchart TD
    IN["Message tới Aggregator"] --> K["Tính correlation key"]
    K --> G{"Đã có group?"}
    G -->|Chưa| NEW["Tạo group"]
    G -->|Có| ADD["Thêm vào group"]
    NEW --> ADD
    ADD --> R{"Release condition đúng?"}
    R -->|Không| WAIT["Giữ group, chờ message khác"]
    R -->|Có| BUILD["Output processor"]
    BUILD --> SEND["Phát message tổng hợp"]
    SEND --> COMPLETE["Hoàn tất/cleanup group theo cấu hình"]
    WAIT --> TIME{"Timeout / expiry?"}
    TIME -->|Chưa| IN
    TIME -->|Rồi| EXPIRE["Expire / partial / discard / cảnh báo"]
~~~

Một group có thể được tạo khi message đầu tiên tới, tiếp tục nhận nhiều phần và chỉ phát output sau một khoảng thời gian. Do đó, Aggregator là **một endpoint có trạng thái** theo nghĩa nó quản lý các nhóm đang mở.

### 5.1. State nằm ở đâu?

- Trong ví dụ/test đơn giản, có thể dùng message store trong bộ nhớ.
- Nếu cần sống sót sau restart, phải thiết kế **persistent MessageGroupStore** tương thích môi trường.
- Nếu nhiều instance cùng xử lý một nhóm, cần xem xét shared store, locking, transaction và concurrent delivery.
- Nếu nhóm không bao giờ đủ, phải có **timeout/expiry policy**; nếu không, store có thể tăng không giới hạn.
- Nếu group đã hoàn tất nhưng message tới muộn, cần quy tắc xử lý thay vì tùy tiện mở lại.

**Không giả định Aggregator tự tạo durable queue.** Message store, retry, acknowledgement và broker có vai trò khác nhau.

### 5.2. Một nhóm không đồng nghĩa một transaction toàn hệ thống

Aggregator có thể lưu đủ message, phát output rồi downstream ghi database. Nếu lỗi xảy ra giữa các bước, message hoặc kết quả có thể được xử lý lại tùy cấu hình transaction/ack. Cần thêm idempotency/outbox khi nghiệp vụ phải chống phát trùng.

## 6. Headers do Splitter tạo giúp Aggregator ra sao?

Một Splitter thường gửi các message con có header:

| Header | Vai trò |
|---|---|
| `correlationId` | Xác định nhóm các phần của một split |
| `sequenceNumber` | Vị trí của message con trong chuỗi |
| `sequenceSize` | Tổng số phần dự kiến |
| `traceId` | Truy vết, nếu được truyền từ nguồn |
| `businessCorrelationId` | Liên kết kết quả với đơn hàng |

Ví dụ Splitter phát ba phần:

~~~text
Message 1: correlationId=abc, sequenceNumber=1, sequenceSize=3
Message 2: correlationId=abc, sequenceNumber=2, sequenceSize=3
Message 3: correlationId=abc, sequenceNumber=3, sequenceSize=3
~~~

Với topology chuẩn và sequence headers phù hợp, **Aggregator mặc định** có thể dùng correlation/release strategy dựa vào các metadata này để gom các phần trở lại.

### 6.1. Vì sao không phải lúc nào cũng có sequenceSize?

Khi ba service gửi `OrderRegistered`, `PaymentCaptured`, `InventoryReserved` độc lập, không có Splitter chung ở upstream. Producer có thể không gửi `sequenceSize`; nếu có, dữ liệu cũng chưa chắc tương ứng với số part mong đợi. Do đó cần **custom correlation/release strategy** theo nghiệp vụ.

### 6.2. Dữ liệu bị Filter loại sau Splitter

Một lỗi kinh điển:

~~~mermaid
flowchart LR
    B["Batch 3 parts"] --> S["Splitter"]
    S --> A["Part 1"]
    S --> C["Part 2"]
    S --> D["Part 3"]
    A --> AG["Aggregator"]
    C --> F{"Filter"}
    F -->|Rejected| DROP["Discard"]
    D --> AG
~~~

Mỗi part có thể mang `sequenceSize=3`, nhưng Aggregator chỉ nhận **2/3 message**. Nó có thể chờ vô hạn nếu release strategy yêu cầu đủ ba part. Các lựa chọn thiết kế:

- **Filter trước Splitter**, để số phần được tính sau khi loại dữ liệu.
- Thay vì discard, phát một kết quả đại diện `SkippedPart` để vẫn đủ nhóm.
- Dùng release strategy xử lý tập các part thực tế, có điều kiện hoàn tất riêng.
- Dùng timeout/expiry và quy tắc phát nhóm partial khi chấp nhận thiếu.

Không sửa `sequenceSize` tùy tiện trên từng message đã split để "vá" một Aggregator đang chờ.

## 7. Ví dụ Java 17+: từ OrderLine đến PricedLine

Ta xây một flow đơn giản, có thể kiểm thử: một batch chứa các dòng hàng, Splitter tạo message con, Transformer tính tiền từng dòng, Aggregator gom lại.

### 7.1. Model đầu vào

~~~java
import java.math.BigDecimal;
import java.util.List;

public record OrderLine(
        String sku,
        BigDecimal unitPrice,
        int quantity
) {}

public record PricedLine(
        String sku,
        BigDecimal lineTotal
) {}

public record OrderBatch(
        String orderId,
        List<OrderLine> lines
) {
    public OrderBatch {
        lines = List.copyOf(lines);
    }
}
~~~

Các khai báo top-level `public` trong ví dụ cần đặt ở những source file Java tương ứng khi triển khai thật. `List.copyOf` tạo snapshot của collection, nhưng nếu từng phần tử chứa object mutable, vẫn cần defensive copy sâu hơn.

### 7.2. Chính sách tính tiền của một dòng

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

        BigDecimal total = line.unitPrice()
                .multiply(BigDecimal.valueOf(line.quantity()));

        return new PricedLine(line.sku(), total);
    }
}
~~~

Dùng `BigDecimal` giúp tính giá trị tiền tệ trong hệ số thập phân, tránh lỗi biểu diễn nhị phân khi dùng `double`. Quy tắc số lượng dương và giá không âm là hợp đồng minh họa; một luồng refund hoặc credit note có thể có quy tắc khác.

### 7.3. Tính tổng kết quả sau khi Aggregator đã gom

~~~java
import java.math.BigDecimal;
import java.util.List;

public record OrderPriceResult(
        String orderId,
        List<PricedLine> lines,
        BigDecimal total
) {}

public final class OrderPricingAssembler {

    public OrderPriceResult assemble(
            String orderId, List<PricedLine> lines) {

        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("ORDER_ID_REQUIRED");
        }
        if (lines == null || lines.isEmpty()) {
            throw new IllegalArgumentException("LINES_REQUIRED");
        }

        List<PricedLine> snapshot = List.copyOf(lines);
        BigDecimal sum = snapshot.stream()
                .map(PricedLine::lineTotal)
                .reduce(BigDecimal.ZERO, BigDecimal::add);

        return new OrderPriceResult(orderId, snapshot, sum);
    }
}
~~~

Assembler ở đây là một **hàm thuần** trên một collection đã đầy đủ. Bản thân nó **không phải Aggregator endpoint** vì nó không nhận những message riêng, không tạo group và không quyết định release. Nó có thể được dùng trong aggregation output processor hoặc một Transformer ngay sau `.aggregate()`.

## 8. Spring Integration Java DSL: Splitter → Aggregator

Ví dụ này sử dụng một message có payload là `List<OrderLine>`. Đầu vào là **List** để `split()` mặc định tách các phần tử; nếu muốn truyền `OrderBatch`, hãy thêm bước chuyển từ `OrderBatch.lines()` sang List trước `split()`.

### 8.1. Cấu hình flow

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
public class OrderLinesFlowConfiguration {

    @Bean(name = "order.lines.input")
    public MessageChannel input() {
        return new DirectChannel();
    }

    @Bean(name = "order.lines.output")
    public PollableChannel output() {
        return new QueueChannel();
    }

    @Bean
    public LinePricingPolicy linePricingPolicy() {
        return new LinePricingPolicy();
    }

    @Bean
    public IntegrationFlow linePricingFlow(
            LinePricingPolicy policy) {

        return IntegrationFlow
                .from("order.lines.input")
                .split()
                .transform(OrderLine.class, policy::price)
                .aggregate()
                .channel("order.lines.output")
                .get();
    }
}
~~~

Cách đọc flow:

1. Producer gửi **một** `Message<List<OrderLine>>` vào `order.lines.input`.
2. Splitter tạo từng `Message<OrderLine>` và gắn sequence/correlation metadata phù hợp.
3. Transformer tạo `PricedLine` cho mỗi part.
4. Aggregator gom các `PricedLine` thuộc cùng group.
5. Sau khi đủ part theo release strategy mặc định, message kết quả được gửi tới `order.lines.output`.

Kết quả mặc định thường là **collection các payload** của nhóm. Nếu downstream cần `OrderPriceResult` cụ thể, hãy thêm output transformation lấy ID đơn từ metadata hợp lệ hoặc dùng custom output processor phù hợp.

**Lưu ý phạm vi:** đây là ví dụ đồng bộ trong bộ nhớ. `QueueChannel` giúp quan sát kết quả trong unit/integration tests, không phải bảo đảm lưu bền vững qua restart.

### 8.2. Tại sao trong ví dụ không cần tự tạo correlationStrategy?

Vì `split()` cung cấp các sequence/correlation headers và Aggregator mặc định biết cách sử dụng chúng. Với input từ các producer **không có chung Splitter**, không thể mặc định rằng cơ chế tương tự sẽ nhận biết được nhóm đầy đủ. Khi đó cần thiết kế riêng.

### 8.3. Thứ tự phần tử trong output có chắc giống input?

Một flow đơn giản chạy đồng bộ có thể trả về collection theo thứ tự quen thuộc, nhưng **không nên đặt logic tính đúng vào thứ tự arrival** khi có executor, broker, retry hoặc fan-out. Nếu kết quả cần đúng thứ tự dòng hàng, hãy dùng `sequenceNumber` hoặc một `lineIndex` rõ ràng, rồi sort trong output processor.

### 8.4. Trường hợp batch rỗng

Nếu đầu vào là list rỗng, Splitter không có part để phát. Aggregator không nhận message và vì vậy không tự sinh output rỗng. Hợp đồng phải quy định xử lý trước: chấp nhận tổng 0, reject hoặc tạo result trực tiếp. Đừng để Gateway chờ vô hạn một output mà flow không tạo.

## 9. Test integration: Aggregator thực sự phát một kết quả

Unit test `LinePricingPolicy` không thể khẳng định Spring wiring đúng. Ta dùng Spring Test và `QueueChannel` trong cấu hình mục 8.

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

@SpringJUnitConfig(classes = OrderLinesFlowConfiguration.class)
class OrderLinesFlowTest {

    @Autowired
    @Qualifier("order.lines.input")
    MessageChannel input;

    @Autowired
    @Qualifier("order.lines.output")
    PollableChannel output;

    @Test
    void splitsPricesAndAggregatesAllParts() {
        List<OrderLine> lines = List.of(
                new OrderLine("SKU-A",
                        new BigDecimal("100.00"), 2),
                new OrderLine("SKU-B",
                        new BigDecimal("50.00"), 1),
                new OrderLine("SKU-C",
                        new BigDecimal("25.00"), 3));

        assertTrue(input.send(
                MessageBuilder.withPayload(lines)
                        .setHeader("traceId", "trace-1001")
                        .build()));

        Message<?> aggregated = output.receive(1000);
        assertNotNull(aggregated);

        assertInstanceOf(
                Collection.class, aggregated.getPayload());

        Collection<?> payload =
                (Collection<?>) aggregated.getPayload();
        assertEquals(3, payload.size());

        Set<PricedLine> actual = payload.stream()
                .map(PricedLine.class::cast)
                .collect(Collectors.toSet());

        assertEquals(Set.of(
                new PricedLine(
                        "SKU-A", new BigDecimal("200.00")),
                new PricedLine(
                        "SKU-B", new BigDecimal("50.00")),
                new PricedLine(
                        "SKU-C", new BigDecimal("75.00"))),
                actual);

        // Chỉ một output cho nhóm đã hoàn tất.
        assertNull(output.receive(0));
    }
}
~~~

Test xác nhận:

- Có ba part được xử lý.
- Output là **một** message mang collection của ba `PricedLine`.
- Không có hai hoặc ba message output riêng cho một nhóm đã hoàn tất.
- Giá trị từng line đúng, không dựa vào thứ tự collection.

Test trên **không xác nhận durability**, không kiểm tra xử lý đa instance hay lỗi bất đồng bộ. Những yêu cầu đó cần test bổ sung theo topology triển khai.

### 9.1. Test nhiều batch không trộn nhóm

Có thể gửi hai message batch lần lượt, ví dụ một batch gồm 2 dòng và batch kia gồm 3 dòng. Kỳ vọng hai output riêng, mỗi output chứa đúng các part tương ứng. Với xử lý concurrent, cần test gửi interleaved và xác nhận correlation không làm lẫn hai batch.

### 9.2. Test đầu vào sai

Nếu một `OrderLine` có `quantity=0`, `LinePricingPolicy` sẽ ném exception. Trong luồng `DirectChannel` đồng bộ, lỗi có thể được ném về sender; không nên chờ một kết quả tổng hợp thành công. Với executor hoặc broker, cần kiểm thử error flow/ack/timeout phù hợp.

## 10. Correlation strategy cho nhiều nguồn sự kiện

Trường hợp Splitter là ví dụ đơn giản. Trong thực tế, các service có thể phát event độc lập:

~~~text
OrderRegistered(orderId=ORDER-1001)
PaymentCaptured(orderId=ORDER-1001)
InventoryReserved(orderId=ORDER-1001)
~~~

Các event có thể đến theo thứ tự:

~~~text
Payment -> Inventory -> Order
Inventory -> Order -> Payment
Order -> Payment -> Inventory
~~~

Aggregator phải hoạt động đúng cho **mọi thứ tự được phép**.

### 10.1. Contract của các message

~~~java
import java.math.BigDecimal;

public sealed interface OrderPart
        permits OrderRegistered, PaymentCaptured, InventoryReserved {
    String orderId();
}

public record OrderRegistered(
        String orderId,
        String customerId,
        BigDecimal amount
) implements OrderPart {}

public record PaymentCaptured(
        String orderId,
        String paymentId
) implements OrderPart {}

public record InventoryReserved(
        String orderId,
        String reservationId
) implements OrderPart {}

public record OrderReady(
        String orderId,
        String customerId,
        BigDecimal amount,
        String paymentId,
        String reservationId
) {}
~~~

Các khai báo top-level `public` trong code block được đặt chung để người học so sánh. Khi đưa vào project Java, hãy đặt từng khai báo vào **source file riêng** có tên phù hợp.

### 10.2. Key đúng: theo orderId, không theo customerId

Nếu hai order cùng thuộc `CUST-21`:

~~~text
ORDER-1001 -> customerId CUST-21
ORDER-1002 -> customerId CUST-21
~~~

Nhóm theo `customerId` có thể trộn payment của ORDER-1001 với inventory của ORDER-1002. Vì vậy, key thường là `orderId`, hoặc composite key gồm `tenantId` đã xác thực và `orderId`.

~~~java
public record OrderCorrelationKey(
        String tenantId, String orderId
) {}
~~~

Ở trust boundary, không chấp nhận `tenantId` do client tự khai làm bằng chứng quyền truy cập. Tầng authentication/authorization phải xác minh trước khi tạo key.

### 10.3. Một chiến lược tương quan thuần

~~~java
import org.springframework.messaging.Message;

public final class OrderCorrelationPolicy {

    public String groupKey(Message<?> message) {
        if (!(message.getPayload() instanceof OrderPart part)) {
            throw new IllegalArgumentException(
                    "UNSUPPORTED_ORDER_PART");
        }
        if (part.orderId() == null
                || part.orderId().isBlank()) {
            throw new IllegalArgumentException(
                    "ORDER_ID_REQUIRED");
        }
        return part.orderId();
    }
}
~~~

Code này phù hợp cho mô hình một tenant và ID duy nhất toàn hệ thống. Trong production đa tenant, trả composite key có tenant đã được xác thực. Đừng dựa vào tên message class hoặc MessageHeaders.ID để tương quan các message của cùng đơn.

## 11. Release strategy phải kiểm tra đủ *loại* message

Giả sử Aggregator đã nhận:

~~~text
OrderRegistered(ORDER-1001)
PaymentCaptured(ORDER-1001)
PaymentCaptured(ORDER-1001)  // duplicate
~~~

`group.size()==3` không đồng nghĩa đã đủ `InventoryReserved`. Nếu release sớm, hệ thống có thể tạo `OrderReady` sai.

### 11.1. Chính sách kiểm tra đủ dữ kiện

~~~java
import java.util.List;

public final class OrderGroupPolicy {

    public boolean complete(List<OrderPart> parts) {
        return count(parts, OrderRegistered.class) == 1
                && count(parts, PaymentCaptured.class) == 1
                && count(parts, InventoryReserved.class) == 1
                && parts.size() == 3;
    }

    private long count(
            List<OrderPart> parts, Class<? extends OrderPart> type) {
        return parts.stream().filter(type::isInstance).count();
    }
}
~~~

Chính sách này **không tự deduplicate**: nếu có hai PaymentCaptured, group không thỏa release. Đó là một lựa chọn để minh họa lỗi duplicate, nhưng trong production nếu duplicate có thể xảy ra thì **nhóm có thể không bao giờ hoàn tất** nếu không có bước chống trùng hoặc chiến lược xử lý/expiry riêng.

Các lựa chọn:

- Dedup theo `eventId` trước Aggregator.
- Lưu phiên bản mới nhất theo business key, có quy tắc conflict rõ.
- Reject duplicate với error/reject flow.
- Thiết kế group policy chấp nhận một bản duy nhất đã xác minh, đồng thời ghi nhận phần trùng.

### 11.2. Kết hợp output qua một assembler

~~~java
import java.util.List;

public final class OrderReadyAssembler {

    public OrderReady assemble(List<OrderPart> parts) {
        OrderGroupPolicy policy = new OrderGroupPolicy();
        if (!policy.complete(parts)) {
            throw new IllegalArgumentException(
                    "ORDER_GROUP_INCOMPLETE");
        }

        OrderRegistered order = exactlyOne(
                parts, OrderRegistered.class);
        PaymentCaptured payment = exactlyOne(
                parts, PaymentCaptured.class);
        InventoryReserved inventory = exactlyOne(
                parts, InventoryReserved.class);

        if (!order.orderId().equals(payment.orderId())
                || !order.orderId().equals(inventory.orderId())) {
            throw new IllegalArgumentException(
                    "MISMATCHED_ORDER_ID");
        }

        return new OrderReady(
                order.orderId(),
                order.customerId(),
                order.amount(),
                payment.paymentId(),
                inventory.reservationId());
    }

    private <T extends OrderPart> T exactlyOne(
            List<OrderPart> parts, Class<T> type) {
        List<T> values = parts.stream()
                .filter(type::isInstance)
                .map(type::cast)
                .toList();

        if (values.size() != 1) {
            throw new IllegalArgumentException(
                    "MISSING_OR_DUPLICATED_" + type.getSimpleName());
        }
        return values.get(0);
    }
}
~~~

Đây là một **hàm ghép kết quả**. Spring Integration Aggregator vẫn cần cấu hình correlation strategy, release strategy, MessageGroupStore và output processor để gọi hàm này đúng thời điểm.

### 11.3. Kết nối vào endpoint Aggregator

Về mặt kiến trúc:

~~~text
order.parts.input
  -> Aggregator
       correlationStrategy(message) = orderId
       releaseStrategy(group) =
           OrderGroupPolicy.complete(payloads(group))
       outputProcessor(group) =
           OrderReadyAssembler.assemble(payloads(group))
       messageStore = cấu hình theo durability cần thiết
       groupTimeout = thời gian chờ theo nghiệp vụ
  -> orders.ready
~~~

Đây là **sơ đồ cấu hình**, không phải Java DSL có thể biên dịch trực tiếp. API cấu hình cụ thể có thể dùng `AggregatorSpec` với những callback/strategy beans tương ứng tùy phiên bản Spring Integration. Ví dụ `.aggregate()` ở mục 8 là flow chạy được theo mô hình Splitter mặc định; phần này tập trung vào **quy tắc nghiệp vụ** của event join để tránh trộn hai trường hợp.

### 11.4. Khi nào dùng custom release strategy?

- Nhiều event không có `sequenceSize`.
- Số part cần thiết thay đổi theo loại nghiệp vụ.
- Điều kiện release phụ thuộc trạng thái/loại event, không chỉ đếm.
- Có kết quả negative, cancel hoặc rejection thay thế một part.
- Có thể phát partial result sau deadline.
- Cần phát kết quả theo version cụ thể và chống duplicate.

## 12. Unit test correlation, release và assemble

Các policy thuần có thể kiểm thử **không cần Spring context**. Đây là cách phát hiện lỗi nhóm nhầm và release thiếu trước khi kiểm tra wiring.

### 12.1. Nhóm đầy đủ không phụ thuộc thứ tự

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.List;

import org.junit.jupiter.api.Test;

class OrderReadyAssemblerTest {

    @Test
    void buildsResultRegardlessOfArrivalOrder() {
        List<OrderPart> parts = List.of(
                new InventoryReserved("ORDER-9", "RES-9"),
                new OrderRegistered(
                        "ORDER-9", "CUST-9",
                        new BigDecimal("900.00")),
                new PaymentCaptured("ORDER-9", "PAY-9"));

        OrderGroupPolicy policy = new OrderGroupPolicy();
        assertTrue(policy.complete(parts));

        OrderReady result =
                new OrderReadyAssembler().assemble(parts);

        assertEquals("ORDER-9", result.orderId());
        assertEquals("CUST-9", result.customerId());
        assertEquals(new BigDecimal("900.00"), result.amount());
        assertEquals("PAY-9", result.paymentId());
        assertEquals("RES-9", result.reservationId());
    }
}
~~~

### 12.2. Thiếu part phải chờ

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.List;

import org.junit.jupiter.api.Test;

class IncompleteOrderGroupTest {

    @Test
    void doesNotReleaseWithoutInventory() {
        List<OrderPart> incomplete = List.of(
                new OrderRegistered(
                        "ORDER-9", "CUST-9",
                        new BigDecimal("900.00")),
                new PaymentCaptured("ORDER-9", "PAY-9"));

        OrderGroupPolicy policy = new OrderGroupPolicy();

        assertFalse(policy.complete(incomplete));

        assertThrows(
                IllegalArgumentException.class,
                () -> new OrderReadyAssembler().assemble(incomplete));
    }
}
~~~

### 12.3. Trùng payment không được coi như inventory

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.List;

import org.junit.jupiter.api.Test;

class DuplicateOrderPartTest {

    @Test
    void duplicatePaymentDoesNotCompleteTheGroup() {
        List<OrderPart> duplicated = List.of(
                new OrderRegistered(
                        "ORDER-9", "CUST-9",
                        new BigDecimal("900.00")),
                new PaymentCaptured("ORDER-9", "PAY-9"),
                new PaymentCaptured("ORDER-9", "PAY-9-DUP"));

        assertFalse(new OrderGroupPolicy().complete(duplicated));
    }

    @Test
    void assemblerRejectsDuplicateEvenWithInventory() {
        List<OrderPart> duplicated = List.of(
                new OrderRegistered(
                        "ORDER-9", "CUST-9",
                        new BigDecimal("900.00")),
                new PaymentCaptured("ORDER-9", "PAY-9"),
                new PaymentCaptured("ORDER-9", "PAY-9-DUP"),
                new InventoryReserved("ORDER-9", "RES-9"));

        assertThrows(
                IllegalArgumentException.class,
                () -> new OrderReadyAssembler().assemble(duplicated));
    }
}
~~~

Đây là test của business policy, **không thay thế** integration test Aggregator thật về lưu group, release, timeout và concurrency. Nhưng chúng giúp bảo đảm rằng số lượng message không được nhầm với độ đầy đủ về loại dữ liệu.

### 12.4. Những test nên bổ sung

| Ca kiểm thử | Điều cần xác nhận |
|---|---|
| Part tới theo mọi thứ tự | Output giống nhau |
| Hai order cùng khách hàng | Không trộn nhóm |
| Hai tenant dùng cùng orderId | Không trộn nhóm nếu key gồm tenant |
| Thiếu Payment | Không release thành OrderReady |
| Duplicate OrderRegistered | Không tạo output sai |
| Duplicate eventId | Bị dedup hoặc reject đúng contract |
| Late Inventory sau expiry | Có hành vi định nghĩa rõ |
| Part sai schema | Không lặng lẽ đưa vào nhóm |
| Payment đã reversed | Không coi như captured thành công nếu business không cho |
| Output processor lỗi | Error flow và group cleanup nhất quán |

## 13. Chọn output processor: collection hay DTO?

### 13.1. Default output

Trong ví dụ Splitter → Aggregator cơ bản, output có thể là một **collection các payload**. Điều này hữu ích khi downstream còn phải tính toán trên collection.

### 13.2. DTO kết quả tường minh

Khi downstream cần `OrderPriceResult` hoặc `OrderReady`, nên có một output processor chuyên trách tạo kiểu dữ liệu rõ ràng. Có thể triển khai như:

~~~text
MessageGroup
    -> lấy các message thuộc group
    -> kiểm tra type, version, eventId, orderId
    -> chọn/tính các trường đúng nghiệp vụ
    -> tạo OrderReady bất biến
    -> tạo output message với metadata theo contract
~~~

Một số message trong group có thể chứa headers mâu thuẫn, như `replyChannel`, `traceId` hoặc `tenantId` khác nhau. Không thể tự giả định **mọi header của mọi part** đều được copy nguyên vẹn sang output. Hãy kiểm thử và định nghĩa header mapping cụ thể.

### 13.3. Thứ tự output

Message arrival order có thể khác business order vì concurrency/retry. Nếu DTO chứa `List<PricedLine>` với thứ tự có ý nghĩa, lưu `lineIndex` hoặc sequenceNumber đáng tin và sort trước khi tạo output. Không dựa vào thứ tự iterator của một MessageGroupStore bất kỳ.

## 14. Timeout, expiry và incomplete groups

Aggregator có thể **không bao giờ nhận đủ message** nếu producer lỗi, Filter loại một part, broker mất sự kiện hoặc correlation bị sai. Phải có chính sách cho nhóm chưa đủ.

~~~mermaid
flowchart TD
    A["MessageGroup đang chờ"] --> T{"Deadline/timeout?"}
    T -->|Chưa| WAIT["Tiếp tục nhận part"]
    T -->|Đến hạn| P{"Cho phép partial result?"}
    P -->|Có| PARTIAL["Phát kết quả partial có trạng thái"]
    P -->|Không| ERR["Ghi lỗi/expired group"]
    PARTIAL --> CLEAN["Cleanup theo contract"]
    ERR --> CLEAN
~~~

### 14.1. Timeout của Aggregator khác timeout HTTP

Một Enricher chờ HTTP lookup thường có timeout ở mức **một request**. Aggregator chờ **nhiều message** có thể có deadline dài hơn, hoặc group expiry xử lý qua scheduler. Không áp dụng máy móc timeout 500ms của HTTP client cho một quy trình inventory reservation kéo dài nhiều phút.

### 14.2. Phát kết quả partial khi nào?

Chỉ phát partial khi downstream chấp nhận nó. Ví dụ report analytics có thể chấp nhận 2/3 dữ kiện và đánh dấu `partial=true`. Nhưng một hệ thống phát lệnh giao hàng có thể **không được phép** tạo `OrderReady` khi chưa có InventoryReserved.

Nên dùng kiểu kết quả riêng nếu nghiệp vụ cần phân biệt:

~~~java
public enum AggregationOutcome {
    COMPLETE,
    PARTIAL,
    EXPIRED
}

public record AggregationResult<T>(
        AggregationOutcome outcome,
        T value,
        String reasonCode
) {}
~~~

Các khai báo trên cần source file riêng khi tạo project Java. `AggregationResult` ở đây là kiểu **minh họa**, không phải class có sẵn của Spring Integration.

### 14.3. Nhóm hết hạn cần được quan sát

Khi một group expire, cần biết: group key, số part đã nhận, loại part còn thiếu, tuổi nhóm, deadline và trạng thái business. Đừng chỉ xóa group rồi mất mọi thông tin chẩn đoán. Với dữ liệu cá nhân, hạn chế log payload thô.

### 14.4. Late arrival sau khi group đóng

Khi Payment đến sau khi group đã release, có thể:

- Reject và đưa vào dead-letter/quarantine.
- Bỏ qua nếu đó là duplicate đã xử lý.
- Reopen group theo hợp đồng đặc biệt.
- Sinh một **compensating event** hoặc correction.
- Chuyển tới process manager xử lý saga dài hạn.

Mỗi lựa chọn kéo theo yêu cầu idempotency và audit. Không mặc định Aggregator luôn reopen group theo cách mình muốn; hành vi phụ thuộc cấu hình group completion/expiry.

## 15. Duplicate, redelivery và idempotency

Các hệ thống messaging thường có khả năng phân phối lại: producer retry, consumer crash sau commit nhưng trước ack, broker redeliver, hoặc một bước downstream ném exception. Do vậy cùng một **business event** có thể tới Aggregator nhiều lần.

### 15.1. Phân biệt hai loại ID

- `MessageHeaders.ID`: ID của một Spring message instance, có thể đổi khi tạo message khác.
- `eventId`: ID nghiệp vụ ổn định của event, nên giữ qua replay/redelivery.
- `correlationId` hoặc business group key: xác định **nhóm** chứa event.

Không dùng một trong ba ID để thay thế hoàn toàn các mục đích còn lại.

### 15.2. Dedup ở đâu?

Có thể dedup trước khi lưu group theo `eventId`, hoặc trong storage/grouper có policy chống trùng phù hợp. Sau Aggregator, output cũng cần idempotency nếu hai lần release/replay có thể đưa cùng kết quả tới DB/email/broker.

~~~text
Producer -> Broker
         -> Validation
         -> Dedup by eventId
         -> Aggregator by (tenantId, orderId)
         -> Output processor
         -> Idempotent handler/outbox
~~~

Một bản `PaymentCaptured` lặp lại **không được** tính thành một phần loại `InventoryReserved`. Nếu nhận trùng với payload khác nhau nhưng cùng eventId, đó là data integrity violation cần xử lý tường minh.

### 15.3. Exactly-once không đến từ Aggregator

Aggregator có thể phát một output cho một group hoàn tất trong một lần chạy, nhưng điều này **không tự bảo đảm exactly-once side effect** xuyên broker, database và hệ thống ngoài. Cần transaction, acknowledgement, outbox, dedup/idempotency và kiểm thử failure windows.

## 16. Concurrency và nhiều instance

Khi hai message cùng group đến gần như đồng thời, Aggregator cần xử lý việc ghi group và đánh giá release. Trong Spring Integration, behavior phụ thuộc group store, locking strategy và transaction topology.

### 16.1. Một JVM với DirectChannel

Trong ví dụ đồng bộ đơn giản, thứ tự xử lý thường dễ quan sát. Tuy nhiên, hai producer thread vẫn có thể gửi cùng lúc. Không dùng một `ArrayList` do ứng dụng tự quản lý như một group store mà không có đồng bộ phù hợp.

### 16.2. ExecutorChannel hoặc broker

Message có thể đến ở nhiều worker với thứ tự không xác định. Cần:

- Một correlation key ổn định, không phụ thuộc thread.
- Store và lock phù hợp để không release trùng.
- Timeout/reaper nhất quán.
- Idempotency cho output handler.
- Tracing theo group key/eventId thay vì chỉ dựa vào timestamp.

### 16.3. Nhiều application instance

Nếu mỗi instance có **in-memory MessageGroupStore riêng**, các part của cùng order có thể bị chia ra hai nhóm khác nhau và không nhóm nào đủ. Cần một trong các hướng:

- Partition/route cùng key về một instance.
- Shared/persistent message store với cơ chế lock phù hợp.
- Nền tảng stream processing/stateful aggregation có hỗ trợ key partitioning.
- Process manager phù hợp với workflow phân tán.

Việc chỉ thêm `@EnableIntegration` không tạo điều phối liên instance tự động.

## 17. Aggregator, Gateway và request–reply

Một Gateway có thể gửi request và chờ Aggregator gom kết quả. Tuy nhiên, **Aggregator có thể chưa sẵn sàng phát ngay**.

### 17.1. Một batch request–reply

Với Splitter → Aggregator trong một flow đồng bộ ngắn, Gateway có thể nhận một collection kết quả sau khi tất cả part được xử lý và gom.

### 17.2. Nhiều nguồn event độc lập

Nếu Payment và Inventory đến hàng phút sau, việc giữ một HTTP request hoặc Gateway thread chờ lâu có thể không phù hợp. Có thể cần:

- Trả ngay `202 Accepted` với `orderId`/`trackingId`.
- Theo dõi trạng thái nhóm bằng API hoặc sự kiện.
- Phát `OrderReady` bất đồng bộ khi group hoàn tất.
- Có SLA và deadline riêng cho quy trình.
- Gửi sự kiện lỗi/expired khi nhóm không đủ.

### 17.3. Reply channel không phải group key

`replyChannel` xác định nơi một reply có thể tới trong topology; group key xác định message thuộc cùng nhóm. Các part từ ba nguồn khác nhau có thể có replyChannel khác nhau hoặc không có replyChannel; output processor phải quyết định đường output đúng theo contract, không lấy bừa replyChannel của part đầu.

## 18. Kết hợp Aggregator với Filter, Router, Transformer và Publish–Subscribe

### 18.1. Transformer trước Aggregator

Transformer có thể chuẩn hóa các part trước khi lưu nhóm:

~~~text
PaymentCapturedRaw -> validate/transform -> PaymentCaptured
InventoryRaw       -> validate/transform -> InventoryReserved
OrderRaw           -> validate/transform -> OrderRegistered
                                         -> Aggregator
~~~

Điều này giúp release strategy xử lý **typed payloads** thay vì parse lại JSON hoặc Map ở mỗi lần đánh giá.

### 18.2. Filter trước Aggregator

Filter có thể loại part không hợp lệ. Nhưng nếu group cần đủ part, loại mất một message có thể khiến nhóm bị treo. Phải thiết kế error/reject event, timeout hoặc result đại diện thay vì giả định release vẫn tự hoạt động.

### 18.3. Router và Aggregator

Router có thể chọn nhánh xử lý cho từng loại event trước khi chúng hội tụ. Sau khi Aggregator phát `OrderReady`, Router lại có thể chọn `priority`/`standard`. Khi route đi qua nhiều channel, bảo toàn correlation metadata.

### 18.4. Publish–Subscribe và fan-in

`PublishSubscribeChannel` fan-out tới nhiều subscriber. Nếu các nhánh trả kết quả độc lập, Aggregator có thể dùng correlation và sequence metadata để fan-in. Nhưng không phải mọi subscriber đều tạo reply. Một nhánh chỉ ghi audit `void` không thể mặc nhiên được tính là đã phát result cho Aggregator.

### 18.5. Content Enricher và Aggregator

Enricher thường bổ sung dữ liệu từ lookup cho **một** message; Aggregator gom **nhiều message**. Có thể enrich `OrderRegistered` bằng customer tier trước khi đưa vào Aggregator với Payment/Inventory. Việc kết hợp giúp group có đủ dữ liệu đầu vào đã chuẩn hóa mà không yêu cầu Aggregator tự gọi API.

### 18.6. Splitter/Aggregator không tự bảo toàn mọi header

Khi biến một message thành nhiều part rồi gom lại, cần kiểm tra `traceId`, `businessCorrelationId`, `replyChannel` và custom headers. Output của Aggregator có thể áp dụng một quy tắc kết hợp headers; với dữ liệu có nhiều nguồn và giá trị xung đột, hãy định nghĩa output mapping rõ ràng.

## 19. Error channel, retry và ranh giới giao dịch

Các lỗi khác nhau có hậu quả khác nhau.

| Lỗi | Bản chất | Hướng xử lý |
|---|---|---|
| Part không đúng schema | Dữ liệu không hợp lệ | Reject/quarantine, không retry vô hạn |
| Correlation key thiếu | Không xác định được nhóm | Validation/error trước Aggregator |
| Duplicate eventId | Phát lại hoặc data integrity | Dedup/reject, log reason |
| MessageGroupStore unavailable | Lỗi hạ tầng | Retry bounded, bảo đảm ack/transaction phù hợp |
| Output processor exception | Lỗi domain/code | Error flow, tránh release trùng |
| Nhóm chờ quá lâu | Thiếu part/deadline | Timeout/expiry policy |
| Late arrival | Message đến sau group hoàn tất | Chính sách correction/reject |
| Downstream DB 503 | Lỗi handler sau aggregate | Retry/idempotency downstream |

### 19.1. Đồng bộ và bất đồng bộ

Với `DirectChannel`, exception có thể lan về sender. Với executor, adapter hoặc broker bất đồng bộ, lỗi có thể được gửi thành `ErrorMessage` tới error channel tùy cấu hình. Không mặc định rằng chỉ cần có header `errorChannel` thì mọi exception của mọi topology đều tự đi vào đó.

### 19.2. Retry các part có thể dẫn đến release lặp

Nếu một part được thêm vào group nhưng ack thất bại, broker có thể gửi lại. Nếu group đã release nhưng cleanup chưa đồng bộ với transaction, cũng có thể xảy ra tình huống đầu ra được tạo lại. Đặt **idempotency key ở output handler** là tuyến bảo vệ cuối cùng cho side effect.

### 19.3. Định nghĩa transaction boundary

Nếu dùng persistent group store, cần hiểu transaction của thao tác **thêm part**, **đánh giá release**, **phát output**, **ack broker** và **ghi business DB**. Chúng không nhất thiết nằm trong cùng một transaction phân tán. Thiết kế thực tế có thể dùng outbox và idempotency thay vì kỳ vọng commit đồng thời qua mọi hệ thống.

## 20. Quan sát tiến trình gom nhóm

Một Aggregator có thể không phát output trong thời gian dài và đây **không nhất thiết là lỗi**. Monitoring phải giúp phân biệt nhóm đang chờ hợp lệ với nhóm đã kẹt.

| Metric/trace | Câu hỏi | Ghi chú |
|---|---|---|
| `aggregation_messages_received_total` | Đã nhận bao nhiêu part? | Tách theo flow/type nếu cardinality nhỏ |
| `aggregation_open_groups` | Có bao nhiêu group chưa xong? | Cảnh báo tăng không giới hạn |
| `aggregation_group_age_seconds` | Group đã chờ bao lâu? | Theo dõi percentiles/oldest groups |
| `aggregation_completed_total` | Bao nhiêu group đã release? | Khác số message đầu vào |
| `aggregation_expired_total` | Bao nhiêu group timeout? | Chẩn đoán missing part |
| `aggregation_duplicates_total` | Có nhiều part trùng không? | Theo reason code |
| `aggregation_late_arrivals_total` | Bao nhiêu event đến sau khi group đóng? | Theo SLA producer |
| `aggregation_output_failures_total` | Output processor/downstream lỗi? | Cần error flow |
| `correlationKey` | Group nào đang kẹt? | Đặt trong log/trace có kiểm soát |

Đừng dùng `orderId`, `eventId` hoặc `traceId` làm metric labels không giới hạn; chúng có cardinality rất cao. Dùng labels theo flow, event type, outcome và reason code, còn giá trị cụ thể ở trace/log tuân theo chính sách bảo mật.

### 20.1. Log có cấu trúc

~~~text
flow=order-aggregation
eventId=evt-payment-9
groupKey=tenant-a/ORDER-9
partType=PaymentCaptured
groupPartTypes=[OrderRegistered, PaymentCaptured]
release=false
groupAgeMs=18500
traceId=trace-42
~~~

Đây là ví dụ diễn giải hoạt động. Không log toàn bộ payment token, địa chỉ, hồ sơ khách hàng hoặc nội dung message chứa dữ liệu nhạy cảm.

### 20.2. Đừng kết luận group hoàn tất chỉ từ group.size()

Một dashboard hiển thị group size=3 không nói được đã có đúng ba part cần thiết hay chưa. Monitoring có thể bổ sung tập loại part đã nhận và reason code cho những part bị thiếu, nhưng phải tránh gắn danh sách ID riêng lẻ vào metric label.

## 21. Hiệu năng và tài nguyên

### 21.1. Bộ nhớ tăng theo số nhóm đang mở

Nếu có một triệu order với mỗi order đang chờ PaymentCaptured, Aggregator có thể giữ một triệu group state. Phải giới hạn thời gian chờ, memory usage và lưu bền vững theo yêu cầu. Dùng persistent store không loại bỏ vấn đề lưu trữ; chỉ chuyển chi phí sang DB/Redis hoặc backend khác.

### 21.2. Group lớn

Một batch có hàng trăm nghìn dòng có thể gây áp lực bộ nhớ nếu gom mọi payload về một collection. Nếu nghiệp vụ chỉ cần sum/count/min/max, có thể thiết kế **incremental aggregation** hoặc stateful stream processing phù hợp, thay vì giữ toàn bộ parts, kèm cơ chế cập nhật an toàn. Không tự thay default Aggregator bằng một biến global cộng dồn thiếu correlation hoặc transaction.

### 21.3. Hot key

Nếu quá nhiều event cùng group key, lock contention có thể gây nghẽn. Cần xem xét partitioning, batching, giới hạn tải, backpressure và tốc độ downstream. Một group key "unknown" dùng chung cho mọi message là nguyên nhân phổ biến của hot key và trộn dữ liệu.

### 21.4. Serialization và message store

Khi lưu message xuống store bền vững, payload/headers phải tương thích serializer. Tránh đặt các object nội bộ không serializable, token hay `MessageChannel` object ra ngoài phạm vi phù hợp. Kiểm thử serialization thực với store dự định sử dụng.

## 22. Những lỗi thiết kế thường gặp

### Lỗi 1 — Dùng group.size() thay vì kiểm tra đủ thông tin

**Triệu chứng:** hai Payment và một Order khiến hệ thống phát OrderReady.

**Khắc phục:** release theo **loại part bắt buộc**, thêm dedup và validation; test duplicate.

### Lỗi 2 — Tương quan theo ID không đủ phân biệt

**Triệu chứng:** các đơn của cùng khách hoặc cùng orderId ở hai tenant bị gom chung.

**Khắc phục:** dùng business key ổn định, có tenant đã xác thực nếu cần.

### Lỗi 3 — Không có timeout/expiry

**Triệu chứng:** group chờ mãi, message store tăng không giới hạn.

**Khắc phục:** có deadline, group expiry, alert và incomplete-group policy.

### Lỗi 4 — Tin rằng Splitter/Aggregator luôn nhận đủ part

**Triệu chứng:** Filter loại một phần, Aggregator không release.

**Khắc phục:** Filter trước Splitter, tạo result đại diện hoặc custom release/timeout.

### Lỗi 5 — Dùng in-memory store nhưng cần recover sau restart

**Triệu chứng:** đang chờ hai trong ba event thì process restart, nhóm biến mất.

**Khắc phục:** persistent MessageGroupStore hoặc workflow/state store phù hợp, cùng test recovery.

### Lỗi 6 — Dựa vào thứ tự arrival

**Triệu chứng:** output đảo thứ tự line items khi chạy async.

**Khắc phục:** dùng sequenceNumber/lineIndex và sắp xếp tường minh trước khi tạo output.

### Lỗi 7 — Tin rằng Aggregator tự làm exactly-once

**Triệu chứng:** output hoặc side effect được xử lý trùng khi broker redeliver.

**Khắc phục:** dedup eventId, idempotency output handler và transaction/outbox.

### Lỗi 8 — Dùng customerId làm group key cho OrderReady

**Triệu chứng:** hai đơn cùng khách bị trộn payment/inventory.

**Khắc phục:** correlation theo orderId hoặc composite key.

### Lỗi 9 — Không định nghĩa late-arrival policy

**Triệu chứng:** event tới sau group đóng gây tạo group mới kẹt hoặc output thứ hai.

**Khắc phục:** có closed-group/tombstone/retention hoặc cơ chế correction.

### Lỗi 10 — Log payload nhạy cảm của group

**Triệu chứng:** dashboard chứa toàn bộ payment/customer data.

**Khắc phục:** log group key được kiểm soát, event type, outcome, reason, tuổi nhóm và trace ID; che/mã hóa identifiers khi cần.

### Lỗi 11 — Trộn Content Enricher với Aggregator

**Triệu chứng:** chỉ cần tra cứu profile cho một đơn nhưng tạo group store và release strategy.

**Khắc phục:** dùng Content Enricher cho lookup; dùng Aggregator khi thực sự có nhiều message cần hội tụ.

### Lỗi 12 — Không kiểm tra transaction/error boundary

**Triệu chứng:** group đã release nhưng DB lỗi; retry tạo nhiều output.

**Khắc phục:** mô hình hóa failure windows, có replay/idempotency test và error handling theo topology.

## 23. Bài tập thực hành

**Bối cảnh:** một nền tảng thương mại điện tử cần tính tổng đơn hàng và chỉ phát `OrderReady` khi có Order, Payment và Inventory.

### Bài 1 — Splitter → Aggregator cơ bản

Dùng `OrderLinesFlowConfiguration` ở mục 8. Gửi List gồm ba OrderLine, kiểm tra chỉ có **một output message** mang ba PricedLine.

### Bài 2 — Tính tổng sau aggregate

Thêm một Transformer sau `aggregate()` để tạo `OrderPriceResult`. Cần chọn cách lấy orderId đáng tin cậy từ request/correlation metadata và bảo toàn nó qua Splitter; test sum đúng `325.00`.

### Bài 3 — Hai batch xen kẽ

Tạo hai batch có group IDs khác nhau. Gửi message xen kẽ nếu topology test cho phép, kiểm tra output không trộn A/B và mỗi batch release đúng một lần.

### Bài 4 — Filter bỏ một part

Đặt Filter sau Splitter, loại một dòng hàng. Quan sát Aggregator không đủ part nếu dùng sequenceSize mặc định. Thiết kế lại bằng cách filter trước split hoặc custom release/partial result.

### Bài 5 — Custom correlation

Tạo `OrderCorrelationKey(tenantId, orderId)` với tenant đến từ nguồn đã xác thực. Test cùng orderId ở hai tenant không vào cùng group.

### Bài 6 — Custom release

Viết `OrderGroupPolicy.complete(...)` yêu cầu đúng một OrderRegistered, PaymentCaptured và InventoryReserved. Test cả mọi thứ tự và thiếu/duplicate.

### Bài 7 — Output processor

Dùng `OrderReadyAssembler` tạo DTO bất biến. Test amount, paymentId, reservationId và việc không trộn orderId.

### Bài 8 — Timeout và incomplete group

Giả lập một order chỉ có OrderRegistered và PaymentCaptured. Cấu hình expiry/group timeout theo phiên bản Spring Integration đang dùng; xác nhận có outcome rõ ràng, cleanup và metric expired.

### Bài 9 — Replay/redelivery

Gửi lại PaymentCaptured với cùng `eventId` trước và sau khi group hoàn tất. Thiết kế dedup/late-arrival policy và idempotent output handler.

### Bài 10 — Restart/recovery

Dùng persistent group store phù hợp với môi trường. Gửi hai part, restart app, gửi part thứ ba và xác nhận release đúng một lần nếu đây là yêu cầu hệ thống.

### Bài 11 — Gateway hay async status?

So sánh một batch tính tiền trả kết quả ngay với ba event độc lập mất nhiều phút. Thiết kế API/trackingId, SLA và event output cho trường hợp thứ hai.

### Bài 12 — Observability

Gắn các metric open groups, expired groups, completed groups, duplicates, latency; tạo log theo correlation và eventId không chứa dữ liệu nhạy cảm.

### Câu hỏi tự kiểm tra

1. Aggregator khác Transformer và Content Enricher ở điểm nào?
2. Vì sao Aggregator cần cả correlation strategy lẫn release strategy?
3. `sequenceSize` của Splitter có ý nghĩa gì?
4. Khi nào Aggregator mặc định không đủ cho các nguồn event độc lập?
5. Tại sao `group.size()==3` có thể release sai?
6. Vì sao group key nên là orderId thay vì customerId?
7. Với nhiều tenant, correlation key nên thay đổi ra sao?
8. Output processor chịu trách nhiệm gì?
9. Nếu Filter bỏ một part, Aggregator sẽ có nguy cơ nào?
10. MessageGroupStore mặc định có bảo đảm sống sót sau restart không?
11. Group timeout khác request HTTP timeout thế nào?
12. Late arrival và duplicate khác nhau ở điểm nào?
13. Vì sao `MessageHeaders.ID` không phù hợp làm business event ID?
14. Làm sao chống output side effect trùng sau replay?
15. Với collection kết quả, làm sao giữ đúng thứ tự dòng hàng?
16. Khi nào nên phát partial result và khi nào tuyệt đối không?
17. Vì sao nhiều JVM dùng in-memory store riêng có thể khiến group không bao giờ đủ?
18. Cần metric gì để phát hiện nhóm đang bị kẹt?

## 24. Checklist thiết kế Aggregator

- [ ] Xác định mục tiêu N→1 và schema output trước khi viết flow.
- [ ] Đã mô tả nguồn message: Splitter hay producer độc lập.
- [ ] Correlation key duy nhất trong đúng phạm vi business/tenant.
- [ ] Release strategy xác nhận **đủ dữ kiện**, không chỉ đếm mù.
- [ ] Output processor tạo DTO có kiểu và header mapping tường minh.
- [ ] Các part được validate/normalize trước khi vào group.
- [ ] Sequence/correlation headers của Splitter được giữ khi cần.
- [ ] Biết điều gì xảy ra nếu Filter loại một part.
- [ ] Có chính sách duplicate/eventId và late arrival.
- [ ] Có timeout/expiry/incomplete group policy.
- [ ] MessageGroupStore phù hợp memory/durability/scale.
- [ ] Có locking/transaction/concurrency strategy khi nhiều worker/instance.
- [ ] Không dựa vào thứ tự arrival nếu không có bảo đảm.
- [ ] Handler sau aggregate có idempotency khi có redelivery.
- [ ] Gateway/reply/error/ack được thiết kế theo latency và topology.
- [ ] Có unit test correlation/release/assembler và integration test channel thực.
- [ ] Có test restart, recovery, concurrency nếu production yêu cầu.
- [ ] Theo dõi open groups, tuổi nhóm, completed, expired và duplicates.
- [ ] Không log payload nhạy cảm và không lấy client header chưa xác thực làm group key.

## 25. Tổng kết

**Aggregator** trong Spring Integration là nơi **nhiều message liên quan hội tụ thành một kết quả**. Để làm đúng, nó phải xác định **correlation key**, giữ **MessageGroup**, đánh giá **release strategy**, chạy **output processor** và quản lý nhóm chưa đủ, hết hạn hoặc đến muộn. Với `Splitter → Aggregator`, các header `correlationId`, `sequenceNumber`, `sequenceSize` giúp nhóm và release những phần của cùng batch. Với event đến độc lập, cần custom correlation/release, duplicate policy và storage phù hợp.

Aggregator không thay thế Content Enricher (bổ sung dữ liệu bằng lookup), Transformer (đổi biểu diễn) hay Router (chọn đường đi). Nó cũng **không tự bảo đảm persistence hay exactly-once**. Cần kiểm thử flow thực, xử lý lỗi đúng theo sync/async topology, bảo toàn tracing/correlation và dùng idempotency cho side effect downstream.

Khi kết hợp Aggregator với Splitter, Filter, Transformer, Router, Gateway, retry và error channel, module **SPRING_INTEGRATION_PATTERN** có thể xây dựng các pipeline xử lý song song hoặc bất đồng bộ mà vẫn tạo kết quả tổng hợp có ý nghĩa, dễ mở rộng và dễ quan sát.

### Tài liệu tham khảo

- Spring Integration Reference — Aggregator: https://docs.spring.io/spring-integration/reference/aggregator.html
- Spring Integration Reference — Splitter: https://docs.spring.io/spring-integration/reference/splitter.html
- Spring Integration Reference — Correlation & release: https://docs.spring.io/spring-integration/reference/aggregator.html
- Spring Integration Reference — Message Store: https://docs.spring.io/spring-integration/reference/message-store.html
- Spring Integration Reference — Java DSL: https://docs.spring.io/spring-integration/reference/dsl.html
- Spring Integration API — MessageGroup: https://docs.spring.io/spring-integration/api/org/springframework/integration/store/MessageGroup.html
- Spring Integration API — ReleaseStrategy: https://docs.spring.io/spring-integration/api/org/springframework/integration/aggregator/ReleaseStrategy.html
- Spring Integration API — CorrelationStrategy: https://docs.spring.io/spring-integration/api/org/springframework/integration/aggregator/CorrelationStrategy.html
- Spring Integration API — DefaultAggregatingMessageGroupProcessor: https://docs.spring.io/spring-integration/api/org/springframework/integration/aggregator/DefaultAggregatingMessageGroupProcessor.html
- JUnit 5 User Guide — Parameterized Tests: https://junit.org/junit5/docs/current/user-guide/#writing-tests-parameterized-tests

