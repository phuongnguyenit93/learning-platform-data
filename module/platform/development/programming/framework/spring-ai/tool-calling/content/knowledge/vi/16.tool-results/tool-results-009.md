# Lưu nguồn dữ liệu và thời điểm đọc để hỗ trợ kiểm chứng

Kết quả một tool có thể đúng tại thời điểm truy vấn nhưng đã cũ khi người dùng đọc câu trả lời. Model cũng có thể diễn giải dữ liệu mà không giữ được thông tin nguồn nếu callback chỉ trả về một chuỗi hoặc một con số. Vì vậy, kết quả tool nên mang theo thông tin nguồn gốc và thời điểm ứng dụng lấy dữ liệu để người dùng, hệ thống và người kiểm tra có thể xác minh câu trả lời.

Trong Spring AI, callback chịu trách nhiệm trả kết quả cho luồng tool calling. Ứng dụng quyết định cấu trúc kết quả đó, cách ghi nhận provenance và cách lưu audit. Một kết quả có thể gồm dữ liệu nghiệp vụ, mã bằng chứng, tên nguồn, thời điểm đọc, thời điểm nguồn cập nhật và trạng thái độ mới. Model có thể dùng các trường này để diễn giải kết quả; backend vẫn cần giữ bản ghi đáng tin cậy và ánh xạ mã bằng chứng sang nguồn đã được kiểm soát.

## Sau bài học, bạn có thể

- Phân biệt thời điểm ứng dụng đọc dữ liệu với thời điểm nguồn cập nhật hoặc công bố dữ liệu.
- Thiết kế DTO kết quả tool có provenance và evidence ID.
- Ghi nhận timestamp theo UTC bằng `Instant` và `Clock`.
- Giữ thông tin nguồn khi một tool tổng hợp nhiều bản ghi hoặc nhiều dịch vụ.
- Xử lý nguồn thiếu timestamp, dữ liệu cache và kết quả đã cũ.
- Cung cấp bằng chứng cho model mà không để model tự tạo URL hoặc nguồn trích dẫn.
- Lưu audit phục vụ kiểm chứng mà không ghi lộ dữ liệu nhạy cảm.
- Kiểm thử thời điểm đọc, độ mới và ánh xạ bằng chứng.

## Vì sao kết quả tool cần provenance?

Giả sử người dùng hỏi: “Đơn hàng DH-1024 hiện đang ở đâu?”. Tool truy vấn dịch vụ vận chuyển và trả về trạng thái `IN_TRANSIT`. Chỉ có trạng thái này thì chưa đủ để xác định:

- Dữ liệu đến từ hệ thống vận chuyển nào?
- Ứng dụng đọc trạng thái lúc mấy giờ?
- Nguồn đã cập nhật trạng thái lần cuối khi nào?
- Dữ liệu được đọc trực tiếp hay lấy từ cache?
- Có mã tham chiếu nào để kiểm tra lại bản ghi gốc?
- Kết quả có đủ mới để đưa ra câu trả lời “hiện tại” không?

Provenance (thông tin nguồn gốc) trả lời những câu hỏi này. Nó giúp phân biệt nội dung nghiệp vụ với bằng chứng về nơi và thời điểm nội dung được lấy.

Một kết quả tool nên có ít nhất hai nhóm thông tin:

1. **Dữ liệu nghiệp vụ:** trạng thái đơn hàng, số dư, thông tin khách hàng hoặc kết quả tính toán.
2. **Thông tin kiểm chứng:** nguồn, thời điểm đọc, thời điểm cập nhật từ nguồn nếu có, mã bản ghi hoặc evidence ID, và trạng thái độ mới.

~~~mermaid
flowchart TD
    A[Tool nhận yêu cầu] --> B[Đọc nguồn dữ liệu]
    B --> C[Dữ liệu nghiệp vụ]
    B --> D[Metadata nguồn và timestamp]
    C --> E[Kết quả có provenance]
    D --> E
    E --> F[ToolCallback trả kết quả]
    F --> G[Model diễn giải cùng bằng chứng]
    E --> H[Audit store / evidence registry]
    G --> I[Câu trả lời có dẫn chiếu]
    H --> J[Ứng dụng xác minh evidence ID]
~~~

Thông tin provenance không chứng minh dữ liệu chắc chắn đúng. Nó cho biết dữ liệu được lấy từ đâu và vào thời điểm nào để người kiểm tra có thể đánh giá độ tin cậy, độ mới và khả năng truy vết.

## Phân biệt các loại thời điểm

Không dùng một trường timestamp cho nhiều ý nghĩa. Những thời điểm sau thường khác nhau:

| Trường | Ý nghĩa | Ai cung cấp |
|---|---|---|
| `sourcePublishedAt` | Thời điểm nguồn công bố tài liệu hoặc bản ghi | Hệ thống nguồn |
| `sourceUpdatedAt` | Thời điểm dữ liệu ở nguồn được cập nhật gần nhất | Hệ thống nguồn |
| `retrievedAt` | Thời điểm ứng dụng đọc dữ liệu từ nguồn | Ứng dụng |
| `servedAt` | Thời điểm ứng dụng trả dữ liệu cho caller | Ứng dụng |
| `originFetchedAt` | Thời điểm dữ liệu được lấy từ nguồn gốc trước khi đưa vào cache | Cache/client metadata |
| `eventOccurredAt` | Thời điểm sự kiện nghiệp vụ thực sự xảy ra | Hệ thống phát sinh sự kiện |

Ví dụ, một đơn hàng được giao lúc 09:00, hệ thống vận chuyển cập nhật bản ghi lúc 09:03, ứng dụng đọc lúc 09:05 và trả câu trả lời lúc 09:05:02. Bốn thời điểm này không thể thay thế cho nhau.

Đặc biệt:

- Không đặt tên `retrievedAt` cho timestamp do upstream gửi.
- Không thay `sourceUpdatedAt` bị thiếu bằng `Instant.now()`; điều đó tạo ấn tượng sai rằng nguồn vừa cập nhật.
- Không dùng thời điểm model trả lời làm thời điểm dữ liệu được đọc.
- Nếu không biết thời điểm nguồn cập nhật, biểu diễn là không có giá trị hoặc trạng thái `UNKNOWN`, đồng thời giữ `retrievedAt` do ứng dụng ghi nhận.

## Thiết kế DTO kết quả có provenance

Với method `@Tool`, nên trả về một DTO có cấu trúc thay vì chỉ trả một chuỗi đã ghép. Ví dụ:

~~~java
public record SourceEvidence(
        String evidenceId,
        String sourceId,
        String sourceLabel,
        Instant retrievedAt,
        Instant sourceUpdatedAt,
        Freshness freshness,
        String sourceVersion,
        String recordReference,
        boolean cacheHit,
        Long cacheAgeSeconds
) {
}

public record OrderStatusToolResult(
        String orderId,
        String status,
        String currentLocation,
        SourceEvidence evidence
) {
}
~~~

Ý nghĩa của các trường:

- `evidenceId`: mã duy nhất do ứng dụng tạo để tra cứu bản ghi bằng chứng.
- `sourceId`: định danh nguồn ổn định trong registry nội bộ.
- `sourceLabel`: tên nguồn đã được ứng dụng xác định.
- `retrievedAt`: thời điểm ứng dụng lấy dữ liệu.
- `sourceUpdatedAt`: timestamp nguồn cung cấp, có thể không có.
- `sourceVersion`: phiên bản hoặc revision nếu nguồn hỗ trợ.
- `recordReference`: mã tham chiếu bản ghi đã được làm sạch.
- `cacheHit` và `cacheAgeSeconds`: thông tin cache nếu kết quả đến từ cache.

Không phải tool nào cũng cần tất cả trường. Chọn những metadata có ý nghĩa đối với nguồn cụ thể. Nếu không dùng cache, có thể bỏ các trường cache. Nếu nguồn không có version, để trường đó vắng mặt thay vì tự tạo giá trị giả.

DTO trả về phải phù hợp với cách Spring AI serialize kết quả tool. Với method-based tool, dùng kiểu dữ liệu có thể serialize; với function callback, dùng POJO/record được hỗ trợ. Nếu dùng custom result converter, kiểm tra output thực tế mà model nhận được để chắc chắn provenance không bị loại bỏ.

## Ghi retrievedAt từ ứng dụng

Ứng dụng nên tự ghi nhận thời điểm hoàn tất việc đọc dữ liệu từ nguồn. Dùng `Instant` để lưu thời điểm tuyệt đối theo UTC và inject `Clock` để test có thể điều khiển thời gian.

Ví dụ service đọc trạng thái đơn hàng:

~~~java
@Service
public class OrderQueryService {

    private final ShippingGateway shippingGateway;
    private final Clock clock;
    private final EvidenceIdGenerator evidenceIdGenerator;

    public OrderQueryService(
            ShippingGateway shippingGateway,
            Clock clock,
            EvidenceIdGenerator evidenceIdGenerator) {
        this.shippingGateway = shippingGateway;
        this.clock = clock;
        this.evidenceIdGenerator = evidenceIdGenerator;
    }

    public OrderStatusToolResult getStatusForTenant(String orderId, String tenantId) {
        ShippingSnapshot snapshot = shippingGateway.getStatus(orderId, tenantId);

        Instant retrievedAt = clock.instant();
        Freshness freshness = evaluateFreshness(
                snapshot.updatedAt(),
                retrievedAt,
                Duration.ofMinutes(5)
        );

        SourceEvidence evidence = new SourceEvidence(
                evidenceIdGenerator.nextId(),
                "shipping-provider",
                "Hệ thống vận chuyển",
                retrievedAt,
                snapshot.updatedAt(),
                freshness,
                snapshot.version(),
                snapshot.reference(),
                false,
                null
        );

        return new OrderStatusToolResult(
                snapshot.orderId(),
                snapshot.status(),
                snapshot.currentLocation(),
                evidence
        );
    }
}
~~~

Ở đây `snapshot.updatedAt()` là timestamp do nguồn vận chuyển cung cấp; `clock.instant()` là thời điểm ứng dụng đọc xong snapshot. Hai trường được giữ riêng để người đọc biết dữ liệu nguồn cũ bao lâu tại thời điểm truy vấn.

Trong dự án thực tế, `ShippingSnapshot`, `EvidenceIdGenerator` và `ShippingGateway` là các kiểu của ứng dụng. Hãy bảo đảm gateway chỉ trả timestamp nguồn sau khi xác minh response và định dạng timestamp hợp lệ.

### Cấu hình Clock

Có thể cung cấp clock UTC bằng Spring bean:

~~~java
@Configuration(proxyBeanMethods = false)
public class TimeConfiguration {

    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }
}
~~~

Trong unit test, dùng clock cố định:

~~~java
Clock fixedClock = Clock.fixed(
        Instant.parse("2026-11-27T13:00:00Z"),
        ZoneOffset.UTC
);
~~~

Cách này giúp test timestamp ổn định, không phụ thuộc thời điểm chạy test hoặc timezone của máy. Lưu timestamp ở UTC; chỉ chuyển sang múi giờ địa phương khi hiển thị cho người dùng.

## Gắn provenance vào method @Tool

Tool nên trả về kết quả có evidence thay vì chỉ trả dữ liệu nghiệp vụ:

~~~java
@Component
public class OrderTools {

    private final OrderQueryService orderQueryService;

    public OrderTools(OrderQueryService orderQueryService) {
        this.orderQueryService = orderQueryService;
    }

    @Tool(description = "Tra cứu trạng thái đơn hàng và thông tin nguồn cập nhật")
    public OrderStatusToolResult getOrderStatus(
            @ToolParam(description = "Mã đơn hàng cần tra cứu") String orderId,
            ToolContext toolContext) {

        String tenantId = (String) toolContext.getContext().get("tenantId");

        return orderQueryService.getStatusForTenant(orderId, tenantId);
    }
}
~~~

Trong ví dụ này, tool nhận `orderId` từ JSON do model tạo và `tenantId` từ context do ứng dụng thiết lập. Dịch vụ phải xác thực quyền xem đơn hàng trước khi truy vấn. Không đưa tenant ID vào tham số mà model tự tạo.

Kết quả tool mang `evidence` về nguồn và thời điểm đọc. Khi model tổng hợp câu trả lời, nó có thể diễn đạt: “Theo hệ thống vận chuyển, đơn hàng đang trên đường giao; dữ liệu được đọc lúc 20:00 UTC và nguồn cập nhật lúc 19:58 UTC.” Ứng dụng nên chuyển timestamp sang timezone người dùng và kiểm tra định dạng trước khi hiển thị.

## Phân biệt thời điểm đọc trực tiếp và thời điểm phục vụ từ cache

Khi dữ liệu đến từ cache, `retrievedAt` dễ bị hiểu sai. Nếu ứng dụng đọc một bản cache lúc 10:05, điều đó không có nghĩa dữ liệu gốc vừa được lấy lúc 10:05.

Nên ghi rõ:

- `servedAt`: thời điểm request hiện tại lấy dữ liệu từ cache.
- `originFetchedAt`: thời điểm cache/client lấy dữ liệu từ nguồn gốc.
- `sourceUpdatedAt`: thời điểm nguồn gốc nói rằng bản ghi được cập nhật.
- `cacheAgeSeconds`: tuổi của bản cache tại thời điểm phục vụ.

Ví dụ:

~~~java
public record CachedSourceEvidence(
        String evidenceId,
        String sourceId,
        Instant servedAt,
        Instant originFetchedAt,
        Instant sourceUpdatedAt,
        long cacheAgeSeconds,
        boolean cacheHit
) {
}
~~~

Nếu cache trả về `originFetchedAt=10:00` và request đọc cache lúc 10:05, `cacheAgeSeconds` xấp xỉ 300 giây. Nếu chỉ lưu `retrievedAt=10:05`, model có thể hiểu nhầm dữ liệu đã được lấy từ nguồn gốc lúc 10:05.

Cache metadata phải được tạo từ cache layer đáng tin cậy. Không để model tự điền `cacheHit` hoặc `cacheAgeSeconds`. Nếu không biết thời điểm fetch gốc, hãy ghi `UNKNOWN` hoặc bỏ trường đó, không suy đoán từ thời điểm cache được đọc.

## Tính và diễn đạt độ mới của dữ liệu

Độ mới có thể được đánh giá từ chênh lệch giữa thời điểm hiện tại và timestamp phù hợp. Chọn timestamp theo ý nghĩa dữ liệu:

- Với bản ghi nguồn, dùng `sourceUpdatedAt`.
- Với dữ liệu chỉ có thể xác định lúc ứng dụng truy vấn, dùng `retrievedAt` và nói rõ đó là thời điểm đọc.
- Với cache, cân nhắc cả `originFetchedAt` và `cacheAgeSeconds`.

Ví dụ một chính sách đơn giản:

~~~java
public enum Freshness {
    FRESH,
    STALE,
    UNKNOWN
}

public Freshness evaluateFreshness(
        Instant sourceUpdatedAt,
        Instant retrievedAt,
        Duration maxAge) {

    if (sourceUpdatedAt == null) {
        return Freshness.UNKNOWN;
    }

    Duration age = Duration.between(sourceUpdatedAt, retrievedAt);

    if (age.isNegative()) {
        return Freshness.UNKNOWN;
    }

    return age.compareTo(maxAge) <= 0
            ? Freshness.FRESH
            : Freshness.STALE;
}
~~~

Timestamp tương lai có thể xuất phát từ clock skew hoặc lỗi dữ liệu; không nên tự coi nó là dữ liệu mới. Đánh dấu `UNKNOWN` và ghi nhận bất thường để điều tra.

Ngưỡng `maxAge` phải theo nghiệp vụ. Giá chứng khoán có thể cần vài giây; trạng thái hồ sơ hành chính có thể chấp nhận vài phút; tài liệu chính sách có thể chấp nhận ngày hoặc tháng. Không áp dụng một ngưỡng freshness chung cho mọi tool.

Nếu dữ liệu đã cũ, ứng dụng có thể:

- Trả kết quả kèm trạng thái `STALE` để model thông báo rõ.
- Thử làm mới nguồn nếu còn ngân sách thời gian.
- Từ chối trả kết luận “hiện tại” khi dữ liệu vượt ngưỡng quan trọng.
- Yêu cầu người dùng xác nhận hoặc thực hiện tra cứu lại.

Không bỏ metadata freshness chỉ vì dữ liệu vẫn có giá trị tham khảo. Model cần biết sự khác nhau giữa “trạng thái hiện tại” và “trạng thái ở lần đọc gần nhất”.

## Giữ provenance khi tổng hợp nhiều nguồn

Một tool có thể đọc nhiều nguồn, hoặc model có thể gọi nhiều tool trong cùng một lượt. Không gộp nhiều nguồn thành một trường `source` duy nhất nếu mỗi phần dữ liệu đến từ nguồn khác nhau.

Ví dụ kết quả tổng hợp:

~~~java
public record EvidenceReference(
        String evidenceId,
        String sourceId,
        Instant retrievedAt,
        Instant sourceUpdatedAt
) {
}

public record CustomerOverviewResult(
        CustomerSummary customer,
        List<OrderSummary> recentOrders,
        List<EvidenceReference> evidence
) {
}
~~~

Nếu thông tin hồ sơ đến từ CRM và đơn hàng đến từ Order Service, danh sách evidence phải giữ cả hai nguồn. Mỗi evidence ID liên kết với bản ghi nguồn cụ thể và thời điểm đọc riêng.

Với nhiều tool call chạy song song, mỗi callback nên tạo metadata cho kết quả của chính nó. Khi ứng dụng tổng hợp, giữ nguyên evidence ID và timestamp của từng phần. Không gán thời điểm hoàn thành cuối cùng của toàn bộ hội thoại cho tất cả nguồn vì thời gian đọc thực tế có thể khác nhau.

Nếu cần một thời điểm tổng hợp, có thể thêm `assembledAt` hoặc `responseGeneratedAt`, nhưng vẫn giữ `retrievedAt` riêng của từng evidence.

## Để model dẫn chiếu bằng evidence ID

Một cách an toàn là cho model thấy mã bằng chứng và metadata đã được ứng dụng tạo, sau đó yêu cầu model nhắc mã đó khi đưa ra kết luận. Backend dùng mã này để lấy nguồn tham chiếu đáng tin cậy.

Ví dụ nội dung tool result:

~~~json
{
  "orderId": "DH-1024",
  "status": "IN_TRANSIT",
  "evidence": {
    "evidenceId": "ev-8f13",
    "sourceLabel": "Hệ thống vận chuyển",
    "retrievedAt": "2026-11-27T13:00:00Z",
    "sourceUpdatedAt": "2026-11-27T12:58:00Z",
    "freshness": "FRESH"
  }
}
~~~

Model có thể trả lời rằng trạng thái được lấy từ nguồn vận chuyển và dẫn chiếu `[ev-8f13]`. Ứng dụng kiểm tra evidence ID có tồn tại trong registry của request hay không rồi mới render liên kết hoặc citation.

Không để model tự tạo URL trích dẫn từ tên nguồn. Model có thể tạo URL sai hoặc dẫn tới domain không đáng tin. Backend nên ánh xạ `evidenceId` sang URL hoặc trang chi tiết đã được xác minh, áp dụng allowlist domain và loại bỏ query parameter có thể chứa token.

Nếu tool result được chuyển về model dưới dạng plain text, giữ JSON hoặc format có cấu trúc nhất quán để model nhận diện evidence ID. Đồng thời lưu cùng metadata ở backend; không dựa vào nội dung model nhắc lại như nguồn audit duy nhất.

## Lưu audit để có thể kiểm chứng sau này

Tool result trong hội thoại không thay thế audit log. Nếu cần điều tra hoặc tái lập câu trả lời, ứng dụng nên lưu một audit event có cấu trúc:

~~~java
public record ToolEvidenceAuditEvent(
        String requestId,
        String conversationId,
        String toolName,
        String evidenceId,
        String sourceId,
        String userId,
        String tenantId,
        Instant retrievedAt,
        Instant sourceUpdatedAt,
        String sourceVersion,
        String outcome,
        long durationMillis
) {
}
~~~

Các trường audit giúp trả lời:

- Request nào đã gọi tool?
- Tool nào đã được thực thi?
- Người dùng và tenant nào thực hiện?
- Dữ liệu được lấy từ nguồn nào?
- Ứng dụng đọc lúc nào và nguồn cập nhật lúc nào?
- Phiên bản hoặc revision nào đã được dùng?
- Tool thành công, thất bại hay trả dữ liệu cũ?

Không mặc định lưu toàn bộ tool input/output. Dữ liệu có thể chứa thông tin cá nhân, access token hoặc nội dung nhạy cảm. Hãy lưu ID tham chiếu, timestamp, trạng thái và hash nếu cần đối chiếu; áp dụng retention, kiểm soát truy cập và mã hóa theo chính sách dữ liệu.

Nếu cần bảo đảm tính toàn vẹn cao hơn, có thể lưu hash của payload đã chuẩn hóa cùng version/schema. Hash giúp phát hiện payload thay đổi khi có bản gốc để đối chiếu; nó không chứng minh nguồn bên ngoài là chính xác hoặc đã được xác thực.

## Xử lý nguồn thiếu hoặc không đáng tin cậy

Không phải nguồn nào cũng cung cấp timestamp hoặc định danh ổn định. Hãy mô tả chính xác giới hạn:

| Tình huống | Cách biểu diễn | Cách diễn giải |
|---|---|---|
| Có sourceUpdatedAt hợp lệ | Ghi timestamp nguồn | Có thể tính tuổi dữ liệu |
| Nguồn không cung cấp timestamp | Để trống và freshness=UNKNOWN | Chỉ biết thời điểm ứng dụng đọc |
| Timestamp nguồn sai định dạng | Đánh dấu lỗi metadata | Không dùng để kết luận độ mới |
| Timestamp nằm trong tương lai | Freshness=UNKNOWN và ghi cảnh báo | Có thể có clock skew hoặc lỗi nguồn |
| Nguồn chỉ có version | Lưu sourceVersion | Có thể đối chiếu revision, không suy ra thời gian |
| Nguồn là cache | Ghi servedAt, originFetchedAt và cacheAge | Phân biệt thời điểm đọc cache với thời điểm fetch gốc |
| Nguồn không xác thực được | Không quảng bá như bằng chứng đáng tin | Dừng hoặc đánh dấu kết quả không xác minh |

Không nâng mức tin cậy chỉ vì dữ liệu có URL hoặc timestamp. Nguồn phải được xác thực theo cơ chế kết nối của ứng dụng: TLS, chứng thực service, chữ ký payload hoặc allowlist tùy hệ thống.

## Kiểm thử provenance và timestamp

Inject `Clock` giúp kiểm thử thời điểm đọc mà không phụ thuộc đồng hồ thật. Ví dụ:

~~~java
@Test
void shouldRecordReadTimeSeparatelyFromSourceUpdateTime() {
    Instant sourceUpdatedAt =
            Instant.parse("2026-11-27T12:58:00Z");
    Instant retrievedAt =
            Instant.parse("2026-11-27T13:00:00Z");

    Clock clock = Clock.fixed(retrievedAt, ZoneOffset.UTC);

    ShippingSnapshot snapshot = new ShippingSnapshot(
            "DH-1024",
            "IN_TRANSIT",
            "Da Nang",
            sourceUpdatedAt,
            "revision-17",
            "provider-ref-1024"
    );

    OrderQueryService service = new OrderQueryService(
            (orderId, tenantId) -> snapshot,
            clock,
            () -> "ev-8f13"
    );

    OrderStatusToolResult result = service.getStatusForTenant("DH-1024", "tenant-42");

    assertThat(result.evidence().retrievedAt()).isEqualTo(retrievedAt);
    assertThat(result.evidence().sourceUpdatedAt()).isEqualTo(sourceUpdatedAt);
    assertThat(result.evidence().evidenceId()).isEqualTo("ev-8f13");
}
~~~

Các test nên bao gồm:

- Timestamp đọc được ghi từ clock do ứng dụng quản lý.
- Timestamp nguồn được giữ riêng và không bị thay bằng retrievedAt.
- Nguồn thiếu timestamp trả freshness UNKNOWN.
- Timestamp tương lai không bị đánh dấu FRESH.
- Cache hit giữ originFetchedAt và tính cache age đúng.
- Nhiều nguồn giữ evidence ID và thời điểm riêng.
- Backend chỉ render citation khi evidence ID tồn tại và thuộc request hiện tại.
- Không rò rỉ secret hoặc dữ liệu cá nhân trong evidence và audit log.
- Tool trả dữ liệu cũ được gắn nhãn hoặc xử lý theo freshness policy.

Ngoài unit test, nên có integration test xác minh tool result converter giữ nguyên các trường provenance. Nếu model nhận kết quả dưới dạng chuỗi JSON, kiểm tra chuỗi thực tế chứa `evidenceId`, `retrievedAt` và `sourceUpdatedAt` khi các trường đó có sẵn.

## Những lỗi thường gặp

- **Dùng retrievedAt thay cho sourceUpdatedAt:** ứng dụng vừa đọc dữ liệu không có nghĩa nguồn vừa cập nhật.
- **Không lưu thời điểm đọc:** không thể xác định dữ liệu được lấy lúc nào để đánh giá freshness.
- **Dùng LocalDateTime không có timezone:** timestamp có thể bị hiểu khác giữa máy hoặc hệ thống. Lưu Instant UTC.
- **Để model tự tạo source URL hoặc timestamp:** metadata không còn đáng tin. Ứng dụng phải tạo và xác minh.
- **Gộp nhiều nguồn thành một source:** mất quan hệ giữa từng dữ liệu và nguồn tương ứng. Giữ evidence list.
- **Không phân biệt cache read và origin fetch:** dữ liệu cache cũ có thể bị mô tả như vừa lấy từ nguồn.
- **Coi timestamp là bằng chứng xác thực:** timestamp chỉ là metadata; cần xác thực nguồn và tính toàn vẹn riêng.
- **Không kiểm tra evidence ID:** model có thể nhắc mã không tồn tại hoặc thuộc request khác. Backend phải tra registry.
- **Ghi toàn bộ payload vào audit:** có thể làm lộ dữ liệu nhạy cảm và tăng rủi ro lưu trữ. Lưu metadata tối thiểu.
- **Dùng timestamp hiện tại khi nguồn không có timestamp:** tạo độ mới giả. Để UNKNOWN và nói rõ giới hạn.

## Checklist trước khi phát hành tool

- [ ] Kết quả tool có dữ liệu nghiệp vụ và metadata provenance riêng.
- [ ] Source ID và evidence ID được tạo hoặc xác minh ở backend.
- [ ] retrievedAt được ghi bởi ứng dụng sau khi đọc dữ liệu.
- [ ] sourceUpdatedAt chỉ lấy từ nguồn và có thể để trống.
- [ ] Timestamp dùng Instant UTC và Clock có thể inject trong test.
- [ ] Cache metadata phân biệt servedAt, originFetchedAt và cache age.
- [ ] Nhiều nguồn giữ danh sách evidence riêng.
- [ ] Model chỉ nhận metadata cần thiết và không tự tạo citation URL.
- [ ] Backend ánh xạ evidence ID sang nguồn/link đã xác minh.
- [ ] Audit log có request ID, tool, source, timestamp và outcome.
- [ ] Không lưu secret hoặc payload nhạy cảm không cần thiết.
- [ ] Có test cho timestamp, freshness, cache, evidence mapping và converter.

## Ghi nhớ khi thiết kế

Kết quả tool có thể được model dùng để đưa ra kết luận, nhưng người dùng cần biết dữ liệu đến từ đâu và được đọc lúc nào. Hãy giữ riêng `retrievedAt` do ứng dụng ghi nhận, `sourceUpdatedAt` do nguồn cung cấp và timestamp nghiệp vụ như `eventOccurredAt`. Với cache, lưu thêm thời điểm fetch gốc và tuổi cache.

Đưa provenance vào DTO kết quả tool, tạo evidence ID ở backend, lưu audit có kiểm soát và để backend ánh xạ evidence ID sang nguồn đã xác minh. Nếu không có timestamp nguồn, biểu diễn UNKNOWN thay vì suy đoán. Cách làm này giúp câu trả lời dễ kiểm chứng mà vẫn giữ được ranh giới giữa dữ liệu model diễn giải và bằng chứng do ứng dụng quản lý.

## Tài liệu tham khảo

- [Spring AI Reference — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring AI Reference — Tool Calling và Tool Results](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Java SE — Instant](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html)
- [Java SE — Clock](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Clock.html)
- [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/)

