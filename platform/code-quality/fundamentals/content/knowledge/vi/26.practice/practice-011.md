# Rà soát một thay đổi bằng hợp đồng, rủi ro và kiểm thử

## Mục tiêu thực hành

Sau bài học này, bạn có thể:

1. Rà soát một pull request theo **hợp đồng hành vi**, thay vì chỉ đọc từng dòng hoặc kiểm tra style.
2. Xác định **phạm vi thay đổi**, caller, dữ liệu, API, tác dụng phụ và các nhóm có thể bị ảnh hưởng.
3. Viết rõ **precondition, postcondition, invariant, error behavior và side effect** cho một thay đổi.
4. Đánh giá rủi ro theo **tác động, khả năng xảy ra, khả năng phát hiện, phạm vi ảnh hưởng và khả năng phục hồi**.
5. Chọn bằng chứng kiểm thử phù hợp: unit, integration, contract, security, concurrency, migration, end-to-end và kiểm thử vận hành.
6. Đưa ra review comment có thể hành động, phân biệt blocker với suggestion và kết luận dựa trên bằng chứng.
7. Nhận biết khi nào cần yêu cầu sửa, bổ sung test, tham vấn owner, thu hẹp phạm vi hoặc dừng merge để làm rõ rủi ro.

Trong module **CODE_QUALITY_FUNDAMENTALS**, chúng ta học những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi hay không**. Bài thực hành này kết nối các chủ đề về hợp đồng, cấu trúc, dữ liệu, kiểm thử, bảo mật, hiệu năng, quality gate và cộng tác thành một quy trình review có thể áp dụng cho thay đổi thật.

**Một review tốt trả lời ba câu hỏi:** thay đổi phải bảo đảm hành vi nào, điều gì có thể sai và bằng chứng nào cho thấy rủi ro đã được kiểm soát. Reviewer không cần chứng minh mình đọc được mọi dòng nhanh hơn tác giả; reviewer cần giúp nhóm phát hiện những giả định, hợp đồng hoặc đường lỗi mà thay đổi có thể làm hỏng.

## 1. Tình huống xuyên suốt: thay đổi quy tắc hủy đơn hàng

Giả sử một sản phẩm đang cho phép khách hàng hủy đơn ở trạng thái PENDING. Yêu cầu mới là cho phép hủy cả đơn CONFIRMED, miễn là kho chưa bắt đầu đóng gói. Khi hủy thành công, hệ thống cần giải phóng giữ chỗ tồn kho và phát một sự kiện để các hệ thống liên quan cập nhật.

Một pull request được mở với mô tả ngắn:

> “Allow cancellation for confirmed orders. Add status check and update tests.”

Nếu chỉ nhìn tiêu đề, thay đổi có vẻ đơn giản. Nhưng review cần làm rõ:
- Làm sao biết kho chưa bắt đầu đóng gói?
- Ai có quyền hủy đơn?
- Nếu kho bắt đầu đóng gói đồng thời với request hủy thì điều gì xảy ra?
- Hủy đơn có giải phóng tồn kho ngay hay qua event?
- Nếu phát event thất bại sau khi cập nhật đơn thì hệ thống phục hồi thế nào?
- Request hủy gửi lại có tạo side effect hai lần không?
- Mobile client cũ hiểu trạng thái mới ra sao?
- Test nào chứng minh hợp đồng mới?

Đây là lý do review phải bắt đầu từ **hành vi và rủi ro**, rồi mới đi vào implementation.

### Bối cảnh nghiệp vụ minh họa

Để thực hành, ta tạm dùng các quy tắc sau:

- Khách chỉ được yêu cầu hủy đơn của chính mình hoặc đơn mà họ có quyền quản lý.
- PENDING có thể hủy.
- CONFIRMED có thể hủy nếu kho chưa bắt đầu đóng gói.
- PACKING và SHIPPED không thể hủy bằng luồng thông thường.
- Hủy thành công chỉ tạo một lần chuyển trạng thái và một yêu cầu giải phóng giữ chỗ.
- Request lặp lại sau khi đã hủy phải có kết quả xác định, không giải phóng tồn kho nhiều lần.
- Nếu trạng thái thay đổi đồng thời trong lúc xử lý, chỉ một transition hợp lệ được thắng.
- API phải trả lỗi rõ ràng khi đơn không thể hủy hoặc người gọi không có quyền.

Đây là **hợp đồng giả định cho bài học**, không phải chính sách chung cho mọi hệ thống. Trong dự án thật, product/domain owner phải xác nhận quy tắc và các ngoại lệ trước khi reviewer coi chúng là tiêu chuẩn.

## 2. Bước đầu tiên: hiểu thay đổi trước khi đọc sâu code

Trước khi đọc diff, hãy đọc mô tả PR, ticket, acceptance criteria và các quyết định liên quan mà tác giả cung cấp. Mục tiêu là hiểu **vấn đề đang được giải quyết** và **ranh giới được phép thay đổi**.

### 2.1. Viết lại mục tiêu bằng một câu

Ví dụ:

> “Cho phép chủ đơn hủy đơn đã xác nhận khi kho chưa bắt đầu đóng gói, đồng thời bảo đảm trạng thái, giữ chỗ tồn kho và thông báo cho consumer nhất quán khi có request đồng thời hoặc gửi lặp.”

Câu này cụ thể hơn “thêm trạng thái hủy” vì nêu:
- Actor: chủ đơn.
- Điều kiện: kho chưa đóng gói.
- Hành động: hủy.
- Các bất biến cần bảo vệ: trạng thái, tồn kho, event.
- Rủi ro: đồng thời và idempotency.

### 2.2. Hỏi những câu còn thiếu

| Nhóm câu hỏi | Điều cần xác nhận |
| --- | --- |
| **Actor và quyền** | Ai được hủy? Chủ đơn, nhân viên hỗ trợ hay quản trị viên? |
| **Trạng thái** | Những trạng thái nào cho phép chuyển sang CANCELLED? |
| **Điều kiện kho** | PACKING được ghi nhận ở service nào? Có thể thay đổi đồng thời không? |
| **Tồn kho** | Reservation được giải phóng đồng bộ hay qua event? Có thể giải phóng hai lần không? |
| **Thanh toán** | Đơn đã thanh toán có cần refund hay chỉ release authorization? |
| **API** | Mã HTTP, error code và response nào được giữ tương thích? |
| **Lặp request** | Retry cùng request có trả kết quả cũ hay báo conflict? |
| **Dữ liệu lịch sử** | Đơn cũ có trạng thái hoặc trường nào cần migration không? |
| **Quan sát** | Có metric để theo dõi hủy thành công, bị từ chối và lỗi consumer không? |
| **Triển khai** | Có cần rollout theo tenant, feature flag hoặc phối hợp consumer không? |

Nếu câu trả lời ảnh hưởng tới tính đúng đắn hoặc an toàn, reviewer nên yêu cầu làm rõ trước khi phê duyệt. Không nên tự điền giả định nghiệp vụ vào code review chỉ để PR đi tiếp.

### 2.3. Xác định phạm vi và ngoài phạm vi

**Trong phạm vi**
- Quy tắc cho phép hủy.
- Kiểm tra quyền.
- Transition trạng thái có kiểm soát đồng thời.
- Yêu cầu giải phóng giữ chỗ.
- API response và test liên quan.

**Ngoài phạm vi nếu chưa được yêu cầu**
- Thiết kế lại toàn bộ payment service.
- Thay hệ thống event broker.
- Viết lại mọi trạng thái đơn hàng.
- Đổi toàn bộ API public không liên quan.

Phạm vi rõ giúp reviewer phát hiện scope creep và giúp tác giả giải thích những thay đổi bắt buộc phải mở rộng.

## 3. Đọc hợp đồng: precondition, postcondition và invariant

Một cách hiệu quả để review là viết hợp đồng trước khi xem implementation. Hợp đồng diễn đạt điều caller được phép kỳ vọng và điều hệ thống phải giữ.

### 3.1. Precondition — điều kiện trước khi thao tác

Với yêu cầu hủy đơn:
- Request có order ID hợp lệ.
- Actor đã được xác thực.
- Actor có quyền thực hiện hành động trên đơn.
- Đơn tồn tại và có trạng thái phù hợp.
- Điều kiện nghiệp vụ về kho cho phép hủy.
- Request có đủ thông tin cần thiết để nhận diện thao tác nếu API dùng idempotency key.

Không phải mọi precondition đều phải kiểm tra trong cùng một lớp. Authentication có thể do middleware xử lý; authorization và trạng thái đơn cần được bảo vệ ở service/domain boundary phù hợp.

### 3.2. Postcondition — điều kiện sau khi thao tác

Nếu hủy thành công:
- Đơn ở trạng thái CANCELLED.
- Phiên bản hoặc revision của đơn được cập nhật.
- Yêu cầu giải phóng reservation được ghi nhận đúng một lần theo hợp đồng.
- Event hoặc outbox record được tạo theo cơ chế đã chọn.
- Response phản ánh kết quả đã được commit.

Nếu thao tác bị từ chối:
- Đơn không bị chuyển trạng thái.
- Không có side effect giải phóng tồn kho.
- Caller nhận được lỗi phù hợp.
- Hệ thống có đủ thông tin để truy vết lý do từ chối mà không lộ dữ liệu nhạy cảm.

### 3.3. Invariant — điều luôn phải đúng

Một số invariant quan trọng:
- Đơn SHIPPED không được chuyển ngược về CANCELLED bằng luồng này.
- Không giải phóng một reservation nhiều hơn một lần.
- Actor không được truy cập đơn ngoài phạm vi quyền.
- Một transition chỉ thành công nếu trạng thái hiện tại vẫn phù hợp tại thời điểm ghi.
- Event phản ánh transition đã commit, không phải một ý định chưa được lưu bền vững.

Invariant thường quan trọng hơn chi tiết implementation. Reviewer nên hỏi liệu code có bảo vệ invariant trong điều kiện đồng thời, lỗi phụ thuộc và retry hay không.

### 3.4. Error behavior — hành vi khi không thành công

| Tình huống | Hành vi cần xác định |
| --- | --- |
| Order ID không hợp lệ | Validation error |
| Không tìm thấy đơn | Not found hoặc phản hồi không tiết lộ sự tồn tại theo chính sách |
| Actor không có quyền | Forbidden hoặc phản hồi bảo vệ thông tin tài nguyên |
| Trạng thái không cho phép hủy | Conflict/business error |
| Trạng thái đổi đồng thời | Conflict/retryable result theo hợp đồng |
| Repository/database lỗi | Không báo thành công; transaction được rollback hoặc xử lý theo thiết kế |
| Event broker tạm lỗi | Outbox/retry hoặc trạng thái pending được xác định |
| Request gửi lại | Kết quả idempotent hoặc conflict rõ ràng |

Không nên để mọi lỗi thành HTTP 500 hoặc trả thành công dù một side effect quan trọng chưa được ghi nhận.

## 4. Lập bản đồ thay đổi: ai gọi, ai bị ảnh hưởng?

Sau khi hiểu hợp đồng, hãy lần theo thay đổi qua các ranh giới.

### 4.1. Tìm caller và consumer

Một thao tác hủy có thể được gọi từ:
- REST API cho mobile/web.
- Trang hỗ trợ khách hàng.
- Job tự động hủy đơn hết hạn.
- Consumer xử lý yêu cầu từ đối tác.
- Admin tool.

Một thay đổi ở service method có thể ảnh hưởng tất cả caller. Review cần xác định:
- Caller nào được hưởng quy tắc mới?
- Caller nào cần quyền khác?
- Có luồng nào không được phép hủy CONFIRMED?
- Có consumer nào hiểu trạng thái mới?
- Có API hoặc event contract bị đổi không?

### 4.2. Lần theo dữ liệu và side effect

~~~mermaid
flowchart TD
    A[Client / Job] --> B[API validation]
    B --> C[Authentication and authorization]
    C --> D[Order domain policy]
    D --> E[Atomic state transition]
    E --> F[Persist cancellation intent]
    F --> G[Outbox / event publisher]
    G --> H[Inventory consumer]
    G --> I[Other consumers]
    H --> J[Release reservation]
~~~

Sơ đồ là một luồng tham khảo. Hệ thống thật có thể dùng transaction đồng bộ hoặc cơ chế khác. Điểm review là phải biết **đâu là điểm commit**, **side effect nào có thể lặp** và **cách phục hồi khi một bước thất bại**.

### 4.3. Xác định ranh giới sở hữu

| Thành phần | Câu hỏi ownership |
| --- | --- |
| Order domain | Ai sở hữu state machine và điều kiện hủy? |
| Authorization | Ai duy trì quyền actor trên đơn? |
| Order persistence | Ai bảo đảm transition nguyên tử? |
| Inventory | Ai sở hữu reservation và release idempotency? |
| Event contract | Ai quyết định schema và tương thích consumer? |
| API | Ai chịu trách nhiệm response/error code? |
| Operations | Ai theo dõi lỗi, event lag và rollback? |

Nếu một PR chạm vào contract của team khác, cần có bằng chứng tham vấn hoặc quy trình phối hợp tương ứng.

## 5. Đánh giá rủi ro trước khi quyết định mức review

Không phải mọi thay đổi cần cùng mức kiểm tra. Hãy đánh giá rủi ro theo các chiều:

- **Impact:** nếu sai thì hậu quả là gì?
- **Likelihood:** điều kiện khiến lỗi có thể xảy ra thường xuyên đến đâu?
- **Detectability:** có test, alert hoặc đối soát phát hiện trước khi ảnh hưởng không?
- **Blast radius:** bao nhiêu user, tenant, service hoặc dữ liệu bị ảnh hưởng?
- **Recoverability:** có rollback, replay, bù trừ hoặc khôi phục không?
- **Change frequency:** module này thay đổi thường xuyên hay ít khi đụng tới?

### Ma trận rủi ro định tính

| Tác động | Khả năng thấp | Khả năng cao |
| --- | --- | --- |
| **Thấp** | Review thông thường, test phù hợp | Bổ sung kiểm tra nếu lỗi dễ lặp |
| **Cao** | Cần guardrail, owner và khả năng phục hồi | Ưu tiên review sâu, test nhiều tầng và rollout có kiểm soát |

Đây là công cụ sàng lọc, không phải phép tính rủi ro tuyệt đối. Một lỗi bảo mật có xác suất khó ước lượng nhưng hậu quả lớn vẫn có thể cần ưu tiên cao.

### Ví dụ đánh giá rủi ro cho thao tác hủy

| Rủi ro | Tác động | Dấu hiệu cần tìm |
| --- | --- | --- |
| Người khác hủy đơn không thuộc quyền | Cao | Authorization check, test actor khác chủ đơn |
| Hủy đơn sau khi kho đóng gói | Cao | State transition và dữ liệu warehouse |
| Hai request cùng hủy | Trung bình/cao | Atomic update, version, concurrency test |
| Release tồn kho hai lần | Cao | Idempotency key, unique constraint, event deduplication |
| Event mất sau khi cập nhật đơn | Cao | Transactional outbox hoặc cơ chế phục hồi |
| API client cũ không hiểu trạng thái | Trung bình/cao | Contract compatibility, consumer tests |
| Log chứa thông tin cá nhân | Cao | Logging review, data minimization |

Một risk register nhỏ giúp reviewer tập trung vào những điều có thể gây hậu quả, thay vì yêu cầu tác giả giải thích mọi dòng giống nhau.

## 6. Đọc diff theo câu hỏi, không theo thứ tự dòng đơn thuần

Khi mở diff, hãy đọc theo các nhóm câu hỏi:

1. **Entry point:** thao tác bắt đầu ở đâu? Có đường gọi nào khác không?
2. **Decision logic:** quy tắc nghiệp vụ nằm ở đâu? Có bản sao không?
3. **Data access:** query, transaction, lock, version hoặc constraint có đổi không?
4. **Side effects:** email, event, payment, inventory, audit được gọi khi nào?
5. **Error handling:** lỗi được truyền, chuyển đổi hoặc nuốt ở đâu?
6. **Security:** actor và resource được xác minh ở ranh giới nào?
7. **Compatibility:** response, schema, event và dữ liệu cũ có đổi không?
8. **Observability:** có thể biết điều gì xảy ra sau triển khai không?
9. **Tests:** test nào bảo vệ từng hợp đồng và rủi ro?
10. **Scope:** thay đổi có chạm phần không liên quan không?

### Dấu hiệu cần điều tra

- Thêm một trạng thái enum nhưng không cập nhật mọi consumer.
- Chuyển điều kiện nghiệp vụ vào controller hoặc repository mà không có lý do.
- Dùng giá trị mặc định khi dữ liệu bắt buộc bị thiếu.
- Catch exception rồi trả success.
- Gửi event trước khi transaction commit.
- Thay một query có điều kiện thành đọc rồi ghi không nguyên tử.
- Thêm retry mà không kiểm tra idempotency.
- Bỏ kiểm tra quyền vì “API đã có authentication”.
- Test chỉ kiểm tra status code mà không kiểm tra state và side effect.
- Sửa hàng loạt file format không liên quan, làm khó review.

Một dấu hiệu không tự chứng minh có bug. Nó là điểm cần hỏi, kiểm tra hoặc yêu cầu bằng chứng.

## 7. Chọn kiểm thử theo hợp đồng và rủi ro

Test nên được chọn để trả lời câu hỏi cụ thể. Không nên chỉ yêu cầu “thêm test” mà không nói test cần bảo vệ điều gì.

| Loại test | Câu hỏi được trả lời | Ví dụ trong thao tác hủy |
| --- | --- | --- |
| **Unit** | Quy tắc thuần có đúng không? | PENDING/CONFIRMED được phép, SHIPPED bị từ chối |
| **Service test** | Điều phối và side effect có đúng không? | Không gọi repository update khi actor không có quyền |
| **Integration** | Database/transaction/constraint có đúng không? | Chỉ một transition thắng khi hai request cạnh tranh |
| **Contract** | Producer và consumer hiểu cùng hợp đồng không? | Consumer nhận event OrderCancelled |
| **Security** | Actor có thể thao tác ngoài quyền không? | Người dùng A không hủy được đơn của B |
| **Concurrency** | Cạnh tranh có phá invariant không? | Hủy đồng thời với bắt đầu đóng gói |
| **End-to-end** | Luồng người dùng có hoạt động không? | Mobile gửi hủy và nhận kết quả đúng |
| **Resilience** | Hệ thống phản ứng khi phụ thuộc lỗi thế nào? | Broker tạm ngừng, outbox vẫn lưu ý định |
| **Migration** | Dữ liệu cũ có tương thích không? | Đơn lịch sử vẫn đọc được sau schema change |

Không phải PR nào cũng cần tất cả các tầng. Nhưng nếu thay đổi chạm vào transaction, quyền, event hoặc dữ liệu quan trọng, chỉ có unit test thường chưa đủ.

### 7.1. Test happy path không đủ

Test hủy thành công một đơn PENDING chỉ chứng minh một trường hợp. Cần xem:
- Đơn CONFIRMED chưa đóng gói.
- Đơn CONFIRMED đã đóng gói.
- Đơn SHIPPED.
- Actor không phải chủ đơn.
- Đơn không tồn tại.
- Request trùng.
- Hai request đồng thời.
- Repository lỗi.
- Event publisher lỗi.
- Consumer xử lý event lặp.

### 7.2. Test phải có assertion có ý nghĩa

Một test chỉ gọi service và không kiểm tra kết quả có thể tăng coverage nhưng không bảo vệ hợp đồng.

Ví dụ assertion hữu ích:
- State sau thao tác là CANCELLED.
- Store chỉ nhận một transition.
- Không gọi release khi request bị từ chối.
- Event/outbox record có order ID và correlation ID đúng.
- Error code đúng với trạng thái conflict.
- Retry cùng idempotency key không tạo side effect mới.

### 7.3. Test ở đúng ranh giới

Unit test cho policy không chứng minh câu lệnh SQL có điều kiện. Test repository với database không thay thế test quyền qua API. Contract test không chứng minh consumer đã xử lý event idempotent. Reviewer cần biết **mỗi test đang chứng minh điều gì và không chứng minh điều gì**.

## 8. Ví dụ Java 17: policy và service với ranh giới rõ

Đoạn code sau minh họa cách tách quy tắc hủy khỏi chi tiết lưu trữ. Nó phục vụ việc học review hợp đồng, không phải một triển khai production hoàn chỉnh.

### 8.1. Mô hình và policy

~~~java
import java.util.Objects;

enum OrderStatus {
    PENDING,
    CONFIRMED,
    PACKING,
    SHIPPED,
    CANCELLED
}

record Order(
        String id,
        String ownerId,
        OrderStatus status,
        long version,
        boolean warehouseStartedPacking) {
    Order {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(ownerId, "ownerId");
        Objects.requireNonNull(status, "status");
        if (id.isBlank() || ownerId.isBlank() || version < 0) {
            throw new IllegalArgumentException("invalid order");
        }
    }
}

@FunctionalInterface
interface CancellationPolicy {
    boolean canCancel(Order order);
}

final class DefaultCancellationPolicy
        implements CancellationPolicy {

    @Override
    public boolean canCancel(Order order) {
        Objects.requireNonNull(order, "order");

        if (order.status() == OrderStatus.PENDING) {
            return true;
        }

        return order.status() == OrderStatus.CONFIRMED
                && !order.warehouseStartedPacking();
    }
}
~~~

Policy chỉ trả lời câu hỏi nghiệp vụ dựa trên snapshot được cung cấp. Nó không đọc database, không kiểm tra quyền actor và không thực hiện side effect.

Reviewer cần hỏi: dữ liệu warehouseStartedPacking có đủ mới không? Nếu nó thay đổi đồng thời, policy trên snapshot có thể cũ. Vì vậy service/repository phải có cơ chế bảo vệ transition tại thời điểm ghi.

### 8.2. Hợp đồng repository và service

~~~java
enum CancellationResult {
    CANCELLED,
    ALREADY_CANCELLED,
    STATE_CHANGED
}

interface OrderRepository {
    Order findRequired(String orderId);

    /**
     * Atomic transition contract:
     * - Actor must be authorized for this order.
     * - Current version must equal expectedVersion.
     * - Current status and warehouse condition must still allow cancellation.
     * - State transition and durable cancellation intent are committed together.
     * - Repeating the same logical request must not duplicate the intent.
     */
    CancellationResult cancelIfStillEligible(
            String orderId,
            String actorId,
            long expectedVersion);
}

@FunctionalInterface
interface CancellationAuthorization {
    boolean canCancel(String actorId, Order order);
}

final class OrderCancellationService {
    private final OrderRepository repository;
    private final CancellationPolicy policy;
    private final CancellationAuthorization authorization;

    OrderCancellationService(
            OrderRepository repository,
            CancellationPolicy policy,
            CancellationAuthorization authorization) {
        this.repository = Objects.requireNonNull(repository);
        this.policy = Objects.requireNonNull(policy);
        this.authorization = Objects.requireNonNull(authorization);
    }

    CancellationResult cancel(String actorId, String orderId) {
        if (actorId == null || actorId.isBlank()
                || orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("actor and order are required");
        }

        Order snapshot = repository.findRequired(orderId);

        if (!authorization.canCancel(actorId, snapshot)) {
            throw new SecurityException("not allowed to cancel this order");
        }

        if (!policy.canCancel(snapshot)) {
            throw new IllegalStateException("order cannot be cancelled");
        }

        return repository.cancelIfStillEligible(
                orderId, actorId, snapshot.version());
    }
}
~~~

Phần quan trọng nhất để review là **hợp đồng của cancelIfStillEligible**. Tên phương thức không chứng minh implementation đã nguyên tử. Cần kiểm tra adapter/database thật để biết nó:
- Kiểm tra actor có quyền trên đúng order.
- Kiểm tra version chưa đổi.
- Kiểm tra trạng thái và điều kiện kho tại thời điểm commit.
- Chỉ chuyển trạng thái một lần.
- Ghi cancellation intent bền vững cùng transaction hoặc cơ chế tương đương.
- Trả STATE_CHANGED khi snapshot đã cũ.

Nếu implementation chỉ đọc lại trạng thái rồi update không điều kiện, race condition vẫn có thể xảy ra. Nếu update đơn đã commit nhưng ghi intent thất bại, hệ thống có thể để đơn CANCELLED mà tồn kho không được giải phóng. Đây là lý do reviewer cần đi qua hợp đồng persistence và side effect.

### 8.3. Unit test cho policy

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class DefaultCancellationPolicyTest {
    private final DefaultCancellationPolicy policy =
            new DefaultCancellationPolicy();

    @Test
    void allowsPendingOrder() {
        assertTrue(policy.canCancel(order(
                OrderStatus.PENDING, false)));
    }

    @Test
    void allowsConfirmedOrderBeforePacking() {
        assertTrue(policy.canCancel(order(
                OrderStatus.CONFIRMED, false)));
    }

    @Test
    void rejectsConfirmedOrderAfterPackingStarted() {
        assertFalse(policy.canCancel(order(
                OrderStatus.CONFIRMED, true)));
    }

    @Test
    void rejectsPackingAndShippedOrders() {
        assertFalse(policy.canCancel(order(
                OrderStatus.PACKING, true)));
        assertFalse(policy.canCancel(order(
                OrderStatus.SHIPPED, true)));
    }

    @Test
    void rejectsAlreadyCancelledOrder() {
        assertFalse(policy.canCancel(order(
                OrderStatus.CANCELLED, false)));
    }

    private Order order(OrderStatus status, boolean packing) {
        return new Order(
                "O-100", "U-10", status, 4L, packing);
    }
}
~~~

Test này xác nhận các trường hợp policy đã nêu. Nó chưa chứng minh quyền actor, cập nhật nguyên tử, transaction hoặc event. Reviewer cần yêu cầu test tương ứng ở tầng phù hợp.

## 9. Rà soát service bằng test tương tác có ý nghĩa

Một service test có thể dùng fake repository để kiểm tra điều phối. Ví dụ dưới đây minh họa hai đường quan trọng: actor không có quyền và trạng thái thay đổi trong lúc xử lý.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class OrderCancellationServiceTest {

    @Test
    void rejectsUnauthorizedActorBeforeTransition() {
        FakeOrderRepository repository =
                new FakeOrderRepository(order(
                        OrderStatus.PENDING, false));

        var service = new OrderCancellationService(
                repository,
                new DefaultCancellationPolicy(),
                (actor, order) -> false);

        assertThrows(SecurityException.class,
                () -> service.cancel("U-OTHER", "O-100"));

        assertEquals(0, repository.transitionCalls);
    }

    @Test
    void reportsStateChangeInsteadOfAssumingSuccess() {
        FakeOrderRepository repository =
                new FakeOrderRepository(order(
                        OrderStatus.CONFIRMED, false));
        repository.nextResult = CancellationResult.STATE_CHANGED;

        var service = new OrderCancellationService(
                repository,
                new DefaultCancellationPolicy(),
                (actor, order) -> actor.equals(order.ownerId()));

        assertEquals(
                CancellationResult.STATE_CHANGED,
                service.cancel("U-10", "O-100"));
        assertEquals(1, repository.transitionCalls);
    }

    private static Order order(
            OrderStatus status, boolean packing) {
        return new Order(
                "O-100", "U-10", status, 4L, packing);
    }

    private static final class FakeOrderRepository
            implements OrderRepository {
        private final Order snapshot;
        private int transitionCalls;
        private CancellationResult nextResult =
                CancellationResult.CANCELLED;

        private FakeOrderRepository(Order snapshot) {
            this.snapshot = snapshot;
        }

        @Override
        public Order findRequired(String orderId) {
            return snapshot;
        }

        @Override
        public CancellationResult cancelIfStillEligible(
                String orderId, String actorId, long expectedVersion) {
            transitionCalls++;
            return nextResult;
        }
    }
}
~~~

Fake test chứng minh service:
- Từ chối actor trước khi yêu cầu transition.
- Không giả định thao tác chắc chắn thành công sau khi đã đọc snapshot.
- Trả lại kết quả conflict từ repository.

Nhưng fake repository không thực thi SQL và không chứng minh tính nguyên tử. Cần integration test trên database phù hợp để kiểm tra conditional update, version và transaction.

## 10. Những test bổ sung reviewer nên yêu cầu

Với thay đổi này, một test matrix có thể là:

| Trường hợp | Tầng test | Kỳ vọng |
| --- | --- | --- |
| PENDING, chủ đơn | Unit/service | Cho phép hủy |
| CONFIRMED, kho chưa đóng gói | Unit/service | Cho phép hủy |
| CONFIRMED, kho đã đóng gói | Unit/service | Từ chối |
| PACKING hoặc SHIPPED | Unit/service | Từ chối |
| Actor khác chủ đơn | Service/security | Không thay đổi trạng thái |
| Đơn không tồn tại | API/service | Error contract đúng |
| Hai request hủy đồng thời | Integration/concurrency | Chỉ một transition và một intent |
| Kho bắt đầu đóng gói đồng thời | Integration/concurrency | Một transition hợp lệ thắng theo thứ tự commit |
| Request retry | Integration/contract | Không release reservation hai lần |
| Broker ngừng hoạt động | Resilience | Cancellation intent vẫn được lưu bền vững theo thiết kế |
| Consumer nhận event lặp | Consumer integration | Release idempotent |
| Client cũ nhận response/event | Contract | Tương thích theo version policy |

Không cần nhồi toàn bộ test vào một class. Test nên đặt gần trách nhiệm và ranh giới cần bảo vệ.

### Một câu hỏi review quan trọng

Nếu unit test policy xanh nhưng integration test concurrency thất bại, **có thể merge không?**

Không, nếu concurrency là rủi ro nằm trong hợp đồng của thay đổi. Policy đúng không bù được một transition không nguyên tử.

## 11. Đánh giá security trong review

Review bảo mật nên xem cả actor, action, resource và context.

### Checklist authorization

- Actor đã được xác thực chưa?
- Quyền được kiểm tra trên đúng tài nguyên hay chỉ kiểm tra role chung?
- Có IDOR/BOLA khi caller thay ID tài nguyên không?
- Có đường truy cập khác bỏ qua policy không?
- Job nội bộ hoặc admin có quyền khác và được ghi rõ không?
- Quyền có thể thay đổi giữa lúc đọc và ghi không?
- Error response có làm lộ thông tin không cần thiết không?
- Log có chứa token, thông tin cá nhân hoặc dữ liệu nhạy cảm không?

### Negative test là bắt buộc khi quyền là hợp đồng

Đừng chỉ test actor được phép. Hãy test:
- Actor không phải chủ sở hữu.
- Actor có role nhưng không có quyền trên resource cụ thể.
- Token hết hạn hoặc thiếu scope.
- Tài nguyên thuộc tenant khác.
- Đường gọi nội bộ không có identity hợp lệ.
- Quyền bị thu hồi hoặc thay đổi trong lúc thao tác nếu mô hình cho phép.

Một security scanner PASS không thay thế những test này. Scanner không biết đầy đủ chính sách nghiệp vụ của một order.

## 12. Đánh giá dữ liệu, transaction và concurrency

Một trong những lỗi khó phát hiện nhất là review chỉ đọc code theo luồng tuần tự. Production có nhiều request đồng thời.

### Race condition minh họa

1. Request A đọc đơn CONFIRMED.
2. Request B đọc đơn CONFIRMED.
3. A kiểm tra kho chưa đóng gói.
4. B kiểm tra kho chưa đóng gói.
5. A hủy đơn.
6. B cũng ghi CANCELLED và phát yêu cầu release.
7. Reservation có thể bị giải phóng hai lần.

Nếu code chỉ dùng chuỗi find, check, update không có cơ chế đồng bộ, test tuần tự có thể vẫn xanh.

### Các cơ chế cần xem

- Conditional update theo version/status.
- Optimistic locking.
- Pessimistic locking nếu phù hợp.
- Unique constraint cho logical operation/event.
- Transaction bao gồm state change và outbox intent.
- Idempotency key và deduplication.
- Consumer idempotency.
- Retry có giới hạn, backoff và phân loại lỗi.

Không phải hệ thống nào cũng cần khóa mạnh. Cần chọn cơ chế theo consistency model, tải, database và hậu quả khi hai thao tác cùng thành công.

### Câu hỏi về transaction

- Điểm commit ở đâu?
- Nếu update order thành công nhưng insert outbox thất bại thì sao?
- Nếu outbox có nhưng publish thất bại thì sao?
- Nếu publish thành công nhưng đánh dấu đã gửi thất bại thì sao?
- Consumer nhận lại event có tạo side effect trùng không?
- Có cách đối soát order đã hủy nhưng reservation chưa release không?

Reviewer không cần bắt tác giả xây distributed transaction nếu outbox và idempotency đã giải quyết đúng hợp đồng. Nhưng phải hiểu cách hệ thống phục hồi từ các điểm lỗi.

## 13. Review API và compatibility

Một thay đổi nội bộ có thể tác động tới client qua:
- HTTP status.
- Error code.
- JSON field.
- Enum value.
- Event name/schema.
- Thứ tự hoặc timing của response.
- Semantics của retry.

Ví dụ thêm trạng thái CANCEL_REQUESTED vào response. Client cũ có thể:
- Crash khi parse enum nghiêm ngặt.
- Hiển thị trạng thái không xác định.
- Cho phép người dùng thao tác sai.
- Không cập nhật màn hình vì không biết transition.

### Checklist contract

- Field mới có optional/default phù hợp không?
- Enum có fallback cho client cũ không?
- Breaking change có versioning/deprecation plan không?
- Error code có giữ semantics đã công bố không?
- Consumer nào đang dùng event/API?
- Có contract test với consumer đại diện không?
- Dữ liệu lịch sử thiếu field mới được đọc thế nào?
- Có rollout theo giai đoạn không?

Không thể kết luận tương thích chỉ bằng việc server compile. Cần biết **caller thật đang phụ thuộc vào contract nào**.

## 14. Review observability và khả năng vận hành

Một thay đổi quan trọng cần có cách biết nó hoạt động đúng sau triển khai.

Với cancellation, metric có thể gồm:
- Số yêu cầu hủy theo kết quả.
- Tỷ lệ bị từ chối do trạng thái.
- Tỷ lệ conflict do state changed.
- Số outbox record chờ publish.
- Độ trễ event đến consumer.
- Số lỗi release reservation.
- Số lần xử lý trùng được deduplicate.

Log/trace có thể cần:
- Order ID dạng phù hợp chính sách dữ liệu.
- Correlation/request ID.
- Actor ID ở dạng được phép.
- Transition từ trạng thái nào sang trạng thái nào.
- Kết quả xử lý và mã lỗi.
- Outbox/event ID.

Không log secret, token hoặc toàn bộ dữ liệu cá nhân chỉ để tiện debug.

### Câu hỏi review vận hành

- Khi cancellation rate tăng đột biến, ai nhận alert?
- Có thể lần theo một order từ API tới consumer không?
- Nếu event backlog tăng, có runbook không?
- Có thể replay an toàn không?
- Rollback có để lại dữ liệu nửa chừng không?
- Có feature flag hoặc giới hạn rollout phù hợp không?

Một PR có thể không cần tự tạo dashboard mới nếu dashboard hiện tại đã đáp ứng. Reviewer nên yêu cầu **bằng chứng observability phù hợp**, không mặc định mỗi PR phải thêm một hệ thống mới.

## 15. Viết review comment có thể hành động

Một comment tốt nêu:
1. Vị trí hoặc hành vi cụ thể.
2. Rủi ro hoặc hợp đồng liên quan.
3. Tình huống có thể xảy ra.
4. Bằng chứng hoặc thay đổi cần thiết để giải quyết.

### Ví dụ comment

**Blocker — race condition**

> Đoạn này đọc trạng thái rồi cập nhật không có điều kiện theo version. Nếu request hủy và worker bắt đầu đóng gói chạy đồng thời, cả hai có thể cùng vượt qua kiểm tra snapshot. Cần bảo vệ transition tại thời điểm ghi bằng conditional update/locking phù hợp và có integration test cho hai thao tác cạnh tranh.

**Blocker — authorization**

> Kiểm tra actor đã đăng nhập chưa chưa bảo đảm họ có quyền hủy orderId này. Cần xác nhận quyền trên tài nguyên cụ thể và thêm test khi actor là người khác chủ đơn.

**Question — business contract**

> Khi đơn đã thanh toán nhưng chưa đóng gói, thao tác này chỉ giải phóng authorization hay cần refund? Hợp đồng hiện tại chưa nêu, nên cần domain/product xác nhận trước khi quyết định side effect.

**Suggestion — readability**

> Có thể đặt điều kiện trạng thái vào CancellationPolicy để unit test các chuyển trạng thái độc lập. Đây là đề xuất maintainability; nếu có lý do giữ trong service, hãy giải thích ở PR.

**Nit — style**

> Tên biến này có thể cụ thể hơn để phân biệt snapshot với trạng thái sau transition.

### Tránh comment không thể hành động

Không hữu ích:
- “Code xấu.”
- “Thêm test đi.”
- “Cần clean architecture.”
- “Cách này không scale.”
- “Có thể lỗi concurrency.”

Tốt hơn:
- Chỉ rõ tình huống và hậu quả.
- Nêu test hoặc bằng chứng cần bổ sung.
- Phân biệt yêu cầu bắt buộc với đề xuất.
- Đưa ra một hoặc hai hướng giải quyết khả thi mà không áp đặt implementation khi chưa đủ dữ liệu.

## 16. Quyết định review: approve, request changes hay cần thảo luận?

### Approve

Phù hợp khi:
- Hợp đồng đã rõ.
- Rủi ro quan trọng được kiểm soát.
- Test và bằng chứng đáp ứng tiêu chí.
- Không còn blocker.
- Owner/consumer liên quan đã tham gia khi cần.

Approve không có nghĩa reviewer bảo đảm không còn bug. Nó xác nhận thay đổi đạt tiêu chí review trong phạm vi và bằng chứng đã xem.

### Request changes

Phù hợp khi:
- Có vi phạm hợp đồng.
- Thiếu kiểm tra quyền.
- Có nguy cơ sai dữ liệu hoặc side effect trùng.
- Test bắt buộc thất bại hoặc thiếu bằng chứng cần thiết.
- API/schema bị phá tương thích.
- Có rủi ro cao chưa có biện pháp kiểm soát.

Request changes nên chỉ rõ điều kiện cần đạt để có thể review lại.

### Needs discussion / clarification

Phù hợp khi:
- Yêu cầu nghiệp vụ chưa rõ.
- Có nhiều phương án trade-off và cần người có thẩm quyền quyết định.
- Phạm vi vượt ranh giới owner.
- Metric hoặc benchmark chưa đủ dữ liệu.
- Chưa biết consumer nào bị ảnh hưởng.

Không nên biến câu hỏi nghiệp vụ thành blocker kỹ thuật tự suy đoán. Hãy nêu rõ ai cần xác nhận.

## 17. Mẫu review worksheet dùng cho một pull request

Có thể copy mẫu này vào ghi chú review:

~~~text
PR / CHANGE:
Mục tiêu:
Tác giả:
Module / owner:
Caller và consumer bị ảnh hưởng:

1. CONTRACT
- Preconditions:
- Postconditions:
- Invariants:
- Error behavior:
- Side effects:
- Compatibility:

2. RISK
- Failure modes:
- Impact:
- Likelihood:
- Detectability:
- Blast radius:
- Recovery / rollback:

3. EVIDENCE
- Unit tests:
- Integration / DB tests:
- Contract tests:
- Security tests:
- Concurrency tests:
- Performance / load evidence:
- Operational checks:

4. OWNERSHIP
- Domain decision owner:
- Code/service owner:
- Consumer teams consulted:
- Security/platform/SRE consulted:

5. REVIEW FINDINGS
- Blockers:
- Questions:
- Suggestions:
- Accepted limitations:

6. DECISION
- APPROVE / REQUEST CHANGES / NEEDS DISCUSSION
- Điều kiện còn thiếu:
- Người chịu trách nhiệm:
- Bằng chứng cần bổ sung:
~~~

Không phải PR nào cũng cần điền mọi trường. Với sửa đổi nhỏ, worksheet có thể rút gọn. Với thay đổi payment, quyền, migration hoặc event contract, những trường tương ứng cần được ghi cụ thể.

## 18. Walkthrough: review một diff giả định

Giả sử tác giả gửi đoạn code:

~~~java
void cancel(String orderId) {
    Order order = repository.findRequired(orderId);

    if (order.status() == OrderStatus.PENDING
            || order.status() == OrderStatus.CONFIRMED) {
        repository.updateStatus(orderId, OrderStatus.CANCELLED);
        inventory.release(orderId);
        events.publish(new OrderCancelled(orderId));
    }
}
~~~

Đọc nhanh có thể thấy code ngắn, dễ hiểu và có đủ ba bước. Nhưng review theo hợp đồng sẽ phát hiện nhiều câu hỏi.

### Vấn đề 1 — Không có authorization

Phương thức không nhận actor và không kiểm tra quyền trên đơn.

**Rủi ro:** người gọi có thể hủy đơn của người khác nếu tầng trước không bảo vệ hoặc có đường gọi nội bộ khác.

**Bằng chứng cần:** kiểm tra quyền ở ranh giới tin cậy và test actor không có quyền.

### Vấn đề 2 — Không kiểm tra trạng thái kho

CONFIRMED được phép hủy vô điều kiện, dù kho có thể đã bắt đầu đóng gói.

**Rủi ro:** order state và warehouse state lệch nhau.

**Bằng chứng cần:** hợp đồng trạng thái và kiểm tra condition tại thời điểm transition.

### Vấn đề 3 — Không bảo vệ concurrency

Hai request có thể cùng đọc PENDING và cùng cập nhật.

**Rủi ro:** side effect được thực hiện nhiều lần.

**Bằng chứng cần:** atomic transition/version/constraint và concurrency test.

### Vấn đề 4 — Side effect không có cơ chế phục hồi rõ

Order được cập nhật, sau đó inventory release, rồi publish event. Nếu bước thứ hai hoặc thứ ba lỗi thì sao?

**Rủi ro:** trạng thái đã đổi nhưng tồn kho hoặc consumer không được cập nhật.

**Bằng chứng cần:** transaction/outbox, idempotency và retry/reconciliation.

### Vấn đề 5 — Không có error contract

Nếu trạng thái không cho phép hủy, method chỉ im lặng không làm gì.

**Rủi ro:** API có thể trả thành công dù không có transition.

**Bằng chứng cần:** kết quả rõ như CANCELLED, ALREADY_CANCELLED, STATE_CHANGED hoặc business error.

### Kết luận review

Đây chưa phải thay đổi có thể approve chỉ vì happy path hoạt động. Các vấn đề authorization, state transition đồng thời và phục hồi side effect là blocker nếu nằm trong hợp đồng đã xác nhận. Cần làm rõ thêm payment/refund nếu đơn có thể đã thanh toán.

## 19. Phân biệt blocker với phần cải thiện có thể tách riêng

Một review dễ bị kéo dài nếu mọi đề xuất đều được coi là bắt buộc.

| Nhận xét | Phân loại thường phù hợp | Lý do |
| --- | --- | --- |
| Thiếu authorization trên resource | Blocker | Có thể cho phép thao tác trái quyền |
| Update trạng thái không nguyên tử | Blocker khi concurrency thuộc hợp đồng | Có thể phá invariant |
| Event có thể mất sau commit | Blocker nếu event là side effect bắt buộc | Có thể làm các service lệch trạng thái |
| Tên biến chưa rõ | Suggestion hoặc nit | Không nhất thiết làm sai hợp đồng |
| Có thể trích policy riêng | Suggestion nếu maintainability chưa bị ảnh hưởng nghiêm trọng | Có thể cải thiện testability |
| Formatter chưa chạy | Theo quality gate dự án | Dễ tự động hóa |
| Benchmark chưa có cho thay đổi không chạm hot path | Thường không cần | Không liên quan trực tiếp rủi ro |
| Thay đổi public enum thiếu compatibility plan | Blocker khi có consumer cũ | Có thể phá client |

Phân loại phụ thuộc bối cảnh. Một tên mơ hồ trong code bảo mật có thể làm tăng nguy cơ hiểu sai; một đề xuất style trong code generated có thể không đáng chặn.

## 20. Khi review phát hiện yêu cầu chưa rõ

Reviewer không nên tự chọn một hành vi nghiệp vụ chỉ vì implementation hiện tại dễ viết.

Ví dụ:
- Nếu đơn đã thanh toán, có refund không?
- Nếu kho bắt đầu đóng gói trong cùng millisecond, ai thắng?
- Nếu người dùng retry sau timeout, trả kết quả nào?
- Nếu một consumer cũ không hiểu event mới, có giữ version cũ không?

Cách xử lý:
1. Viết câu hỏi cụ thể và tình huống minh họa.
2. Xác định người có thẩm quyền nghiệp vụ hoặc contract.
3. Tạm dừng phần quyết định phụ thuộc vào câu trả lời.
4. Có thể tiếp tục review các phần độc lập.
5. Ghi quyết định sau khi được xác nhận.
6. Cập nhật acceptance criteria và test.

Đừng dùng một comment “please clarify” chung chung. Nêu lựa chọn và hậu quả để người quyết định trả lời nhanh hơn.

## 21. Review thay đổi nhỏ và thay đổi lớn

Mức review cần tương xứng với phạm vi và hậu quả.

### Thay đổi nhỏ

Ví dụ: sửa tên một biến local trong hàm thuần, không đổi logic.

Có thể tập trung:
- Ý nghĩa tên.
- Diff có giới hạn.
- Test/formatter hiện có.
- Không có thay đổi ngoài ý muốn.

### Thay đổi vừa

Ví dụ: thêm điều kiện trạng thái trong domain service.

Cần:
- Hợp đồng trước/sau.
- Trường hợp biên và lỗi.
- Unit/service tests.
- Caller bị ảnh hưởng.
- Error behavior và side effect.

### Thay đổi lớn hoặc rủi ro cao

Ví dụ: thay schema event, transaction thanh toán hoặc authorization.

Cần thêm:
- Owner và consumer review.
- Contract/integration/concurrency/security tests.
- Migration và compatibility plan.
- Observability, rollout và rollback.
- ADR hoặc decision record khi trade-off có ảnh hưởng dài hạn.

Không nên đánh giá chất lượng review bằng số comment. Một PR lớn có thể cần nhiều vòng trao đổi; một PR nhỏ có thể chỉ cần một xác nhận chính xác.

## 22. Cách review test: test đang bảo vệ điều gì?

Khi đọc test diff, đừng chỉ đếm số test. Hãy lập ánh xạ từ rủi ro tới test.

| Rủi ro/hợp đồng | Test bảo vệ | Khoảng trống còn lại |
| --- | --- | --- |
| Policy cho phép đúng trạng thái | Unit test policy | Chưa chứng minh trạng thái DB mới nhất |
| Actor chỉ thao tác trên đơn được phép | Service/security test | Cần kiểm tra mọi entry point |
| Chỉ một transition thành công | Integration concurrency test | Cần kiểm tra DB/transaction thực |
| Event không mất sau commit | Outbox integration test | Cần quan sát publisher và retry |
| Consumer không xử lý lặp | Consumer idempotency test | Cần kiểm tra dedupe retention |
| Client cũ tương thích | Contract test | Cần biết phiên bản client đang hoạt động |

Nếu một rủi ro quan trọng không có test, reviewer nên hỏi:
- Có biện pháp khác bảo vệ không?
- Test có thể đặt ở tầng nào?
- Có thể mô phỏng tình huống một cách ổn định không?
- Ai chịu trách nhiệm bổ sung?
- Có thể triển khai an toàn khi chưa có test không?

Không phải mọi khoảng trống đều buộc phải viết test mới ngay trong cùng PR, nhưng nếu rủi ro không được kiểm soát thì không nên giả định nó đã được giải quyết.

## 23. Review migration và dữ liệu lịch sử

Nếu thay đổi thêm trường hoặc đổi trạng thái, cần xem dữ liệu hiện tại:
- Record cũ có giá trị mặc định nào?
- Null có ý nghĩa gì?
- Migration chạy một lần hay nhiều lần?
- Có thể chạy khi ứng dụng cũ và mới cùng hoạt động không?
- Có cần backfill không?
- Có thể rollback schema sau khi dữ liệu mới được ghi không?
- Consumer/report có đọc cả dữ liệu cũ lẫn mới không?
- Đối soát nào phát hiện bản ghi sai?

### Expand-and-contract là một chiến lược có thể dùng

1. Mở rộng schema để hỗ trợ cả dạng cũ và mới.
2. Deploy code đọc được cả hai và ghi theo chiến lược chuyển tiếp.
3. Backfill/verify dữ liệu.
4. Chuyển consumer và producer theo giai đoạn.
5. Quan sát việc sử dụng trường cũ.
6. Xóa trường cũ khi không còn consumer và đã qua mốc deprecation.

Không phải migration nào cũng cần nhiều giai đoạn. Nhưng nếu deployment không nguyên tử và nhiều phiên bản chạy đồng thời, reviewer cần kiểm tra compatibility trong thời gian chuyển đổi.

## 24. Review hiệu năng theo đúng giả thuyết

Nếu PR ghi “optimize query”, hãy yêu cầu biết:
- Điểm nghẽn ban đầu ở đâu?
- Baseline được đo thế nào?
- Workload đại diện gồm những trường hợp nào?
- Số query, execution plan, p95/p99 và tài nguyên thay đổi ra sao?
- Có đánh đổi giữa memory, DB CPU và network không?
- Có ảnh hưởng tới thứ tự hoặc tính đầy đủ dữ liệu không?

### Ví dụ: thay N+1 bằng join

Một thay đổi có thể giảm số query từ 101 xuống 1, nhưng query join có thể tạo hàng nghìn dòng trùng do quan hệ one-to-many và làm tăng memory.

Reviewer cần xem:
- Cardinality của join.
- Index và execution plan.
- Phân bố dữ liệu lớn.
- Pagination và thứ tự.
- Duplicate handling.
- p99 và resource saturation.

**Ít query hơn không tự động có nghĩa nhanh hơn hoặc rẻ hơn.** Cần đo tổng chi phí ở cấp độ mục tiêu.

## 25. Review khả năng đọc và maintainability

Một thay đổi có thể đúng hiện tại nhưng khiến lần sửa tiếp theo khó hơn.

Hãy hỏi:
- Tên class/method có phản ánh trách nhiệm?
- Quy tắc nghiệp vụ có một nơi sở hữu rõ?
- Dependency có được truyền qua ranh giới dễ kiểm thử?
- Có abstraction mới vì nhu cầu thật hay vì dự đoán?
- Có trạng thái mutable dùng chung khó suy luận?
- Error behavior có bị giấu trong null/default?
- Test có mô tả hợp đồng hay khóa chặt implementation?
- Có comment giải thích lý do thay vì nhắc lại code?
- Một người mới có thể tìm nơi sửa quy tắc không?

Review maintainability nên chỉ ra **chi phí thay đổi cụ thể**, không chỉ nói “code chưa clean”.

## 26. Mẫu PR description giúp review hiệu quả

Một PR tốt giúp reviewer hiểu mục tiêu và bằng chứng trước khi đọc code.

~~~text
## Mục tiêu
Cho phép chủ đơn hủy đơn CONFIRMED khi kho chưa bắt đầu đóng gói.

## Hợp đồng
- PENDING: được hủy.
- CONFIRMED và chưa PACKING: được hủy.
- PACKING/SHIPPED: từ chối.
- Actor phải có quyền trên đơn.
- Transition chỉ thành công một lần.
- Cancellation intent được lưu bền vững cùng thay đổi trạng thái.

## Phạm vi
- Order domain policy
- Atomic repository transition
- API error mapping
- Test và event contract liên quan

## Rủi ro đã xem xét
- Authorization
- Request đồng thời
- Retry/idempotency
- Event delivery
- Consumer compatibility

## Bằng chứng
- Unit tests: policy và trường hợp biên
- Service tests: quyền và điều phối
- Integration tests: conditional update/concurrency
- Contract tests: event và API response
- Resilience tests: broker unavailable
- [Ghi kết quả thực tế của các lệnh CI]

## Triển khai
- [Feature flag / rollout nếu cần]
- [Dashboard / alert]
- [Rollback hoặc forward-fix]

## Giới hạn còn lại
- [Nêu phần chưa kiểm chứng và owner]
~~~

Không ghi test hoặc benchmark là PASS nếu chưa chạy. PR description phải phân biệt **đã xác nhận**, **chưa xác nhận** và **được chấp nhận có điều kiện**.

## 27. Những lỗi phổ biến khi review

### 27.1. Chỉ review từng dòng

Reviewer bỏ lỡ luồng tổng thể, caller và side effect. Hãy bắt đầu bằng mục tiêu, contract và bản đồ phụ thuộc.

### 27.2. Chỉ kiểm tra happy path

Test một trường hợp thành công không bảo vệ quyền, lỗi, retry và cạnh tranh. Hãy lập test matrix theo rủi ro.

### 27.3. Dùng test xanh để thay thế domain confirmation

Test có thể lặp lại một giả định sai. Quy tắc chưa rõ phải được xác nhận bởi người có thẩm quyền nghiệp vụ.

### 27.4. Bỏ qua concurrency vì “ít khi xảy ra”

Hai request có thể đến cùng lúc trong hệ thống thực. Nếu invariant quan trọng, cần thiết kế và test đúng cơ chế đồng bộ.

### 27.5. Tin vào tên phương thức

Một method tên atomicUpdate không tự chứng minh nó nguyên tử. Cần xem implementation, transaction và database semantics.

### 27.6. Yêu cầu mọi test ở một tầng

Unit test không thể chứng minh database; E2E test không phải cách hiệu quả để kiểm tra mọi quy tắc thuần. Chọn tầng theo câu hỏi.

### 27.7. Review style thay vì rủi ro

Formatter và linter nên tự động hóa những điều cơ học. Reviewer dành thời gian cho hợp đồng, quyền, dữ liệu, phụ thuộc và khả năng phục hồi.

### 27.8. Đưa mọi suggestion thành blocker

Điều này kéo dài PR và làm mất trọng tâm. Phân biệt lỗi phải sửa với đề xuất cải thiện.

### 27.9. Không kiểm tra compatibility

Server mới có thể làm client cũ hỏng dù unit test server xanh. Xác định consumer và contract.

### 27.10. Không ghi giới hạn còn lại

Một review approve nhưng không ghi khoảng trống có thể khiến người vận hành hiểu rằng mọi rủi ro đã được xử lý. Ghi rõ phần chưa kiểm chứng và owner.

## 28. Bài tập thực hành

### Bài tập 1 — Viết hợp đồng cho thay đổi

Một API cho phép người dùng đổi địa chỉ giao hàng sau khi đặt đơn. Hãy xác định:
- Preconditions.
- Postconditions.
- Invariants.
- Error behavior.
- Side effects.
- Các trạng thái đơn được phép thay đổi.
- Những điều cần xác nhận với product/warehouse.

*Gợi ý:* Địa chỉ có thể thay đổi sau khi kho đã đóng gói không? Phí vận chuyển và thuế có cần tính lại không?

### Bài tập 2 — Review diff có race condition

Một phương thức có logic:

~~~java
Order order = repository.findRequired(id);
if (order.status() == OrderStatus.PENDING) {
    repository.updateStatus(id, OrderStatus.CANCELLED);
}
~~~

Hãy viết một blocker review comment nêu:
- Kịch bản hai request đồng thời.
- Invariant có thể bị phá.
- Cơ chế cần xem xét.
- Test cần bổ sung.

*Gợi ý:* Đọc rồi ghi không nguyên tử; xem conditional update/version/locking và integration test.

### Bài tập 3 — Tìm khoảng trống authorization

Một endpoint yêu cầu người dùng đăng nhập, sau đó lấy order theo ID và trả dữ liệu. Hãy xác định vì sao authentication chưa đủ. Viết test cho actor khác chủ đơn và một đường gọi nội bộ.

### Bài tập 4 — Side effect và event

Code cập nhật trạng thái đơn rồi publish event trực tiếp. Broker có thể tạm ngừng. Hãy mô tả các trạng thái lỗi có thể xảy ra và đề xuất cách bảo đảm ý định được lưu bền vững, publish có thể retry và consumer xử lý lặp an toàn.

### Bài tập 5 — Chọn tầng test

Một PR:
- Thay điều kiện tính phí.
- Thêm cột database.
- Đổi event schema.
- Tăng số worker xử lý nền.

Hãy lập bảng test theo từng thay đổi và giải thích câu hỏi mà mỗi tầng test trả lời. Chỉ ra phần nào không thể chứng minh bằng unit test.

### Bài tập 6 — Phân loại review comment

Phân loại các nhận xét sau thành blocker, question, suggestion hoặc nit trong một bối cảnh phù hợp:
1. “Actor chưa được kiểm tra quyền trên order.”
2. “Tên biến hơi ngắn.”
3. “Nếu payment đã capture thì hủy có refund không?”
4. “Update status không có điều kiện theo version.”
5. “Có thể trích policy để test độc lập.”
6. “Event schema đổi nhưng không có consumer compatibility plan.”

Giải thích vì sao mỗi nhận xét có mức độ đó.

### Bài tập 7 — Review PR description

Một PR ghi:
> “Fix cancel order. Tests pass.”

Hãy viết lại mô tả gồm mục tiêu, contract, phạm vi, rủi ro, bằng chứng test, rollout và giới hạn còn lại. Không tự khẳng định test đã chạy nếu đề bài không cung cấp bằng chứng.

### Bài tập 8 — Thực hiện review có cấu trúc

Chọn một thay đổi trong dự án học tập hoặc một PR mẫu. Điền review worksheet ở mục 17. Tối thiểu phải có:
- Một contract.
- Ba rủi ro.
- Một test matrix.
- Một review comment có thể hành động.
- Một kết luận approve/request changes/needs discussion và lý do.

### Bài tập 9 — Review migration

Một PR đổi trạng thái đơn từ chuỗi tự do sang enum. Hãy xem dữ liệu lịch sử, giá trị không biết, client cũ, migration, rollback và cách deploy khi hai phiên bản ứng dụng cùng chạy.

### Bài tập 10 — Review theo mức rủi ro

So sánh:
- PR sửa comment trong một helper.
- PR đổi quyền xem dữ liệu khách hàng.
- PR thay cách tính tiền.
- PR đổi connection pool và retry.

Hãy xác định ai cần review, test nào bắt buộc, gate nào áp dụng và bằng chứng nào đủ để quyết định.

## 29. Tự kiểm tra kiến thức

**Câu 1.** Vì sao review nên bắt đầu từ hợp đồng thay vì đọc diff theo thứ tự file?

*Trả lời:* Hợp đồng xác định hành vi cần bảo vệ. Khi hiểu contract, reviewer có thể tìm đúng caller, side effect, ranh giới và test thay vì chỉ nhận xét cú pháp.

**Câu 2.** Precondition và postcondition khác nhau thế nào?

*Trả lời:* Precondition là điều kiện cần đúng trước thao tác; postcondition là kết quả phải đúng sau thao tác thành công.

**Câu 3.** Vì sao test happy path không đủ cho thao tác hủy đơn?

*Trả lời:* Nó không kiểm tra quyền, trạng thái không hợp lệ, request lặp, lỗi phụ thuộc và cạnh tranh đồng thời.

**Câu 4.** Unit test policy xanh có chứng minh database transition nguyên tử?

*Trả lời:* Không. Cần integration/concurrency test và kiểm tra implementation persistence thực.

**Câu 5.** Authentication có đồng nghĩa authorization không?

*Trả lời:* Không. Authentication xác định actor; authorization xác định actor có được thực hiện hành động trên tài nguyên cụ thể hay không.

**Câu 6.** Khi nào cần contract test?

*Trả lời:* Khi thay đổi ảnh hưởng hợp đồng giữa producer/consumer, API, event hoặc schema mà các thành phần khác phụ thuộc.

**Câu 7.** Một reviewer có nên yêu cầu mọi suggestion thành blocker?

*Trả lời:* Không. Cần phân biệt vi phạm hợp đồng/rủi ro phải sửa với cải thiện có thể tách riêng.

**Câu 8.** Nếu update order thành công nhưng publish event thất bại thì sao?

*Trả lời:* Hệ thống cần cơ chế phục hồi đã thiết kế, chẳng hạn lưu outbox intent cùng transaction và retry publish; consumer cũng cần xử lý lặp an toàn.

**Câu 9.** Review approve có nghĩa không còn bug?

*Trả lời:* Không. Nó xác nhận thay đổi đáp ứng tiêu chí và bằng chứng đã xem trong phạm vi review; các giới hạn cần được ghi rõ.

**Câu 10.** Một review comment tốt cần có gì?

*Trả lời:* Hành vi/vị trí cụ thể, rủi ro, tình huống có thể xảy ra và bằng chứng hoặc hành động cần thiết để giải quyết.

## Ghi nhớ

**Rà soát một thay đổi bằng hợp đồng, rủi ro và kiểm thử** là cách chuyển code review từ nhận xét bề mặt thành một hoạt động bảo vệ chất lượng. Trước hết hãy hiểu mục tiêu, actor, precondition, postcondition, invariant, error behavior và side effect. Tiếp theo lần theo caller, dữ liệu, consumer và owner; đánh giá tác động, khả năng xảy ra, phát hiện và phục hồi. Chọn test theo ranh giới cần chứng minh, phân biệt điều unit test xác nhận với điều chỉ integration, contract, security hoặc concurrency test mới kiểm tra được. Review comment phải cụ thể và có thể hành động; kết luận approve hay request changes phải dựa trên bằng chứng, đồng thời ghi rõ giới hạn còn lại. Cách làm này giúp nhóm bảo vệ phần mềm **đáng tin cậy, dễ hiểu và dễ thay đổi**, kể cả khi nhiều người cùng tham gia vào một thay đổi.
