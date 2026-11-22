# Giữ payload gốc và dữ liệu đã enrich

## 1. Vì sao cần giữ cả dữ liệu ban đầu và dữ liệu bổ sung?

Trong một luồng tích hợp đơn hàng, message ban đầu chỉ có mã đơn, mã khách hàng và số tiền. Trước khi quyết định nhánh xử lý, hệ thống cần truy vấn thông tin hồ sơ khách hàng, như hạng thành viên hoặc trạng thái xác minh. **Content Enricher** là Enterprise Integration Pattern (EIP) bổ sung thông tin cho message dựa trên dữ liệu sẵn có hoặc dữ liệu lấy từ một nguồn khác.

Ví dụ:

~~~text
Payload gốc từ Checkout:
  orderId    = ORD-1001
  customerId = C-007
  amountVnd  = 9000000

Dữ liệu trả về từ Customer Profile Service:
  customerId = C-007
  tier       = GOLD
  verified   = true

Payload sau enrich:
  original:
    orderId    = ORD-1001
    customerId = C-007
    amountVnd  = 9000000
  profile:
    customerId = C-007
    tier       = GOLD
    verified   = true
  enrichment:
    source     = customer-profile
    retrievedAt= ...
~~~

Yêu cầu **giữ payload gốc** có nghĩa dữ liệu ban đầu vẫn truy xuất được sau bước enrich, không bị ghi đè bằng câu trả lời của hệ thống tra cứu. Đồng thời cần giữ **dữ liệu đã enrich** như một thành phần tách biệt, biết nó đến từ đâu, được lấy khi nào và có còn phù hợp với message gốc không.

~~~mermaid
flowchart LR
    A[OrderRequest gốc] --> E[Content Enricher]
    E --> L[Profile lookup]
    L --> E
    E --> O["EnrichedOrder"]
    O --> OG["original: OrderRequest"]
    O --> PG["profile: CustomerProfile"]
    O --> MG["metadata: source / retrievedAt"]
    O --> R[Router / Filter / Handler]
~~~

Nếu chỉ giữ kết quả lookup, các bước sau không còn biết **số tiền, mã đơn và yêu cầu ban đầu**. Nếu chỉ sửa trực tiếp payload gốc để thêm dữ liệu, audit và retry có thể không phân biệt được **client thật sự gửi gì** với **hệ thống đã bổ sung gì**. Một cấu trúc rõ ràng giúp giải quyết cả hai vấn đề.

Bài thuộc chương **Content enricher** của module `SPRING_INTEGRATION_PATTERN`. Phạm vi module là thực hành các Enterprise Integration Patterns trong Spring Integration để xây dựng message flow ít phụ thuộc, dễ mở rộng, kết hợp Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation, đồng thời kiểm thử và theo dõi từng nhánh.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **payload gốc**, **enriched payload**, **metadata/provenance** và **message headers**.
2. So sánh enrich bằng cách **sửa object**, **tạo object mới**, hoặc **bao cả dữ liệu gốc và dữ liệu bổ sung trong envelope**.
3. Viết một integration flow Java DSL thực hiện enrichment mà không làm mất input gốc.
4. Hiểu cách dùng nguồn lookup đồng bộ, cách ánh xạ request/reply và giới hạn của Content Enricher.
5. Thiết kế khi lookup thiếu dữ liệu, sai ID, timeout, trả dữ liệu cũ hoặc lỗi.
6. Kiểm thử bất biến, dữ liệu enrichment, correlation, idempotency và khả năng truy nguyên.

## 2. Content Enricher thực chất làm gì?

### 2.1. Quy trình cơ bản

~~~text
Message<OrderRequest>
    |
    v
Lấy lookup key từ OrderRequest.customerId
    |
    v
Gọi Customer Profile (local repository / outbound gateway)
    |
    v
Kiểm tra response khớp customerId và hợp lệ
    |
    v
Tạo EnrichedOrder(original, profile, lookupMetadata)
    |
    v
Message<EnrichedOrder> -> downstream
~~~

Content Enricher thường bao gồm **tạo yêu cầu bổ sung dữ liệu**, **chờ/nhận phản hồi** và **kết hợp** dữ liệu nhận được với payload ban đầu. Spring Integration có hỗ trợ **Content Enricher** trong framework, và cũng có thể hiện thực cùng pattern bằng các endpoint/Gateway/Transformer có trách nhiệm rõ ràng.

**Điểm quan trọng:** Content Enricher không phải một Router. Nó làm thay đổi **nội dung có sẵn cho bước sau**, không tự quyết định message phải đi channel nào. Nếu sau enrich cần điều hướng theo `profile.tier`, hãy đặt **Router sau bước enrich**.

### 2.2. Những gì phải được giữ

| Thành phần | Ví dụ | Vai trò |
|---|---|---|
| **Original payload** | `OrderRequest(orderId, customerId, amountVnd)` | Bằng chứng dữ liệu ban đầu dùng cho nghiệp vụ. |
| **Enrichment result** | `CustomerProfile(tier, verified)` | Thông tin bổ sung để quyết định và xử lý. |
| **Lookup metadata** | `source`, `retrievedAt`, `lookupRequestId` | Nguồn gốc, thời điểm và khả năng truy nguyên. |
| **Message headers** | `traceId`, `correlationId`, `replyChannel` | Ngữ cảnh của luồng message, không phải bản sao tự động của payload. |
| **Business decision** | `requiresManualReview` | Kết luận do một policy tính từ cả original và profile; nên tách khỏi dữ liệu thô. |

Giữ payload gốc **không có nghĩa lưu mãi tất cả dữ liệu cá nhân**. Nguyên tắc minimization, retention, masking và phân quyền vẫn cần được áp dụng. Với dữ liệu nhạy cảm, chỉ lưu những trường cần cho mục tiêu nghiệp vụ/audit đã được cho phép.

### 2.3. Tại sao không thay thế payload gốc bằng response lookup?

Giả sử Customer Profile Service trả:

~~~json
{
  "customerId": "C-007",
  "tier": "GOLD",
  "verified": true
}
~~~

Nếu Transformer hoặc handler viết `return customerProfile` mà không mang theo thông tin order, endpoint tiếp theo chỉ nhận `CustomerProfile`; `orderId` và `amountVnd` không còn trong payload. Có thể một số header vẫn tồn tại, nhưng header không được dùng như nơi ngầm chứa mọi dữ liệu nghiệp vụ đã bị mất.

Thay vì thế, tạo một envelope:

~~~text
EnrichedOrder
  original: OrderRequest
  profile: CustomerProfile
  metadata: LookupMetadata
~~~

Mỗi trường có một trách nhiệm. Một Router có thể đọc `profile.tier`, Handler thanh toán có thể đọc `original.amountVnd`, còn tracing/audit có thể sử dụng `metadata.source` và `retrievedAt`.

## 3. Ba cách kết hợp dữ liệu và đánh đổi

### 3.1. Sửa object gốc tại chỗ

~~~java
// Ví dụ minh họa nguy cơ, không phải cách khuyến nghị.
class MutableOrder {
    String orderId;
    String customerId;
    String tier;
}

void enrichInPlace(MutableOrder order, String tier) {
    order.tier = tier;
}
~~~

Ưu điểm là ít tạo object mới. Nhưng khi nhiều subscriber cùng giữ reference đến `order`, việc cập nhật `tier` có thể làm thay đổi dữ liệu mà một nhánh khác đang đọc. Qua `ExecutorChannel` hoặc Publish–Subscribe, shared mutable state có thể gây race condition, khó test và khó audit.

Nếu phải dùng mutable bean vì thư viện/adapter, cần xác định rõ ownership và clone/copy semantics; không giả định một Content Enricher tự tạo **deep copy** của toàn object graph.

### 3.2. Tạo DTO mới, làm phẳng tất cả trường

~~~java
record FlatEnrichedOrder(
        String orderId,
        String customerId,
        java.math.BigDecimal amountVnd,
        String tier,
        boolean verified) {}
~~~

Cách này phù hợp khi consumer cần một projection nhỏ, rõ schema. Nhưng có những rủi ro:

- Không phân biệt trường do caller cung cấp với trường được lookup.
- Khi cùng tên trường xuất hiện ở cả hai nguồn, quy tắc ưu tiên dễ không rõ.
- Nếu bổ sung dữ liệu hoặc thay đổi lookup schema, một DTO phẳng có thể khó thể hiện nguồn gốc.
- Nếu muốn kiểm tra payload gốc byte-for-byte, object mới chưa chắc đủ bằng chứng về serialization ban đầu.

### 3.3. Bao original và enrichment riêng biệt

~~~java
record EnrichedOrder(
        OrderRequest original,
        CustomerProfile profile,
        LookupMetadata metadata) {}
~~~

**Đây là cách chính của bài học**: original không bị thay, dữ liệu enrich có namespace riêng, metadata đủ để truy nguyên. Có thể thêm projection được tính sau đó thay vì sửa dữ liệu đầu vào.

| Tiêu chí | Mutate in-place | Flat DTO mới | Wrapper giữ original |
|---|---|---|---|
| Không sửa input object | Không | Có | Có |
| Giữ phân biệt nguồn dữ liệu | Khó | Cần quy ước tên | Rõ ràng |
| Dễ truy nguyên dữ liệu ban đầu | Thấp | Trung bình | Cao |
| Phù hợp xử lý song song | Có rủi ro | Tốt nếu immutable | Tốt nếu các thành phần immutable |
| Payload nhỏ gọn | Thường có | Có | Có thể lớn hơn |
| Schema downstream đơn giản | Trung bình | Dễ với use case nhỏ | Cần consumer biết wrapper |

Không phải mọi flow đều cần wrapper. Nếu chỉ cần tính một field nhỏ và không có yêu cầu giữ nguyên original, một Transformer đơn giản có thể đủ. Nhưng khi **giữ cả payload gốc và dữ liệu đã enrich** là hợp đồng bắt buộc, wrapper giúp ý nghĩa và test rõ ràng nhất.

## 4. Thiết kế dữ liệu bất biến và provenance

### 4.1. Domain model

Mô hình Java 17 có thể viết bằng `record`. Tất cả các trường dưới đây dùng `String`, `BigDecimal`, `boolean`, `Instant` hoặc record khác để minh họa tính bất biến theo giá trị:

~~~java
import java.math.BigDecimal;
import java.time.Instant;

record OrderRequest(
        String orderId,
        String customerId,
        BigDecimal amountVnd) {}

record CustomerProfile(
        String customerId,
        String tier,
        boolean verified) {}

record LookupMetadata(
        String source,
        String lookupRequestId,
        Instant retrievedAt) {}

record EnrichedOrder(
        OrderRequest original,
        CustomerProfile profile,
        LookupMetadata metadata) {}
~~~

**Cần hiểu đúng `record`:** nó giúp cố định reference của component, nhưng **không biến mọi object lồng bên trong thành immutable**. Nếu payload chứa `List`, `Map`, array hoặc một mutable POJO, constructor phải **defensive copy** hoặc dùng một kiểu immutable đã được xác minh.

Ví dụ cho collection:

~~~java
import java.util.List;

record OrderWithItems(String orderId, List<String> itemIds) {
    OrderWithItems {
        itemIds = List.copyOf(itemIds);
    }
}
~~~

`List.copyOf` là **shallow copy**: nếu phần tử là object mutable, vẫn cần xử lý sâu hơn. Không nhầm immutable wrapper với việc clone toàn bộ payload như một snapshot vật lý.

### 4.2. Bất biến nghiệp vụ quan trọng

Một `EnrichedOrder` hợp lệ cho ví dụ này phải thỏa:

1. `original.orderId` và `original.customerId` có giá trị.
2. `original.amountVnd` dương, đã chuẩn hóa về VND.
3. `profile.customerId` **khớp** `original.customerId`.
4. `profile.tier` thuộc tập được chấp nhận, ví dụ `STANDARD`, `SILVER`, `GOLD`.
5. `metadata.source` cho biết nguồn tra cứu thực tế.
6. `metadata.retrievedAt` do component enrichment ghi khi lấy/cấp kết quả.
7. Original object không bị mutate trong lúc enrichment.
8. Không đưa dữ liệu chưa xác minh vào trường khiến Router hiểu nhầm là đã xác minh.

**Trường hợp lookup trả profile của customer khác phải được coi là lỗi**, không tự trộn profile và order chỉ vì hai payload đều có dữ liệu.

### 4.3. Nhận biết dữ liệu từ nguồn nào

| Trường | Nguồn | Có được coi là luôn đúng? |
|---|---|---|
| `original.amountVnd` | Checkout / upstream producer | Phải được validate/authorize theo contract. |
| `profile.tier` | Customer Profile Service | Phụ thuộc thời điểm lookup và độ tin cậy của nguồn. |
| `metadata.retrievedAt` | Enricher | Chỉ chứng minh thời điểm ứng dụng quan sát kết quả; không tự chứng minh dữ liệu mới nhất. |
| `metadata.lookupRequestId` | Enricher hoặc lookup client | Dùng correlation, không thay thế business ID. |
| `headers.traceId` | Observability context | Phải được propagate đúng qua executor/adapter. |

Nếu lookup service trả thêm một `updatedAt` của hồ sơ, ta có thể lưu cả **sourceUpdatedAt** và **retrievedAt** để phân biệt lúc hồ sơ cập nhật với lúc hệ thống tra cứu. Không tự lấy `Instant.now()` rồi tuyên bố đó là thời gian hồ sơ được cập nhật.

## 5. Một Content Enricher có thể kiểm thử bằng Java

### 5.1. Tách lookup khỏi logic kết hợp payload

Content Enricher không nên trộn HTTP client, validation, mapping và routing vào một hàm dài. Trước tiên tạo **hợp đồng nguồn tra cứu**; test có thể dùng implementation in-memory, còn production dùng một client có timeout, security và tracing phù hợp.

~~~java
import java.util.Map;
import java.util.Optional;

interface CustomerProfileDirectory {
    Optional<CustomerProfile> findByCustomerId(String customerId);
}

final class InMemoryCustomerProfileDirectory
        implements CustomerProfileDirectory {

    private final Map<String, CustomerProfile> profiles = Map.of(
            "C-007", new CustomerProfile("C-007", "GOLD", true),
            "C-008", new CustomerProfile("C-008", "STANDARD", false));

    @Override
    public Optional<CustomerProfile> findByCustomerId(String customerId) {
        return Optional.ofNullable(profiles.get(customerId));
    }
}
~~~

`Optional.empty()` trong ví dụ chỉ biểu thị **không tìm được hồ sơ**. Nó khác hẳn HTTP timeout hoặc dịch vụ hồ sơ không truy cập được; hai tình huống này cần được phân loại lỗi khác nhau.

### 5.2. Enrichment service: không sửa `OrderRequest`

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Set;

final class ProfileNotFoundException extends RuntimeException {
    ProfileNotFoundException(String customerId) {
        super("PROFILE_NOT_FOUND: " + customerId);
    }
}

final class ProfileMismatchException extends RuntimeException {
    ProfileMismatchException() {
        super("PROFILE_CUSTOMER_ID_MISMATCH");
    }
}

final class OrderContentEnrichmentService {
    private static final Set<String> ALLOWED_TIERS =
            Set.of("STANDARD", "SILVER", "GOLD");

    private final CustomerProfileDirectory directory;
    private final Clock clock;

    OrderContentEnrichmentService(
            CustomerProfileDirectory directory, Clock clock) {
        this.directory = directory;
        this.clock = clock;
    }

    EnrichedOrder enrich(OrderRequest original) {
        validateOriginal(original);

        CustomerProfile profile = directory
                .findByCustomerId(original.customerId())
                .orElseThrow(() ->
                        new ProfileNotFoundException(
                                original.customerId()));

        if (!original.customerId().equals(profile.customerId())) {
            throw new ProfileMismatchException();
        }
        if (!ALLOWED_TIERS.contains(profile.tier())) {
            throw new IllegalArgumentException(
                    "INVALID_ENRICHED_CUSTOMER_TIER");
        }

        LookupMetadata metadata = new LookupMetadata(
                "customer-profile-directory",
                "lookup-" + original.orderId(),
                Instant.now(clock));

        // Original và dữ liệu mới nằm trong hai trường riêng.
        return new EnrichedOrder(original, profile, metadata);
    }

    private static void validateOriginal(OrderRequest order) {
        if (order == null
                || order.orderId() == null
                || order.orderId().isBlank()
                || order.customerId() == null
                || order.customerId().isBlank()
                || order.amountVnd() == null
                || order.amountVnd().signum() <= 0) {
            throw new IllegalArgumentException(
                    "MALFORMED_ORIGINAL_ORDER");
        }
    }
}
~~~

**Đọc code theo thứ tự:**

1. Kiểm tra original trước khi gọi nguồn bổ sung. Malformed request không nên tạo một network request vô ích.
2. Dùng `customerId` của order làm lookup key và nhận `CustomerProfile`.
3. Xác minh profile trả về khớp chính customer đó, không trộn dữ liệu từ một record khác.
4. Từ chối `tier` ngoài tập cho phép, tránh gửi một giá trị tùy ý cho Router phía sau.
5. Sinh `LookupMetadata` để biết dữ liệu đã được lấy từ nguồn nào và thời điểm nào.
6. Trả một **object mới** bao gồm `original` và `profile`; không có lệnh `setAmount` hoặc `setTier` nào sửa object ban đầu.

`lookupRequestId = "lookup-" + orderId` chỉ là **mã minh họa để dễ đọc test**. Trong hệ thống có nhiều lần tra cứu đồng thời cho cùng một đơn, cần một correlation/attempt ID thực sự đủ phân biệt; đồng thời một idempotency key có thể có semantics khác. Không dùng chuỗi minh họa này làm khóa duy nhất của mọi yêu cầu ở production.

**Giới hạn của ví dụ:** lookup chạy trong bộ nhớ, không mô phỏng timeout hay cache; `Instant.now(clock)` là thời điểm ứng dụng tạo kết quả enrich. Production cần xác định provenance, source version và thời điểm dữ liệu thực tế có hiệu lực.

### 5.3. Ví dụ gọi Java trực tiếp

~~~java
import java.math.BigDecimal;
import java.time.Clock;

OrderContentEnrichmentService enricher =
        new OrderContentEnrichmentService(
                new InMemoryCustomerProfileDirectory(),
                Clock.systemUTC());

OrderRequest request = new OrderRequest(
        "ORD-1001", "C-007", new BigDecimal("9000000"));

EnrichedOrder enriched = enricher.enrich(request);

// Payload gốc vẫn truy xuất được:
// enriched.original().orderId() == "ORD-1001"
// enriched.original().amountVnd() == 9000000

// Kết quả lookup được giữ riêng:
// enriched.profile().tier() == "GOLD"
// enriched.profile().verified() == true
~~~

Kiểu trả về `EnrichedOrder` giúp caller **không nhầm** giữa request gốc và response từ hệ thống hồ sơ. Không cần bỏ orderId/amount vào những message headers tùy biến chỉ để “giữ lại” dữ liệu nghiệp vụ.

## 6. Tích hợp bằng Spring Integration Java DSL

### 6.1. Vị trí của Content Enricher trong flow

Ví dụ dùng **Java 17+, Spring Boot 3.x và Spring Integration 6.x**, cùng dependency `spring-boot-starter-integration`. Trong Spring Integration có thành phần Content Enricher chuyên dụng; ở đây ta triển khai **cùng pattern với một service enrichment và Transformer endpoint** để thể hiện rõ wrapper bất biến. Cách này không giả định bean Java mutable hay sửa property tại chỗ.

~~~mermaid
flowchart LR
    G[MessagingGateway] --> I[(orders.enrich.input)]
    I --> T["Transformer: OrderContentEnrichmentService"]
    T --> R["Message<EnrichedOrder>"]
    R --> RP[Gateway reply]
~~~

### 6.2. Cấu hình có Gateway trả `EnrichedOrder`

~~~java
import java.time.Clock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@MessagingGateway
interface OrderEnrichmentGateway {
    @Gateway(requestChannel = "orders.enrich.input")
    EnrichedOrder enrich(OrderRequest request);
}

@Configuration
@EnableIntegration
@IntegrationComponentScan
class OrderEnrichmentFlowConfiguration {

    @Bean(name = "orders.enrich.input")
    MessageChannel input() {
        return new DirectChannel();
    }

    @Bean
    Clock enrichmentClock() {
        return Clock.systemUTC();
    }

    @Bean
    CustomerProfileDirectory profileDirectory() {
        return new InMemoryCustomerProfileDirectory();
    }

    @Bean
    OrderContentEnrichmentService orderContentEnrichmentService(
            CustomerProfileDirectory directory,
            Clock enrichmentClock) {
        return new OrderContentEnrichmentService(
                directory, enrichmentClock);
    }

    @Bean
    IntegrationFlow enrichOrderFlow(
            OrderContentEnrichmentService service) {
        return IntegrationFlow.from("orders.enrich.input")
                .transform(OrderRequest.class, service::enrich)
                .get();
    }
}
~~~

**Vì sao vẫn gọi là Content Enricher khi code dùng `transform`?** EIP mô tả **ý nghĩa thao tác**, không bắt buộc mọi triển khai phải dùng cùng một tên class. `OrderContentEnrichmentService` bổ sung thông tin từ `CustomerProfileDirectory` và giữ original trong wrapper; `.transform(...)` là endpoint thực thi việc tạo payload mới. Khi cần enrichment kiểu property/header của framework, có thể dùng Content Enricher/`.enrich(...)` chuyên dụng; không nên tuyên bố hai cơ chế có cùng chi tiết mutation, request/reply hay header propagation trong mọi cấu hình.

Ở ví dụ:

- `DirectChannel` giúp luồng xử lý đồng bộ.
- `@MessagingGateway` tạo message từ tham số và chờ một kết quả `EnrichedOrder`.
- Transformer làm enrichment và trả payload mới, rồi kết quả theo reply path của Gateway khi không có output channel cố định cho một bước tiếp theo.
- Mỗi lookup chỉ mang dữ liệu từ in-memory directory. Không có cơ sở dữ liệu hoặc HTTP thật trong demo.
- Trong một ứng dụng thực tế, tách các type cần `public` thành file Java riêng; các record/class minh họa cùng package để dễ theo dõi bài.

### 6.3. Gọi Gateway và so sánh trước/sau

~~~java
OrderRequest input = new OrderRequest(
        "ORD-1001", "C-007", new java.math.BigDecimal("9000000"));

EnrichedOrder result = orderEnrichmentGateway.enrich(input);

assert result.original().equals(input);
assert "C-007".equals(result.profile().customerId());
assert "GOLD".equals(result.profile().tier());
assert "customer-profile-directory".equals(
        result.metadata().source());
~~~

Đoạn trên dùng Java `assert` để minh họa; trong unit/integration test nên dùng JUnit 5 `assertEquals`, `assertSame`, `assertNotNull` thay vì phụ thuộc tùy chọn JVM `-ea`.

### 6.4. Khi cần một channel sau enrichment

Nếu không cần Gateway trả enriched payload ngay, có thể cho message đi tiếp tới Filter hoặc Router:

~~~text
orders.enrich.input
  -> Content Enricher / Transformer
  -> orders.enriched
  -> Router(profile.tier / profile.verified)
  -> Handler / external gateway
~~~

Trong flow có message tiếp tục qua nhiều endpoint, cần kiểm soát **trạng thái hoàn tất cuối cùng**. `EnrichedOrder` đã được tạo không có nghĩa endpoint thanh toán hoặc lưu đơn sau Router đã thành công.

## 7. Content Enricher chuyên dụng so với Transformer

### 7.1. Khi nào dùng `ContentEnricher`?

Spring Integration cung cấp một thành phần **Content Enricher** để làm giàu message dựa trên dữ liệu trả về từ request channel hoặc expression, chẳng hạn gọi service lookup rồi cập nhật các property/header đã cấu hình. Khi chọn cơ chế này, cần kiểm tra kỹ:

- **Request channel:** gửi yêu cầu lookup tới đâu?
- **Request payload:** truyền cả order hay chỉ `customerId`?
- **Reply payload:** response là `CustomerProfile`, wrapper hay kiểu khác?
- **Property/header mapping:** dữ liệu trả về được đưa vào trường nào?
- **Original payload handling:** framework/bean xử lý theo kiểu mutate/copy/transform nào?
- **Timeout/error flow:** nếu lookup không trả reply, phải chờ bao lâu và xử lý gì?

Một sơ đồ cấu hình khái niệm:

~~~text
ContentEnricher
  requestChannel     = customer.profile.lookup
  requestPayload     = original.customerId
  lookup reply       = CustomerProfile
  target             = enriched.profile
  original           = giữ trong enriched.original
  on missing/timeout = error hoặc fallback có kiểm soát
~~~

Đây là **đặc tả hành vi**, không phải cú pháp DSL có thể copy nguyên vào Java. Khi dùng `.enrich(...)`, phải dựa trên API của phiên bản Spring Integration được chọn và test cụ thể chuyện property mapping với POJO mutable/record. **Không mặc định** một Content Enricher sẽ tự deep-clone original hoặc tạo wrapper theo schema ứng dụng.

### 7.2. Khi nào Transformer tạo wrapper thuận lợi hơn?

Nếu yêu cầu bắt buộc là **payload gốc còn nguyên, dữ liệu enrich tách namespace**, một Transformer trả `new EnrichedOrder(original, profile, metadata)` có nhiều lợi thế:

1. Hợp đồng kết quả được Java type system biểu diễn rõ.
2. Không cần setter trên original.
3. Có thể test `assertSame(original, result.original())` khi original là immutable.
4. Dễ bắt lỗi profile mismatch trước khi tạo enriched object.
5. Có thể thêm metadata provenance mà không làm thay đổi schema original.

Đổi lại, service viết tay chịu trách nhiệm lookup, timeouts, mapping và validation; **đừng bỏ qua những chức năng framework có thể hỗ trợ** nếu đang dùng native Content Enricher. Chọn theo mức độ rõ của hợp đồng, chứ không chỉ theo ít dòng code.

### 7.3. Enrich header khác enrich payload

Spring Integration cũng hỗ trợ **Header Enricher**, dùng khi cần bổ sung metadata điều phối/quan sát, ví dụ một `routeGroup` hoặc correlation header đã được kiểm soát.

~~~text
Payload:
  original order + enriched customer profile

Headers:
  traceId, correlationId, routeVersion, replyChannel
~~~

Đừng đưa cả `CustomerProfile` vào headers rồi yêu cầu mọi consumer đọc `headers.customerProfile` nếu nó thật sự là dữ liệu nghiệp vụ của kết quả. Headers có thể bị lọc hoặc đổi khi qua HTTP/Kafka/JMS/AMQP; một số header còn chứa object nội bộ không serialize được. Chọn payload hoặc header theo **ý nghĩa, security và contract transport**, không chỉ vì thao tác đọc thuận tiện.

## 8. Kiểm thử payload gốc không bị mất hoặc thay đổi

### 8.1. Những invariant quan trọng nhất

Với yêu cầu “giữ payload gốc và dữ liệu đã enrich”, test cần **khẳng định cả hai chiều**:

1. **Original invariant:** dữ liệu input giữ nguyên sau enrich; các trường `orderId`, `customerId` và `amountVnd` không thay đổi.
2. **Enrichment invariant:** dữ liệu lookup đúng customer, đúng tier/verified, có provenance hợp lệ.
3. **Separation invariant:** sửa/đổi kết quả lookup (ở các lần thực hiện khác nhau) không được làm original bị thay đổi.
4. **Failure invariant:** khi lookup lỗi, không công bố một `EnrichedOrder` có profile sai hoặc giả.
5. **Downstream invariant:** Router/Handler có thể truy cập **cả original và profile** trong cùng một payload đã enrich.

Không chỉ test `result.profile() != null`. Nó có thể chứa profile **sai khách hàng**, sai nguồn, sai schema hoặc chưa xác minh.

### 8.2. JUnit 5 kiểm tra success case

~~~java
import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertTrue;

class OrderContentEnrichmentServiceTest {
    private static final Instant FIXED_TIME =
            Instant.parse("2026-01-01T00:00:00Z");

    private final OrderContentEnrichmentService service =
            new OrderContentEnrichmentService(
                    new InMemoryCustomerProfileDirectory(),
                    Clock.fixed(FIXED_TIME, ZoneOffset.UTC));

    @Test
    void keepsOriginalAndAddsProfileAndMetadata() {
        OrderRequest original = new OrderRequest(
                "ORD-1", "C-007", new BigDecimal("9000000"));

        EnrichedOrder result = service.enrich(original);

        assertSame(original, result.original());
        assertEquals("ORD-1", result.original().orderId());
        assertEquals("C-007", result.original().customerId());
        assertEquals(new BigDecimal("9000000"),
                result.original().amountVnd());

        assertNotNull(result.profile());
        assertEquals("C-007", result.profile().customerId());
        assertEquals("GOLD", result.profile().tier());
        assertTrue(result.profile().verified());

        assertEquals("customer-profile-directory",
                result.metadata().source());
        assertEquals(FIXED_TIME, result.metadata().retrievedAt());
    }

    @Test
    void twoDifferentOrdersDoNotSwapOriginalInformation() {
        OrderRequest first = new OrderRequest(
                "ORD-A", "C-007", new BigDecimal("5000000"));
        OrderRequest second = new OrderRequest(
                "ORD-B", "C-008", new BigDecimal("800000"));

        EnrichedOrder one = service.enrich(first);
        EnrichedOrder two = service.enrich(second);

        assertSame(first, one.original());
        assertSame(second, two.original());
        assertEquals("GOLD", one.profile().tier());
        assertEquals("STANDARD", two.profile().tier());
    }
}
~~~

**Vì sao dùng `Clock.fixed`?** Nếu dùng `Instant.now()` trực tiếp rồi assert một timestamp cố định, test sẽ phụ thuộc thời gian thực. Inject `Clock` cho phép kiểm tra chính xác việc metadata được tạo mà không cần `Thread.sleep`.

`assertSame(original, result.original())` là assertion mạnh cho implementation **đang giữ reference original**. Nếu production chọn **deep copy có kiểm soát** để ngăn shared mutable state, test nên dùng `assertEquals` với dữ liệu/serialized representation đã chuẩn hóa, không bắt buộc identity reference. Bất biến thực sự là **không mất và không sửa dữ liệu gốc theo contract**, không phải luôn giữ cùng object identity.

### 8.3. Negative tests: không ghép nhầm profile

~~~java
import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Optional;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class OrderContentEnrichmentFailureTest {
    private static final Clock FIXED_CLOCK = Clock.fixed(
            Instant.parse("2026-01-01T00:00:00Z"), ZoneOffset.UTC);

    @Test
    void missingProfileIsNotSilentlyReplacedByFakeProfile() {
        CustomerProfileDirectory empty =
                customerId -> Optional.empty();
        OrderContentEnrichmentService service =
                new OrderContentEnrichmentService(
                        empty, FIXED_CLOCK);

        ProfileNotFoundException error = assertThrows(
                ProfileNotFoundException.class,
                () -> service.enrich(new OrderRequest(
                        "ORD-2", "C-404", new BigDecimal("2000000"))));

        assertEquals("PROFILE_NOT_FOUND: C-404",
                error.getMessage());
    }

    @Test
    void profileForAnotherCustomerIsRejected() {
        CustomerProfileDirectory wrongDirectory =
                id -> Optional.of(
                        new CustomerProfile("OTHER", "GOLD", true));
        OrderContentEnrichmentService service =
                new OrderContentEnrichmentService(
                        wrongDirectory, FIXED_CLOCK);

        assertThrows(ProfileMismatchException.class, () ->
                service.enrich(new OrderRequest(
                        "ORD-3", "C-007", new BigDecimal("2000000"))));
    }

    @Test
    void unsupportedTierIsRejectedBeforeBuildingWrapper() {
        CustomerProfileDirectory invalidTier =
                id -> Optional.of(new CustomerProfile(
                        id, "ADMIN", true));
        OrderContentEnrichmentService service =
                new OrderContentEnrichmentService(
                        invalidTier, FIXED_CLOCK);

        assertThrows(IllegalArgumentException.class, () ->
                service.enrich(new OrderRequest(
                        "ORD-4", "C-007", new BigDecimal("2000000"))));
    }

    @Test
    void invalidOriginalFailsBeforeLookup() {
        CustomerProfileDirectory notCalled = customerId -> {
            throw new AssertionError(
                    "Lookup must not be called for malformed input");
        };
        OrderContentEnrichmentService service =
                new OrderContentEnrichmentService(
                        notCalled, FIXED_CLOCK);

        assertThrows(IllegalArgumentException.class, () ->
                service.enrich(new OrderRequest(
                        "ORD-5", "C-007", BigDecimal.ZERO)));
    }
}
~~~

Những test này có giá trị cao vì chúng bảo vệ **ngữ nghĩa của enrichment**: không sửa dữ liệu gốc để “chữa” một lookup sai, không lấy profile của người khác, và không ngầm tạo giá trị `GOLD` khi dịch vụ tra cứu trả thiếu dữ liệu.

### 8.4. Test dữ liệu gốc có collection

Nếu original chứa `List<Item>`, cần kiểm thử:

- Caller thay `List` nguồn sau khi tạo payload thì bản snapshot ban đầu có đổi không?
- Item mutable có thể bị một subscriber khác sửa không?
- Serialization sang JSON rồi deserialization có giữ đầy đủ các item ban đầu không?
- Nếu cần audit byte-level, có lưu **raw inbound envelope** ở biên được cho phép, hay chỉ lưu DTO sau khi parse?

**Giữ original DTO** không tự bảo đảm giữ lại mọi byte/field của request wire. Converter có thể bỏ unknown field, chuẩn hóa Unicode, timezone hoặc số. Nếu nghiệp vụ yêu cầu bằng chứng chính xác bản nhận ở biên, phải định nghĩa một **raw-event retention mechanism** riêng, kèm bảo vệ dữ liệu nhạy cảm và lifecycle lưu trữ.

## 9. Integration test Spring Integration: Gateway nhận đủ hai phần dữ liệu

### 9.1. Kiểm thử đúng pipeline, không chỉ service

Từ `OrderEnrichmentFlowConfiguration` ở mục 6, dùng Spring Test/JUnit 5:

~~~java
import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringJUnitConfig(OrderEnrichmentFlowConfiguration.class)
class OrderEnrichmentFlowIntegrationTest {

    @Autowired
    private OrderEnrichmentGateway gateway;

    @Test
    void gatewayReturnsOriginalAndEnrichmentTogether() {
        OrderRequest request = new OrderRequest(
                "ORD-900", "C-007", new BigDecimal("9000000"));

        EnrichedOrder result = gateway.enrich(request);

        assertEquals(request, result.original());
        assertEquals("C-007", result.profile().customerId());
        assertEquals("GOLD", result.profile().tier());
        assertNotNull(result.metadata());
        assertNotNull(result.metadata().retrievedAt());
    }

    @Test
    void aSecondCustomerHasItsOwnProfile() {
        OrderRequest request = new OrderRequest(
                "ORD-901", "C-008", new BigDecimal("500000"));

        EnrichedOrder result = gateway.enrich(request);

        assertEquals(request, result.original());
        assertEquals("STANDARD", result.profile().tier());
        assertEquals(false, result.profile().verified());
    }
}
~~~

Test trên đi qua **Messaging Gateway → DirectChannel → Transformer → Gateway reply**, không chỉ gọi Java service trực tiếp. Nếu muốn chứng minh một **channel downstream** nhận đúng `EnrichedOrder`, hãy thêm channel/handler hoặc interceptor test ở sau Transformer và xác minh original/profile cùng hiện diện.

### 9.2. Vì sao không dùng một “reply payload = CustomerProfile”?

Gateway của bài trả `EnrichedOrder`, thay vì trả riêng `CustomerProfile`. Nhờ đó caller có thể dùng cả dữ liệu gốc và dữ liệu bổ sung. Nếu cần một reply nhỏ như `EnrichmentReceipt`, nên tạo **projection riêng** tại boundary:

~~~java
record EnrichmentReceipt(
        String orderId,
        String customerTier,
        boolean verified) {}

EnrichmentReceipt toReceipt(EnrichedOrder result) {
    return new EnrichmentReceipt(
            result.original().orderId(),
            result.profile().tier(),
            result.profile().verified());
}
~~~

Việc tạo projection không làm thay đổi đối tượng `EnrichedOrder` trong bước xử lý nội bộ. Tuy nhiên, **nếu chỉ trả receipt cho bên ngoài** thì bên ngoài không thể truy cập original đầy đủ qua reply đó; đây là một quyết định hợp đồng, không phải mất dữ liệu do Enricher.

### 9.3. Test Gateway khi lookup không có hồ sơ

~~~java
import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringJUnitConfig(OrderEnrichmentFlowConfiguration.class)
class OrderEnrichmentGatewayErrorTest {
    @Autowired
    private OrderEnrichmentGateway gateway;

    @Test
    void unknownCustomerDoesNotReturnFakeEnrichedOrder() {
        assertThrows(RuntimeException.class, () ->
                gateway.enrich(new OrderRequest(
                        "ORD-404", "C-404", new BigDecimal("500000"))));
    }
}
~~~

Trong một endpoint Spring Integration, exception nghiệp vụ có thể bị framework bọc trong `MessageHandlingException` hoặc loại exception messaging khác. **Đừng ràng buộc test vào một wrapper cụ thể** nếu contract của phiên bản đang dùng không yêu cầu; ở hệ thống thật nên xác minh cause chain/mã lỗi và không có reply “success” giả. Một test mở rộng có thể kiểm tra mã `PROFILE_NOT_FOUND`, nhưng tránh phụ thuộc vào message của thư viện có thể đổi giữa các phiên bản.

## 10. Khi lookup thất bại: không thể “enrich đại” để đi tiếp

### 10.1. Phân biệt không có dữ liệu và hạ tầng thất bại

| Tình huống | Bản chất | Hướng xử lý |
|---|---|---|
| Không tìm thấy `customerId` | Kết quả domain `NOT_FOUND`. | Business rejection/hold theo contract; không tự tạo GOLD/verified. |
| Response trả customerId khác | Sai liên kết hoặc lỗi dữ liệu. | Fail closed, ghi lỗi bảo mật/dữ liệu, không ghép nhầm. |
| Profile thiếu trường bắt buộc | Schema/validation error. | Từ chối hoặc quarantine; sửa upstream/schema. |
| Dịch vụ lookup timeout | Có thể là lỗi hạ tầng tạm thời. | Retry có giới hạn, backoff, deadline, idempotency. |
| Cache trả dữ liệu quá cũ | Freshness violation. | Refresh/hold theo mức quan trọng, không ngụy trang là mới. |
| Lookup thành công nhưng downstream lỗi | Enrichment xong, xử lý tiếp thất bại. | Error/recovery ở endpoint downstream, không tính là lỗi lookup. |
| Customer profile bị thu hồi quyền/verified | Dữ liệu thay đổi theo thời gian. | Quyết định validity window và source-of-truth phù hợp. |

Nếu downstream dùng `verified` để cho phép xuất hàng, việc lookup timeout **không được tự hiểu thành verified=true**. Một giá trị “không biết” phải được biểu diễn rõ, hoặc flow phải thất bại/hold theo quy định.

### 10.2. Khi nào dùng fallback?

Một số tác vụ **không quan trọng**, như chỉ hiển thị tên khách hàng trong email, có thể dùng một fallback dạng `displayName="Khách hàng"`. Nhưng với dữ liệu ảnh hưởng tới **quyền truy cập, chống gian lận, hạn mức, thuế hoặc thanh toán**, fallback sai có thể gây hại.

Nếu dùng fallback, kết quả không nên giả làm lookup thành công:

~~~text
EnrichmentResult:
  original: ...
  profile:
    ... các trường được phép sử dụng fallback
  metadata:
    enrichmentStatus: FALLBACK
    source: local-cache
    sourceUpdatedAt: ...
    retrievedAt: ...
~~~

Flow ví dụ chính hiện **chưa có `enrichmentStatus`**. Đó là schema mở rộng nếu nghiệp vụ thật cần fallback. Không thêm trường và default chỉ vì muốn mọi message luôn nhận được reply.

### 10.3. Bắt lỗi ở đúng tầng

Đường xử lý được khuyến nghị:

~~~mermaid
flowchart TD
    I[Original OrderRequest] --> V{Validate original}
    V -->|Malformed| E1[Input validation error]
    V -->|Valid| L[Lookup profile]
    L -->|Not found| E2[Business hold / reject]
    L -->|Timeout| E3[Retry / recovery]
    L -->|Response| C{Validate customerId + schema}
    C -->|Mismatch| E4[Data integrity failure]
    C -->|OK| W[Create EnrichedOrder wrapper]
    W --> N[Downstream processing]
    N -->|Error| E5[Downstream error flow]
~~~

Tách các lỗi này giúp unit test và metrics không trộn `malformed_original` với `lookup_timeout` hoặc `downstream_failed`. Nếu tất cả đều bị bắt rồi trả `new CustomerProfile("unknown", "GOLD", true)`, hệ thống có thể chạy tiếp nhưng mang dữ liệu giả và mất khả năng truy nguyên.

### 10.4. Chỗ đặt retry

Nếu lookup nằm trong một flow đồng bộ, có thể đặt retry quanh **bước gọi lookup**; không nhất thiết retry toàn bộ pipeline từ đầu. Một retry toàn flow có thể làm các bước trước đó (audit, ghi DB hoặc outbound request) chạy lại.

Với `DirectChannel`, exception từ lookup thường có thể truyền lên call stack. Với `ExecutorChannel`, `QueueChannel`/poller hoặc broker, failure có thể xảy ra sau khi producer đã tiếp nhận message; cần thiết kế `errorChannel`, `ErrorMessage` hoặc error handler theo từng adapter/poller.

Không giả định mọi lỗi async đều tự đi vào một error channel chung hoặc được retry an toàn. Cần xác định **delivery semantics, ack, redelivery, retry scope, dead-letter/quarantine, timeout và giới hạn số lần thử**.

## 11. Giữ correlation và ngữ cảnh của message

### 11.1. Original payload không thay thế MessageHeaders

Khi dùng wrapper `EnrichedOrder`, original nghiệp vụ được giữ **trong payload mới**. Nhưng message còn có **headers** của Spring Integration:

| Metadata | Dùng cho | Khi qua Enricher cần lưu ý |
|---|---|---|
| `MessageHeaders.ID` | Nhận diện một Spring message cụ thể. | Có thể được sinh lại khi endpoint tạo message mới. |
| `timestamp` | Thời điểm message được tạo theo framework. | Không nhất thiết trùng thời điểm lookup. |
| `traceId` / trace context | Truy nguyên xuyên thread/service. | Cần propagation theo instrumentation/adapter thực tế. |
| `correlationId` | Gom các message hoặc kết quả của cùng một công việc. | Đặc biệt quan trọng với Splitter/Aggregator. |
| `sequenceNumber` / `sequenceSize` | Thứ tự và số phần trong một nhóm. | Không sửa tùy tiện khi enrich một message con. |
| `replyChannel` | Đường trả lời nội bộ của Gateway. | Có thể là object JVM; không serialize nguyên sang HTTP/broker khác. |
| `errorChannel` | Ngữ cảnh lỗi của message. | Không tự bảo đảm mọi failure sẽ có ErrorMessage. |

**Giữ payload gốc là một yêu cầu khác với giữ headers.** Không dùng một assertion `result.original().equals(request)` để suy ra trace/correlation đã được bảo toàn xuyên adapter.

### 11.2. Correlation cho lookup request–reply

Giả sử hai đơn khác nhau cùng có `customerId=C-007`:

~~~text
Order A: orderId=ORD-11, customerId=C-007
Order B: orderId=ORD-12, customerId=C-007
~~~

Cả hai request lookup có thể trả cùng một customer profile, nhưng mỗi kết quả phải quay đúng **original order tương ứng**. Nếu chỉ dựa vào `customerId` để ghép request–reply bất đồng bộ, hai request song song rất dễ bị lẫn.

Trong triển khai request–reply qua transport, nên có một định danh **lookupAttemptId / correlation ID** đủ duy nhất cho mỗi request cần ghép, cùng cơ chế timeout và cleanup. Business `orderId` giúp truy nguyên, nhưng không thay thế hoàn toàn attempt ID nếu cùng đơn được lookup nhiều lần song song.

~~~mermaid
sequenceDiagram
    participant A as Order A
    participant B as Order B
    participant E as Enricher
    participant P as Profile Service
    A->>E: Order A (ORD-11)
    B->>E: Order B (ORD-12)
    E->>P: Lookup C-007 / attempt-a
    E->>P: Lookup C-007 / attempt-b
    P-->>E: Profile / attempt-b
    E-->>B: EnrichedOrder(original=B, profile)
    P-->>E: Profile / attempt-a
    E-->>A: EnrichedOrder(original=A, profile)
~~~

Đây là **sơ đồ hợp đồng cần đạt được**, không phải cam kết Spring Integration tự tạo trường `attempt-a`/`attempt-b` cho mọi adapter. Phải dùng cơ chế correlation/reply mapping được transport và component hỗ trợ, hoặc tự quản lý nếu xây dựng workflow bất đồng bộ.

### 11.3. Khi enrichment xảy ra giữa Splitter và Aggregator

Ví dụ một đơn có ba dòng hàng:

~~~mermaid
flowchart LR
    O[Order có 3 items] --> S[Splitter]
    S --> I1[Item 1]
    S --> I2[Item 2]
    S --> I3[Item 3]
    I1 --> E[Enricher lấy product details]
    I2 --> E
    I3 --> E
    E --> A[Aggregator]
    A --> R[EnrichedOrderItems]
~~~

Mỗi item cần giữ cả dữ liệu gốc của item và thông tin product đã được enrich, nhưng **cũng phải giữ correlation/sequence** để Aggregator biết các item thuộc cùng đơn. Nếu một item lookup thất bại và không phát kết quả, group có thể chờ đến timeout. Khi đó cần định nghĩa:

- **Partial failure:** có được trả danh sách hai item đã enrich không?
- **Release policy:** chờ đủ ba, chờ quorum, hay hết deadline?
- **Missing item representation:** item lỗi có được đưa vào một result mang status failure không?
- **Retry:** chỉ retry item lỗi hay lại split/lookup toàn đơn?
- **Duplicate:** message item đến hai lần có làm Aggregator đếm sai `sequenceSize` không?

Một Enricher có thể giữ payload gốc chính xác nhưng flow vẫn lỗi nếu metadata correlation bị mất khi đi qua một adapter. Vì thế unit test wrapper và integration test Splitter/Aggregator phải là **hai lớp kiểm tra khác nhau**.

### 11.4. Message History không bằng provenance

**Message History** của Spring Integration có thể ghi dấu những component đã đi qua khi tracking được bật. Nó **không tự cho biết** dữ liệu `profile.tier` đến từ phiên bản nào của Customer Profile Service, được query lúc nào và có stale hay không. Ngược lại, `LookupMetadata` mô tả provenance của dữ liệu lookup nhưng không tự ghi đủ mọi endpoint trên hành trình.

Muốn truy nguyên một quyết định quan trọng, kết hợp:

1. Business ID và correlation/trace context.
2. Input gốc có nguồn tin cậy.
3. Enrichment source, timestamp, policy version hoặc dữ liệu version khi cần.
4. Route decision/outcome của các bước downstream.
5. Error/retry history có thể đối chiếu bằng stable IDs.

## 12. Freshness, caching và replay

### 12.1. Enrichment result có thể trở nên cũ

Giả sử:

~~~text
10:00 Customer tier = GOLD
10:01 Order ORD-10 được enrich với GOLD
10:05 Customer tier đổi thành STANDARD
10:08 Replay ORD-10
~~~

Khi replay, có hai lựa chọn khác nhau:

| Chính sách | Replay dùng | Khi nào phù hợp |
|---|---|---|
| **Historical reproducibility** | Profile snapshot/provenance đã dùng ở 10:01. | Cần audit, tái hiện quyết định trước đó. |
| **Re-evaluate latest** | Tra cứu profile mới ở 10:08. | Nghiệp vụ cho phép quyết định lại theo trạng thái hiện tại. |

Nếu không nêu rõ policy, cùng một original order có thể được enrich khác nhau mỗi lần retry. Điều này **không nhất thiết là bug**, nhưng bắt buộc phải được hiểu rõ nếu các nhánh sau tính hạn mức, ưu đãi, thuế hoặc quyền truy cập.

### 12.2. Phân biệt cache hit và dữ liệu được xác minh

Cache giảm latency nhưng tăng yêu cầu về freshness:

~~~text
EnrichmentMetadata
  source          = profile-cache
  retrievedAt     = 10:08
  sourceUpdatedAt = 09:30
  cacheHit        = true
  maxAgeSeconds   = 300
~~~

Đây là **schema minh họa mở rộng**, không phải các trường hiện có trong `LookupMetadata` của đoạn Java chính. Một `retrievedAt=10:08` không chứng minh profile mới được cập nhật 10:08.

Với dữ liệu kiểm soát truy cập hoặc thanh toán, cần xác định **TTL, stale-while-revalidate có được phép không, khả năng invalidation, fallback khi nguồn chính không khả dụng** và mức bảo đảm nhất quán. Không dùng cache stale để “xác minh” một trạng thái đã bị thu hồi.

### 12.3. Idempotency khi enrich kèm side effect

Lookup thuần đọc có thể được thực hiện lại, nhưng một enrichment flow đôi khi gọi hệ thống ngoài để **tạo** hồ sơ, cấp mã hoặc ghi transaction. Khi đó retry có thể tạo side effect trùng. Cần một operation/idempotency key và replay policy phù hợp.

Nếu logic đơn thuần là:

~~~text
OrderRequest -> GET CustomerProfile -> EnrichedOrder
~~~

thì enrichment có vẻ không có side effect, nhưng vẫn có thể trả dữ liệu mới theo thời gian. “Idempotent” theo nghĩa **không nhân đôi side effect** không đồng nghĩa “kết quả luôn giống từng byte giữa các lần gọi”. Phải phân biệt hai mục tiêu:

- **Side-effect idempotency:** không tạo lặp thay đổi nghiệp vụ.
- **Deterministic replay:** tái tạo đúng quyết định và dữ liệu tại một thời điểm.

### 12.4. Version hóa schema original và enrichment

Nếu Checkout từ v1 sang v2 thêm `salesChannel`, còn Profile Service đổi `tier` thành `membershipLevel`, một wrapper giúp tách hai schema. Tuy nhiên downstream vẫn phải biết schema của `EnrichedOrder` và cách migrate trường mới.

Một protocol envelope dùng qua HTTP/Kafka có thể bổ sung:

~~~json
{
  "schemaVersion": 2,
  "original": {
    "orderId": "ORD-1001",
    "customerId": "C-007",
    "amountVnd": 9000000
  },
  "profile": {
    "customerId": "C-007",
    "tier": "GOLD",
    "verified": true
  },
  "enrichment": {
    "source": "customer-profile-directory",
    "lookupRequestId": "lookup-ORD-1001",
    "retrievedAt": "2026-01-01T00:00:00Z"
  }
}
~~~

Đây là **ví dụ JSON giao tiếp**, không phải dữ liệu lấy từ hệ thống thật. Nếu cần diễn giải lại message cũ, phải giữ khả năng đọc version cũ và không nhầm timestamp kỹ thuật với thời điểm có hiệu lực nghiệp vụ.

## 13. Kiểm thử khi có Router hoặc Filter sau enrichment

### 13.1. Router phải đọc đúng phần dữ liệu mới

Một Router có thể cần chọn channel dựa trên hạng khách hàng, nhưng handler thanh toán vẫn cần amount gốc:

~~~text
EnrichedOrder
   |
   +-- original.amountVnd = 9000000
   +-- profile.tier = GOLD
   |
   v
Router
   | tier=GOLD  -> priority
   | other      -> standard
~~~

Không đưa `profile.tier` vào `original` chỉ vì Router đọc bằng path ngắn hơn. Một bước Router đơn giản có thể dùng:

~~~java
String routeFor(EnrichedOrder order) {
    return "GOLD".equals(order.profile().tier())
            && order.profile().verified()
            ? "priority" : "standard";
}
~~~

Trong thực tế, chọn route theo `tier` có thể liên quan ưu đãi hoặc phân quyền; phải biết **tier đã được xác minh**, không tin dữ liệu client gửi trong original để giả mạo tier.

### 13.2. Filter sau enrich có thể loại message hợp lệ

Nếu Filter yêu cầu `profile.verified() == true`, một order **được enrich hợp lệ** nhưng có `verified=false` sẽ bị Filter **rejected theo policy**. Đó không phải lỗi lookup hoặc malformed.

~~~text
Order C-008
  -> lookup trả CustomerProfile(C-008, STANDARD, false)
  -> EnrichedOrder hợp lệ
  -> Filter(verified)
  -> rejected / review
~~~

Phải phân biệt:

- **Lookup error:** không tạo được enriched payload đúng hợp đồng.
- **Filter rejection:** enriched payload hợp lệ, nhưng không đạt điều kiện.
- **Router decision:** dựa trên enriched payload để chọn channel.
- **Downstream error:** endpoint sau khi accept message gặp lỗi.

Một test chuyên biệt nên assert rằng `profile.verified=false` **không bị biến thành profile missing**, và message có thể đi vào nhánh review theo chính sách.

### 13.3. Một hàm quyết định có thể kiểm thử độc lập

~~~java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class EnrichedOrderRoutingPolicyTest {
    @Test
    void verifiedGoldGoesToPriorityWithoutChangingOriginal() {
        OrderRequest original = new OrderRequest(
                "ORD-1", "C-007",
                new java.math.BigDecimal("9000000"));
        EnrichedOrder result = new EnrichedOrder(
                original,
                new CustomerProfile("C-007", "GOLD", true),
                new LookupMetadata("test", "lookup-1",
                        java.time.Instant.EPOCH));

        String route = "GOLD".equals(result.profile().tier())
                && result.profile().verified()
                ? "priority" : "standard";

        assertEquals("priority", route);
        assertEquals(original, result.original());
    }
}
~~~

Nếu ứng dụng triển khai thành Router của Spring Integration, integration test phải kiểm tra **channel thực nhận message**, không chỉ assert hàm `routeFor`. Bảng channel mapping, subscriber lifecycle và error handling là những tầng khác cần xác minh.

## 14. Quan sát enrichment mà không làm lộ dữ liệu

### 14.1. Theo dõi các mốc xử lý

Một sự kiện `OrderCreated` có thể đi qua các trạng thái:

~~~text
ORDER_RECEIVED
  -> ENRICHMENT_STARTED
  -> PROFILE_LOOKUP_SENT
  -> PROFILE_LOOKUP_RECEIVED
  -> ENRICHMENT_COMPLETED
  -> ROUTE_DECIDED
  -> BRANCH_COMPLETED
~~~

Nếu tra cứu lỗi:

~~~text
ORDER_RECEIVED
  -> ENRICHMENT_STARTED
  -> PROFILE_LOOKUP_FAILED (timeout)
  -> ENRICHMENT_RETRY_SCHEDULED
  -> ... / ENRICHMENT_RECOVERY
~~~

**Đây là schema sự kiện do ứng dụng đề xuất**, không phải log được Spring Integration tự sinh khi gọi `.transform(...)`. Mỗi event có tên riêng để không nhầm **đã gửi lookup** với **đã nhận profile** hoặc **đã hoàn thành xử lý downstream**.

### 14.2. Structured logs có provenance

Ví dụ:

~~~text
event=ENRICHMENT_STARTED
  orderId=ORD-1001 customerRef=C-007
  traceId=T-1001 lookupAttemptId=L-0001

event=PROFILE_LOOKUP_RECEIVED
  lookupAttemptId=L-0001
  source=customer-profile-directory
  profileMatch=true

event=ENRICHMENT_COMPLETED
  orderId=ORD-1001
  lookupAttemptId=L-0001
  source=customer-profile-directory
  tier=GOLD

event=ROUTE_DECIDED
  orderId=ORD-1001
  route=priority
  reason=VERIFIED_GOLD
~~~

Không log bản sao toàn bộ `OrderRequest` hoặc `CustomerProfile` nếu chúng chứa tên, địa chỉ, email, token hoặc dữ liệu cá nhân. Trong nhiều hệ thống, ngay cả `customerId` cũng có thể là thông tin định danh cần masking/hash hoặc giảm thời gian lưu. Chỉ log các trường được policy cho phép.

### 14.3. Metrics tách thời gian lookup và thời gian downstream

| Metric minh họa | Ý nghĩa |
|---|---|
| `enrichment_requests_total` | Số message bắt đầu làm giàu. |
| `enrichment_completed_total` | Số lần tạo enriched payload hợp lệ. |
| `enrichment_failed_total{reason}` | Phân loại not-found, mismatch, timeout, schema. |
| `profile_lookup_latency_ms` | Độ trễ của nguồn tra cứu. |
| `enrichment_total_latency_ms` | Toàn bộ thời gian validate + lookup + merge. |
| `enrichment_cache_hit_total` | Số lần dùng cache, nếu có. |
| `enrichment_fallback_total` | Số lần fallback theo contract, nếu được phép. |
| `enrichment_stale_result_total` | Số lần dữ liệu bị đánh dấu quá hạn. |
| `enriched_branch_completed_total` | Kết quả ở downstream sau enrich. |
| `error_channel_messages_total` | Số lỗi đi qua error flow đã cấu hình. |

Đây là **các tên metric gợi ý**, không khẳng định những meter này được Spring Integration tự cung cấp. Không đưa `orderId`, `customerId` hoặc `traceId` vào metric labels có cardinality cao; giữ chúng trong log/tracing khi được phép.

### 14.4. Phân biệt các câu hỏi điều tra

| Tín hiệu | Kết luận hợp lệ |
|---|---|
| Có `ENRICHMENT_STARTED` | Enricher bắt đầu, chưa chắc đã lookup xong. |
| Có `PROFILE_LOOKUP_RECEIVED` | Có response, chưa chắc schema/customerId hợp lệ. |
| Có `ENRICHMENT_COMPLETED` | Wrapper được tạo theo contract, chưa chắc downstream thành công. |
| Có `ROUTE_DECIDED` | Router đã chọn đích, chưa chắc handler nhận được. |
| Có `BRANCH_COMPLETED` | Nhánh báo hoàn tất theo contract, còn tùy side effect và transaction. |

Ví dụ nếu khách hàng phản ánh “đơn GOLD không được ưu tiên”, kiểm tra tuần tự: order gốc có đúng `customerId` không, lookup trả profile nào, có mismatch/stale không, enriched payload có `verified=true` không, Router đọc đúng profile namespace không, rồi mới kiểm tra channel/handler ưu tiên.

## 15. Security, privacy và ranh giới tin cậy

### 15.1. Không để dữ liệu input tự giả làm enrichment

Nếu client gửi:

~~~json
{
  "orderId": "ORD-1001",
  "customerId": "C-007",
  "amountVnd": 9000000,
  "tier": "GOLD",
  "verified": true
}
~~~

thì các field `tier` và `verified` **không được tự động tin cậy chỉ vì nằm trong JSON**. Trong mô hình bài học, original không chứa hai field này; Enricher phải lấy chúng từ nguồn đã được xác thực và kiểm tra customer ID. Nếu converter vẫn nhận unknown fields, cần quyết định rõ liệu reject, ignore hay log schema violation — không để chúng lặng lẽ ghi đè `profile` đáng tin.

### 15.2. Xác thực kết quả lookup

Một lời gọi Customer Profile Service production cần:

- Sử dụng cơ chế authentication/authorization giữa dịch vụ và tối thiểu quyền cần thiết.
- Kiểm tra response schema, mã khách hàng khớp và các giá trị tier được phép.
- Có timeout, retry policy và cơ chế phân biệt lỗi vĩnh viễn/tạm thời.
- Giới hạn dữ liệu trả về theo mục đích; tránh lấy toàn bộ hồ sơ khi chỉ cần tier/verified.
- Bảo vệ dữ liệu trong log, message store, DLQ, tracer và broker.
- Không nhận profile từ response cache sai tenant hoặc sai phân vùng.

**Profile mismatch** có thể là bug tra cứu hoặc rò rỉ dữ liệu giữa tenant, nên không nên chỉ “bỏ qua và dùng customerId của original” như thể mọi thứ vẫn đúng.

### 15.3. Payload vs header qua adapter

Một outbound adapter có thể map payload và headers khác nhau. Nếu schema `EnrichedOrder` cần qua Kafka/HTTP:

1. Định nghĩa **wire schema** có version, các trường `original`/`profile`/`enrichment` được phép.
2. Serialize/deserialize một cách có kiểm tra, không giả định toàn bộ header nội bộ được truyền tự động.
3. Propagate trace/correlation context theo cơ chế transport được hỗ trợ.
4. Không serialise object `replyChannel`/`errorChannel` của JVM.
5. Test round-trip để chứng minh original và enrichment không bị rơi mất trường.
6. Mã hóa hoặc giảm thiểu dữ liệu nhạy cảm theo yêu cầu bảo mật.

Nếu chỉ gửi payload `profile` mà bỏ `original` vào một header tùy biến, adapter có thể lọc header làm mất thông tin ban đầu. Với yêu cầu **hai phần là dữ liệu nghiệp vụ bắt buộc**, wrapper payload là một hợp đồng dễ kiểm chứng hơn.

## 16. Ma trận kiểm thử toàn diện

| ID | Input/điều kiện | Expected | Không được xảy ra |
|---|---|---|---|
| CE-01 | Order hợp lệ, profile GOLD verified | Wrapper có original + profile + metadata | Original bị đổi amount/customerId. |
| CE-02 | Order hợp lệ, profile STANDARD unverified | Wrapper vẫn hợp lệ | Tự gán GOLD/verified. |
| CE-03 | Customer profile không tồn tại | Lỗi `PROFILE_NOT_FOUND` | Trả fake profile “thành công”. |
| CE-04 | Lookup trả customerId khác | Lỗi mismatch | Ghép profile người khác vào original. |
| CE-05 | Tier ngoài allowlist | Lỗi validation | Router nhận key lạ. |
| CE-06 | Amount `null`/0/âm | Lỗi original validation trước lookup | Gọi lookup không cần thiết. |
| CE-07 | CustomerId trống | Lỗi original validation | Định tuyến như khách hàng hợp lệ. |
| CE-08 | Số tiền 9.000.000 | Kết quả giữ đúng `BigDecimal` | Mất precision do ép `double`. |
| CE-09 | Original chứa mutable list | Defensive copy theo hợp đồng | Subscriber khác làm thay đổi dữ liệu gốc. |
| CE-10 | Clock cố định | Metadata có timestamp chính xác | Test phụ thuộc `sleep`. |
| CE-11 | Gateway gửi OrderRequest | Reply `EnrichedOrder` đầy đủ | Chỉ còn `CustomerProfile`. |
| CE-12 | Lookup trả dữ liệu đúng nhưng downstream lỗi | Enrichment success, downstream failure | Đếm như lookup failed. |
| CE-13 | CustomerProfile Service timeout | Retry/recovery có giới hạn | Gán verified=true hoặc retry vô hạn. |
| CE-14 | Cache trả dữ liệu stale | Hành vi theo freshness policy | Đánh dấu dữ liệu cũ như mới. |
| CE-15 | Hai order cùng customer | Mỗi enriched wrapper đúng order | Ghép reply của order A cho B. |
| CE-16 | Splitter item qua enrich | Correlation/sequence đúng | Aggregator gom nhầm group. |
| CE-17 | Một item bị lookup lỗi | Release/timeout rõ | Aggregator chờ vô hạn. |
| CE-18 | Message qua HTTP/Kafka adapter | Original/enrichment round-trip đúng | Header/field quan trọng biến mất im lặng. |
| CE-19 | Replay khi profile đã đổi | Hành vi đúng policy historical/latest | Không biết phiên bản nào đã dùng. |
| CE-20 | Lookup thành công nhưng reply Gateway timeout | Lỗi/late reply được quản lý | Caller tự coi request đã hủy mọi side effect. |
| CE-21 | Client tự gửi tier/verified giả | Không override profile đáng tin | Bỏ qua authorization. |
| CE-22 | Đồng thời nhiều request lookup | Correlation không lẫn | Dùng chỉ customerId để ghép mọi reply. |
| CE-23 | Retry operation có side effect | Idempotency/reconciliation phù hợp | Tạo side effect lặp. |
| CE-24 | Handler sau enrich yêu cầu original | Vẫn truy cập được orderId/amount | Chỉ còn header ngầm hoặc profile. |

Không phải tất cả test đều cần gọi dịch vụ thật. **Unit test** bảo vệ policy/wrapper, **Spring integration test** kiểm tra Gateway/Transformer/channel, **adapter-level test** kiểm tra serialization/header mapping, và **system test** kiểm tra timeout, caching, retry, consistency, security. Điều quan trọng là chọn **cấp kiểm thử có thể phát hiện đúng loại lỗi**.

### 16.1. Khi test không cần spring context

Dùng JUnit thường cho `OrderContentEnrichmentService` với directory giả:

~~~text
Given:
  original = OrderRequest(ORD-1, C-007, 9000000)
  directory trả CustomerProfile(C-007, GOLD, true)

When:
  enrich(original)

Then:
  result.original == original
  result.profile.customerId == original.customerId
  result.metadata.source != blank
~~~

Không mock quá mức khiến test chỉ chứng minh mock trả gì. Ví dụ, nếu mock `directory` trả profile nhưng service không kiểm tra customerId, **negative test mismatched ID** ở phần 8 mới bắt được lỗi có ý nghĩa.

### 16.2. Khi test phải đi qua adapter thật

Nếu module gửi enriched payload tới Kafka:

~~~text
Java EnrichedOrder
   -> serializer / outbound adapter
   -> broker record
   -> inbound adapter / deserializer
   -> Java EnrichedOrder
~~~

Cần assert sau round-trip:

- `original.orderId`/`customerId`/`amountVnd` đúng.
- `profile.tier`/`verified` đúng.
- `metadata.source`/`retrievedAt` đúng theo contract.
- Schema version tương thích, message sai phiên bản bị phát hiện.
- Trace/correlation được map và khôi phục khi nghiệp vụ cần.

Đừng dùng một serializer test với object trong cùng JVM rồi suy ra broker consumer ở process khác chắc chắn giữ đầy đủ mọi header. Cần test adapter/transport theo cấu hình thực tế.

## 17. Những sai lầm thiết kế thường gặp

| Sai lầm | Rủi ro | Cách làm đúng |
|---|---|---|
| Enricher chỉ trả `CustomerProfile`. | Mất `orderId` và amount của original trong payload. | Dùng wrapper giữ cả original và profile hoặc projection có chủ đích. |
| Ghi đè original bằng dữ liệu lookup. | Không biết upstream gửi gì; audit và retry khó tin cậy. | Giữ original tách biệt, gắn provenance dữ liệu enrich. |
| Coi Java `record` là deep immutable. | Collection/object lồng vẫn bị mutate. | Defensive copy và loại bỏ shared mutable state. |
| Coi customerId của response không cần kiểm tra. | Ghép dữ liệu khách hàng khác, có thể vi phạm phân vùng. | So khớp lookup key, response identity và authorization. |
| Dùng tier do client tự đưa vào. | Giả mạo hạng/quyền. | Lấy từ nguồn đáng tin và validate. |
| Không tìm thấy profile thì mặc định GOLD. | Cho phép xử lý sai chính sách. | Fail closed hoặc fallback có nhãn và phạm vi rõ. |
| Lookup timeout được coi là `verified=false` mà không phân biệt nguyên nhân. | Trộn lỗi hạ tầng với dữ liệu thực tế chưa xác minh. | Có trạng thái unavailable/recovery riêng. |
| `retrievedAt` được hiểu là thời điểm profile cập nhật. | Ra quyết định dựa trên độ mới sai. | Tách sourceUpdatedAt và retrievedAt khi cần. |
| Enrich mọi field để “đề phòng”. | Payload lớn, chi phí lookup cao, lộ dữ liệu không cần thiết. | Chỉ lấy đúng thông tin phục vụ consumer. |
| Dùng `replyChannel` như chỗ giữ original. | Header nội bộ có thể không qua transport; semantics sai. | Giữ original trong payload/schema nghiệp vụ. |
| Chỉ test profile không null. | Có thể ghép sai customer hoặc mất original. | Assert cả hai phần, ID matching, metadata và negative cases. |
| Coi `.transform` và native `.enrich` hoàn toàn đồng nhất. | Bỏ sót khác biệt mutation/property mapping/reply. | Chọn API theo contract, kiểm thử theo version dùng thật. |
| Chạy lookup ở mỗi retry toàn flow. | Tăng traffic, kết quả có thể thay đổi và tạo side effect trùng. | Retry ở đúng phạm vi, dùng idempotency/provenance. |
| Dùng cache cũ mà không đánh dấu. | Người dùng/Router tin dữ liệu đã được cập nhật. | Freshness policy và metadata nguồn. |
| Giả định Dispatcher/MessageBuilder tự giữ mọi headers qua HTTP/Kafka. | Mất correlation hoặc reply context. | Map headers theo hợp đồng transport; test round-trip. |
| Enricher bị lỗi nhưng tiếp tục sang Router với profile fake. | Nhánh processing bị chọn sai. | Không tạo success wrapper khi điều kiện bảo đảm chưa đạt. |
| Đặt toàn bộ enriched profile vào log. | Lộ dữ liệu nhạy cảm. | Log ID/flags có kiểm soát, masking và retention. |
| Coi Message History là lịch sử dữ liệu profile. | Không biết dữ liệu lấy từ nguồn/version nào. | Thêm provenance và audit record khi cần. |
| Chỉ cần accepted từ Gateway là external side effect đã commit. | Trả thành công sớm. | Theo dõi business outcome ở từng endpoint. |
| Nhiều request cùng customerId dùng chung một lookup correlation ID. | Reply lẫn giữa các order. | Tạo attempt/request ID đủ duy nhất khi ghép kết quả bất đồng bộ. |

## 18. Các bài tập thực hành

1. **Bảo toàn original:** tạo `OrderRequest` hợp lệ, dùng `OrderContentEnrichmentService` tạo `EnrichedOrder`; kiểm tra mọi trường gốc vẫn giữ đúng giá trị.
2. **Lỗi nguồn tra cứu:** directory trả `Optional.empty()`. Viết test xác nhận không tạo một `CustomerProfile` giả và nhận đúng `ProfileNotFoundException`.
3. **Sai customer:** directory cố ý trả profile của ID khác. Chứng minh `ProfileMismatchException` được ném trước khi downstream nhận message.
4. **Kiểm tra immutable:** thêm `List<OrderItem>` vào original, sửa list nguồn sau khi khởi tạo record. Áp dụng defensive copy và viết test phát hiện.
5. **Provenance:** bổ sung `sourceUpdatedAt` vào metadata, kiểm thử khác biệt với `retrievedAt` bằng `Clock.fixed`.
6. **Gateway integration:** dùng `OrderEnrichmentFlowConfiguration`, gọi `OrderEnrichmentGateway.enrich` và assert original/profile/metadata đều có.
7. **Native Content Enricher:** thay Transformer bằng cách dùng Content Enricher của phiên bản Spring Integration trong dự án. Làm rõ mapping request/reply, property/header, mutation/copy, output. Test kết quả vẫn giữ đủ hai phần.
8. **Enrich từ HTTP:** thay in-memory directory bằng một outbound gateway/client giả; thử success, 404, response sai schema và timeout. Thiết kế retry với deadline và phân loại lỗi.
9. **Router sau enrich:** nếu `GOLD` và verified thì gửi tới priority, còn lại standard; chứng minh handler ở mỗi nhánh vẫn đọc được original order.
10. **Filter sau enrich:** profile hợp lệ nhưng `verified=false`. Xác minh business rejection khác với lỗi lookup.
11. **Dữ liệu cache stale:** giả lập cache có `sourceUpdatedAt` quá cũ; chọn fail closed hoặc fallback theo một policy xác định và viết test.
12. **Replay:** enrich cùng original vào hai thời điểm khác nhau trong lúc tier khách thay đổi. So sánh snapshot historical với re-evaluate latest.
13. **Splitter/Aggregator:** chia một đơn thành ba item, enrich từng item theo product ID rồi gom lại. Làm mất một item có chủ đích và xử lý timeout/group release.
14. **Correlation async:** gửi hai request cùng customerId nhưng khác orderId tới lookup service bất đồng bộ, đảo thứ tự reply và chứng minh không ghép lẫn original.
15. **Transport:** serialize một `EnrichedOrder` ra JSON, rồi deserialize. Kiểm tra original, profile và provenance đầy đủ; thêm test missing-field/schema-version.
16. **Bảo mật:** gửi một original payload có trường `tier=GOLD` giả mạo từ client. Chứng minh parser/validation không cho field đó ghi đè profile tra cứu.
17. **Observability:** tạo log `ENRICHMENT_STARTED`, `PROFILE_LOOKUP_RECEIVED`, `ENRICHMENT_COMPLETED`, `ENRICHMENT_FAILED` và tìm một request thất bại theo trace/correlation.
18. **Error channel:** chuyển lookup sang asynchronous adapter, cấu hình xử lý lỗi tương ứng và chứng minh producer acknowledgement không đồng nghĩa enrich đã xong.

### Gợi ý kiểm tra kết quả bài tập

Để đánh giá một implementation đúng, hãy hỏi:

- Sau bước enrich, một consumer có thể **truy cập payload gốc mà không tra cứu lại** không?
- Dữ liệu bổ sung có **đúng identity và đúng nguồn** không?
- Có biết profile đến từ lúc nào và có thể stale hay không?
- Khi lookup thiếu hoặc lỗi, có **không phát success wrapper** sai không?
- Khi một message được retry hoặc replay, quyết định về dùng snapshot cũ/mới có rõ ràng không?
- Ở flow async, có biết khi nào **đã dispatch**, **đã enrich** và **đã hoàn tất downstream** không?

Nếu câu trả lời là “không” cho một câu hỏi quan trọng với nghiệp vụ, cần bổ sung schema, error handling hoặc test trước khi đưa vào production.

## 19. Câu hỏi tự kiểm tra

**Câu 1:** Vì sao chỉ trả `CustomerProfile` từ enrichment có thể là lỗi?  
**Đáp án:** Payload sau lookup không còn chứa `OrderRequest` và các trường như `orderId`/`amountVnd` nếu không có hợp đồng lưu riêng; downstream không thể truy cập original theo yêu cầu.

**Câu 2:** Dùng `record EnrichedOrder(OrderRequest original, CustomerProfile profile, ...)` đã bảo đảm mọi object bên trong là immutable chưa?  
**Chưa.** Record cố định các reference, nhưng object/collection mutable lồng bên trong vẫn có thể thay đổi; cần defensive copy khi phù hợp.

**Câu 3:** Original có customerId `C-007` nhưng lookup trả profile `C-099`. Có thể ghép chung và tiếp tục không?  
**Không.** Đây là lỗi identity/data integrity, có thể còn là vấn đề bảo mật; phải từ chối hoặc recovery theo contract.

**Câu 4:** Lookup không tìm thấy profile khác gì lookup HTTP timeout?  
**Not found** là một kết quả domain; **timeout** có thể là lỗi hạ tầng hoặc outcome không chắc chắn. Chính sách retry/recovery của hai loại khác nhau.

**Câu 5:** Có thể dùng `Clock.fixed` để kiểm thử `retrievedAt` không?  
**Có.** Inject Clock giúp test deterministic mà không cần chờ hoặc đọc thời gian hệ thống rồi so sánh xấp xỉ.

**Câu 6:** Nếu `EnrichedOrder` chứa original và profile, có chắc tất cả message headers được giữ qua Kafka không?  
**Không.** Payload và MessageHeaders là hai phần khác nhau; adapter/header mapper/serializer quyết định metadata nào được truyền.

**Câu 7:** Nếu cùng một order được enrich lại ngày hôm sau với tier mới, hai kết quả khác nhau có tự chứng minh bug không?  
**Không.** Cần biết policy historical snapshot hay re-evaluate latest; profile có thể thay đổi hợp lệ theo thời gian.

**Câu 8:** Khi một Filter sau enrichment loại order vì `verified=false`, đó có phải là lookup failure không?  
**Không.** Lookup có thể đã thành công và trả một profile hợp lệ; Filter từ chối vì policy nghiệp vụ.

**Câu 9:** Tại sao chỉ dùng `customerId` làm correlation key có thể sai khi lookup bất đồng bộ?  
**Vì** nhiều order hoặc nhiều attempt có thể cùng customerId; reply phải quay về đúng request/original tương ứng.

**Câu 10:** Dùng `.transform(...)` để tạo wrapper có thể hiện thực Content Enricher pattern không?  
**Có.** Pattern mô tả hành vi bổ sung dữ liệu; endpoint Transformer thực hiện việc tạo payload mới. Nhưng khác với các API Content Enricher chuyên dụng ở chi tiết mapping, request–reply và xử lý object, cần test đúng lựa chọn.

**Câu 11:** Có nên copy toàn bộ object `replyChannel` và `errorChannel` sang JSON event để “giữ metadata” không?  
**Không.** Chúng có thể là tham chiếu JVM nội bộ; phải thiết kế transport reply/correlation và header mapping thích hợp.

**Câu 12:** Vì sao log `ENRICHMENT_COMPLETED` chưa đủ chứng minh đơn đã được lưu?  
**Vì** đó chỉ là mốc tạo kết quả enrichment. Endpoint lưu đơn ở downstream có thể chưa chạy, đang chạy hoặc thất bại.

## 20. Kết luận

**Giữ payload gốc và dữ liệu đã enrich** không chỉ là thao tác nối thêm vài field vào một object. Đây là quyết định về **hợp đồng dữ liệu, tính bất biến, nguồn gốc, khả năng truy nguyên và tính đúng đắn của các bước downstream**.

Với Spring Integration, một cách rõ ràng là giữ `OrderRequest` trong trường `original`, lưu kết quả tra cứu trong `profile` và metadata trong `enrichment`/`metadata`. Có thể dùng **Content Enricher chuyên dụng** hoặc dùng **Transformer kết hợp enrichment service** để tạo wrapper immutable; điều quan trọng là không mất input, không trộn sai identity, không giả dữ liệu khi lookup lỗi và hiểu rõ response/header semantics của endpoint đang sử dụng.

Khi kết hợp với Router, Filter, Gateway, Splitter, Aggregator và error channel trong `SPRING_INTEGRATION_PATTERN`, hãy kiểm thử đủ các đường thành công, thiếu dữ liệu, mismatch, timeout, dữ liệu stale, retry và correlation. Kết quả là flow ít phụ thuộc hơn, dễ mở rộng hơn và cho phép người vận hành trả lời được ba câu hỏi thiết yếu: **“Ban đầu đã nhận gì?”, “Đã bổ sung dữ liệu gì từ đâu?”, và “Bước tiếp theo đã quyết định/xử lý ra sao?”**
