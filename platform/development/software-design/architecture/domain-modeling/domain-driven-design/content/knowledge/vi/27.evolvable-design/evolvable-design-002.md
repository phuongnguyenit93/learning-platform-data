# Phân biệt truy vấn không gây tác dụng phụ với lệnh thay đổi trạng thái

Trong Domain-Driven Design (DDD), một ứng dụng vừa cung cấp thông tin để người dùng ra quyết định, vừa thực hiện những hành động làm thay đổi trạng thái nghiệp vụ. Nhân viên có thể xem chi tiết đơn hàng, tìm các đơn đang chờ xử lý, xác nhận một đơn hoặc đánh dấu thông báo đã đọc. Những thao tác này có thể xuất hiện cạnh nhau trên cùng giao diện, nhưng có ngữ nghĩa khác nhau đối với hệ thống.

**Query (truy vấn)** yêu cầu hệ thống cung cấp thông tin và không làm thay đổi trạng thái nghiệp vụ. **Command (lệnh)** diễn đạt ý định yêu cầu hệ thống thực hiện một hành động có thể làm thay đổi trạng thái hoặc tạo tác động nghiệp vụ. Phân biệt rõ hai loại giúp API dễ hiểu, cache và retry an toàn hơn, đồng thời giữ các quy tắc thay đổi trạng thái ở đúng nơi.

Một query vẫn có thể tạo tác động kỹ thuật như ghi log, cập nhật cache hoặc metric. Điều quan trọng là nó không âm thầm thay đổi sự thật nghiệp vụ mà caller đang đọc. Nếu thao tác “xem thông báo” làm trạng thái chuyển từ chưa đọc sang đã đọc, đó là một hành động nghiệp vụ riêng và nên được biểu diễn như command `MarkNotificationAsRead`.

## Sau bài học này

Bạn có thể:

- Phân biệt query, command và event theo ý nghĩa của chúng.
- Nhận diện side effect nghiệp vụ ẩn trong thao tác tưởng như chỉ đọc.
- Thiết kế query handler trả dữ liệu mà không sửa domain state.
- Thiết kế command handler tải aggregate, gọi hành vi miền và lưu thay đổi.
- Đặt logic đọc, ghi và tác động phụ ở đúng layer.
- Hiểu liên hệ giữa query/command với HTTP method, cache, retry và idempotency.
- Chọn mức CQRS phù hợp mà không triển khai thêm hạ tầng không cần thiết.
- Xử lý audit truy cập, lượt xem, thông báo đã đọc và các trường hợp đọc có ghi nhận.
- Kiểm thử rằng query không gây thay đổi nghiệp vụ và command tuân thủ invariant.

## 1. Query và Command trả lời hai câu hỏi khác nhau

Query trả lời: “Thông tin hiện tại là gì?” hoặc “Những đối tượng nào thỏa điều kiện này?”. Ví dụ:

- Lấy chi tiết đơn hàng theo mã.
- Tìm các đơn đang chờ thanh toán.
- Xem số dư tài khoản.
- Tra cứu lịch sử giao dịch.
- Tính trước một báo giá để hiển thị.

Command trả lời: “Tôi muốn hệ thống thực hiện điều gì?”. Ví dụ:

- Xác nhận đơn hàng.
- Hủy đơn.
- Giữ hàng trong kho.
- Ghi nhận thanh toán.
- Đánh dấu thông báo đã đọc.
- Đăng ký một lượt tham gia.

| Khía cạnh | Query | Command |
| --- | --- | --- |
| Ý định | Đọc thông tin | Yêu cầu hành động |
| Thay đổi trạng thái nghiệp vụ | Không | Có thể có; phải qua quy tắc miền |
| Kết quả | Dữ liệu/projection | Kết quả thực hiện hoặc trạng thái xử lý |
| Tác động thường gặp | Đọc database, cache, metrics, access log | Thay đổi aggregate, ghi event, tạo tác vụ |
| Cache | Thường có thể cache nếu chính sách cho phép | Không nên cache như một response đọc thông thường |
| Retry | Thường an toàn về mặt tác động nghiệp vụ | Cần xem xét idempotency và tác động đã xảy ra |
| Ví dụ | `GetOrderDetails` | `ConfirmOrder` |

### Query không phải là một method có chữ get

Tên method không quyết định ngữ nghĩa. Một method tên `getAndMarkAsRead()` vừa đọc vừa thay đổi trạng thái. Một endpoint `GET /notifications/{id}` mà âm thầm đánh dấu thông báo đã đọc cũng đang làm thay đổi nghiệp vụ dù dùng HTTP GET.

Ngược lại, command không nhất thiết phải có tên bắt đầu bằng `create`, `update` hoặc `delete`. `ApproveRefund`, `ReserveSeat`, `PublishArticle` và `MarkNotificationAsRead` diễn đạt ý định nghiệp vụ rõ ràng hơn một tên CRUD chung.

## 2. Side effect là gì?

Side effect (tác dụng phụ) là thay đổi hoặc tác động xảy ra ngoài giá trị mà một biểu thức/hàm trả về. Trong thiết kế ứng dụng nghiệp vụ, cần phân biệt side effect kỹ thuật và side effect nghiệp vụ.

**Side effect nghiệp vụ** làm thay đổi sự thật hoặc trạng thái mà domain quan tâm:

- Chuyển đơn từ ACCEPTED sang CONFIRMED.
- Giảm số lượng khả dụng hoặc tạo reservation.
- Đánh dấu thông báo đã đọc.
- Ghi nhận người dùng đã chấp thuận điều khoản.
- Tạo lượt sử dụng coupon.
- Ghi nhận một khoản thanh toán.

**Side effect kỹ thuật/vận hành** hỗ trợ hệ thống hoạt động:

- Ghi access log hoặc diagnostic log.
- Tăng metric phục vụ quan sát.
- Đọc/ghi cache.
- Ghi trace hoặc telemetry.
- Cập nhật thống kê truy cập không có ý nghĩa quyết định nghiệp vụ.

Ranh giới không phải lúc nào cũng tuyệt đối. Ví dụ, lượt xem bài viết có thể chỉ là metric phân tích, nhưng trong hệ thống tính phí theo lượt xem hoặc xếp hạng dựa trên lượt xem, nó có thể trở thành dữ liệu nghiệp vụ. Cần hỏi: “Nếu tác động này không xảy ra, nghiệp vụ có cho rằng một điều gì đó đã không được thực hiện không?”

### Query có thể có tác động kỹ thuật

Một query có thể ghi log truy cập để bảo mật, tăng metric hoặc làm nóng cache. Điều đó không tự động biến nó thành command. Tuy nhiên, các tác động kỹ thuật này phải được kiểm soát để query vẫn an toàn khi cache, retry, prefetch hoặc gọi lặp.

Nếu việc ghi nhận truy cập là một yêu cầu nghiệp vụ có hậu quả như tính phí, cấp điểm, tăng lượt sử dụng hoặc thay đổi quyền lợi, hãy mô hình hóa nó thành command riêng hoặc một bước có chủ đích.

## 3. Vì sao query nên không thay đổi trạng thái nghiệp vụ?

Một query thuần về mặt nghiệp vụ có nhiều lợi ích.

### Có thể gọi lặp mà không tạo thêm tác động nghiệp vụ

UI có thể tải lại trang, trình duyệt có thể retry request, proxy có thể prefetch hoặc người dùng có thể mở cùng màn hình nhiều lần. Nếu query chỉ đọc, các lần gọi này không vô tình xác nhận đơn, tiêu thụ coupon hoặc thay đổi trạng thái thông báo.

### Dễ cache

Query có thể được cache trong thời gian phù hợp vì việc trả lại dữ liệu đã đọc không làm mất một hành động cần thực hiện. Cache vẫn cần chính sách freshness, quyền truy cập và invalidation, nhưng ngữ nghĩa đọc giúp việc đó rõ ràng hơn.

### Dễ scale và tối ưu riêng

Query có thể dùng projection, index, replica hoặc read model phù hợp với màn hình. Nó không nhất thiết phải tải toàn bộ aggregate để hiển thị một vài trường.

### Dễ kiểm thử

Có thể xác nhận query trả dữ liệu đúng và không gọi repository ghi hoặc hành vi làm thay đổi aggregate. Điều này giúp phát hiện side effect vô tình bị thêm vào trong quá trình phát triển.

### Giảm coupling giữa giao diện và vòng đời domain

Giao diện có thể đọc dữ liệu qua DTO/projection. Nó không cần biết aggregate được lưu như thế nào hoặc phải gọi những hành vi nào để lấy thông tin.

## 4. Command không chỉ là câu lệnh SQL ghi dữ liệu

Command thể hiện một ý định nghiệp vụ. Nó không nên chỉ là một yêu cầu cập nhật field tùy ý.

Thay vì:

~~~java
updateOrderStatus(orderId, "CONFIRMED");
~~~

hãy dùng:

~~~java
confirmOrder(new ConfirmOrder(orderId, actorId));
~~~

Application Service tải aggregate và gọi hành vi miền:

~~~java
public void handle(ConfirmOrder command) {
    transactions.required(() -> {
        Order order = orders.findById(command.orderId())
            .orElseThrow(() -> new OrderNotFoundException(command.orderId()));

        accessPolicy.ensureCanConfirm(command.actorId(), order);
        order.confirm(clock.instant());
        orders.save(order);
    });
}
~~~

Ví dụ lược giản constructor và event/outbox. `Order.confirm()` phải kiểm tra invariant như trạng thái hiện tại, điều kiện dòng hàng và các quy tắc khác. Application Service điều phối, còn aggregate quyết định hành vi có hợp lệ hay không.

### Command có thể bị từ chối

Gửi command không có nghĩa hành động đã xảy ra. `ConfirmOrder` có thể bị từ chối vì đơn đã hủy hoặc caller không có quyền. Event `OrderConfirmed` chỉ nên được ghi nhận sau khi hành vi xác nhận thành công.

Điểm này giúp phân biệt:

- Command: yêu cầu thực hiện hành động.
- Kết quả command: hành động thành công, bị từ chối hoặc đang chờ.
- Event: sự thật đã xảy ra sau khi hành động thành công.

## 5. Thiết kế query handler không gây thay đổi domain state

Query handler nhận tiêu chí đọc, gọi query port và trả read model/DTO:

~~~java
public record GetOrderDetails(OrderId orderId, UserId actorId) {}

public record OrderDetailsView(
    OrderId orderId,
    String orderNumber,
    String customerName,
    OrderStatus status,
    Money total
) {}

public final class GetOrderDetailsHandler {
    private final OrderQueries queries;
    private final OrderReadAccessPolicy accessPolicy;

    public Optional<OrderDetailsView> handle(GetOrderDetails query) {
        accessPolicy.ensureCanView(query.actorId(), query.orderId());
        return queries.findDetails(query.orderId());
    }
}
~~~

Query handler có thể kiểm tra quyền đọc, nhưng không gọi `orders.save()`, không gọi `order.confirm()` và không phát event nghiệp vụ. Query adapter có thể thực hiện SQL projection:

~~~sql
SELECT
    o.id,
    o.order_number,
    c.display_name AS customer_name,
    o.status,
    o.total_amount,
    o.currency_code
FROM orders o
JOIN customers c ON c.id = o.customer_id
WHERE o.id = :order_id;
~~~

Kết quả được map thành `OrderDetailsView`. Đây là read model, không phải aggregate cần được lưu trở lại.

### Không tải aggregate chỉ để đọc

Nếu query chỉ cần mã đơn, tên khách hàng và trạng thái, tải toàn bộ `Order` cùng các association có thể gây nhiều truy vấn hoặc N+1. Projection có thể hiệu quả hơn.

Tuy nhiên, nếu query cần tính toán dựa trên hành vi miền phức tạp hoặc cần bảo đảm một quyết định theo trạng thái có thẩm quyền, hãy xác định rõ liệu đó thực sự là query hay là một bước trong command/use case.

## 6. Những thao tác tưởng như đọc nhưng thực ra là command

Một số thao tác thường bị thiết kế nhầm thành query:

| Thao tác | Vì sao có side effect? | Cách mô hình hóa phù hợp |
| --- | --- | --- |
| Đánh dấu thông báo đã đọc | Thay đổi trạng thái Notification | `MarkNotificationAsRead` |
| Tiêu thụ token đăng nhập một lần | Token không còn dùng được | `ConsumeLoginToken` |
| Redeem coupon khi mở trang ưu đãi | Ghi nhận quyền lợi đã dùng | `RedeemCoupon` |
| Ghi nhận người dùng chấp thuận điều khoản | Tạo bằng chứng chấp thuận | `AcceptTerms` |
| Đặt chỗ khi xem lịch | Giữ chỗ và ảnh hưởng người khác | `ReserveSeat` |
| Tạo báo cáo và lưu bản phát hành chính thức | Tạo một artifact nghiệp vụ có vòng đời | `GenerateOfficialReport` |
| Tính phí cho một lần tra cứu | Tạo khoản sử dụng có thể tính tiền | `RecordBillableLookup` |

### Trường hợp đánh dấu đã đọc

Nếu mở trang thông báo làm trạng thái chuyển sang READ, có thể tách:

1. `GET /notifications/{id}` đọc nội dung.
2. `POST /notifications/{id}/read` thực hiện command đánh dấu đã đọc.

Hoặc UI có thể gọi một command riêng sau khi người dùng thực sự mở thông báo. Nhờ vậy, prefetch của trình duyệt không vô tình tiêu thụ trạng thái.

### Trường hợp lượt xem

Nếu lượt xem chỉ phục vụ analytics, có thể ghi một telemetry event riêng và xử lý bất đồng bộ. Nếu lượt xem tạo điểm thưởng hoặc tính phí, cần command có định danh/idempotency rõ ràng để tránh ghi nhận trùng khi client retry.

## 7. HTTP method và ngữ nghĩa Query/Command

HTTP cung cấp các method với ngữ nghĩa chuẩn. Thiết kế API nên tôn trọng chúng:

| HTTP method | Ngữ nghĩa HTTP thường dùng | Cách dùng phổ biến |
| --- | --- | --- |
| GET | Safe: không yêu cầu thay đổi trạng thái tài nguyên | Đọc chi tiết, tìm kiếm, tải danh sách |
| HEAD | Safe, tương tự GET nhưng không trả body | Kiểm tra metadata |
| OPTIONS | Safe, hỏi khả năng giao tiếp | Khám phá method/headers |
| POST | Thực hiện xử lý theo resource; không mặc định idempotent | Tạo resource hoặc command |
| PUT | Thay thế representation; idempotent theo ngữ nghĩa HTTP | Cập nhật resource theo trạng thái mong muốn |
| PATCH | Thay đổi một phần representation; không mặc định idempotent | Cập nhật một phần |
| DELETE | Yêu cầu xóa resource; idempotent theo ngữ nghĩa HTTP | Xóa/hủy resource theo hợp đồng API |

GET không nên gây thay đổi trạng thái nghiệp vụ. Ví dụ, không nên dùng GET để xác nhận đơn hoặc đánh dấu thông báo đã đọc.

### HTTP method không tự quyết định thiết kế domain

Một endpoint POST có thể chỉ tạo yêu cầu tính toán không làm thay đổi domain state, nhưng vẫn là POST vì hợp đồng giao thức hoặc payload. Một thao tác PUT có thể được thiết kế idempotent ở cấp API. Cần giữ đúng semantics HTTP và đồng thời đặt tên command/query theo ngôn ngữ nghiệp vụ.

### Safe và idempotent là hai thuộc tính khác nhau

- **Safe:** client không yêu cầu server thay đổi trạng thái tài nguyên; tác động phụ kỹ thuật như log/metrics vẫn có thể xảy ra.
- **Idempotent:** thực hiện cùng một request nhiều lần có cùng hiệu quả dự kiến lên trạng thái như thực hiện một lần.

GET thường vừa safe vừa idempotent. PUT và DELETE được định nghĩa là idempotent theo semantics HTTP nhưng không phải safe. POST không mặc định idempotent. Một command POST có thể được làm idempotent bằng idempotency key hoặc định danh operation.

Không nên nhầm “command không idempotent” với “command luôn không được retry”. Có thể retry an toàn nếu command có idempotency contract và server thực hiện deduplication đúng.

## 8. Cache, prefetch và retry

Query thuần giúp hệ thống tận dụng cache và prefetch mà không tạo hành động nghiệp vụ ngoài ý muốn.

### Cache

Query có thể được cache ở browser, CDN, API gateway hoặc application. Nhưng cần xem xét:

- Dữ liệu có nhạy cảm không?
- Cache key có bao gồm tenant, user hoặc quyền truy cập cần thiết không?
- TTL có phù hợp độ mới của dữ liệu không?
- Khi command thành công, cache nào cần invalidation?
- Có read model bất đồng bộ khiến cache đã mới nhưng nguồn vẫn trễ không?

Không cache dữ liệu riêng tư ở shared cache nếu cache key và policy không cô lập người dùng. Không dùng cache như nguồn có thẩm quyền cho quyết định ghi quan trọng.

### Prefetch

Browser có thể tải trước link hoặc query để cải thiện tốc độ. Nếu GET làm thay đổi trạng thái nghiệp vụ, prefetch có thể thực hiện hành động mà người dùng chưa chủ ý. Đây là một lý do quan trọng để giữ GET safe.

### Retry

Query có thể được retry khi lỗi mạng vì việc đọc lặp không tạo thêm tác động nghiệp vụ. Kết quả có thể khác nếu trạng thái nguồn thay đổi giữa các lần đọc, nhưng không có command nào bị thực hiện lặp.

Command cần chính sách retry riêng. Ví dụ, nếu request xác nhận đơn timeout sau khi server commit nhưng response bị mất, client không biết hành động đã thành công hay chưa. Dùng command ID/idempotency key giúp truy vấn kết quả hoặc gửi lại cùng yêu cầu mà không xác nhận hai lần.

## 9. CQRS ở mức phù hợp

CQRS (Command Query Responsibility Segregation) tách trách nhiệm đọc và ghi. Ở mức đơn giản, có thể chỉ cần hai handler và hai interface khác nhau trong cùng ứng dụng, dùng chung database.

~~~mermaid
flowchart TD
    A[API Adapter]
    Q[Query Handler]
    R[Read Query / Projection]
    C[Command Handler]
    D[Domain Aggregate]
    P[Repository]
    DB[(Database)]
    A -->|Query| Q --> R --> DB
    A -->|Command| C --> P --> DB
    P --> D
    D --> P
~~~

Query side có thể trả DTO hoặc projection. Command side tải aggregate, gọi hành vi và lưu trạng thái. Không bắt buộc phải có hai database, broker hay Event Sourcing.

### Khi nào tách query và command thành handler riêng?

- Khi trách nhiệm đọc và ghi đã khác nhau rõ.
- Khi query cần projection hoặc truy vấn nhiều bảng.
- Khi command cần transaction và aggregate behavior.
- Khi muốn kiểm thử side effect và quyền truy cập độc lập.
- Khi nhiều adapter cần gọi cùng use case.

### Khi nào không cần CQRS riêng biệt?

Với CRUD đơn giản, một service nhỏ có thể đủ nếu mỗi method vẫn thể hiện rõ query hay command. Không nên tạo nhiều interface và lớp trung gian chỉ để theo một khuôn mẫu khi chúng không giúp code dễ hiểu hơn.

### CQRS không đồng nghĩa Event Sourcing

Có thể tách query/command nhưng vẫn lưu trạng thái hiện tại trong database quan hệ. Event Sourcing là một lựa chọn lưu trữ khác, trong đó event history là nguồn dữ liệu có thẩm quyền. Không cần triển khai Event Sourcing chỉ để bảo đảm query không sửa trạng thái.

## 10. Query và command có thể dùng cùng một aggregate nhưng trách nhiệm khác nhau

Một aggregate có thể cung cấp dữ liệu để query trong domain/application, nhưng query không nên gọi các hành vi làm thay đổi trạng thái. Ví dụ:

~~~java
public final class Subscription {
    private final SubscriptionId id;
    private SubscriptionStatus status;
    private Instant expiresAt;

    public boolean isActiveAt(Instant at) {
        return status == SubscriptionStatus.ACTIVE
            && at.isBefore(expiresAt);
    }

    public void cancel(CancellationReason reason, Instant now) {
        if (status != SubscriptionStatus.ACTIVE) {
            throw new SubscriptionCannotBeCancelledException(id, status);
        }
        status = SubscriptionStatus.CANCELLED;
        // Ghi nhận SubscriptionCancelled.
    }
}
~~~

`isActiveAt(...)` là phép hỏi về trạng thái, không thay đổi aggregate. `cancel(...)` là hành vi thay đổi và bảo vệ invariant. Tuy nhiên, không nhất thiết mọi query phải tải aggregate; query service có thể đọc projection phù hợp.

### Getter cũng cần giữ ngữ nghĩa đơn giản

Getter không nên có hành vi ẩn như tự gia hạn subscription, đánh dấu đã xem hoặc cập nhật thời gian truy cập có ý nghĩa nghiệp vụ. Nếu một phương thức có tên `getCurrentBalance()` nhưng tự ghi phí tra cứu, tên và ranh giới của nó đang che giấu command.

## 11. Phân biệt validation của Query và Command

Query và command có thể cùng cần validation, nhưng mục tiêu khác nhau.

**Query validation** kiểm tra tiêu chí đọc:

- ID có đúng định dạng không?
- Khoảng thời gian có hợp lệ không?
- Page size có nằm trong giới hạn không?
- Bộ lọc/sort có nằm trong allowlist không?
- Caller có quyền xem dữ liệu không?

**Command validation** kiểm tra yêu cầu hành động:

- Dữ liệu đầu vào có đủ để diễn đạt ý định không?
- Caller có quyền thực hiện use case không?
- Aggregate có tồn tại không?
- Trạng thái hiện tại có cho phép hành vi không?
- Invariant có được bảo vệ dưới cập nhật đồng thời không?

Không nên coi validation request là thay thế cho domain invariant. Client có thể gửi một command có cấu trúc hợp lệ nhưng hành động vẫn không được phép trong trạng thái hiện tại.

## 12. Audit truy cập và query có ghi nhận

Một số hệ thống cần ghi lại ai đã xem dữ liệu nhạy cảm. Ví dụ, nhân viên y tế xem hồ sơ bệnh nhân hoặc nhân viên hỗ trợ xem thông tin tài khoản. Đây là yêu cầu audit quan trọng nhưng không có nghĩa query phải thay đổi domain aggregate.

Có thể tách:

- Query handler kiểm tra quyền và trả dữ liệu được phép.
- Audit infrastructure ghi access record với actor, resource, thời điểm và mục đích.
- Audit record được lưu ở một boundary riêng, không sửa aggregate chỉ vì có lượt xem.

Nếu việc xem dữ liệu tạo ra hậu quả nghiệp vụ (ví dụ tính phí mỗi lần tra cứu hoặc tiêu thụ một lượt truy cập), hãy biểu diễn tác động đó bằng command hoặc một operation có hợp đồng rõ.

### Audit không nên làm lộ dữ liệu trong log

Access log thường chỉ cần định danh actor/resource, thời gian, kết quả authorization và correlation ID. Tránh ghi toàn bộ payload nhạy cảm hoặc nội dung hồ sơ vào log chỉ để chứng minh đã truy cập.

### Query và audit cần xử lý lỗi thế nào?

Nếu audit là yêu cầu pháp lý bắt buộc, cần xác định điều gì xảy ra khi ghi audit thất bại: từ chối đọc, ghi vào durable queue hay dùng cơ chế khác. Không nên để quyết định này ngầm phụ thuộc vào một log statement. Đây là chính sách bảo mật/compliance cần được thiết kế và kiểm thử riêng.

## 13. Các trường hợp đặc biệt: preview, validation và tính toán

Không phải mọi thao tác trả về kết quả đều là query đơn giản, và không phải mọi thao tác có tính toán đều là command.

### Preview báo giá

Một query có thể tính báo giá dự kiến dựa trên dữ liệu hiện tại mà không giữ giá hoặc tạo đơn. Kết quả chỉ mang tính tham khảo. Khi người dùng xác nhận, command `PlaceOrder` phải tính hoặc xác nhận lại giá theo chính sách có thẩm quyền.

Nếu doanh nghiệp muốn khóa giá trong một khoảng thời gian, thao tác preview có thể thực sự tạo một quote/reservation có vòng đời. Khi đó nên mô hình hóa thành command `CreateQuote` hoặc `ReservePrice`, không giả vờ nó chỉ là query.

### Kiểm tra khả năng thực hiện

Query `CanCancelOrder` có thể trả lời dựa trên trạng thái hiện tại để UI bật/tắt nút. Nhưng kết quả có thể cũ khi command thật được gửi. `CancelOrder` vẫn phải kiểm tra lại điều kiện bên trong aggregate/transaction.

Query kiểm tra trước không phải là sự bảo đảm rằng command sau đó sẽ thành công.

### Tính toán có tốn tài nguyên

Một query có thể tốn CPU nhưng không thay đổi domain state. Có thể cần rate limit, timeout, cache hoặc job bất đồng bộ. Nếu yêu cầu tính toán tạo một artifact chính thức, tính phí hoặc chiếm tài nguyên có giới hạn, cần xác định phần nào là query và phần nào là command.

## 14. Đặt tên và thiết kế hợp đồng

Tên rõ giúp người gọi hiểu thao tác có thay đổi trạng thái không.

| Tên mơ hồ | Query rõ nghĩa | Command rõ nghĩa |
| --- | --- | --- |
| `processOrder(id)` | `GetOrderDetails(id)` | `ConfirmOrder(id)` |
| `viewNotification(id)` | `GetNotification(id)` | `MarkNotificationAsRead(id)` |
| `checkCoupon(code)` | `GetCouponEligibility(code)` | `RedeemCoupon(code)` |
| `getSeat(id)` | `GetSeatAvailability(id)` | `ReserveSeat(id)` |
| `calculateReport(...)` | `PreviewReport(...)` | `GenerateOfficialReport(...)` nếu tạo artifact chính thức |

### Query thường trả projection/DTO

Query contract nên chỉ ra tiêu chí, phân trang và kiểu dữ liệu trả về. Ví dụ:

~~~java
public interface OrderQueries {
    Optional<OrderDetailsView> findDetails(OrderId id);
    Page<OrderSummary> search(OrderSearch criteria);
}
~~~

### Command diễn đạt ý định, không phải patch tùy ý

~~~java
public record CancelOrder(
    OrderId orderId,
    UserId actorId,
    CancellationReason reason,
    UUID requestId
) {}
~~~

Command nêu rõ hành động, actor, lý do và định danh request. Không nên nhận một DTO có mọi field của entity rồi cho phép client gửi tùy ý trạng thái, tổng tiền, version hoặc người phê duyệt.

## 15. Kiểm thử query và command

Kiểm thử nên xác nhận ngữ nghĩa của từng loại thao tác.

### Query test

- Trả đúng projection với dữ liệu hiện tại.
- Áp dụng đúng filter, sort và pagination.
- Kiểm tra quyền trước khi trả dữ liệu.
- Không gọi repository ghi hoặc hành vi thay đổi aggregate.
- Không phát domain event do đọc.
- Không làm thay đổi trạng thái nghiệp vụ sau nhiều lần gọi.
- Cache không trộn dữ liệu giữa user/tenant.

Ví dụ, gọi `GetOrderDetails` nhiều lần không được làm thay đổi `Order.status`, tổng tiền hoặc event history.

### Command test

- Command hợp lệ gọi đúng hành vi aggregate.
- Invariant được kiểm tra trong domain.
- Command bị từ chối không lưu thay đổi hoặc phát event thành công.
- Authorization được kiểm tra trên resource cụ thể.
- Transaction và outbox được xử lý đúng.
- Request lặp theo cùng idempotency key không tạo tác động lặp.
- Cập nhật đồng thời được phát hiện hoặc xử lý theo chính sách.

### Test side effect ẩn

Với query, có thể dùng fake repository và spy cho event publisher để xác nhận không có lệnh ghi. Integration test có thể đọc trạng thái trước/sau để xác nhận query không thay đổi domain state. Với audit/metrics, kiểm thử riêng rằng tác động kỹ thuật không thay đổi nghiệp vụ và không làm lộ dữ liệu nhạy cảm.

## 16. Những sai lầm thường gặp

- **Dùng GET để thực hiện command:** prefetch, cache hoặc retry có thể kích hoạt hành động ngoài ý muốn.
- **Gộp đọc và ghi trong một method:** caller không biết thao tác có side effect hay không.
- **Ẩn mutation trong getter:** đọc object làm thay đổi trạng thái hoặc phát event.
- **Để query cập nhật lastViewedAt có ý nghĩa nghiệp vụ:** biến một thao tác đọc thành command không rõ ràng.
- **Dùng query preview làm cam kết:** dữ liệu có thể thay đổi trước lúc command thật được thực hiện.
- **Dựa vào query kiểm tra trước để bảo đảm command:** trạng thái có thể thay đổi giữa lần đọc và lần ghi.
- **Cho phép client gửi toàn bộ entity để cập nhật:** có thể sửa field ngoài quyền và bỏ qua hành vi miền.
- **Dùng repository ghi cho mọi truy vấn:** tải aggregate không cần thiết và dễ tạo N+1.
- **Coi audit log là lý do để query sửa aggregate:** audit truy cập nên có boundary và chính sách riêng.
- **Cache query nhạy cảm không đúng key:** có thể trả dữ liệu của user/tenant khác.
- **Retry command mà không idempotency:** có thể tạo thanh toán, reservation hoặc lượt sử dụng lặp.
- **Đồng nhất command với event:** command là yêu cầu; event là sự thật đã xảy ra.
- **Áp dụng CQRS quá mức:** tạo nhiều lớp và hạ tầng mà không có nhu cầu.
- **Cho rằng query luôn không có bất kỳ side effect kỹ thuật nào:** log, metric và cache có thể thay đổi; điều cần bảo vệ là ngữ nghĩa nghiệp vụ và hợp đồng safe.

## 17. Quy trình phân loại một thao tác

Khi thiết kế một endpoint, method hoặc use case mới, hãy đặt các câu hỏi:

1. **Caller muốn biết điều gì hay muốn hệ thống làm điều gì?**
2. **Sau thao tác, có sự thật nghiệp vụ nào thay đổi không?**
3. **Có tạo reservation, token consumption, fee, audit evidence hoặc quyền lợi mới không?**
4. **Nếu browser gọi lại hoặc prefetch, có gây hậu quả không?**
5. **Nếu request timeout rồi retry, có thể lặp tác động không?**
6. **Query có thể trả projection/DTO mà không tải aggregate không?**
7. **Command cần aggregate nào bảo vệ invariant?**
8. **Có side effect kỹ thuật như audit/metrics không, và nó thuộc policy nào?**
9. **HTTP method có đúng semantics safe/idempotent không?**
10. **Có cần tách command/query handler hay chỉ cần method rõ ràng trong cùng service?**
11. **Kết quả preview có thể cũ trước lúc command thực hiện không?**
12. **Có test chứng minh query không sửa domain state và command không bỏ qua invariant không?**

## Checklist rà soát

- [ ] Query chỉ cung cấp thông tin, không thay đổi sự thật nghiệp vụ.
- [ ] Command diễn đạt một ý định hành động cụ thể.
- [ ] Event chỉ được ghi nhận sau khi sự thật tương ứng đã xảy ra.
- [ ] Side effect nghiệp vụ không bị ẩn trong getter, query handler hoặc GET endpoint.
- [ ] Query dùng read model/projection phù hợp và trả DTO rõ ràng.
- [ ] Command tải aggregate root và gọi hành vi miền.
- [ ] Query và command có validation, authorization phù hợp.
- [ ] Preview/check query không bị xem là bảo đảm cho command sau đó.
- [ ] HTTP GET/HEAD/OPTIONS được giữ safe theo semantics.
- [ ] Command retry có idempotency khi cần.
- [ ] Cache có freshness, authorization và invalidation policy rõ.
- [ ] Audit/metrics được tách khỏi mutation nghiệp vụ và không log dữ liệu thừa.
- [ ] CQRS chỉ được áp dụng ở mức mang lại lợi ích thực tế.
- [ ] Có test query không thay đổi domain state và command bảo vệ invariant.

## Kết luận

Query trả lời câu hỏi về thông tin và không làm thay đổi trạng thái nghiệp vụ; command diễn đạt ý định thực hiện một hành động có thể thay đổi trạng thái. Giữ hai ngữ nghĩa riêng giúp hệ thống tận dụng cache, prefetch và retry cho thao tác đọc, đồng thời buộc mọi thay đổi đi qua application use case và domain behavior phù hợp. Những tác động kỹ thuật như log, metric hoặc audit truy cập vẫn có thể xảy ra khi đọc, nhưng cần được phân biệt với side effect nghiệp vụ. Khi một thao tác đọc thực sự tiêu thụ quyền lợi, thay đổi trạng thái hoặc tạo nghĩa vụ, hãy mô hình hóa phần đó thành command rõ ràng. Sự phân biệt này làm API dễ hiểu, kiểm thử dễ hơn và giúp mô hình DDD tiến hóa mà không che giấu tác động của mỗi thao tác.
