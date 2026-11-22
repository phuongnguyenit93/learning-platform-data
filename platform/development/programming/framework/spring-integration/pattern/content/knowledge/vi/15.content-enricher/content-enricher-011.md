# Phân biệt enricher với aggregator

Trong kiến trúc tích hợp bằng **Spring Integration**, một message đôi khi **chưa đủ thông tin để xử lý**: sự kiện đặt hàng chỉ có `customerId` nhưng nhánh tính ưu đãi cần hạng khách hàng; hoặc một quy trình có nhiều sự kiện `OrderPlaced`, `PaymentCaptured` và `ShipmentReserved` cần được kết hợp trước khi hoàn tất. Cả hai bài toán đều có vẻ như “ghép thêm dữ liệu”, nhưng chúng không dùng cùng một Enterprise Integration Pattern (EIP).

- **Content Enricher** bổ sung thông tin cho **một message hiện có**, thường bằng cách tra cứu dữ liệu tham chiếu hoặc gọi một hệ thống phụ trợ.
- **Aggregator** thu thập **nhiều message thuộc cùng nhóm**, giữ trạng thái nhóm, chờ điều kiện hoàn thành (*release condition*) rồi phát một message kết quả.

Bài thuộc chương **Content enricher** của module **SPRING_INTEGRATION_PATTERN**. Module tập trung triển khai EIP với Spring Integration để xây luồng thông điệp ít phụ thuộc, dễ mở rộng; thực hành Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation, đồng thời kiểm thử, theo dõi các nhánh xử lý. Trọng tâm bài này là chọn **đúng pattern theo nguồn dữ liệu, số lượng message, thời điểm dữ liệu xuất hiện và cơ chế hoàn tất**.

## 1. Mục tiêu học tập

Sau khi học xong, bạn có thể:

1. Giải thích Content Enricher và Aggregator bằng khái niệm đầu vào, đầu ra và trạng thái.
2. Phân biệt hai dạng dữ liệu bổ sung: **tra cứu có thể yêu cầu ngay** và **những message độc lập đến theo thời gian**.
3. Biết khi nào Enricher phù hợp, khi nào phải dùng Aggregator, và khi nào nên kết hợp cả hai.
4. Thiết kế Enricher theo hợp đồng `OrderPlaced → EnrichedOrder`, với lookup có timeout, kiểm soát thiếu dữ liệu và khả năng kiểm thử.
5. Hiểu component `ContentEnricher` chuyên dụng so với `@Transformer` dùng để triển khai cùng ý tưởng nghiệp vụ.
6. Nắm các khái niệm `correlationStrategy`, `releaseStrategy`, `MessageGroup`, `MessageGroupStore`, timeout và xử lý nhóm chưa đủ.
7. Xây ví dụ Splitter → Aggregator bằng Java DSL, kiểm tra các sequence headers và kết quả gom nhóm.
8. Thiết kế trường hợp join các sự kiện độc lập, xử lý thứ tự đến bất định và chống duplicate.
9. Giải thích propagation của trace/correlation, lỗi enrich, retry, idempotency, dữ liệu nhạy cảm và quan sát tiến trình.
10. Viết unit test và integration test xác nhận **không nhầm lookup với tập hợp message**.

## 2. Hai bài toán nhìn giống nhau nhưng khác bản chất

### 2.1. Bài toán A: Đơn hàng thiếu thông tin khách hàng

Producer phát:

~~~text
OrderPlaced
  orderId: ORDER-1001
  customerId: CUST-21
  amount: 350.00
~~~

Hệ thống tính khuyến mãi cần `customerTier` và `active` đang nằm trong Customer Directory. Có thể gửi request tra cứu và nhận kết quả ngay theo hợp đồng:

~~~mermaid
flowchart LR
    O["OrderPlaced"] --> E["Content Enricher"]
    E -->|"lookup(CUST-21)"| D["Customer Directory"]
    D -->|"CustomerProfile"| E
    E --> R["EnrichedOrder"]
    R --> F["Filter / Router / Business Handler"]
~~~

Dưới góc nhìn flow chính, **một** message đầu vào tạo ra **một** message đã được bổ sung. Việc hệ thống tra cứu trả một object không khiến đây trở thành Aggregator; đó là kết quả của một lời gọi bổ sung thông tin để xử lý **message gốc**.

### 2.2. Bài toán B: Ba sự kiện độc lập phải hội tụ

Các producer độc lập lần lượt gửi:

~~~text
OrderPlaced(orderId=ORDER-1001)
PaymentCaptured(orderId=ORDER-1001)
InventoryReserved(orderId=ORDER-1001)
~~~

Không thể bảo đảm chúng đến cùng lúc hoặc đúng thứ tự. Hệ thống cần đợi đủ ba dữ kiện của **cùng một orderId** rồi phát `OrderReady`:

~~~mermaid
flowchart LR
    A["OrderPlaced"] --> AG["Aggregator"]
    P["PaymentCaptured"] --> AG
    I["InventoryReserved"] --> AG
    AG -->|"correlation=orderId"| G["Message Group"]
    G -->|"đủ 3 loại"| O["OrderReady"]
~~~

Ở đây có **ba input messages** riêng, cần **tích lũy trạng thái theo nhóm**. Đó chính là vai trò của Aggregator, không phải một Enricher tra cứu thông thường.

### 2.3. Tóm tắt bằng một phép so sánh

~~~text
ENRICHER
  Một message + thông tin được lấy bổ sung
      → Một message phong phú hơn

AGGREGATOR
  Nhiều message có cùng correlation key
      → Giữ trong một nhóm
      → Khi release condition đúng
      → Một message kết quả tổng hợp
~~~

Ký hiệu **1→1** và **N→1** là mô hình khái niệm của *đường xử lý thành công*: khi lookup lỗi, Enricher có thể không có output; khi nhóm hết hạn hoặc chính sách phát kết quả một phần, Aggregator có thể sinh một kết quả khác hoặc không sinh message hoàn chỉnh. Đừng coi đây là lời hứa chính xác một output trong mọi tình huống.

## 3. Bảng so sánh Enricher và Aggregator

| Khía cạnh | Content Enricher | Aggregator |
|---|---|---|
| Mục đích | Bổ sung dữ kiện còn thiếu cho message đang xử lý | Gom các message liên quan thành kết quả chung |
| Số message đầu vào chính | Thường 1 | Nhiều |
| Nguồn dữ liệu bổ sung | Lookup, service, cache, metadata, dữ liệu tham chiếu | Các message độc lập do Splitter hoặc producer khác phát |
| State nhóm theo thời gian | Thường không cần | Có: Message Group và group lifecycle |
| Correlation key | Có thể cần cho request–reply/tracing | **Cốt lõi** để nhóm message đúng |
| Release strategy | Không cần group release | **Cốt lõi** để biết lúc nào đủ nhóm |
| Thứ tự đến của nhiều phần | Thường không phải vấn đề chính | Có thể bất định, cần xử lý |
| Timeout | Timeout lookup/request | Timeout chờ nhóm hoặc expiry |
| Retry | Retry truy vấn tạm lỗi; tránh retry dữ liệu cố định | Retry delivery, xử lý duplicate, idempotent group output |
| Storage | Cache/lookup tùy thiết kế | Có thể cần `MessageGroupStore` bền vững |
| Output | Bản ghi được enrich | Bản ghi tổng hợp/collection/result |
| Spring Integration | `ContentEnricher` (payload enrichment), `HeaderEnricher`, `@Transformer` / Java DSL | Aggregating endpoint, `.aggregate(...)`, correlation/release strategies |
| Rủi ro đặc trưng | Lookup chậm, thiếu profile, stale cache, N+1 requests | Group không bao giờ đủ, duplicate, late arrival, memory growth |
| Câu hỏi chọn pattern | “Tôi lấy thêm trường cho message này ở đâu?” | “Những message nào thuộc cùng một nhóm và khi nào nhóm xong?” |

**Điểm phân biệt quyết định:** *mối quan hệ của dữ liệu bổ sung với message*. Nếu có một request–reply rõ ràng để lấy profile cho order hiện tại, thường dùng Enricher. Nếu dữ liệu sẽ **tới như các message riêng vào những thời điểm độc lập**, cần một cơ chế tương quan và chờ đợi — Aggregator hoặc một process manager chuyên dụng.

## 4. Content Enricher là gì?

Content Enricher nhận message, xác định những thông tin còn thiếu, thu thập chúng từ một nguồn phù hợp, rồi kết hợp vào payload hoặc message để endpoint sau có thể dùng.

Một chu trình phổ biến:

1. Nhận `OrderPlaced` có `customerId`.
2. Gửi request tra cứu `CustomerProfile` tới adapter/service/cache.
3. Kiểm tra kết quả có mặt, đúng khách hàng, đúng quyền truy cập và hợp đồng kiểu dữ liệu.
4. Tạo `EnrichedOrder` gồm dữ liệu đơn gốc và các trường bổ sung.
5. Chuyển message kết quả sang validation/Filter/Router tiếp theo.

Trong Spring Integration, **Content Enricher chuyên dụng** được hiện thực bằng `ContentEnricher` cho payload enrichment; Java DSL có bước `enrich(...)`. Tuy nhiên, nếu muốn tạo **một DTO bất biến hoàn toàn mới** và chỉ cần chuyển đổi thông tin, một `@Transformer` gọi service enrichment cũng có thể thực hiện cùng ý tưởng EIP. Đó là **lựa chọn triển khai**, không có nghĩa `@Transformer` và `ContentEnricher` là cùng một class.

### 4.1. Enricher khác Transformer như thế nào?

| Điều cần làm | Công cụ thường phù hợp |
|---|---|
| Đổi biểu diễn toàn payload, ví dụ `RawOrder` → `TypedOrder` | Transformer |
| Bổ sung `customerTier` vào dữ liệu đơn bằng kết quả lookup | Content Enricher |
| Bổ sung `traceId`/`tenantId` đã xác thực vào headers | Header Enricher |
| Tạo một `EnrichedOrder` bất biến từ `OrderPlaced` + profile | Có thể dùng Transformer đóng vai trò Enricher |
| Ghép ba kết quả async không cùng request–reply | Aggregator |

Một `ContentEnricher` có thể làm việc qua biểu thức/property trên đối tượng payload; với JavaBean mutable có thể có hành vi thay đổi thuộc tính. Nếu ứng dụng yêu cầu **bất biến dữ liệu**, ưu tiên tạo DTO mới theo hợp đồng và kiểm thử đối tượng đầu vào không bị mutate.

### 4.2. Đầu vào, đầu ra và bất biến

Ví dụ domain Java 17+:

~~~java
import java.math.BigDecimal;

public record OrderPlaced(
        String eventId,
        String orderId,
        String customerId,
        BigDecimal total
) {}

public record CustomerProfile(
        String customerId,
        String tier,
        boolean active
) {}

public record EnrichedOrder(
        String eventId,
        String orderId,
        String customerId,
        BigDecimal total,
        String tier,
        boolean customerActive
) {}
~~~

Các `public record` ở ví dụ này được trình bày cùng một code block để dễ so sánh; khi tạo project Java, đặt mỗi khai báo top-level `public` vào **source file riêng** có tên tương ứng.

Ba record có vai trò khác nhau:

- `OrderPlaced` là sự kiện đầu vào, chỉ biết ID và thông tin đơn.
- `CustomerProfile` là dữ liệu tham chiếu nhận được sau lookup.
- `EnrichedOrder` là kết quả phục vụ downstream.

Không nên dùng một `Map<String, Object>` chung rồi tùy ý `put("tier",...)` ở mọi endpoint. DTO có kiểu giúp thấy ngay trường nào được bổ sung và ngăn lỗi chính tả key.

## 5. Viết một Enricher có thể kiểm thử

Ta tách việc **truy xuất profile** và việc **ghép kết quả**. Mục tiêu là để phần kết hợp dữ liệu được thử nghiệm bằng Java thuần, không cần broker hoặc database.

### 5.1. Hợp đồng lookup

~~~java
import java.util.Optional;

@FunctionalInterface
public interface CustomerDirectory {
    Optional<CustomerProfile> findById(String customerId);
}
~~~

Sử dụng `Optional<CustomerProfile>` cho biết lookup **có thể không tìm thấy** một bản ghi. Điều này không đồng nghĩa lỗi mạng: "không tìm thấy" và "lookup thất bại" phải được phân loại riêng.

### 5.2. Exception có ý nghĩa

~~~java
public final class CustomerProfileMissingException
        extends RuntimeException {

    public CustomerProfileMissingException(String customerId) {
        super("CUSTOMER_PROFILE_MISSING: " + customerId);
    }
}
~~~

Trong môi trường thật, nội dung exception gửi tới client hoặc log có thể cần được **ẩn/mã hóa identifier** theo chính sách dữ liệu cá nhân. Ví dụ trên để người học hiểu logic; một hệ thống lớn nên dùng error code ổn định thay vì nối nguyên dữ liệu từ nguồn không tin cậy vào thông báo.

### 5.3. Service enrichment

~~~java
import java.util.Objects;

public final class OrderContentEnricher {

    private final CustomerDirectory directory;

    public OrderContentEnricher(CustomerDirectory directory) {
        this.directory =
                Objects.requireNonNull(directory, "directory");
    }

    public EnrichedOrder enrich(OrderPlaced order) {
        Objects.requireNonNull(order, "order");

        if (order.customerId() == null
                || order.customerId().isBlank()) {
            throw new IllegalArgumentException(
                    "customerId is required");
        }

        CustomerProfile profile = directory
                .findById(order.customerId())
                .orElseThrow(() ->
                        new CustomerProfileMissingException(
                                order.customerId()));

        // Chống lỗi lookup trả nhầm profile do cache/mapping.
        if (!order.customerId().equals(profile.customerId())) {
            throw new IllegalStateException(
                    "CUSTOMER_PROFILE_ID_MISMATCH");
        }

        return new EnrichedOrder(
                order.eventId(),
                order.orderId(),
                order.customerId(),
                order.total(),
                profile.tier(),
                profile.active());
    }
}
~~~

Ở đây `OrderContentEnricher` thực hiện một lần lookup và tạo DTO **mới**. Việc ghép dữ liệu không làm biến đổi `OrderPlaced` gốc. Trong hệ thống thực, cần thêm kiểm soát rằng profile lấy được **thuộc tenant/khách hàng được phép truy cập**. Chỉ so customerId là kiểm tra nhất quán dữ liệu, không đủ thay thế authorization.

### 5.4. Điều gì xảy ra khi lookup chậm hoặc lỗi?

Nếu `CustomerDirectory` được triển khai bằng REST/database:

- Một request có thể mất hàng trăm mili-giây hoặc timeout.
- Endpoint enrichment có thể trở thành nút thắt của toàn flow.
- Retry lookup có thể giúp khi lỗi mạng tạm thời.
- Không tìm thấy profile là **kết quả nghiệp vụ**, thường không nên retry vô hạn.
- Profile trả về có thể **stale** nếu cache chưa được cập nhật.
- Với nhiều order cùng customerId, lookup lặp gây vấn đề N+1 request.

Hãy quy định timeout, cache TTL, circuit breaker, bulkhead và concurrency ở tầng adapter phù hợp. Không giải quyết vấn đề lookup chậm bằng cách thay Enricher thành Aggregator nếu không có các **message độc lập** thực sự cần tương quan.

## 6. Tích hợp Enricher vào Spring Integration

Một phương án rõ ràng với DTO bất biến là tạo endpoint `@Transformer` để triển khai ý tưởng làm giàu nội dung:

~~~java
import org.springframework.integration.annotation.Transformer;

public final class OrderEnrichmentEndpoint {

    private final OrderContentEnricher enricher;

    public OrderEnrichmentEndpoint(OrderContentEnricher enricher) {
        this.enricher = enricher;
    }

    @Transformer(
            inputChannel = "orders.toEnrich",
            outputChannel = "orders.enriched")
    public EnrichedOrder enrich(OrderPlaced order) {
        return enricher.enrich(order);
    }
}
~~~

**Lưu ý:** đây là **Transformer đóng vai trò Content Enricher**, không phải đoạn cấu hình của `ContentEnricher` chuyên dụng. Nó hữu ích khi muốn tạo record đầu ra bất biến và kiểm thử độc lập.

### 6.1. Cấu hình một flow kiểm thử

~~~java
import java.util.Map;
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
public class OrderEnrichmentConfiguration {

    @Bean(name = "orders.toEnrich")
    public MessageChannel input() {
        return new DirectChannel();
    }

    @Bean(name = "orders.enriched")
    public PollableChannel enriched() {
        return new QueueChannel();
    }

    @Bean
    public CustomerDirectory customerDirectory() {
        Map<String, CustomerProfile> fixtures = Map.of(
                "CUST-21",
                new CustomerProfile("CUST-21", "GOLD", true),
                "CUST-22",
                new CustomerProfile("CUST-22", "STANDARD", true));

        // Chỉ minh họa: thay bằng adapter REST/DB ở production.
        return customerId ->
                Optional.ofNullable(fixtures.get(customerId));
    }

    @Bean
    public OrderContentEnricher contentEnricher(
            CustomerDirectory directory) {
        return new OrderContentEnricher(directory);
    }

    @Bean
    public OrderEnrichmentEndpoint orderEnrichmentEndpoint(
            OrderContentEnricher enricher) {
        return new OrderEnrichmentEndpoint(enricher);
    }
}
~~~

`QueueChannel` ở ví dụ chỉ để nhận kết quả trong JUnit, không phải một hàng đợi có độ bền dữ liệu qua restart. Khi triển khai thật, downstream thường là Filter/Router/Service Activator.

### 6.2. Message có trace/correlation

~~~java
import java.math.BigDecimal;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

OrderPlaced order = new OrderPlaced(
        "evt-1001",
        "ORDER-1001",
        "CUST-21",
        new BigDecimal("350.00"));

Message<OrderPlaced> input = MessageBuilder
        .withPayload(order)
        .setHeader("traceId", "trace-1001")
        .setHeader("businessCorrelationId", "ORDER-1001")
        .build();
~~~

Nếu gửi message này tới `orders.toEnrich`, endpoint tạo một payload `EnrichedOrder` với `tier="GOLD"`. Với Transformer trả payload, framework tạo message output và thường truyền các headers đầu vào thích hợp; phần test tiếp theo kiểm tra `traceId` thực tế.

### 6.3. ContentEnricher chuyên dụng cho payload

Spring Integration có component `ContentEnricher` và Java DSL `.enrich(...)`. Nó có thể gửi một **enrichment request** tới một request channel, nhận reply và dùng các property expressions để bổ sung thuộc tính của payload. Về mặt kiến trúc:

~~~text
orders.input
  -> ContentEnricher
       -> enrichment request
       -> customer.lookup.request
       <- customer.lookup.reply
       -> merge dữ liệu trả về vào payload theo property mapping
  -> orders.enriched
~~~

Các điểm cần hiểu trước khi dùng component này:

1. Chọn **dữ liệu cần gửi** sang nguồn lookup, ví dụ chỉ `customerId`.
2. Chọn **property đích** để cập nhật, ví dụ `customerTier`.
3. Đảm bảo reply có kiểu/shape mà các expressions xử lý được.
4. Xác định timeout, xử lý reply thiếu và lỗi lookup.
5. Kiểm soát việc tạo bản sao hoặc mutate payload tùy model và cấu hình.
6. Phải kiểm thử kết quả khi input/output chạy qua channel thực.

Nếu payload là `record` bất biến không có setter, không nên giả định một cấu hình property enrichment có thể tùy ý gán thêm field vào chính record. Trong trường hợp ấy, **tạo `EnrichedOrder` mới bằng Transformer** có thể đơn giản và an toàn hơn. Mấu chốt là **pattern** (bổ sung thông tin) không ép buộc chỉ một class Spring Integration.

## 7. Aggregator là gì và vì sao cần correlation?

Aggregator nhận nhiều message, phân nhóm theo một **correlation key**, duy trì trạng thái của từng nhóm và quyết định khi nào phát kết quả tổng hợp.

~~~mermaid
flowchart TB
    O["OrderPlaced(orderId=A)"] --> C{"correlationStrategy"}
    P["PaymentCaptured(orderId=A)"] --> C
    I["InventoryReserved(orderId=A)"] --> C
    C --> G["MessageGroup for A"]
    G --> R{"releaseStrategy"}
    R -->|Chưa đủ| WAIT["Tiếp tục chờ"]
    R -->|Đã đủ| M["Output processor"]
    M --> READY["OrderReady(A)"]
~~~

Hai chiến lược **không thể thiếu**:

- **Correlation strategy:** quyết định message thuộc **nhóm nào**, ví dụ `orderId`.
- **Release strategy:** quyết định nhóm đã **đủ thông tin để phát kết quả** hay chưa.

Ngoài ra còn:

- **Message Group Store:** giữ các message và metadata nhóm.
- **Aggregation output processor:** kết hợp payload của nhóm thành kết quả.
- **Expiry/timeout:** xử lý nhóm chờ quá lâu, thiếu phần hoặc message đến muộn.
- **Duplicate/late arrival handling:** tránh release nhầm và xử lý một phần nhiều lần.

### 7.1. Correlation đúng là điều kiện an toàn dữ liệu

Ví dụ có hai đơn:

~~~text
A: OrderPlaced(A), PaymentCaptured(A), InventoryReserved(A)
B: OrderPlaced(B), PaymentCaptured(B), InventoryReserved(B)
~~~

Aggregator phải tạo **hai nhóm độc lập**, A và B. Nếu chọn correlation theo `customerId`, những đơn khác nhau của cùng khách có thể bị **ghép nhầm**. Với mô hình này, `orderId` là ứng viên thích hợp hơn.

Khi dữ liệu đa tenant, chỉ `orderId` có thể chưa đủ nếu các tenant dùng ID trùng. Key an toàn có thể là `(tenantId, orderId)` với tenant đã được **xác thực** ở ingress.

### 7.2. Release không chỉ là đếm ba message

Một thiết kế đơn giản:

~~~text
release when group.size() == 3
~~~

có rủi ro nếu producer gửi hai bản `PaymentCaptured` và một `OrderPlaced` nhưng thiếu `InventoryReserved`: nhóm đủ ba message **theo số lượng** mà vẫn thiếu loại dữ liệu cần thiết.

Với sự kiện độc lập, release strategy tốt hơn là kiểm tra **đã có đúng các loại dữ liệu bắt buộc**, xử lý duplicate, xác định thông điệp mới nhất/phiên bản hợp lệ và tránh chọn bừa một message bất kỳ.

### 7.3. Aggregator không đồng nghĩa Splitter

**Splitter** tạo nhiều message từ một đầu vào; **Aggregator** có thể gom các message ấy lại. Tuy nhiên, Aggregator cũng có thể tập hợp **nhiều nguồn độc lập**, không nhất thiết phải xuất phát từ một Splitter.

- Splitter thường gắn `correlationId`, `sequenceNumber`, `sequenceSize`.
- Aggregator mặc định có thể tận dụng những metadata này để tạo group và biết khi nào đủ.
- Với sự kiện đến từ ba producer độc lập, không nhất thiết tồn tại `sequenceSize` đáng tin. Khi đó cần custom correlation và release strategy.

## 8. Ví dụ Spring Integration: Splitter → Aggregator

Một ví dụ tự chứa giúp phân biệt Aggregator với Enricher mà không cần giả lập ba hệ thống bất đồng bộ: một batch chứa nhiều dòng hàng được tách, tính thành tiền từng dòng và gom kết quả.

### 8.1. Các loại payload

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

Một `List<OrderLine>` ở đầu vào là **một message mang collection**. Splitter tạo một message cho mỗi phần tử; chúng liên quan bởi correlation/sequence headers.

### 8.2. Java DSL minh họa

~~~java
import java.math.BigDecimal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
public class OrderLinesAggregationConfiguration {

    @Bean
    public IntegrationFlow orderLinesFlow() {
        return IntegrationFlow.from("order.lines.batch")
                .split()
                .transform(OrderLine.class, line ->
                        new PricedLine(
                                line.sku(),
                                line.unitPrice().multiply(
                                        BigDecimal.valueOf(line.quantity()))))
                .aggregate()
                .channel("order.lines.aggregated")
                .get();
    }
}
~~~

Ý nghĩa:

1. `split()` chuyển các phần tử trong batch thành các message đơn.
2. `transform(...)` tính `PricedLine` cho từng message.
3. `aggregate()` nhóm các message theo correlation/sequence mà Splitter cung cấp.
4. Khi có đủ các phần tử theo release strategy mặc định, output là một message tổng hợp. Với default aggregation processor cho trường hợp collection, payload thường là **collection các payload kết quả**.
5. `order.lines.aggregated` là channel nhận kết quả; cần khai báo/kiểm tra output channel trong test hoặc app.

**Đây là ví dụ dùng Aggregator**: mặc dù producer chỉ gửi một batch message ban đầu, **sau Splitter** đã có nhiều message độc lập chạy qua các bước và được gom lại bởi một endpoint giữ group state.

### 8.3. Kiểm tra metadata do Splitter tạo

Một tập các message sau Splitter thường mang:

~~~text
correlationId: ID nhóm của batch
sequenceNumber: 1, 2, 3, ...
sequenceSize: số phần tử của batch
~~~

Các header được Spring Integration dùng trong cơ chế Aggregator mặc định; không tự tạo `sequenceSize` sai để ghép những message không thuộc cùng batch.

### 8.4. Điều gì nếu Filter loại một phần tử?

~~~mermaid
flowchart LR
    B["Batch 3 lines"] --> S["Splitter"]
    S --> L1["Line 1"]
    S --> L2["Line 2"]
    S --> L3["Line 3"]
    L1 --> A["Aggregator"]
    L2 --> F{"Filter"}
    F -->|Rejected| D["Discard"]
    L3 --> A
~~~

Nếu Splitter đặt `sequenceSize=3` nhưng Filter bỏ một message, Aggregator mặc định có thể chờ **đủ ba phần** và không bao giờ release theo tiêu chí ban đầu. Cần quyết định:

- Giữ một result đại diện cho phần bị loại để nhóm vẫn hoàn tất;
- Thay release strategy theo hợp đồng nghiệp vụ;
- Sử dụng timeout và chính sách partial-group;
- Hoặc Filter trước khi Splitter để tính đúng tập phần tử sẽ được gom.

Vấn đề **chờ nhóm** không phải đặc trưng của Enricher.

## 9. Aggregator cho nhiều sự kiện độc lập

Khi Order, Payment và Inventory được tạo bởi ba service khác nhau, hãy thiết kế contract trước khi viết DSL.

### 9.1. Các loại sự kiện

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

Các khai báo top-level `public` trong ví dụ được trình bày chung cho dễ đọc; khi đưa vào project Java, cần tách thành các source file tương ứng.

Một nhóm `OrderPart` hợp lệ cần có ít nhất một bản ghi của **mỗi loại**. Với duplicate event, phải có quy tắc chọn đúng phiên bản/ID thay vì lấy phần tử đầu tiên một cách tùy ý.

### 9.2. Logic kết hợp Java thuần

~~~java
import java.util.List;

public final class OrderPartAssembler {

    public boolean hasRequiredParts(List<OrderPart> parts) {
        return parts.stream().anyMatch(OrderRegistered.class::isInstance)
                && parts.stream().anyMatch(PaymentCaptured.class::isInstance)
                && parts.stream().anyMatch(InventoryReserved.class::isInstance);
    }

    public OrderReady assemble(List<OrderPart> parts) {
        if (!hasRequiredParts(parts)) {
            throw new IllegalArgumentException(
                    "ORDER_PARTS_INCOMPLETE");
        }

        OrderRegistered order = exactlyOne(parts, OrderRegistered.class);
        PaymentCaptured payment = exactlyOne(parts, PaymentCaptured.class);
        InventoryReserved inventory =
                exactlyOne(parts, InventoryReserved.class);

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
        List<T> matches = parts.stream()
                .filter(type::isInstance)
                .map(type::cast)
                .toList();

        if (matches.size() != 1) {
            throw new IllegalArgumentException(
                    "DUPLICATE_OR_MISSING_" + type.getSimpleName());
        }
        return matches.get(0);
    }
}
~~~

Hàm này cố ý **reject duplicate** thay vì tự chọn bản mới nhất, bởi chọn bản nào là một quy tắc nghiệp vụ phải được công bố. Trong production, có thể deduplicate theo `eventId` trước Aggregator, hoặc giữ version/timestamp đáng tin cậy để xử lý update/correction.

### 9.3. Correlation strategy

Với message có payload `OrderPart`:

~~~java
import org.springframework.messaging.Message;

public Object correlationKey(Message<?> message) {
    OrderPart part = (OrderPart) message.getPayload();
    return part.orderId();
}
~~~

Đây là **hàm minh họa** dùng trong adapter Aggregator. Nếu hệ thống đa tenant, nên tạo một key bất biến gồm tenantId được xác thực và orderId. Không lấy orderId thô từ producer chưa xác thực làm bằng chứng ownership.

### 9.4. Release strategy

Có thể kiểm tra group chứa đủ ba loại:

~~~java
import java.util.List;
import java.util.stream.Collectors;

import org.springframework.integration.store.MessageGroup;
import org.springframework.messaging.Message;

public boolean shouldRelease(
        MessageGroup group, OrderPartAssembler assembler) {
    List<OrderPart> parts = group.getMessages().stream()
            .map(Message::getPayload)
            .map(OrderPart.class::cast)
            .collect(Collectors.toList());

    return assembler.hasRequiredParts(parts);
}
~~~

Điều này chỉ là **điều kiện đủ về loại sự kiện**; muốn bảo đảm không có duplicate, cần kiểm tra số bản ghi mỗi loại hoặc dùng deduplication trước khi lưu group. Release strategy không tự giải quyết exactly-once.

### 9.5. Liên hệ với Spring Integration Aggregator

Spring Integration hỗ trợ `.aggregate(...)` và các cấu hình như `correlationStrategy`, `releaseStrategy`, `outputProcessor`. Kiến trúc đúng có dạng:

~~~text
order.parts.input
  -> Aggregator
       correlationStrategy(message) = orderId
       releaseStrategy(group) = có đủ OrderRegistered,
                                PaymentCaptured, InventoryReserved
       outputProcessor(group) = OrderPartAssembler.assemble(...)
       group timeout / expiry / message store / duplicate policy
  -> orders.ready
~~~

Đây là **mô tả cấu hình**, không phải Java DSL có thể sao chép nguyên xi. Mỗi hàm phải được nối vào Aggregator theo API của phiên bản Spring Integration trong dự án, cấu hình group timeout và MessageGroupStore nếu có yêu cầu durability. Không nhầm các phương thức trên với API của `ContentEnricher`.

### 9.6. Vì sao cần MessageGroupStore?

Giả sử PaymentCaptured đến lúc 10:00 và InventoryReserved đến lúc 10:05. Trong khoảng giữa, Aggregator phải giữ dữ liệu nhóm ở đâu đó. Spring Integration dùng `MessageGroupStore` để lưu group.

- Một store trong bộ nhớ đơn giản phù hợp test/prototype.
- Nếu yêu cầu sống sót sau restart, cần cấu hình backing store bền vững phù hợp và kiểm thử transaction/recovery.
- Nếu nhóm không bao giờ đủ, phải có timeout/expiry/eviction để tránh memory growth.
- Nếu sự kiện đến muộn sau khi nhóm đã release, cần chính sách late-arrival/reopening/reject.
- Nếu hai app instance cùng gom cùng orderId, cần xem xét locking, shared store và cơ chế delivery phù hợp.

Enricher thông thường không cần một **group store** để chờ ba event độc lập.

## 10. Tại sao không thay Aggregator bằng Enricher?

Một suy nghĩ có vẻ hợp lý là: khi `OrderPlaced` tới, Enricher gọi hai API `paymentStatus(orderId)` và `inventoryStatus(orderId)` rồi bổ sung dữ liệu. Cách đó **có thể đúng**, nhưng chỉ khi các API có thể cung cấp một snapshot nhất quán và hệ thống chấp nhận ngữ nghĩa truy vấn ngay.

Vấn đề xuất hiện khi:

1. `OrderPlaced` tới trước khi Payment/Inventory event được tạo.
2. Enricher gọi API nhiều lần nhưng trạng thái chưa sẵn sàng.
3. Message bị giữ chờ, retry hoặc polling tốn tài nguyên.
4. Trạng thái thay đổi giữa hai lần lookup, tạo snapshot không nhất quán.
5. Khi một API không hoạt động, toàn pipeline bị chặn.
6. Không có chính sách hoàn tất, hết hạn hay xử lý message đến muộn rõ ràng.

Nếu các phần dữ liệu **được phát như event độc lập**, Aggregator giải quyết nhu cầu **chờ và nhóm theo correlation** một cách trực tiếp hơn. Tuy nhiên, **Aggregator cũng không tự bảo đảm tính nhất quán hay exactly-once**; nó cần contract, duplicate policy, store và error handling.

### 10.1. Khi nào lookup của Enricher vẫn hợp lý?

- Customer profile có sẵn khi OrderPlaced được xử lý.
- Thông tin là reference data ổn định hoặc có TTL rõ.
- Bước enrich không cần chờ những event tương lai.
- Request–reply timeout có thể chấp nhận trong latency budget.
- Cần một **đầu ra ngay** cho mỗi order.
- Dữ liệu lookup được phép truy cập theo tenant/principal đã xác thực.

### 10.2. Khi nào Aggregator hợp lý hơn?

- Có nhiều message độc lập từ những nguồn khác nhau.
- Thời điểm và thứ tự đến không xác định.
- Phải đợi đủ dữ liệu trước khi phát kết quả.
- Cần phân nhóm theo `orderId` hoặc business correlation key.
- Cần timeout, xử lý nhóm chưa đủ, duplicate và late arrivals.
- Yêu cầu lưu group state và phục hồi có thể tồn tại.

## 11. Khi nào kết hợp cả Enricher và Aggregator?

Trong hệ thống thực, hai pattern không cạnh tranh nhau mà thường **bổ sung** nhau.

Ví dụ quy trình:

1. `OrderPlaced` tới.
2. Enricher tra Customer Directory để bổ sung tier và trạng thái customer.
3. Payment service phát `PaymentCaptured`.
4. Inventory service phát `InventoryReserved`.
5. Aggregator nhóm ba message theo orderId rồi phát `OrderReady`.
6. Router chọn priority/standard theo dữ liệu đã enrich.
7. Handler lưu kết quả và phát event, dùng idempotency.

~~~mermaid
flowchart TB
    OP["OrderPlaced"] --> EN["Content Enricher"]
    REF["Customer Directory"] -.->|"lookup"| EN
    EN --> EO["EnrichedOrderPlaced"]
    EO --> AG["Aggregator: orderId"]
    PAY["PaymentCaptured"] --> AG
    INV["InventoryReserved"] --> AG
    AG --> OK["OrderReady"]
    OK --> ROUTER{"Router"}
    ROUTER --> PRI["Priority handler"]
    ROUTER --> STD["Standard handler"]
~~~

Để triển khai ví dụ này, hãy thống nhất **schema** của message vào Aggregator: hoặc định nghĩa một sealed hierarchy cho ba loại input sau enrich, hoặc dùng adapter chuyển chúng về một format chung. `EnrichedOrderPlaced` là một loại phần của group, không phải message kết quả cuối.

## 12. Đường lỗi và retry khác nhau

### 12.1. Enricher lỗi

Ví dụ lookup Customer Directory bị timeout:

~~~text
OrderPlaced -> Enricher -> Customer Directory timeout
                          -> retry bounded
                          -> error channel / quarantine / fallback có chủ đích
~~~

Phân loại:

| Lỗi | Hướng xử lý |
|---|---|
| Customer ID rỗng | Validation/reject, không retry vô hạn |
| Không tìm thấy profile | Quy tắc nghiệp vụ: reject hoặc explicit fallback |
| HTTP 503 / timeout | Retry có giới hạn, backoff, circuit breaker |
| Profile không đúng tenant | Security/contract violation |
| Cache stale | Quản lý TTL/version, có thể làm mới theo chính sách |
| EnrichedOrder tạo thất bại | Error flow, không chuyển một object nửa hợp lệ |

**Fallback mặc định tier="STANDARD"** chỉ phù hợp nếu hợp đồng cho phép. Nó không được dùng để che lỗi profile không thể truy cập trong những flow cần chính xác về quyền lợi khách hàng.

### 12.2. Aggregator lỗi

Ví dụ chỉ có OrderPlaced và PaymentCaptured, còn InventoryReserved không bao giờ tới:

~~~text
group(orderId=ORDER-1001)
  OrderPlaced        arrived
  PaymentCaptured    arrived
  InventoryReserved  missing
  ---> timeout / expiry / incomplete-group policy
~~~

Đây không phải đơn giản là một request timeout của Enricher. Có **group state** cần giữ, loại bỏ, phát cảnh báo hoặc tạo kết quả partial theo hợp đồng.

| Lỗi/sự kiện | Hướng xử lý |
|---|---|
| Thiếu một part | Timeout, expiry, alert, partial result nếu được phép |
| Duplicate PaymentCaptured | Dedup theo event ID hoặc reject |
| orderId sai | Validation/reject trước khi đưa vào group |
| Message thuộc tenant khác | Correlation có tenant đã xác thực |
| Late arrival sau release | Chính sách reopen/reject/compensation |
| Process restart | Group store bền vững nếu yêu cầu |
| Aggregated output xử lý trùng | Idempotency ở downstream |

### 12.3. Error channel trong flow đồng bộ/bất đồng bộ

Ở một `DirectChannel` đồng bộ, exception từ Enricher có thể lan về caller; khi flow chạy bất đồng bộ, lỗi có thể được phát thành `ErrorMessage` theo cấu hình error channel/adapter. Aggregator có thể được kích hoạt bởi sự kiện đến, timeout hoặc expiry; nơi quan sát lỗi cần gắn với **group ID** và outcome, không chỉ với một request message.

**Không suy rằng đặt header `errorChannel` là mọi lỗi của mọi endpoint tự động đi vào đó.** Cần integration test trên topology thực tế.

## 13. Correlation: cùng tên nhưng khác nhiệm vụ

Cả Enricher và Aggregator có thể dùng từ “correlation”, nhưng mục đích không giống nhau.

### Enricher

- `customerId` dùng để **tra cứu** customer profile.
- `traceId` giúp theo dõi request–reply.
- `businessCorrelationId` gắn quá trình xử lý của đơn.
- Việc có customerId **không có nghĩa** phải tạo MessageGroup.

### Aggregator

- `orderId` hoặc composite `tenantId+orderId` dùng làm **correlation key**.
- Mọi part cùng key được đưa vào cùng một nhóm.
- `sequenceNumber` và `sequenceSize` (nếu đáng tin) hỗ trợ nhận biết nhóm đủ.
- Không thể dùng `MessageHeaders.ID` của từng message độc lập làm correlation key, vì mỗi message có ID khác nhau.

### Ví dụ đối chiếu

~~~text
Order A, customer CUST-21 -> enrichment lookup(CUST-21)
Order B, customer CUST-21 -> enrichment lookup(CUST-21)

Aggregator:
  group A = messages có orderId=A
  group B = messages có orderId=B

Không gom Order A và B chung chỉ vì cùng customerId.
~~~

Đây là lỗi thiết kế dữ liệu nghiêm trọng nếu hai đơn của cùng khách bị trộn vào một group và tạo kết quả thanh toán/tồn kho sai.

## 14. Đồng bộ, bất đồng bộ và độ trễ

### 14.1. Enricher có thể chặn thread

Khi Enricher gọi một service HTTP đồng bộ, thread xử lý có thể chờ kết quả. Với lượng message lớn:

- Cần timeout đủ ngắn và nhất quán với request budget.
- Giới hạn concurrency và số kết nối lookup.
- Có thể cache profile theo contract freshness.
- Cân nhắc batch lookup khi nhiều message dùng cùng key.
- Không để một external API lỗi gây nghẽn toàn hệ thống.

Enricher có thể được dùng trong một pipeline bất đồng bộ ở cấp channel; điều đó **không** khiến bản thân lookup trở thành một Aggregator.

### 14.2. Aggregator giữ trạng thái chờ

Aggregator thường chấp nhận nhiều message đến ở các thời điểm khác nhau và giữ group cho đến khi đủ. Latency của output phụ thuộc **part chậm nhất** hoặc chính sách timeout.

- Cần metric số group đang mở và tuổi group.
- Có giới hạn memory/store, expiry hoặc retention policy.
- Cần hiểu cách locking và concurrency khi nhiều message cùng group tới gần đồng thời.
- Có thể xử lý sự kiện out-of-order, nhưng phải có version/dedup nếu các part bị sửa.
- Phải quy định kết quả partial khi deadline đến.

Một Aggregator không tự làm message bền vững chỉ vì nó giữ group: loại `MessageGroupStore` quyết định durability.

## 15. Bảo toàn payload, headers và quyền truy cập

### 15.1. Với Enricher

Khi tạo `EnrichedOrder` mới, hãy bảo toàn các metadata cần cho downstream:

~~~text
traceId
businessCorrelationId
sourceSystem (đã xác minh)
schemaVersion
replyChannel / errorChannel (khi topology nội bộ cần)
~~~

Trong ví dụ `@Transformer` trả payload, framework thường truyền những header phù hợp sang output. Nếu bạn tự tạo `Message<?>` mới, phải kiểm soát header propagation. Khi message đi ra broker/API, **không sao chép mù** reply/error channel objects, token hoặc headers nhạy cảm.

### 15.2. Với Aggregator

Message nhóm có thể đến từ nhiều source và mang headers **khác nhau**. Không thể giả định output của Aggregator giữ mọi header theo cách không xung đột. Hãy thiết kế:

- Correlation ID của nhóm.
- Trace context dùng cho group và các part.
- Tenant/security context đáng tin cậy.
- Quy tắc chọn header nguồn nếu có nhiều giá trị khác nhau.
- Output schema rõ ràng, không dùng nguyên một part làm đại diện cho cả nhóm.

Khi dùng `DefaultAggregatingMessageGroupProcessor`, Spring Integration có quy tắc tổng hợp headers; nếu nghiệp vụ đòi metadata cụ thể, nên kiểm thử hoặc custom output processor. Không suy rằng `replyChannel` của một part sẽ tự trở thành reply channel đúng cho cả nhóm nhiều nguồn.

### 15.3. Tránh trộn dữ liệu đa tenant

Enricher phải kiểm tra quyền truy cập khi lookup Customer Directory. Aggregator phải tránh gộp message của hai tenant dù cùng orderId. **Cả hai** đều cần security boundary, nhưng khác nơi áp dụng: tra cứu dữ liệu tham chiếu so với phân nhóm message.

## 16. Unit test Enricher không cần Spring context

Ta có thể kiểm thử `OrderContentEnricher` trực tiếp với một stub `CustomerDirectory`.

### 16.1. Enrichment thành công

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.Optional;

import org.junit.jupiter.api.Test;

class OrderContentEnricherTest {

    @Test
    void addsCustomerTierWithoutMutatingOrder() {
        CustomerDirectory directory = id ->
                Optional.of(new CustomerProfile(
                        id, "GOLD", true));

        OrderContentEnricher enricher =
                new OrderContentEnricher(directory);

        OrderPlaced original = new OrderPlaced(
                "evt-1", "ORDER-1001", "CUST-21",
                new BigDecimal("350.00"));

        EnrichedOrder result = enricher.enrich(original);

        assertEquals("ORDER-1001", result.orderId());
        assertEquals("CUST-21", result.customerId());
        assertEquals("GOLD", result.tier());
        assertTrue(result.customerActive());
        assertEquals(
                new BigDecimal("350.00"), result.total());

        // Input record vẫn giữ nguyên dữ liệu.
        assertEquals("CUST-21", original.customerId());
        assertEquals(
                new BigDecimal("350.00"), original.total());
    }
}
~~~

Test này xác nhận converter/domain enrichment, không chứng minh Spring đã chuyển message sang channel chính xác.

### 16.2. Thiếu profile là lỗi có chủ đích

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.Optional;

import org.junit.jupiter.api.Test;

class MissingCustomerProfileTest {

    @Test
    void doesNotInventTierWhenProfileMissing() {
        CustomerDirectory missing =
                customerId -> Optional.empty();

        OrderContentEnricher enricher =
                new OrderContentEnricher(missing);

        OrderPlaced order = new OrderPlaced(
                "evt-2", "ORDER-1002", "CUST-404",
                new BigDecimal("200.00"));

        assertThrows(CustomerProfileMissingException.class,
                () -> enricher.enrich(order));
    }
}
~~~

Ở đây không tự tạo tier mặc định. Nếu sản phẩm có chính sách fallback, nên tách thành logic tường minh và có test; đừng biến mọi lỗi HTTP/timeout thành `Optional.empty()` rồi che nguyên nhân.

### 16.3. Lookup trả nhầm customerId

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.Optional;

import org.junit.jupiter.api.Test;

class ProfileConsistencyTest {

    @Test
    void rejectsProfileForAnotherCustomer() {
        CustomerDirectory corrupted = id ->
                Optional.of(new CustomerProfile(
                        "OTHER-CUSTOMER", "GOLD", true));

        OrderContentEnricher enricher =
                new OrderContentEnricher(corrupted);

        OrderPlaced order = new OrderPlaced(
                "evt-3", "ORDER-1003", "CUST-21",
                new BigDecimal("300.00"));

        IllegalStateException error =
                assertThrows(IllegalStateException.class,
                        () -> enricher.enrich(order));

        assertEquals(
                "CUSTOMER_PROFILE_ID_MISMATCH",
                error.getMessage());
    }
}
~~~

Đối với dữ liệu đa tenant, bổ sung test quyền truy cập và tenant scope ở adapter lookup. Việc có cùng ID chưa đủ nếu hai hệ thống không chia sẻ namespace.

## 17. Integration test Enricher qua channel

Unit test không xác nhận endpoint `@Transformer` được đăng ký, output channel tồn tại hay trace headers được giữ. Một test với Spring Test sẽ kiểm tra topology.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = OrderEnrichmentConfiguration.class)
class OrderEnrichmentFlowTest {

    @Autowired
    @Qualifier("orders.toEnrich")
    MessageChannel input;

    @Autowired
    @Qualifier("orders.enriched")
    PollableChannel output;

    @Test
    void enrichesAndPreservesTracing() {
        OrderPlaced order = new OrderPlaced(
                "evt-1",
                "ORDER-1001",
                "CUST-21",
                new BigDecimal("350.00"));

        assertTrue(input.send(
                MessageBuilder.withPayload(order)
                        .setHeader("traceId", "trace-1001")
                        .setHeader("businessCorrelationId",
                                "ORDER-1001")
                        .build()));

        Message<?> result = output.receive(1000);
        assertNotNull(result);
        assertInstanceOf(
                EnrichedOrder.class, result.getPayload());

        EnrichedOrder enriched =
                (EnrichedOrder) result.getPayload();

        assertEquals("GOLD", enriched.tier());
        assertEquals("ORDER-1001", enriched.orderId());
        assertEquals(
                "trace-1001",
                result.getHeaders().get("traceId"));
        assertEquals(
                "ORDER-1001",
                result.getHeaders().get("businessCorrelationId"));
    }
}
~~~

Với `DirectChannel` và fixture lookup trong bộ nhớ, ví dụ chạy đồng bộ. Nếu thay bằng HTTP client thật, test nên dùng stub server/fake adapter để không phụ thuộc network. `send()==true` không chứng minh mọi xử lý phía sau đã hoàn tất trong flow bất đồng bộ.

## 18. Kiểm thử Aggregator và group lifecycle

### 18.1. Unit test ghép part với thứ tự bất định

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.List;

import org.junit.jupiter.api.Test;

class OrderPartAssemblerTest {

    private final OrderPartAssembler assembler =
            new OrderPartAssembler();

    @Test
    void assemblesPartsRegardlessOfArrivalOrder() {
        List<OrderPart> parts = List.of(
                new InventoryReserved("ORDER-9", "RES-9"),
                new OrderRegistered(
                        "ORDER-9",
                        "CUST-9",
                        new BigDecimal("900.00")),
                new PaymentCaptured("ORDER-9", "PAY-9"));

        assertTrue(assembler.hasRequiredParts(parts));

        OrderReady result = assembler.assemble(parts);

        assertEquals("ORDER-9", result.orderId());
        assertEquals("CUST-9", result.customerId());
        assertEquals("PAY-9", result.paymentId());
        assertEquals("RES-9", result.reservationId());
    }

    @Test
    void rejectsGroupWithoutInventoryPart() {
        List<OrderPart> incomplete = List.of(
                new OrderRegistered(
                        "ORDER-9",
                        "CUST-9",
                        new BigDecimal("900.00")),
                new PaymentCaptured("ORDER-9", "PAY-9"));

        assertFalse(assembler.hasRequiredParts(incomplete));

        assertThrows(
                IllegalArgumentException.class,
                () -> assembler.assemble(incomplete));
    }

    @Test
    void rejectsDuplicatePaymentPart() {
        List<OrderPart> duplicated = List.of(
                new OrderRegistered(
                        "ORDER-9",
                        "CUST-9",
                        new BigDecimal("900.00")),
                new PaymentCaptured("ORDER-9", "PAY-9"),
                new PaymentCaptured("ORDER-9", "PAY-9-DUP"),
                new InventoryReserved("ORDER-9", "RES-9"));

        assertThrows(
                IllegalArgumentException.class,
                () -> assembler.assemble(duplicated));
    }
}
~~~

Các test này kiểm tra **tính đúng của output processor**, không thay thế integration test Aggregator thực về correlation, MessageGroupStore, timeout và release strategy.

### 18.2. Test Splitter → Aggregator có sequence headers

Với `OrderLinesAggregationConfiguration` ở mục 8 và các channel thích hợp, một integration test nên:

1. Gửi một message chứa `List<OrderLine>`.
2. Xác nhận `Splitter` tạo các phần tử và Aggregator gom thành một output.
3. Kiểm tra mọi lineTotal đúng với số lượng/đơn giá.
4. Kiểm tra một batch khác có correlation key khác không bị trộn.
5. Test một phần bị loại trước Aggregator để thấy trường hợp group không đủ nếu chưa điều chỉnh release/timeout.

Đối với demo in-memory, test với `QueueChannel` ở output có thể đọc kết quả. Trong production cần thêm test group state với storage và deadline, nhất là khi xử lý đồng thời.

### 18.3. Test nhiều nguồn độc lập

Với ba sự kiện độc lập, nên thử mọi thứ tự đáng chú ý:

~~~text
Order → Payment → Inventory
Payment → Inventory → Order
Inventory → Order → Payment
Order → Order(duplicate) → Payment → Inventory
Order(A) → Payment(B) → Inventory(A) → Payment(A) → ...
~~~

Các điều kiện phải thỏa:

- Không phát `OrderReady(A)` trước khi đủ dữ liệu thuộc A.
- Không dùng Payment của B để hoàn tất A.
- Duplicate phải được xử lý theo chính sách, không bị tính là một loại part khác.
- Sau timeout, nhóm chưa đủ có outcome rõ ràng.
- Late arrival sau release có behavior được định nghĩa.

## 19. Decision tree: chọn Enricher hay Aggregator?

~~~mermaid
flowchart TD
    START["Thiếu dữ liệu để xử lý?"] --> Q1{"Dữ liệu bổ sung có thể tra cứu theo request ngay?"}
    Q1 -->|Có| Q2{"Chỉ cần bổ sung một message hiện tại?"}
    Q2 -->|Có| E["Content Enricher"]
    Q2 -->|Không| MORE["Xem xét pipeline / fan-out / join"]
    Q1 -->|Không: dữ liệu sẽ đến như event| Q3{"Có nhiều message cần tương quan và chờ đủ?"}
    Q3 -->|Có| A["Aggregator"]
    Q3 -->|Không| OTHER["Router / Filter / Transformer / workflow khác"]
    E --> FOLLOW["Có thể tiếp tục Router / Filter"]
    A --> FOLLOW
~~~

Một số câu hỏi cụ thể trước khi quyết định:

1. **Ai sở hữu thông tin bổ sung?** Customer Directory có thể trả snapshot ngay hay Payment Service chỉ phát event khi xử lý xong?
2. **Tôi đang thêm field hay chờ nhiều message?** Thêm `tier` từ lookup khác với đợi đủ payment/inventory.
3. **Có cần giữ state lâu không?** Nếu có, nghĩ tới Aggregator/process manager và storage.
4. **Điều kiện hoàn tất là gì?** Enricher hoàn tất khi request lookup/reply xong; Aggregator khi release condition đúng.
5. **Thiếu dữ liệu thì sao?** Enricher: timeout/fallback/reject; Aggregator: incomplete group/expiry/compensation.
6. **Có cần kết quả ngay cho Gateway?** Enricher thường phù hợp với latency ngắn, còn Aggregator có thể cần async result hoặc SLA dài.
7. **Có phải dữ liệu bổ sung từ nhiều nguồn không?** Nhiều API lookup không tự biến flow thành Aggregator; nhiều event độc lập cần giữ group mới là tín hiệu mạnh.
8. **Dữ liệu nào dùng làm correlation?** Với Aggregator, key phải đủ phân biệt từng nhóm và tenant.
9. **Có duplicate/replay không?** Cả hai cần idempotency downstream; Aggregator còn cần dedup part.
10. **Cần khôi phục sau crash không?** Có thể yêu cầu group persistence và replay.

## 20. Hiệu năng và quan sát vận hành

### 20.1. Enricher cần metric gì?

| Metric/log field | Mục tiêu |
|---|---|
| `enrichment_requests_total` | Số lookup |
| `enrichment_success_total` | Số message được enrich thành công |
| `enrichment_failure_total{code}` | Không tìm thấy, timeout, sai contract |
| `enrichment_duration_seconds` | Latency lookup/merge |
| `customer_cache_hit_ratio` | Hiệu quả cache nếu có |
| `traceId` và `businessCorrelationId` | Chẩn đoán request cụ thể |

Đừng dùng customerId hoặc orderId làm metric label có cardinality cao; đặt trong log/trace với chính sách bảo mật.

### 20.2. Aggregator cần metric gì?

| Metric/log field | Mục tiêu |
|---|---|
| `aggregation_open_groups` | Số nhóm đang chờ |
| `aggregation_group_age_seconds` | Nhóm chờ quá lâu |
| `aggregation_completed_total` | Nhóm release thành công |
| `aggregation_expired_total` | Nhóm timeout/hết hạn |
| `aggregation_duplicates_total` | Message part trùng |
| `aggregation_late_arrivals_total` | Message tới sau khi nhóm đóng |
| `correlationKey` (log/trace, không metric label tùy ý) | Truy vết một nhóm |

Cả hai pattern có thể ảnh hưởng throughput, nhưng nút thắt rất khác: **Enricher bị chi phối bởi latency lookup**, **Aggregator bị chi phối bởi số nhóm đang mở, kích thước store và thời gian chờ part**.

### 20.3. Cảnh báo hành vi bất thường

- Enrichment failure tăng đột ngột: Customer Directory có thể lỗi hoặc đổi schema.
- Lookup latency tăng: thread pool/channel ở upstream có thể nghẽn.
- Open groups tăng liên tục: part bị mất, correlation sai, release strategy không khớp.
- Late arrivals tăng: producer trễ, timeout quá ngắn hoặc duplicate/retry bất thường.
- Aggregation output duplicate: cần kiểm tra idempotency và group lifecycle.

Monitoring của Aggregator không thể thay hoàn toàn bằng monitor HTTP lookup của Enricher.

## 21. Lỗi thiết kế phổ biến

### Lỗi 1 — Gọi Aggregator chỉ để tra một hồ sơ khách hàng

**Triệu chứng:** tạo MessageGroup theo customerId để bổ sung tier cho đơn đã có đủ thông tin.

**Vấn đề:** thêm group state, release/timeout phức tạp không cần thiết và có thể gộp nhiều order cùng customer.

**Khắc phục:** dùng Enricher tra cứu profile; nếu cần cache, thiết kế cache theo hợp đồng.

### Lỗi 2 — Dùng Enricher polling mãi để chờ sự kiện tương lai

**Triệu chứng:** sau OrderPlaced, code gọi payment/inventory API liên tục để chờ trạng thái sẵn sàng.

**Vấn đề:** tốn tài nguyên, tăng latency, khó kiểm soát deadline và tạo snapshot có thể không nhất quán.

**Khắc phục:** nếu hệ thống phát các event độc lập, cân nhắc Aggregator hoặc process manager với correlation và timeout.

### Lỗi 3 — Chọn correlation key là customerId

**Triệu chứng:** một khách có hai đơn bị ghép chung thông tin payment/inventory.

**Khắc phục:** chọn orderId (và tenantId nếu cần) theo đúng vòng đời nghiệp vụ.

### Lỗi 4 — Release ngay khi group có ba message

**Triệu chứng:** duplicate Payment khiến group có ba message dù thiếu Inventory.

**Khắc phục:** kiểm tra đủ **loại part**; có dedup/phiên bản và chính sách xử lý duplicate.

### Lỗi 5 — Không cấu hình group timeout/expiry

**Triệu chứng:** group chưa đủ tồn tại mãi, memory/store tăng.

**Khắc phục:** đặt deadline, giám sát tuổi nhóm và quyết định rõ incomplete-group behavior.

### Lỗi 6 — Enricher trả default cho mọi lỗi

**Triệu chứng:** Customer Directory timeout nhưng tier bị gán STANDARD như thể dữ liệu hợp lệ.

**Khắc phục:** phân biệt "không tìm thấy", "lỗi hạ tầng", "không đủ quyền"; fallback chỉ khi hợp đồng cho phép.

### Lỗi 7 — Nhầm correlationId với traceId

**Triệu chứng:** các part được nhóm theo traceId dù nguồn payment và inventory có trace khác nhau.

**Khắc phục:** correlation key là **business identity** đủ ổn định cho group; traceId dành cho tracing.

### Lỗi 8 — Xem MessageGroupStore mặc định là durable

**Triệu chứng:** restart làm mất group đang chờ.

**Khắc phục:** cấu hình persistent MessageGroupStore nếu yêu cầu, kèm transaction/recovery test.

### Lỗi 9 — Mutate payload gốc trong Enricher

**Triệu chứng:** các nhánh Publish–Subscribe cùng dùng object mutable, một nhánh thấy field bị thêm/sửa ngoài ý muốn.

**Khắc phục:** dùng DTO bất biến và tạo output mới; kiểm tra behavior khi sử dụng `ContentEnricher` với property mutation.

### Lỗi 10 — Tin output của Aggregator luôn giữ mọi header

**Triệu chứng:** replyChannel/tenantId/trace context biến mất hoặc bị lấy từ part sai.

**Khắc phục:** custom output processor/mapping header và integration test cho metadata.

### Lỗi 11 — Retry toàn quy trình gây side effect trùng

**Triệu chứng:** Enricher lookup lại hoặc Aggregator release lại và downstream gửi email/ghi DB nhiều lần.

**Khắc phục:** giữ eventId ổn định, dedup part và idempotency ở handler có side effect.

### Lỗi 12 — Dùng default aggregate mà input không có sequence size

**Triệu chứng:** message được giữ vô hạn vì không biết bao giờ đủ nhóm.

**Khắc phục:** với các producer độc lập, cấu hình correlation/release strategy rõ thay vì dựa vào metadata do Splitter tạo.

## 22. Bài tập thực hành

### Bài 1 — Enricher bổ sung hồ sơ

Tạo `OrderPlaced`, `CustomerProfile`, `EnrichedOrder` và `CustomerDirectory`. Viết `OrderContentEnricher` gọi lookup và sinh DTO bất biến; test một customer GOLD và một customer không tìm thấy.

### Bài 2 — Kiểm thử header propagation

Dùng `@Transformer` triển khai Content Enricher trên `orders.toEnrich`. Gửi message có `traceId` và `businessCorrelationId`, assert payload ra đúng và headers vẫn giữ. Không gọi API thật trong test.

### Bài 3 — Content Enricher chuyên dụng

Thử cấu hình `ContentEnricher` hoặc DSL `enrich(...)` cho một JavaBean mutable có property `customerTier`, sử dụng lookup request–reply. So sánh với `@Transformer` trả `EnrichedOrder` record bất biến; kiểm tra xem input có bị mutate không.

### Bài 4 — Splitter → Aggregator

Gửi một batch ba `OrderLine`, dùng Splitter tách thành ba message, Transformer tính tiền từng dòng, Aggregator gom lại. Test output chỉ xuất hiện khi đã đủ các phần và không trộn hai batch.

### Bài 5 — Filter làm thiếu một phần

Bỏ một line sau Splitter, quan sát Aggregator mặc định có release hay chờ. Đề xuất điều chỉnh flow hoặc release strategy/timeout theo hợp đồng nghiệp vụ.

### Bài 6 — Ba nguồn sự kiện

Thiết kế Aggregator cho `OrderRegistered`, `PaymentCaptured`, `InventoryReserved`. Chọn correlation theo orderId, release khi đủ ba loại và output `OrderReady`. Test đủ cả ba thứ tự đến khác nhau.

### Bài 7 — Duplicate và late arrival

Cho PaymentCaptured gửi hai bản và InventoryReserved đến sau timeout. Quy định xử lý duplicate/late arrival; xác minh hệ thống không phát hai lần `OrderReady` cho cùng event nghiệp vụ.

### Bài 8 — Enricher kết hợp Aggregator

Bổ sung tier cho OrderRegistered trước khi vào Aggregator với Payment/Inventory. Sau release, dùng Router chọn priority/standard. Test rằng cùng customerId nhưng hai order khác nhau vẫn tạo hai group.

### Bài 9 — Lỗi hạ tầng khác dữ liệu thiếu

Giả lập Customer Directory trả not found, trả timeout và trả profile sai ID. So sánh lỗi; chỉ retry timeout có giới hạn. Không mặc nhiên trả profile STANDARD cho cả ba trường hợp.

### Bài 10 — Khôi phục trạng thái

Lập kế hoạch persistent store cho Aggregator, mô phỏng restart khi nhóm mới có hai phần. Nêu rõ điều kiện khôi phục, dedup và reconciliation. Giải thích vì sao một Enricher lookup ngắn không cần cùng cơ chế group persistence.

### Câu hỏi tự kiểm tra

1. Vì sao `OrderPlaced + CustomerProfile lookup` thường là Content Enricher, không phải Aggregator?
2. Hai pattern khác nhau ở số input messages và nhu cầu giữ state như thế nào?
3. Khi PaymentCaptured tới muộn, Enricher có tự giữ OrderPlaced chờ event không?
4. Correlation key của Aggregator nên được chọn theo nguyên tắc nào?
5. Tại sao `group.size()==3` có thể release sai?
6. Vì sao cùng customerId không có nghĩa hai order phải vào cùng group?
7. Khi nào `@Transformer` có thể dùng để triển khai ý tưởng enrichment?
8. ContentEnricher chuyên dụng khác Header Enricher ở đâu?
9. Với `record` bất biến, vì sao cần cẩn thận khi dùng property enrichment?
10. `MessageGroupStore` có tác dụng gì, và mặc định có bảo đảm durable qua restart không?
11. Nếu Filter loại một phần sau Splitter, Aggregator có nguy cơ gì?
12. Trong luồng request–reply, Enricher và Aggregator có các loại timeout khác nhau như thế nào?
13. Khi aggregator output chỉ có một traceId, có thể kết luận mọi part mang cùng traceId không?
14. Enricher và Aggregator có cần idempotency không, và đặt ở đâu?
15. Cần những metric nào để phân biệt lookup chậm với nhóm chờ quá lâu?

## 23. Checklist kiến trúc

- [ ] Đã xác định **một message cần bổ sung dữ liệu** hay **nhiều message cần hội tụ**.
- [ ] Nguồn bổ sung có thể lookup request–reply hay chỉ phát event khi sẵn sàng.
- [ ] Với Enricher, có timeout, fallback/reject và phân loại lỗi lookup.
- [ ] Với Enricher, dữ liệu sau enrich có kiểu rõ, không mutate đầu vào ngoài ý muốn.
- [ ] Có kiểm soát tenant/authorization khi lấy reference data.
- [ ] Với Aggregator, correlation key ổn định và không trộn tenant/order.
- [ ] Với Aggregator, release strategy kiểm tra **đủ nội dung cần thiết**, không chỉ đếm mù.
- [ ] Có duplicate, late arrival, timeout và incomplete-group policy.
- [ ] Group state có store và chính sách phục hồi phù hợp yêu cầu durability.
- [ ] Output processor có schema rõ và xử lý headers/correlation đúng.
- [ ] Filter sau Splitter không làm Aggregator chờ vô hạn ngoài ý định.
- [ ] Retry chỉ dùng cho lỗi có thể phục hồi, không che dữ liệu sai cố định.
- [ ] Handler có side effect có idempotency key ổn định.
- [ ] Có unit test logic enrich/assemble và integration test channel/group lifecycle.
- [ ] Đo metric riêng cho enrichment lookup và aggregation group.
- [ ] Không dùng Routing Slip/traceId/message ID làm thay business correlation key.
- [ ] Tài liệu giải thích rõ nơi dùng Content Enricher, Aggregator và vị trí kết hợp cả hai.

## 24. Tổng kết

**Content Enricher** và **Aggregator** đều tạo đầu ra nhiều thông tin hơn đầu vào nhưng giải quyết **hai bài toán khác nhau**. Enricher bổ sung dữ liệu cho **message hiện tại**, thường qua lookup có request–reply, rồi tiếp tục xử lý. Aggregator **nhận nhiều message riêng biệt**, gom theo correlation key, chờ release condition và sinh một kết quả chung; nó còn phải quản lý state, timeout, duplicate và late arrival.

Trong Spring Integration, Content Enricher có thể triển khai bằng component `ContentEnricher` chuyên dụng hoặc một `@Transformer` tạo DTO enriched bất biến. Aggregator sử dụng `MessageGroup`, correlation/release strategies và output processor, thường kết hợp Splitter hoặc nhiều nguồn sự kiện. Chọn đúng pattern giúp giảm độ phụ thuộc giữa các endpoint, tránh những vòng polling không cần thiết hoặc những group state thừa, đồng thời xác định chính xác nơi cần retry, error channel, correlation và kiểm thử.

Với module **SPRING_INTEGRATION_PATTERN**, cách tiếp cận hiệu quả là **enrich dữ liệu tham chiếu khi lookup khả thi; aggregate khi nhiều message cần hội tụ; và kết hợp hai pattern khi một quy trình vừa cần bổ sung thuộc tính vừa phải chờ đủ các sự kiện độc lập**.

### Tài liệu tham khảo

- Spring Integration Reference — Content Enricher: https://docs.spring.io/spring-integration/reference/content-enrichment.html
- Spring Integration Reference — Aggregator: https://docs.spring.io/spring-integration/reference/aggregator.html
- Spring Integration Reference — Splitter: https://docs.spring.io/spring-integration/reference/splitter.html
- Spring Integration Reference — Java DSL: https://docs.spring.io/spring-integration/reference/dsl.html
- Spring Integration Reference — Message Store: https://docs.spring.io/spring-integration/reference/message-store.html
- Spring Integration API — ContentEnricher: https://docs.spring.io/spring-integration/api/org/springframework/integration/transformer/ContentEnricher.html
- Spring Integration API — MessageGroup: https://docs.spring.io/spring-integration/api/org/springframework/integration/store/MessageGroup.html
- Spring Integration API — ReleaseStrategy: https://docs.spring.io/spring-integration/api/org/springframework/integration/aggregator/ReleaseStrategy.html
- Spring Integration API — CorrelationStrategy: https://docs.spring.io/spring-integration/api/org/springframework/integration/aggregator/CorrelationStrategy.html
- JUnit 5 User Guide — Parameterized Tests: https://junit.org/junit5/docs/current/user-guide/#writing-tests-parameterized-tests

