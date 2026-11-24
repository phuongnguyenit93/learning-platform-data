# Dữ liệu kiểm thử sát production (Production parity test data)

Trong chương **Testing Strategy** của module bảo vệ logic nghiệp vụ, dữ liệu kiểm thử cần tái hiện những điều kiện khiến quy tắc nghiệp vụ có thể bị lạm dụng: một người dùng thuộc tenant khác, một đơn đã đổi trạng thái, một báo giá dùng chính sách cũ, một khoản hoàn đang chờ kết quả hoặc hai yêu cầu cùng sử dụng một hạn mức.

**Production parity test data** là dữ liệu kiểm thử có mức tương đồng cần thiết với dữ liệu vận hành về cấu trúc, quan hệ, trạng thái, lịch sử và phân bố để kiểm tra một giả thuyết cụ thể. Mức tương đồng phải gắn với lỗi muốn phát hiện và kết quả mong đợi. Một triệu bản ghi giống hệt nhau có thể ít giá trị hơn hai đơn hàng có chủ sở hữu khác nhau nhưng cùng các thuộc tính còn lại.

Bài học hướng dẫn xây dựng bộ dữ liệu như vậy cho business invariants, state machine, quyền theo đối tượng, transaction và idempotency. Các định danh, số tiền, chính sách và tình huống bên dưới đều là ví dụ tổng hợp phục vụ kiểm thử.

## 1. Xác định parity theo rủi ro nghiệp vụ

### 1.1. Những chiều tương đồng cần quan tâm

| Chiều dữ liệu | Điều cần tái hiện | Lỗi có thể bị bỏ lọt nếu dữ liệu quá đơn giản |
|---|---|---|
| Cấu trúc | Schema, kiểu số, currency, null hợp lệ, trường tùy chọn | Chuyển đổi sai số tiền; coi trường chưa có là giá trị 0 |
| Quan hệ | Tenant, membership, chủ sở hữu, dòng hàng, giao dịch và đối tượng cha | Truy vấn chỉ theo `orderId`, thiếu phạm vi tenant |
| Trạng thái | Bản nháp, chờ duyệt, đã duyệt, đã thu tiền, hủy, hoàn một phần | Endpoint chấp nhận thao tác ở trạng thái không hợp lệ |
| Lịch sử | Phiên bản chính sách, thay đổi quyền, lần thử trước, sự kiện đến muộn | Tái tính giao dịch cũ bằng chính sách mới |
| Thời gian | Trước, đúng và sau hạn; múi giờ; thời điểm thu hồi quyền | Coupon hết hạn vẫn dùng được; quyền cũ vẫn có hiệu lực |
| Phân bố | Tenant lớn/nhỏ, giá trị biên, tài nguyên nóng, lịch sử dài | Test chỉ chứng minh trường hợp trung bình |
| Tranh chấp | Nhiều tác vụ cùng nhắm một đơn, hạn mức hoặc ý định | Hai transaction cùng vượt số tiền được hoàn |
| Ranh giới tích hợp | Định danh provider, amount/currency, callback, retry | Lẫn các lần thử với các giao dịch tài chính khác nhau |

Parity dữ liệu và parity môi trường hỗ trợ nhau. Một fixture đúng vẫn không kiểm tra được cơ chế khóa của database nếu test chỉ dùng repository giả. Ngược lại, dùng cùng loại database nhưng mọi tài nguyên đều thuộc cùng một người sẽ không bộc lộ lỗi phân quyền theo đối tượng.

### 1.2. Viết mục tiêu có thể kiểm chứng

Thay vì yêu cầu “dữ liệu giống production”, hãy viết một mục tiêu cụ thể:

> Bộ dữ liệu có hai tenant, mỗi tenant có khách hàng và đơn đã thanh toán. Hai đơn có cùng số tiền và trạng thái. Khi khách tenant A gửi định danh đơn tenant B vào API hoàn tiền, yêu cầu bị từ chối và không tạo giữ chỗ hay lệnh hoàn.

Mục tiêu này chỉ ra được dữ liệu cần có, thao tác tấn công và oracle. Không cần bản sao toàn bộ dữ liệu vận hành để chứng minh thuộc tính đó.

Với từng mục tiêu, ghi thêm giới hạn của bằng chứng. Hai tenant đủ cho ca cô lập tenant cơ bản nhưng chưa chứng minh tính đúng đắn khi một người tham gia nhiều tenant, khi đổi tenant đang hoạt động hoặc khi quyền vừa bị thu hồi.

## 2. Bắt đầu từ bản đồ quy tắc và kịch bản tấn công

### 2.1. Chuyển quy tắc thành yêu cầu dữ liệu

| Quy tắc cần bảo vệ | Dữ liệu tối thiểu | Thao tác cần thử | Kết quả mong đợi |
|---|---|---|---|
| Chỉ chủ đơn được xem đơn | Hai khách cùng tenant, mỗi người có đơn | Khách A yêu cầu đơn của B | Không trả dữ liệu không được phép |
| Không vượt tenant | Hai tenant có dữ liệu gần giống nhau | Đổi tenant đang hoạt động hoặc thay `orderId` | Kiểm tra membership và phạm vi đối tượng |
| Người yêu cầu không tự duyệt | Requester, approver, yêu cầu chờ duyệt | Requester gọi endpoint duyệt | Không chuyển trạng thái |
| Chỉ hoàn tiền đã thu | Đơn nháp, đã thu, đã hủy và giao dịch thu thất bại | Hoàn cùng số tiền ở từng trạng thái | Chỉ trạng thái đủ điều kiện được tiếp tục |
| Tổng hoàn không vượt mức được phép | Khoản đã hoàn và khoản đang giữ chỗ | Hai ý định hoàn cạnh tranh | Bất biến được giữ sau commit |
| Coupon đúng đối tượng và giới hạn | Coupon riêng, công khai, hết hạn, đã dùng | Đổi người dùng, lặp yêu cầu hoặc đổi thứ tự bước | Không nhận thêm ưu đãi trái phép |
| Một ý định chỉ tạo một hiệu ứng | Giao dịch trước và các lần thử liên quan | Retry, callback trùng, timeout | Không thu/hoàn tiền trùng |
| Giao dịch cũ giữ chính sách phù hợp | Giao dịch theo v1 và cấu hình hiện hành v2 | Hoàn hoặc đối soát giao dịch cũ | Dùng đúng dữ liệu và chính sách đã chốt |

Một danh sách giá trị ngẫu nhiên không thay thế được ma trận này. Tên giả, địa chỉ giả và số lượng bản ghi lớn chỉ hữu ích nếu chúng tham gia điều kiện mà hệ thống thực sự kiểm tra.

### 2.2. Luôn tạo cặp được phép và bị từ chối

Với kiểm thử phân quyền, một phản hồi từ chối chỉ có giá trị khi tài nguyên đích thực sự tồn tại và đã có đối chứng hợp lệ:

1. Chủ đơn truy cập thành công đơn của mình.
2. Người khác truy cập cùng đơn bị từ chối.
3. Sau lần bị từ chối, đơn và các dữ liệu liên quan không thay đổi.

Nếu test gửi một UUID ngẫu nhiên chưa tồn tại, phản hồi `404` chỉ chứng minh đường không tìm thấy tài nguyên. Nó chưa chứng minh việc kiểm tra quyền trên tài nguyên tồn tại. API có thể chủ động dùng `404` cho trường hợp không có quyền; oracle vẫn phải biết fixture nào tồn tại và kiểm tra hiệu ứng bền vững.

Các cặp hữu ích khác gồm coupon còn hạn/hết hạn, request đang chờ duyệt/đã duyệt, thành viên còn quyền/đã bị thu hồi quyền và hoàn tiền còn hạn mức/hết hạn mức.

## 3. Lập hợp đồng cho bộ dữ liệu

### 3.1. Chọn nguồn theo nhu cầu kiểm thử

| Nguồn | Phù hợp với | Điều phải kiểm soát |
|---|---|---|
| Fixture tổng hợp nhỏ | Test hồi quy, quyền theo đối tượng, trạng thái và biên | Quan hệ hợp lệ, kết quả mong đợi rõ ràng |
| Generator có seed | Nhiều tổ hợp, lịch sử dài, phân bố và tài nguyên nóng | Ràng buộc miền, khả năng tái hiện và ngân sách kích thước |
| Số liệu tổng hợp đã được phép sử dụng | Ước lượng phân bố theo nhóm | Độ cập nhật, khả năng suy ra nhóm hiếm và sai lệch mẫu |
| Trích xuất đã được cho phép và xử lý | Hình dạng dữ liệu lịch sử khó tổng hợp | Tối thiểu hóa dữ liệu, biến đổi nhất quán và cô lập môi trường |
| Luồng sự kiện tổng hợp hoặc đã làm sạch | Retry, callback trùng, sự kiện đảo thứ tự | Loại bỏ thông tin xác thực và mọi đường gọi thật |

Dữ liệu tổng hợp thường là nền tảng phù hợp cho test có oracle chính xác. Khi dùng số liệu hoặc dữ liệu từ vận hành, quy trình lấy và xử lý phải nằm trong phạm vi được cho phép của tổ chức; bản thân yêu cầu viết test không cấp quyền truy cập dữ liệu đó.

### 3.2. Manifest là hợp đồng tái hiện

Manifest mô tả bộ dữ liệu, không chứa bí mật hay dữ liệu cá nhân thật. Ví dụ dưới đây là nội dung minh họa, không yêu cầu tạo thêm file:

```yaml
datasetId: business-security-example-v1
generatorVersion: example-generator-v1
schemaVersion: example-schema-v3
seed: 84007
clock: '2030-01-15T10:00:00Z'
timezone: UTC
policyVersions:
  pricing: [price-v1, price-v2]
  refund: [refund-v1]
scenarios:
  - same-tenant-other-owner
  - cross-tenant-refund
  - partial-refund-with-reservation
  - duplicate-callback
  - historical-policy
expected:
  tenants: 2
  baselineValid: true
  externalMode: fake
```

`seed` giúp tái tạo lựa chọn ngẫu nhiên, nhưng để tái tạo đầy đủ còn cần phiên bản generator, chính sách, clock và quy tắc sắp xếp. Cùng seed có thể sinh dữ liệu khác nếu thuật toán hoặc thứ tự duyệt collection thay đổi.

Không ghi phiên bản hoặc số lượng mong đợi theo cảm tính. Manifest thực tế phải được kiểm tra với dữ liệu đã sinh và với các migration mà test áp dụng.

### 3.3. Tách dữ liệu hợp lệ ban đầu khỏi yêu cầu tấn công

Một baseline thông thường phải thỏa khóa ngoại và các bất biến dữ liệu. Từ baseline đó, test gửi yêu cầu không hợp lệ qua ranh giới đang kiểm tra:

- Giữ nguyên đơn của tenant B trong database; client tenant A thay `orderId` trong request.
- Giữ nguyên giá đã xác nhận; client gửi `total` thấp hơn.
- Giữ nguyên khoản hoàn đã thành công; gửi lại cùng ý định.
- Giữ nguyên quy trình chờ duyệt; requester cố gọi bước duyệt.

Nếu sửa dữ liệu trong database thành một trạng thái không thể xuất hiện qua luồng hợp lệ, cần đặt nhãn rõ là **dữ liệu lỗi để kiểm tra phục hồi hoặc ràng buộc**. Test loại này có ích nhưng chứng minh một thuộc tính khác với việc ngăn kẻ tấn công lợi dụng API.

## 4. Thiết kế quan hệ, quyền và trạng thái có ý nghĩa

### 4.1. Mô hình dữ liệu cho kiểm thử quyền

Một mô hình thường gặp:

```text
Tenant ──< Membership >── User
Tenant ──< Order >── Owner
Order ──< Payment
Order ──< RefundIntent ──< ProcessingAttempt
ApprovalRequest ── Requester + Approver + Target
```

Các dấu nối mô tả quan hệ khái niệm, không ấn định schema. Ví dụ, một người có thể có nhiều membership thay vì một `tenantId` duy nhất trên user.

Ngoài hai tenant cơ bản, nên có các tình huống:

- Hai người cùng tenant nhưng khác chủ sở hữu tài nguyên.
- Một người tham gia hai tenant với vai trò khác nhau.
- Người đã bị xóa membership nhưng có phiên đăng nhập được tạo trước đó.
- Quản trị viên có quyền trong tenant A và không có quyền trong tenant B.
- Một người đồng thời có vai trò requester và approver, trong khi chính sách cấm tự duyệt cùng một yêu cầu.
- Tài nguyên có trạng thái mềm như bị khóa, lưu trữ hoặc chuyển chủ sở hữu, nếu mô hình hỗ trợ.

Nếu mọi fixture đều dùng tài khoản quản trị, test có thể vượt qua nhờ quyền rộng và không kiểm tra được đường mà khách hàng thông thường sử dụng. Principal trong test phải thể hiện đúng vai trò, tenant đang hoạt động và thời điểm quyền được đánh giá.

### 4.2. Tạo trạng thái bằng lịch sử phù hợp

Trạng thái `PAID` thường cần giao dịch thu thành công, currency và amount khớp, thời điểm thu hợp lệ và phiên bản giá đã xác nhận. Chỉ gán chuỗi `PAID` lên một đơn trống có thể bỏ qua điều kiện mà code thực tế phụ thuộc.

Tương tự, `PARTIALLY_REFUNDED` cần có khoản hoàn thành công; một khoản `RESERVED` cần công việc xử lý hoặc ý định đang chờ; một yêu cầu đã duyệt phải biết ai duyệt và có đáp ứng quy tắc tách biệt nhiệm vụ hay không.

Nên tạo fixture qua hàm dựng miền hoặc luồng nghiệp vụ khi chi phí phù hợp. Với dữ liệu lớn được nạp trực tiếp để tiết kiệm thời gian, chạy validator miền và kiểm tra hậu điều kiện để tránh baseline không thể xuất hiện trong thực tế.

## 5. Thời gian và phiên bản là dữ liệu đầu vào

### 5.1. Kiểm soát clock cho các mốc quan trọng

Với coupon hết hạn tại `T`, hợp đồng phải nêu rõ `now < T` hay `now <= T` mới được dùng. Từ đó tạo ba ca quanh biên theo độ chính xác thời gian mà hệ thống hỗ trợ:

| Thời điểm kiểm thử | Mục tiêu |
|---|---|
| Ngay trước `T` | Xác nhận nhánh còn hạn |
| Đúng `T` | Xác nhận quy tắc bao hàm hay loại trừ điểm biên |
| Ngay sau `T` | Xác nhận nhánh hết hạn |

Không mặc định dùng nanosecond nếu database chỉ lưu millisecond hoặc second. Sau khi lưu và đọc lại, mốc thời gian có thể bị chuẩn hóa; fixture phải phản ánh độ chính xác thật của hợp đồng lưu trữ và API.

Trong Java, có thể truyền `Clock.fixed(...)` cho service thay vì để fixture phụ thuộc `Instant.now()`. Cần kiểm soát các thành phần tham gia quyết định thời gian, bao gồm background worker hoặc phía database nếu chúng là nơi đánh giá hạn.

### 5.2. Bảo toàn quan hệ thời gian khi biến đổi dữ liệu

Nếu dịch chuyển các timestamp của một kịch bản, hãy giữ các quan hệ có ý nghĩa:

```text
createdAt <= approvedAt <= paidAt
paidAt <= refundRequestedAt
reservationCreatedAt <= reservationExpiresAt
eventOccurredAt có thể trước eventReceivedAt một khoảng đáng kể
```

Sự kiện đến trễ và sai thứ tự nhận là tình huống bình thường trong một số tích hợp. Test cần phân biệt thời điểm sự kiện xảy ra với thời điểm ứng dụng nhận được sự kiện. Không ép toàn bộ lịch sử thành một chuỗi nhận tăng dần rồi kết luận hệ thống xử lý được callback đảo thứ tự.

Các chính sách v1/v2 cũng cần quan hệ rõ với giao dịch. Ví dụ, giao dịch bán theo `price-v1` vẫn giữ snapshot v1 trong khi cấu hình hiện hành là v2. Khi hoàn tiền, oracle xác định phiên bản cần dùng theo hợp đồng đã chốt, thay vì luôn chọn cấu hình mới nhất.

## 6. Ví dụ Java: fixture xác định và validator miền

Ví dụ Java 17 trở lên dưới đây tập trung vào quyền sở hữu và hạn mức hoàn tiền. Đây là lược đồ tối giản trong bộ nhớ; fixture cho một ứng dụng thật còn cần bổ sung payment, membership, lịch sử chuyển trạng thái và các ràng buộc của mô hình đó.

Trong ví dụ, tất cả khoản tiền là VND theo scale 0, biểu diễn bằng `long`. `refundableMinor` là tổng tiền được phép hoàn theo chính sách đã xác định. Khoản hoàn `SUCCEEDED` đã tiêu hạn mức; `RESERVED` đang giữ hạn mức; `FAILED` đã có kết quả thất bại cuối cùng nên không còn giữ hạn mức.

```java
import java.time.Instant;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;

public final class ParityFixtures {
    public enum OrderState { PAID, CANCELLED }
    public enum RefundState { RESERVED, SUCCEEDED, FAILED }

    public record Buyer(String id, String tenantId) {}

    public record Order(
            String id,
            String tenantId,
            String buyerId,
            OrderState state,
            String currency,
            long paidMinor,
            long refundableMinor,
            String pricePolicyVersion,
            Instant paidAt) {}

    public record Refund(
            String id,
            String orderId,
            long amountMinor,
            RefundState state) {}

    public record Dataset(
            Instant now,
            Set<String> tenantIds,
            List<Buyer> buyers,
            List<Order> orders,
            List<Refund> refunds) {
        public Dataset {
            tenantIds = Set.copyOf(tenantIds);
            buyers = List.copyOf(buyers);
            orders = List.copyOf(orders);
            refunds = List.copyOf(refunds);
        }
    }

    public static Dataset baseline() {
        Instant now = Instant.parse("2030-01-15T10:00:00Z");
        var data = new Dataset(
                now,
                Set.of("tenant-red", "tenant-blue"),
                List.of(
                        new Buyer("buyer-red", "tenant-red"),
                        new Buyer("buyer-red-other", "tenant-red"),
                        new Buyer("buyer-blue", "tenant-blue")),
                List.of(
                        new Order("order-red-paid", "tenant-red", "buyer-red",
                                OrderState.PAID, "VND", 100_000, 100_000,
                                "price-v1", now.minusSeconds(3_600)),
                        new Order("order-blue-paid", "tenant-blue", "buyer-blue",
                                OrderState.PAID, "VND", 100_000, 100_000,
                                "price-v2", now.minusSeconds(1_800)),
                        new Order("order-red-cancelled", "tenant-red", "buyer-red",
                                OrderState.CANCELLED, "VND", 0, 0,
                                "price-v2", null)),
                List.of(
                        new Refund("refund-done", "order-red-paid", 30_000,
                                RefundState.SUCCEEDED),
                        new Refund("refund-pending", "order-red-paid", 20_000,
                                RefundState.RESERVED),
                        new Refund("refund-failed", "order-red-paid", 40_000,
                                RefundState.FAILED)));
        validate(data);
        return data;
    }

    public static long available(Dataset data, String orderId) {
        Order order = data.orders().stream()
                .filter(candidate -> candidate.id().equals(orderId))
                .findFirst().orElseThrow();
        long usedOrReserved = data.refunds().stream()
                .filter(refund -> refund.orderId().equals(orderId))
                .filter(refund -> refund.state() == RefundState.SUCCEEDED
                        || refund.state() == RefundState.RESERVED)
                .mapToLong(Refund::amountMinor)
                .reduce(0L, Math::addExact);
        return Math.subtractExact(order.refundableMinor(), usedOrReserved);
    }

    public static void validate(Dataset data) {
        var buyers = data.buyers().stream().collect(Collectors.toMap(
                Buyer::id, Function.identity()));
        var orders = data.orders().stream().collect(Collectors.toMap(
                Order::id, Function.identity()));

        for (Buyer buyer : data.buyers()) {
            check(data.tenantIds().contains(buyer.tenantId()), "unknown tenant");
        }
        for (Order order : data.orders()) {
            Buyer owner = buyers.get(order.buyerId());
            check(owner != null && owner.tenantId().equals(order.tenantId()),
                    "owner/tenant mismatch");
            check("VND".equals(order.currency()), "unsupported currency");
            check(order.paidMinor() >= 0 && order.refundableMinor() >= 0
                    && order.refundableMinor() <= order.paidMinor(),
                    "invalid refundable amount");
            check(Set.of("price-v1", "price-v2")
                    .contains(order.pricePolicyVersion()), "unknown policy");
            check(order.state() != null, "missing order state");
            if (order.state() == OrderState.PAID) {
                check(order.paidAt() != null
                        && !order.paidAt().isAfter(data.now()), "invalid paidAt");
            } else {
                check(order.paidMinor() == 0 && order.refundableMinor() == 0
                        && order.paidAt() == null, "invalid cancelled baseline");
            }
        }
        var refundIds = new HashSet<String>();
        for (Refund refund : data.refunds()) {
            Order order = orders.get(refund.orderId());
            check(refundIds.add(refund.id()), "duplicate refund id");
            check(order != null && order.state() == OrderState.PAID,
                    "refund requires a paid order");
            check(refund.amountMinor() > 0 && refund.state() != null,
                    "invalid refund");
        }
        for (Order order : data.orders()) {
            check(available(data, order.id()) >= 0, "refund limit exceeded");
        }
    }

    private static void check(boolean valid, String message) {
        if (!valid) {
            throw new IllegalStateException(message);
        }
    }
}
```

Đơn `order-red-paid` còn `100.000 − 30.000 − 20.000 = 50.000` VND để giữ chỗ cho hoàn mới. Khoản `FAILED` không làm giảm số còn lại trong mô hình này. Một khoản bị timeout nhưng chưa biết kết quả phải được biểu diễn bằng trạng thái chưa xác định/đang xử lý phù hợp, không tùy tiện gán `FAILED` để giải phóng hạn mức.

Đơn `order-blue-paid` có cùng số tiền đã thu nhưng khác tenant và chủ sở hữu; `buyer-red-other` là đối chứng cùng tenant nhưng khác chủ. Có thể dùng fixture để kiểm tra:

| Principal và yêu cầu | Kỳ vọng |
|---|---|
| `buyer-red` xem `order-red-paid` | Được phép nếu quyền xem thuộc chủ đơn |
| `buyer-red-other` xem `order-red-paid` | Bị từ chối theo chính sách chỉ chủ đơn |
| `buyer-red` yêu cầu hoàn `order-blue-paid` | Bị từ chối do khác tenant/quyền đối tượng |
| `buyer-red` hoàn 50.001 trên `order-red-paid` | Bị từ chối do vượt phần còn lại |
| Hai ý định của chủ đơn cùng hoàn 40.000 trên `order-red-paid` | Tổng giữ chỗ mới không được vượt 50.000 |

Principal trong test phải được tạo qua cơ chế phù hợp với lớp đang kiểm thử. Unit test service có thể truyền principal giả lập; test xác thực đầu cuối cần đi qua cơ chế đăng nhập/token của môi trường test và xác minh claim đúng.

Validator fixture giúp phát hiện lỗi chuẩn bị dữ liệu, nhưng không thay thế oracle. Trong test hạn mức, vẫn giữ expected value `50_000` được suy ra độc lập từ hợp đồng; tránh gọi `available(...)` làm expected cho chính service có thể dùng cùng công thức sai.

Mã trên minh họa cách tổ chức dữ liệu, không khẳng định đã được chạy trong một project cụ thể. Khi áp dụng, cần cấu hình Java và điều chỉnh quy tắc theo mô hình của ứng dụng. Chẳng hạn, hệ thống cho phép hủy sau khi thu tiền sẽ cần lịch sử và bất biến khác với nhánh `CANCELLED` đơn giản của ví dụ.

## 7. Giữ cả phân bố phổ biến và các trường hợp hiếm có rủi ro

### 7.1. Xây hai nhóm dữ liệu phục vụ hai mục đích

**Nhóm gần phân bố vận hành** giúp tìm lỗi xuất hiện do hình dạng dữ liệu: một tenant có rất nhiều đơn, lịch sử hoàn dài, một tài khoản tham gia nhiều tổ chức hoặc một số tài nguyên nhận phần lớn truy cập.

**Nhóm kịch bản bảo mật có chủ đích** dành chỗ cho các trường hợp hiếm: giao dịch sát trần, người vừa mất quyền, coupon hết hạn đúng lúc xác nhận, callback cũ đến sau callback mới và ý định hoàn đang chờ kết quả bên ngoài.

Giữ nhãn và mục tiêu cho hai nhóm. Nếu tăng tỷ lệ trường hợp hiếm để kiểm tra bảo mật, không dùng tỷ lệ ấy để suy ra tần suất lỗi trong vận hành. Nếu chỉ lấy mẫu theo tần suất thực tế, có thể không có một trường hợp biên nào trong một lần chạy ngắn.

### 7.2. Bảo toàn mối tương quan

Sinh từng cột độc lập dễ tạo ra dữ liệu không đại diện:

- Trạng thái `REFUNDED` không có giao dịch thu hay hoàn tương ứng.
- Đơn có nhiều dòng nhưng discount phân bổ không cộng về tổng đơn.
- Tenant không có thành viên nhưng vẫn sở hữu hàng nghìn tác vụ do thành viên tạo.
- Mọi yêu cầu đều có idempotency key khác nhau dù mục tiêu là kiểm tra retry.
- Người tham gia nhiều tenant lại luôn có cùng vai trò ở tất cả tenant.

Generator nên sinh theo đồ thị nghiệp vụ: tạo tenant, membership, đơn và giao dịch; sau đó chọn một nhánh lịch sử hợp lệ; cuối cùng sinh request hợp lệ hoặc request tấn công theo kịch bản. Cách này giữ được các tương quan mà policy thực sự sử dụng.

Một cách phát triển generator là bắt đầu từ fixture tối thiểu đã hiểu rõ, rồi tăng số tenant, số dòng và độ dài lịch sử theo tham số. Giữ các mốc biên và đối chứng bằng quy tắc riêng để chúng không biến mất do ngẫu nhiên.

### 7.3. Dữ liệu cho concurrency phải tạo tranh chấp thực

Nếu mỗi thread dùng một order khác nhau, test chủ yếu đo xử lý song song. Để kiểm tra vượt hạn mức, nhiều tác vụ phải cùng tác động tới một tài nguyên hoặc một ràng buộc tổng.

Ví dụ với phần còn lại 50.000 VND:

- Hai ý định khác nhau, mỗi ý định hoàn 40.000: kiểm tra giữ chỗ nguyên tử.
- Hai lần gửi cùng một ý định hoàn 40.000: kiểm tra idempotency.
- Một yêu cầu hoàn 40.000 cạnh tranh với worker hoàn tất khoản `RESERVED`: kiểm tra chuyển trạng thái và cách tính phần còn lại.
- Hai đơn khác nhau cùng dùng coupon có một lượt sử dụng còn lại: kiểm tra ràng buộc ở cấp coupon, vượt ra ngoài một order.

Các tình huống này cần định danh riêng cho ý định và lần thử. Nếu fixture gom chúng thành một `requestId`, bộ test khó phân biệt một retry hợp lệ với một thao tác nghiệp vụ mới.

Với integration test, dùng connection/transaction riêng và điểm điều phối có chủ đích. Không lấy số lượng bản ghi lớn làm bằng chứng rằng hai thao tác đã cùng đi qua điểm tranh chấp.

## 8. Biến đổi dữ liệu vận hành mà vẫn giữ ý nghĩa kiểm thử

Khi một trích xuất được cho phép thực sự cần thiết, mục tiêu là giữ cấu trúc cần kiểm tra và loại bỏ khả năng sử dụng dữ liệu đó để truy cập, liên hệ hoặc nhận diện người thật ngoài phạm vi được phép.

### 8.1. Biến đổi nhất quán theo đồ thị

| Thành phần | Cách xử lý phù hợp với mục tiêu | Điều cần kiểm tra sau xử lý |
|---|---|---|
| ID và khóa ngoại | Ánh xạ nhất quán theo namespace/phạm vi cần thiết | Các cạnh trong tập dữ liệu vẫn trỏ đúng |
| Tên, email, số điện thoại | Thay bằng giá trị tổng hợp hoặc bỏ nếu không cần | Đúng định dạng test, không liên hệ người thật |
| Token, cookie, API key, bí mật ký | Loại bỏ và cấp thông tin riêng cho môi trường test | Không còn thông tin có thể xác thực ở production |
| Nội dung tự do, ghi chú, file đính kèm | Loại bỏ hoặc tạo lại theo cấu trúc cần kiểm tra | Không sót dữ liệu nhạy cảm trong text hoặc metadata |
| Timestamp | Biến đổi đồng bộ theo kịch bản | Giữ quan hệ trước/sau, tuổi dữ liệu và các biên cần thử |
| Số tiền, thuế, discount | Tái sinh nhất quán từ chính sách hoặc biến đổi có bảo toàn bất biến | Tổng và các phân bổ vẫn đúng |
| Provider reference, URL, webhook | Thay bằng định danh và đích của fake/sandbox | Không định tuyến tới dịch vụ thật |

Hash một email đơn thuần không bảo đảm ẩn danh: miền đầu vào có thể đoán được và giá trị băm vẫn cho phép liên kết bản ghi. Nếu cần ánh xạ nhất quán, chọn cơ chế được tổ chức chấp thuận và quản lý khóa/bảng ánh xạ tách khỏi dữ liệu test. Dữ liệu đã thay định danh vẫn có thể tái nhận diện qua tổ hợp thuộc tính hoặc nhóm hiếm.

ID không phải lúc nào cũng duy nhất toàn cục. Với khóa nghiệp vụ chỉ duy nhất trong tenant, bảng ánh xạ cần xét tenant và loại đối tượng, đồng thời giữ đúng quy tắc uniqueness của schema. Làm mất phạm vi này có thể vô tình tạo xung đột hoặc xóa mất tình huống cần kiểm tra.

### 8.2. Các biến đổi dễ phá hỏng test

- Thay mọi tenant thành cùng một tenant làm biến mất ranh giới phân quyền.
- Đổi mọi thời điểm thành thời điểm hiện tại làm mất dữ liệu hết hạn và lịch sử.
- Xóa mọi refund đang xử lý làm hạn mức trông lớn hơn trạng thái vận hành.
- Nhân mọi khoản tiền với một hệ số rồi làm tròn từng cột độc lập làm lệch tổng và phân bổ.
- Chuyển mọi user thành cùng role làm mất các cặp quyền đối chứng.
- Xóa phiên bản cũ làm test chỉ còn đường dữ liệu mới.
- Thay mọi key và provider reference bằng giá trị ngẫu nhiên mới làm mất quan hệ retry/callback trùng.

Sau biến đổi, chạy lại validator quan hệ và miền, kiểm tra các kịch bản bắt buộc còn tồn tại rồi mới sử dụng tập dữ liệu. Một bộ dữ liệu đã che thông tin nhưng mất điều kiện tấn công sẽ không đáp ứng mục tiêu parity.

## 9. Replay sự kiện và cô lập hiệu ứng bên ngoài

### 9.1. Giữ đúng danh tính của giao dịch, ý định và lần thử

Một chuỗi sự kiện kiểm thử có thể bao gồm:

```text
refundIntent = refund-intent-01, amount = 20000 VND
attempt-01: gửi tới provider, ứng dụng nhận timeout
providerEvent = event-01: provider xác nhận thành công
delivery-01: giao event-01 tới ứng dụng
delivery-02: giao lại cùng event-01
attempt-02: ứng dụng retry hoặc tra cứu theo hợp đồng tích hợp
```

`delivery-01` và `delivery-02` là hai lần giao cùng sự kiện. `attempt-01` và `attempt-02` gắn với cùng ý định. Nếu generator đổi `eventId` và `refundIntentId` trong mọi bản ghi, nó đã tạo các hoạt động độc lập và không còn kiểm tra được deduplication của chuỗi này.

Một lịch phát lại nên mô tả cả thứ tự và điểm tiêm lỗi:

| Bước | Dữ liệu hoặc lỗi đưa vào | Bất biến quan sát |
|---|---|---|
| 1 | Khoản hoàn 20.000 đã giữ chỗ | Chưa cho ý định khác sử dụng khoản này |
| 2 | Provider xử lý thành công, phản hồi bị mất | Giữ trạng thái chưa có kết quả cuối cùng ở local |
| 3 | Callback thành công đến | Chuyển đúng khoản giữ chỗ sang đã hoàn |
| 4 | Callback thành công đến lần nữa | Không ghi thêm một hiệu ứng tiền |
| 5 | Thông báo đang xử lý cũ đến muộn | Không kéo trạng thái thành công lùi lại |

Trong mô hình fixture ở mục 6, chuyển khoản 20.000 từ `RESERVED` sang `SUCCEEDED` làm `F` tăng 20.000 và `P` giảm 20.000. Tổng `F + P` giữ nguyên, nên phần còn lại vẫn là 50.000. Bộ dữ liệu này giúp phát hiện cả lỗi đếm hai lần lẫn lỗi giải phóng hạn mức quá sớm.

### 9.2. Tạo danh tính và chữ ký riêng cho môi trường test

Luồng replay cần tái tạo hợp đồng sự kiện bằng thông tin của môi trường test. Khi test kiểm tra chữ ký callback, tạo chữ ký bằng bí mật dành riêng cho test và thêm các ca chữ ký sai, payload bị thay đổi hoặc timestamp không còn hợp lệ theo hợp đồng.

Đường happy path với chữ ký test hợp lệ không được suy rộng thành bằng chứng rằng ứng dụng kiểm tra chữ ký production đúng. Contract test phải xác nhận adapter diễn giải đúng cấu trúc cần ký, encoding và nội dung theo hợp đồng tích hợp của hệ thống.

Thay URL đích, provider reference và thông tin liên hệ trong dữ liệu là một lớp bảo vệ. Cấu hình runtime còn phải chọn adapter fake/sandbox, queue test và nơi lưu file test. Trường `externalMode: fake` trong manifest chỉ mô tả ý định; bộ khởi tạo môi trường cần xác nhận cấu hình thực thi tương ứng.

Fake có thể ghi nhận lệnh gửi ra để test đối chiếu order, amount, currency và business intent. Có thể có nhiều lần thử HTTP hợp lệ nhưng chỉ một giao dịch tài chính; oracle phải phân biệt số lần thử với số hiệu ứng thành công.

### 9.3. Cô lập giữa các lần chạy mà vẫn giữ tính trùng bên trong kịch bản

Mỗi lần chạy có thể có namespace riêng cho tenant, định danh và idempotency key. Bên trong một kịch bản, các lần retry vẫn phải tái dùng đúng khóa của cùng ý định. Ánh xạ namespace cần được áp dụng đồng bộ trên mọi khóa ngoại và sự kiện liên quan.

Nếu các job dùng chung database hoặc queue, chỉ xóa database chưa đủ để reset. Worker cũ, cache, inbox/outbox, deduplication store và message đang chờ có thể làm thay đổi lần chạy sau. Lựa chọn database/schema/queue riêng hoặc cơ chế reset có phạm vi rõ ràng tùy môi trường; test phải biết dữ liệu nền nào được phép tồn tại.

## 10. Đưa chất lượng dữ liệu vào quy trình kiểm thử

### 10.1. Một pipeline dữ liệu có thể kiểm tra

```text
Chọn rủi ro và kịch bản
        ↓
Chốt schema, policy, clock và generator version
        ↓
Sinh hoặc biến đổi dữ liệu trong phạm vi được phép
        ↓
Kiểm tra quan hệ + bất biến + kịch bản bắt buộc
        ↓
Nạp vào môi trường test đã cô lập
        ↓
Đọc lại dữ liệu quan trọng sau migration/serialization
        ↓
Chạy thao tác hợp lệ và thao tác tấn công
        ↓
Đối chiếu response + trạng thái bền vững + hiệu ứng ngoài
```

Đọc lại sau khi nạp giúp phát hiện sự thay đổi do kiểu cột, precision thời gian, chuẩn hóa currency hoặc mapping ORM. Với test cần chứng minh constraint database, dữ liệu phải đi qua database thật tương ứng; validator trong bộ nhớ chỉ là một lớp kiểm tra bổ sung.

Nếu cần cắt một tập nhỏ từ tập lớn, giữ các quan hệ cần thiết cho kịch bản: tenant, membership, chính sách, dòng hàng, payment, refund và sự kiện liên quan. Cắt `orders` mà bỏ `memberships` hoặc payment có thể làm toàn bộ yêu cầu bị từ chối vì thiếu dữ liệu, che mất lỗi kiểm tra quyền hay trạng thái mà test muốn phát hiện.

### 10.2. Tổ chức theo chi phí và mục đích

| Nhóm chạy | Đặc điểm dữ liệu | Mục tiêu |
|---|---|---|
| Mỗi thay đổi liên quan | Fixture nhỏ, cố định, oracle rõ, có các cặp cho phép/từ chối | Hồi quy quy tắc và quyền cơ bản |
| Integration có chọn lọc | Lịch sử thật theo miền, transaction riêng, tranh chấp có điều phối | Ràng buộc database, idempotency và xử lý bất đồng bộ |
| Chạy mở rộng | Generator có seed, phân bố lệch, nhiều policy và lịch sử dài | Tìm tổ hợp khó thấy và lỗi phụ thuộc hình dạng dữ liệu |
| Kiểm tra trước phát hành phù hợp rủi ro | Dữ liệu và adapter test tương ứng cấu hình sẽ phát hành | Schema, mapping, cấu hình và hợp đồng xuyên các bước |

Không bắt buộc mọi test dùng tập lớn nhất. Chọn tập nhỏ nhất vẫn giữ được điều kiện gây lỗi để phản hồi nhanh và dễ giải thích. Khi tìm được lỗi từ generator, giữ seed để điều tra, rồi rút thành fixture hồi quy tối thiểu chứa nguyên nhân.

### 10.3. Bằng chứng cần lưu khi có lỗi

Thông tin hữu ích gồm dataset ID, phiên bản generator/schema/policy, seed, clock, mã kịch bản, định danh tổng hợp, điểm tiêm lỗi và trạng thái trước/sau. Với concurrency, lưu thêm thứ tự các mốc quan sát và ràng buộc bị vi phạm; seed đơn thuần không tái hiện được lịch chạy của thread hoặc thứ tự giao message.

Có thể tạo fingerprint từ biểu diễn chuẩn hóa của dữ liệu tổng hợp: sắp xếp theo khóa ổn định, chuẩn hóa số và thời gian, rồi tính digest. Fingerprint giúp nhận biết hai lần chạy có cùng dữ liệu đầu vào; nó không chứng minh dữ liệu đại diện đủ cho production và cũng không tự biến dữ liệu nhạy cảm thành dữ liệu an toàn.

Hạn chế artifact ở mức cần điều tra. Thường một đồ thị dữ liệu đã thu nhỏ và các hiệu ứng liên quan hữu ích hơn một bản dump đầy đủ. Artifact cũng cần được quản lý theo phạm vi dữ liệu mà nó chứa.

## 11. Đánh giá mức đủ và các lỗi thiết kế thường gặp

### 11.1. Đánh giá theo kịch bản, không chỉ theo số bản ghi

Một bảng theo dõi có thể ghi:

| Chỉ số | Câu hỏi nó trả lời |
|---|---|
| Số quy tắc có kịch bản dữ liệu và oracle | Quy tắc nào đã có bằng chứng kiểm thử? |
| Cặp được phép/bị từ chối theo owner, tenant, role và state | Test có thực sự phân biệt quyền và trạng thái không? |
| Tổ hợp phiên bản chính sách và tuổi giao dịch | Dữ liệu lịch sử có được kiểm tra không? |
| Mốc thời gian và giá trị biên bắt buộc | Có kiểm tra đúng các điểm quyết định không? |
| Tài nguyên nóng và các kiểu trùng/đảo thứ tự | Test có tạo đúng điều kiện concurrency và replay không? |
| Kết quả validator trước/sau khi nạp | Fixture có còn hợp lệ sau mapping và lưu trữ không? |
| Lỗi cũ đã được rút thành fixture hồi quy | Bộ dữ liệu có học được từ sự cố trước không? |

Không gộp các chiều này thành một phần trăm “giống production” nếu chưa xác định ý nghĩa và trọng số. Hai tập cùng kích thước có thể có mức bao phủ rủi ro rất khác nhau. Khi báo cáo, nêu kịch bản đã kiểm tra và khoảng trống còn lại.

### 11.2. Những dấu hiệu dễ gây cảm giác an toàn sai

| Thiết kế dữ liệu/test | Vì sao có thể bỏ lọt lỗi | Cách cải thiện |
|---|---|---|
| Chỉ có một tenant và một user | Owner, tenant và caller luôn trùng nhau | Tạo cặp khác owner cùng tenant và cặp khác tenant |
| Mọi đơn đều mới và chưa có lịch sử | Không chạm đường policy cũ hoặc hoàn một phần | Thêm giao dịch lịch sử, refund thành công và đang giữ chỗ |
| Mọi ID đều ngẫu nhiên và luôn mới | Không có retry hay sự kiện trùng thực sự | Dùng chung business intent/event ID đúng theo kịch bản |
| Tất cả user có vai trò quản trị | Đường quyền rộng che thiếu kiểm tra ở user thường | Chọn principal tương ứng từng quyền cần kiểm tra |
| Dữ liệu ngẫu nhiên vi phạm nhiều bất biến cùng lúc | Bị chặn sớm vì lý do ngoài mục tiêu | Baseline hợp lệ; mỗi kịch bản nhắm điều kiện cụ thể |
| Chỉ assert response | Ghi dữ liệu hoặc gọi provider vẫn có thể xảy ra trước khi trả lỗi | Kiểm tra commit, giữ chỗ, outbox và hiệu ứng ngoài |
| Expected được tính bằng helper production | Fixture và hệ thống cùng sai một cách | Dùng kết quả độc lập từ hợp đồng và ví dụ tính tay |
| Generator phụ thuộc thời gian hệ thống | Test đổi kết quả khi chạy vào ngày khác | Truyền clock và lưu mốc thời gian trong manifest |
| Cùng seed nhưng không khóa phiên bản generator | Không tái tạo được tổ hợp gây lỗi | Lưu đầy đủ các phiên bản và quy tắc tạo dữ liệu |
| Tập rất lớn nhưng mỗi tác vụ dùng tài nguyên riêng | Không tạo tranh chấp ở ràng buộc chung | Thiết kế nhóm cùng sử dụng order, coupon hoặc hạn mức |

### 11.3. Dùng thay đổi sai giả định để thử sức bộ dữ liệu

Hãy hỏi bộ test có thất bại nếu implementation:

- Bỏ điều kiện `tenantId` hoặc điều kiện chủ sở hữu trong truy vấn.
- Cho requester tự phê duyệt khi họ cũng có role approver.
- Chỉ kiểm tra tiền đã hoàn và bỏ qua tiền đang giữ chỗ.
- Dùng chính sách giá hiện hành để tính lại một giao dịch v1.
- Tạo key mới khi retry sau timeout.
- Xử lý callback cũ như một cập nhật trạng thái mới hơn.
- Tin số tiền khách gửi thay vì snapshot đã xác nhận.

Nếu dữ liệu không có tenant đối chứng, khoản giữ chỗ, phiên bản cũ hoặc callback đảo thứ tự, nhiều thay đổi sai trên sẽ không làm test đỏ. Đây là dấu hiệu cụ thể để bổ sung fixture; tăng thêm số lượng bản ghi cùng hình dạng sẽ không giải quyết được khoảng trống đó.

## 12. Bài tập áp dụng và tiêu chí hoàn thành

Thiết kế một bộ dữ liệu tổng hợp cho luồng mua hàng, duyệt điều chỉnh và hoàn tiền:

1. Tạo hai tenant; có hai khách cùng một tenant, một khách ở tenant còn lại và các vai trò duyệt theo chính sách.
2. Tạo một giao dịch thu 100.000 VND, đã hoàn 30.000 và đang giữ chỗ 20.000; ghi expected phần còn lại là 50.000.
3. Tạo đơn đối chứng khác tenant có cùng trạng thái và số tiền, cùng một đơn không đủ điều kiện hoàn.
4. Thêm giao dịch dùng chính sách v1 trong khi cấu hình hiện tại là v2; ghi rõ dữ liệu lịch sử cần dùng khi hoàn.
5. Thêm coupon hoặc báo giá ở ba mốc quanh thời điểm hết hạn, sử dụng clock cố định.
6. Mô tả các request đổi chủ thể, bỏ bước duyệt, sửa giá và yêu cầu vượt hạn mức từ baseline hợp lệ.
7. Tạo hai lần gửi cùng ý định và hai ý định khác nhau cùng cạnh tranh phần còn lại; chỉ rõ định danh nào phải trùng và định danh nào phải khác.
8. Tạo callback thành công bị giao lặp và một thông báo cũ đến sau; kiểm tra trạng thái cuối và số hiệu ứng tiền.
9. Viết validator kiểm tra quan hệ, policy, thời gian và tổng tiền; đọc lại dữ liệu sau khi nạp để kiểm tra mapping.
10. Ghi manifest và oracle độc lập cho từng kịch bản; rút gọn một kịch bản thành fixture tối thiểu có thể tái hiện.

Bộ dữ liệu đáp ứng mục tiêu khi mỗi kịch bản bắt buộc có baseline hiểu được, thao tác rõ ràng, đối chứng phù hợp và bằng chứng về trạng thái bền vững cùng hiệu ứng bên ngoài. Khả năng tái tạo phải bao gồm cả dữ liệu lẫn cách điều phối sự kiện hoặc tác vụ khi cần.

Giá trị của production parity nằm ở việc giữ đúng các quan hệ và điều kiện khiến quy tắc nghiệp vụ có thể bị phá vỡ. Một bộ fixture có mục tiêu, được quản lý phiên bản và có oracle độc lập giúp phát hiện những lỗi mà dữ liệu chỉ gồm các trường hợp thuận lợi sẽ bỏ qua.
