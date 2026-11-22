# Loại trùng tri thức mà vẫn giữ các trường hợp khác nhau

> **Chương:** Tái cấu trúc  
> **Học phần:** `CODE_QUALITY_FUNDAMENTALS` — hiểu những thuộc tính quyết định mã nguồn có đáng tin cậy, dễ hiểu và dễ thay đổi hay không.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao nguyên tắc **DRY (Don't Repeat Yourself)** hướng đến **tri thức hoặc quyết định có một nguồn sự thật**, chứ không bắt buộc xóa mọi đoạn mã giống nhau về mặt ký tự.
2. Phân biệt **trùng lặp cùng quy tắc nghiệp vụ** với **hai trường hợp khác nhau tình cờ có cùng công thức hoặc cấu trúc**.
3. Dựa vào **lý do thay đổi, chủ sở hữu chính sách, dữ liệu đầu vào, lỗi và vòng đời** để quyết định có nên hợp nhất code không.
4. Thực hiện refactor nhỏ trong Java để hai luồng cùng dùng một quy tắc tính giá, có kiểm thử bảo vệ hành vi và ranh giới tích hợp.
5. Tránh trừu tượng hóa sớm: cờ boolean điều khiển nhiều trường hợp, lớp cơ sở quá tổng quát, tham số tùy chọn chồng chất và sự ghép nối sai domain.
6. Giữ những khác biệt có ý nghĩa bằng **tên, kiểu, chính sách, cấu hình có phạm vi hoặc chiến lược riêng**, thay vì tạo một cơ chế chung khó hiểu.
7. Đánh giá kết quả refactor qua **số nơi phải sửa khi chính sách đổi, tính đúng đắn và khả năng đọc**, không chỉ qua số dòng được xóa.

## 1. Trùng dòng mã và trùng tri thức là hai việc khác nhau

Xét hai thao tác của hệ thống bán hàng: **xem báo giá** và **xác nhận thanh toán**. Cả hai phải dùng cùng chính sách giảm giá VIP. Nếu mỗi luồng tự cài đặt điều kiện và công thức, một lần đổi chính sách có thể phải sửa hai nơi. Nếu chỉ một nơi được cập nhật, khách hàng có thể thấy báo giá khác số tiền bị thu.

Ở đây, vấn đề không phải hai phương thức giống nhau vài dòng. Vấn đề là **một quyết định nghiệp vụ** — “khách VIP được giảm thế nào” — đang có **hai nguồn sự thật**.

Trong cùng hệ thống, một chức năng hỗ trợ phí vận chuyển cũng đang lấy **10%** của một số tiền. Nó có thể có vài câu lệnh giống tính giảm giá VIP. Nhưng chính sách vận chuyển thuộc nghiệp vụ khác, có người sở hữu khác và có thể thay đổi vào thời điểm khác. Gộp cả hai vào một hàm `calculateDiscount(...)` chung chỉ vì cùng phép chia 10 có thể khiến chúng bị ràng buộc sai.

Điều cốt lõi của bài này:

> **Hợp nhất những nơi đang diễn đạt cùng một quyết định; giữ tách biệt những quyết định độc lập, ngay cả khi code hiện tại trông giống nhau.**

Đó là cách vận dụng DRY để mã **dễ hiểu, đáng tin cậy và dễ thay đổi**, thay vì coi DRY là cuộc thi giảm số dòng.

### Câu hỏi để bắt đầu

Trước khi trích xuất một đoạn mã, hãy hỏi:

- Hai đoạn này có phải tuân theo **cùng một hợp đồng nghiệp vụ** không?
- Khi yêu cầu thay đổi, có **bắt buộc** sửa hai nơi giống nhau không?
- Nếu chỉ một bên thay đổi, đó là **lỗi đồng bộ** hay **sự khác nhau có chủ đích**?
- Một bên có những điều kiện, ngoại lệ, vòng đời hoặc yêu cầu tương thích riêng không?
- Việc chia sẻ mã làm người đọc **hiểu rõ hơn** hay phải suy đoán một cơ chế quá tổng quát?

Không trả lời được những câu này thì chưa nên kết luận chỉ bằng số lượng dòng giống nhau.

## 2. DRY nói về tri thức được biểu diễn một cách có thẩm quyền

Trong ngữ cảnh refactoring, **tri thức** có thể là:

- Quy tắc giảm giá theo ngưỡng và cách làm tròn.
- Quy tắc một đơn ở trạng thái nào được hủy.
- Chính sách ai được xem dữ liệu của tenant nào.
- Một định dạng JSON hoặc schema sự kiện đã công bố.
- Cách ánh xạ một trạng thái domain sang trạng thái lưu trữ.
- Quy tắc nhận dạng, kiểm tra hoặc chuẩn hóa dữ liệu.
- Quy trình tạo và kiểm chứng thay đổi tương thích.

Nếu hai phần của hệ thống cùng giữ một tri thức, việc cập nhật tri thức ở một phần nhưng quên phần còn lại có thể tạo lỗi. **DRY có ích nhất khi xác định đúng nơi sở hữu tri thức và khiến các nơi khác tham chiếu tới nó theo một hợp đồng rõ ràng.**

Tuy nhiên, “chỉ có một nguồn sự thật” không nhất thiết nghĩa là **chỉ có một file hoặc một phương thức**. Một hợp đồng công khai có thể được biểu diễn ở tài liệu, schema, mã server và bài kiểm thử. Các biểu diễn đó phục vụ **những nhiệm vụ khác nhau**. Vấn đề là chúng có **cơ chế bảo đảm thống nhất** hay không, chẳng hạn schema được kiểm tra tự động và contract test.

### Ba cách trùng lặp dễ nhầm

| Loại lặp lại | Ví dụ | Câu hỏi quyết định |
| --- | --- | --- |
| **Trùng văn bản/cấu trúc** | Hai vòng `for` giống nhau | Chúng có cùng trách nhiệm và lý do thay đổi không? |
| **Trùng tri thức nghiệp vụ** | Cùng ngưỡng VIP được cài ở báo giá và checkout | Có thể đưa một chính sách làm nguồn sự thật không? |
| **Nhiều biểu diễn có chủ đích** | Schema OpenAPI, DTO, tài liệu và contract test cùng nói về `amountDueVnd` | Có cơ chế kiểm tra các biểu diễn thống nhất không? |

Một phép kiểm tra “duplicate lines” có thể phát hiện dòng giống nhau, nhưng **không tự chứng minh** chúng biểu diễn cùng tri thức. Ngược lại, hai đoạn code nhìn hoàn toàn khác nhau vẫn có thể đang **nhân bản một chính sách**.

### Sự khác nhau cần giữ lại

Có những lý do chính đáng để hai phần cùng sử dụng một cấu trúc nhưng vẫn tách:

- Hai domain có **chủ sở hữu nghiệp vụ khác nhau**.
- Hai API có **vòng đời phiên bản** và thời hạn hỗ trợ khác nhau.
- Một phần xử lý dữ liệu đã xác thực, phần khác xử lý dữ liệu từ bên ngoài với quy tắc tin cậy khác.
- Tên trường và đơn vị trông giống nhau nhưng **nghĩa hoặc nguồn dữ liệu** khác.
- Hai thuật toán hiện có cùng kết quả trên dữ liệu nhỏ nhưng **khác quy tắc ở biên**.
- Một phần được sinh tự động từ nguồn chuẩn, phần khác là triển khai độc lập cần kiểm thử giao tiếp.

Giữ tách biệt đôi khi là điều giúp hệ thống **ít coupling hơn**.

## 3. Phân biệt cùng một chính sách với tình cờ cùng công thức

Hãy xét bốn đoạn tính toán:

~~~java
long vipDiscountVnd = subtotalVnd / 10;
long shippingSubsidyVnd = shippingFeeVnd / 10;
long partnerCommissionVnd = partnerRevenueVnd / 10;
long refundAdjustmentVnd = refundBaseVnd / 10;
~~~

Chúng có cùng công thức số học tại thời điểm hiện tại. Nhưng liệu cả bốn đều nên dùng `TenPercentCalculator` chung?

Không nhất thiết. Cần xem:

| Khía cạnh | VIP discount | Hỗ trợ phí vận chuyển | Hoa hồng đối tác | Điều chỉnh hoàn tiền |
| --- | --- | --- | --- | --- |
| **Mục đích** | Giảm số tiền khách phải trả | Giảm phí giao được thu | Phân chia doanh thu với đối tác | Tính khoản điều chỉnh khi hoàn |
| **Nguồn chính sách** | Chương trình khách VIP | Chiến dịch giao hàng | Hợp đồng với đối tác | Chính sách hoàn tiền |
| **Điều kiện áp dụng** | Có thể theo ngưỡng/tình trạng VIP | Khu vực, thời điểm, loại giao hàng | Loại đối tác, thỏa thuận | Trạng thái thanh toán và hoàn |
| **Quy tắc làm tròn** | Theo giá bán | Theo chính sách phí | Theo hợp đồng đối tác | Theo đối soát thanh toán |
| **Thời điểm đổi** | Khi đổi ưu đãi VIP | Khi đổi campaign giao hàng | Khi đổi hợp đồng | Khi đổi chính sách hoàn |

Những công thức giống nhau **không đủ chứng minh một quyết định chung**. Nếu ngày mai hoa hồng tăng lên 12% nhưng VIP vẫn 10%, hai chính sách phải được sửa độc lập. Trừ khi có bằng chứng chúng thực sự cùng tham chiếu một quy tắc được sở hữu chung, không nên dùng một constant `TEN_PERCENT` rồi để nhiều domain cùng phụ thuộc nó như một “chính sách toàn cầu”.

### Câu hỏi “cùng thay đổi vì cùng lý do?”

Một tiêu chí rất hữu ích:

> **Nếu yêu cầu thay đổi, các đoạn mã này có phải thay đổi cùng nhau vì cùng một lý do nghiệp vụ không?**

Nếu có: khả năng đang trùng tri thức, đáng cân nhắc một nguồn chính sách.

Nếu không: chúng là **những lý do thay đổi khác nhau**. Có thể tái sử dụng một tiện ích toán học thuần túy ở mức thấp khi thực sự giúp rõ ràng, nhưng **không được làm mất tên và hợp đồng nghiệp vụ riêng**.

Lịch sử `git` hoặc các PR sửa cùng nhiều nơi có thể là bằng chứng bổ sung, nhưng không phải chứng minh tuyệt đối. Những vùng code thường thay cùng nhau cũng có thể do một chiến dịch sản phẩm lớn hoặc một lần migration hạ tầng.

## 4. Ví dụ Java: trùng tri thức giảm giá VIP ở hai luồng

Giả sử chính sách bài học đã được thống nhất:

1. Giá trị `subtotalVnd` là số nguyên VND không âm.
2. Khách VIP được giảm **10%** khi tổng **từ 1.000.000 VND trở lên**.
3. Tiền giảm tính bằng phép chia nguyên `subtotalVnd / 10`, tức làm tròn xuống số đồng giảm.
4. Cả **báo giá** và **checkout** phải đưa ra cùng số tiền sau giảm nếu nhận cùng subtotal và trạng thái VIP.
5. Những bước sau như phí vận chuyển, voucher hoặc thanh toán thật không nằm trong hàm thuần minh họa.

Đây là **quy tắc giả định để học**, không tự động đại diện cho chính sách của một sản phẩm thực tế.

### 4.1. Code trước khi refactor

~~~java
final class QuoteService {
    long amountDueVnd(long subtotalVnd, boolean vip) {
        if (vip && subtotalVnd >= 1_000_000L) {
            return subtotalVnd - subtotalVnd / 10;
        }
        return subtotalVnd;
    }
}
~~~

~~~java
final class CheckoutService {
    long amountDueVnd(long subtotalVnd, boolean vip) {
        if (vip && subtotalVnd > 1_000_000L) {
            return subtotalVnd - subtotalVnd / 10;
        }
        return subtotalVnd;
    }
}
~~~

Cả hai luồng cùng diễn đạt **một chính sách VIP**, nhưng điều kiện ở `CheckoutService` dùng `>` thay vì `>=`. Tại đúng ngưỡng 1.000.000 VND, chúng trả kết quả khác nhau.

Có hai vấn đề cần **phân biệt**:

- **Defect:** checkout tính sai theo chính sách đã xác nhận tại ngưỡng.
- **Trùng tri thức:** hai nơi độc lập giữ cùng ngưỡng và công thức nên dễ lệch khi chính sách thay đổi.

Tái cấu trúc không nên âm thầm che việc sửa lỗi. Nếu hệ thống đã xử lý tiền theo cách sai, phải đánh giá phạm vi tác động, test, đối soát và quy trình sửa lỗi thích hợp, bên cạnh việc giảm nhân bản code.

### 4.2. Đưa quy tắc về một nơi có tên nghiệp vụ

~~~java
final class VipPricingPolicy {
    private static final long VIP_THRESHOLD_VND = 1_000_000L;

    long amountDueVnd(long subtotalVnd, boolean vip) {
        if (subtotalVnd < 0) {
            throw new IllegalArgumentException("Negative subtotal");
        }

        if (vip && subtotalVnd >= VIP_THRESHOLD_VND) {
            long vipDiscountVnd = subtotalVnd / 10;
            return subtotalVnd - vipDiscountVnd;
        }

        return subtotalVnd;
    }
}
~~~

Bây giờ các luồng dùng cùng chính sách:

~~~java
final class QuoteService {
    private final VipPricingPolicy vipPricingPolicy;

    QuoteService(VipPricingPolicy vipPricingPolicy) {
        this.vipPricingPolicy =
                java.util.Objects.requireNonNull(vipPricingPolicy);
    }

    long amountDueVnd(long subtotalVnd, boolean vip) {
        return vipPricingPolicy.amountDueVnd(subtotalVnd, vip);
    }
}

final class CheckoutService {
    private final VipPricingPolicy vipPricingPolicy;

    CheckoutService(VipPricingPolicy vipPricingPolicy) {
        this.vipPricingPolicy =
                java.util.Objects.requireNonNull(vipPricingPolicy);
    }

    long amountDueVnd(long subtotalVnd, boolean vip) {
        return vipPricingPolicy.amountDueVnd(subtotalVnd, vip);
    }
}
~~~

Lợi ích chính không phải đã xóa được bao nhiêu dòng `if`. Lợi ích là **ngưỡng và công thức VIP có một chủ sở hữu**. Khi chính sách VIP đổi, người sửa biết cần thay phần nào và kiểm tra những caller nào.

Nếu hai service trong thực tế còn phải gọi database hoặc gateway, việc chia sẻ policy **không làm hai service trở thành cùng một use case**. Chúng vẫn nên giữ ranh giới nghiệp vụ, transaction và các ràng buộc riêng.

### 4.3. Tên và ranh giới phải làm lộ tri thức

Tên `VipPricingPolicy` nêu rõ **chính sách nào** được sở hữu; tên `amountDueVnd` nêu rõ **đơn vị và ý nghĩa giá trị**. Một lớp `CommonHelper` với phương thức `calculate(x, flag)` có thể giảm dòng lặp nhưng khiến người đọc phải đoán công việc và điều kiện.

Đưa tri thức về một nơi không có nghĩa đưa mọi phép toán, validation và tác dụng phụ vào một lớp “tiện ích” khổng lồ. **Một nguồn sự thật chỉ hữu ích khi nguồn đó có trách nhiệm rõ ràng và dễ tìm.**

## 5. Kiểm thử trước và sau refactor: bảo vệ cả điểm giống lẫn khác

Vì ví dụ ban đầu chứa defect ở ngưỡng, cần **xác nhận đặc tả** trước khi sửa. Sau đó đặt kiểm thử cho cả chính sách chung và đường gọi ở hai service.

### 5.1. Unit test cho nguồn quy tắc

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class VipPricingPolicyTest {
    private final VipPricingPolicy policy = new VipPricingPolicy();

    @Test
    void discountsVipAtExactThreshold() {
        assertEquals(900_000L,
                policy.amountDueVnd(1_000_000L, true));
    }

    @Test
    void doesNotDiscountVipBelowThreshold() {
        assertEquals(999_999L,
                policy.amountDueVnd(999_999L, true));
    }

    @Test
    void nonVipDoesNotReceiveVipDiscount() {
        assertEquals(1_200_000L,
                policy.amountDueVnd(1_200_000L, false));
    }

    @Test
    void usesSpecifiedIntegerRounding() {
        assertEquals(900_005L,
                policy.amountDueVnd(1_000_005L, true));
    }

    @Test
    void rejectsNegativeSubtotal() {
        assertThrows(IllegalArgumentException.class,
                () -> policy.amountDueVnd(-1L, true));
    }
}
~~~

Trong bộ test, kỳ vọng về ngưỡng và làm tròn phải xuất phát từ **chính sách đã được xác nhận**, không copy mù quáng kết quả từ implementation cũ. Test sao chép một lỗi cũ sẽ chỉ bảo vệ lỗi đó.

### 5.2. Kiểm tra caller thật dùng quy tắc chung

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class VipPricingCallersTest {
    @Test
    void quoteAndCheckoutUseTheSharedVipPolicy() {
        VipPricingPolicy policy = new VipPricingPolicy();
        QuoteService quote = new QuoteService(policy);
        CheckoutService checkout = new CheckoutService(policy);

        assertEquals(900_000L,
                quote.amountDueVnd(1_000_000L, true));
        assertEquals(900_000L,
                checkout.amountDueVnd(1_000_000L, true));
    }
}
~~~

Test này phát hiện một caller vô tình giữ logic cũ hoặc dùng giá trị khác tại ngưỡng. Nhưng nó **chưa chứng minh** adapter thanh toán thật dùng số tiền sau giảm, JSON response trả đúng đơn vị, hoặc mọi đường controller đang gọi service đúng. Khi có I/O và nhiều client, phải bổ sung **component/integration/contract tests** ở các ranh giới chứa rủi ro.

### 5.3. Không chỉ test hai kết quả bằng nhau

Nếu test duy nhất là:

~~~java
assertEquals(
        quote.amountDueVnd(subtotalVnd, vip),
        checkout.amountDueVnd(subtotalVnd, vip));
~~~

thì **hai hàm cùng sai** vẫn có thể làm test xanh. Hãy có ít nhất một **oracle độc lập**: kỳ vọng cụ thể từ đặc tả nghiệp vụ, ví dụ 900.000 VND tại đúng ngưỡng. Kiểm thử tương đương giữa hai luồng **bổ sung**, không thay thế kiểm thử tính đúng đắn.

## 6. Khi trùng cú pháp nhưng phải giữ hai chính sách riêng

Giờ xét một chính sách **hỗ trợ phí vận chuyển**.

Giả định tạm thời, chiến dịch phí giao đang hoạt động thì giảm 10% trên phí giao, **không có ngưỡng VIP**. Công thức có dòng tương tự giảm giá VIP, nhưng ngữ nghĩa và điều kiện khác:

~~~java
final class ShippingCampaignPolicy {
    long feeAfterCampaignVnd(
            long originalShippingFeeVnd,
            boolean campaignActive
    ) {
        if (originalShippingFeeVnd < 0) {
            throw new IllegalArgumentException("Negative shipping fee");
        }

        if (campaignActive) {
            long subsidyVnd = originalShippingFeeVnd / 10;
            return originalShippingFeeVnd - subsidyVnd;
        }

        return originalShippingFeeVnd;
    }
}
~~~

**Không nên** thay cả `VipPricingPolicy` và `ShippingCampaignPolicy` bằng một hàm chung `discountTenPercent(long amount, boolean enabled)` rồi làm mất các khác biệt:

- VIP có **ngưỡng tổng tiền**; chiến dịch phí giao không có ngưỡng ấy.
- Điều kiện **vip** khác **campaignActive**.
- Chính sách làm tròn, trần hỗ trợ hoặc miễn phí hoàn toàn có thể thay đổi độc lập.
- Nếu mai chiến dịch hỗ trợ phí giao chuyển từ 10% sang 20%, **không được** kéo theo chính sách VIP.
- Nếu thay điều kiện VIP do quy tắc thành viên, không nên thay logic vận chuyển.

Một thiết kế có thể chia sẻ **phép toán thuần** như tính phần trăm nếu việc đó thực sự giảm lỗi và có hợp đồng số học rõ. Tuy nhiên, **tri thức về điều kiện, mức áp dụng và người sở hữu** phải nằm ở từng policy.

### Bài test chứng minh sự khác biệt có chủ đích

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class DistinctPoliciesTest {
    @Test
    void vipNeedsThresholdButShippingCampaignDoesNot() {
        VipPricingPolicy vip = new VipPricingPolicy();
        ShippingCampaignPolicy shipping =
                new ShippingCampaignPolicy();

        assertEquals(500_000L,
                vip.amountDueVnd(500_000L, true));

        assertEquals(90_000L,
                shipping.feeAfterCampaignVnd(100_000L, true));
    }

    @Test
    void differentFlagsControlDifferentBusinessCases() {
        VipPricingPolicy vip = new VipPricingPolicy();
        ShippingCampaignPolicy shipping =
                new ShippingCampaignPolicy();

        assertEquals(900_000L,
                vip.amountDueVnd(1_000_000L, true));

        assertEquals(100_000L,
                shipping.feeAfterCampaignVnd(100_000L, false));
    }
}
~~~

Hai chính sách có thể được tính cùng nhau trong một đơn, nhưng vẫn là **hai quyết định độc lập**. Test giữ rõ các khác biệt thay vì ép hai kết quả “đều phải giảm 10%” ở mọi điều kiện.

## 7. Dấu hiệu một abstraction đang gom nhầm các trường hợp

Trong quá trình giảm trùng lặp, một abstraction quá rộng có thể tạo kiểu code như sau:

~~~java
// Phản ví dụ: chữ ký quá tổng quát, mơ hồ về nghiệp vụ.
long calculate(
        long amount,
        boolean vip,
        boolean shipping,
        boolean refund,
        boolean campaignActive,
        boolean specialCase
) {
    // Nhiều nhánh kiểm tra cờ và thay đổi công thức.
    throw new UnsupportedOperationException("Illustrative anti-pattern");
}
~~~

Mã phản ví dụ không nhằm chạy nghiệp vụ. Nó cho thấy **sự gia tăng cờ điều khiển** để nhét nhiều use case khác nhau vào một đầu mối.

### Những mùi thiết kế đáng chú ý

| Dấu hiệu | Câu hỏi nên hỏi | Hướng cải thiện có thể phù hợp |
| --- | --- | --- |
| Hàm có nhiều boolean `isX` | Có đang trộn nhiều quyết định không? | Tách policy có tên; dùng kiểu biểu diễn hành động nếu phù hợp |
| `switch` theo loại nghiệp vụ tăng liên tục | Các trường hợp có vòng đời độc lập không? | Tách trách nhiệm hoặc chiến lược theo domain |
| Lớp `CommonUtils` biết domain rất rộng | Chủ sở hữu thực của quy tắc là ai? | Đưa tri thức về module sở hữu |
| Mỗi caller truyền 4 giá trị giả/`null` cho tham số không dùng | Hợp đồng chung có bao trùm quá nhiều trường hợp không? | Phân tách interface hoặc use case |
| Mọi thay đổi ở một policy làm test nhiều policy khác thất bại | Các trường hợp có bị coupling sai không? | Xem lại ranh giới và cách cấu hình |
| Một bên phải dùng constant đặc biệt để “né” logic chung | Abstraction có đang ép trường hợp khác biệt không? | Tách logic có nghĩa riêng |
| Tên chung chung như `process`, `doWork`, `handle` | Người đọc có dự đoán được hành vi không? | Đặt tên theo trách nhiệm và kết quả |
| Chỉ thay đổi code chung vì một caller | Các caller khác có bị ảnh hưởng không chủ ý? | Kiểm tra nghĩa thay đổi và hợp đồng các bên |

Đừng coi mọi `switch` hay boolean là lỗi. Một lựa chọn đơn giản, đủ rõ cho vài trường hợp có thể tốt hơn hệ thống class phức tạp. **Chỉ tách khi có khác biệt cần diễn đạt hoặc chi phí thay đổi thực sự**, không phải vì muốn “đạt chuẩn thiết kế”.

## 8. Chọn ranh giới tái sử dụng: thuật toán, chính sách hay luồng nghiệp vụ?

Một hệ thống thường có ba lớp nhu cầu khác nhau:

1. **Phép toán/thuật toán thuần:** cộng số, làm tròn đã xác định, kiểm tra định dạng.
2. **Chính sách nghiệp vụ:** VIP được giảm khi nào, phí giao được hỗ trợ đến đâu, trạng thái nào cho phép hủy.
3. **Use case/luồng:** tạo báo giá, checkout, hoàn tiền, lập báo cáo; bao gồm quyền, transaction, I/O và tác dụng phụ.

Các lớp có thể dùng nhau nhưng không nhất thiết phải được **gộp**.

~~~mermaid
flowchart TD
    Q["QuoteService"] --> V["VipPricingPolicy: một nguồn quy tắc VIP"]
    C["CheckoutService"] --> V
    C --> S["ShippingCampaignPolicy: quy tắc phí giao riêng"]
    V --> M["Phép toán số học có hợp đồng rõ (nếu cần)"]
    S --> M
    C --> P["Payment adapter / transaction"]
    Q --> R["Quote response"]
~~~

Trong sơ đồ:

- Hai service được chia sẻ **một tri thức VIP**, vì phải thay đổi cùng nhau khi chính sách VIP đổi.
- Chính sách phí giao vẫn riêng vì có lý do thay đổi khác.
- Một phép toán cấp thấp có thể tái sử dụng nếu cùng hợp đồng về số học/rounding, nhưng nó **không sở hữu chính sách**.
- Quote và checkout vẫn giữ **đường đi riêng**; việc checkout gọi payment adapter không phải nhiệm vụ của quote.

### Đưa code về đúng module sở hữu

Không nên chuyển mọi hàm giống nhau vào `shared/common` ở tầng cơ sở chỉ để xóa duplicate warning. Làm vậy có thể khiến tầng thấp phụ thuộc tên và dữ liệu của nhiều domain, hoặc nhiều module phải thay cùng một thư viện chung vì yêu cầu của một module.

Một thư viện dùng chung chỉ phù hợp khi:

- Nó có **hợp đồng tương đối ổn định** giữa những nơi sử dụng.
- Chủ sở hữu và chu kỳ phát hành/phiên bản rõ.
- Việc chia sẻ đem lại **giảm trùng tri thức thật** hoặc giải quyết một kỹ thuật ổn định, không chỉ vài dòng code.
- Các consumer có thể nâng cấp mà không bị phá vỡ ngoài kế hoạch.

Trong trường hợp chưa chắc chắn, **trùng một ít code đơn giản** có thể an toàn hơn phụ thuộc chéo vào một abstraction sai.

## 9. Đừng quên dữ liệu, lỗi và các trường hợp biên

Hai đoạn giống nhau ở **happy path** có thể khác ở những điểm ít gặp:

| Khía cạnh | Câu hỏi bắt buộc trước khi hợp nhất |
| --- | --- |
| **Không có dữ liệu** | `null`, `Optional.empty()`, danh sách rỗng hay lỗi biểu thị điều gì ở từng use case? |
| **Đơn vị** | Đều là VND nguyên, hay một bên dùng cent, một bên dùng tỷ lệ? |
| **Làm tròn** | Làm tròn xuống, lên, gần nhất hay theo chính sách tài chính nào? |
| **Thời gian** | Điều kiện dựa theo UTC, ngày địa phương hay kỳ tính theo `ZoneId`? |
| **Trạng thái** | Một bên cho phép `DRAFT`, bên kia cần `PAID`? |
| **Quyền** | Có cần kiểm tra owner/tenant theo từng tác vụ khác nhau không? |
| **Lỗi phụ thuộc** | Timeout là retry được, hay không thể xác định đã xảy ra tác dụng phụ? |
| **Tương thích API** | Tên trường/enum/error code nào đang có client cũ sử dụng? |
| **Đồng thời** | Có race condition hoặc điều kiện phải kiểm tra ngay tại transaction không? |
| **Vòng đời** | Chính sách nào dự kiến đổi độc lập, bởi nhóm nào? |

Một refactor xóa duplication ở mặt cú pháp nhưng làm **mất ngữ nghĩa biên** là một hồi quy. Vì vậy phải có test cho cả **điểm giống bắt buộc** và **điểm khác cố ý**.

### Ví dụ: cùng câu “không có kết quả” nhưng khác nghĩa

- `findById` có thể trả `Optional.empty()` khi truy vấn thành công nhưng không có bản ghi.
- Một lời gọi đến database bị timeout phải giữ tín hiệu lỗi, không chuyển thành empty.
- `search` có thể trả danh sách rỗng khi không có phần tử phù hợp.

Ép mọi trường hợp vào hàm `getOrEmpty(...)` sẽ tạo **trùng cách biểu diễn sai** thay vì xóa tri thức thừa. Hãy dựa vào hợp đồng thực tế để quyết định.

## 10. Không nhầm lặp lại có chủ đích ở ranh giới API với nợ nội bộ

Một DTO hoặc schema có thể có trường cũ và trường mới trong giai đoạn di chuyển:

~~~json
{
  "orderId": "OD-123",
  "totalVnd": 250000,
  "amountDueVnd": 250000
}
~~~

Thoạt nhìn, `totalVnd` và `amountDueVnd` chứa “dữ liệu trùng lặp”. Nhưng nếu `totalVnd` đang được client v1 sử dụng, việc giữ hai trường có thể là **một cách bảo vệ tương thích** trong giai đoạn chuyển đổi.

Điều cần thống nhất:

1. Hai trường có **cùng ngữ nghĩa và đơn vị** trong giai đoạn hỗ trợ không?
2. Dữ liệu có được lấy từ **cùng nguồn**, tránh tự tính riêng rồi lệch nhau không?
3. Trường cũ còn được bảo đảm `required` theo hợp đồng nào?
4. Consumer nào cần chuyển đổi, khi nào có thể thu hẹp hợp đồng?
5. Contract test nào phát hiện việc vô tình xóa hoặc đổi nghĩa một trường?

Đừng áp dụng “DRY nên xóa một trong hai field” như một lý do đủ để phá API. **Lặp dữ liệu có mục đích tương thích** khác với **nhân bản quy tắc tính giá**. Khi hết thời hạn hỗ trợ, loại bỏ trường cũ theo lộ trình rõ ràng.

### Nhiều biểu diễn dữ liệu không tự là lỗi thiết kế

Entity, DTO, schema, event và test fixture đôi khi đều mô tả một khái niệm vì chúng phục vụ **ranh giới khác nhau**. Muốn tránh drift, dùng mapping rõ, schema validation và contract test. Không nhất thiết trả entity database trực tiếp qua API chỉ vì muốn “một mô hình duy nhất”; làm vậy có thể lộ trường nội bộ hoặc ghép chặt API vào database.

## 11. Phân biệt sinh mã, template và trùng tri thức

Có trường hợp nhiều file giống nhau vì cùng được tạo từ schema, template hoặc DSL. Việc sửa từng bản sinh ra bằng tay sẽ khiến code **mất đồng bộ với nguồn chuẩn**.

Ví dụ:

~~~text
OpenAPI / schema được sở hữu
      ├── Java client sinh tự động
      ├── DTO cho consumer khác
      └── tài liệu hợp đồng
              ↓
        Contract tests kiểm tra hành vi triển khai
~~~

Ở đây, cách giảm trùng tri thức không phải xóa tất cả lớp được sinh. Thay vào đó:

- Sửa **nguồn đã được xác định là chuẩn**.
- Sinh lại artifact theo quy trình có phiên bản.
- Kiểm tra diff để phát hiện thay đổi hợp đồng ngoài ý muốn.
- Test tính tương thích với consumer được hỗ trợ.
- Không sửa thủ công generated code nếu lần build sau sẽ ghi đè.

Ngược lại, không nên vội tạo code generator cho vài đoạn trùng ngắn, vì bản thân generator, template, pipeline và việc debug code sinh ra cũng có chi phí bảo trì.

**Điểm quyết định:** tri thức gốc đang ở đâu, các bản khác được cập nhật ra sao và người đọc có kiểm tra được sự thống nhất không?

## 12. Dùng lịch sử thay đổi để tìm trùng tri thức

Một tín hiệu hữu ích là **shotgun surgery**: thay một chính sách nhưng phải sửa nhiều file, nhiều layer, nhiều repository. Điều đó có thể gợi ý tri thức bị phân tán.

Ví dụ một thay đổi yêu cầu VIP giảm từ 10% xuống 12% khiến nhóm phải sửa:

- `QuoteService`
- `CheckoutService`
- `OrderEmailTemplate`
- `InvoiceBuilder`
- `LoyaltyReport`

Trước khi gom cả năm vào một class, cần phân loại:

- `QuoteService` và `CheckoutService` có thể cần dùng **cùng nguồn chính sách giá hiện tại**.
- `InvoiceBuilder` có thể cần hiển thị **giá đã chốt của giao dịch**, không tính lại bằng chính sách hiện tại.
- `OrderEmailTemplate` có thể chỉ hiển thị số tiền **đã lưu**, không sở hữu logic giảm giá.
- `LoyaltyReport` có thể phân tích sự kiện lịch sử theo quy tắc đã áp dụng tại thời điểm phát sinh.

Nếu gộp mọi nơi vào một hàm “tính giá VIP mới nhất”, hóa đơn lịch sử có thể thay giá khi chính sách đổi — **một lỗi nghiệp vụ nghiêm trọng**.

Vì thế, “các file thường sửa cùng nhau” là **tín hiệu cần điều tra**, không phải giấy phép hợp nhất.

### Sự khác nhau giữa tính lại và đọc sự kiện đã chốt

- **Báo giá đang mở:** có thể áp dụng chính sách hiện tại, tùy hợp đồng.
- **Checkout chưa hoàn thành:** cần xác định chính sách lúc xác nhận và điều kiện khóa giá.
- **Hóa đơn đã phát hành:** thường phải phản ánh giá trị đã được chốt, không tự thay theo chính sách mới.
- **Báo cáo lịch sử:** phải dùng dữ liệu/tỷ lệ có ý nghĩa tại thời điểm giao dịch, không giả định mọi giao dịch đều theo policy hiện hành.

Khi các luồng dùng dữ liệu ở những thời điểm khác nhau, cùng biểu thức tính toán không tự nói lên cùng tri thức.

## 13. Refactor theo trình tự có bằng chứng

Một phương pháp ít rủi ro khi muốn loại trùng tri thức:

1. **Ghi nhận tình trạng:** xác định các đoạn giống nhau, các caller, những lỗi hoặc khó khăn đã quan sát.
2. **Xác định tri thức đang trùng:** viết một câu chính sách tường minh, ví dụ “hai luồng đều tính VIP theo cùng ngưỡng và rounding”.
3. **Liệt kê khác biệt có chủ đích:** điều kiện, dữ liệu, đơn vị, trạng thái, quyền, lỗi, thời điểm hiệu lực và hợp đồng API.
4. **Xác nhận đặc tả:** với chủ sở hữu nghiệp vụ hoặc tài liệu đã được duyệt. Không mặc nhiên coi code cũ là chuẩn.
5. **Thêm test trước khi sửa:** các ví dụ xác định hành vi đúng và khác biệt cần giữ. Với code khó hiểu, có thể dùng characterization test để mô tả **hiện trạng**, nhưng phải đánh dấu phần nào là defect.
6. **Trích xuất nguồn tri thức nhỏ nhất phù hợp:** một hàm, policy hoặc domain type có tên rõ.
7. **Chuyển từng caller và kiểm tra:** không thay mọi tầng cùng lúc nếu khó chẩn đoán.
8. **Kiểm tra ranh giới thật:** serialization, DB, transaction, quyền, client và event nếu bị tác động.
9. **Xóa bản sao khi đủ bằng chứng:** không giữ cả logic cũ lẫn mới mà không có lý do/điểm thu hẹp.
10. **Đọc lại thiết kế:** người mới có biết chính sách được định nghĩa ở đâu, còn trường hợp nào khác nhau không?

~~~mermaid
flowchart TD
    A["Phát hiện đoạn lặp"] --> B{"Cùng tri thức và lý do thay đổi?"}
    B -->|"Chưa rõ"| C["Thu thập hợp đồng, caller và ví dụ biên"]
    C --> B
    B -->|"Không"| D["Giữ policy riêng; tái sử dụng kỹ thuật nếu thật cần"]
    B -->|"Có"| E["Chọn chủ sở hữu chính sách"]
    E --> F["Test đúng và test khác biệt cần giữ"]
    F --> G["Trích xuất và chuyển caller từng bước"]
    G --> H["Test tích hợp/contract và review"]
    H --> I{"Có giữ hợp đồng và khác biệt có chủ đích?"}
    I -->|"Chưa"| J["Điều chỉnh/rollback thay đổi"]
    J --> F
    I -->|"Có"| K["Loại bản sao, ghi quyết định"]
~~~

**Tách thay đổi hành vi và thay đổi cấu trúc** giúp reviewer biết lỗi nào được sửa theo đặc tả, phần nào chỉ chuyển quyền sở hữu policy. Điều này đặc biệt quan trọng nếu code cũ đã lệch nhau.

## 14. Chọn kỹ thuật refactor theo mục đích

| Tình huống | Kỹ thuật có thể phù hợp | Rủi ro cần tránh |
| --- | --- | --- |
| Một công thức nhỏ lặp trong cùng lớp và cùng nghĩa | Extract Method | Tạo hàm quá nhỏ, tên mơ hồ |
| Cùng chính sách dùng ở nhiều use case | Extract Class/Policy | Tạo lớp dùng chung quá rộng |
| Mỗi use case có vài biến thể đã được mô tả | Strategy/Policy theo trách nhiệm | Tạo quá nhiều lớp cho hai nhánh đơn giản |
| Nhiều giá trị luôn xuất hiện cùng và cần bất biến chung | Introduce Value Object | Đưa quá nhiều domain khác nhau vào một kiểu |
| Mapping nhiều nơi cùng theo schema | Mapper rõ hoặc code generation có chủ | Làm mất tùy chọn/phân quyền của từng endpoint |
| Caller cần hợp đồng cũ và mới trong thời gian chuyển đổi | Adapter/Compatibility Layer | Giữ mã tương thích mãi không theo dõi |
| Điều kiện if giống nhau do hai domain độc lập | **Không gộp policy** | Coupling sai và khiến thay đổi lan rộng |
| Logic lịch sử cần giá đã chốt, logic mới cần chính sách hiện tại | Tách đọc dữ liệu đã chốt và tính theo policy | Tính lại giao dịch lịch sử bằng quy tắc mới |

Một kỹ thuật không tự là “thực hành tốt” nếu không giải quyết vấn đề cụ thể. **Đặt đúng ranh giới sở hữu quyết định** thường quan trọng hơn chọn mẫu thiết kế có tên nổi tiếng.

### Khi Strategy/Policy có ích

Nếu một loại quyết định thực sự có nhiều biến thể cùng **hợp đồng đầu vào/đầu ra** và được lựa chọn theo dữ liệu hoặc cấu hình được kiểm soát, một interface nhỏ có thể rõ hơn nhiều `if`:

~~~java
interface ShippingFeePolicy {
    long finalShippingFeeVnd(long originalFeeVnd);
}
~~~

Nhưng phải định nghĩa **ai chọn policy**, phạm vi hiệu lực và dữ liệu nào được tin cậy. Một interface chỉ có một implementation, không có khả năng biến thiên đã được chứng minh, có thể làm thiết kế phức tạp hơn mà không giảm trùng tri thức.

## 15. Khi chia sẻ logic lại làm tăng coupling

Một module `SharedRules` có vẻ tiện lợi. Tuy nhiên, nếu nó dần biết:

- trạng thái thanh toán,
- quyền nhân viên,
- chính sách VIP,
- phí vận chuyển,
- hợp đồng đối tác,
- quy tắc hoàn tiền,
- JSON response cho các API khác nhau,

thì mỗi thay đổi ở một domain có thể buộc cập nhật/test/phát hành một phần dùng chung của mọi domain.

### Đánh giá chi phí chia sẻ

Cần xem:

1. **Độ ổn định của hợp đồng chung:** cùng tên có thật sự cùng nghĩa lâu dài không?
2. **Tần suất thay đổi độc lập:** các domain có lịch phát triển riêng không?
3. **Chủ sở hữu:** nhóm nào có quyền thay chính sách, ai phê duyệt tác động tới caller?
4. **Chi phí phát hành:** thư viện chung phải version như thế nào; client độc lập có nâng cùng lúc không?
5. **Rủi ro dữ liệu/bảo mật:** có vô tình chia sẻ quyền hoặc thông tin nhạy cảm khác nhau không?
6. **Khả năng kiểm thử:** có test cho mỗi consumer và các trường hợp khác biệt không?
7. **Chi phí hiểu:** điều hướng qua một abstraction chung có dễ hơn đọc hai hàm riêng không?

Một lựa chọn có thể là **tái sử dụng một phép toán thuật toán ổn định**, nhưng **không tái sử dụng quyết định nghiệp vụ độc lập**. Hoặc giữ hai implementation nhỏ có test rõ, chấp nhận vài dòng tương tự để tránh coupling.

> **Mục tiêu không phải tối thiểu hóa duplication bằng mọi giá; mục tiêu là tối thiểu hóa chi phí và rủi ro khi phải hiểu, kiểm tra và thay đổi hệ thống.**

## 16. Một bảng quyết định: nên hợp nhất hay giữ tách?

| Câu hỏi | Nghiêng về **hợp nhất** | Nghiêng về **giữ tách** |
| --- | --- | --- |
| Hai đoạn nói về cùng một quy tắc? | Có cùng chính sách và người sở hữu | Chỉ giống phép toán |
| Khi quy tắc đổi, các nơi phải cùng đổi? | Bắt buộc đổi cùng lý do | Có quyền đổi độc lập |
| Hợp đồng input/output có đồng nhất? | Cùng đơn vị, lỗi, nullability, điều kiện | Khác dữ liệu, ngữ nghĩa, lỗi |
| Có khác biệt ở trạng thái/biên? | Không; hoặc biến thể rõ trong cùng policy | Khác biệt quan trọng, không nên ép chung |
| Chi phí giữ bản sao? | Đã gây bug hoặc sửa trùng nhiều lần | Ít thay, chưa có hậu quả đáng kể |
| Chi phí abstraction chung? | Nhỏ, tên rõ, ownership ổn | Tạo dependency chéo, nhiều boolean hoặc phiên bản |
| Khả năng kiểm chứng? | Có test cho policy và từng caller | Chưa xác minh hành vi/caller |
| Vòng đời API/data? | Có thể chuyển đổi an toàn | Cần duy trì hợp đồng cũ hoặc dữ liệu lịch sử |

Đây là khung **định hướng thảo luận**, không phải bảng cộng điểm máy móc. Một khác biệt về bảo mật hoặc tính đúng đắn có thể quan trọng hơn nhiều dấu “nghiêng về hợp nhất”.

## 17. Đo kết quả refactor bằng khả năng thay đổi, không chỉ số dòng

Một pull request giảm từ 300 dòng xuống 180 dòng chưa chắc đã cải thiện chất lượng nếu:

- Hàm chung đòi nhiều tham số khó hiểu.
- Mỗi lần sửa một policy làm ba use case khác hỏng.
- Các lỗi quan trọng không còn được diễn đạt rõ.
- Ranh giới quyền và transaction bị trộn.
- Client cũ không còn đọc được JSON.
- Test xanh vì chỉ so hai implementation cùng sai.

Những câu hỏi đánh giá có ích hơn:

- Với **một yêu cầu VIP mới**, giờ phải sửa ở **mấy nơi có quyền quyết định**?
- Thay chính sách phí giao có ảnh hưởng tới VIP không? Nếu có, **vì sao**?
- Người đọc biết **policy nào là nguồn sự thật** và khác biệt nào là chủ đích không?
- Test phát hiện lỗi ở ngưỡng, null, dữ liệu biên và những caller thật không?
- Cách mới có tạo dependency chéo hoặc tăng số tầng phải đọc không?
- Có giữ API/DB contract, quyền và dữ liệu lịch sử không?
- Thời gian review, CI và số lỗi liên quan giảm qua nhiều thay đổi tương đương không?

Không thể quy toàn bộ biến động metric cho refactor chỉ từ một lần đo trước/sau. Mức độ khó công việc, thay đổi yêu cầu và môi trường kiểm thử có thể khác. Cần gắn bằng chứng với **cơ chế giảm rủi ro cụ thể**, không chỉ dashboard đẹp.

## 18. Những ngộ nhận thường gặp

**“Hai đoạn code giống nhau thì luôn phải gộp.”** Trùng cú pháp không chứng minh trùng tri thức; hai domain có thể đổi độc lập.

**“DRY nghĩa là chỉ được có một biểu diễn dữ liệu.”** DTO, schema, event và entity có thể cần tồn tại ở ranh giới khác nhau; dùng mapping và contract test để giữ nhất quán.

**“Càng nhiều lớp chung càng dễ bảo trì.”** Abstraction sai làm tăng coupling, phạm vi ảnh hưởng và thời gian hiểu.

**“Hai chính sách đang cùng mức 10% nên phải dùng một constant.”** Mức bằng nhau hiện tại không bảo đảm cùng lý do thay đổi.

**“Extract Method luôn là cải tiến.”** Trích xuất không có tên nghĩa hoặc chia logic thành quá nhiều mảnh có thể giảm khả năng đọc.

**“Đưa logic vào helper dùng chung là hết trùng lặp.”** Nếu helper có trách nhiệm mơ hồ, nhiều cờ và biết quá nhiều domain, chỉ đang **giấu** trùng tri thức sau abstraction.

**“Refactor có thể âm thầm sửa bug luôn.”** Sửa defect và bảo toàn hành vi cấu trúc là hai loại thay đổi cần test, mô tả và review rõ.

**“Nếu cả báo giá lẫn checkout ra cùng kết quả thì chắc đúng.”** Hai implementation có thể cùng sai; cần kỳ vọng độc lập từ đặc tả.

**“Cùng thay đổi trong lịch sử là bằng chứng đủ để gộp.”** Hóa đơn lịch sử và giá đang tính có thể đổi trong cùng chiến dịch nhưng phải giữ quy tắc thời điểm khác nhau.

**“Xóa field cũ giúp DRY hơn nên không cần xét client.”** API công khai có hợp đồng tương thích; đôi khi giữ hai field là yêu cầu có chủ đích.

**“Một ít duplicate code luôn là nợ kỹ thuật nghiêm trọng.”** Số dòng lặp là tín hiệu cần xem xét, không tự cho biết tác động.

**“Gộp nhiều use case sẽ giảm số test.”** Khi use case vẫn có khác biệt quan trọng, vẫn phải test riêng tại ranh giới của chúng.

## 19. Bài tập thực hành

### Bài tập A — xác định tri thức đang trùng

Hai phương thức đều giảm VIP theo ngưỡng từ 1.000.000 VND, một ở báo giá, một ở checkout. Hãy:

1. Viết **một câu mô tả chính sách** hai phương thức phải cùng tuân thủ.
2. Xác định lỗi có thể xảy ra khi một bên dùng `>`, bên kia dùng `>=`.
3. Đặt tên cho một policy chung và chỉ ra caller nào dùng policy ấy.
4. Nêu một test **oracle từ đặc tả** và một test xác nhận hai caller.
5. Giải thích vì sao việc hợp nhất policy không đồng nghĩa gộp hai use case.

### Bài tập B — giữ hai trường hợp khác nhau

`VipPricingPolicy` và `ShippingCampaignPolicy` cùng có phép chia 10. Ngày mai chiến dịch giao hàng đổi lên 20%, còn VIP giữ 10%.

Hãy:

1. Chỉ ra **lý do thay đổi** của từng policy.
2. Giải thích vì sao một `DiscountManager` chung với nhiều cờ có thể gây rủi ro.
3. Đề xuất cách giữ tên/kiểu/hợp đồng riêng mà vẫn tránh lặp lại những phép toán thật sự ổn định nếu cần.
4. Viết hai test để khi đổi phí giao, chính sách VIP **không thay đổi**.
5. Nêu trường hợp nào một tiện ích tính phần trăm chung là hợp lý.

### Bài tập C — đừng tính lại lịch sử

Một báo cáo hóa đơn lưu `amountDueVnd` đã chốt ở thời điểm bán. Một người đề xuất dùng `VipPricingPolicy` mới nhất để tính lại mọi hóa đơn vì “không nên lặp công thức”.

Hãy giải thích vì sao đây có thể là lỗi nghiêm trọng, phân biệt **chính sách hiện hành** và **sự kiện đã chốt**, đề xuất dữ liệu cần giữ và loại test cần có.

### Bài tập D — đánh giá abstraction nhiều boolean

Bạn thấy phương thức:

~~~java
long adjust(long value,
        boolean isRefund,
        boolean isShipping,
        boolean isVip,
        boolean isPartner,
        boolean special);
~~~

Hãy nêu các trách nhiệm có thể đang bị trộn, so sánh hai lựa chọn “giữ vài policy riêng” và “dùng một strategy interface”, rồi chọn hướng phù hợp với các giả định do bạn nêu rõ. Không mặc định phải dùng Strategy chỉ vì có nhiều cờ.

### Bài tập E — lộ trình refactor có tương thích

Một JSON response đang trả `totalVnd` cho nhiều client cũ. Nhóm muốn chuẩn hóa nội bộ thành `amountDueVnd` và loại việc tính giá ở controller.

Hãy lập kế hoạch nhỏ gồm:
- nguồn policy chung;
- mapping dữ liệu, tên trường và ý nghĩa đơn vị;
- test logic và contract test;
- thứ tự phát hành provider/consumer;
- điều kiện loại bỏ field cũ;
- cách rollback nếu client vẫn phụ thuộc hợp đồng cũ.

## 20. Câu hỏi tự kiểm tra

1. DRY tập trung vào trùng tri thức khác thế nào với phát hiện các dòng mã giống nhau?
2. Thế nào là “một nguồn sự thật” của một quyết định nghiệp vụ?
3. Vì sao hai đoạn cùng tính `value / 10` có thể phải tách?
4. Câu hỏi “cùng thay đổi vì cùng lý do” giúp đánh giá refactor thế nào?
5. Trong ví dụ VIP, lỗi hiện tại và nợ nhân bản khác nhau ở đâu?
6. Vì sao phải xác nhận đặc tả trước khi biến hai implementation lệch nhau thành một implementation chung?
7. Một test chỉ assert báo giá bằng checkout có thể bỏ sót loại lỗi nào?
8. Trong bài test, oracle độc lập là gì và vì sao cần thiết?
9. Giữ chính sách phí giao riêng có làm vi phạm DRY không? Hãy giải thích bằng người sở hữu và vòng đời.
10. Nêu ba dấu hiệu `CommonUtils` hoặc `DiscountManager` đang quá tổng quát.
11. Có nên trích xuất một hàm chung nếu các caller cần truyền nhiều tham số `null` không dùng? Tại sao?
12. Vì sao code sinh tự động và DTO tại các ranh giới không nhất thiết là trùng tri thức cần xóa?
13. Những trường hợp biên nào cần kiểm tra trước khi gộp hai chính sách tiền?
14. Vì sao một hóa đơn lịch sử không nên tự tính lại bằng policy VIP mới nhất?
15. Làm thế nào để giảm shotgun surgery mà không gom mọi trách nhiệm vào cùng một lớp?
16. Bạn sẽ kiểm tra gì về transaction, quyền và API compatibility sau refactor?
17. Khi nào một chút duplication có thể tốt hơn một abstraction dùng chung?
18. Đâu là dấu hiệu refactor thành công ngoài việc giảm số dòng?
19. Một thư viện dùng chung giữa nhiều module cần hợp đồng và ownership như thế nào?
20. Khi nào Strategy giúp biểu đạt biến thể, và khi nào nó chỉ tạo thêm phức tạp?

## Ghi nhớ

**Tái cấu trúc để loại trùng tri thức là làm cho mỗi quyết định có một nơi sở hữu rõ ràng, chứ không phải ép mọi đoạn mã giống nhau vào chung một hàm.** Hãy xác định điều gì **phải cùng thay đổi**, điều gì **được phép thay đổi độc lập**, rồi giữ các trường hợp khác nhau bằng tên, kiểu, policy và hợp đồng có ý nghĩa. Bảo vệ cả điểm chung và điểm khác bằng test; tách refactor khỏi sửa lỗi nghiệp vụ; kiểm tra ranh giới API, dữ liệu lịch sử, quyền và tác dụng phụ. Một refactor tốt giúp người sau biết **sửa ở đâu, tại sao sửa và những gì không được vô tình thay đổi** — đó mới là đóng góp lâu dài cho chất lượng mã.
